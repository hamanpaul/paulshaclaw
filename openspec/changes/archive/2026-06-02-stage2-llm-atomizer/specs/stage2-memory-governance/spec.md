## ADDED Requirements

### Requirement: Per-session LLM semantic promoter

Stage 2 SHALL provide an `LLMPromoter` that implements the Topic 3 `Promoter` seam to perform semantic promotion of one session's fragments into knowledge slices. The `Promoter` interface SHALL be widened from per-fragment to per-session: `promote(fragments, config) -> list[Slice]`, so the promoter MAY merge fragments into one slice or split one fragment into several. The deterministic `IdentityPromoter` MUST be preserved under the same per-session signature and MUST remain selectable. The splitter, ledgers, flow-through, and two-pass pipeline of Topic 3 MUST NOT be otherwise changed.

#### Scenario: IdentityPromoter remains 1:1 under per-session signature

- **WHEN** `IdentityPromoter.promote(fragments, config)` is called
- **THEN** it MUST return exactly one slice per input fragment

#### Scenario: LLM promoter may merge fragments

- **WHEN** the LLM promoter promotes a session whose fragments describe one concept across two fragments
- **THEN** it MAY return a single slice whose `source_fragment_indices` lists both fragments

### Requirement: Configurable agent-exec backend

Stage 2 SHALL drive the LLM promoter through a configurable `agent_exec` backend that invokes a one-shot subprocess command (default `scripts/claude-gemma4`, a local model). The backend MUST NOT require an API key or per-token billing; authentication, if any, is the invoked agent's responsibility. The agent command MUST be a configuration value (not hardcoded) and MUST be shareable with the paulshiabro `/agent` command's launcher configuration. The promoter MUST accept an injectable client so tests can substitute a fake without a real model.

#### Scenario: Agent command is configurable

- **WHEN** an operator sets `agent_exec.command` in `atomizer.yaml` or its override
- **THEN** the promoter MUST invoke that command rather than a hardcoded one

#### Scenario: Tests run without a real model

- **WHEN** the promoter is constructed with a fake agent client
- **THEN** promotion MUST complete deterministically using the fake's canned output, with no network or model dependency

### Requirement: Seed atomization skill document

Stage 2 SHALL ship a seed atomization skill document at `paulshaclaw/memory/atomizer/skills/atomize-knowledge-slice.md` that instructs the agent how to split, merge, tag, and relate session content into knowledge slices, and that declares the mandatory output contract. Atomization behavior MUST live in this skill document, not be hardcoded in prompt assembly, so the skill is the single artifact a future optimization loop refines.

#### Scenario: Skill declares the output contract

- **WHEN** a reviewer reads the seed skill document
- **THEN** it MUST describe the required JSON output schema the agent must emit (slices with `artifact_kind`, `project`, `tags`, `body`, `source_fragment_indices`, and `relations`)

### Requirement: LLM output contract and slice assembly

Stage 2 SHALL require the agent to return a JSON array of slice proposals, each with `title`, `artifact_kind` (a Stage 3 `ARTIFACT_KIND`), `project` (a known project or `_unknown`), `tags`, a non-empty `body`, `source_fragment_indices`, and `relations`. Stage 2 MUST parse and schema-validate this output and MUST fail closed on any violation. Each accepted proposal MUST become a slice whose frontmatter is the Topic 4 ∪ Stage 3 union plus a `tags` field, whose `checksum` equals `sha256(body)`, and whose `slice_id` is content-derived from the session identity and the body. Every produced slice MUST pass `paulshaclaw.lifecycle.schema.validate_frontmatter` and the Topic 4 read contract.

#### Scenario: Invalid output fails closed for the whole session

- **WHEN** the agent returns malformed JSON, an out-of-range `artifact_kind`, an unknown `project`, or an empty `body`
- **THEN** no knowledge slice MAY be written for that session
- **THEN** the session MUST remain in `state=split` with a warning, for retry on the next run

#### Scenario: Produced slice passes the Stage 3 gate

- **WHEN** a slice produced by the LLM promoter is fed to `python3 -m paulshaclaw.lifecycle.gate`
- **THEN** validation MUST pass

### Requirement: Semantic relations and tags

Stage 2 SHALL record LLM-inferred semantic relations as new edge types in `runtime/ledger/relations.jsonl`: `relates_to` (slice to slice) and `mentions` (slice to `entity:<NAME>`), in addition to the Topic 3 deterministic edges. A `relates_to` whose target cannot be resolved within the promotion batch MUST be skipped with a warning rather than failing the session. Slice tags MUST be stored in a Stage-2-owned `tags` frontmatter field and MUST NOT extend the Stage 3 required schema.

#### Scenario: Dangling relation is skipped, not fatal

- **WHEN** a proposal's `relates_to` target title does not match any slice in the same batch
- **THEN** that edge MUST be skipped with a warning
- **THEN** the remaining slices and edges MUST still be written

### Requirement: Frozen LLM output and crash-resume determinism

Stage 2 SHALL freeze a session's LLM output at first promotion so the non-deterministic step is idempotent on resume. The raw agent output MUST be cached at `runtime/cache/atomize/<session_key>__<fragments_hash>.json`; a subsequent promotion of the same session and fragments MUST reuse the cache rather than re-invoking the agent. A corrupt cache entry MUST be treated as a miss (re-invoke) and MUST NOT fail the run. The processing `promoted` ledger record MUST include `promoter`, `model`, and `skill_hash` for later optimization traceability.

#### Scenario: Resume reuses cached output

- **WHEN** a promotion is interrupted after the agent call but before the `promoted` ledger record
- **THEN** the next run MUST reuse the cached agent output and MUST NOT call the agent again for that session

#### Scenario: Promoted record is traceable

- **WHEN** the LLM promoter promotes a session
- **THEN** the `processing.jsonl` `promoted` record MUST include `promoter`, `model`, and `skill_hash`

### Requirement: Redaction trust boundary for distilled output

Stage 2 LLM promotion MUST treat its input fragments as already redacted at the Topic 8 `raw_to_distilled` boundary and MUST NOT re-scan slice bodies for secrets in this change. This limitation MUST be documented; a future `distilled_to_canonical` policy pass is the place to add output-side scanning. Logs MUST NOT contain raw agent output or session body content.

#### Scenario: Logs never contain model output

- **WHEN** the promoter logs a failure
- **THEN** the log entry MUST NOT contain the raw agent output or any session body content
- **THEN** it MUST contain only the failure category, `session_key`, and skill/config hashes
