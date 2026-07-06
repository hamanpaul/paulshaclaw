## 1. Gap ①：retrieval scoped corpus（PR-1，可平行）

- [x] 1.1 RED：兩 project fixture——A 的 instruction 內容出現在 B 的 slice，現行 broad corpus 會誤排除 B（先證明 fail）
- [x] 1.2 `build_index` 改 per-project scoped corpus（projects.yaml roots → `corpus_for_roots()`；無 roots → 空語料不排除）
- [x] 1.3 per-project `indexed/excluded/exclude_rate` 遙測＋>40% WARN（含 50% fixture 觸發測試）
- [x] 1.4 GREEN＋全套件回歸；rebuild live index，驗證 testpilot/serialwrap 覆蓋 >90%、paulshaclaw 不退化、短清單能 offer 兩桶

## 2. Gap ③：janitor ledger 容錯（PR-2，可平行）

- [ ] 2.1 RED：fixture 混排（空行/壞 JSON/正常行）→ 現行 abort（先證明 fail）
- [ ] 2.2 import ledger 逐行容錯：壞行 skip＋計數，warning 報 `skipped N bad line(s)`
- [ ] 2.3 GREEN＋回歸；ops：備份後清 live 壞行，確認 janitor warning 消失

## 3. Gap ②：park 地板複驗（PR-3，ops 先行）

- [ ] 3.1 ops 複驗：6 parked session 的 cache 時戳 vs #190 merge 時點＋retry budget sidecar，逐筆判定殘留/新生（記錄附回 #197）
- [ ] 3.2 殘留者：備份後清該 session cache＋reset budget，交背景 loop 重試（禁手動 dream run），觀察下輪 pass 收斂
- [ ] 3.3 （條件觸發）若新碼仍失敗：RED→prose 容忍抽取（唯一頂層 array 才取、歧義 fail-closed）＋atomizer prompt 加固→GREEN
- [ ] 3.4 驗收：backlog 收斂至 transport-only，或逐筆記錄「真無知識」

## 4. 收尾

- [ ] 4.1 三 PR 各自全套件綠、互不依賴可獨立 merge
- [ ] 4.2 #197 三個 checklist 對應勾銷
