# Stage 9 — Project Monitor Design

- Date: 2026-04-26
- Status: proposed
- Owner: @hamanpaul
- Topic: Stage 9 reborn as the always-on project-monitor service

## 0. Background

The §5.1 stage table currently marks Stage 9 as **cancelled** (replaced by the §4.3 memory symlink). This design re-uses the Stage 9 slot for a different, complementary mission: a **Project Monitor service** that produces a unified, always-current view of every active project's stage / task / todo state, and serves it to Stage 1 and Stage 3 as their canonical task source.

The motivating observation is that the recent status review showed each consumer (the operator, Stage 1 dispatch, Stage 3 lifecycle, Stage 11 cockpit) currently has to walk per-stage `todo.md` / `task.md` files independently. Without a single producer, in-flight projects would have to maintain duplicated state.

## 1. Goals & Non-Goals

### 1.1 Goals

- Provide one canonical, autonomously maintained snapshot of every tracked project's stage state.
- Surface, per project, **completed stages**, **in-progress stages** (with **processing task** and **next task**), and **pending / future stages**.
- Update the in-progress stage view as the underlying project artifacts change — without requiring the project owner to manually push state.
- Run as a long-lived service that survives across sessions, restartable via the same install/upgrade path as other paulshaclaw daemons.
- Introduce a paulshaclaw-level config (none exists today) so workspace paths and monitor settings live in one place.
- Treat unrecognised / undocumented projects as **legacy** and surface them only as a name + path, never as tracked work.

### 1.2 Non-Goals

- This change does **not** rewrite Stage 1 dispatch or Stage 3 lifecycle to consume the monitor; it only defines the contract and ships the monitor.
- Not a project-management product: the monitor reads truth from project files; it does not provide editing UIs, permissions, sprints, or roadmaps.
- Not a memory layer: it does not replace Stage 2 `paulsha-memory` or write to `~/.agents/memory`.
- Not a CI / test runner: it observes state, it does not enforce gates.
- The Stage 9 original mission (legacy asset import) remains cancelled.

## 2. Stage Positioning & Boundaries

```
~/prj_arc/<project>/                     ← scanned (default workspace #1)
~/prj_pri/<project>/                     ← scanned (default workspace #2)
   │
   ▼ filesystem watch + periodic scan
Stage 9 Project Monitor (this change)
   │
   ├── read API   ──► Stage 1 daemon (dispatch chooses tasks from monitor output)
   ├── read API   ──► Stage 3 lifecycle (lifecycle treats monitor output as task source)
   └── subscribe  ──► Stage 11 cockpit (future: pane "current project" view)
```

What Stage 9 owns:

- The workspace scan loop and project discovery rules.
- The project-state schema (how a project declares itself trackable).
- The read API surface and event subscription contract.
- The paulshaclaw global config file (workspaces, poll cadence, legacy policy).

What Stage 9 does **not** own:

- Stage 1 daemon or Stage 3 lifecycle internal task selection logic.
- Stage 2 memory routing.
- The artifact frontmatter schema (Stage 3 still owns it).

## 3. Core Design Decisions

### 3.1 Single source of truth — derive, don't duplicate

The monitor must **read project artifacts as truth** and never persist a parallel state that the operator has to keep in sync. Internal in-memory snapshots are allowed; a durable per-project state file owned by the monitor is **not**.

### 3.2 Discovery contract — what makes a project "tracked"

A project under a configured workspace is **tracked** if and only if it satisfies all of:

1. It has a `.paul-project.yml` (matching the existing convention used by paulshaclaw itself), OR
2. It has the `docs/superpowers/workstreams/` directory with at least one `stage*/` workstream containing `todo.md` and/or `task.md`.

If neither is present, the project is classified as **legacy** and only its path + directory name is exposed; no stage state is inferred. This is policy is configurable (`monitor.legacy_policy`) but defaults to "list, don't track".

### 3.3 Project-state extraction

For each tracked project, the monitor produces:

```
ProjectState:
  project_id        : str          (derived from .paul-project.yml or directory name)
  workspace         : str          (which configured workspace it lives under)
  path              : str          (absolute path)
  stages:
    completed       : [StageRef]   (stage spec exists AND archive entry exists in main)
    in_progress     : [StageView]  (workstream todo.md has open items OR matching wt/* branch ahead of main)
    pending         : [StageRef]   (stage row in canonical table but no workstream artifacts yet)
  legacy            : bool         (true if not satisfying 3.2)
  last_seen_at      : timestamp
  source_signals    : [Signal]     (which files / git refs were inspected — for debugging)

StageView (per in_progress stage):
  stage_id          : str
  workstream_path   : str
  processing_task   : TaskRef | null   (first unchecked item in todo.md > Current Sprint)
  next_task         : TaskRef | null   (second unchecked item, or first item if processing_task is null)
  blockers          : [str]            (parsed from todo.md > Blockers)
```

Extraction rules:

- "Completed stage" detection follows the existing pattern used in today's verification: an archive entry under `openspec/changes/archive/*stageN-baseline*` AND a merge commit in `main`.
- "In-progress" requires either (a) an open checkbox in `todo.md > Current Sprint`, or (b) a `wt/stageN-*` branch with commits ahead of `main`.
- "Processing task" is parsed deterministically from `todo.md > Current Sprint` (existing convention from §4 of `2026-04-20-stage-parallel-plan.md`).
- All parsing must degrade gracefully — a malformed file marks the stage as `degraded` rather than crashing the monitor.

### 3.4 Service shape

The monitor runs as a **long-lived process** with three loops:

1. **Workspace scanner** (periodic, cadence from config) — discovers added/removed projects.
2. **Filesystem watcher** (event-driven) — watches `docs/superpowers/workstreams/`, `openspec/changes/archive/`, `.paul-project.yml`, and `.git/HEAD` per tracked project, debounced.
3. **Read API server** — serves the snapshot to consumers.

Suggested transports (decision to be confirmed in implementation):

- **Local Unix domain socket** at `~/.agents/run/project-monitor.sock` for in-process Python clients (Stage 1, Stage 3, Stage 11) — consistent with the deploy three-plane layout.
- **CLI subcommand** `python -m paulshaclaw.monitor query …` for ad-hoc human use.
- A `--once` mode (parity with Stage 11) for one-shot scan + JSON dump, useful for tests and for the operator to run the same logic the service runs.

### 3.5 Global config — first paulshaclaw-wide config file

paulshaclaw currently has only stage-scoped configs (e.g. `config/paulshaclaw-stage1.sample.json`). Stage 9 introduces the first **global config**.

- Path: `~/.config/paulshaclaw/paulshaclaw.yaml` (per §4.1 — secret/config plane), with a sample at `paulshaclaw/config/paulshaclaw.sample.yaml` in repo.
- Loader honours: `--config` CLI flag → `PAULSHACLAW_CONFIG` env → default path → sample fallback (read-only).
- Schema (initial):

```yaml
workspaces:
  - path: ~/prj_arc
    name: archive
  - path: ~/prj_pri
    name: private

monitor:
  poll_interval_seconds: 60         # workspace scan cadence
  watch_debounce_ms: 500            # filesystem event debounce
  legacy_policy: list-only          # list-only | hide
  socket_path: ~/.agents/run/project-monitor.sock
  ignore_dirs:                      # extra patterns; .git/node_modules already implicit
    - target
    - .venv
```

Stage 1 / Stage 3 / Stage 11 may later add their own keys under this same file (e.g. `core:`, `cockpit:`), so the loader must be additive and forwards-compatible.

### 3.6 Subscription model

Consumers subscribe with `subscribe(filter)` over the Unix socket and receive newline-delimited JSON events when a tracked project's state changes. Events are coalesced per project per debounce window. The contract is **at-least-once delivery** with a per-event sequence number so consumers can detect gaps and re-fetch a snapshot.

## 4. Decisions (confirmed 2026-04-26)

The following decisions were made by the operator before implementation begins:

1. **Stage number reuse — Stage 9.** The Stage 9 slot is reused. Original "legacy asset import" mission stays cancelled (superseded by §4.3 memory symlink). The canonical stage table in `docs/research/05...` §5.1 has been updated, and a footnote records the prior mission's cancellation alongside the 2026-04-26 reactivation as Project Monitor. The §6.2 dependency diagram has been updated to show Stage 9 as an independent service depending on Stage 0.
2. **Watcher library — `watchdog`.** Cross-platform, mature, low-friction install. Implementation must wrap it behind an internal `Watcher` interface so the dependency can be swapped without touching consumers.
3. **Transport — local Unix domain socket only.** Path `~/.agents/run/project-monitor.sock`, permission `0600`. Permission containment outweighs the convenience of HTTP. If a future change needs remote access for Stage 11 cockpit, that becomes a separate transport change.
4. **`.paul-project.yml` schema — unchanged.** This change only reads the existing fields (`policy_profile`, `policy_version`). Tracked-vs-legacy classification relies on directory presence rules per §3.2. Any `monitor:` section is deferred to a future schema-extension change.
5. **Git branch inspection — `subprocess` shell-out to `git`.** Avoids adding `pygit2` (libgit2 build dependency). Performance is acceptable because branch checks happen per debounced refresh, not per request. The implementation must wrap git invocations behind an internal `GitInspector` interface so the strategy can be swapped if performance becomes a bottleneck.

## 5. Risks

- **Scan cost on large workspaces.** If `~/prj_pri` grows to dozens of projects, naïve periodic scans can become noisy. Mitigation: filesystem watcher is the primary signal; periodic scan is a slow safety net.
- **Stale snapshots after crash.** The monitor is the source of truth at runtime; if it crashes, consumers must fall back to "last known" or to a `--once` invocation. Document this in the recovery playbook (Stage 5).
- **Drift between canonical stage table and discovered state.** Stage 9 will surface this drift instead of hiding it (e.g. a stage marked completed in README but with open todo.md items will be shown as `in_progress`). This is intentional — it forces the canonical table to stay honest.
- **Secret leakage.** Project paths and titles flow across the API. Must respect Stage 6 redaction rules; never serialise file contents beyond declared fields.

## 6. Test strategy

- **Unit:** project-state extraction against synthetic workspace fixtures (tracked / legacy / degraded / mixed).
- **Integration:** point the monitor at a temporary workspace containing a clone of paulshaclaw itself; verify the produced snapshot matches the manually-walked state from today's verification pass.
- **Service:** start the monitor, modify a `todo.md`, assert that subscribers receive a coalesced change event within the debounce window.
- **CLI:** `python -m paulshaclaw.monitor --once --config <fixture>` exits 0 and prints a JSON snapshot matching the integration baseline.
