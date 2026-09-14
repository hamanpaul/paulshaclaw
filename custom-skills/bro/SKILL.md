---
name: bro
description: Use whenever the user wants the answer sent through PaulShiaBro / bro / Telegram, especially when the current workspace is unrelated to paulshaclaw and the reply flow must not depend on the active source tree or repo venv.
---

# PaulShiaBro Telegram Reply

Deliver the finished reply through the local PaulShiaBro Telegram bridge, then echo the same content in the CLI.

This skill now carries its own skill-local tool, so it does **not** depend on the current workspace being a `paulshaclaw` checkout.

**Single source of truth（#296）**：本目錄（`paulshaclaw/custom-skills/bro/`）是唯一 canonical 副本，CI 跑 `custom-skills/bro/tests/`。runtime 載入點 `~/.agents/skills/bro` 必須是指向本 repo checkout 的 symlink，不得另存實體副本或以 hardlink 同步；`tests/test_runtime_copy_drift.py` 會在本機把漂移攤出來。

## When to use

- The user explicitly asks for a reply "以bro" or "以paulshiabro" 回覆
- The user wants the answer sent via PaulShiaBro / bro / Telegram instead of only shown inline
- The user wants the same reply both sent to Telegram and shown back in the terminal

## Two tools

| Tool | 用途 |
| --- | --- |
| `reply_bridge.py` | **回覆**流程：把最終回覆送給 source user（或所有綁定用戶），CLI 同步 echo。 |
| `notify.py` | **單向通知**：長跑任務進度、告警、里程碑等 fire-and-forget 訊息（無需對話語境）。gateway-first + direct fallback，適合背景/長任務每隔一段時間回報。 |

兩者送達同一個 PaulShiaBro bot。回覆選 `reply_bridge.py`；狀態通知選 `notify.py`。

## Workflow

1. Draft the final reply text first.
2. Use the skill-local tool at `~/.agents/skills/bro/scripts/reply_bridge.py`.
3. If the current context provides a source Telegram user id, pass `--source-user-id <id>`.
4. If no source Telegram user id is available, omit that flag so the bridge fans out to all allowed users with known chat bindings.
5. Send the reply through the bridge.
6. After successful delivery, echo the same reply text in the CLI.

## Bundled tool

The bundled tool is self-contained and uses only these runtime files:

- `~/.config/paulshaclaw/paulshaclaw.state.json`
- `~/.config/paulshaclaw/paulshaclaw.telegram.secret.env`
- `~/.agents/state/telegram-chat-bindings.json`

It can be run from **any** working directory.

## Preferred command

```bash
python3 ~/.agents/skills/bro/scripts/reply_bridge.py \
  --text '最終回覆內容放這裡'
```

With a source user id:

```bash
python3 ~/.agents/skills/bro/scripts/reply_bridge.py \
  --text '最終回覆內容放這裡' \
  --source-user-id 8313353234
```

Dry-run without sending:

```bash
python3 ~/.agents/skills/bro/scripts/reply_bridge.py \
  --text '最終回覆內容放這裡' \
  --dry-run
```

## Multiline or quote-heavy replies

If the reply contains quotes or multiple lines, invoke the bundled tool through a tiny Python wrapper so the text stays exact:

```bash
python3 - <<'PY'
import os
import subprocess
import sys

text = """把最終 multiline 回覆完整放在這裡。"""
tool = os.path.expanduser("~/.agents/skills/bro/scripts/reply_bridge.py")
raise SystemExit(subprocess.run([sys.executable, tool, "--text", text], check=False).returncode)
PY
```

If you know the source user id, add `--source-user-id`.

## One-way notification（notify.py）

長跑任務要「每隔一段時間回報進度」時用這支，不要用 reply_bridge。送達策略兩層、
任一成功即算送達：先探測本地 max gateway（127.0.0.1:7777，常沒開，探不到就跳過、
不算失敗），再 fallback 到 canonical paulshaclaw config 直打 Telegram Bot API
（復用 `reply_bridge.send_reply()`，fan-out 給綁定用戶）。祕密只在 runtime 讀取、
絕不輸出。

```bash
# 單向通知（fan-out 給所有綁定用戶）
python3 ~/.agents/skills/bro/scripts/notify.py --text '任務進度：120/415 案完成'

# 只送給特定綁定用戶
python3 ~/.agents/skills/bro/scripts/notify.py --text '...' --source-user-id 8313353234

# 從 stdin 讀（multiline 安全）
printf '第一行\n第二行' | python3 ~/.agents/skills/bro/scripts/notify.py

# 強制跳過 gateway / 驗接線不實送
python3 .../notify.py --text '...' --no-gateway
python3 .../notify.py --text '...' --dry-run
```

背景長任務典型用法：spawn 一支 detached 迴圈，每 N 分鐘算進度後呼叫 `notify.py`，
任務結束送最終摘要後退出（見 test suite `bro/tests/test_notify.py` 對送達路徑選擇的
覆蓋）。

## Quick reference

| Situation | Command shape |
| --- | --- |
| Normal reply | `python3 .../reply_bridge.py --text '...'` |
| Reply to source user only | `python3 .../reply_bridge.py --text '...' --source-user-id 123` |
| Verify wiring without sending | `python3 .../reply_bridge.py --text '...' --dry-run` |
| Override config paths | add `--config ... --secret-env ... --bindings-path ...` |
| One-way status notification | `python3 .../notify.py --text '...'` |
| Notify one bound user | `python3 .../notify.py --text '...' --source-user-id 123` |
| Force direct (skip gateway) | `python3 .../notify.py --text '...' --no-gateway` |

## Common mistakes

- Running the old repo-venv command from an unrelated workspace — use the bundled tool instead.
- Assuming the active git repo matters — it does not.
- Omitting `--source-user-id` when you need a one-user reply.
- Pretending send succeeded after a bridge error — surface the error plainly.

## Output expectations

- On success, show the delivery summary plus the full reply text.
- On failure, surface the bridge error plainly and do not pretend the Telegram send succeeded.
- Do not rewrite the reply after sending; the CLI echo should match what was delivered.
