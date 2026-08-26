## ADDED Requirements

### Requirement: Telegram long-poll listener entrypoint

Stage 1 SHALL provide a Telegram listener entrypoint invocable as `python -m paulshaclaw.bot.listener`. The listener MUST use Telegram Bot API long polling, MUST load Stage 1 config through `--config` or `PSC_STAGE1_CONFIG`, MUST route text commands through `TelegramCommandRouter`, and MUST reply through Telegram `sendMessage`. The listener MUST NOT call coordinator APIs directly.

#### Scenario: Authorized text command is routed through router

- **WHEN** the listener receives a Telegram update whose sender user id is listed in `allowed_user_ids` and whose text is `/status`
- **THEN** the listener MUST call `TelegramCommandRouter.handle_message(user_id=<sender_id>, text="/status")` exactly once and MUST send the returned message through Telegram `sendMessage`

#### Scenario: Non-text update does not dispatch

- **WHEN** the listener receives a Telegram update without `message.text`
- **THEN** the listener MUST NOT call `PaulShiaBroDaemon.dispatch` and MUST either ignore the update or reply with `目前只支援文字命令`

### Requirement: Telegram bot secret and identity checks

The Telegram listener SHALL require `PSC_TELEGRAM_BOT_TOKEN` from the environment. The listener MUST support optional `PSC_TELEGRAM_EXPECTED_USERNAME` and `PSC_TELEGRAM_EXPECTED_BOT_ID` checks. On startup, the listener MUST call Telegram `getMe`; if an expected username or bot id is configured and does not match the `getMe` result, startup MUST fail closed with a non-zero exit code.

#### Scenario: Missing token fails startup

- **WHEN** `PSC_TELEGRAM_BOT_TOKEN` is absent and the operator starts `python -m paulshaclaw.bot.listener`
- **THEN** the process MUST exit non-zero and MUST print a clear error identifying the missing token

#### Scenario: Bot identity mismatch fails startup

- **WHEN** `PSC_TELEGRAM_EXPECTED_USERNAME=expected_bot` is set and Telegram `getMe` returns username `other_bot`
- **THEN** the listener MUST exit non-zero before polling updates

### Requirement: Telegram production dispatch guard

The integrated Telegram listener SHALL NOT report `/dispatch` success through `LocalCoordinator`. If no real coordinator backend is configured for the listener, `/status` MAY continue to work, but `/dispatch <task_id>` MUST return a clear failure message containing `coordinator backend 未設定` and MUST NOT return a fake local job id.

#### Scenario: Dispatch without backend fails closed

- **WHEN** the Telegram listener is started without a configured real coordinator backend and an authorized user sends `/dispatch sample-task`
- **THEN** the reply MUST indicate `coordinator backend 未設定` and MUST NOT contain a `local-` job id

#### Scenario: Unit tests can still inject fake coordinator

- **WHEN** a unit test constructs `PaulShiaBroDaemon` with an explicit fake coordinator and invokes `/dispatch sample-task`
- **THEN** the daemon MUST call the injected fake coordinator and MAY return the fake job id for test assertions

### Requirement: Local integrated startup includes Telegram service

The repository SHALL provide `scripts/start.sh` as a local integrated startup script that launches monitor and Telegram listener as background services, then runs cockpit TUI in the foreground. When the cockpit exits normally, receives Ctrl+C, or the script receives TERM, the script MUST terminate and wait for both background services. Telegram listener logs MUST be written to `~/.agents/log/telegram.log`.

#### Scenario: Ctrl+C terminates background services

- **WHEN** `scripts/start.sh` has started monitor and Telegram listener in the background and the foreground cockpit receives Ctrl+C
- **THEN** the script MUST terminate both background services before exiting

#### Scenario: Normal cockpit exit terminates Telegram listener

- **WHEN** the foreground cockpit process exits with status 0
- **THEN** `scripts/start.sh` MUST terminate the Telegram listener background process before returning

### Requirement: Telegram listener tests avoid real network

Stage 1 SHALL test Telegram listener behavior without calling the real Telegram API. Tests MUST use fake HTTP openers, fake update payloads, or injected client objects to verify `getMe`, `getUpdates`, `sendMessage`, authorization routing, non-text handling, and single-send behavior.

#### Scenario: Listener test suite runs offline

- **WHEN** an operator runs the Stage 1 Telegram listener tests without network access
- **THEN** the tests MUST complete without DNS or Telegram API calls
