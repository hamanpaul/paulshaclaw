## 1. Control-plane contract & path constants

- [x] 1.1 Add a control-plane constants module (single source for `~/.agents/control/` root, `requests/`, `done/`, `status.json`, `schema_version`) — no scattered `Path.home()` (#91)
- [x] 1.2 Add a `req_id` generator (UTC timestamp + uuid4) and the request/done/status JSON shapes (with `schema_version`)
- [x] 1.3 RED: contract tests — schema round-trip, `schema_version` present on every written file

## 2. Frontend controller client (`paulshaclaw/control/client.py`)

- [x] 2.1 RED: client tests — `submit_request` writes atomically (temp + `os.rename`), concurrent submits from two callers do not overwrite, `read_status` degrades explicitly on missing/stale `status.json`, `poll_done` returns on record / None on timeout
- [x] 2.2 Implement `submit_request(type, args, requested_by)` (atomic write, unique `req_id`)
- [x] 2.3 Implement `read_status()` with explicit degraded marker (never a stale value)
- [x] 2.4 Implement `poll_done(req_id, timeout)`
- [x] 2.5 Assert (test) the client module imports without importing the coordinator package

## 3. Manager daemon (`paulshaclaw/coordinator/manager_daemon.py`)

- [x] 3.1 RED: daemon tests with injected fake `Dispatcher`/`JobRegistry` — drain one `tick` request → writes `done` + updates `status`; duplicate `req_id` is idempotent; periodic tick is idle-gated; a single failing request writes `error` done and the loop continues; second instance is refused by the lock
- [x] 3.2 Implement `run_loop`: drain `requests/*.json` time-ordered → dispatch via existing `manager.run_tick` / `autonomy.dispatch_ready` → write `done/` → remove request (reuse coordinator internals, no re-implementation)
- [x] 3.3 Implement idempotent `done/` handling (existing record wins) and invalid-schema rejection (error `done`, no crash)
- [x] 3.4 Implement periodic idle-gated fanout tick (`tick_interval` default 300s; `--require-idle` stays fanout-only) and `status.json` rollup (`ready`/`in_flight`/`recent_done`/`daemon`)
- [x] 3.5 Implement single-instance lock and per-request failure isolation (log + continue)
- [x] 3.6 Preserve safety gates unchanged: default `executor=copilot`, `allow_unsafe=false`, fail-closed `--allow-unsafe` guard (reject when >1 slice is ready), worktree from `main`

## 4. Runtime mount (`scripts/start.sh`)

- [x] 4.1 Add `start_manager_loop()` mirroring `start_dream_loop()` — background subshell, `PSC_MANAGER_DAEMON_DISABLED` toggle, `~/.agents/log/manager.log`, bound to `start.sh` cleanup
- [x] 4.2 Retire the `start_manager_service()` timer mount (disable/ignore) so the manager does not double-tick

## 5. cockpit bindings (`paulshaclaw/cockpit/app.py`)

- [x] 5.1 Add `Binding("m", "manager_panel", ...)` → `action_manager_panel` pushing a `ManagerModal` populated from `read_status()` (mirror `HelpModal`)
- [x] 5.2 Add `Binding("t", "manager_tick", ...)` → `action_manager_tick` submitting a non-blocking `tick` (must not block the Textual event loop), then refresh
- [x] 5.3 Verify new bindings appear in the `?` help modal — locally by import/AST/inspect, behavior authoritative on CI (Textual-drift lesson)

## 6. paulshiabro `/manager` (`core/commands.json` + `core/daemon.py`)

- [x] 6.1 Register `/manager [status|tick]` in `commands.json` with a Telegram menu entry
- [x] 6.2 RED: handler tests with injected fake client — `status` renders `read_status()` summary; `tick` submits + short-polls `done/` and falls back to "queued, check `/manager status`" on timeout
- [x] 6.3 Implement `_handle_manager_command` following the `/tmate` sub-action pattern

## 7. Integration & regression

- [x] 7.1 End-to-end: cockpit `t` → request file → daemon drain → `done` + `status` → cockpit modal reflects result (with fakes; no real dispatch)
- [x] 7.2 Regression: existing `/dispatch`, `/agent`, and cockpit pane-swap behavior unchanged
- [x] 7.3 Full suite green via `~/.local/bin/pytest paulshaclaw/...` (avoid `unittest discover` — it drops `def test(tmp_path)` style)

## 8. Deploy & docs

- [x] 8.1 Disable the legacy manager `--user` timer on the host to avoid double-tick; confirm `start_manager_loop` runs after a tmux restart
- [x] 8.2 Sync docs (`README.md` / `docs/**`) for the new control plane + `/manager` + cockpit bindings (R-18), or apply `policy-exempt:docs-sync` if internal-only
