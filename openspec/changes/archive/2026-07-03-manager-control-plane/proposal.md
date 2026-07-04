## Why

The persona **manager** (`paulshaclaw.coordinator`) can today only be driven two ways — the CLI (`python -m paulshaclaw.coordinator tick|fanout|ready|jobs|stat`) and a systemd `--user` timer — and neither operator frontend is wired to it. Worse, on this WSL host there is no user systemd, so `scripts/start.sh`'s `start_manager_service()` graceful-skips and the manager timer never fires (`systemctl --user list-timers` is empty): the manager effectively does not run here. The one always-on pattern proven on this host is the dream loop (`start.sh` background loop, idle-gated, lifecycle-bound). This change gives the manager a resident daemon on that proven pattern and wires cockpit + paulshiabro to it through a decoupled **file contract** — which also becomes the stable inter-repo API required before #125 splits the repo.

## What Changes

- **New file contract** at `~/.agents/control/` — the sole interface between frontends and the manager (and, post-#125, between repos):
  - `requests/<req_id>.json` — frontend writes intent (`tick` / `fanout`) via atomic temp + `os.rename`; `req_id` = timestamp + uuid4.
  - `done/<req_id>.json` — daemon writes per-request result/ack, idempotent by `req_id`.
  - `status.json` — daemon rollup each round (`ready` / `in_flight` / `recent_done` / daemon liveness); the frontends' single observation source.
  - Paths centralised in one constants module (no scattered `Path.home()`, per #91); `schema_version` on every file for #125 contract evolution.
- **New resident manager daemon** `paulshaclaw/coordinator/manager_daemon.py` (`run_loop`, deliberately not `daemon.py` to avoid clashing with paulshiabro's `core/daemon.py`). Each round: drain `requests/` (time-ordered) → dispatch via existing `manager.run_tick` / `autonomy.dispatch_ready` → write `done/` → remove request; run a periodic idle-gated fanout tick (assumes the timer's job); write the `status.json` rollup; `sleep poll_interval`. Reuses existing coordinator internals (`autonomy`, `JobRegistry`, `Dispatcher`) — the daemon is a thin contract shell, not a re-implementation. A single-instance lock guards it; one bad request writes `done status=error` and never topples the loop.
- **Runtime mount**: `scripts/start.sh` gains `start_manager_loop()` mirroring `start_dream_loop()` (background subshell, `PSC_MANAGER_DAEMON_DISABLED` toggle, `~/.agents/log/manager.log`, bound to `start.sh` cleanup). It **replaces** the skipped `start_manager_service()` timer mount; the old timer is disabled/ignored to avoid double-tick.
- **New frontend controller client** `paulshaclaw/control/client.py` — `read_status()`, `submit_request()`, `poll_done()`. Pure controllers: they touch only the contract, never import coordinator, so the UI is immune to coordinator refactors and the repo split. A missing/stale `status.json` reads as an explicit degraded marker, never a stale value.
- **cockpit** (`app.py`): `Binding("m", ...)` opens a manager status modal (mirrors the existing `HelpModal`) from `read_status()`; `Binding("t", ...)` submits a non-blocking `tick` request; both auto-appear in the `?` help modal via the existing `BINDINGS` mechanism.
- **paulshiabro** (`commands.json` + `core/daemon.py`): `/manager [status|tick]` following the `/tmate` sub-action pattern — `status` renders a `read_status()` summary; `tick` submits a request and short-polls `done/` (~15s), returning a summary or "queued, check `/manager status`".
- Existing manager safety is preserved unchanged (headless `executor` default `copilot`, Haiku alias `claude-haiku-4.5`; `allow_unsafe` default false with the `_refuse_unsafe_fanout` fail-closed ≤1-ready-slice guard; worktree cut from `main`).

## Capabilities

### New Capabilities

- `manager-control-plane`: the `~/.agents/control/` file contract (request/done/status schemas plus atomic-write, single-instance, idempotency, and degraded-read rules), the resident manager daemon that consumes it (request drain, periodic idle-gated tick, `status.json` rollup, `start.sh` runtime mount, preserved safety gates), and the pure-controller frontend surface (`control/client.py` + cockpit `m`/`t` bindings + paulshiabro `/manager` command). The frontends never import coordinator.

### Modified Capabilities

None. The frontend integrations are additive controllers owned by the new capability: existing `stage11-operator-cockpit` (pane swap, active-slot) and `agent-command` (`/agent`) requirements do not change semantics.

## Impact

- **New code**: `paulshaclaw/coordinator/manager_daemon.py`, `paulshaclaw/control/client.py` (+ a control-path constants module).
- **Modified code**: `scripts/start.sh` (`start_manager_loop`, retire timer mount), `paulshaclaw/cockpit/app.py` (`m`/`t` bindings + manager modal), `paulshaclaw/core/daemon.py` + `paulshaclaw/core/commands.json` (`/manager` handler + registration).
- **Reused, not changed**: `manager.run_tick`, `autonomy.scan_specs/ready_units/dispatch_ready`, `JobRegistry`, `Dispatcher`.
- **Runtime**: `start.sh` is the entrypoint; deploy requires a tmux restart (ops: tmux death = full restart). Manager timer disabled to avoid double-tick.
- **Deferred (explicit non-goals)**: real systemd residency → #126; add-slice-from-frontend (needs a plan, too heavy for a thin frontend); enforce flip / persona-scope required check → #124; fixing legacy `/dispatch` → #23; actual repo split → #125 (this only defines the file contract as its precursor).
- **Tests**: contract schema round-trip + atomic write + concurrent submit + degraded read; daemon drain / idle-gated tick / idempotency / single-instance lock / single-request-failure isolation via injected fake `Dispatcher`/`JobRegistry`; frontend actions via injected fake client; cockpit help modal includes the new bindings (import/AST locally, behavior on CI per the Textual-drift lesson). Run with `~/.local/bin/pytest paulshaclaw/...`.
