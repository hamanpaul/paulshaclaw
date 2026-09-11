---
status: draft
---

# paulshaclaw 全部 open issues 修正計畫

## 1. 範圍與完成定義

2026-09-07 核對 GitHub：`hamanpaul/paulshaclaw` 有 5 個 open issues（#296、#324、#325、#326、#328），沒有 open PR。工作樹 HEAD 與 GitHub main 同為 `c2dd954f0d67b36796cca66e01f0e49a15f80bed`。本文件為規劃草案，尚未實作、測試、派工、merge 或部署；不以 `accepted` 或 auto label 觸發 Cortex。

每個 issue 的完成條件是其驗收證據與對應 PR 合併；涉及 runtime 切換或新版 release 時，另記錄部署／artifact 驗證結果。不能把 issue 關閉、source tests 通過與現場可用混為同一件事。

| Issue | 工作 | Stage／owner | 依賴與建議順序 |
|---|---|---|---|
| [#324](https://github.com/hamanpaul/paulshaclaw/issues/324) | repo 自有 TestPilot Docker 安裝 regression plugin | Stage 7；paulshaclaw 的獨立 testpilot 子專案 | 第一批；先交付可重現 RED |
| [#326](https://github.com/hamanpaul/paulshaclaw/issues/326) | deploy templates 打包、失敗 report 與 release gate | Stage 7；paulshaclaw | 可與 #324 並行；最終 artifact 驗收共用其環境 |
| [#325](https://github.com/hamanpaul/paulshaclaw/issues/325) | README 安裝前置與排錯 | Stage 7；paulshaclaw | #324 merge 且取得 RED 後，改成 GREEN |
| [#296](https://github.com/hamanpaul/paulshaclaw/issues/296) | bro 雙副本整合與單一來源 | Stage 1／7；paulshaclaw + 本機安裝路徑 | 可獨立開發；runtime 切換排在整合測試後 |
| [#328](https://github.com/hamanpaul/paulshaclaw/issues/328) | JOBS 顯示實際 executor／model | Stage 4／9 producer 在 Cortex；Stage 11 consumer 在 paulshaclaw | 先上游契約，再 consumer 與 pin，再整合驗收 |

建議拆成 6 個功能 PR：#324、#326、#325、#296、#328 Cortex producer、#328 paulshaclaw consumer／pin。新版 release 另有收尾提交。這是依賴順序，不要求其餘工作等待 #324 全部完成。

## 2. 已核對的現況與規劃裁決

- #324：目前只有未追蹤的 `docs/superpowers/workstreams/deploy-testpilot-case/plan.md` 等草稿；本 repo 尚無 plugin 實作。草稿已裁決 plugin 為獨立子專案，沿用此邊界。issue 的 TestPilot API／CLI 名稱是待核對契約，不假設目前 core 仍逐字相容。
- #325：`README.md` §A 未宣告 git 系統前置；`pyproject.toml` 仍以 git+SHA 安裝 Hippo／Cortex。最小修法保留 distribution 設計，補完整安裝前置與失敗處理。
- #326：`pyproject.toml` package-data 只有 cockpit tcss 與 core JSON，repo 的 12 個 deploy templates 未宣告。`release.yml` 與 `scripts/release-artifacts.sh` 的 templates grep 沒有先驗存在；`deploy/__main__.py` 的 install 路徑只攔 `ArtifactVerificationError`；`apply_install_plan()` 在逐檔寫入時才讀 template。這些為 source 證據，本輪未重建 wheel 或重跑 Docker。
- #296：本機 runtime bro symlink 指向外部 custom-skills checkout。兩側 `reply_bridge.py`／測試目前 inode 不同、link count 為 1，且內容不同；runtime 側另有 `notify.py`／`test_notify.py`，repo 側有 `MessagePaneMap`。不能以直接覆蓋或單純改 symlink 解決。選擇 repo 為 canonical，先合併功能，再提供可回復的安裝切換。
- #328：Cortex 的 `coordinator/manager.py::workflow_status_entry()` 未輸出 executor/model；本 repo `cockpit/app.py::_ingest_workflow_run()`、`models.py::JobRow` 也未承接。必須跨 repo 修；persona 保留角色語意。上游證據來自本機 checkout，實作前需核對上游 remote main 與目前 dependency pin 是否已有同類修正。
- 現有 `.cortex/`、`runtime/`、launcher 與 TestPilot 未追蹤文件屬既有工作；不搬移、不覆寫、不一併 stage。草稿若需納入正式工作，以明確檔案清單比較後採用。

## 3. 共通動工與整合流程

1. 再查 5 個 issues 與相關 PR；已完成者先核對 evidence，避免重做。Git 同步依 repo 規則先 `git pull --ff-only`，失敗才 `git fetch --all --prune`；有重疊本機修改時先保留並改用隔離 checkout。
2. 每條工作線建立自己的 branch／worktree、OpenSpec proposal/design/tasks 與 tests 對照；沿用既有 spec 名稱、Stage 與語言。Cortex producer 使用其 repo 自己的契約文件。
3. 各線完成 RED → 最小修正 → GREEN → review → verification → archive → policy／commit／PR。尚未執行的 checklist 保持未勾選。
4. 若採多 agent：master 持有依賴表與整合權；worker 只寫自己 branch 的 scope。README、release-contract、pyproject、CI 與 changelog 是共用檔，由整合者處理交疊。
5. 對抗審查首輪附標準：未處置缺陷／缺口為 FAIL；已明文接受、影響分析有界且文件列管的殘餘風險不單獨構成 FAIL。每條 finding 獨立驗證後修正、附證據駁回或接受列管。
6. PR／comments 使用 zh-TW。修復 PR 使用 `Closes #N`；Cortex PR 若關聯下游 issue，使用完整 repo reference，且不要提前關閉尚未完成 consumer 的 #328，依該 repo policy 使用非 closing 引用豁免。

## 4. 工作 A：#324 TestPilot regression 基座

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

## 5. 工作 B：#326 templates 與 artifact 可用性

建議 branch：`feature/326-deploy-template-packaging`。

修改範圍：`pyproject.toml`、`paulshaclaw/deploy/{planner,installer,__main__}.py`、兩個 release 入口、新增共享 artifact 檢查器與測試、既有 deploy 測試、`docs/release-contract.md`。

- [ ] RED：wheel、sdist、由 sdist 重建的 wheel，逐一驗 templates 相對路徑集合等於 source；source 集合須非空且符合 planner 所需資產。另保留 core commands.json、cockpit.tcss、entry points 與 launcher 檢查，避免 #335 回歸。
- [ ] 加 deploy package-data 規則。集合比較不只比較數量，也不永久硬編碼 12；缺一檔、多一錯路徑、空目錄、整個目錄缺失皆須被 gate 擋住。
- [ ] 兩個 release 入口共用同一 checker：檢查 wheel／sdist 內容與禁用模板字串；archive 開啟錯誤、檔案不存在、讀取失敗均回非零。PR CI 即跑此 gate，不能只在 tag release 時跑。
- [ ] 在 install／upgrade 的任何寫入或 checkpoint 前，完整驗證並 render 所需 templates；缺失或讀取錯誤回 exit 1 + 單一 JSON，`status=failed`，帶 instance/root、失敗資產與可操作訊息。既有 artifact checksum 錯誤的 exit 2 契約維持。
- [ ] plan-only install／upgrade 也驗模板可讀，缺失回非零 JSON；純 status／uninstall 不因不需要的模板而失效。
- [ ] 缺模板反例以「最後一個 template 缺失」確認不會先寫入部分檔案、更新 install record 或碰 systemd。若預檢後發生一般 I/O 失敗，report 誠實保留已寫檔清單，不宣稱整體原子性；upgrade 沿用既有 rollback 契約。
- [ ] 在乾淨容器 venv 安裝 candidate wheel，從 checkout 外以該 venv python 跑 `deploy install --apply --verify`；驗 exit、JSON 欄位、applied_files、permissions、install record 的版本與 SHA。移除 PYTHONPATH 污染並記錄模組實際載入位置。
- [ ] 測試容器不接 host user bus；無 systemd 時報告 skip，不能冒稱 service 啟動已驗證。單純 `--home-dir` 只隔離檔案落點，不足以隔離 `loginctl`／`systemctl` 的副作用。
- [ ] 文件補「必須使用裝有 wheel 的 Python」，以及 deploy 寫 units/config、CLI PATH 由 pip/pipx 安裝處理的邊界。

驗收：issue S2-1／3／4／5／7／8 全部有對應證據；source tests 綠、artifact 內容與 installed execution 皆綠。正式新版容器重跑列入第 9 節收尾，不覆寫舊 v0.2.7 release。

## 6. 工作 C：#325 README 前置修正

建議 branch：`feature/325-install-prerequisites`；開始條件：#324 已 merge，且歷史 RED report 可查。

- [ ] README §A 明列 Ubuntu/Debian 的 `python3 python3-venv git`；說明 git 是 git+SHA dependencies 所需。pipx 段補安裝 pipx、git、ensurepath 與新 shell 驗證。
- [ ] 安裝步驟要求 pip 非零即停，補查 venv console script、`Cannot find command 'git'` 與 PATH 問題的排錯；不要用 `pipx upgrade` 暗示能從 PyPI 取得本 repo 的 release。
- [ ] release-contract distribution 節與新 release notes 同步前置。不要更改既有 artifact 或為消除 git 需求擴張 distribution 範圍。
- [ ] 用 candidate README 重跑 #324 的 TC-1／TC-1p → GREEN；TC-1c／TC-1g 維持 GREEN。歷史 README + 舊 artifact 仍保留精確 RED oracle，current README + candidate wheel 不允許 expected failure。

驗收：僅按文件宣告的套件建立容器即可完成 venv／pipx 安裝，完整 entry points 與 CLI exits 正確；#325 PR 附 RED/GREEN 對照與各自 README revision。

## 7. 工作 D：#296 bro 單一來源

建議 branch：`feature/296-bro-canonical-source`。

- [ ] 盤點 repo／runtime／外部 checkout 的逐檔相對路徑、hash、symlink target 與 inode，保留原始副本；列出所有呼叫入口（含 gemma4 hook 與 notify 使用者）。不收集 secret 值。
- [ ] 以 repo 為 canonical，將外部 `notify.py`、測試與必要 SKILL 說明先作功能及機敏檢查，再整合進 repo；保留 repo 的 MessagePaneMap／source-pane 行為。用 fixtures 與 fake sender 驗 gateway-first、direct fallback、dry-run、message-id→pane 追溯，不對外發 Telegram。
- [ ] 新增有 `--check`／dry-run／apply 的 scoped 安裝工具；source 與 runtime target 都可參數化。建議以版本化 snapshot 複製部署並記錄 source commit + 內容 hash，runtime symlink 指向該 snapshot，避免 runtime 隨開發 branch 即時改動；開發環境可明示選 checkout symlink 模式。
- [ ] 兩種模式都禁止 hardlink。先在 temp roots 演練：既有實體目錄有差異時拒絕覆寫、broken symlink、有增刪檔、重跑冪等、失敗回復、舊 snapshot 可回滾。排除 cache，但不得排除 SKILL／scripts／tests 等功能資產來掩蓋漂移。
- [ ] CI 比較暫存部署與 canonical 檔案集合／hash，並對刻意漂移反例 FAIL；現場 `--check` 比較 runtime 與部署 receipt，分辨內容遭改與新版本尚未部署。CI 不依賴作者機器的外部 custom-skills 路徑。
- [ ] 完成測試後才做現場切換，先可回復備份舊 target／副本；驗 runtime resolve 路徑與內容、依賴 import、dry-run 與 hook 解析。外部舊副本退役保留備份，不再作可編輯來源；回滾只切回既有已驗版本。

驗收：兩側功能整合測試綠；canonical／部署內容一致且 provenance 可查；原子式編輯任一普通副本都不能靠 hardlink 偷渡同步；drift 能被偵測；runtime dry-run 綠。僅修 repo 而未切換 runtime，記為「實作完成、部署待完成」。

## 8. 工作 E：#328 executor／model 可觀測性

建議 branches：Cortex `feature/jobs-execution-identity`，paulshaclaw `feature/328-jobs-execution-identity`。

責任鏈：Cortex registry job／WorkflowStep → Cortex status projection → paulshaclaw `_ingest_workflow_run()` → `JobRow` → JOBS widget。Cortex 決定身份事實，cockpit 只解析與顯示。

- [ ] 先核對 Cortex remote、pin、`WorkflowStep` 與 job binding；重用既有 status identity 契約（若已有修復）。同 phase 有多卡與 retries，不能只取第一個 phase 相同的 step。
- [ ] producer 選取順序：已綁定的當前 in-flight job → 當前卡最後一次實際執行的 job → 沒有可證明 job 時顯示未派工／unknown。必須校驗 repo、run、card、attempt 綁定，不能跨 run 借用舊模型。planned step 身份若顯示，明確標為「預定」，不得冒充實際執行。
- [ ] 提案為 additive status 欄位：`executor`、`model`、`job_id`、`card`、`identity_source` 與執行狀態；內部 job `model_id` 映射成公開 `model`。欄位名稱以既有上游契約核對後固定，producer／consumer 使用同一組 fixture。
- [ ] 所有可顯示 workflow 的 status sections 都須覆蓋，不只 attention。claim／not_claimable 無 worker 時顯示未派工；manager deterministic step 明示 deterministic；needs_human 的最後執行者標示「上次執行」，避免被讀成仍在跑。
- [ ] consumer 在 JobRow 增加有預設值的欄位，ingest 使用 typed fallback；缺欄位的舊 Cortex 保持可讀，顯示未提供，不從 persona 推 executor/model。
- [ ] JOBS 加 agent · model 的 detail/trailer；保留 project/stage/persona、reason、next_actions、run_id；窄寬度可摘要，但展開後完整模型字串可見，處理 CJK 寬度與 markup 字元。
- [ ] 測試矩陣：新／舊 schema、缺值／null／型別錯誤、同 phase 多卡、provider retry／換模型、verify→review、未派工、阻塞、完成、跨 repo 同 work_id、未知 executor、長 model、窄面板與刷新。
- [ ] 上游 PR merge 後固定實際 SHA；下游更新 Cortex pin，跑 `tests/test_cortex_alignment.py`。既有約定要求 Hippo／Cortex lifecycle 對齊，必要時成對移 pin，但只採經驗證的版本；不能直接用 floating main。
- [ ] 在隔離測試環境用已安裝的 Cortex producer 輸出，餵給已安裝的 paulshaclaw cockpit，與 registry 的實際 job 對照。Textual headless 測試覆蓋 render／刷新；保留去識別化 snapshot 與結果。

驗收：operator 看得到某 run 的當前或上次實際 executor／model，以及清楚的狀態；來源可追到具相同 run/card 綁定的 job。完成 producer、consumer、pin 與 runtime 整合證據後，才由下游 PR `Closes #328`。

## 9. 整合、發布與結案

- [ ] 整合者解決 README／release-contract／pyproject／CI 交疊；各 PR 依動工時核對的 repo policy 更新 changelog，不另行遷移紀錄格式；release 收尾同步 VERSION／pyproject／CHANGELOG。
- [ ] 每線跑相關 unit／integration tests；整合後執行 `./scripts/preflight-tests.sh`（含 `custom-skills/bro/tests/`）、TestPilot stub／discovery、`openspec validate --all --strict` 與目標版本 policy preflight。
- [ ] 組裝一次最終 wheel／sdist，通過共享內容 gate、sdist rebuild 與 checkout 外安裝測試；Docker 跑 current README 的 venv／pipx 與 deploy apply cases。完整依賴安裝不能用 `--no-deps` 代替，`--no-deps` 只用在明示控制組。
- [ ] 每個 PR 的 CI 綠、actionable review threads 全處置、HEAD 與受審查 revision 相同、mergeability 確認後才 merge；再次確認 GitHub 合併與 issue closing cross-reference。
- [ ] 以新的未使用版本發布（版本號發布前查 tags/releases 決定）；保留 v0.2.7 作歷史重現。下載真正 Release assets 驗 checksums，重跑安裝與 deploy cases，確認 published artifact 與測試對象一致。
- [ ] #296 留下本機切換／回滾 receipt；#328 留下已安裝 producer→consumer 證據。release 安裝、service 啟動與 Trust Root lifecycle 是不同驗收，不把本計畫擴成全部 Cortex backlog 修復。
- [ ] 完成後重新查未過濾 open issues；目標集合這 5 件全結案，期間新增 issue 另列，不無限擴張本輪 scope。若使用 Cortex 派工，另完成該 run 的正式 terminal closeout，不直接改 registry。

## 10. 證據交付與計畫自檢

每線附：base／final SHA、issue／PR、變更檔案、測試命令與 exit、RED/GREEN report、artifact hash（如適用）、殘餘風險、部署狀態。原始 Docker logs／私有 runtime receipts 留在隔離 evidence 目錄；進 repo／PR 的摘要去除機敏值。

本計畫已逐項自檢：五件皆有 owner、scope、順序與 exit gate；#324 的預期 RED 不掩蓋基礎設施失敗；#326 的前置檢查先於寫入；#296 保留雙側功能且包含現場切換；#328 包含上游 producer 與 dependency pin，且區分 planned／actual／last execution。

尚待實作時核實：TestPilot core 實際 API／版本、Cortex 上游最新狀態、雙份 bro 全量語意整合、Docker 可用性與最終 release 版本。這些列為各線第一個 task；本輪未執行 fresh-reader 外部審查或功能測試。
