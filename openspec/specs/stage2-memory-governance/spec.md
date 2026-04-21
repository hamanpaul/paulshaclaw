# stage2-memory-governance Specification

## Purpose
TBD - created by archiving change stage2-baseline. Update Purpose after archive.
## Requirements
### Requirement: Canonical memory routing path

Stage 2 SHALL fix the canonical memory path as `inbox → work-centric → knowledge`. No producer MAY write directly to `knowledge` without first passing through `inbox` and `work-centric`. `inbox` MUST retain original source and ingestion metadata but MUST NOT serve as the long-term query entrypoint. `work-centric` MUST aggregate by project / workstream / story and MUST be where the classifier performs dedup, correlation, and replay-candidate preparation. `knowledge` MUST only hold reusable, citable, replayable conclusions that already have provenance and source references.

#### Scenario: Scope declares the full path

- **WHEN** a reviewer reads `openspec/specs/stage2/scope.md`
- **THEN** the document MUST contain the phrase `inbox -> work-centric -> knowledge` in §2 (memory routing rules)

#### Scenario: Each layer states its own constraint

- **WHEN** a reviewer reads `openspec/specs/stage2/scope.md` §2
- **THEN** the document MUST describe all three layers with their respective constraints (inbox retains metadata but is not query entry, work-centric is where classifier runs, knowledge requires provenance)

### Requirement: Importer / classifier / replay / janitor boundary

Stage 2 SHALL separate `importer`, `classifier`, `replay`, and `janitor` as independently verifiable components. `janitor` MUST be declared as an independent service — not a pipeline tail step. `replay bundle` MUST read only distilled artefacts and ledger events; it MUST NOT scan raw prompts. `importer / classifier / replay` MUST each be independently testable so they can serve as sync-back gate prerequisites.

#### Scenario: Janitor is an independent service

- **WHEN** a reviewer reads `paulshaclaw/janitor/service.md`
- **THEN** the document MUST state janitor is an independent service (not attached to the ingestion pipeline) and MUST describe its guardrails

#### Scenario: Replay reads only distilled artefacts

- **WHEN** a reviewer reads `openspec/specs/stage2/scope.md` §4 or `paulshaclaw/memory/routing.md`
- **THEN** replay MUST be declared to read only distilled artefacts and ledger events, never raw prompts

### Requirement: decayed and reactivation events

Stage 2 SHALL treat `decayed` and `reactivation` as first-class ledger events, not implicit states. A `decayed` event MUST fire when a fact expires, its source becomes invalid, or it is superseded by conflicting evidence; the handler MUST retain the original reference, annotate the decay reason, and remove the record from the high-trust retrieval set. A `reactivation` event MUST fire when new evidence, human confirmation, or replay validation re-supports an existing record; the handler MUST append a `record-agent-reference` and restore retrieval weight.

#### Scenario: Scope names both events

- **WHEN** a reviewer reads `openspec/specs/stage2/scope.md` §3
- **THEN** the document MUST contain the literal string `decayed/reactivation` and describe the trigger + action for each event

### Requirement: Sync-back gate to custom-skills

Stage 2 SHALL declare a sync-back gate that governs when the project-tuned `paulsha-memory` skill may be pushed back to `hamanpaul/custom-skills`. The gate MUST require all of: (a) importer / classifier / replay passed Stage 2 tests, (b) `decayed/reactivation` rules documented with test evidence, (c) evidence files stored under `docs/superpowers/workstreams/stage2-paulsha-memory/evidence/`, (d) `review.md` contains no blocking finding, (e) Stage 2 MUST NOT extend the Stage 3 frontmatter schema — the canonical required fields `slice_id / artifact_kind / supersedes / checksum` remain owned by Stage 3.

#### Scenario: Gate lists five conditions

- **WHEN** a reviewer reads `custom-skills/paulsha-memory/README.md`
- **THEN** the document MUST enumerate five numbered sync-back gate conditions covering importer/classifier/replay pass, decayed/reactivation evidence retention, evidence location, non-blocking review, and non-extension of Stage 3 frontmatter schema

#### Scenario: Stage 3 frontmatter fields are named explicitly

- **WHEN** a reviewer reads `openspec/specs/stage2/scope.md` §5 item 4
- **THEN** the document MUST name `slice_id`, `artifact_kind`, `supersedes`, and `checksum` as the Stage 3-owned required fields that Stage 2 MUST NOT extend

### Requirement: Stage 2 integration check

Stage 2 SHALL ship `paulshaclaw/memory/tests/stage2_integration_check.sh` as a guard that fails fast under `set -euo pipefail` and validates seven surfaces via literal `grep -Fq` against specific phrases: scope routing phrase, memory routing inbox/knowledge, janitor systemd/reactivation, sync-back gate phrases, Stage 3 frontmatter field names (slice_id / artifact_kind / supersedes / checksum), evidence template sections, and review.md non-blocking conclusion. Running the script in a clean checkout MUST exit zero and print `[stage2] ok`.

#### Scenario: Clean run exits zero

- **WHEN** an operator runs `bash paulshaclaw/memory/tests/stage2_integration_check.sh` from the repo root on main
- **THEN** the script MUST exit with code 0 and its last line MUST be `[stage2] ok`

#### Scenario: Missing frontmatter field is caught

- **WHEN** any of `slice_id`, `artifact_kind`, `supersedes`, or `checksum` is removed from `openspec/specs/stage2/scope.md`
- **THEN** the script MUST exit non-zero at the "validate Stage 3 frontmatter field names named explicitly" check

### Requirement: Stage 2 evidence and archive layout

Stage 2 SHALL keep workstream artefacts under `docs/superpowers/workstreams/stage2-paulsha-memory/`. The directory MUST contain `plan.md`, `task.md`, `todo.md`, `review.md`, and an `evidence/` subdirectory with at least `README.md` and `stage2-integration-template.md` describing the test command and evidence file-naming convention. The repo SHALL also keep a handoff note at `docs/superpowers/archive/stage2-paulsha-memory-*.md` summarising the landing.

#### Scenario: Workstream directory contains required artefacts

- **WHEN** a reviewer lists `docs/superpowers/workstreams/stage2-paulsha-memory/`
- **THEN** the directory MUST contain `plan.md`, `task.md`, `todo.md`, `review.md`, and a non-empty `evidence/` subdirectory with at least `README.md` and `stage2-integration-template.md`

