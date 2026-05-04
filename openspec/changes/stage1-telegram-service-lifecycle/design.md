## Context

Stage 1 already defines the command surface (`/status`, `/dispatch`) and the Telegram authorization router, but no process connects that router to Telegram Bot API. Local startup currently runs monitor plus cockpit only, and Stage 7 deploy templates expose only a core service skeleton. The recovery docs already mention a bot service, so the documented operating model and the actual startup lifecycle have diverged.

The integration target is wmbri-style operator usage: Telegram should be a real remote entrypoint, but it must remain a transport adapter. Dispatch authority stays in the daemon/coordinator boundary. GitHub issue #14 tracks the separate real coordinator adapter; this change only prevents production Telegram startup from pretending local fake dispatch is real.

## Goals / Non-Goals

**Goals:**

- Add a standard-library Telegram long-poll listener entrypoint.
- Keep Telegram command handling behind `TelegramCommandRouter`.
- Start and stop the Telegram listener with `scripts/start.sh`.
- Add deploy templates for a separate Telegram service unit and secret/runtime environment.
- Fail closed when Telegram `/dispatch` is used without a real coordinator backend.
- Cover the behavior with no-network unit and lifecycle tests.

**Non-Goals:**

- No webhook support.
- No BotFather provisioning automation.
- No Telegram button, 2FA, photo, or proactive notification support.
- No real coordinator adapter implementation; that belongs to #14.
- No TUI systemd service.

## Decisions

### Use standard-library long polling

Use `urllib.request` and `json` for `getMe`, `getUpdates`, and `sendMessage`. This avoids adding a framework dependency before the Telegram surface needs buttons, rich message handlers, or webhook hosting.

Alternative considered: `python-telegram-bot`. It would reduce bot boilerplate, but it adds a new dependency and event-loop model while the first required surface is small.

### Keep Telegram transport separate from dispatch

The listener parses Telegram updates and sends replies. It does not call coordinator APIs. It calls `TelegramCommandRouter.handle_message(user_id, text)`, which delegates to `PaulShiaBroDaemon.handle_command(command_text)`.

This preserves the Stage 1 module boundary: bot authorizes and formats messages, core handles commands, and coordinator remains a replaceable seam.

### Require secret environment for bot identity

`PSC_TELEGRAM_BOT_TOKEN` is required. `PSC_TELEGRAM_EXPECTED_USERNAME` and `PSC_TELEGRAM_EXPECTED_BOT_ID` are optional sanity checks. When configured, the listener validates them through `getMe` at startup and exits on mismatch.

This keeps tokens out of repo config and makes accidental connection to the wrong bot visible before the listener starts processing updates.

### Fail closed for production dispatch without backend

The current `LocalCoordinator` is useful for Stage 1 smoke tests, but it is not a production backend. The Telegram listener must construct the daemon in a mode that does not silently use `LocalCoordinator` for `/dispatch`. Until #14 lands a real backend, `/dispatch` from Telegram returns a clear coordinator-not-configured error.

Tests may still inject fake coordinators directly into `PaulShiaBroDaemon`.

### Track background PIDs explicitly in `start.sh`

`scripts/start.sh` should start monitor and Telegram listener as named background processes, then run cockpit in the foreground. Cleanup sends TERM to each known background PID and waits. This makes Ctrl+C and normal TUI exit deterministic.

### Deploy Telegram as a separate unit

Stage 7 should render `<instance>-telegram.service` separately from `<instance>.service`. The Telegram unit can be restarted independently and can load a secret env file containing the bot token.

## Risks / Trade-offs

- Telegram API transient errors can create noisy logs -> use bounded backoff around `getUpdates`.
- Updating offset too early can drop commands -> advance offset only after an update is accepted for processing.
- Retrying `sendMessage` after dispatch can duplicate side effects -> log send failure and do not re-run the command.
- Production dispatch guard can surprise local users expecting fake dispatch -> keep `/status` working and make the `/dispatch` error explicit.
- OpenSpec CLI emits PostHog network flush errors in restricted environments -> treat them as telemetry noise when the command exit code is zero and files are created.

## Migration Plan

1. Land the listener and tests without requiring a live Telegram token.
2. Update `scripts/start.sh` so local integrated startup includes the Telegram listener when token/config are present.
3. Update Stage 7 template catalog and docs so deploy plans include the Telegram unit and secret env.
4. Before #14 is complete, validate `/dispatch` from Telegram fails closed.
5. After #14 is complete, configure the listener/daemon to use the real coordinator backend.

Rollback is reverting the listener, start script, deploy template, tests, and docs from this change. Secret files are not repo-tracked and require no rollback action.

## Open Questions

No blocking question remains for #13. The exact real coordinator backend contract is tracked by #14.
