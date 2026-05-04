# Tmate Command Registry Design

## Context

GitHub issue #4 tracks adding tmate support through Telegram commands. Stage 1 currently supports `/status` and `/dispatch` in `PaulShiaBroDaemon.handle_command()` with hand-written branches. `TelegramCommandRouter` only authorizes users and formats daemon results. This means the command surface, help text, and Telegram command menu can drift unless they are generated from one command registry.

Telegram command discovery is also not just a text `/help` response. The desired operator experience is the Telegram client command list shown from the command/menu button near the message composer. That list is managed with Telegram Bot API `setMyCommands`, whose `BotCommand` object uses a slash-less command name and a short description.

Relevant Telegram constraints from the official Bot API:

- `setMyCommands` accepts at most 100 commands.
- `BotCommand.command` is 1 to 32 characters and may contain only lowercase English letters, digits, and underscores.
- `BotCommand.description` is 1 to 256 characters.
- Telegram graphical clients show bot commands when a user starts a message with `/`.

Sources:

- <https://core.telegram.org/bots/api#setmycommands>
- <https://core.telegram.org/bots/api#botcommand>
- <https://core.telegram.org/api/bots/commands>

## Confirmed Decisions

- Scope is Stage 1 Telegram/runtime commands only: `/help`, `/status`, `/dispatch`, and `/tmate`.
- Do not include repo-local `/opsx:*` Claude/GitHub commands in this registry.
- Use a real JSON file as the command registry single source of truth.
- `func_call` supports Python handlers and fixed shell argv calls.
- `/tmate` supports subcommands: `status`, `start`, and `stop`; bare `/tmate` means `/tmate status`.
- `/tmate start` returns read-write and read-only SSH/Web links to authorized Telegram users.
- tmate idle timeout defaults to 3600 seconds.
- Idle means the managed tmate session has had zero attached clients continuously for the timeout window.
- Telegram command menu sync is a first-class requirement; `/help` remains a detailed fallback generated from the same registry.

## Goals

- Replace hand-maintained runtime command branching with a small registry-backed dispatcher.
- Generate Telegram command menu entries from the same JSON registry used by `/help`.
- Support safe fixed shell commands in `func_call` without `shell=True`.
- Add managed tmate lifecycle commands with automatic idle stop.
- Keep Telegram authorization in `TelegramCommandRouter` and command execution in `PaulShiaBroDaemon`.
- Avoid writing tmate connection links or bot tokens to ordinary logs.

## Non-Goals

- Do not manage `/opsx:*` slash commands or `.claude` / `.github` prompt files.
- Do not add Telegram inline keyboard buttons.
- Do not provision a Telegram bot or configure BotFather.
- Do not implement a separate always-on tmate systemd timer in this change.
- Do not expose tmate links to unauthorized users or non-Telegram transports without existing daemon authorization.

## Architecture

The Stage 1 command path becomes:

```text
Telegram Bot API
  -> paulshaclaw.bot.listener
  -> TelegramCommandRouter.handle_message(user_id, text)
  -> PaulShiaBroDaemon.handle_command(command_text)
  -> CommandRegistry lookup
  -> CommandDispatcher execute
  -> Python handler or fixed shell argv
```

`TelegramCommandRouter` continues to reject users whose Telegram user id is not in `allowed_user_ids`. It does not parse tmate or shell command details. The daemon owns command parsing and dispatch, using the registry to map command names to handlers.

The Telegram listener startup path becomes:

```text
load bot settings
  -> getMe identity check
  -> load commands.json
  -> derive Telegram BotCommand list
  -> setMyCommands
  -> start long polling
```

If command menu sync fails, startup fails closed. This keeps the visible Telegram command list aligned with the runtime surface.

## Command Registry

The registry lives at `paulshaclaw/core/commands.json`.

Example shape:

```json
{
  "version": 1,
  "defaults": {
    "timeout_seconds": 30
  },
  "commands": [
    {
      "name": "/help",
      "usage": "/help [command]",
      "summary": "列出可用命令，或顯示單一命令用法",
      "telegram_menu": {
        "enabled": true,
        "command": "help",
        "description": "列出可用命令"
      },
      "func_call": {
        "type": "python",
        "target": "help"
      }
    },
    {
      "name": "/status",
      "usage": "/status",
      "summary": "顯示 PaulShiaBro runtime 狀態",
      "telegram_menu": {
        "enabled": true,
        "command": "status",
        "description": "顯示 runtime 狀態"
      },
      "func_call": {
        "type": "python",
        "target": "status"
      }
    },
    {
      "name": "/dispatch",
      "usage": "/dispatch <task_id>|<pane_id> <message>",
      "summary": "派工到 coordinator，或送訊息到 tmux pane",
      "telegram_menu": {
        "enabled": true,
        "command": "dispatch",
        "description": "派工或送訊息到 pane"
      },
      "func_call": {
        "type": "python",
        "target": "dispatch"
      }
    },
    {
      "name": "/tmate",
      "usage": "/tmate [status|start|stop]",
      "summary": "管理 tmate remote access session",
      "telegram_menu": {
        "enabled": true,
        "command": "tmate",
        "description": "管理 tmate remote access"
      },
      "func_call": {
        "type": "python",
        "target": "tmate",
        "timeout_seconds": 3600
      }
    }
  ]
}
```

Registry validation rules:

- `version` must be `1`.
- command `name` must start with `/`.
- command names must be unique.
- `usage` and `summary` must be non-empty.
- `telegram_menu.command` must omit `/` and satisfy Telegram `BotCommand.command` constraints.
- `telegram_menu.description` must satisfy Telegram `BotCommand.description` constraints.
- `func_call.type` must be `python` or `shell`.
- Python targets must be in an explicit handler map.
- Shell calls must use an argv array and must never use `shell=True`.

## Shell Func Call Boundary

Shell calls are supported for fixed operational commands, but the registry does not become an arbitrary shell script runner.

Allowed shell shape:

```json
{
  "name": "/example",
  "usage": "/example <arg>",
  "summary": "執行固定命令",
  "telegram_menu": {
    "enabled": false
  },
  "func_call": {
    "type": "shell",
    "argv": ["some-command", "--fixed-flag", "{arg0}"],
    "timeout_seconds": 10
  }
}
```

Safety rules:

- `argv` must be a non-empty array of strings.
- Arguments are passed directly to `subprocess.run()` without `shell=True`.
- Placeholder substitution is restricted to a small allowlist such as `{args}` and `{arg0}`.
- Unknown placeholders fail validation at startup.
- Missing required placeholders fail before running a command.
- Shell command stdout may be returned to the caller; stderr is summarized without leaking secrets.
- Default timeout comes from registry defaults unless overridden by the command.

## Telegram Command Menu Sync

`TelegramApiClient` adds:

- `set_my_commands(commands: list[dict[str, str]]) -> None`
- `get_my_commands() -> list[dict[str, object]]` for tests and diagnostics

The listener derives Bot API commands from registry entries with `telegram_menu.enabled == true`:

```json
[
  {"command": "help", "description": "列出可用命令"},
  {"command": "status", "description": "顯示 runtime 狀態"},
  {"command": "dispatch", "description": "派工或送訊息到 pane"},
  {"command": "tmate", "description": "管理 tmate remote access"}
]
```

The Telegram menu only supports top-level commands, so `/tmate start` and `/tmate stop` are not separate menu entries. The menu shows `/tmate`; detailed usage comes from `/help tmate` or `/help /tmate`.

Startup sequence:

1. Load token and optional expected bot identity.
2. Call `getMe` and validate identity.
3. Load and validate `commands.json`.
4. Call `setMyCommands` with the derived menu commands.
5. Start long polling only after menu sync succeeds.

## Help Command

`/help` is generated from the same registry.

- `/help` lists enabled command usage and summary.
- `/help tmate` and `/help /tmate` show detailed usage for `/tmate`.
- Unknown command names return a clear validation error and list available commands.
- `/help` output may include syntax and notes that are too detailed for Telegram menu descriptions.

No separate help document is maintained for Stage 1 runtime commands.

## Tmate Lifecycle

The managed tmate session uses deterministic defaults owned by the daemon. Runtime state stays under `~/.agents/` and out of the repo:

```text
socket_path = ~/.agents/run/paulshaclaw-tmate.sock
state_path  = ~/.agents/state/tmate.json
session     = paulshaclaw
```

Commands:

- `/tmate` means `/tmate status`.
- `/tmate status` reports whether the managed session exists, whether links are ready, current attached client count, and idle timeout status.
- `/tmate start` starts the managed session if absent, waits a bounded period for tmate links, and returns read-write plus read-only SSH/Web links.
- `/tmate start` is idempotent: if a managed session already exists, return the existing links and status.
- `/tmate stop` kills the managed session and clears state.

Expected tmate CLI interactions use fixed argv commands:

```text
tmate -S <socket> new-session -d -s <session>
tmate -S <socket> has-session -t <session>
tmate -S <socket> display-message -p "#{session_attached}"
tmate -S <socket> display-message -p "#{tmate_ssh}"
tmate -S <socket> display-message -p "#{tmate_ssh_ro}"
tmate -S <socket> display-message -p "#{tmate_web}"
tmate -S <socket> display-message -p "#{tmate_web_ro}"
tmate -S <socket> kill-session -t <session>
```

## Idle Timeout

The timeout defaults to 3600 seconds and is configured on the `/tmate` command entry as `func_call.timeout_seconds`.

Idle definition:

```text
idle = managed tmate session exists
       AND session_attached == 0
       continuously for timeout_seconds
```

State file fields:

```json
{
  "socket_path": "/home/user/.agents/run/paulshaclaw-tmate.sock",
  "session_name": "paulshaclaw",
  "started_at": "2026-05-04T00:00:00+08:00",
  "last_no_client_at": "2026-05-04T00:30:00+08:00",
  "timeout_seconds": 3600
}
```

Cleanup rules:

- Every `/tmate status`, `/tmate start`, and `/tmate stop` checks current tmate state.
- The Telegram listener also runs cleanup once per polling loop, including loops with no updates.
- When `session_attached > 0`, clear `last_no_client_at`.
- When `session_attached == 0` and `last_no_client_at` is missing, set it to now.
- When `session_attached == 0` and `now - last_no_client_at >= timeout_seconds`, kill the managed tmate session and mark it stopped.
- If the Telegram listener is not running, idle cleanup does not run in the background; the next command invocation still performs cleanup before returning status.

## Security And Logging

- Telegram authorization remains mandatory before any command execution.
- tmate links are treated as sensitive operational access material.
- Bot token and tmate links must not be printed in normal logs.
- Telegram inbound/outbound logging should avoid full message text for `/tmate start` responses, or redact URL/token-like values before writing logs.
- `setMyCommands` payload contains only command names and descriptions, not tmate links or secrets.
- Shell command errors are sanitized before returning to Telegram.

## Error Handling

Registry and startup errors:

- Missing or invalid `commands.json`: fail startup with a clear error.
- Duplicate command name: fail startup.
- Invalid Telegram menu command or description: fail startup before polling.
- Telegram `setMyCommands` failure: fail closed before polling.

Runtime errors:

- Unknown command: return `不支援的指令` plus `/help` hint.
- Missing tmate binary: return `tmate not found`.
- tmate server absent on `/tmate status`: return a stopped status.
- tmate link not ready after bounded wait: return pending status and suggest retrying `/tmate status`.
- tmate command failure: return a concise error without traceback.
- Shell backend timeout: return a timeout error and do not retry automatically.

## Testing Strategy

Automated tests must not call Telegram or tmate network services.

Unit coverage:

- Load and validate `commands.json`.
- Reject duplicate command names and invalid Telegram menu entries.
- Generate Telegram `setMyCommands` payload from registry.
- `/help` list and single-command output are generated from registry.
- Dispatcher routes Python targets by registry entry.
- Dispatcher executes shell argv without `shell=True`, with placeholder validation and timeout handling.
- Existing `/status` and `/dispatch` behavior remains compatible.
- `/tmate` subcommand parsing covers bare `/tmate`, `status`, `start`, `stop`, and invalid subcommands.
- tmate manager uses fake executor output for session existence, link readiness, client count, stop, and timeout cleanup.
- Telegram listener startup calls `setMyCommands` after `getMe` and before long polling.
- Telegram listener cleanup runs once per polling loop.
- Logs redact tmate links in outbound logging paths.

Manual smoke validation:

```bash
PSC_STAGE1_CONFIG=/path/to/config.json \
PSC_TELEGRAM_BOT_TOKEN=<bot-token-from-secret-env> \
python -m paulshaclaw.bot.listener
```

Then from an allowed Telegram user:

```text
/help
/tmate status
/tmate start
/tmate stop
```

Confirm that Telegram shows the top-level command menu with `help`, `status`, `dispatch`, and `tmate`.

## Acceptance Criteria

- Stage 1 runtime commands are declared in `paulshaclaw/core/commands.json`.
- `/help` is generated from `commands.json` and has no separate hand-maintained help text.
- Telegram listener startup syncs the command menu with `setMyCommands` using entries from `commands.json`.
- Telegram command menu includes `help`, `status`, `dispatch`, and `tmate`.
- `/status` and `/dispatch` retain current behavior through the registry dispatcher.
- `/tmate status`, `/tmate start`, and `/tmate stop` work through the registry dispatcher.
- `/tmate start` returns read-write and read-only SSH/Web links to authorized users.
- Managed tmate sessions automatically stop after 3600 seconds with zero attached clients.
- Shell `func_call` entries are supported only through safe argv execution.
- Tests pass without real Telegram API calls or real tmate network sessions.
