## Why

repo 功能完成度高但易用性最弱（#125 評估補充）：零 `[project.scripts]` 入口、`Path.home()` 散落 29 處無 facade（#91）、版號治理死（VERSION 0.0.0 vs pyproject 0.1.0、0 tag）。Phase 0 不動 repo 邊界即可交付易用性，同時是 #125 拆包的解耦前置。

## What Changes

- PR-A：新增 `psc` 傘狀 CLI（薄 dispatcher → memory.cli / coordinator.cli，零行為變更；`python -m` 舊入口保留）；VERSION 對齊 0.1.0 + tag `v0.1.0`（R-07 正規化比對）+ 一致性測試；清 `janitor/`、`chat/` 空殼（保留 `config/` 給 facade）。
- PR-B：新增 `paulshaclaw/config/paths.py` env facade（`PSC_*` env → 預設；`Path.home()` 僅允許存在於 facade 本體）；遷移 29 處呼叫點與硬編碼預設；收編 P0-1 Stage A 的過渡 env；LLM 後端讀取集中經 facade/config 層並補文件。

## Capabilities

### New Capabilities
- `psc-cli-entry`: `psc` 傘狀命令入口——子命令路由、exit code、與既有 module 入口並存。
- `env-path-facade`: 路徑解析 facade——`PSC_*` env 覆寫鏈、path-split 契約預設、facade 為唯一 `Path.home()` 呼叫點。

### Modified Capabilities
<!-- 版號治理屬 repo 慣例（R-07），不涉既有 capability requirement 變更 -->

## Impact

- 受影響碼：`pyproject.toml`（scripts）、新 `paulshaclaw/cli.py`、新 `paulshaclaw/config/paths.py`、29 處 `Path.home()` call site、`coordinator/seams.py`、`memory/importer/backfill.py`、`VERSION`。
- 依賴序：P0-1 Stage A（2 處 env 化）→ PR-B facade 收編；PR-A 無依賴可先行。
- 部署：hooks 為複製部署——若 hook 引用 facade，交付 checklist 須含重跑 install 同步。
- tag 推送屬對外動作：由 owner 執行或明確授權後代行。
