## Why

#125 Phase 1：memory 子系統（31k LOC、repo 佔比 88%）已具產品完成度，但「別人／未來的你裝起來用」的易用性是最弱面；抽成獨立 repo `paulsha-hippo` 是解易用性與跨 LLM vendor 定位的槓桿。設計依據：`docs/superpowers/specs/2026-07-06-memory-extraction-hippo-design.md`（已含 Codex 對抗審查四項修正）。

## What Changes

- 新 repo `hamanpaul/paulsha-hippo`：從 new-project-template 建立（無歷史、conventions 1.0.12、deident gate day-1）；`memory/**` 全數遷入；共用件以自足子 package `paulsha_hippo.lib`（lifecycle/idle/jsonl）出貨（先二後三，CI import-lint 護欄）。
- 單一權威路徑 resolver（`paulsha_hippo.paths`）：優先序 CLI 旗標 > `HIPPO_MEMORY_ROOT` > `PSC_MEMORY_ROOT`（deprecated 警告）> config.yaml > 預設 `~/.agents/memory`；`hippo doctor` 對雙 root 不一致 FAIL。
- 蒸餾 LLM backend 三檔位：`claude-headless`（預設，零 key/oauth）、`openai-compatible`（內建 http-runner）、`custom-argv`（保留現行 `agent_exec`）。
- 常駐服務沿 G3 決策樹：`hippo install service`（systemd 偵測→user units；不可用→`hippo dream supervise` 前景模式）。
- **BREAKING（主 repo）**：刪除 `paulshaclaw/memory/**`、`paulshaclaw/lifecycle/**`；pyproject 依賴 `paulsha-hippo @ git+https://...@<commit-sha>`（SHA pin）；`psc` CLI memory 子樹移除；`core/daemon.py` 解耦 atomizer config（agent argv 改 daemon 自有 config）；`start.sh` dream 段改呼叫 `hippo dream supervise`（cutover + 回滾步驟）。
- 動工前置：站穩閘 G1–G5 全綠 + `p1-memory-three-gaps`/`g5-hook-install`/`p2-usability-phase0` 落地（避免 move-vs-modify）。

## Capabilities

### New Capabilities
- `hippo-consumer`: 主 repo 對 paulsha-hippo 的依賴契約——SHA pin 依賴、允許 import 面限定 `paulsha_hippo.lib.{lifecycle,idle,jsonl}`（daemon 不得 import hippo internals）、path-split 相容（`~/.agents/memory` 零資料遷移）、consumer tests（/agent 無 memory 綠、舊 PSC hooks 同 root、systemd-unavailable fallback）。

### Modified Capabilities
- `agent-command`: `/agent start` 的 agent 命令 argv 來源由 atomizer config 改為 daemon 自有 config 區段（安裝為套件後 `resolve_command_argv` 相對路徑解析必壞）。
- `stage7`: dream 常駐部署移交 hippo installer（`hippo install service`）；`start.sh` dream supervisor 段 cutover 為 PATH 檢測呼叫 `hippo dream supervise`，未安裝則跳過並警告。

## Impact

- 受影響碼：`paulshaclaw/memory/**`（遷出）、`paulshaclaw/lifecycle/**`（遷出）、`core/daemon.py`、`persona/contract.py`、`coordinator/manager.py`、`scripts/start.sh`、`scripts/claude-gemma4`（→hippo examples）、pyproject、deploy planner dream unit。
- Specs：`openspec/specs/stage2-*`（12 capability）隨拆包遷入 hippo openspec（行為要求不變，故不列 Modified）。
- 文件：CLAUDE.md／README／docs stage 2 章節改指向 hippo（R-18 同 PR）；#125 工作名 `paulsha-memory` 以 issue comment 更名註記。
- 資料：`~/.agents/memory` runtime 零遷移；secret 改 `~/.config/paulsha-hippo/secret.env`（提供指引、不自動搬）。
