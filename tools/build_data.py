#!/usr/bin/env python3
"""令和8年度当初予算の附表「主な事業」の材料を検算し、画面が読む data.js を作る（標準ライブラリのみ）。

材料（inputs.lock.json に、リポジトリ・コミット・パス・sha256 を記録）:
  shiga-hino-plans  data/fuhyo/fuhyo-r8.json      附表の事業（書式は PLAN_SCHEMA.md §9）
                    data/audit_log/fuhyo-r8.tsv   附表の検収の台帳
                    data/sources_index.tsv        原典の台帳（fuhyo-r8 の行の url を使う）
                    data/plans/jisshi.json        実施計画（事業名を引く）
  hino-ronten       links/fuhyo.tsv               附表と実施計画の事業の対応（書式は LINK_SCHEMA.md）

材料は、このリポジトリと同じフォルダにある各リポジトリ（例 ../shiga-hino-plans）から読む。
別の場所にあるときは --src <フォルダ> で、各リポジトリを置いたフォルダを指定する。

検算:
  1. inputs.lock.json の sha256 と、いまのファイルが一致する
  2. 附表の事業が 181件で、key が重複しない（項目の形も PLAN_SCHEMA §9 に合う）
  3. 検収の台帳の行（先頭が # の説明の行を除く）がすべて checked=✓
  4. 対応の台帳（LINK_SCHEMA §5・§11 に合わせた5つ）
     a. 全行: from が fh:fuhyo-r8/<key>、to が node:jisshi/<key> か none:jisshi、method が fuhyo、
        status が confirmed か rejected（candidate が残っていれば判定の途中として止める）
     b. confirmed の行の from: 附表にその key があり、事業名を §4 で正規化した値が context と同じ
     c. confirmed の node の行: jisshi.json にその key の事業があり、その name が to_label と同じ
     d. confirmed の none の行: to_label が「記載なし」
     e. 附表の各事業が、confirmed の node が1行以上か、confirmed の none が1行だけ
  5. data/totals.json（当初予算の会計ごとの予算規模。原典から転記した正本）の単位が千円で、
     会計ごとの和が合計と一致し、出典の url・sha256・pdf_page がある
どれかが合わなければ data.js を書かずに終了コード 1 で止まる。
"""
import argparse, csv, hashlib, json, pathlib, re, sys, unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXPECTED_ITEMS = 181
FUHYO_ID = 'fuhyo-r8'
PLAN_ID = 'jisshi'

ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
ap.add_argument('--src', default=str(ROOT.parent), help='材料のリポジトリを置いたフォルダ（既定はこのリポジトリの親）')
args = ap.parse_args()
SRC = pathlib.Path(args.src).resolve()

errors = []


def fail_now():
    print('\n'.join(errors))
    print(f'検算 NG（{len(errors)}件）。data.js は書き出していません。')
    sys.exit(1)


# 1. lock --------------------------------------------------------------------
lock = json.loads((ROOT / 'inputs.lock.json').read_text(encoding='utf-8'))
files = {}
for ent in lock['inputs']:
    repo_dir = ent['repo'].split('/')[-1]
    p = SRC / repo_dir / ent['path']
    tag = f"{repo_dir}/{ent['path']}"
    if not p.is_file():
        errors.append(f'lock: {tag} がない（{p}）')
        continue
    b = p.read_bytes()
    h = hashlib.sha256(b).hexdigest()
    if h != ent['sha256']:
        errors.append(f"lock: {tag} の sha256 が違う（lock {ent['sha256'][:12]}… / いま {h[:12]}…。"
                      f"lock の commit は {ent['commit'][:7]}）")
    files[tag] = b.decode('utf-8')
if errors:
    fail_now()

FUHYO = f'shiga-hino-plans/data/fuhyo/{FUHYO_ID}.json'
AUDIT = f'shiga-hino-plans/data/audit_log/{FUHYO_ID}.tsv'
SINDEX = 'shiga-hino-plans/data/sources_index.tsv'
JISSHI = f'shiga-hino-plans/data/plans/{PLAN_ID}.json'
LINKS = 'hino-ronten/links/fuhyo.tsv'
for tag in (FUHYO, AUDIT, SINDEX, JISSHI, LINKS):
    if tag not in files:
        errors.append(f'lock: {tag} が inputs.lock.json に載っていない')
if errors:
    fail_now()


def read_tsv(text, skip_comments=False):
    lines = [l for l in text.split('\n') if l != '']
    if skip_comments:
        lines = [lines[0]] + [l for l in lines[1:] if not l.startswith('#')]
    head = lines[0].split('\t')
    rows = []
    for n, l in enumerate(lines[1:], 2):
        cells = l.split('\t')
        if len(cells) != len(head):
            errors.append(f'列の数が違う（{len(cells)}／見出し {len(head)}）: {l[:80]}')
            continue
        rows.append(dict(zip(head, cells)))
    return head, rows


# 2. 附表 -----------------------------------------------------------------------
fuhyo = json.loads(files[FUHYO])
if fuhyo.get('id') != FUHYO_ID:
    errors.append(f"附表: id が {fuhyo.get('id')!r}")
FIELDS = {'key': str, 'kubun': list, 'kan': str, 'name': str, 'desc': str,
          'details': list, 'amount': int, 'dept': list, 'page': int}
items = []
for p in fuhyo['pillars']:
    if not isinstance(p.get('no'), int) or not isinstance(p.get('name'), str):
        errors.append(f'附表: 柱の no・name の形が違う: {p.get("no")!r}')
    for it in p['items']:
        if set(it) != set(FIELDS):
            errors.append(f"附表: {it.get('key')} の項目が違う: {sorted(set(it) ^ set(FIELDS))}")
            continue
        for k, t in FIELDS.items():
            if not isinstance(it[k], t) or (t is int and isinstance(it[k], bool)):
                errors.append(f"附表: {it['key']} の {k} の型が違う")
        if not re.fullmatch(r'b[0-9]{3,}', it['key']):
            errors.append(f"附表: key の形が違う: {it['key']}")
        if any(k not in ('新規', '拡充') for k in it['kubun']):
            errors.append(f"附表: {it['key']} の kubun に新規・拡充以外がある: {it['kubun']}")
        if not it['dept']:
            errors.append(f"附表: {it['key']} の dept が空")
        items.append((p, it))
if len(items) != EXPECTED_ITEMS:
    errors.append(f'附表: 事業が {len(items)}件（{EXPECTED_ITEMS}件のはず）')
seen = {}
for _, it in items:
    seen[it['key']] = seen.get(it['key'], 0) + 1
dup = [k for k, c in seen.items() if c > 1]
if dup:
    errors.append(f'附表: key が重複: {dup}')
F = {it['key']: it for _, it in items}

# 原典の台帳
_, srows = read_tsv(files[SINDEX])
srow = [r for r in srows if r['id'] == FUHYO_ID and r['file'] == fuhyo['source']['file']]
if len(srow) != 1 or not srow[0]['url'].startswith('https://'):
    errors.append(f"原典の台帳: id={FUHYO_ID}・file={fuhyo['source']['file']} の行が {len(srow)}行（1行で url があるはず）")
    fail_now()
srow = srow[0]

# 3. 検収の台帳 -------------------------------------------------------------------
ahead, arows = read_tsv(files[AUDIT], skip_comments=True)
if 'checked' not in ahead:
    errors.append('検収の台帳: checked の列がない')
    fail_now()
not_ok = [r for r in arows if r['checked'] != '✓']
for r in not_ok:
    errors.append('検収の台帳: checked が ✓ でない行: ' + '\t'.join(r[h] for h in ahead))
if not arows:
    errors.append('検収の台帳: 行がない')

# 4. 実施計画と対応の台帳 ---------------------------------------------------------------
jisshi = json.loads(files[JISSHI])


def walk(o):
    if isinstance(o, dict):
        if o.get('type') == 'programs':
            yield o
        for v in o.values():
            yield from walk(v)
    elif isinstance(o, list):
        for v in o:
            yield from walk(v)


E = {}
for b in walk(jisshi):
    for g in b.get('groups', []):
        its = list(g.get('items', []))
        for s in g.get('subgroups', []):
            its += s.get('items', [])
        for it in its:
            k = it.get('key')
            if not k:
                errors.append(f"実施計画: key の無い事業がある: {it.get('name')}")
            elif k in E:
                errors.append(f'実施計画: key が重複: {k}')
            else:
                E[k] = it['name']
if not E:
    errors.append('実施計画: programs の事業が見つからない')


def norm(s):  # LINK_SCHEMA §4
    s = unicodedata.normalize('NFKC', s)
    s = re.sub(r'\n[0-9]+-[0-9]+', '', s)
    s = re.sub(r'-[0-9]+-', '', s)
    return re.sub(r'\s', '', s)


_, lrows = read_tsv(files[LINKS])
node_of = {k: [] for k in F}
none_of = {k: 0 for k in F}
for r in lrows:
    tag = f"links: {r['from']} → {r['to']}"
    mf = re.fullmatch(rf'fh:{FUHYO_ID}/(b[0-9]{{3,}})', r['from'])
    mn = re.fullmatch(rf'node:{PLAN_ID}/(e[0-9]{{3,}})', r['to'])
    is_none = r['to'] == f'none:{PLAN_ID}'
    if not mf or not (mn or is_none) or r['method'] != 'fuhyo':  # a
        errors.append(f'{tag}: from・to・method の形が違う')
        continue
    if r['status'] == 'candidate':
        errors.append(f'{tag}: candidate のまま（判定の途中）')
        continue
    if r['status'] not in ('confirmed', 'rejected'):
        errors.append(f"{tag}: status が {r['status']!r}")
        continue
    if r['status'] != 'confirmed':
        continue
    fk = mf.group(1)
    if fk not in F:  # b
        errors.append(f'{tag}: 附表に {fk} がない')
        continue
    if norm(F[fk]['name']) != r['context']:
        errors.append(f"{tag}: 附表の事業名「{F[fk]['name']}」が context「{r['context']}」と合わない")
    if mn:  # c
        ek = mn.group(1)
        if ek not in E:
            errors.append(f'{tag}: 実施計画に {ek} がない')
        elif E[ek] != r['to_label']:
            errors.append(f"{tag}: 実施計画の事業名「{E[ek]}」が to_label「{r['to_label']}」と違う")
        else:
            node_of[fk].append(ek)
    else:  # d
        if r['to_label'] != '記載なし':
            errors.append(f"{tag}: to_label が「記載なし」でない（{r['to_label']}）")
        else:
            none_of[fk] += 1
for k in F:  # e
    n, z = len(node_of[k]), none_of[k]
    if not ((n >= 1 and z == 0) or (n == 0 and z == 1)):
        errors.append(f'links: {k}（{F[k]["name"]}）の confirmed が node {n}行・記載なし {z}行')

# 5. 当初予算の総額（このリポジトリの data/totals.json。原典から転記した正本） ---------------------
totals = json.loads((ROOT / 'data/totals.json').read_text(encoding='utf-8'))
if totals.get('unit') != '千円':
    errors.append(f"totals: unit が千円でない（{totals.get('unit')!r}）")
acc = sum(a['amount'] for a in totals['accounts'])
if acc != totals['total']['amount']:
    errors.append(f"totals: 会計ごとの和 {acc:,} ≠ 合計 {totals['total']['amount']:,}")
src = totals['source']
if not src.get('url', '').startswith('https://') or not re.fullmatch(r'[0-9a-f]{64}', src.get('sha256', '')) \
        or not isinstance(src.get('pdf_page'), int):
    errors.append('totals: 出典の url・sha256・pdf_page の形が違う')

if errors:
    fail_now()

# 書き出し -----------------------------------------------------------------------
out_items = []
for p, it in items:
    out_items.append({
        'key': it['key'], 'pillar': p['no'], 'kubun': it['kubun'], 'kan': it['kan'],
        'name': it['name'], 'desc': it['desc'], 'details': it['details'], 'amount': it['amount'],
        'dept': it['dept'], 'page': it['page'],
        'jisshi': [{'key': ek, 'name': E[ek]} for ek in sorted(node_of[it['key']])],
    })
meta = {
    'fiscal_year': fuhyo['fiscal_year'],
    'source': {'id': FUHYO_ID, 'file': fuhyo['source']['file'], 'page_id': fuhyo['source'].get('page_id', ''),
               'label': srow['label'], 'url': srow['url'], 'fetched': srow['fetched']},
    'pillars': [{'no': p['no'], 'name': p['name']} for p in fuhyo['pillars']],
    'inputs': sorted({(e['repo'], e['commit']) for e in lock['inputs']}),
    'plan': {'id': PLAN_ID, 'name': jisshi['meta']['name']},
    'audit': {'rows': len(arows),
              'pdftext': sum(1 for r in arows if r['reviewer'] == 'auto:pdftext'),
              'ai': sum(1 for r in arows if r['reviewer'] == 'auto:ai'),
              'human': sum(1 for r in arows if not r['reviewer'].startswith('auto:'))},
    'totals': {'source': {k: src[k] for k in ('title', 'url', 'pdf_page', 'printed_page', 'fetched')},
               'accounts': totals['accounts'], 'total': totals['total']['amount']},
}
meta['inputs'] = [{'repo': r, 'commit': c} for r, c in meta['inputs']]
js = ['/* tools/build_data.py で生成。直接編集しない。材料と版は inputs.lock.json にある。 */',
      'const BUDGET = ' + json.dumps(meta, ensure_ascii=False)[:-1] + ', "items": [']
js += [json.dumps(o, ensure_ascii=False) + (',' if i < len(out_items) - 1 else '') for i, o in enumerate(out_items)]
js += [']};', '']
(ROOT / 'data.js').write_text('\n'.join(js), encoding='utf-8')

# 報告 ---------------------------------------------------------------------------
fmt = lambda n: f'{n:,}'
print(f'材料: {len(lock["inputs"])}ファイルとも sha256 が inputs.lock.json と一致')
print(f'附表: {len(items)}件、key の重複なし')
print(f'検収の台帳: {len(arows)}行すべて checked=✓')
nc = sum(1 for r in lrows if r['status'] == 'confirmed')
nr = sum(1 for r in lrows if r['status'] == 'rejected')
print(f'対応の台帳: confirmed {nc}行（実施計画の事業 {sum(len(v) for v in node_of.values())}行・記載なし {sum(none_of.values())}行）、'
      f'rejected {nr}行、candidate 0行')
print(f'  実施計画の事業に対応 {sum(1 for v in node_of.values() if v)}事業、記載なし {sum(1 for v in none_of.values() if v)}事業')
print('柱ごと:')
for p in fuhyo['pillars']:
    print(f"  柱{p['no']} {p['name']}: {len(p['items'])}件・{fmt(sum(i['amount'] for i in p['items']))}千円")
print(f"  合計: {len(items)}件・{fmt(sum(it['amount'] for _, it in items))}千円")
print(f"区分: 新規 {sum(1 for _, it in items if '新規' in it['kubun'])}件、拡充 {sum(1 for _, it in items if '拡充' in it['kubun'])}件")
print('当初予算の総額（data/totals.json）: ' + '・'.join(f"{a['name']} {fmt(a['amount'])}" for a in totals['accounts'])
      + f" ＝ 合計 {fmt(totals['total']['amount'])}千円（{src['title']} {src['printed_page']}ページ）")
print('検算 OK。data.js を書き出しました。')
