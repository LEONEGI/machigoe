# マチゴエ 運用マニュアル

## 構成

- `crawler/machigoe.py` — 収集本体（ルールベース、LLM不使用、コスト0円）
- `crawler/sources.yaml` — 巡回ソース定義。**運用の中心はこのファイル**
- `crawler/state.json` — 既知アイテムの記憶（自動生成、手で触らない）
- `docs/data.json` / `docs/calendar.ics` — 公開データ（GitHub Pagesで配信）
- `.github/workflows/crawl.yml` — 毎日06:00/14:00 JSTに自動実行

## 初回セットアップ（1回だけ）

1. GitHubに新規リポジトリ `machigoe` を作成（公開推奨: 市民プロジェクトとしての信頼）
2. このフォルダの中身をpush
3. リポジトリ Settings → Pages → Source: `main` ブランチの `/docs` フォルダ
4. Actions タブで crawl を手動実行（workflow_dispatch）して初回データ生成
5. `https://<ユーザー名>.github.io/machigoe/data.json` が見えることを確認
6. WordPressの表示ページ（frontend/ 参照）のJS内 DATA_URL をこのURLに書き換え

## 日常運用（目標: 週30分以内）

- 平常時: 何もしない。Actionsが毎日回る
- 新しい自治体の追加: 下の「ソース追加プロンプト」をSonnetセッションに渡す
- ソースが壊れたら: data.json の sources の last_success が古くなる（フロントに「更新が止まっています」表示が出る）→ Sonnetに該当ソースの修理を依頼

## ソース追加プロンプト（Sonnetにこのまま渡す）

```
Dropbox\Claude\Projects\machigoe\crawler\sources.yaml に自治体を1つ追加したい。
対象: ◯◯区（市）
手順:
1. WebSearch/WebFetchで、その自治体のパブリックコメント一覧ページと新着RSSの有無を確認（URLは実際にアクセスして200を確認）
2. RSSがあれば type: rss、なければ type: html_list でsources.yamlにエントリを追記
3. ローカルで `python crawler/machigoe.py` を実行し、そのソースからitemsが取れることを確認
   （Windowsでは python の実体パス C:\Users\leo\AppData\Local\Programs\Python\Python314\python.exe を使うこと）
4. 取れない場合は selector（一覧を含む要素のCSSセレクタ）を指定して再試行
```

## 品質ルール（govwatchと共通思想）

1. 締切の抽出は推定を含む → フロントに「締切は必ず原典で確認」を常時表示
2. robots.txt遵守・1.5秒間隔・UAに連絡先明記（machigoe.py に実装済み、変更しない）
3. 対応自治体は必ず「対応リスト」として明示。「全国対応」とは絶対に言わない

## マネタイズの実装順（design参照）

1. 無料公開＋運営者表記（今）
2. キーワード通知の登録フォーム（メールリスト形成）→ 週次ダイジェスト
3. 有料プラン: 業種向けAI解説つき通知（不動産→都市計画ウォッチへ合流、士業→補助金・制度改正）月1万円前後
4. データAPI/CSV提供（事業者向け、月数千円〜）
