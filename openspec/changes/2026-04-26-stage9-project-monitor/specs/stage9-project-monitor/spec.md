# Capability: stage9-project-monitor

## Purpose

Provide a single, autonomously maintained source of truth for every tracked project's stage / task / todo state, so that Stage 1 dispatch, Stage 3 lifecycle, and operator-facing surfaces (Stage 11 cockpit, ad-hoc CLI) consume one snapshot instead of each walking project files independently.

## Scope

In scope:

- Discovery of projects under one or more configured workspace roots.
- Classification of each project as **tracked** or **legacy**.
- Extraction of per-stage state for tracked projects: completed, in-progress (with processing task and next task), pending.
- A long-lived service that keeps the snapshot current via filesystem events plus a periodic safety scan.
- A read API and subscription stream over a local Unix socket.
- A `--once` CLI mode that runs the same logic as the service and emits the snapshot to stdout.
- The first paulshaclaw-wide global config file (workspaces, monitor knobs).

Out of scope:

- Modifying Stage 1 dispatch or Stage 3 lifecycle to consume the new API (those will be separate changes).
- Project management features (assignment, scheduling, sprints, permissions).
- Memory routing or knowledge graph maintenance (Stage 2 owns that).
- Enforcement of lifecycle gates (Stage 3 owns that).
- Importing or migrating legacy assets (the original Stage 9 mission, which remains cancelled).

## Behaviours

### B1. Workspace configuration

The service reads a global config that declares one or more workspace roots. Defaults are `~/prj_arc` and `~/prj_pri`. The config schema is additive and forwards-compatible so that other stages may later contribute their own sections to the same file.

### B2. Project classification

A subdirectory of any configured workspace is classified as **tracked** if it contains either a `.paul-project.yml` file or a populated `docs/superpowers/workstreams/stage*/` directory containing at least one `todo.md` or `task.md`. Otherwise it is classified as **legacy**.

Legacy projects are exposed to consumers only as a directory name and absolute path; no stage state is inferred for them. The visibility of legacy projects is controlled by a config policy (`list-only` by default, `hide` available).

### B3. Stage-state extraction

For each tracked project, the service produces three disjoint stage groupings:

- **Completed:** the stage has both an archived `openspec/changes/archive/*stageN-*` entry and a corresponding merge commit on `main`.
- **In-progress:** the stage has at least one open checkbox in its workstream `todo.md > Current Sprint`, OR it has a `wt/stageN-*` branch with commits ahead of `main`.
- **Pending:** the stage appears in the project's canonical stage table (or has a workstream skeleton) but has no in-progress or completed signal.

For every in-progress stage, the service additionally exposes:

- The first unchecked item in `todo.md > Current Sprint` as **processing task**.
- The next unchecked item (or first item, if there is no processing task yet) as **next task**.
- All entries under `todo.md > Blockers` as a list of blocker strings.

When a file is unparseable, the affected stage is marked **degraded** rather than causing the service to crash; the failing path is recorded in a per-project `source_signals` field so consumers can diagnose.

### B4. Single source of truth

The service derives state from project artifacts on every refresh. It does **not** maintain a persistent per-project state file owned by itself. Operators are never asked to maintain a parallel truth. In-memory caches are permitted; durable parallel state is not.

### B5. Service lifecycle

The service is a long-lived process with three concurrent loops:

1. A periodic workspace scanner that discovers added or removed projects at the configured cadence (default 60 s).
2. A filesystem watcher that observes `docs/superpowers/workstreams/`, `openspec/changes/archive/`, `.paul-project.yml`, and `.git/HEAD` per tracked project, with events debounced (default 500 ms) and coalesced per project before re-extraction.
3. A read API server that responds to consumer requests against the current snapshot.

The service must support a `--once` mode that performs a full scan + extract + JSON dump to stdout and exits 0, mirroring the `--once` parity established by Stage 11 cockpit.

### B6. Read API surface

Consumers interact with the service over a local Unix domain socket whose path is configured (default `~/.agents/run/project-monitor.sock`, permissions `0600`). The API offers:

- `list_projects` — returns every project (tracked and, depending on policy, legacy) with its current high-level state.
- `get_project_state(project_id)` — returns the full per-project state document (completed / in-progress / pending stages, with processing task / next task / blockers / source signals).
- `subscribe(filter)` — opens a newline-delimited JSON event stream. Events carry monotonic sequence numbers. Delivery is at-least-once; consumers detect gaps via the sequence numbers and re-fetch a snapshot when needed.

A thin CLI (`python -m paulshaclaw.monitor query …`) wraps the same socket calls for human and scripted use.

### B7. Failure & degradation

- If the workspace path does not exist, the workspace is logged as missing and skipped; other workspaces continue to scan.
- If a project's git operation fails (e.g. corrupt repo), only that project's branch-derived signals are dropped; file-derived signals continue.
- If the watcher fails to subscribe to a path, the service falls back to the periodic scan for that project and emits a `source_signals` warning.
- The service never silently rewrites or deletes files in scanned projects.

### B8. Privacy & security

Project paths and titles flow through the API; arbitrary file contents do not. The service never returns file content beyond the declared extracted fields. Any content surfaced via the API is subject to the redaction rules owned by Stage 6.

## Validation

- Unit tests cover tracked-vs-legacy classification, completed/in-progress/pending extraction, processing-task / next-task / blockers parsing, and degraded-path handling.
- An integration test runs the monitor against a temporary clone of paulshaclaw itself and asserts the snapshot matches the manually verified state recorded under `docs/superpowers/workstreams/stage9-project-monitor/evidence/`.
- A service test starts the monitor, edits a `todo.md`, and asserts a subscriber receives a coalesced change event within the configured debounce window.
- A CLI smoke test runs `python -m paulshaclaw.monitor --once --config <fixture>` and verifies a zero exit code with a JSON snapshot conforming to the documented schema.
- Evidence (red → green → refactor logs, sample snapshots, sample event streams) is captured under the workstream `evidence/` directory.

## Dependencies

- Stage 0 tooling (workstream skeleton convention).
- Stage 1 daemon's existing `load_config` patterns are referenced for the new global config loader contract.
- Stage 6 redaction rules apply to any data surfaced via the API.

## Explicit non-dependencies

- Does not depend on Stage 11 cockpit; the cockpit may consume Stage 9 in a follow-up but is not required by it.
- Does not depend on Stage 2 memory or Stage 3 lifecycle internal contracts beyond reading their public artifact files.
