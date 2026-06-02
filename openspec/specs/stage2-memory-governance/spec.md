# stage2-memory-governance Specification

## Purpose
Define the Stage 2 memory governance contract, including the repo-local importer
and hook substrate that writes canonical session artifacts into
`~/.agents/memory/`.
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

### Requirement: Stage 2 memory policy boundary contract

Stage 2 SHALL define a memory security policy boundary contract with the canonical boundary identifiers `external_to_raw`, `raw_to_distilled`, `distilled_to_canonical`, `canonical_to_indexed`, and `indexed_to_consumer`. The boundary identifiers SHALL reuse the existing Stage 2 memory layer model and SHALL NOT redefine the physical memory tree. MVP execution MUST enforce policy at `external_to_raw` and `raw_to_distilled`; the other boundaries MUST be reserved in policy schema for future Stage 2 components.

#### Scenario: Boundary schema lists all five identifiers

- **WHEN** an operator reads `paulshaclaw/memory/policy/boundaries.yaml`
- **THEN** it MUST list `external_to_raw`, `raw_to_distilled`, `distilled_to_canonical`, `canonical_to_indexed`, and `indexed_to_consumer`
- **THEN** `external_to_raw` and `raw_to_distilled` MUST be marked mandatory for MVP execution
- **THEN** the remaining three boundaries MUST be marked deferred

### Requirement: Policy artifacts and effective policy hash

Stage 2 SHALL store default policy artifacts in `paulshaclaw/memory/policy/secrets.yaml`, `classification.yaml`, and `boundaries.yaml`. Stage 2 SHALL support a local override file at `~/.config/paulshaclaw/policy.override.yaml`. The policy loader MUST merge defaults and local override into an effective policy and compute a deterministic `effective_policy_hash`. Ledger and audit records written by the policy layer MUST include both `policy_version` and `effective_policy_hash`.

#### Scenario: Local override participates in effective hash

- **WHEN** a local override disables a rule for a session
- **THEN** the effective policy hash MUST change
- **THEN** dry-run, audit, and ledger output for that session MUST include the changed hash

#### Scenario: Unsupported major version fails closed

- **WHEN** a consumer loads a policy with an unsupported major `policy_version`
- **THEN** fail-closed boundaries MUST reject processing
- **THEN** no inbox artifact MAY be published

### Requirement: Redaction at ingress boundaries

Stage 2 SHALL run cheap regex redaction at `external_to_raw` before hook scripts write queue payloads. Stage 2 SHALL run the full policy library and gitleaks detector at `raw_to_distilled` before importer writes `inbox/`. Redaction action MUST be line-level: every line with one or more hits MUST be replaced with `[REDACTED LINE: <rule-id> x<count>]` or an equivalent multi-rule placeholder. The memory system MUST NOT store matched secret text or original matched lines in `inbox/`, ledger, audit, `archive/queue/`, or `runtime/queue/_failed/`.

#### Scenario: Hook redacts before queue write

- **WHEN** a hook payload contains an obvious GitHub PAT fixture
- **THEN** the queue payload MUST contain a redacted line placeholder
- **THEN** the queue payload MUST NOT contain the original token

#### Scenario: Gitleaks-only hit is not archived raw

- **WHEN** gitleaks finds a secret in a queue payload that hook regex missed
- **THEN** the importer MUST write only redacted content to `inbox/`
- **THEN** any `archive/queue/` copy MUST be redacted
- **THEN** the original queue payload MUST be unlinked after successful processing

### Requirement: Classification tagging for distilled artifacts

Stage 2 SHALL classify every distilled `inbox/` artifact with `classification_level`, `classification_reason`, `classification_policy_hash`, and `classification_source`. Allowed levels MUST be `public`, `private`, and `secret`. Unknown projects MUST default to `private`. Any artifact with redaction hits MUST be classified as `private` unless a more restrictive rule applies. Classification failure MUST fail open with warning by writing the artifact as `private` and recording `classification-warning`.

#### Scenario: Unknown project defaults private

- **WHEN** the project resolver returns `_unknown`
- **THEN** the inbox artifact MUST contain `classification_level: private`
- **THEN** `classification_reason` MUST indicate the unknown-project fallback

#### Scenario: Redaction hit downgrades classification

- **WHEN** a session would otherwise be `public` but has any redaction hit
- **THEN** the final inbox artifact MUST be classified `private`

### Requirement: Policy audit and ledger records

Stage 2 SHALL record session-level policy summaries in the importer ledger and rule-level events in `~/.agents/memory/runtime/audit/policy.jsonl`. Both record types MUST include `session_ref`, `policy_version`, and `effective_policy_hash`. Audit records MUST include boundary, component, rule ID, detector, line number when available, and action. Audit and ledger records MUST NOT contain matched secret text or original line content.

#### Scenario: Audit contains rule metadata but no secret

- **WHEN** a redaction rule matches a token fixture
- **THEN** `policy.jsonl` MUST contain the rule ID, detector, boundary, action, and line number
- **THEN** `policy.jsonl` MUST NOT contain the matched token or original line text

### Requirement: Policy failure behavior

Stage 2 SHALL treat redaction failures at `external_to_raw` and `raw_to_distilled` as fail-closed with retry. Retry exhaustion MUST write only a metadata failure stub under `runtime/queue/_failed/`, unlink the queue payload, avoid publishing inbox output, and write `policy-error` to the ledger when the ledger is available. If the ledger is unavailable, the failure stub MUST say `ledger_status: unavailable` and the component MUST write a best-effort warning to `~/.agents/memory/log/policy.log`. Classification failures MUST fail open with `private` fallback and warning.

#### Scenario: Gitleaks missing fails closed

- **WHEN** gitleaks is enabled but unavailable
- **THEN** `raw_to_distilled` MUST retry according to `boundaries.yaml`
- **THEN** retry exhaustion MUST NOT write an inbox artifact
- **THEN** `_failed/` MUST contain only metadata stub fields, not the original payload

#### Scenario: Ledger unavailable does not claim policy-error was recorded

- **WHEN** a fail-closed policy error occurs and ledger append fails after retry
- **THEN** the failure stub MUST include `ledger_status: unavailable`
- **THEN** no requirement MAY claim a ledger `policy-error` entry exists for that event

### Requirement: Local override and dry-run policy workflow

Stage 2 SHALL support audited local override through `~/.config/paulshaclaw/policy.override.yaml`. Overrides MAY disable rules globally, disable rules for specific sessions, append local regex rules, append local classification rules, and override project defaults. Stage 2 SHALL provide `psc memory dry-run-policy <session-id>` that reports rule IDs, detector, line number, action, classification result, and effective policy hash without writing inbox output or printing matched strings.

#### Scenario: Rule disabled for one session

- **WHEN** local override disables `rule-x` for `session-a`
- **THEN** dry-run for `session-a` MUST report `rule-x` as skipped
- **THEN** dry-run for another session MUST still apply `rule-x`
- **THEN** audit output MUST include an override event without secret text

### Requirement: Consumer policy API enforcement

Stage 2 SHALL provide `paulshaclaw.memory.policy` as the only supported policy execution API. Memory consumers MUST NOT parse policy YAML directly, implement their own detector, or write policy audit records by hand. The repository SHALL include CI lint that fails when a memory consumer writes or emits memory across a declared boundary without calling the policy boundary API.

#### Scenario: Consumer bypass is caught by lint

- **WHEN** a Python memory consumer fixture writes to a memory boundary without calling `paulshaclaw.memory.policy`
- **THEN** `paulshaclaw/memory/lint/policy_consumer_lint.py` MUST exit non-zero

### Requirement: Canonical agent memory tree

Stage 2 SHALL provision `~/.agents/memory/` as the canonical agent memory substrate, fully disjoint from any Obsidian vault (`~/notes/`). The tree MUST contain `inbox/{sessions,plans,research,reports}/<tool>/<YYYY-MM-DD>/`, `work-centric/`, `knowledge/`, `runtime/{queue,queue/_failed,locks,ledger,indexes}/`, `log/`, `hooks/`, and `archive/queue/<YYYY-MM>/`. Directory mode MUST be 0700. `work-centric/`, `knowledge/`, and `runtime/indexes/` MUST be created as empty placeholders in this MVP; only `inbox/`, `runtime/queue*`, `runtime/locks`, `runtime/ledger`, `log/`, `hooks/`, and `archive/queue/` are active write targets in the repo-local implementation.

#### Scenario: Install creates the canonical tree

- **WHEN** an operator runs `~/.agents/memory/hooks/install.sh --tree-only`
- **THEN** all directories listed above MUST exist with mode 0700
- **THEN** placeholder subtrees MUST contain a `.gitkeep` file but no other content
- **THEN** `~/notes/` MUST NOT be touched

### Requirement: Hook-based session ingestion for three CLIs

Stage 2 SHALL provide native hook integrations for Claude Code (`SessionEnd`), Codex CLI (`Stop` and `SubagentStop`), and GitHub Copilot CLI (`sessionEnd`). Hook scripts MUST be thin: they MUST write the raw payload into `~/.agents/memory/runtime/queue/` via atomic rename and fire-and-forget invoke `paulshaclaw.memory.importer.cli ingest --queue-item <path>`. Claude Code and GitHub Copilot CLI MAY use stable `<tool>__<session-id>.json` queue paths; Codex CLI MUST use a distinct per-event queue filename under `codex__<session-id>__<event-id>.json` because `Stop` and `SubagentStop` can fire multiple times within one session. Hook scripts MUST tag every payload with a `capture_scope` of `session_end`, `turn`, or `subagent`. Hook scripts MUST NOT raise to the host CLI; any failure MUST be logged to `~/.agents/memory/log/hooks.log` and the script MUST exit zero.

#### Scenario: Claude SessionEnd writes a queue payload

- **WHEN** an authorized operator finishes a Claude Code session
- **THEN** `~/.agents/memory/runtime/queue/claude-code__<sid>.json` MUST appear within the hook timeout
- **THEN** the payload MUST include `capture_scope: "session_end"`
- **THEN** `~/.agents/memory/log/hooks.log` MUST NOT contain an ERROR entry for that session

#### Scenario: Codex Stop is treated as turn snapshot

- **WHEN** Codex CLI fires `Stop` mid-session
- **THEN** the hook MUST write a distinct queue payload for that event with `capture_scope: "turn"` and `ended_at: null`
- **THEN** the hook MUST NOT treat the event as session termination

#### Scenario: Copilot sessionEnd renames camelCase keys

- **WHEN** Copilot CLI fires `sessionEnd` with payload keys `sessionId`, `timestamp`, `cwd`, `reason`
- **THEN** the hook MUST normalize `sessionId` to `session_id`
- **THEN** the hook MUST supplement missing transcript fields by reading `~/.copilot/history-session-state/session_<sid>_*.json`

### Requirement: Content-hash and completeness idempotency

Stage 2 SHALL deduplicate session imports using `idempotency_key = "<source_agent>:<source_session>"`. The importer MUST compute `content_hash = sha256(canonical_json((session_id, capture_scope, turn_count, ended_at, sorted(touched_files), len(user_prompts))))` and `completeness = (scope_rank, turn_count, len(touched_files), len(user_prompts))` where `scope_rank` maps `{turn:0, subagent:0, session_end:1, watcher_final:2}`. For each incoming payload, after acquiring a `flock` on `runtime/locks/<key>.lock`, the importer MUST compare against the last ledger record for that key and resolve to exactly one of these statuses: `written`, `hash-duplicate`, `updated`, or `stale-skip`. Every decision MUST append a record to `~/.agents/memory/runtime/ledger/import.jsonl`.

#### Scenario: Higher completeness yields updated

- **WHEN** the importer processes a payload whose `completeness` is strictly greater (per Python tuple ordering) than the recorded entry
- **THEN** the importer MUST overwrite the inbox file
- **THEN** the ledger MUST receive an entry with `status: "updated"` including `from_completeness` and `to_completeness`

### Requirement: Project identity resolution with longest-prefix

Stage 2 SHALL resolve each session payload to a project identity using `~/.agents/config/projects.yaml`. Resolution MUST attempt, in order: (1) longest-prefix match of payload `cwd` against any project's `roots`; (2) longest-prefix match of explicit git toplevel against `roots`; (3) normalized match of remote URLs against `remotes`. If no rule hits, the importer MUST set `project: _unknown` and continue without raising. On alias collision, the first definition in `projects.yaml` wins and a WARN entry MUST be emitted through the importer logger.

#### Scenario: Monorepo child wins over parent

- **WHEN** `projects.yaml` declares both `monorepo` with root `/repo` and `monorepo-web` with root `/repo/web`, and the payload `cwd` is `/repo/web/src`
- **THEN** the resolver MUST return `monorepo-web`

### Requirement: Frontmatter contract for inbox entries

Stage 2 SHALL produce every inbox markdown file with a YAML frontmatter block whose required fields match `docs/research/02.obs-auto-moc-memory-dream-mode-24-7-service-notes-.md` lines 220–234, aligned with Stage 3 frontmatter. The MVP MUST NOT introduce new frontmatter fields beyond that contract. Missing best-effort fields MUST appear as deterministic fallback scalars (for example `_unknown`) or empty collections, never as `null` or as missing keys.

#### Scenario: Lint passes on repo-local fixtures

- **WHEN** an operator runs `paulshaclaw/memory/lint/frontmatter_lint.py` over importer output produced from the repo-local fixture set
- **THEN** the lint MUST report zero failures

### Requirement: Atomizer post-import promotion pipeline

Stage 2 SHALL provide a deterministic `atomizer` component that promotes records along `inbox → knowledge` as an independent post-import step. The atomizer MUST NOT modify the Stage 2 importer (`paulshaclaw.memory.importer`); it MUST only read importer output from the raw layer and consume it. Promotion MUST run as two independently re-entrant passes: a `split_pass` (raw session → deterministic fragments) and a `promote_pass` (fragments → knowledge slices). Each pass MUST derive its work-list from the filesystem plus the processing ledger so a crash between passes resumes safely on the next run.

#### Scenario: Importer is untouched

- **WHEN** a reviewer inspects the atomizer change
- **THEN** no file under `paulshaclaw/memory/importer/` MAY be modified
- **THEN** the atomizer MUST consume raw session documents written by the importer without altering importer code or output paths

#### Scenario: Passes are re-entrant

- **WHEN** `split_pass` has written fragments and recorded `state=split` but `promote_pass` has not run
- **THEN** a subsequent run MUST complete `promote_pass` for that session without re-splitting

### Requirement: Deterministic structural splitter

Stage 2 SHALL split each raw session document into fragments using deterministic structural boundaries (turn, heading, artifact markers) configured in `atomizer.yaml`. The splitter MUST be a pure function of `(session body, config)` with no LLM call, no randomness, and no wall-clock dependence. Fragment order and `fragment_index` MUST be deterministic. An empty or whitespace-only session MUST yield zero fragments without error.

#### Scenario: Same input yields same fragments

- **WHEN** the splitter runs twice over identical input and config
- **THEN** it MUST return identical fragments in identical order

#### Scenario: Oversize fragment is bounded

- **WHEN** a structural fragment exceeds `split.max_fragment_chars`
- **THEN** the splitter MUST further split it deterministically rather than emit an unbounded fragment

### Requirement: Per-session LLM semantic promoter

Stage 2 SHALL define the `Promoter` interface at session scope: `promote(fragments, config) -> list[Slice]`. Stage 2 SHALL provide an `LLMPromoter` that may merge multiple fragments into one slice or split one fragment into several, while preserving the deterministic `IdentityPromoter` under the same per-session signature. The splitter, ledgers, frontmatter builder, and flow-through MUST remain reusable across both promoters.

#### Scenario: IdentityPromoter remains 1:1 under per-session signature

- **WHEN** `IdentityPromoter.promote(fragments, config)` is called
- **THEN** it MUST return exactly one slice per input fragment

#### Scenario: LLM promoter may merge fragments

- **WHEN** the LLM promoter promotes a session whose fragments describe one concept across two fragments
- **THEN** it MAY return a single slice whose `source_fragment_indices` lists both fragments

### Requirement: Configurable agent-exec backend

Stage 2 SHALL drive the LLM promoter through a configurable `agent_exec` backend that invokes a one-shot subprocess command (default `scripts/claude-gemma4`, a local model). The backend MUST NOT require an API key or per-token billing; authentication, if any, is the invoked agent's responsibility. The agent command MUST be a configuration value and MUST be shareable with the paulshiabro `/agent` launcher configuration. The promoter MUST accept an injectable client so tests can substitute a fake without a real model.

#### Scenario: Agent command is configurable

- **WHEN** an operator sets `agent_exec.command` in `atomizer.yaml` or its override
- **THEN** the promoter MUST invoke that command rather than a hardcoded one

#### Scenario: Tests run without a real model

- **WHEN** the promoter is constructed with a fake agent client
- **THEN** promotion MUST complete deterministically using the fake's canned output, with no network or model dependency

### Requirement: Seed atomization skill document

Stage 2 SHALL ship a seed atomization skill document at `paulshaclaw/memory/atomizer/skills/atomize-knowledge-slice.md` that instructs the agent how to split, merge, tag, and relate session content into knowledge slices, and that declares the mandatory JSON output contract. Atomization behavior MUST live in this skill document, not be hardcoded in prompt assembly.

#### Scenario: Skill declares the output contract

- **WHEN** a reviewer reads the seed skill document
- **THEN** it MUST describe the required JSON output schema the agent must emit, including `artifact_kind`, `project`, `tags`, `body`, `source_fragment_indices`, and `relations`

### Requirement: Knowledge slice frontmatter union contract

Stage 2 SHALL produce knowledge slices whose frontmatter is the union of the Topic 4 janitor read contract and the Stage 3 frontmatter schema, plus a Stage-2-owned `tags` field. Each slice frontmatter MUST pass `paulshaclaw.lifecycle.schema.validate_frontmatter` and MUST also expose the Topic 4 fields (`memory_layer=knowledge`, `source_agent`, `captured_at`, `provenance`, `supersedes`). The atomizer MUST assign `slice_id`, `artifact_kind`, `checksum`, and `supersedes` deterministically and MUST NOT extend or redefine the Stage 3 required frontmatter schema. `checksum` MUST equal `sha256(slice body)`.

#### Scenario: Slice passes Stage 3 gate

- **WHEN** a knowledge slice produced by the atomizer is fed to `python3 -m paulshaclaw.lifecycle.gate`
- **THEN** validation MUST pass

#### Scenario: Invalid slice fails closed

- **WHEN** a fragment cannot be mapped to a valid `artifact_kind` and a slice would fail frontmatter validation
- **THEN** the slice MUST NOT be written to `knowledge/`
- **THEN** the session MUST remain in `state=split` and a warning MUST be logged

### Requirement: LLM output contract and slice assembly

Stage 2 SHALL require the LLM promoter to return a JSON array of slice proposals, each with `title`, `artifact_kind` (a Stage 3 `ARTIFACT_KIND`), `project` (a known project or `_unknown`), `tags`, a non-empty `body`, `source_fragment_indices`, and `relations`. Stage 2 MUST parse and schema-validate this output and MUST fail closed on any violation. Each accepted proposal MUST become a slice whose frontmatter is the Topic 4 ∪ Stage 3 union plus `tags`, whose `checksum` equals `sha256(body)`, and whose `slice_id` is content-derived from the session identity and body.

#### Scenario: Invalid output fails closed for the whole session

- **WHEN** the agent returns malformed JSON, an out-of-range `artifact_kind`, an unknown `project`, or an empty `body`
- **THEN** no knowledge slice MAY be written for that session
- **THEN** the session MUST remain in `state=split` with a warning, for retry on the next run

### Requirement: Flow-through with archive retention

Stage 2 SHALL keep working layers lean by moving consumed inputs out of the working layer into `archive/`, not by deleting them. After `split_pass`, the raw session MUST be moved to `archive/sessions/<YYYY-MM>/`. After `promote_pass`, the fragments MUST be moved to `archive/fragments/<YYYY-MM>/`. The raw layer MUST NOT retain processed sessions and `inbox/_slices/` MUST NOT retain promoted fragments, while the original content MUST remain recoverable under `archive/`.

#### Scenario: Working layers are emptied, archive retains evidence

- **WHEN** a session has completed both passes
- **THEN** the raw layer MUST NOT contain that session and `inbox/_slices/` MUST NOT contain its fragments
- **THEN** `archive/sessions/` and `archive/fragments/` MUST contain the consumed inputs

### Requirement: Semantic relations and tags

Stage 2 SHALL record LLM-inferred semantic relations as new edge types in `runtime/ledger/relations.jsonl`: `relates_to` (slice to slice) and `mentions` (slice to `entity:<NAME>`), in addition to the deterministic derivation edges. A `relates_to` whose target cannot be resolved within the promotion batch MUST be skipped with a warning rather than failing the session. Slice tags MUST be stored in the Stage-2-owned `tags` frontmatter field and MUST NOT extend the Stage 3 required schema.

#### Scenario: Dangling relation is skipped, not fatal

- **WHEN** a proposal's `relates_to` target title does not match any slice in the same batch
- **THEN** that edge MUST be skipped with a warning
- **THEN** the remaining slices and edges MUST still be written

### Requirement: Processing ledger and relations

Stage 2 SHALL record every processed session in an append-only processing ledger at `runtime/ledger/processing.jsonl` keyed by `<agent>:<session>`, with states `split` (deterministic analysis done, in process) and `promoted` (atomized, processed). A session with no ledger entry MUST be treated as not-yet-processed. Stage 2 SHALL also record derivation and semantic edges in an append-only `runtime/ledger/relations.jsonl` with edge types `fragment_of`, `promoted_to`, `distilled_from`, `supersedes`, `relates_to`, and `mentions`, with nodes namespaced `session:`/`fragment:`/`slice:`. Both ledgers MUST stamp each record with the injected scan `now` (not wall-clock) and the `atomizer_config_hash`, MUST be append-only, and MUST NOT store raw record body content. The `promoted` ledger record for LLM promotion MUST include `promoter`, `model`, and `skill_hash`.

#### Scenario: Processing state is queryable

- **WHEN** a session has been split but not promoted
- **THEN** the processing ledger fold MUST report its state as `split`

#### Scenario: Slice traces back to its session

- **WHEN** a knowledge slice exists
- **THEN** `relations.jsonl` MUST contain a `distilled_from` edge from that slice to its origin `session:<agent>:<sid>`

#### Scenario: Promoted record is traceable

- **WHEN** the LLM promoter promotes a session
- **THEN** the `processing.jsonl` `promoted` record MUST include `promoter`, `model`, and `skill_hash`

### Requirement: Frozen LLM output and crash-resume determinism

Stage 2 SHALL freeze a session's LLM output at first promotion so the non-deterministic step is idempotent on resume. The raw agent output MUST be cached at `runtime/cache/atomize/<session_key>__<fragments_hash>.json`; a subsequent promotion of the same session and fragments MUST reuse the cache rather than re-invoking the agent. A corrupt cache entry MUST be treated as a miss (re-invoke) and MUST NOT fail the run. Successful promotion MUST clear the session cache after archiving fragments.

#### Scenario: Resume reuses cached output

- **WHEN** a promotion is interrupted after the agent call but before the `promoted` ledger record
- **THEN** the next run MUST reuse the cached agent output and MUST NOT call the agent again for that session

### Requirement: Deterministic atomizer execution and fail modes

Stage 2 atomizer execution MUST be deterministic given `(records, ledgers, config, now)` once any LLM output for a session has been frozen in cache: no randomness beyond the first agent invocation, injected `now`, and a deterministic `atomizer_config_hash` over the effective config. Config load failure or unsupported `schema_version` MUST fail closed (abort, no writes). A corrupt `processing.jsonl` or `relations.jsonl` line MUST fail closed for the affected pass. A single unparseable raw session MUST be skipped with a warning without aborting the run. Any promoter failure or schema violation during promotion MUST leave the session in `state=split`.

#### Scenario: Unsupported config version fails closed

- **WHEN** `atomizer.yaml` declares an unsupported `schema_version`
- **THEN** the atomizer MUST abort without writing fragments, slices, or ledger entries

#### Scenario: One bad session does not abort the run

- **WHEN** a single raw session document has unparseable frontmatter
- **THEN** that session MUST be skipped with a warning
- **THEN** other sessions MUST still be processed

### Requirement: Redaction trust boundary for distilled output

Stage 2 LLM promotion MUST treat its input fragments as already redacted at the Topic 8 `raw_to_distilled` boundary and MUST NOT re-scan slice bodies for secrets in this change. This limitation MUST be documented; a future `distilled_to_canonical` policy pass is the place to add output-side scanning. Logs MUST NOT contain raw agent output or session body content.

#### Scenario: Logs never contain model output

- **WHEN** the promoter logs a failure
- **THEN** the log entry MUST NOT contain the raw agent output or any session body content
- **THEN** it MUST contain only the failure category, `session_key`, and skill/config hashes
