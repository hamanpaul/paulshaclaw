# launcher-anywhere-startup-v2 Host Runtime Verification

- 驗證日期：2026-08-31（Asia/Taipei）
- candidate：`f0e7097e4f045d0a16f3af0a8b8a1cc80da1a248`
- installed version：`0.2.7`
- wheel SHA-256：`c5e0c86e990ea72339826919ce89eed79690344b7a2af02bad8e522d907cc29f`
- wheel：`paulshaclaw-0.2.7-py3-none-any.whl`

## Deterministic gates

- Cortex Manager 在 candidate worktree 重跑完整 pytest：`840 passed`，gate ledger `exit_code=0`。
- root 在 detached candidate worktree 重跑 launcher 聚焦測試：`12 passed`。
- `bash -n scripts/start.sh scripts/release-artifacts.sh` 通過。
- built wheel 內容已確認包含：
  - `paulshaclaw/core/commands.json`
  - `paulshaclaw/cockpit/cockpit.tcss`
  - `paulshaclaw/launcher/{cli,lock,services,supervisor}.py`

## Installed identity

- executable：`/home/paul_chen/.local/bin/paulshaclaw`
- resolved executable：`/home/paul_chen/.local/share/pipx/venvs/paulshaclaw/bin/paulshaclaw`
- import path：`/home/paul_chen/.local/share/pipx/venvs/paulshaclaw/lib/python3.12/site-packages/paulshaclaw/__init__.py`
- installed `core/commands.json`：存在。
- 驗證命令均清除 `PYTHONPATH`，未從 repo worktree import。

## `/tmp` no-cockpit live proof

1. 在 `/tmp` 執行裸 executable 的 `paulshaclaw --no-cockpit`。
2. start lock holder PID `950144`，其 `/proc/950144/cwd` 為 `/tmp`。
3. console 明確回報現有 Cortex monitor 與 nested manager lock 已辨識，未啟 fallback。
4. Telegram ready file size 為 `6`，launcher、cost、telegram supervisor、listener 均存活。
5. 從 `/tmp` 執行 `paulshaclaw down`，回報 `status=taken-over` 與 `SIGTERM pid=950144`。
6. holder 與三個子程序全數消失，start lock 回到 `held=false`；foreground exit `143` 為被正式 down 路徑送 SIGTERM 的預期結果。

## `/var/tmp` bare cockpit live proof

1. 建立獨立 tmux session `psc-anywhere-334-live`，pane cwd 設為 `/var/tmp`，command 僅為 `paulshaclaw`。
2. start lock holder PID `956665`，其子程序出現 installed `python -m paulshaclaw.cockpit --cockpit-pane %104`。
3. tmux capture 顯示 cockpit 已渲染 WORK、JOBS、manager、tick 與 help/quit 操作列。
4. 對 cockpit 送出 `q`；tmux session 正常消失，launcher、cost、dream zombie、telegram supervisor、listener、cockpit 六個 PID 全數回收，start lock 回到 `held=false`。

## Cortex lock regression proof

- live 前 legacy `/home/paul_chen/.agents/control/manager.lock` 為 free。
- live 前與 live 中 `/home/paul_chen/.agents/control/cortex/manager.lock` 均為 held。
- launcher console 回報 `cortex manager 已在運行（manager.lock 被持有），fallback 不重起 manager daemon`。
- 因此本次驗證直接命中舊版會誤判、候選必須正確處理的 nested-lock 條件。

## Reviewer environment note

Spark verification sandbox 為唯讀環境，`/tmp` 與 `/var/tmp` 均不可寫，因此該 sandbox 的 `tempfile` 初始化與 live proof 無法執行。這是 reviewer 環境限制，不取代上述 host gate；其指出 candidate 未包含 apply-ready OpenSpec change 則是真缺口，repair candidate 必須補入後再重驗。
