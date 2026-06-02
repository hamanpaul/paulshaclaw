## ADDED Requirements

### Requirement: Dream orchestration service

Stage 2 SHALL provide an independent `dream` service that orchestrates the existing per-pass components rather than reimplementing them. `psc memory dream run` MUST execute the Topic 3/3.2 atomize pass and then the Topic 4 janitor pass over the current backlog, in that order, and MUST record one run record to `runtime/ledger/dream.jsonl`. The two passes MUST be isolated: a failure in one pass MUST be recorded and MUST NOT prevent the other pass from running or crash the run. The service MUST be separate from the ingestion pipeline and MUST be triggered by a scheduler, never by the importer.

#### Scenario: Passes run in order and are isolated

- **WHEN** `dream run` executes and the atomize pass raises
- **THEN** the janitor pass MUST still run
- **THEN** the run record MUST capture the atomize error and a degraded `status`

#### Scenario: Run is recorded

- **WHEN** a non-dry-run `dream run` completes
- **THEN** `runtime/ledger/dream.jsonl` MUST gain one record with `run_id`, `status` (`ok`/`partial`/`failed`), per-pass summaries, and `dream_config_hash`

#### Scenario: Dry run does not mutate state

- **WHEN** `dream run --dry-run` executes
- **THEN** both passes MUST run in dry mode and no `dream.jsonl` record MUST be written

### Requirement: Dream status and backlog

Stage 2 SHALL provide `psc memory dream status` returning the latest run summary (from `dream.jsonl`) and the current backlog depth (count of unprocessed raw sessions). The status MUST NOT contain slice body content or any raw prompt content.

#### Scenario: Status reflects last run

- **WHEN** `dream status` runs after a `dream run`
- **THEN** it MUST report the latest run's `status` and a backlog depth

### Requirement: Idle-gated scheduling

Stage 2 SHALL ship a systemd user unit/timer template and an idle-check wrapper so the dream service can run on a workday-morning schedule only when the system is idle. The timer template MUST use `OnCalendar` for Monday–Friday morning and MUST invoke `dream run --require-idle`. `--require-idle` MUST skip the run (log and exit zero) when the system is confirmed busy, and MUST proceed when idle or when idleness cannot be determined (fail-safe-to-run). The idle decision MUST be implemented in Python so it is unit-testable with an injected probe.

#### Scenario: Busy system skips

- **WHEN** `dream run --require-idle` runs and the idle probe reports busy
- **THEN** the run MUST be skipped, exit zero, and write no `dream.jsonl` record

#### Scenario: Indeterminate idleness proceeds

- **WHEN** the idle probe cannot determine load
- **THEN** the run MUST proceed

### Requirement: Proposal-first framework for cross-session changes

Stage 2 SHALL establish a proposal-first framework at `runtime/proposals/` with a human-review gate, so that any future cross-session canonical change (lineage merges, supersession, entity reconciliation) is proposed and gated rather than auto-applied. The MVP dream service MUST NOT auto-apply any cross-session canonical change and MUST NOT generate proposal content in this change; the framework API (`append`, `pending`, `requires_approval`) and storage MUST exist for later population.

#### Scenario: No auto-apply path

- **WHEN** the MVP dream service runs
- **THEN** it MUST NOT write any cross-session merge/supersession directly to `knowledge/`
- **THEN** `requires_approval` MUST return true for canonical-mutating proposal kinds

### Requirement: Replay bundle reads only distilled artefacts and ledger

Stage 2 SHALL provide `psc memory bundle` that assembles a replay bundle from selected knowledge slices and their ledger events, and MUST NOT read raw prompts or raw queue/inbox/archive payloads. Selection MUST support `--project`, `--tag`, and `--entity` facets combined with AND, default to the active (non-decayed) set via the Topic 4 retrieval-set API, and require at least one facet. The bundle MUST contain a `manifest.json` (selection, slice ids, counts, `raw_excluded: true`), a `slices/` directory of the selected distilled slices, and a `ledger.jsonl` of the touching lifecycle/relations/processing events.

#### Scenario: Bundle excludes raw

- **WHEN** a bundle is built for any selection
- **THEN** the bundle MUST contain only distilled slices and ledger events
- **THEN** `manifest.json` MUST declare `raw_excluded: true` and the bundle MUST contain no raw prompt content

#### Scenario: At least one facet required

- **WHEN** `bundle` is invoked with no `--project`/`--tag`/`--entity`
- **THEN** it MUST fail with an error rather than dumping the whole knowledge base

#### Scenario: Active-set default

- **WHEN** a bundle is built without `--include-decayed`
- **THEN** decayed slices MUST be excluded via the Topic 4 retrieval-set API

### Requirement: Dream service determinism and logs

Stage 2 dream and bundle execution MUST inject `now` (no wall-clock in records), append-only with flock for `dream.jsonl`, and MUST NOT write slice body content or raw content to logs (`~/.agents/memory/log/dream.log` carries only run id, counts, and error categories). A corrupt `dream.jsonl` line MUST fail closed on read.

#### Scenario: Logs carry no content

- **WHEN** the dream service logs a pass failure
- **THEN** the log entry MUST contain only the run id, counts, and error category, not slice or raw content
