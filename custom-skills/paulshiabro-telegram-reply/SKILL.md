---
name: paulshiabro-telegram-reply
description: Use whenever the user says "以bro回覆我", "以paulshiabro回覆我", "用 bro 回我", "從 telegram 回我", or otherwise wants the answer delivered through the local PaulShiaBro Telegram service instead of only appearing in the CLI. Use this even if they mention only bro/PaulShiaBro without saying "Telegram" explicitly.
---

# PaulShiaBro Telegram Reply

Deliver the finished reply through the local PaulShiaBro Telegram bridge, then echo the same content in the CLI.

## When to use

- The user explicitly asks for a reply "以bro" or "以paulshiabro" 回覆
- The user wants the answer sent via PaulShiaBro / bro / Telegram instead of only shown inline
- The user wants the same reply both sent to Telegram and shown back in the terminal

## Workflow

1. Draft the final reply text first.
2. Find the repository root with `git rev-parse --show-toplevel`.
3. If the current working tree is not a `paulshaclaw` checkout with `.venv` available, stop and explain that the local PaulShiaBro bridge is unavailable from this directory.
4. If the current context provides a source Telegram user id, pass `--source-user-id <id>`.
5. If no source Telegram user id is available, omit that flag so the bridge fans out to all allowed users with known chat bindings.
6. Send the reply through the bridge.
7. After successful delivery, echo the same reply text in the CLI.

## Preferred command

Use the repo venv and the local bridge module:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
"$REPO_ROOT/.venv/bin/python" -m paulshaclaw.bot.reply \
  --text '最終回覆內容放這裡'
```

With a source user id:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
"$REPO_ROOT/.venv/bin/python" -m paulshaclaw.bot.reply \
  --text '最終回覆內容放這裡' \
  --source-user-id 8313353234
```

## Multiline or quote-heavy replies

If the reply contains quotes or multiple lines, prefer a tiny Python wrapper so the text stays exact:

```bash
REPO_ROOT=$(git rev-parse --show-toplevel)
"$REPO_ROOT/.venv/bin/python" - <<'PY'
from paulshaclaw.bot.reply import build_reply_bridge, _format_delivery_summary

text = """把最終 multiline 回覆完整放在這裡。"""
targets = build_reply_bridge().reply(text=text, source_user_id=None)
print(_format_delivery_summary(targets))
print(text)
PY
```

If you know the source user id, pass it into `reply(...)` instead of `None`.

## Output expectations

- On success, show the delivery summary plus the full reply text.
- On failure, surface the bridge error plainly and do not pretend the Telegram send succeeded.
- Do not rewrite the reply after sending; the CLI echo should match what was delivered.
