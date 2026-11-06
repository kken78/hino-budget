#!/usr/bin/env python3
"""当初予算の附表「主な事業」（令和3〜8年度）の材料を検算し、画面が読む data.js を作る（標準ライブラリのみ）。

材料（inputs.lock.json に、リポジトリ・コミット・パス・sha256 を記録）:
  shiga-hino-plans  data/fuhyo/fuhyo-r<n>.json          附表の事業（書式は PLAN_SCHEMA.md §9）。n は 3〜8
                    data/audit_log/fuhyo-r<n>.tsv       附表の検収の台帳
                    data/source_issues/fuhyo-r<n>.tsv   段3（文章の点検）の指摘と判断
                    data/sources_index.tsv              原典の台帳（fuhyo-r<n> の行の url を使う）
                    data/plans/jisshi.json              実施計画（事業名を引く）
  hino-ronten       links/fuhyo.tsv                     附表（令和8年度）と実施計画の事業の対応（書式は LINK_SCHEMA.md）
                    links/fuhyo-years.tsv               附表の事業の年度をまたぐ対応（LINK_SCHEMA.md「年度の台帳」）
  hino-town-docs    data/sources.tsv                    町の公開資料の台帳（yosan-r<n>-gaiyou の行で、当初予算の概要の
                                                        url・bytes・sha256 を確かめる）
このリポジトリ   data/totals-r<n>.json                 当初予算の会計ごとの予算規模（原典から転記した正本）

材料は、このリポジトリと同じフォルダにある各リポジトリ（例 ../shiga-hino-plans）から読む。
別の場所にあるときは --src <フォルダ> で、各リポジトリを置いたフォルダを指定する。

検算:
  1. inputs.lock.json の sha256 と、いまのファイルが一致する
  2. 附表: 年度ごとに事業数が決まった数（EXPECTED_ITEMS）で、key が重複しない（項目の形も PLAN_SCHEMA §9 に合う）。
     柱の番号と名前が6年で同じ。年度ごとの予算額の合計を数え、報告に出す
  3. 検収の台帳: 全行の列が合い、checked が ✓ か空、✓ の reviewer が auto:pdftext・auto:ai か人。
     ✓ でない行の note が PLAN_SCHEMA §11.3 の理由の表にある。照合の状況（§11.2 の N・M・a・b・c・U・F・X）を数える
     段3の台帳: status が決まった語彙のどれか。未判断の件数を数える
  4. 対応の台帳（links/fuhyo.tsv。令和8年度。LINK_SCHEMA §5・§11 に合わせた5つ）
     a. 全行: from が fh:fuhyo-r8/<key>、to が node:jisshi/<key> か none:jisshi、method が fuhyo、
        status が confirmed か rejected（candidate が残っていれば判定の途中として止める）
     b. confirmed の行の from: 附表にその key があり、事業名を §4 で正規化した値が context と同じ
     c. confirmed の node の行: jisshi.json にその key の事業があり、その name が to_label と同じ
     d. confirmed の none の行: to_label が「記載なし」
     e. 附表の各事業が、confirmed の node が1行以上か、confirmed の none が1行だけ
  5. 年度の台帳（links/fuhyo-years.tsv）
     a. 全行: from・to が fh:fuhyo-r<n>/<key> で from の年度が to の年度より前、method が name か manual、
        status が confirmed か rejected（candidate が残っていれば止める）
     b. confirmed の行: 両端の事業が附表にあり、from の事業名を正規化した値が context と同じ、to の事業名が to_label と同じ
     c. 1つの事業から同じ年度への confirmed は1行だけ。同じ年度から1つの事業への confirmed も1行だけ。
        つないで束ねた1本の中に、同じ年度の事業が2つ無い
  6. data/totals-r<n>.json: 単位が千円で、会計ごとの和が合計と一致し、出典の title・url・bytes・sha256 が
     hino-town-docs の台帳の yosan-r<n>-gaiyou の行と一致し、pdf_page・printed_page がある
どれかが合わなければ data.js を書かずに終了コード 1 で止まる。
"""
import argparse, hashlib, json, pathlib, re, sys, unicodedata

ROOT = pathlib.Path(__file__).resolve().parent.parent
YEARS = [3, 4, 5, 6, 7, 8]                       # 令和の年度
EXPECTED_ITEMS = {3: 155, 4: 166, 5: 168, 6: 177, 7: 184, 8: 181}
LINK_YEAR = 8                                     # 実施計画と突き合わせた附表の年度（links/fuhyo.tsv）
PLAN_ID = 'jisshi'
ISSUE_STATUS = {'未判断', 'ダッシュボードで対応', '原典どおり掲載(注記)', '原典どおり掲載', '対象外'}  # check_source_issues.py
# 検収の台帳の note と、画面の理由の対応（shiga-hino-plans の tools/audit_display.py、PLAN_SCHEMA §11.3）
REASON_MISMATCH = '人の確認で食い違いが見つかり、直している'
REASON_HOLD = '人が確かめたが、判断を保留している'
REASON_H1 = 'AI 2回の照合の結果がそろわない、または確信が高くない'
H2_REASONS = {
    '出典が4ページ以上(集計した値)': '原典の複数のページにわたる値を、数えたり集計したりした値',
    '数値でない': '数値でない項目（名前・年度など）',
    '出典の PDF がない': '原典の PDF が無い資料から引いた値',
    '出典ページがない、または PDF の範囲にない': '原典のページを特定できない値',
    '出典の PDF やページがない': '原典の PDF またはページを特定できない値',
}
NOT_YET = 'まだ照合していない'
REASON_ORDER = [REASON_MISMATCH, REASON_HOLD, REASON_H1, *dict.fromkeys(H2_REASONS.values()), NOT_YET]
HUMAN_SEEN = {REASON_MISMATCH, REASON_HOLD}       # 人がすでに見た理由（「人が確かめます」を添えない）
MACHINE = {'auto:pdftext': 'a', 'auto:ai': 'b'}

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

FUHYO = {y: f'shiga-hino-plans/data/fuhyo/fuhyo-r{y}.json' for y in YEARS}
AUDIT = {y: f'shiga-hino-plans/data/audit_log/fuhyo-r{y}.tsv' for y in YEARS}
ISSUES = {y: f'shiga-hino-plans/data/source_issues/fuhyo-r{y}.tsv' for y in YEARS}
SINDEX = 'shiga-hino-plans/data/sources_index.tsv'
JISSHI = f'shiga-hino-plans/data/plans/{PLAN_ID}.json'
LINKS = 'hino-ronten/links/fuhyo.tsv'
LINKS_Y = 'hino-ronten/links/fuhyo-years.tsv'
TOWN = 'hino-town-docs/data/sources.tsv'
for tag in (*FUHYO.values(), *AUDIT.values(), *ISSUES.values(), SINDEX, JISSHI, LINKS, LINKS_Y, TOWN):
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


def norm(s):  # LINK_SCHEMA §4
    s = unicodedata.normalize('NFKC', s)
    s = re.sub(r'\n[0-9]+-[0-9]+', '', s)
    s = re.sub(r'-[0-9]+-', '', s)
    return re.sub(r'\s', '', s)


# 2. 附表 -----------------------------------------------------------------------
FIELDS = {'key': str, 'kubun': list, 'kan': str, 'name': str, 'desc': str,
          'details': list, 'amount': int, 'dept': list, 'page': int}
# 任意の項目。読みの注（PLAN_SCHEMA §9 の sic。原典の誤字の箇所と正しい読み）。画面には出さず、本文は原典のまま。
OPTIONAL_FIELDS = {'sic'}
fuhyo = {}       # 年度 → JSON
items = {}       # 年度 → [(柱, 事業)]
F = {}           # 年度 → {key: 事業}
pillar_names = None
for y in YEARS:
    d = json.loads(files[FUHYO[y]])
    fuhyo[y] = d
    if d.get('id') != f'fuhyo-r{y}':
        errors.append(f"附表 r{y}: id が {d.get('id')!r}")
    fy = d.get('fiscal_year', {})
    if fy.get('label') != f'令和{y}年度' or fy.get('year') != 2018 + y:
        errors.append(f'附表 r{y}: fiscal_year が違う: {fy}')
    names = []
    its = []
    for p in d['pillars']:
        if not isinstance(p.get('no'), int) or not isinstance(p.get('name'), str):
            errors.append(f'附表 r{y}: 柱の no・name の形が違う: {p.get("no")!r}')
        names.append((p.get('no'), p.get('name')))
        for it in p['items']:
            if set(it) - OPTIONAL_FIELDS != set(FIELDS):
                errors.append(f"附表 r{y}: {it.get('key')} の項目が違う: {sorted((set(it) - OPTIONAL_FIELDS) ^ set(FIELDS))}")
                continue
            if 'sic' in it and not (isinstance(it['sic'], list) and all(
                    isinstance(x, dict) and isinstance(x.get('text'), str) and x.get('field') in ('name', 'desc', 'details')
                    for x in it['sic'])):
                errors.append(f"附表 r{y}: {it['key']} の sic の形が違う")
            for k, t in FIELDS.items():
                if not isinstance(it[k], t) or (t is int and isinstance(it[k], bool)):
                    errors.append(f"附表 r{y}: {it['key']} の {k} の型が違う")
            if not re.fullmatch(r'b[0-9]{3,}', it['key']):
                errors.append(f"附表 r{y}: key の形が違う: {it['key']}")
            if any(k not in ('新規', '拡充') for k in it['kubun']):
                errors.append(f"附表 r{y}: {it['key']} の kubun に新規・拡充以外がある: {it['kubun']}")
            if not it['dept']:
                errors.append(f"附表 r{y}: {it['key']} の dept が空")
            its.append((p, it))
    if len(its) != EXPECTED_ITEMS[y]:
        errors.append(f'附表 r{y}: 事業が {len(its)}件（{EXPECTED_ITEMS[y]}件のはず）')
    seen = {}
    for _, it in its:
        seen[it['key']] = seen.get(it['key'], 0) + 1
    dup = [k for k, c in seen.items() if c > 1]
    if dup:
        errors.append(f'附表 r{y}: key が重複: {dup}')
    if pillar_names is None:
        pillar_names = names
    elif names != pillar_names:
        errors.append(f'附表 r{y}: 柱の番号と名前が令和{YEARS[0]}年度と違う: {names}')
    items[y] = its
    F[y] = {it['key']: it for _, it in its}
if errors:
    fail_now()

# 原典の台帳
_, srows = read_tsv(files[SINDEX])
srow = {}
for y in YEARS:
    rs = [r for r in srows if r['id'] == f'fuhyo-r{y}' and r['file'] == fuhyo[y]['source']['file']]
    if len(rs) != 1 or not rs[0]['url'].startswith('https://'):
        errors.append(f"原典の台帳: id=fuhyo-r{y}・file={fuhyo[y]['source']['file']} の行が {len(rs)}行（1行で url があるはず）")
        continue
    srow[y] = rs[0]
if errors:
    fail_now()


# 3. 検収の台帳と段3の台帳 -----------------------------------------------------------
def reason(note):
    """✓ でない行の理由（PLAN_SCHEMA §11.3 の対応表）。表に無い note は None。"""
    mis, hold = ' / 不一致:' in note, ' / 保留:' in note
    if mis and hold:
        return None
    if mis:
        return REASON_MISMATCH
    if hold:
        return REASON_HOLD
    if note.startswith('要人確認:H1'):
        return REASON_H1
    if note.startswith('要人確認:H2 '):
        return H2_REASONS.get(note[len('要人確認:H2 '):].split(' / ')[0])
    if note == '':
        return NOT_YET
    return None


audit = {}
issues = {}
for y in YEARS:
    ahead, arows = read_tsv(files[AUDIT[y]], skip_comments=True)
    for col in ('key', 'checked', 'reviewer', 'date', 'note', 'label'):
        if col not in ahead:
            errors.append(f'検収の台帳 r{y}: {col} の列がない')
    if errors:
        fail_now()
    if not arows:
        errors.append(f'検収の台帳 r{y}: 行がない')
    s = {'n': len(arows), 'm': 0, 'a': 0, 'b': 0, 'c': 0, 'u': 0, 'f': 0, 'x': 0}
    reasons = dict.fromkeys(REASON_ORDER, 0)
    dates = []
    keys = set()
    for r in arows:
        if r['key'] in keys:
            errors.append(f"検収の台帳 r{y}: key が重複: {r['key']}")
        keys.add(r['key'])
        if r['date']:
            dates.append(r['date'])
        if r['checked'] not in ('✓', ''):
            errors.append(f"検収の台帳 r{y}: checked が ✓ でも空でもない行: {r['checked']!r} {r['label']}")
            continue
        ok = r['checked'] == '✓'
        rv = r['reviewer']
        if ok:
            s['m'] += 1
            if rv.startswith('auto:'):
                if rv not in MACHINE:
                    errors.append(f"検収の台帳 r{y}: PLAN_SCHEMA §11.2 に無い機械の照合: reviewer={rv!r}")
                else:
                    s[MACHINE[rv]] += 1
            else:
                s['c'] += 1
        else:
            s['u'] += 1
            rs = reason(r['note'])
            if rs is None:
                errors.append(f"検収の台帳 r{y}: PLAN_SCHEMA §11.3 の表に無い note: {r['note']!r}")
            else:
                reasons[rs] += 1
        if r['note'].startswith('要人確認:H4'):
            s['f'] += 1
            if ok and not rv.startswith('auto:'):
                s['x'] += 1
    s['reasons'] = [[k, v, k not in HUMAN_SEEN] for k, v in reasons.items() if v]  # [理由, 件数, 人が確かめます]
    s['last'] = max(dates) if dates else ''
    audit[y] = s

    ihead, irows = read_tsv(files[ISSUES[y]])
    if 'status' not in ihead:
        errors.append(f'段3の台帳 r{y}: status の列がない')
        continue
    by = {}
    for r in irows:
        if r['status'] not in ISSUE_STATUS:
            errors.append(f"段3の台帳 r{y}: status が決まった語彙にない: {r['status']!r}（No.{r.get('no')}）")
        by[r['status']] = by.get(r['status'], 0) + 1
    issues[y] = {'rows': len(irows), 'pending': by.get('未判断', 0),
                 'by_status': [[k, v] for k, v in sorted(by.items(), key=lambda kv: -kv[1])]}
if errors:
    fail_now()

# 4. 実施計画と対応の台帳（令和8年度） ---------------------------------------------------
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

FL = F[LINK_YEAR]
_, lrows = read_tsv(files[LINKS])
node_of = {k: [] for k in FL}
none_of = {k: 0 for k in FL}
for r in lrows:
    tag = f"links: {r['from']} → {r['to']}"
    mf = re.fullmatch(rf'fh:fuhyo-r{LINK_YEAR}/(b[0-9]{{3,}})', r['from'])
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
    if fk not in FL:  # b
        errors.append(f'{tag}: 附表に {fk} がない')
        continue
    if norm(FL[fk]['name']) != r['context']:
        errors.append(f"{tag}: 附表の事業名「{FL[fk]['name']}」が context「{r['context']}」と合わない")
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
for k in FL:  # e
    n, z = len(node_of[k]), none_of[k]
    if not ((n >= 1 and z == 0) or (n == 0 and z == 1)):
        errors.append(f'links: {k}（{FL[k]["name"]}）の confirmed が node {n}行・記載なし {z}行')

# 5. 年度の台帳 -------------------------------------------------------------------
_, yrows = read_tsv(files[LINKS_Y])
FH = re.compile(r'fh:fuhyo-r([3-8])/(b[0-9]{3,})')
edges = []                       # (from_year, from_key, to_year, to_key)
out_of = {}                      # (from_year, from_key, to_year) → 件数
in_of = {}                       # (to_year, to_key, from_year) → 件数
ny = {'name': 0, 'manual': 0, 'rejected': 0}
for r in yrows:
    tag = f"years: {r['from']} → {r['to']}"
    mf, mt = FH.fullmatch(r['from']), FH.fullmatch(r['to'])
    if not mf or not mt or r['method'] not in ('name', 'manual'):  # a
        errors.append(f'{tag}: from・to・method の形が違う')
        continue
    fy, fk, ty, tk = int(mf.group(1)), mf.group(2), int(mt.group(1)), mt.group(2)
    if fy >= ty:
        errors.append(f'{tag}: from の年度が to の年度より前でない')
        continue
    if r['status'] == 'candidate':
        errors.append(f'{tag}: candidate のまま（判定の途中）')
        continue
    if r['status'] not in ('confirmed', 'rejected'):
        errors.append(f"{tag}: status が {r['status']!r}")
        continue
    if r['status'] != 'confirmed':
        ny['rejected'] += 1
        continue
    if fk not in F[fy] or tk not in F[ty]:  # b
        errors.append(f'{tag}: 附表に無い事業がある')
        continue
    if norm(F[fy][fk]['name']) != r['context']:
        errors.append(f"{tag}: from の事業名「{F[fy][fk]['name']}」が context「{r['context']}」と合わない")
    if F[ty][tk]['name'] != r['to_label']:
        errors.append(f"{tag}: to の事業名「{F[ty][tk]['name']}」が to_label「{r['to_label']}」と違う")
    ny[r['method']] += 1
    edges.append((fy, fk, ty, tk))
    out_of[(fy, fk, ty)] = out_of.get((fy, fk, ty), 0) + 1
    in_of[(ty, tk, fy)] = in_of.get((ty, tk, fy), 0) + 1
for (fy, fk, ty), c in out_of.items():  # c
    if c > 1:
        errors.append(f'years: fh:fuhyo-r{fy}/{fk} から令和{ty}年度への confirmed が {c}行')
for (ty, tk, fy), c in in_of.items():
    if c > 1:
        errors.append(f'years: 令和{fy}年度から fh:fuhyo-r{ty}/{tk} への confirmed が {c}行')

# 束ねる（同じ事業の年度をまたぐつながり）
parent = {(y, k): (y, k) for y in YEARS for k in F[y]}


def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


for fy, fk, ty, tk in edges:
    parent[find((fy, fk))] = find((ty, tk))
groups = {}
for x in parent:
    groups.setdefault(find(x), []).append(x)
chains = []
for g in sorted(groups.values(), key=lambda g: min(g)):
    g = sorted(g)
    ys = [y for y, _ in g]
    if len(set(ys)) != len(ys):
        errors.append('years: 束ねた1本に同じ年度の事業が2つある: ' + ', '.join(f'fh:fuhyo-r{y}/{k}' for y, k in g))
    chains.append(g)
chain_of = {x: i for i, g in enumerate(chains) for x in g}

# 6. 当初予算の総額（このリポジトリの data/totals-r<n>.json。原典から転記した正本） -------------
_, trows = read_tsv(files[TOWN])
town = {r['id']: r for r in trows}
totals = {}
for y in YEARS:
    t = json.loads((ROOT / f'data/totals-r{y}.json').read_text(encoding='utf-8'))
    if t.get('unit') != '千円':
        errors.append(f"totals r{y}: unit が千円でない（{t.get('unit')!r}）")
    acc = sum(a['amount'] for a in t['accounts'])
    if acc != t['total']['amount']:
        errors.append(f"totals r{y}: 会計ごとの和 {acc:,} ≠ 合計 {t['total']['amount']:,}")
    src = t['source']
    if not isinstance(src.get('pdf_page'), int) or not isinstance(src.get('printed_page'), int):
        errors.append(f'totals r{y}: 出典の pdf_page・printed_page の形が違う')
    tr = town.get(src.get('docs_id', ''))
    if tr is None:
        errors.append(f"totals r{y}: hino-town-docs の台帳に {src.get('docs_id')!r} の行がない")
    else:
        if tr['id'] != f'yosan-r{y}-gaiyou':
            errors.append(f"totals r{y}: docs_id が yosan-r{y}-gaiyou でない（{tr['id']}）")
        for k in ('title', 'url', 'sha256'):
            if src.get(k) != tr[k]:
                errors.append(f"totals r{y}: 出典の {k} が hino-town-docs の台帳と違う（{src.get(k)} / {tr[k]}）")
        if str(src.get('bytes')) != tr['bytes']:
            errors.append(f"totals r{y}: 出典の bytes が hino-town-docs の台帳と違う（{src.get('bytes')} / {tr['bytes']}）")
    totals[y] = t

if errors:
    fail_now()

# 書き出し -----------------------------------------------------------------------
out_items = []
for y in YEARS:
    for p, it in items[y]:
        o = {
            'fy': y, 'key': it['key'], 'pillar': p['no'], 'kubun': it['kubun'], 'kan': it['kan'],
            'name': it['name'], 'desc': it['desc'], 'details': it['details'], 'amount': it['amount'],
            'dept': it['dept'], 'page': it['page'], 'chain': chain_of[(y, it['key'])],
        }
        if y == LINK_YEAR:
            o['jisshi'] = [{'key': ek, 'name': E[ek]} for ek in sorted(node_of[it['key']])]
        out_items.append(o)
years = []
for y in YEARS:
    d, s, t = fuhyo[y], srow[y], totals[y]
    years.append({
        'fy': y, 'label': d['fiscal_year']['label'], 'year': d['fiscal_year']['year'],
        'source': {'id': f'fuhyo-r{y}', 'file': d['source']['file'], 'page_id': d['source'].get('page_id', ''),
                   'label': s['label'], 'url': s['url'], 'fetched': s['fetched']},
        'audit': audit[y], 'issues': issues[y],
        'totals': {'source': {k: t['source'][k] for k in ('title', 'url', 'pdf_page', 'printed_page', 'fetched')},
                   'accounts': t['accounts'], 'total': t['total']['amount']},
    })
meta = {
    'years': years,
    'pillars': [{'no': no, 'name': name} for no, name in pillar_names],
    'inputs': sorted({(e['repo'], e['commit']) for e in lock['inputs']}),
    'plan': {'id': PLAN_ID, 'name': jisshi['meta']['name'], 'fy': LINK_YEAR},
    'chains': {'n': len(chains), 'name': ny['name'], 'manual': ny['manual']},
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
print('附表（事業数・予算額の合計・新規・拡充）:')
for y in YEARS:
    its = [it for _, it in items[y]]
    print(f"  令和{y}年度: {len(its)}件・{fmt(sum(it['amount'] for it in its))}千円"
          f"（新規 {sum(1 for it in its if '新規' in it['kubun'])}・拡充 {sum(1 for it in its if '拡充' in it['kubun'])}）")
print(f'  合計: {len(out_items)}件')
print('柱ごとの予算額（千円）:')
for no, name in pillar_names:
    print(f"  柱{no} {name}: " + '・'.join(f"R{y} {fmt(sum(it['amount'] for p, it in items[y] if p['no'] == no))}" for y in YEARS))
print('検収の台帳（照合の対象／済み／人の抜き取り 済み／対象）と段3の未判断:')
for y in YEARS:
    s, i = audit[y], issues[y]
    print(f"  令和{y}年度: {s['n']}行／{s['m']}行（プログラム {s['a']}・AI {s['b']}・人 {s['c']}）／抜き取り {s['x']}／{s['f']}"
          f"、段3 未判断 {i['pending']}／{i['rows']}件、記録の最終日 {s['last']}")
nc = sum(1 for r in lrows if r['status'] == 'confirmed')
nr = sum(1 for r in lrows if r['status'] == 'rejected')
print(f'対応の台帳（令和{LINK_YEAR}年度）: confirmed {nc}行（実施計画の事業 {sum(len(v) for v in node_of.values())}行・'
      f'記載なし {sum(none_of.values())}行）、rejected {nr}行、candidate 0行')
print(f'  実施計画の事業に対応 {sum(1 for v in node_of.values() if v)}事業、記載なし {sum(1 for v in none_of.values() if v)}事業')
print(f"年度の台帳: confirmed {len(edges)}行（名前の一致 {ny['name']}・手でつないだ {ny['manual']}）、rejected {ny['rejected']}行。"
      f"束ねた事業 {len(chains)}本（6年とも載る {sum(1 for g in chains if len(g) == len(YEARS))}本・1年だけ {sum(1 for g in chains if len(g) == 1)}本）")
print('当初予算の総額（data/totals-r<n>.json、千円）:')
for y in YEARS:
    t = totals[y]
    print(f"  令和{y}年度: " + '・'.join(f"{a['name']} {fmt(a['amount'])}" for a in t['accounts'])
          + f" ＝ 合計 {fmt(t['total']['amount'])}（{t['source']['title']} {t['source']['printed_page']}ページ）")
print('検算 OK。data.js を書き出しました。')
