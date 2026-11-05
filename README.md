# 令和8年度 主な事業（日野町データポータル・非公式）

https://kken78.github.io/hino-budget/

滋賀県日野町の「令和8年度当初予算の概要」の附表「令和8年度に取り組む主な事業」に載った181事業を、柱・款・担当課ごとの件数と予算額、事業の一覧で見るページです。附表に載った事業だけを集計したもので、町の予算の全体ではありません。

出典：日野町「[令和8年度予算](https://www.town.shiga-hino.lg.jp/0000008534.html)」のページの「令和8年度当初予算の概要」の附表（[PDF](https://www.town.shiga-hino.lg.jp/cmsfiles/contents/0000008/8534/R8jigyou.pdf)）

## ファイル

| ファイル | 中身 |
|---|---|
| `index.html` | 画面。`data.js` を読むだけで、外部の CSS・JavaScript・フォントは読み込まない |
| `inputs.lock.json` | 材料のファイルごとの、リポジトリ・コミット・パス・sha256 |
| `data.js` | 材料から作る画面用のファイル。直接編集しない |
| `tools/build_data.py` | 材料を検算して `data.js` を作る（標準ライブラリのみ） |

材料はこのリポジトリに置かず、次の2つのリポジトリから読みます。

| リポジトリ | ファイル | 中身 |
|---|---|---|
| [shiga-hino-plans](https://github.com/kken78/shiga-hino-plans) | `data/fuhyo/fuhyo-r8.json` | 附表の事業（書式は PLAN_SCHEMA.md §9） |
| | `data/audit_log/fuhyo-r8.tsv` | 附表を原典の PDF と照らした検収の台帳 |
| | `data/sources_index.tsv` | 原典の台帳（fuhyo-r8 の行の PDF の URL を使う） |
| | `data/plans/jisshi.json` | 第6次日野町総合計画 実施計画（事業名を引く） |
| [hino-ronten](https://github.com/kken78/hino-ronten) | `links/fuhyo.tsv` | 附表の事業と実施計画の事業の対応の台帳（書式は LINK_SCHEMA.md） |

## 作り直し方

1. このリポジトリと同じフォルダに、shiga-hino-plans と hino-ronten を置く（例 `~/GitHub/hino-budget` と `~/GitHub/shiga-hino-plans`・`~/GitHub/hino-ronten`）。
   各リポジトリは `inputs.lock.json` の commit の版にする（`git -C ../shiga-hino-plans checkout <commit>` など）。別の場所に置いたときは、次の手順で `--src <フォルダ>` を付ける。
2. `python3 tools/build_data.py` を実行する。次の検算がすべて合ったときだけ `data.js` が書き出される。合わなければ、合わない行を表示して終了コード 1 で止まる。
   - 材料の sha256 が `inputs.lock.json` と一致する
   - 附表の事業が181件で、key が重複しない
   - 検収の台帳の行（先頭が `#` の説明の行を除く）がすべて checked=✓
   - 対応の台帳（hino-ronten の LINK_SCHEMA.md §5・§11 に合わせた5つ）
     - 全行の from が `fh:fuhyo-r8/<key>`、to が `node:jisshi/<key>` か `none:jisshi`、method が fuhyo、status が confirmed か rejected（candidate が残っていれば止める）
     - confirmed の行の from が附表にあり、事業名を LINK_SCHEMA §4 で正規化した値が context と同じ
     - confirmed の node の行の事業が jisshi.json にあり、事業名が to_label と同じ
     - confirmed の none の行の to_label が「記載なし」
     - 附表の各事業が、confirmed の node が1行以上か、confirmed の none が1行だけ
3. 実行すると、柱ごとの件数と予算額の合計を表示する。

材料を新しい版にするときは、各リポジトリを `git pull` し、`inputs.lock.json` の各ファイルの commit（`git -C <リポジトリ> rev-parse HEAD`）と sha256（`sha256sum <ファイル>`）を書き換えてから、手順2を行う。

画面に載せるのは、附表の事業の key・柱・区分・款・事業名・概要・内訳・予算額（千円）・担当課・原典のページと、対応の台帳で confirmed の実施計画の事業（e番号と事業名）です。原典の文字は直しません（誤字と思われる箇所も含めそのまま）。担当課が2つ以上ある事業は、担当課別の表では「複数の課」の行に数えます（課ごとの金額の内訳が附表に無いため）。

## ライセンス

コードは MIT License（[LICENSE](LICENSE)）。`data.js` の構造は CC BY 4.0（表示は https://github.com/kken78/hino-budget ）。転記した文字と数字は日野町の公表資料によるもので、このリポジトリのライセンスの対象外。
