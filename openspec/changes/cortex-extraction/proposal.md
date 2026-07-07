## Why

#125 Phase 2：治理平面（persona scope 護欄 + coordinator 派工 + control 檔案契約控制面，合計約 3.3k 行）與主 repo 生命週期解耦後，persona 的跨 vendor 定位需要「可單獨安裝、不被記憶產品綁架」的出貨形式；G2 enforce（#124）動工前先定邊界，避免大改後再搬家。設計依據：`docs/superpowers/specs/2026-07-07-cortex-extraction-design.md`（已含 2026-07-07 Codex 對抗審查裁決軌跡：cutover 協議與單寫者不變量採納、control root 隔離與 persona fail-close 重設計推回）。

## What Changes

- 新 repo `hamanpaul/paulsha-cortex`（package `paulsha_cortex`）：`persona/**`、`coordinator/**`、`control/**` 全數遷入，含 `scripts/coordinator/**`、`scripts/service-manager.sh`、manager systemd 單元模板（改由 cortex `install service` 出貨）、persona-scope CI workflow、約 25 個測試檔。新 repo 骨架與 Phase 0/1 工作在 cortex repo 內追蹤，本 change 只管主 repo 遷移刀與 consumer 契約。
- **A′ 零依賴剪線**：cortex 對 paulsha-hippo 零依賴——PHASES 7 字串自帶（主 repo 對齊測試守相等）、`lib/idle.py` 23 行 vendor、`config.paths` 5 函式由 cortex 自帶 paths 模組（同 env 契約 + 等價測試）。「先二後三」的「三」（paulsha-lib）不觸發。
- deck 整包留主 repo（#186 §6 三分裁決）；persona loader 對 deck 維持 lazy import fail-open（選配反向依賴，不入 install_requires；效力=warning 級 lint，非 enforcement）。
- **BREAKING（主 repo）**：刪除 `paulshaclaw/{persona,coordinator,control}/**`；pyproject 依賴 `paulsha-cortex @ git+https://...@<commit-sha>`（SHA pin）；`bot/listener.py`、`cockpit/app.py`、`core/daemon.py` 改 import `paulsha_cortex.control.client`；`psc coordinator` 改 thin shim 委派 cortex CLI；`deploy/planner.py` 移除 manager 單元模板引用；W7 整合測試改 import cortex。
- systemd cutover 協議：停用舊單元→enable cortex 單元、`install service` 冪等、rollback = revert pin + 重 enable 舊單元、雙 daemon 鎖競爭驗證（`manager.lock` flock 單寫者不變量隨包平移）。
- 非目標：paulsha-lib 升格、deck 搬移、G2 enforce 翻牌（#124，拆分後於 cortex repo 內做）、hippo 任何變動、PyPI 發版、control root 多實例／租戶隔離重設計。

## Capabilities

### New Capabilities
- `cortex-consumer`: 主 repo 對 paulsha-cortex 的依賴契約——SHA pin 依賴、允許 import 面限定 `paulsha_cortex.control.client` 與 CLI shim 的 lazy import（其餘 internals 不得 import）、三個對齊測試（PHASES 相等性、paths 等價、deck↔persona 對齊）以主 repo 為契約交會點、path-split 相容（`~/.agents/control` 零資料遷移）、cutover 驗收（雙 daemon 鎖競爭、install 冪等）。

### Modified Capabilities
- `psc-cli-entry`: `psc coordinator` 路由目標由 `paulshaclaw.coordinator.cli` 改為 thin shim lazy import `paulsha_cortex` CLI（使用者面行為不變；cortex 未安裝時明確報錯指引）。
- `hippo-consumer`: 主 repo runtime 對 `paulsha_hippo.lib.*` 的 import 面清零（僅存兩處 lib import 隨 persona/coordinator 遷出）；hippo 依賴保留於測試面（PHASES 對齊測試需同裝 hippo 與 cortex）。

## Impact

- 受影響碼：`paulshaclaw/{persona,coordinator,control}/**`（遷出）、`paulshaclaw/cli.py`（shim）、`bot/listener.py`、`cockpit/app.py`、`core/daemon.py`（import 改線）、`deploy/planner.py` 與 systemd 模板、`scripts/coordinator/**`、`scripts/service-manager.sh`、`.github/workflows/persona-scope.yml`（遷出）、pyproject（pin cortex）、`tests/`（約 25 檔遷出；新增三個對齊測試；W7 整合測試改線）。
- Specs：`coordinator-cli`、`coordinator-tick`、`coordinator-completion-tick`、`coordinator-headless-dispatch`、`manager-control-plane`、`persona-skills-binding`、`stage4`（persona 部分）隨拆包遷入 cortex openspec（行為要求不變，故不列 Modified）。
- 文件：CLAUDE.md／README 治理平面章節改指向 cortex（R-18 同 PR）；命名系統新增 `paulsha-cortex` 條目。
- 資料：`~/.agents/control` runtime 零遷移；`PSC_*` env 覆寫契約不變。
- 風險緩解沿 hippo 教訓：fresh-install E2E 強制閘、跨 repo issue 引用掛 `policy-exempt:issue-link`、worktree 測試假失敗先交叉驗證。
