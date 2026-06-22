## Why

persona-dispatch-guardrail 的零件齊全卻仍 dormant：`coordinator.autonomy.dispatch_ready` 送進 Dispatcher 的 `command` 是佔位註解、`persona` 只是不透明字串，`build_persona_context`／`render_contract_prompt` 在 production 0 命中——設計核心「① 契約 render 進 prompt」從未發生。Phase A 是把 persona 通電進 live runtime（manager daemon）的第一步：先接上 coordinator→persona 那條線，零行為改變、零 live 接觸、解鎖後續 pane 配置與 systemd 化。

## What Changes

- 新增 `paulshaclaw/coordinator/contract_command.py`：`build_dispatch_command(role, *, task, plan_path, executor, catalog)` 純字串函式（強制點 ①），reuse `persona.render.render_contract_prompt` 把契約 render 成 prompt 前言，`shlex.join` 收成可送進 pane 的安全單行 copilot 指令。純函式、零 I/O（只嵌 plan_path 參照，copilot 於 worktree 內自行讀計畫）。
- 修改 `coordinator.autonomy.dispatch_ready`：`command=` 改 import 上述函式產出，取代既有佔位註解 `# dispatch {slice_id} (plan=...)`。
- 新增 `paulshaclaw/persona/personas.yaml` 頂層 `enforcement: shadow` 旗標 + `loader.load_enforcement()` reader（fail-safe 退 `shadow`，缺檔／壞 YAML／非法值一律保守）。目前無人消費，僅顯式化設計 §4 缺的全域旗標。
- **零行為改變**：`dispatch_ready` 既有測試僅斷言 `task`/`persona`，不碰 `command` 內容；`load_catalog` 只讀 `roles`，新增頂層 `enforcement` key 不影響 catalog 載入。

## Capabilities

### New Capabilities

<!-- 無；Phase A 不引入新 capability，僅修改既有 coordinator-cli 與 stage4 -->

### Modified Capabilities

- `coordinator-cli`: fan-out 派工指令由佔位註解改為「render 過 persona 契約的 copilot 指令」；新增 `build_dispatch_command` 作為 coordinator→persona 的契約拼裝原語（強制點 ①）。
- `stage4`: persona catalog 新增全域 `enforcement` 旗標（`shadow`/`enforce`），可由 `load_enforcement` 讀取，fail-safe 退 `shadow`；目前不改變既有護欄行為。

## Impact

- 代碼：新增 `paulshaclaw/coordinator/contract_command.py`；修改 `paulshaclaw/coordinator/autonomy.py`、`paulshaclaw/persona/loader.py`、`paulshaclaw/persona/personas.yaml`；新增 `tests/test_coordinator_contract_command.py`、`tests/test_persona_enforcement_flag.py`，修改 `tests/test_persona_phase4_fanout_autonomy.py`。
- 設計依據：`docs/superpowers/specs/2026-06-22-persona-manager-daemon-design.md` §4.1 / §7（Phase A）；實作計畫 `docs/superpowers/plans/2026-06-22-persona-manager-phase-a.md`。
- 無 runtime 行為變更、無新增外部依賴、未碰 daemon／systemd／tmux／真 copilot。`allowed_phases` 仍限 Stage3 canonical vocabulary。
