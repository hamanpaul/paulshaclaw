## Why

Stage 1 currently ships only a Telegram command router; no process connects to Telegram Bot API, and local startup does not run a Telegram service. As the stages move into integrated wmbri usage, Telegram must become a real service with explicit lifecycle, secret handling, and production-safe dispatch behavior.

## What Changes

- Add a standard-library Telegram long-poll listener entrypoint for Stage 1.
- Wire the Telegram listener into `scripts/start.sh` as a background service that exits with the foreground cockpit TUI, including Ctrl+C and TERM.
- Keep Telegram as transport only: commands still flow through `TelegramCommandRouter`, `PaulShiaBroDaemon`, and the coordinator seam.
- Load Telegram bot token and optional bot identity checks from secret environment variables.
- Fail closed for production Telegram `/dispatch` when no real coordinator backend is configured, instead of reporting fake `LocalCoordinator` success.
- Add Stage 7 deploy visibility for a separate Telegram systemd unit and related runtime/secret template assets.
- Update recovery documentation and tests to match the actual Telegram service and log location.

## Capabilities

### New Capabilities

None. This change tightens the Stage 1 runtime and Stage 7 deployment contracts instead of introducing a separate capability.

### Modified Capabilities

- `stage1-core-runtime`: Add the real Telegram listener, Telegram startup contract, token/bot identity fail-closed behavior, and production dispatch guard.
- `stage7`: Extend deploy template requirements so plans include a Telegram service unit and Telegram secret/runtime assets.

## Impact

- Affected runtime code: `paulshaclaw/bot/`, `paulshaclaw/core/daemon.py`, `scripts/start.sh`.
- Affected deploy code: `paulshaclaw/deploy/planner.py`, `paulshaclaw/deploy/templates/`.
- Affected tests: Stage 1 Telegram tests, start script lifecycle tests, Stage 7 deploy template tests.
- Affected docs: `docs/ops/recovery.md`, plus implementation evidence/plan artifacts.
- Dependencies: no new third-party Python dependency; Telegram transport uses the Python standard library.
