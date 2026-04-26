## Why

Stage 9 was previously marked **cancelled** in the canonical stage table (see `docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md` §5.1) because its original mission — bulk import of legacy assets — was superseded by the §4.3 symlink layout for `~/.agents/memory`.

Since then, two operational gaps have emerged:

1. **No cross-project visibility.** Today's status review showed that listing per-project stage progress (completed / in-progress / pending, plus the in-progress stage's processing task and next task) requires manually walking each repo's `docs/superpowers/workstreams/*/todo.md`, `task.md`, and stage tables. Stage 1 daemon and Stage 3 lifecycle have no shared upstream source they can both consume.
2. **Risk of duplicated state.** If Stage 1 / Stage 3 each cache project state independently, every active workstream has to maintain two truths. We already saw this drift between the README stage table and the workstream `todo.md` files during the validation pass.

Stage 9 is being **revived with a new mission**: an always-on **Project Monitor** service that autonomously scans a configured set of project workspaces, derives each project's stage / task / todo state from in-repo artifacts, and exposes it as the canonical task source for Stage 1 dispatch and Stage 3 lifecycle. Projects without recognised state files are treated as **legacy** and not actively tracked.

This change is needed now because Stages 0–7 + 11 are all on `main`, and the next round of integration work (Stage 3 ↔ Stage 11 real-time sync, Coordinator transport) needs a single authoritative project-state surface to consume.

## What Changes

- **Re-scope Stage 9** from "legacy asset import" (cancelled) to **`stage9-project-monitor`** in the canonical stage table.
- **Add a Project Monitor service** that runs as a long-lived process and maintains an up-to-date snapshot of every tracked project.
- **Introduce a project-level config** (paulshaclaw global config — currently absent) with at minimum:
  - `workspaces`: list of workspace root paths to scan, default `[~/prj_arc, ~/prj_pri]`
  - `monitor.poll_interval`: scan cadence
  - `monitor.legacy_policy`: how to surface untracked / legacy projects (list-only vs hide)
- **Define a project-state contract** (the files Stage 9 will read from each project): `state/`, `todo`, `task` artifacts (kept aligned with the existing `docs/superpowers/workstreams/*/{todo,task}.md` convention so paulshaclaw itself is monitorable on day one).
- **Expose a read API** for Stage 1 dispatch and Stage 3 lifecycle to consume:
  - `list_projects()` — every tracked project with current stage status
  - `get_project_state(project_id)` — completed / in-progress (with processing + next task) / pending stages
  - `subscribe(...)` — change notifications for in-progress stage updates (so Stage 11 cockpit can react)
- **Update the canonical stage table** in `docs/research/05...` and `README.md` to reflect Stage 9's new mission.
- **Single source of truth principle**: Stage 9 must derive state by reading project artifacts; it does **not** maintain its own copy that operators must keep in sync.

## Capabilities

### New Capabilities

- `stage9-project-monitor`: Covers the project-monitor service contract, including workspace discovery, project-state extraction, the read/subscribe API for Stage 1/3 consumption, the global `paulshaclaw` config schema, and the legacy-project policy.

### Modified Capabilities

- None. Stage 1 and Stage 3 will adopt the new read API in their own follow-up changes; this change only defines the contract and ships the monitor.

## Impact

- **Affected code**:
  - New service modules under `paulshaclaw/monitor/` (or equivalent), including the workspace scanner, project-state parser, and read API surface.
  - New global config loader (currently `paulshaclaw` only has stage-scoped configs such as `config/paulshaclaw-stage1.sample.json`).
  - New CLI / service entry point (`python -m paulshaclaw.monitor` or similar) with `--once` parity with Stage 11.
- **Affected documentation**:
  - `docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md` §5.1 stage table — Stage 9 row updated.
  - `README.md` stage table — Stage 9 entry updated.
- **Affected systems**:
  - Stage 1 daemon (`paulshaclaw/core/`) will eventually read from the monitor instead of from a static config — out of scope for this change but the contract is fixed here.
  - Stage 3 lifecycle (`paulshaclaw/lifecycle/`) will eventually treat monitor output as task source.
  - Stage 11 cockpit may add a project-level pane in a follow-up.
- **Dependencies**:
  - Filesystem watcher library (TBD in `design.md`) for change detection.
- **Explicitly not impacted**:
  - Stage 11 cockpit's tmux-pane behaviour (cockpit already runs and is unchanged).
  - The §4.3 memory symlink layout (Stage 9's original cancelled mission stays cancelled).
  - Secret handling under `~/.config/paulshaclaw/`.
