# stage1-core-runtime Specification

## Purpose
TBD - created by archiving change stage1-baseline. Update Purpose after archive.
## Requirements
### Requirement: Daemon status command

The PaulShiaBro daemon SHALL expose a `/status` command that returns a JSON object describing the current runtime snapshot. The JSON payload MUST contain exactly the keys `ok`, `daemon`, `project`, `pane_count`, and `allowed_user_count`. `ok` MUST be boolean; `daemon` and `project` MUST be strings derived from the loaded config; `pane_count` MUST be the integer length of the configured pane assignments; `allowed_user_count` MUST be the integer length of the Telegram authorization whitelist.

#### Scenario: Status returns configured snapshot

- **WHEN** a caller invokes `/status` on a daemon loaded with a config that declares a `daemon_name`, `default_project`, three pane assignments, and two allowed user ids
- **THEN** the returned JSON MUST satisfy `{"ok": true, "daemon": <daemon_name>, "project": <default_project>, "pane_count": 3, "allowed_user_count": 2}`

### Requirement: Daemon dispatch command

The daemon SHALL expose a `/dispatch <task_id>` command that forwards to the coordinator seam and returns a JSON object containing exactly the keys `ok`, `job_id`, `phase`, and `scope`. The `phase` MUST equal the configured `coordinator.phase`. The `scope` MUST equal the supplied `task_id`. The payload passed to the coordinator MUST be the configured `coordinator.default_payload` with a `task_id` key added. A `/dispatch` without a `task_id` MUST raise an error before any coordinator call.

#### Scenario: Dispatch forwards task to coordinator

- **WHEN** a caller invokes `/dispatch job-42` on a daemon whose config declares `coordinator.phase = "build"` and `coordinator.default_payload = {"project": "paulshaclaw"}`
- **THEN** the coordinator MUST be called once with `phase="build"`, `scope="job-42"`, and `payload={"project": "paulshaclaw", "task_id": "job-42"}`; and the returned JSON MUST contain `ok=true`, `phase="build"`, and `scope="job-42"`

#### Scenario: Dispatch rejects missing task id

- **WHEN** a caller invokes `/dispatch ` (empty task id)
- **THEN** the daemon MUST raise a validation error and MUST NOT call the coordinator

### Requirement: Config loader precedence

The config loader SHALL resolve the config file path using a fixed precedence: the explicit `--config` CLI flag first, then the `PSC_STAGE1_CONFIG` environment variable, and finally a validation error if neither is provided. The loader MUST parse JSON, reject non-object payloads, and MUST validate that the top-level object contains `daemon_name`, `default_project`, `coordinator`, and `pane_assignments`. Missing required fields MUST produce an error that names the missing field path.

#### Scenario: Explicit flag overrides environment

- **WHEN** both `--config /path/a.json` is passed AND `PSC_STAGE1_CONFIG=/path/b.json` is set in the environment
- **THEN** the loader MUST read `/path/a.json` and MUST NOT read `/path/b.json`

#### Scenario: Environment fallback when flag absent

- **WHEN** `--config` is not passed AND `PSC_STAGE1_CONFIG=/path/c.json` is set
- **THEN** the loader MUST read `/path/c.json`

#### Scenario: Missing required field is reported

- **WHEN** the loaded JSON lacks the `pane_assignments` key
- **THEN** the loader MUST raise a validation error whose message contains `config.pane_assignments`

### Requirement: Coordinator seam

The daemon runtime SHALL define a `CoordinatorClient` Protocol that exposes exactly one method: `create_job(*, phase: str, scope: str, payload: dict) -> dict`. The runtime MUST ship a default `LocalCoordinator` implementation that returns a dict containing `job_id`, `phase`, `scope`, and the echoed `payload`. Consumers (Stage 3, etc.) MUST be able to inject an alternative `CoordinatorClient` via the daemon constructor without modifying daemon source code.

#### Scenario: Custom coordinator is honored

- **WHEN** a caller constructs the daemon with a custom `CoordinatorClient` that records every call
- **THEN** invoking `/dispatch` MUST route through the custom coordinator and MUST NOT fall back to `LocalCoordinator`

### Requirement: CLI entry point

The daemon SHALL be invocable as a CLI via `python -m paulshaclaw.core.daemon --config <path> --command <command>`. The CLI MUST print the JSON result to stdout on success with exit code 0. On a validation error, a missing file, or an unsupported command, the CLI MUST print the error message to stderr and exit with code 1; no Python traceback MUST leak to stderr.

#### Scenario: Success prints JSON to stdout

- **WHEN** the CLI is invoked with a valid `--config` and `--command /status`
- **THEN** stdout MUST contain a JSON line matching the `/status` shape and the process MUST exit 0

#### Scenario: Invalid command exits cleanly

- **WHEN** the CLI is invoked with `--command /unknown`
- **THEN** stderr MUST contain a short error message (no Python traceback) and the process MUST exit 1

### Requirement: Telegram authorization gate

The Telegram bot router SHALL reject inbound commands whose user id is not present in `config.allowed_user_ids`, returning a refusal message and MUST NOT invoke the daemon. For authorized user ids, the router MUST forward the normalized command to the daemon and surface the daemon response (success) or the daemon's validation error (failure) to the caller.

#### Scenario: Unauthorized user is rejected

- **WHEN** a Telegram update arrives from user id `9999` while `allowed_user_ids = (1001,)`
- **THEN** the router MUST return a refusal message identifying the user as unauthorized, and the daemon's `handle_command` MUST NOT be called

#### Scenario: Authorized user is routed

- **WHEN** a Telegram update arrives from user id `1001` with text `/status` while `allowed_user_ids = (1001,)`
- **THEN** the router MUST call the daemon's `handle_command("/status")` exactly once and MUST surface the returned snapshot to the caller

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

### Requirement: TUI pane and task listing

The TUI SHALL render a view listing every configured pane assignment and its current task id and status. The renderer MUST be deterministic for a given config (stable ordering, no hidden state). The renderer MUST NOT require a real tmux session — it operates over the `PaneAssignment` tuples from the loaded config.

#### Scenario: Renderer enumerates configured panes

- **WHEN** the TUI view is rendered for a config with pane assignments `[{id:"0", title:"stage1", task:"T-1", status:"active"}, {id:"1", title:"stage2", task:"T-2", status:"idle"}]`
- **THEN** the rendered output MUST contain both pane ids, both titles, both task ids, and both status values, with the two panes appearing in the configured order

### Requirement: Sample config schema

The repository SHALL provide `config/paulshaclaw-stage1.sample.json` as a loadable sample that validates against the config loader contract. The sample MUST declare all required top-level fields (`daemon_name`, `default_project`, `coordinator`, `pane_assignments`) and MUST parse successfully via `load_config` without further modification.

#### Scenario: Sample config loads

- **WHEN** a caller invokes `load_config(config_path="config/paulshaclaw-stage1.sample.json")`
- **THEN** the call MUST return an `AppConfig` instance with non-empty `daemon_name`, `default_project`, and at least one `pane_assignments` entry

### Requirement: Smoke test harness

Stage 1 SHALL ship a smoke test suite at `tests/test_stage1_smoke.py` that collectively exercises: config loader happy path, config loader env fallback, config loader missing-field rejection, daemon `/status`, daemon `/dispatch` (with a fake coordinator to assert call args), TUI pane listing, Telegram router authorized route, Telegram router unauthorized rejection, Telegram router invalid-command surface, CLI success path, CLI clean-error path, and CLI env-config path. All cases MUST be executable via `python -m unittest discover -s tests` and MUST exit with zero failures.

#### Scenario: Smoke suite passes on merged main

- **WHEN** an operator runs `python -m unittest discover -s tests -v` from the repo root on main
- **THEN** the suite MUST report all Stage 1 smoke cases as `ok` and exit zero

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
