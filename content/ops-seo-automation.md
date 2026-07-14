# マチゴエ SEO記事 自動投稿パイプライン（2026-07-14構築）

`machigoe-seo-publish`（毎週水曜10:00、`C:\Users\leo\.claude\scheduled-tasks\machigoe-seo-publish\SKILL.md`）が自律実行する。

## やること（毎回）

1. `keyword-map.md` の記事計画テーブルから「状態: 未」の最初の1件を取得
2. 記事本文をテンプレ通りに直接執筆（サブエージェント禁止・1セッション完結）
3. Runware（`recraft:v4.1@0`）でアイキャッチ画像を1216×640で生成、ブランドカラー（ネイビー#070b14＋kindごとの差し色）を`settings.colors`で固定
4. `docs/assets/column/<slug>.jpg` に保存
5. `docs/column/<slug>.html` を公開（description・og:image・JSON-LDまで込みでSEO対応済み）
6. `docs/column/index.html` にカード追加、`docs/sitemap.xml` に追記
7. `keyword-map.md` の状態を✅に更新
8. git commit & push（GitHub Pagesが自動デプロイ）
9. Slackで leoworks00@gmail.com にDM通知（記事タイトル＋URL）

## 意図的な設計判断

- **画像はRunware `recraft:v4.1@0`を使用**（当初検討したHiggsfield系ツールは残高2.5クレジット/枚で残高5.18しかなく自動化に不向きと判断。Runwareは残高$54超・1枚$0.035で持続可能）
- **タイトルの日本語をAIに画像内へ描かせない**（CJKの文字レンダリングは不安定なため、アイキャッチは文字なしの抽象的な幾何学イラストに限定。タイトル文字はHTML側で表示）
- **スラッグは`keyword-map.md`に固定値を事前定義済み**（実行のたびにromaji変換させると表記ゆれが出るため）
- **キーワード在庫が0件になったら自動生成を止めてSlack通知**（新規キーワードの選定は戦略判断のため人間 or 上位モデルが行う。[[model-economy-preference]]の原則に合わせた）
- **サブエージェント（Agentツール）の使用を明示的に禁止**（過去にマチゴエ記事執筆をエージェントに依頼した際、再帰的にサブエージェントを大量生成して暴走した事故があったため。このタスクは常に単一セッションで直接実行する）

## 関連ファイル

- `keyword-map.md` — 記事計画・スラッグ・状態管理
- `docs/assets/site.css` — `.mg-card-img` クラスを追加済み（カードサムネイル表示用）
- 既存の週次自動化: `ops-weekly-report.md`（金曜、コンテンツ下書きのみ・投稿は手動）と役割が異なる点に注意。SEO記事は完全自動公開（人間レビューなし）が今回の明示的な依頼

## 未実施（今回のスコープ外）

- 既存7記事（画像なしで公開済み）へのアイキャッチ画像の遡及追加。やる場合は7枚×$0.035≒$0.25程度で低コスト。希望があれば別途実行
