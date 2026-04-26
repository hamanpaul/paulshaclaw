## 1. Stage 9 scaffolding & canonical updates

- [x] 1.1 Update `docs/research/05.paulshaclaw-overview-architecture-stages-dependencies-acceptance.md` §5.1 to re-list Stage 9 as `project-monitor` (planned), retaining a footnote explaining the prior cancelled mission was superseded by §4.3 *(done in propose: §4.3, §5.1, §6.2 updated)*
- [ ] 1.2 Verify `README.md` stage table — Stage 9 is not listed there today (only 0–4), so no edit is required this round; revisit when README is expanded
- [ ] 1.3 Create the `paulshaclaw/monitor/` package layout (entry point, scanner, parser, api, watcher, models)
- [ ] 1.4 Add the workstream skeleton at `docs/superpowers/workstreams/stage9-project-monitor/{plan,task,todo}.md` per the writing-plans convention

## 2. Global config (first paulshaclaw-wide config)

- [ ] 2.1 Define the global config schema covering `workspaces[]`, `monitor.poll_interval_seconds`, `monitor.watch_debounce_ms`, `monitor.legacy_policy`, `monitor.socket_path`, `monitor.ignore_dirs`
- [ ] 2.2 Implement the config loader honouring `--config` flag → `PAULSHACLAW_CONFIG` env → `~/.config/paulshaclaw/paulshaclaw.yaml` → repo sample fallback
- [ ] 2.3 Ship `paulshaclaw/config/paulshaclaw.sample.yaml` with the documented defaults (`~/prj_arc`, `~/prj_pri`)
- [ ] 2.4 Add config-validation errors with clear messages for missing / malformed required keys (parity with Stage 1 `load_config`)

## 3. Workspace scanning & project discovery

- [ ] 3.1 Implement workspace enumeration that resolves each configured `workspaces[].path` and lists immediate subdirectories
- [ ] 3.2 Implement the tracked-vs-legacy classifier per design §3.2 (presence of `.paul-project.yml` OR a populated `docs/superpowers/workstreams/stage*/`)
- [ ] 3.3 Apply `monitor.ignore_dirs` and the implicit ignore set (`.git`, `node_modules`, etc.)
- [ ] 3.4 Surface legacy projects per `legacy_policy`: `list-only` (path + name only) or `hide`

## 4. Project-state extraction

- [ ] 4.1 Implement the canonical-table reader that lists declared stages for a project from its `docs/research/` overview (when present) or falls back to scanning `docs/superpowers/workstreams/stage*/`
- [ ] 4.2 Implement "completed stage" detection (`openspec/changes/archive/*stageN-*` AND merge commit in `main`)
- [ ] 4.3 Implement "in-progress stage" detection (open checkbox in `todo.md > Current Sprint` OR `wt/stageN-*` ahead of `main`)
- [ ] 4.4 Implement processing-task / next-task parser against the documented `todo.md > Current Sprint` format
- [ ] 4.5 Implement blockers parser against `todo.md > Blockers`
- [ ] 4.6 Mark a stage as `degraded` (rather than crashing) when its files are unparseable; record the failing path in `source_signals`

## 5. Service runtime

- [ ] 5.1 Implement the periodic workspace scanner loop with `monitor.poll_interval_seconds` cadence
- [ ] 5.2 Implement the filesystem watcher (debounced per `watch_debounce_ms`) over `docs/superpowers/workstreams/`, `openspec/changes/archive/`, `.paul-project.yml`, `.git/HEAD` for each tracked project
- [ ] 5.3 Coalesce overlapping events per project per debounce window before re-extracting state
- [ ] 5.4 Provide a `--once` mode that runs scan + extract + emit JSON to stdout and exits 0 (parity with `python -m paulshaclaw.cockpit --once`)

## 6. Read API surface

- [ ] 6.1 Define the JSON contract for `list_projects()`, `get_project_state(project_id)`, and `subscribe(filter)` matching design §3.3 schema
- [ ] 6.2 Implement the local Unix-socket server at the configured `monitor.socket_path` with permission `0600`
- [ ] 6.3 Implement `subscribe(filter)` with newline-delimited JSON events, monotonic `sequence` numbers, at-least-once delivery
- [ ] 6.4 Implement a thin `python -m paulshaclaw.monitor query {list|get|subscribe}` CLI that talks to the socket for human + scripted use

## 7. Validation & evidence

- [ ] 7.1 Unit tests for tracked/legacy classification across synthetic fixtures
- [ ] 7.2 Unit tests for completed/in-progress/pending stage extraction (use paulshaclaw's own state as a golden fixture)
- [ ] 7.3 Unit tests for processing-task / next-task / blockers parsing (including malformed → degraded path)
- [ ] 7.4 Integration test: point monitor at a temp workspace containing a clone of paulshaclaw; assert snapshot matches the manually verified state from 2026-04-26
- [ ] 7.5 Service test: launch monitor, edit a `todo.md`, assert subscriber receives a coalesced change event within the debounce window
- [ ] 7.6 CLI test: `python -m paulshaclaw.monitor --once --config <fixture>` exits 0 with valid JSON
- [ ] 7.7 Capture evidence under `docs/superpowers/workstreams/stage9-project-monitor/evidence/` (red → green → refactor logs, sample snapshot, sample event stream)

## 8. Documentation & handoff

- [ ] 8.1 Update `paulshaclaw/config/README.md` (or create) describing the new global `paulshaclaw.yaml`
- [ ] 8.2 Document the read-API contract (request/response JSON examples) in `docs/superpowers/workstreams/stage9-project-monitor/plan.md`
- [ ] 8.3 Add a follow-up note in Stage 1 and Stage 3 `todo.md` files: "consume Stage 9 monitor as task source — separate change"
- [ ] 8.4 Add a recovery entry to `docs/ops/recovery.md` for monitor crash / restart
