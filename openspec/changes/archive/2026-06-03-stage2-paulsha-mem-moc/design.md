# Design — Stage 2 Topic 7 paulsha-mem-moc

> Canonical design: `docs/superpowers/specs/2026-06-03-stage2-paulsha-mem-moc-design.md`. This file captures the change-scoped architecture and key decisions.

## Context

- `knowledge/<project>/<slice_id>.md` slices exist (T3/T3.2) with Stage 3 ∪ Topic 4 frontmatter; `relations.jsonl` holds `relates_to`/`mentions`/`distilled_from` edges; `retrieval_set.active_records` gives the active set; the T5 dream orchestrator runs atomize → janitor.
- Original intent (`docs/research/00`): memory is Obsidian-native with `<project>-moc.md`/`common-sense-moc.md`/`wiki-moc.md`, Obsidian associations, and faceout. `obs-auto-moc` is reference-only (Stage 0 rename `obs-auto-moc → paulsha-memory`); paulshaclaw self-builds `paulsha-mem-moc`.
- sqlite3 + FTS5 confirmed available.

## Key Decisions

1. **Deterministic materializer, not a semantic engine.** T7 turns existing relations into Obsidian-native form; it does no LLM/semantic work. Entity-graph normalization (T5-C) and lineage (T5-B) are out of scope.
2. **Links in frontmatter only.** `related:`/`aliases:` in frontmatter, never body — preserves Stage 3 `checksum` and the content-derived `slice_id`. (Conflict C2.)
3. **Filename = `<title>--<slice_id>.md`.** Readable for the Obsidian graph, addressable by `slice_id`. The atomizer overwrites by `*--<slice_id>.md` glob so re-imports never duplicate a `slice_id` (the selector raises on duplicates). (Conflict C1.)
4. **MOC files carry `memory_layer: moc`.** The janitor record source and replay selector skip them so they are not mis-scanned as knowledge records. (Conflict C4.)
5. **MOC pass runs after atomize+janitor.** A third isolated dream pass; materialized links/MOC/index are regenerated each pass, so an atomize overwrite (which clears `related:`) is reconciled on the same run. (Conflict C3.)
6. **`relations.jsonl` stays the append-only source of truth.** The moc pass only reads it and materializes a regenerated view into the markdown.
7. **Faceout surfaces, never deletes.** Decayed slices are listed in `wiki-moc.md`; the lifecycle ledger owns the state; slice files and frontmatter are untouched.
8. **Lexical search via FTS5 sidecar.** `runtime/indexes/retrieval.db` rebuilt each moc pass; `psc memory search` ranks BM25 + recency + bidirectional `link_weight`, project-scopable, active-by-default.

## Component Boundaries

- `moc/naming.py` — title derivation + `<title>--<slice_id>.md` + rename/dedup.
- `moc/linker.py` — bidirectional `related:`/`aliases:` frontmatter + `link_weight`.
- `moc/moc_builder.py` — three MOC files.
- `moc/faceout.py` — decayed → wiki-moc.
- `moc/search.py` — FTS5 build + query.
- `moc/runner.py` — `run_moc` (5 steps, idempotent).
- Connected: `atomizer/pipeline.py`, `janitor/record_source.py`, `replay/selector.py`, `dream/{orchestrator,cli}.py`.

## Error / Guardrail Posture

The moc pass is an isolated dream pass: per-step best-effort, core-state corruption fails the step closed, the pass never crashes the dream run. Links never touch the body; `slice_id` is the stable identity; MOC files are excluded from knowledge scanners; `relations.jsonl` is never written; faceout never deletes; deterministic with injected `now`; no coupling to `obs-auto-moc`.

## Out of Scope

LLM/semantic work in T7; T5-C entity-graph normalization; T5-B evolution lineage; SkillOpt; wake-up bundle (Topic 6); using/coupling `obs-auto-moc`.
