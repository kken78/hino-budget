# 当初予算 主な事業（令和3〜8年度）（日野町データポータル・非公式）

https://kken78.github.io/hino-budget/

滋賀県日野町の令和3〜8年度の「当初予算の概要」の附表「令和○年度に取り組む主な事業」に載った事業（6年分で1,031件）を、年度ごとに柱・款・担当課ごとの件数と予算額、事業の一覧で見るページです。柱ごとの事業費の6年分の推移と、同じ事業の年度をまたいだ予算額の推移も示します。附表に載った事業だけを集計したもので、町の予算の全体ではありません。参考として、各年度の当初予算の総額と会計ごとの額（「当初予算の概要」の「予算の規模」の表）を付記しています。

出典：日野町の各年度の「予算」のページ（例 [令和8年度予算](https://www.town.shiga-hino.lg.jp/0000008534.html)）の「当初予算の概要」の附表（PDF）。年度ごとの URL は `data.js` と画面の「データについて」にあります。

## ファイル

| ファイル | 中身 |
|---|---|
| `index.html` | 画面。`data.js` を読むだけで、外部の CSS・JavaScript・フォントは読み込まない |
| `inputs.lock.json` | 材料のファイルごとの、リポジトリ・コミット・パス・sha256（3リポジトリ・23ファイル） |
| `data/totals-r3.json` 〜 `data/totals-r8.json` | 各年度の当初予算の会計ごとの予算規模（千円）。各年度の「当初予算の概要」の「予算の規模」の表から転記した正本で、出典の URL・バイト数・sha256・ページ・取得日と、hino-town-docs の台帳の id（`docs_id`）も持つ |
| `data.js` | 材料から作る画面用のファイル。直接編集しない |
| `tools/build_data.py` | 材料を検算して `data.js` を作る（標準ライブラリのみ） |
| `og.png`・`assets/og.svg` | OGP 画像（1200×630）と、その編集元 |

附表の材料はこのリポジトリに置かず、次の3つのリポジトリから読みます。

| リポジトリ | ファイル | 中身 |
|---|---|---|
| [shiga-hino-plans](https://github.com/kken78/shiga-hino-plans) | `data/fuhyo/fuhyo-r3.json` 〜 `fuhyo-r8.json` | 附表の事業（書式は PLAN_SCHEMA.md §9） |
| | `data/audit_log/fuhyo-r3.tsv` 〜 `fuhyo-r8.tsv` | 附表を原典の PDF と照らした検収の台帳 |
| | `data/source_issues/fuhyo-r3.tsv` 〜 `fuhyo-r8.tsv` | 段3（文章の点検）の指摘と、その判断 |
| | `data/sources_index.tsv` | 原典の台帳（fuhyo-r3〜r8 の行の PDF の URL を使う） |
| | `data/plans/jisshi.json` | 第6次日野町総合計画 実施計画（事業名を引く） |
| [hino-ronten](https://github.com/kken78/hino-ronten) | `links/fuhyo.tsv` | 令和8年度の附表の事業と実施計画の事業の対応の台帳（書式は LINK_SCHEMA.md） |
| | `links/fuhyo-years.tsv` | 附表の事業の年度をまたぐ対応の台帳（LINK_SCHEMA.md「年度の台帳」、DESIGN.md ADR-33） |
| [hino-town-docs](https://github.com/kken78/hino-town-docs) | `data/sources.tsv` | 町の公開資料の台帳（`yosan-r3-gaiyou` 〜 `yosan-r8-gaiyou` の行で、当初予算の概要の URL・バイト数・sha256 を確かめる） |

## 作り直し方

1. このリポジトリと同じフォルダに、shiga-hino-plans・hino-ronten・hino-town-docs を置く（例 `~/GitHub/hino-budget` と `~/GitHub/shiga-hino-plans`・`~/GitHub/hino-ronten`・`~/GitHub/hino-town-docs`）。
   各リポジトリは `inputs.lock.json` の commit の版にする（`git -C ../shiga-hino-plans checkout <commit>` など）。別の場所に置いたときは、次の手順で `--src <フォルダ>` を付ける。
2. `python3 tools/build_data.py` を実行する。次の検算がすべて合ったときだけ `data.js` が書き出される。合わなければ、合わない行を表示して終了コード 1 で止まる。
   - 材料の sha256 が `inputs.lock.json` と一致する
   - 附表：年度ごとの事業数が 155・166・168・177・184・181 件で、key が重複しない。柱の番号と名前が6年で同じ。年度ごとの予算額の合計を数えて表示する
   - 検収の台帳：全行の checked が ✓ か空で、✓ でない行の note が PLAN_SCHEMA §11.3 の理由の表にある。照合の状況（対象・済み・内訳・済んでいないものと理由・人の抜き取り）を、shiga-hino-plans の計画ページと同じ数え方（PLAN_SCHEMA §11.2）で数える
   - 段3の台帳：status が決まった語彙（未判断・ダッシュボードで対応・原典どおり掲載・原典どおり掲載(注記)・対象外）のどれか。未判断の件数を数える
   - 対応の台帳 `links/fuhyo.tsv`（令和8年度。hino-ronten の LINK_SCHEMA.md §5・§11 に合わせた5つ）
     - 全行の from が `fh:fuhyo-r8/<key>`、to が `node:jisshi/<key>` か `none:jisshi`、method が fuhyo、status が confirmed か rejected（candidate が残っていれば止める）
     - confirmed の行の from が附表にあり、事業名を LINK_SCHEMA §4 で正規化した値が context と同じ
     - confirmed の node の行の事業が jisshi.json にあり、事業名が to_label と同じ
     - confirmed の none の行の to_label が「記載なし」
     - 附表の各事業が、confirmed の node が1行以上か、confirmed の none が1行だけ
   - 年度の台帳 `links/fuhyo-years.tsv`
     - 全行の from・to が `fh:fuhyo-r<n>/<key>` で、from の年度が to の年度より前。method が name か manual、status が confirmed か rejected（candidate が残っていれば止める）
     - confirmed の行の両端が附表にあり、from の事業名を正規化した値が context と同じ、to の事業名が to_label と同じ
     - 1つの事業から同じ年度へのつながりは1つだけ、同じ年度から1つの事業へのつながりも1つだけ。つないで束ねた1本の中に、同じ年度の事業が2つ無い
   - `data/totals-r<n>.json`：単位が千円で、会計ごとの和が合計と一致し、出典の title・url・bytes・sha256 が hino-town-docs の台帳の `yosan-r<n>-gaiyou` の行と一致し、pdf_page・printed_page がある
3. 実行すると、年度ごとの事業数と予算額の合計、柱ごとの予算額、検収の状況、年度の台帳の件数、当初予算の総額を表示する。

材料を新しい版にするときは、各リポジトリを `git pull` し、`inputs.lock.json` の各ファイルの commit（`git -C <リポジトリ> rev-parse HEAD`）と sha256（`shasum -a 256 <ファイル>`）を書き換えてから、手順2を行う。`inputs.lock.json` と `data.js` は同じコミットで直す。

### 検収の状況を出し直すとき

令和3〜7年度の附表は、2026年11月6日の時点で、段4（人の抜き取り）と段3の指摘の判断が済んでいません。画面の「原典との照合」は、台帳のその時点の数（抜き取り 0件、段3の未判断 11〜20件）をそのまま出しています。shiga-hino-plans で判断が済んだら、次の手順で出し直します。

1. `git -C ../shiga-hino-plans pull` で、判断を取り込んだ版にする。`python3 ../shiga-hino-plans/tools/audit_autocheck.py fuhyo-r3 --status`（r4〜r7 も同じ）が「完了」になっていることを見る。
2. `inputs.lock.json` の shiga-hino-plans の行（20ファイル）の commit と sha256 を書き換える。附表の JSON を直していれば `data/fuhyo/fuhyo-r<n>.json` の sha256 も変わる。
3. `python3 tools/build_data.py` を実行する。検収の台帳の表示で、人の抜き取りの「済み」が対象と同じ数になり、段3の未判断が 0 になることを確かめる。附表の JSON が直っていれば、事業数・予算額の合計も変わるので、`tools/build_data.py` の `EXPECTED_ITEMS` を原典で確かめた数に直す。
4. `inputs.lock.json` と `data.js` を同じコミットにして、作業ブランチから PR を作る。

画面に載せるのは、各年度の附表の事業の key・柱・区分・款・事業名・概要・内訳・予算額（千円）・担当課・原典のページ、年度の台帳でつながる他の年度の事業、令和8年度については対応の台帳で confirmed の実施計画の事業（e番号と事業名）です。原典の文字は直しません（誤字と思われる箇所も含めそのまま）。担当課が2つ以上ある事業は、担当課別の表では「複数の課」の行に数えます（課ごとの金額の内訳が附表に無いため）。増減は矢印と文言（▲ 増・▼ 減・＝ 同額）で示し、色は付けません。

## ライセンス

コードは MIT License（[LICENSE](LICENSE)）。`data.js` の構造は CC BY 4.0（表示は https://github.com/kken78/hino-budget ）。転記した文字と数字は日野町の公表資料によるもので、このリポジトリのライセンスの対象外。
