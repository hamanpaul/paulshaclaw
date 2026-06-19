## ADDED Requirements

### Requirement: Runtime command registry

The Stage 1 daemon SHALL load runtime command metadata from `paulshaclaw/core/commands.json`. The registry MUST declare `/help`, `/status`, `/dispatch`, and `/tmate` with non-empty `usage`, `summary`, `telegram_menu`, and `func_call` metadata. The daemon MUST dispatch commands through the registry while preserving existing `/status` and `/dispatch` behavior. Invalid registry JSON, duplicate command names, unsupported `func_call.type`, unknown Python handler targets, invalid shell argv definitions, or invalid Telegram menu metadata MUST fail before command polling starts.

#### Scenario: Registry dispatch preserves status

- **WHEN** a caller invokes `/status` on a daemon loaded with the default command registry
- **THEN** the daemon MUST resolve `/status` from `commands.json` and return the same status snapshot shape as the existing Stage 1 `/status` command

#### Scenario: Invalid registry fails startup validation

- **WHEN** the command registry contains duplicate command names or a Telegram menu command containing `/`
- **THEN** registry loading MUST raise a validation error before Telegram long polling starts

### Requirement: Generated help command

The Stage 1 daemon SHALL expose `/help` from the command registry. `/help` MUST list the usage and summary for each registered Stage 1 runtime command. `/help <command>` MUST accept command names with or without a leading slash and return the selected command's usage and summary. Help output MUST be generated from `commands.json`; no separate Stage 1 runtime help document may be required to keep `/help` accurate.

#### Scenario: Help lists registered commands

- **WHEN** an authorized user sends `/help`
- **THEN** the reply MUST include `/help`, `/status`, `/dispatch`, and `/tmate` with their registry-defined usage and summary

#### Scenario: Help accepts slashless command names

- **WHEN** an authorized user sends `/help tmate`
- **THEN** the reply MUST include the `/tmate [status|start|stop]` usage from the registry

### Requirement: Safe shell func call

The command dispatcher SHALL support registry entries whose `func_call.type` is `shell`. Shell entries MUST execute only a non-empty argv array with `shell=False`, MUST apply only explicit placeholder substitutions such as `{arg0}` and `{args}`, MUST reject unknown placeholders during registry validation, and MUST enforce a command timeout from the command entry or registry defaults.

#### Scenario: Shell command uses argv without shell interpolation

- **WHEN** a registry entry declares `{"type": "shell", "argv": ["printf", "{arg0}"], "timeout_seconds": 10}` and the caller invokes it with argument `hello`
- **THEN** the dispatcher MUST call subprocess execution with argv `["printf", "hello"]`, `shell=False`, and timeout `10`

#### Scenario: Unknown shell placeholder is rejected

- **WHEN** a registry entry declares a shell argv containing `{unsafe}`
- **THEN** registry loading MUST fail before the command can run

### Requirement: Telegram command menu sync

The Telegram listener SHALL derive Bot API command-menu entries from registry commands whose `telegram_menu.enabled` value is true. During startup, after successful `getMe` identity validation and before long polling, the listener MUST call Telegram Bot API `setMyCommands` with the derived commands. The derived Telegram command names MUST omit the leading slash and satisfy Telegram Bot API `BotCommand.command` constraints. If `setMyCommands` fails, listener startup MUST fail closed before polling updates.

#### Scenario: Listener syncs commands before polling

- **WHEN** the Telegram listener starts with a valid registry and valid bot identity
- **THEN** it MUST call `setMyCommands` with `help`, `status`, `dispatch`, and `tmate` before calling `getUpdates`

#### Scenario: Menu sync failure stops listener startup

- **WHEN** Telegram Bot API rejects `setMyCommands`
- **THEN** the listener MUST exit non-zero before polling updates

### Requirement: Tmate command lifecycle

The Stage 1 daemon SHALL expose `/tmate`, `/tmate status`, `/tmate start`, and `/tmate stop` through the registry dispatcher. Bare `/tmate` MUST behave as `/tmate status`. `/tmate start` MUST create or reuse one managed tmate session, return read-write and read-only SSH/Web links when links are ready, and store runtime state under `~/.agents/` rather than the repository. Managed tmate subprocesses MUST clear inherited `TMUX` from the child environment so `/tmate start` works even when PaulShiaBro itself is running inside tmux. `/tmate stop` MUST kill the managed session and clear managed state. `/tmate status` MUST report whether the managed session is stopped, pending, or running.

#### Scenario: Bare tmate returns status

- **WHEN** an authorized user sends `/tmate`
- **THEN** the daemon MUST process it as `/tmate status`

#### Scenario: Start returns managed session links

- **WHEN** an authorized user sends `/tmate start` and tmate reports ready SSH/Web link formats
- **THEN** the reply MUST include read-write SSH, read-write Web, read-only SSH, and read-only Web links for the managed session

#### Scenario: Start ignores parent tmux nesting state

- **WHEN** PaulShiaBro is running inside tmux and an authorized user sends `/tmate start`
- **THEN** the managed tmate executor MUST clear inherited `TMUX` before spawning `tmate`, avoiding nested-session startup failure

#### Scenario: Stop clears managed session

- **WHEN** an authorized user sends `/tmate stop`
- **THEN** the daemon MUST kill the managed tmate session and remove or mark the managed state as stopped

### Requirement: Tmate idle timeout

The managed tmate session SHALL automatically stop after the configured timeout when `session_attached == 0` continuously for that timeout. The default timeout MUST be 3600 seconds from the `/tmate` registry entry. When `session_attached > 0`, idle tracking MUST reset. Cleanup MUST run during `/tmate` command handling and once per Telegram listener polling loop.

#### Scenario: No-client session expires

- **WHEN** the managed tmate session exists, `session_attached == 0`, and `last_no_client_at` is at least 3600 seconds in the past
- **THEN** cleanup MUST kill the managed tmate session and mark it stopped

#### Scenario: Attached client resets idle timer

- **WHEN** the managed tmate session exists and `session_attached > 0`
- **THEN** cleanup MUST clear `last_no_client_at` and MUST NOT stop the session

### Requirement: Tmate link redaction

The Telegram listener and daemon logging paths MUST NOT write bot tokens or full tmate connection links to normal logs. Telegram replies MAY include tmate links after the existing Telegram authorization gate accepts the user. Log entries for outbound `/tmate start` responses MUST redact URL/token-like values.

#### Scenario: Outbound tmate response is redacted in logs

- **WHEN** `/tmate start` produces SSH/Web links and the listener sends them to an authorized Telegram chat
- **THEN** the Telegram reply MAY contain the links, but the listener log entry MUST redact the link values

### Requirement: Offline registry and tmate tests

Stage 1 tests SHALL cover command registry loading, generated help, Telegram command-menu sync, safe shell argv dispatch, tmate command lifecycle, no-client idle cleanup, and tmate link redaction without calling the real Telegram API or creating real tmate network sessions.

#### Scenario: Test suite avoids external services

- **WHEN** an operator runs the Stage 1 unit tests without network access
- **THEN** tests for Telegram command-menu sync and tmate lifecycle MUST use fake clients or fake command executors and MUST complete without DNS, Telegram API, or tmate.io calls
