# Telegram Service Lifecycle Design

## Context

GitHub issue #13 tracks that the Telegram service is not wired into the startup lifecycle. Stage 1 currently has a `TelegramCommandRouter`, but no process connects to Telegram Bot API, and `scripts/start.sh` does not start a Telegram service. Stage 7 deploy templates also expose only the core service skeleton, while recovery docs already refer to a bot service.

This design makes Telegram a real service while keeping dispatch ownership out of the Telegram transport layer. GitHub issue #14 tracks the separate work to define and wire the real coordinator adapter for production dispatch.

## Goals

- Add a real Telegram long-poll listener service using the standard library.
- Keep command handling in `TelegramCommandRouter` and `PaulShiaBroDaemon`.
- Wire the listener into `scripts/start.sh` so it exits with the TUI, including Ctrl+C.
- Add deploy/systemd visibility for the Telegram service.
- Keep Telegram bot token and bot identity checks in secret environment files, never in repo-tracked config.
- Fail closed for production `/dispatch` when no real coordinator backend is configured.

## Non-Goals

- Do not implement webhook mode.
- Do not create or provision a Telegram bot through BotFather.
- Do not implement Telegram buttons, 2FA, photo handling, or proactive background notifications.
- Do not implement the real coordinator adapter in #13. That is tracked by #14.
- Do not make the TUI a systemd service.

## Architecture

The Telegram listener is a transport adapter only. It talks to Telegram Bot API, extracts text messages, calls the existing router, and sends the router response back to Telegram.

The command path is:

```text
Telegram Bot API
  -> paulshaclaw.bot.listener
  -> TelegramCommandRouter.handle_message(user_id, text)
  -> PaulShiaBroDaemon.handle_command(command_text)
  -> PaulShiaBroDaemon.dispatch(task_id)
  -> CoordinatorClient.create_job(phase, scope, payload)
```

The listener must not call coordinator APIs directly. The existing `bot` boundary remains responsible for authorization and response formatting. The existing `core` boundary remains responsible for `/status`, `/dispatch`, config loading, and coordinator dispatch seam.

## Components

- `paulshaclaw.bot.telegram`: keep `TelegramCommandRouter` as the command adapter. It continues to reject non-whitelisted human Telegram users through `allowed_user_ids`.
- `paulshaclaw.bot.listener`: add the long-poll process, Telegram API client, CLI entrypoint, token checks, update loop, and send-message behavior.
- `paulshaclaw.core.daemon`: keep the command runtime. Add only the minimum production guard needed to prevent fake local dispatch from reporting success in the integrated Telegram startup path.
- `scripts/start.sh`: start monitor and Telegram listener as background services, then start cockpit in the foreground. On cockpit exit, Ctrl+C, or TERM, terminate and wait for background services.
- `paulshaclaw.deploy`: add Telegram systemd and secret/runtime template assets so deploy plans include the bot service.
- `docs/ops/recovery.md`: align recovery instructions with the actual listener service and logs.

## Config And Secrets

Telegram API credentials are supplied through secret environment variables:

```bash
PSC_TELEGRAM_BOT_TOKEN=<bot-token-from-secret-env>
PSC_TELEGRAM_EXPECTED_USERNAME=your_bot_username
PSC_TELEGRAM_EXPECTED_BOT_ID=123456789
```

`PSC_TELEGRAM_BOT_TOKEN` is required for the listener. `PSC_TELEGRAM_EXPECTED_USERNAME` and `PSC_TELEGRAM_EXPECTED_BOT_ID` are optional startup sanity checks. When either optional value is set, the listener calls `getMe`; a mismatch is a fatal startup error.

The Stage 1 JSON config keeps `allowed_user_ids`. These are human Telegram user IDs allowed to send commands. They are not bot IDs.

The listener must support config path resolution through the existing `PSC_STAGE1_CONFIG` environment variable and an explicit `--config` CLI flag. The explicit flag wins over the environment variable.

## Dispatch Boundary

`/dispatch` still flows through `PaulShiaBroDaemon.dispatch()` and `CoordinatorClient.create_job(phase, scope, payload)`. Telegram does not own dispatch.

For production startup, `/dispatch` must not silently use `LocalCoordinator` and return a fake success. Until #14 defines and wires a real coordinator adapter, the integrated Telegram service may serve `/status`, but `/dispatch` must fail closed with a clear user-facing message such as `coordinator backend 未設定`.

Unit tests may continue to inject fake coordinators explicitly. This preserves the current Stage 1 test seam without allowing production startup to fake dispatch.

## Lifecycle

Local integrated startup:

```text
scripts/start.sh
  -> monitor background service
  -> telegram listener background service
  -> cockpit TUI foreground app
  -> cockpit exit, Ctrl+C, or TERM
  -> terminate and wait for monitor and telegram listener
```

The script should track background PIDs explicitly. Cleanup should send TERM to each live background PID and wait for exit, rather than depending only on broad child-process cleanup. Telegram listener logs should go to `~/.agents/log/telegram.log`.

Deploy mode uses separate systemd units:

```text
<instance>.service
<instance>-telegram.service
```

The Telegram unit loads the same runtime config path and a secret environment file containing the bot token. The core unit and Telegram unit are separate so operators can restart the bot without restarting the whole core process.

## Error Handling

Startup failures:

- Missing `PSC_TELEGRAM_BOT_TOKEN`: exit non-zero with a clear error.
- `getMe` network failure: retry a small bounded number of times, then exit non-zero.
- Expected bot username or bot ID mismatch: exit non-zero immediately.
- Stage 1 config load failure: exit non-zero immediately.

Runtime behavior:

- Unauthorized user: return the existing `未授權使用者` response.
- Non-text message: return `目前只支援文字命令` or ignore without dispatching.
- Telegram `getUpdates` transient error: log and retry with bounded backoff.
- `sendMessage` failure: log the error and do not re-run the command.
- Update offset advances after an update is accepted for processing so restarts do not replay the same command indefinitely.

## Testing Strategy

Automated tests must not call the real Telegram API.

- Unit tests cover Telegram API client request and response parsing with fake HTTP openers.
- Listener tests feed fake updates and verify text routing, unauthorized handling, non-text handling, and single `sendMessage` behavior.
- `tests/test_start_sh.py` verifies `scripts/start.sh` starts monitor, Telegram listener, and cockpit, then terminates both background services when cockpit exits or receives Ctrl+C.
- `tests/test_stage7_deploy_three_plane.py` verifies deploy template catalog includes Telegram systemd and secret/runtime assets.

Manual smoke validation:

```bash
PSC_STAGE1_CONFIG=/path/to/config.json \
PSC_TELEGRAM_BOT_TOKEN=<bot-token-from-secret-env> \
python -m paulshaclaw.bot.listener
```

Send `/status` from an allowed human Telegram user and confirm a status reply. Send `/status` from a non-allowed user and confirm rejection. Send `/dispatch sample-task` before #14 is complete and confirm it fails closed instead of reporting a fake local job.

## Acceptance Criteria

- `python -m paulshaclaw.bot.listener` starts a long-poll Telegram listener when token and config are valid.
- Missing token, bot identity mismatch, and config load errors fail closed at startup.
- Telegram `/status` works for allowed users and rejects non-allowed users.
- Telegram `/dispatch` does not report success through `LocalCoordinator` in production startup.
- `scripts/start.sh` starts the Telegram listener and terminates it when the TUI exits, including Ctrl+C.
- Deploy plan output includes a Telegram service unit and secret/runtime template assets.
- Unit and lifecycle tests pass without network access.
