# マチゴエ 修理・ローカル収集ログ

毎朝のローカル自動実行（machigoe-self-repair）の記録。1日1行を原則とする。

- 2026-07-07: bunkyo-pubcome 修理。旧URL(city.bunkyo.lg.jp/kusejoho/koho/pabukome.html)が(1)裸ドメインIPv4無し(IPv6のみ)でDNS失敗+(2)/b003/p006165.htmlへ301移転、の二重原因。www付き移転先URLへ更新し再実行で15件取得を確認、health.jsonのfailing空に回復。ローカル収集net +19件をcommit&push済み。
