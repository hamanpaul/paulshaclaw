# Design — Stage 2 Topic 3 Atomizer / Linker (deterministic MVP)

> Canonical design: `docs/superpowers/specs/2026-05-31-stage2-t3-atomizer-linker-design.md`. This file captures the change-scoped architecture and key decisions; see the canonical spec for full detail.

## Context

- `inbox/` is populated by Topic 2; `work-centric/` and `knowledge/` are empty placeholders.
- Topic 4 already governs `knowledge/` records via a read contract (`slice_id`, `supersedes`, `source_agent:source_session`, `captured_at`, `provenance`) and the `lifecycle.jsonl` ledger.
- Stage 3 (`paulshaclaw/lifecycle/schema.py`) owns the frontmatter schema (`phase`, `project`, `slice_id`, `artifact_kind`, `version`, `created_at`, `created_by`, `source_session`, `gate_required`, `checksum`) and provides `validate_frontmatter` / `compute_checksum`.

## Key Decisions

1. **Post-import, T2 untouched.** The atomizer is a separate component that reads the importer's raw output and consumes it; the merged importer is not modified.
2. **Deterministic first, LLM later behind one seam.** MVP is fully deterministic (structural split + 1:1 promotion). The `Promoter` interface is the only seam a later LLM atomizer (T3.2: semantic split / relations / tags) replaces.
3. **Two re-entrant passes.** `split_pass` (raw → fragments) and `promote_pass` (fragments → knowledge) each derive their work-list from filesystem + processing ledger, making the pipeline crash-resumable and idempotent. Step order per item: write product → append ledger → move to archive.
4. **Flow-through with archive retention.** Consumed inputs move to `archive/` (not deleted): raw → `archive/sessions/`, fragments → `archive/fragments/`. Working layers stay lean; governance "inbox retains original" is satisfied by archive.
5. **Union frontmatter, dual validation.** Knowledge slice frontmatter = Topic 4 read contract ∪ Stage 3 required fields, validated against both. T3 assigns Stage-3-owned fields deterministically but does not extend the schema (Stage 3 `validate_frontmatter` ignores extra fields, so Topic 4 fields coexist).
6. **Deterministic identity.** `slice_id = sl-<sha256(project,agent,session,fragment_index)[:16]>`; `checksum = sha256(body)`. Re-import of the same session overwrites the same `slice_id` (update path).
7. **Two ledgers.** `processing.jsonl` is the authoritative state machine (`split`/`promoted`); `relations.jsonl` is the derivation graph for Topic 7. Both stamp the injected `now` (Topic 4 lesson: never wall-clock) and `atomizer_config_hash`.

## Component Boundaries

- `atomizer/splitter.py` — pure: `split(body, config) -> list[Fragment]`.
- `atomizer/promoter.py` — `Promoter` interface + `IdentityPromoter` (1:1).
- `atomizer/slice_frontmatter.py` — build union frontmatter, assign `slice_id`/`checksum`, map `artifact_kind`/`phase`, dual-validate.
- `atomizer/pipeline.py` — orchestrates the two passes, ledger writes, and archive moves.
- `atomizer/{config.py,atomizer.yaml,cli.py}` — config loader/hash and `psc memory atomize` entry.
- `ledger/processing.py`, `ledger/relations.py` — append-only JSONL with flock; pure `fold`/`neighbors` read APIs.

## Error / Guardrail Posture

Core state corruption (config, `processing.jsonl`, `relations.jsonl`) fails closed; single-record problems (bad raw session, unpromotable fragment) degrade with a warning and leave the session in `split` for a later retry. Knowledge slices that fail dual validation are never written. All decisions are deterministic and traceable via `atomizer_config_hash`.

## Out of Scope

LLM semantic split / relation inference / tagging (T3.2); advanced `work-centric` aggregation; retrieval/index (T7); embedding/vector/graph; new `agy`/Gemini importer adapter (Topic 2).
