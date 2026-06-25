## 1. noise classifier（單一真相源）

- [ ] 1.1 RED：寫 `test_noise.py` — 6 結構 echo（含 Summary）+ 空殼 + 3 種 placeholder 判 noise；untitled 真 checklist body / 短但真實 fact 判非 noise。watch fail。
- [ ] 1.2 GREEN：新增 `paulshaclaw/memory/noise.py` `classify_noise(frontmatter, body) -> NoiseVerdict`，僅依 body 判定（structural-echo first-line / empty<40 / placeholder）。
- [ ] 1.3 確認 1.1 全綠、reason 字串正確。

## 2. 產生端過濾（防新生）

- [ ] 2.1 RED：在 `test_atomizer_pipeline`（或新 test）寫——含結構 fragment 的 session 經 promote 後，knowledge 不含結構 echo slice、`summary["noise_dropped"]` 計數正確、source fragment 仍 archive。watch fail。
- [ ] 2.2 GREEN：`atomizer/pipeline.py::_promote_pass` 於 validate 後、寫入前套 `classify_noise`，noise 者不寫/不建 relation、計入 `noise_dropped`、append warning；dry-run 分支同步。
- [ ] 2.3 確認 2.1 全綠，且既有 atomizer/pipeline 測試無回歸。

## 3. 回溯 prune CLI

- [ ] 3.1 RED：寫 `test_prune_noise`（CLI 層）——dry-run 不動檔且統計正確；`--apply` 刪噪音、保留乾淨 slice、輸出 manifest、重建後 MOC 不含已刪 slice；單檔失敗以 status=error 記 manifest 並續跑。watch fail。
- [ ] 3.2 GREEN：`paulshaclaw/memory/cli.py` 加 `knowledge prune-noise`（`--memory-root`/`--now`/`--dry-run`/`--apply`），掃 `knowledge/**.md`（排除 `*-moc.md`）、套 classifier、`--apply` hard delete + manifest `runtime/ledger/prune-<now>.jsonl` + `build_mocs` 重建。
- [ ] 3.3 確認 3.1 全綠。

## 4. 驗證與收尾

- [ ] 4.1 跑 memory 相關測試套件全綠（含新增三組），確認無回歸。
- [ ] 4.2 requesting-code-review；修 finding 後 re-review。
- [ ] 4.3 openspec archive；conventional commit；push；開 PR（Closes #139 視 P2 是否收尾，否則 Refs）。
