## Context

Stage 1 already owns the Telegram listener, Telegram authorization router, and daemon command runtime. The current daemon dispatches `/status` and `/dispatch` with direct string branches, while Telegram has no command-menu sync and no generated `/help`. Issue #4 adds `/tmate` support through Telegram, and the operator expects commands to appear in Telegram's command dropdown/menu, not only in a text help response.

The change must preserve the Stage 1 boundary: Telegram remains the transport and authorization layer; daemon core owns command parsing, command execution, and coordinator/tmux/tmate interactions.

## Goals / Non-Goals

**Goals:**

- Make `paulshaclaw/core/commands.json` the single source of truth for Stage 1 runtime command metadata.
- Dispatch `/help`, `/status`, `/dispatch`, and `/tmate` through a registry-backed dispatcher.
- Sync Telegram Bot API commands from the registry during listener startup.
- Implement `/tmate status`, `/tmate start`, and `/tmate stop` with no-client idle cleanup after 3600 seconds.
- Allow fixed shell `func_call` entries through safe argv execution.
- Keep automated tests offline by faking Telegram and tmate execution.

**Non-Goals:**

- Do not include `/opsx:*` Claude/GitHub commands.
- Do not add Telegram inline keyboard buttons.
- Do not create a separate tmate systemd timer.
- Do not provision or configure a Telegram bot through BotFather.
- Do not change the coordinator backend contract.

## Decisions

### Decision: JSON registry as command source of truth

Use `paulshaclaw/core/commands.json` with `name`, `usage`, `summary`, `telegram_menu`, and `func_call` fields.

Rationale: a tracked JSON file makes the command surface inspectable, lets `/help` and `setMyCommands` share metadata, and supports shell command declarations without embedding them in Python branches.

Alternative considered: keep help metadata in Python constants. That is simpler but still couples help and dispatch through hand-written code, leaving more drift risk.

### Decision: Registry-backed dispatcher with explicit Python handler map

`PaulShiaBroDaemon.handle_command()` should parse the first token, resolve a registry entry, and pass remaining tokens to a dispatcher. Python handlers are looked up through a fixed map such as `help`, `status`, `dispatch`, and `tmate`.

Rationale: existing behavior remains owned by the daemon while command discovery and routing move to a small, testable abstraction.

Alternative considered: execute all commands as shell argv from JSON. That would make the registry uniform, but it would force current in-process `/status` and `/dispatch` behavior through subprocesses and weaken test seams.

### Decision: Shell func calls use argv only

Shell `func_call` entries must provide an argv array and must run with `shell=False`. Placeholder support is restricted to explicit tokens such as `{arg0}` and `{args}`.

Rationale: the registry can support operational commands while avoiding shell interpolation and quoting bugs.

Alternative considered: allow shell command strings. That is more flexible but turns the registry into a shell script runner and increases injection risk.

### Decision: Telegram menu sync is startup-gated

After `getMe` identity validation, the listener loads the registry, derives commands where `telegram_menu.enabled` is true, and calls `setMyCommands` before polling. Failure to sync fails startup.

Rationale: the operator expects the Telegram command menu to match runtime commands. Failing closed catches invalid command metadata early.

Alternative considered: log a warning and keep polling if menu sync fails. That improves availability but allows a stale Telegram menu, which is the drift this change is meant to prevent.

### Decision: Managed tmate session with state under `~/.agents`

The tmate manager owns one deterministic session:

```text
socket_path = ~/.agents/run/paulshaclaw-tmate.sock
state_path  = ~/.agents/state/tmate.json
session     = paulshaclaw
```

It uses fixed tmate argv calls for `new-session`, `has-session`, `display-message`, and `kill-session`.

Rationale: deterministic state makes `/tmate status`, idempotent `/tmate start`, and cleanup testable without leaking runtime files into the repository.

Alternative considered: create a new random tmate session on every `/tmate start`. That is simpler to start, but it makes status/cleanup ambiguous and increases stale access risk.

### Decision: Idle cleanup runs in listener and command path

Idle means `session_attached == 0` continuously for `timeout_seconds`, defaulting to 3600 seconds from the `/tmate` registry entry. Cleanup runs once per Telegram polling loop and at the start of each `/tmate` command.

Rationale: this avoids adding a separate timer service while still cleaning up during normal Telegram operation. Running cleanup on command entry keeps status accurate after listener downtime.

Alternative considered: systemd timer cleanup. That is more robust when the listener is down, but it adds deployment surface beyond this Stage 1 runtime change.

## Risks / Trade-offs

- Telegram clients may cache command menus briefly after `setMyCommands` → startup validates the API call, and manual smoke validation verifies the client menu catches up.
- Failing closed on command-menu sync can make the bot unavailable if Telegram API has a transient problem → the listener already depends on Telegram API at startup for `getMe`, so this keeps startup semantics consistent.
- tmate link formats may vary across versions → the manager reads official tmate format fields and treats missing links as a pending state rather than crashing.
- Listener downtime means no background idle cleanup → the next `/tmate` command still checks and stops expired no-client sessions before returning.
- Returning read-write tmate links is sensitive → links are only returned after Telegram authorization and must be redacted from normal logs.

## Migration Plan

1. Add registry and dispatcher with `/status` and `/dispatch` mapped to existing behavior.
2. Add `/help` generated from the registry.
3. Add Telegram `setMyCommands` client support and startup sync.
4. Add tmate manager and `/tmate` handler.
5. Add listener cleanup hook for tmate idle timeout.
6. Update tests and sample command registry.

Rollback is straightforward: revert the change to restore direct daemon command branching. Runtime state under `~/.agents/run/paulshaclaw-tmate.sock` and `~/.agents/state/tmate.json` can be removed manually after killing the managed tmate session.

## Open Questions

None. The selected behavior is fixed by the approved design: Stage 1 runtime only, Telegram menu sync, `/tmate status|start|stop`, read-write/read-only links, and 3600-second no-client idle timeout.
