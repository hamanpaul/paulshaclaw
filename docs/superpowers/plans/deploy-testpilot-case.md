---
work_item: deploy-testpilot-case
status: accepted
---

# TestPilot 安裝回歸基座執行計畫

## Tasks

獨立 testpilot 子專案，不進 operator shell wheel 的 runtime dependencies；歷史 README／v0.2.7 的 expected RED 必須精確對應缺 git，不吞基礎設施失敗。builder 保留既有 AGY 路由。

工作 A：#324 TestPilot regression 基座

建議 branch：`feature/324-deploy-testpilot-case`。

修改範圍：新增 `testpilot/` 獨立 pyproject、plugin、Docker transport、4 組 YAML cases、example testbed、stub tests、執行文件；CI 增加獨立 plugin job。主套件 dependencies 不加入 TestPilot，主 wheel 不包含 plugin。

- [ ] 核對可安裝的 `testpilot-core` API_VERSION、PluginBase／TransportBase、case discovery、reporter 與 CLI help；選可驗證的版本範圍，記錄測試時實際版本。不能只照 issue 的範例編造呼叫介面。
- [ ] 建立 testbed：artifact path／SHA、README revision、image tag／digest、非 root uid、網路需求與 timeout 均明示。歷史 v0.2.7 wheel 固定原 SHA，candidate artifact 另以參數輸入；兩者不可互相覆蓋。
- [ ] TC-1 與 TC-1p 從指定 README revision 的前置段取得套件；初始缺少前置段時採 issue 指定基線。修復後採限定格式的套件宣告，解析器只接受預定套件 token，不能直接執行任意 Markdown。獨立記錄解析結果，避免 harness 暗加 git。
- [ ] TC-1c 固定無 git、`--no-deps`，只驗 entry points／help/version，不拿它證明完整 runtime；TC-1g 明加 git，Ubuntu 22.04 與 24.04 對照。
- [ ] 每步獨立 `docker exec`，保存真正 exit code／stdout／stderr；步驟失敗仍記錄後續診斷。容器只掛載必要 artifact／唯讀輸入，不掛 host HOME、secrets、systemd socket 或 Docker socket。
- [ ] plugin cleanup 使用本次建立的 container ID；正常、失敗、timeout 均可回收；不清理別人的容器。report 保留 container ID 與 cleanup 結果。
- [ ] Stub tests 覆蓋 step evaluation、非零 exit、輸出不符、timeout、cleanup、report 完整性；用獨立 venv 驗證安裝與 plugin/case discovery，避免 core API 或 import-path 假綠。
- [ ] 跑歷史 README + v0.2.7：TC-1／TC-1p 為 RED，且原因必須是缺 git；TC-1c／TC-1g 為 GREEN。網路、checksum 或 image 拉取失敗屬 infrastructure error，不能算預期 RED。
- [ ] CI 使用精確 expected-failure oracle 包住歷史 RED，原始 report 仍為 FAIL；不對整個 job 無條件 `continue-on-error`。其餘 stub／discovery／控制組必須通過。

交付證據：原始逐步 report、artifact SHA、README commit、image digest、core version、4 個 cases 的結果與乾淨回收證據。#324 以 test-only PR merge 結案，不等待修 bug 才交付。


## Integration gates

本工作源自 2026-09-07 使用者核可的五件 issue 修正計畫與 Cortex 平行派工指令。accepted 僅表示規格可執行，不表示程式或驗收已完成。

使用 Cortex 管理的隔離 branch/worktree；不得清理、stage 或覆寫 operator checkout 的既有變更。只處理本件 issue；所有實作、測試、OpenSpec、文件及 changelog 限本件 scope。不同工作線的 pyproject／CI／README 等共用檔須在各自 branch 修改，交由整合者處理衝突，不跨 worker worktree 寫入。

採 RED → 最小修正 → GREEN → 獨立 review → policy/preflight → PR 的受治理流程；未處置缺陷為 FAIL，接受風險需明文、有界且可追溯。禁止跳 gate 或手改 Cortex registry。部署、發布與本機 skill target 切換由 operator 整合驗收後執行，不由本 worker 自行進行；不得對外送 Telegram、覆寫既有 release、變更共享 service/config。PR 可依 Cortex 既有授權 gate 交付；不得僅憑 worker exit 0 宣告完成。

只驗收本件：保留 base/final SHA、RED/GREEN、focused/full tests、review 與 PR 證據。最終五件整合、published release 下載驗證及 runtime 切換屬批次整合者，不由本 worker 跨 scope 執行。
