## Why

Stage 1 runtime commands are currently split between hard-coded daemon branches, Telegram response formatting, and ad hoc help behavior. Adding `/tmate` support and Telegram command-menu discovery would increase drift unless command metadata, help text, and dispatch routing share one source of truth.

## What Changes

- Add a Stage 1 runtime command registry in JSON that declares command name, usage, summary, Telegram menu metadata, and `func_call`.
- Route `/help`, `/status`, `/dispatch`, and `/tmate` through the registry-backed dispatcher while preserving existing `/status` and `/dispatch` behavior.
- Sync Telegram's command dropdown/menu from the registry via Bot API `setMyCommands` during listener startup.
- Add `/help` as a generated text fallback for detailed command usage.
- Add `/tmate status`, `/tmate start`, and `/tmate stop` with managed session state, read-write/read-only SSH/Web link reporting, and automatic no-client idle stop after 3600 seconds.
- Allow fixed shell `func_call` entries through safe argv execution without `shell=True`.

## Capabilities

### New Capabilities

- None.

### Modified Capabilities

- `stage1-core-runtime`: Add registry-backed runtime commands, Telegram command-menu sync, `/help`, safe shell `func_call`, and managed `/tmate` lifecycle requirements.

## Impact

- Affected runtime modules: `paulshaclaw/core/daemon.py`, new command registry/dispatcher modules, `paulshaclaw/bot/telegram.py`, and `paulshaclaw/bot/listener.py`.
- Affected runtime data: new tracked `paulshaclaw/core/commands.json` plus untracked runtime state under `~/.agents/run/` and `~/.agents/state/`.
- Affected tests: Stage 1 smoke tests and Telegram listener tests need offline coverage for registry validation, help generation, Telegram `setMyCommands`, tmate manager behavior, idle cleanup, and shell argv execution.
- External tools: uses installed `tmate` CLI when `/tmate` commands execute; automated tests must fake command execution and avoid real Telegram/tmate network calls.
