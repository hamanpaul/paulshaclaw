## 1. 設定模型

- [ ] 1.1 RED：per-persona override 解析測試（builder=enforce、繼承、未知值→shadow+warning）
- [ ] 1.2 personas.yaml 加 roles.builder.enforcement: enforce＋loader 解析；GREEN

## 2. PR-bound manifest

- [ ] 2.1 RED：branch↔slice 匹配測試（匹配/不匹配/多筆→視同無）
- [ ] 2.2 scope_ci 以 head branch 解析 manifest，棄 find_latest；GREEN

## 3. enforce 判定

- [ ] 3.1 RED：enforce 全路徑測試（違規 1/乾淨 0/無 manifest 觸 governed 1/未觸 0/catalog 壞 1/label 豁免 0）＋shadow 零回歸
- [ ] 3.2 scope_ci enforce 分支＋governed paths 聯集計算＋label 豁免；GREEN

## 4. workflow 與收尾

- [ ] 4.1 persona-scope.yml 更新註記（exit code 依 personas.yaml）
- [ ] 4.2 required check 翻牌 runbook（owner 手動步驟＋試點記錄模板）寫入 docs/ops/
- [ ] 4.3 全套件綠；PR body `Closes #124`
