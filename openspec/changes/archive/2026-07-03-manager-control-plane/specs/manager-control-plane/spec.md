## ADDED Requirements

### Requirement: Control-plane file contract root and layout

The system SHALL expose a control-plane rooted at `~/.agents/control/` as the sole interface between operator frontends and the manager, containing `requests/` (frontend-written intents), `done/` (daemon-written results), and `status.json` (daemon-written rollup), alongside the existing `~/.agents/specs/` work queue. Every control-plane file MUST carry a `schema_version` integer so the contract can evolve across the #125 repo split.

#### Scenario: Control-plane directories exist on first use

- **WHEN** the manager daemon or a frontend client first touches the control plane
- **THEN** `requests/` and `done/` directories exist under `~/.agents/control/` and every file the system writes there includes a `schema_version` field

### Requirement: Request submission is atomic and uniquely identified

A frontend controller SHALL write a request to `requests/<req_id>.json` using a temporary file plus `os.rename`, where `req_id` combines a UTC timestamp and a uuid4. The daemon MUST NOT observe a partially written request.

#### Scenario: Atomic request write

- **WHEN** a frontend submits a `tick` request
- **THEN** the file appears at `requests/<req_id>.json` only as a complete document (temp + rename), and `req_id` is unique per submission

### Requirement: Daemon writes an idempotent done record per request

For each drained request the daemon SHALL write `done/<req_id>.json` with `status` (`ok` | `error`), a `result` summary on success, an `error` reason on failure, and `started_at`/`finished_at` timestamps. Re-processing a `req_id` that already has a `done/` record MUST resolve to the existing record rather than dispatching again.

#### Scenario: Successful tick produces a done record

- **WHEN** the daemon processes a `tick` request
- **THEN** `done/<req_id>.json` is written with `status: "ok"` and a tick `result` summary, and the source `requests/<req_id>.json` is removed

#### Scenario: Duplicate request id is idempotent

- **WHEN** a request whose `req_id` already has a `done/` record is seen again
- **THEN** the daemon reuses the existing `done/` record and does not dispatch a second tick

### Requirement: Status rollup is the sole frontend observation source

The daemon SHALL write `status.json` each round with `updated_at`, a `daemon` liveness block (`pid`, `last_tick_at`, `idle`), and `ready` / `in_flight` / `recent_done` collections. Frontends SHALL read only `status.json` for manager state and MUST NOT scan internal coordinator directories (`runtime/handoff`, `state/coordinator/jobs`).

#### Scenario: Frontend renders manager state from the rollup

- **WHEN** a frontend requests manager status
- **THEN** it reads `status.json` alone and renders `ready` / `in_flight` / `recent_done` without touching any internal coordinator directory

### Requirement: Manager daemon drains requests each round

The manager daemon SHALL run as a resident loop (`paulshaclaw/coordinator/manager_daemon.py::run_loop`) that, each round, lists `requests/*.json` in time order and dispatches each via the existing `manager.run_tick` / `autonomy.dispatch_ready` internals, then writes `done/` and removes the request. The daemon MUST reuse existing coordinator internals rather than re-implementing orchestration.

#### Scenario: Pending requests are drained in order

- **WHEN** two requests are pending at the start of a round
- **THEN** the daemon processes them oldest-first, writing a `done/` record and removing each request

### Requirement: Manager daemon runs a periodic idle-gated tick

The daemon SHALL run a periodic fanout tick when the interval since the last tick is at least `tick_interval` (default 300s), assuming the responsibility previously held by the systemd timer. The idle gate (`--require-idle` semantics) MUST continue to apply to fanout only.

#### Scenario: Periodic tick fires after the interval

- **WHEN** `tick_interval` has elapsed since the last tick and the host is idle
- **THEN** the daemon runs a fanout tick and records it in `status.json` (`last_tick_at`)

#### Scenario: Non-idle host defers the periodic fanout

- **WHEN** the periodic tick is due but the host is not idle
- **THEN** the daemon skips the fanout for that round without erroring

### Requirement: Single-instance daemon lock

The manager daemon SHALL guard against concurrent instances with a single-instance lock. A second instance MUST NOT run while a live one holds the lock.

#### Scenario: Second daemon instance is refused

- **WHEN** a manager daemon is already running and holds the lock
- **THEN** a second `run_loop` invocation detects the lock and does not start a competing loop

### Requirement: A single request failure never topples the loop

A failure processing one request SHALL be isolated: the daemon MUST write `done/<req_id>.json` with `status: "error"` and an `error` reason, log it, and continue the loop. A request with an invalid schema MUST be rejected with an error `done/` record rather than crashing the daemon.

#### Scenario: Failing request is isolated

- **WHEN** processing one request raises an exception
- **THEN** the daemon writes an `error` done record for that `req_id` and continues processing later requests and periodic ticks

### Requirement: Daemon mounted via start.sh loop replacing the timer

`scripts/start.sh` SHALL start the manager daemon through a `start_manager_loop()` function mirroring `start_dream_loop()` — a background loop bound to the `start.sh` lifecycle, toggled by `PSC_MANAGER_DAEMON_DISABLED`, logging to `~/.agents/log/manager.log`. This mount SHALL replace the skipped `start_manager_service()` timer mount so the manager does not double-tick.

#### Scenario: Daemon starts with the lifecycle and honors the toggle

- **WHEN** `start.sh` runs and `PSC_MANAGER_DAEMON_DISABLED` is unset
- **THEN** the manager loop is started in the background and bound to `start.sh` cleanup, and the legacy timer mount is not activated

#### Scenario: Toggle disables the daemon

- **WHEN** `PSC_MANAGER_DAEMON_DISABLED` is set
- **THEN** `start.sh` skips starting the manager loop

### Requirement: Headless dispatch preserves existing safety gates

The daemon's dispatch path SHALL preserve the existing manager safety gates unchanged: a headless `executor` (default `copilot`), `allow_unsafe` defaulting to false with the fail-closed guard that refuses fanout when at most one slice is ready, and worktrees cut from `main`.

#### Scenario: Unsafe fanout is refused when too many slices are ready

- **WHEN** a fanout is requested with `allow_unsafe` true and more than one slice is ready
- **THEN** the daemon refuses the fanout (fail-closed) and records the refusal

### Requirement: Frontend controller client never imports coordinator

The frontend controller client (`paulshaclaw/control/client.py`) SHALL provide `read_status()`, `submit_request(type, args, requested_by)`, and `poll_done(req_id, timeout)`, and MUST NOT import the coordinator package, so the UI is immune to coordinator refactors and the repo split. Control-plane paths MUST be defined in one constants module rather than scattered `Path.home()` calls.

#### Scenario: Client module has no coordinator dependency

- **WHEN** `paulshaclaw/control/client.py` is imported
- **THEN** it does not import the coordinator package, and all control-plane paths resolve from a single constants module

### Requirement: Degraded read on missing or stale status

`read_status()` SHALL return an explicit degraded marker when `status.json` is missing or stale, and MUST NOT substitute a previously read value in its place.

#### Scenario: Missing status degrades explicitly

- **WHEN** `status.json` does not exist or is stale
- **THEN** `read_status()` reports a degraded state rather than returning a stale snapshot

### Requirement: Cockpit exposes manager status and tick bindings

The cockpit SHALL register a `Binding("m", ...)` that opens a manager status modal populated from `read_status()`, and a `Binding("t", ...)` that submits a non-blocking `tick` request via the controller client without blocking the Textual event loop. Both bindings MUST appear in the `?` help modal via the existing `BINDINGS` mechanism.

#### Scenario: Tick binding submits without blocking

- **WHEN** the operator presses `t` in the cockpit
- **THEN** a `tick` request is submitted via the client and the Textual event loop is not blocked waiting for the tick to complete

#### Scenario: New bindings appear in help

- **WHEN** the operator opens the `?` help modal
- **THEN** the `m` and `t` manager bindings are listed

### Requirement: paulshiabro exposes /manager command

paulshiabro SHALL register a `/manager [status|tick]` command in `commands.json` (with a Telegram menu entry) routed to a handler in `core/daemon.py` following the `/tmate` sub-action pattern. `status` MUST render a `read_status()` summary; `tick` MUST submit a request and short-poll `done/` (~15s), returning a result summary or a "queued, check `/manager status`" message on timeout.

#### Scenario: Manager status sub-action

- **WHEN** the operator sends `/manager status`
- **THEN** paulshiabro replies with a summary derived from `read_status()`

#### Scenario: Manager tick sub-action with timeout fallback

- **WHEN** the operator sends `/manager tick` and no `done/` record appears within the short-poll window
- **THEN** paulshiabro replies that the tick is queued and to check `/manager status`
