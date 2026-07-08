# マチゴエ 修理・ローカル収集ログ

毎朝のローカル自動実行（machigoe-self-repair）の記録。1日1行を原則とする。

- 2026-07-07: bunkyo-pubcome 修理。旧URL(city.bunkyo.lg.jp/kusejoho/koho/pabukome.html)が(1)裸ドメインIPv4無し(IPv6のみ)でDNS失敗+(2)/b003/p006165.htmlへ301移転、の二重原因。www付き移転先URLへ更新し再実行で15件取得を確認、health.jsonのfailing空に回復。ローカル収集net +19件をcommit&push済み。
- 2026-07-08: 平常運転。全26ソース健全（health.json failing空）。クローラ計110件取得。新規3件（いずれもe-Gov国パブコメ=海外IP遮断ソース。ローカル収集で補完）: 船員法施行規則改正省令案 / 一般送配電の調整力公募調達の考え方改定案 / 旅客安全情報の一般指針一部改正。commit&push済み。修理なし。
