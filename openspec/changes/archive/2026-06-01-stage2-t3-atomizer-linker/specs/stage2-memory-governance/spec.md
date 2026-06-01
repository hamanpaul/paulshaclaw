## ADDED Requirements

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

### Requirement: Promoter interface and 1:1 MVP

Stage 2 SHALL define a `Promoter` interface that maps one fragment to one or more knowledge slices. The MVP implementation MUST be `IdentityPromoter`, producing exactly one knowledge slice per fragment with no semantic splitting, merging, relation inference, or tagging. The interface MUST be the only seam a future LLM promoter (T3.2) replaces; the splitter, ledgers, frontmatter builder, and flow-through MUST be reusable without change.

#### Scenario: MVP promotes one-to-one

- **WHEN** `IdentityPromoter` promotes a fragment
- **THEN** it MUST produce exactly one knowledge slice carrying `distilled_from` and `fragment_ref`

### Requirement: Knowledge slice frontmatter union contract

Stage 2 SHALL produce knowledge slices whose frontmatter is the union of the Topic 4 janitor read contract and the Stage 3 frontmatter schema. Each slice frontmatter MUST pass `paulshaclaw.lifecycle.schema.validate_frontmatter` and MUST also expose the Topic 4 fields (`memory_layer=knowledge`, `source_agent`, `captured_at`, `provenance`, `supersedes`). The atomizer MUST assign `slice_id`, `artifact_kind`, `checksum`, and `supersedes` deterministically and MUST NOT extend or redefine the Stage 3 frontmatter schema. `checksum` MUST equal `sha256(slice body)`.

#### Scenario: Slice passes Stage 3 gate

- **WHEN** a knowledge slice produced by the atomizer is fed to `python3 -m paulshaclaw.lifecycle.gate`
- **THEN** validation MUST pass

#### Scenario: Invalid slice fails closed

- **WHEN** a fragment cannot be mapped to a valid `artifact_kind` and a slice would fail frontmatter validation
- **THEN** the slice MUST NOT be written to `knowledge/`
- **THEN** the session MUST remain in `state=split` and a warning MUST be logged

### Requirement: Flow-through with archive retention

Stage 2 SHALL keep working layers lean by moving consumed inputs out of the working layer into `archive/`, not by deleting them. After `split_pass`, the raw session MUST be moved to `archive/sessions/<YYYY-MM>/`. After `promote_pass`, the fragments MUST be moved to `archive/fragments/<YYYY-MM>/`. The raw layer MUST NOT retain processed sessions and `inbox/_slices/` MUST NOT retain promoted fragments, while the original content MUST remain recoverable under `archive/`.

#### Scenario: Working layers are emptied, archive retains evidence

- **WHEN** a session has completed both passes
- **THEN** the raw layer MUST NOT contain that session and `inbox/_slices/` MUST NOT contain its fragments
- **THEN** `archive/sessions/` and `archive/fragments/` MUST contain the consumed inputs

### Requirement: Processing ledger and relations

Stage 2 SHALL record every processed session in an append-only processing ledger at `runtime/ledger/processing.jsonl` keyed by `<agent>:<session>`, with states `split` (deterministic analysis done, in process) and `promoted` (atomized, processed). A session with no ledger entry MUST be treated as not-yet-processed. Stage 2 SHALL also record derivation edges in an append-only `runtime/ledger/relations.jsonl` with edge types `fragment_of`, `promoted_to`, `distilled_from`, and `supersedes`, with nodes namespaced `session:`/`fragment:`/`slice:`. Both ledgers MUST stamp each record with the injected scan `now` (not wall-clock) and the `atomizer_config_hash`, MUST be append-only, and MUST NOT store raw record body content.

#### Scenario: Processing state is queryable

- **WHEN** a session has been split but not promoted
- **THEN** the processing ledger fold MUST report its state as `split`

#### Scenario: Slice traces back to its session

- **WHEN** a knowledge slice exists
- **THEN** `relations.jsonl` MUST contain a `distilled_from` edge from that slice to its origin `session:<agent>:<sid>`

### Requirement: Deterministic atomizer execution and fail modes

Stage 2 atomizer execution MUST be deterministic given `(records, ledgers, config, now)`: no LLM, no randomness, injected `now`, and a deterministic `atomizer_config_hash` over the effective config. Config load failure or unsupported `schema_version` MUST fail closed (abort, no writes). A corrupt `processing.jsonl` or `relations.jsonl` line MUST fail closed for the affected pass. A single unparseable raw session MUST be skipped with a warning without aborting the run.

#### Scenario: Unsupported config version fails closed

- **WHEN** `atomizer.yaml` declares an unsupported `schema_version`
- **THEN** the atomizer MUST abort without writing fragments, slices, or ledger entries

#### Scenario: One bad session does not abort the run

- **WHEN** a single raw session document has unparseable frontmatter
- **THEN** that session MUST be skipped with a warning
- **THEN** other sessions MUST still be processed
