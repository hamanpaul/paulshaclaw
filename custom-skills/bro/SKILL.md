---
name: bro
description: Use whenever the user wants the answer sent through PaulShiaBro / bro / Telegram, especially when the current workspace is unrelated to paulshaclaw and the reply flow must not depend on the active source tree or repo venv. ALSO trigger automatically when an incoming message is prefixed with [bro:<user_id>] (routed from the PaulShiaBro daemon): parse <user_id>, complete the request, then reply via this skill with --source-user-id <user_id>.
---

# PaulShiaBro Telegram Reply

Deliver the finished reply through the local PaulShiaBro Telegram bridge, then echo the same content in the CLI.

This skill now carries its own skill-local tool, so it does **not** depend on the current workspace being a `paulshaclaw` checkout.

## When to use

- **An incoming message is prefixed with `[bro:<user_id>]`** (routed from the PaulShiaBro daemon). Treat this as a request to reply to that Telegram user: parse `<user_id>`, complete the work, then reply via this skill passing `--source-user-id <user_id>`. This is the primary automatic trigger.
- The user explicitly asks for a reply "以bro" or "以paulshiabro" 回覆
- The user wants the answer sent via PaulShiaBro / bro / Telegram instead of only shown inline
- The user wants the same reply both sent to Telegram and shown back in the terminal

## Workflow

1. Draft the final reply text first.
2. Use the skill-local tool at `/home/paul_chen/.agents/skills/bro/scripts/reply_bridge.py`.
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
python3 /home/paul_chen/.agents/skills/bro/scripts/reply_bridge.py \
  --text '最終回覆內容放這裡'
```

With a source user id:

```bash
python3 /home/paul_chen/.agents/skills/bro/scripts/reply_bridge.py \
  --text '最終回覆內容放這裡' \
  --source-user-id 8313353234
```

Dry-run without sending:

```bash
python3 /home/paul_chen/.agents/skills/bro/scripts/reply_bridge.py \
  --text '最終回覆內容放這裡' \
  --dry-run
```

## Multiline or quote-heavy replies

If the reply contains quotes or multiple lines, invoke the bundled tool through a tiny Python wrapper so the text stays exact:

```bash
python3 - <<'PY'
import subprocess
import sys

text = """把最終 multiline 回覆完整放在這裡。"""
tool = "/home/paul_chen/.agents/skills/bro/scripts/reply_bridge.py"
raise SystemExit(subprocess.run([sys.executable, tool, "--text", text], check=False).returncode)
PY
```

If you know the source user id, add `--source-user-id`.

## Quick reference

| Situation | Command shape |
| --- | --- |
| Normal reply | `python3 .../reply_bridge.py --text '...'` |
| Reply to source user only | `python3 .../reply_bridge.py --text '...' --source-user-id 123` |
| Verify wiring without sending | `python3 .../reply_bridge.py --text '...' --dry-run` |
| Override config paths | add `--config ... --secret-env ... --bindings-path ...` |

## Common mistakes

- Running the old repo-venv command from an unrelated workspace — use the bundled tool instead.
- Assuming the active git repo matters — it does not.
- Omitting `--source-user-id` when you need a one-user reply.
- Pretending send succeeded after a bridge error — surface the error plainly.

## Output expectations

- On success, show the delivery summary plus the full reply text.
- On failure, surface the bridge error plainly and do not pretend the Telegram send succeeded.
- Do not rewrite the reply after sending; the CLI echo should match what was delivered.
