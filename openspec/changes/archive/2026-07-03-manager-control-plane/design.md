## Context

The persona manager (`paulshaclaw.coordinator`) has only CLI and systemd `--user` timer drivers, and neither the cockpit TUI nor the paulshiabro Telegram bot is wired to it. On this WSL host there is no user systemd, so `scripts/start.sh::start_manager_service()` graceful-skips and the timer never fires — the manager does not actually run. `start_dream_loop()` (a `start.sh` background `while true` loop, idle-gated, lifecycle-bound) is the *proven* always-on pattern here.

Repo constraints that shape this design: **hub-and-spoke** (a single orchestrator holds task authority; workers do bounded execution), **artifact-first** (canonical state lives in files, not prompt text; gates decide on files/schema), the **path split** (`~/.agents/` is private runtime state), path centralisation over scattered `Path.home()` (#91), and the Textual-version-drift lesson for cockpit tests (behavior verified on CI, not local).

The full component breakdown, JSON schemas, and data-flow diagrams live in `docs/superpowers/specs/2026-07-03-manager-control-plane-design.md`; the step-by-step implementation plan lives in `docs/superpowers/plans/2026-07-03-manager-control-plane.md`. This document records the load-bearing decisions only.

## Goals / Non-Goals

**Goals:**
1. Define the manager's **file contract** (`~/.agents/control/`: `requests/`, `done/`, `status.json`, alongside existing `specs/`) as the frontend↔manager interface and the #125 inter-repo API precursor.
2. Ship a **resident manager daemon** on the proven `start.sh` loop pattern: drain requests, run a periodic idle-gated tick, write a `status.json` snapshot each round.
3. Wire **cockpit** (`m` status panel / `t` submit tick) and **paulshiabro** (`/manager [status|tick]`) as pure controllers.
4. Keep frontends **coordinator-import-free** so the UI survives coordinator refactors and the repo split.

**Non-Goals:**
- Adding slices from a frontend (needs a plan; too heavy for a thin controller) → later issue.
- Real systemd residency of the manager → **#126** (this uses a `start.sh` loop as the bridge).
- enforce flip / persona-scope required check → **#124**.
- Fixing the legacy `/dispatch` path → **#23**.
- Actually splitting the repo → **#125** (this only *defines* the file contract as the precursor).

## Decisions

| Decision | Choice | Rationale / Alternatives rejected |
|---|---|---|
| Frontend↔manager coupling | **File contract** (`~/.agents/control/`) | Decoupled, artifact-first, and becomes the #125 inter-repo API. Rejected: direct `import coordinator` (breaks on repo split) and `subprocess` CLI calls (couples to CLI surface, no observable state). |
| Daemon runtime | **`start.sh` loop mirroring `start_dream_loop()`** | WSL has no user systemd (timer is skipped today); the dream loop is proven resident. Rejected: relying on the systemd `--user` timer — it silently no-ops here. The systemd version is deferred to #126. |
| Frontend observation source | **Single `status.json` rollup** written by the daemon | Frontends never scan internal `runtime/handoff` or `state/coordinator/jobs`, so coordinator refactors and the repo split don't touch the UI. Rejected: frontends reading internal state directly. |
| Daemon entry-point name | **`coordinator/manager_daemon.py`** (`run_loop`) | Deliberately not `daemon.py` to avoid confusion with paulshiabro's `core/daemon.py`. Reuses `autonomy`/`JobRegistry`/`Dispatcher`/`manager.run_tick` — the daemon is a thin contract shell, not a re-implementation. |
| Controller placement | **`paulshaclaw/control/client.py`** | A location importable by both cockpit and core that does **not** depend on coordinator, enforcing the import-free rule structurally. Control-path constants centralised here (or a shared paths module), per #91. |
| tick trigger model | **Non-blocking submit** (write request, return) | A blocking tick would stall the Textual event loop / exceed Telegram's ~30s window. Telegram `tick` short-polls `done/` ~15s then falls back to "queued". |
| Request write | **temp file + `os.rename`** (atomic), `req_id` = timestamp+uuid4 | Prevents the daemon reading a half-written request; `req_id` pairs `requests/` ↔ `done/`. Duplicate `req_id` resolves to the existing `done/` (idempotent). |
| Degraded reads | **Explicit `--` marker, never a stale value** | Per the telemetry lesson (a persistently-unreadable source must degrade visibly, not replay old values). Missing/stale `status.json` → degraded. |

## Risks / Trade-offs

- **Double-tick** if both the new loop and the old systemd timer run → disable/ignore the `start_manager_service()` timer mount once the loop is live.
- **WSL / no user systemd** → mitigated by design (the `start.sh` loop is the primary path; systemd is #126, not a dependency).
- **Textual version drift** breaks cockpit tests at patch time and can mask real regressions → verify new bindings by import/AST/inspect locally, treat behavior as CI-authoritative.
- **Deploy friction**: `start.sh` is the entrypoint, so changes need a tmux restart to take effect (ops: tmux death = full restart).
- **Path scatter** regressing #91 → all control-plane paths go through one constants module.
- **`done/` growth** unbounded over time → see Open Questions (retention policy).

## Migration Plan

- **Deploy**: merge → `git pull --ff-only` → restart tmux so `start.sh` re-runs and `start_manager_loop()` starts. The loop replaces the timer mount; disable the old manager `--user` timer to avoid double-tick.
- **Toggle / rollback**: set `PSC_MANAGER_DAEMON_DISABLED=1` (or revert `start.sh`) to stop the daemon. Frontends degrade gracefully — an absent `status.json` shows the degraded marker rather than erroring — and the contract files under `~/.agents/control/` are additive, so there is no destructive migration and nothing to un-migrate.

## Open Questions

- `tick_interval` (default 300s, inherited from the timer cadence) and `poll_interval` (3–5s) — confirm defaults, and whether `--require-idle` semantics stay fanout-only.
- Keep the systemd `--user` timer as a dormant #126 option, or remove its mount entirely now?
- `done/` retention/GC policy — TTL sweep vs. keep-until-acked; who prunes and when.
