## 1. 三態冪等（TDD）

- [ ] 1.1 RED：四 scenario 測試（同 job skip／requeue overwrite＋is_satisfied 翻轉／舊格式升級／壞檔 overwrite）
- [ ] 1.2 complete_tick 冪等判準改 job_id 三態＋manifest 寫入加 job_id；GREEN

## 2. 異常案例與觀測

- [ ] 2.1 RED：雙 terminal 後者勝＋warning 測試；released 觀測 failed→passed 反映測試
- [ ] 2.2 warning 記錄實作；GREEN

## 3. 收尾

- [ ] 3.1 既有 complete_tick 測試零回歸（released/_is_safe_slice_id 路徑）
- [ ] 3.2 全套件綠；PR body `Closes #132`
