# launcher-anywhere-startup-v2 Host Runtime Verification

- 驗證日期：2026-08-31（Asia/Taipei）
- runtime-tested source commit：`ac4c27e004d0e468ca2e8c362b89264cedaf3e3b`
- installed version：`0.2.7`
- wheel SHA-256：`428653ef5067e6bf3b75f46276b884485bbe93df247a76725a4c468c6719b031`
- wheel：`paulshaclaw-0.2.7-py3-none-any.whl`

## Deterministic gates

- Cortex Manager 在 exact candidate worktree 重跑完整 pytest：gate ledger `exit_code=0`、`status=passed`。
- root 在 detached exact-candidate worktree 重跑 launcher 聚焦測試：`21 passed`。
- `openspec validate launcher-anywhere-startup-v2 --strict --no-interactive` 通過。
- `bash -n scripts/start.sh scripts/release-artifacts.sh` 通過。
- built wheel 內容已確認包含：
  - `paulshaclaw/core/commands.json`
  - `paulshaclaw/cockpit/cockpit.tcss`
  - `paulshaclaw/launcher/{cli,lock,services,supervisor}.py`

## Installed identity

- executable：`~/.local/bin/paulshaclaw`
- resolved executable：`~/.local/share/pipx/venvs/paulshaclaw/bin/paulshaclaw`
- import path：`~/.local/share/pipx/venvs/paulshaclaw/lib/python3.12/site-packages/paulshaclaw/__init__.py`
- installed `core/commands.json`：存在。
- 驗證命令均清除 `PYTHONPATH`，未從 repo worktree import。
- installed source hashes：
  - `launcher/cli.py`：`72f38aac01aa7ea8f9aba7e24b157337d431f4d14575727d604253b3e0fc5499`
  - `launcher/supervisor.py`：`0b7dd2255fbde88a8fdb157bd73f12d87a7a1c8aacd53d948f79bc4d69baf221`
  - `core/commands.json`：`31ea0bb0ef872f4755ba1deb6a443ef6e053baea7d67ded6d230469d855eb21f`

## `/tmp` no-cockpit live proof

1. 在 `/tmp` 執行裸 executable 的 `paulshaclaw --no-cockpit`。
2. start lock holder PID `1025356`，其 `/proc/1025356/cwd` 為 `/tmp`。
3. console 明確回報現有 Cortex monitor 與 nested manager lock 已辨識，未啟 fallback。
4. Telegram ready file size 為 `6`，launcher、cost、telegram supervisor、listener 均存活。
5. 從 `/tmp` 執行 `paulshaclaw down`，回報 `status=taken-over` 與 `SIGTERM pid=1025356`。
6. process group `1025356` 的剩餘程序數為 `0`，start lock 回到 `held=false`；foreground exit `143` 為被正式 down 路徑送 SIGTERM 的預期結果。

## `/var/tmp` bare cockpit live proof

1. 建立獨立 tmux session `psc-anywhere-334-ac4`，pane cwd 設為 `/var/tmp`，command 僅為 `paulshaclaw`。
2. start lock holder PID `1029463`，其子程序 cockpit PID 為 `1030389`。
3. tmux capture 顯示 cockpit 已渲染 WORK、JOBS、manager、tick 與 help/quit 操作列。
4. 對 cockpit 送出 `q`；tmux session 正常消失，holder 與 cockpit 均消失，process group `1029463` 的剩餘程序數為 `0`，start lock 回到 `held=false`。

## Cortex lock regression proof

- live 前 legacy `~/.agents/control/manager.lock` 為 free。
- live 前與 live 中 `~/.agents/control/cortex/manager.lock` 均為 held。
- launcher console 回報 `cortex manager 已在運行（manager.lock 被持有），fallback 不重起 manager daemon`。
- 因此本次驗證直接命中舊版會誤判、候選必須正確處理的 nested-lock 條件。

## Reviewer environment note

Spark verification sandbox 為唯讀環境，`/tmp` 與 `/var/tmp` 均不可寫，因此該 sandbox 的 `tempfile` 初始化與 live proof 無法執行。這是 reviewer 環境限制，不取代上述 exact-candidate host gate。Manager 原始 gate ledger 位於 `~/.agents/coordinator/logs/workflow/wf-9589ecbfff-subagent-build-1454.gates.json`，SHA-256 為 `bc4be2e07f8645e339edba2167162c29e05ebccc0dc165272088a133bb7df50d`。

本報告寫入後會產生 descendant review candidate，因此不宣稱檔案能自我引用最終 commit。reviewer 必須機械比對 runtime-tested source commit 到受審 candidate 的 diff：若 `paulshaclaw/**`、`pyproject.toml` 或 `scripts/release-artifacts.sh` 在此後變動，這份 live proof 即失效；只有 evidence、changelog、OpenSpec task 與 test hygiene 變動才可沿用。
