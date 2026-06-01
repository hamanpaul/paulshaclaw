## Why

Stage 2 memory has a populated `inbox/` (Topic 2 importer) and a lifecycle ledger + janitor that govern `knowledge/` (Topic 4). But `work-centric/` and `knowledge/` are still empty placeholders: nothing promotes inbox sessions into citable, governable knowledge slices. Without Topic 3, Topic 7 (retrieval) has no slices to index and no relation graph to traverse, and Topic 4's janitor has no real records to decay or reactivate.

This change adds a deterministic `atomizer` MVP that promotes records along `inbox → knowledge` as an independent post-import step, producing Stage-3-conformant knowledge slices and a derivation graph — without touching the merged importer and without any LLM dependency. The semantic split / relation / tag work is intentionally deferred to a follow-up (T3.2) behind a single `Promoter` seam.

## What Changes

- Add `paulshaclaw.memory.atomizer` package: deterministic structural `splitter`, pluggable `promoter` (MVP `IdentityPromoter`, 1:1), `slice_frontmatter` builder, two-pass `pipeline`, and `cli`.
- Add a deterministic structural splitter that segments raw session documents into fragments by turn / heading / artifact boundaries (config-driven), with no LLM and no randomness.
- Promote fragments into `knowledge/<project>/<slice_id>.md` with frontmatter that is the union of the Topic 4 janitor read contract and the Stage 3 frontmatter schema, validated against both.
- Add flow-through retention: consumed raw sessions and fragments move to `archive/` (not deleted), keeping `inbox/_slices/` and the raw layer lean while preserving provenance.
- Add `paulshaclaw.memory.ledger.processing` (`runtime/ledger/processing.jsonl`) state machine (`split`/`promoted`) keyed by `<agent>:<session>`.
- Add `paulshaclaw.memory.ledger.relations` (`runtime/ledger/relations.jsonl`) with `fragment_of` / `promoted_to` / `distilled_from` / `supersedes` edges for Topic 7 relation traversal.
- Add `psc memory atomize [--dry-run]` one-shot CLI.
- Add an atomizer dry-run guard to `stage2_integration_check.sh`.

## Capabilities

### New Capabilities

None. This change extends the existing `stage2-memory-governance` capability with the deterministic atomizer / linker promotion contract.

### Modified Capabilities

- `stage2-memory-governance`: Add post-import promotion pipeline, deterministic splitter, Promoter interface + 1:1 MVP, knowledge-slice union frontmatter contract, flow-through archive retention, processing/relations ledgers, and deterministic fail-mode requirements.

## Impact

- Affected runtime code (new): `paulshaclaw/memory/atomizer/{splitter,promoter,slice_frontmatter,pipeline,cli,config}.py`, `paulshaclaw/memory/atomizer/atomizer.yaml`, `paulshaclaw/memory/ledger/{processing,relations}.py`.
- Affected layout (new write targets): `inbox/_slices/`, `knowledge/<project>/`, `archive/sessions/`, `archive/fragments/`, `runtime/ledger/{processing,relations}.jsonl`.
- Cross-stage dependency (read-only contract): `paulshaclaw.lifecycle.schema` (`validate_frontmatter`, `compute_checksum`, `ARTIFACT_KINDS`, `PHASES`).
- Affected config: `~/.config/paulshaclaw/atomizer.override.yaml`.
- Affected CLI: `psc memory atomize`.
- Affected tests: splitter, slice_frontmatter, promoter, processing ledger, relations ledger, config, atomizer E2E (split/promote/idempotent/crash-resume/flow-through/reimport/fail-closed/dry-run), cross-stage `lifecycle.gate` conformance.
- Non-Goals: LLM semantic split / relation inference / tagging (T3.2), advanced `work-centric` aggregation/correlation, retrieval/index (T7), embedding/vector/graph, new `agy`/Gemini importer adapter (Topic 2).
