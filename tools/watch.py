#!/usr/bin/env python3
"""町の「予算」のページを巡回し、新しい年度の予算のページと、使っている原典(当初予算の概要・附表)の変化を見つける。

見つけるもの(種類):
  new_year  新しい年度の予算のページ。「予算」の分類のページ(category/32-6-1-…)に、data/watch.tsv に無い年度の
            「令和○年度予算」のページがある。そのページにある PDF のリンク(当初予算の概要・附表など)も載せる
  replaced  差し替え。台帳 data/watch.tsv の URL の PDF が、台帳の sha256 と違う
  missing   取れない。台帳の URL が 404 などで取れない。または、年度のページからその PDF へのリンクが無くなった

取得は1秒に1件以内。HEAD の Content-Length が台帳の bytes と同じで、Last-Modified が台帳の fetched より後でなければ GET しない。
台帳・totals・data.js は変えない(見つけるだけ)。

用法:
  python3 tools/watch.py                  # 巡回し、結果を標準出力に Markdown で出す
  python3 tools/watch.py --json out.json  # 結果を JSON にも書く
  python3 tools/watch.py --ledger 別の台帳.tsv   # 台帳を差し替えて試す(自己検査)
  python3 tools/watch.py --full           # 台帳の PDF を全部 GET して sha256 を比べる(約 10MB)

終了コード: 0 巡回できた / 2 巡回に失敗した(分類のページか年度のページが取れない、通信の失敗)
"""
import argparse
import csv
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "data", "watch.tsv")
HOST = "www.town.shiga-hino.lg.jp"
CATEGORY = f"https://{HOST}/category/32-6-1-0-0-0-0-0-0-0.html"   # 町政情報 > 行財政運営 > 予算
UA = "hino-budget-watch/1.0 (+https://github.com/kken78/hino-budget)"
TIMEOUT = 30
INTERVAL = 1.0
JST = timezone(timedelta(hours=9))
YEAR_RE = re.compile(r"令和(\d+)年度予算")
HREF_RE = re.compile(r"""<a\b[^>]*?href\s*=\s*["']([^"']+)["'][^>]*>(.*?)</a>""", re.I | re.S)

_last = [0.0]


def _wait():
    rest = INTERVAL - (time.monotonic() - _last[0])
    if rest > 0:
        time.sleep(rest)
    _last[0] = time.monotonic()


def _request(url, method="GET"):
    _wait()
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, dict(r.headers), (b"" if method == "HEAD" else r.read())
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), b""


def norm(u):
    pu = urllib.parse.urlsplit(u.strip())
    return urllib.parse.urlunsplit((pu.scheme, pu.netloc, pu.path, "", ""))


def links(base, body):
    """ページの中のリンク [(絶対URL, 文字)]。町のサイトのものだけ。"""
    text = body.decode("utf-8", errors="replace")
    out = []
    for href, inner in HREF_RE.findall(text):
        absu = urllib.parse.urljoin(base, html.unescape(href.strip()))
        if urllib.parse.urlsplit(absu).netloc != HOST:
            continue
        label = html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", inner))).strip()
        label = re.sub(r"\s*(サイズ|ファイルサイズ)[：:]?\s*[\d.,]+\s*[KMG]?B.*$", "", label).strip()
        label = re.sub(r"\s*[（(]PDF形式[、,][^）)]*[）)]\s*$", "", label).strip()
        out.append((norm(absu), label))
    return out


def load_ledger(path):
    with open(path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    need = {"fy", "kind", "docs_id", "page_url", "url", "bytes", "sha256", "fetched"}
    if not rows or not need <= set(rows[0]):
        raise SystemExit(f"台帳 {path} の列が足りない")
    return rows


def newer(last_modified, fetched):
    if not last_modified or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", fetched or ""):
        return True
    try:
        return parsedate_to_datetime(last_modified).astimezone(JST).date().isoformat() > fetched
    except (TypeError, ValueError):
        return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ledger", default=LEDGER)
    ap.add_argument("--json")
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args()
    rows = load_ledger(a.ledger)
    known_years = sorted({int(r["fy"]) for r in rows})
    rep = {"date": datetime.now(JST).strftime("%Y-%m-%d %H:%M JST"), "category": CATEGORY,
           "known_years": known_years, "year_pages": {}, "checked_pdfs": 0, "head_only": 0, "got": 0,
           "findings": {"new_year": [], "replaced": [], "missing": []}, "errors": [],
           "failed": False, "fail_reason": ""}
    fail = []

    # 1. 予算の分類のページ → 年度ごとのページ
    try:
        st, _, body = _request(CATEGORY)
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        st, body = None, b""
        fail.append(f"予算の分類のページが取れない: {e}")
    if st is not None and st != 200:
        fail.append(f"予算の分類のページが取れない: HTTP {st}")
    pages = {}
    for u, label in links(CATEGORY, body):
        m = YEAR_RE.search(label)
        if m and re.fullmatch(r"https://[^/]+/\d{10}\.html", u):
            pages.setdefault(int(m.group(1)), u)
    rep["year_pages"] = {str(k): v for k, v in sorted(pages.items())}
    if body and not pages:
        fail.append("予算の分類のページに「令和○年度予算」のリンクが1つも無い(ページの作りが変わった)")

    # 2. 新しい年度のページ
    for fy, u in sorted(pages.items()):
        if fy in known_years:
            continue
        item = {"fy": fy, "label": f"令和{fy}年度予算", "url": u, "pdfs": []}
        try:
            st, _, body = _request(u)
            if st == 200:
                item["pdfs"] = [{"url": pu, "label": pl} for pu, pl in links(u, body) if pu.lower().endswith(".pdf")]
            else:
                item["note"] = f"ページは HTTP {st}"
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            item["note"] = f"ページが取れない: {e}"
        rep["findings"]["new_year"].append(item)

    # 3. 台帳の PDF(年度のページにリンクがあるか、差し替えられていないか)
    page_links = {}
    for pu in sorted({r["page_url"] for r in rows}):
        try:
            st, _, body = _request(pu)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            fail.append(f"年度のページが取れない: {pu} {e}")
            continue
        if st != 200:
            fail.append(f"年度のページが取れない: {pu} HTTP {st}")
            continue
        page_links[pu] = {u for u, _ in links(pu, body)}
    net_fail = 0
    for r in rows:
        url = norm(r["url"])
        res = {"docs_id": r["docs_id"], "fy": r["fy"], "kind": r["kind"], "url": r["url"], "bytes": int(r["bytes"]),
               "sha256": r["sha256"], "kind2": "same", "status": None, "length": None, "last_modified": "",
               "now_bytes": None, "now_sha256": "", "reason": ""}
        rep["checked_pdfs"] += 1
        if r["page_url"] in page_links and url not in page_links[r["page_url"]]:
            res.update(kind2="missing", reason="年度のページにこの PDF へのリンクが無い")
        try:
            st, hd, _ = _request(r["url"], "HEAD")
            res["status"] = st
            res["last_modified"] = hd.get("Last-Modified", "")
            cl = hd.get("Content-Length")
            res["length"] = int(cl) if cl and cl.isdigit() else None
            if st in (404, 410):
                res.update(kind2="missing", reason=(res["reason"] + "。" if res["reason"] else "") + f"HTTP {st}")
            elif (not a.full and st == 200 and res["length"] == res["bytes"] and not newer(res["last_modified"], r["fetched"])):
                rep["head_only"] += 1
            else:
                st2, hd2, body = _request(r["url"], "GET")
                rep["got"] += 1
                res["status"] = st2
                if st2 in (404, 410):
                    res.update(kind2="missing", reason=f"HTTP {st2}")
                elif st2 != 200:
                    res.update(kind2="error", reason=f"HTTP {st2}")
                    net_fail += 1
                else:
                    sha = hashlib.sha256(body).hexdigest()
                    res.update(now_bytes=len(body), now_sha256=sha, last_modified=hd2.get("Last-Modified", res["last_modified"]))
                    if sha != r["sha256"]:
                        res.update(kind2="replaced", reason="sha256 が台帳と違う")
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            res.update(kind2="error", reason=f"通信の失敗: {e}")
            net_fail += 1
        if res["kind2"] in ("replaced", "missing"):
            rep["findings"][res["kind2"]].append(res)
        elif res["kind2"] == "error":
            rep["errors"].append(res)
    if rows and net_fail * 5 >= len(rows):
        fail.append(f"台帳の PDF {len(rows)} 件のうち {net_fail} 件が通信の失敗")

    if fail:
        rep["failed"] = True
        rep["fail_reason"] = "。".join(fail)

    f = rep["findings"]
    L = [f"町の予算のページを {rep['date']} に巡回した結果。分類のページの年度 {', '.join('令和' + k for k in rep['year_pages'])}。"
         f"台帳の PDF {rep['checked_pdfs']} 件(HEAD だけ {rep['head_only']}・GET {rep['got']})。", ""]
    L.append(f"## 新しい年度の予算のページ({len(f['new_year'])}件)")
    for x in f["new_year"]:
        L.append(f"- {x['label']}: {x['url']}" + (f"({x['note']})" if x.get("note") else ""))
        for p in x["pdfs"]:
            L.append(f"  - {p['label'] or '(文字なし)'}: {p['url']}")
    L += ["- なし"] if not f["new_year"] else []
    L.append(""); L.append(f"## 差し替え({len(f['replaced'])}件)")
    for x in f["replaced"]:
        L.append(f"- {x['docs_id']}: 台帳 {x['bytes']} バイト・{x['sha256'][:12]}… → いま {x['now_bytes']} バイト・{x['now_sha256'][:12]}…(Last-Modified {x['last_modified'] or '不明'})。{x['url']}")
    L += ["- なし"] if not f["replaced"] else []
    L.append(""); L.append(f"## 取れない({len(f['missing'])}件)")
    for x in f["missing"]:
        L.append(f"- {x['docs_id']}: {x['reason']}。{x['url']}")
    L += ["- なし"] if not f["missing"] else []
    if rep["errors"]:
        L.append(""); L.append(f"## 確かめられなかったもの({len(rep['errors'])}件)")
        for x in rep["errors"]:
            L.append(f"- {x['docs_id']}: {x['reason']}")
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fo:
            json.dump(rep, fo, ensure_ascii=False, indent=1)
    print("\n".join(L))
    if rep["failed"]:
        print(f"\n巡回に失敗した: {rep['fail_reason']}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
