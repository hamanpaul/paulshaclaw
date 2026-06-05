# Design — Stage 2 T6 wake-up + PreCompact capture

Full design: `docs/superpowers/specs/2026-06-05-stage2-t6-wakeup-design.md`. Implementation plan: `docs/superpowers/plans/2026-06-05-stage2-t6-wakeup.md`. This mirrors the binding decisions.

## Architecture

`memory/wakeup/` is the CLI-agnostic core: `build_brief(memory_root, project, *, now, k=8, char_budget=8000) -> str` assembles a brief from existing data only (T7 `knowledge/<project>-moc.md` + `lifecycle`/`retrieval_set` ledgers). `psc memory wakeup` exposes it. Four thin hooks call into it (session-start) or into the existing importer (precompact). Runs at the CLI/hook boundary; the builder itself is pure and read-only.

## Components
- `wakeup/builder.py` — brief assembly: MOC body + recent-K active pointers, budget truncation (Map tail trimmed; Recent preserved).
- `wakeup/cli.py` — `psc memory wakeup --project|--cwd --memory-root --k --char-budget --now`.
- `hooks/_wakeup_common.py` — shared: `memory_root`, `read_payload`, `log_warn`, `compute_brief`, `write_queue_payload`, `fire_importer`.
- `hooks/{claude,copilot}_session_start.py` — resolve project from `cwd`, emit `additionalContext`.
- `hooks/{claude,copilot}_precompact.py` — write `capture_scope=pre_compact` queue payload, fire importer.

## Boundaries (zero duplication)
- project ← `importer/project_resolver.resolve_project(cwd=...)` (returns slug or `_unknown`).
- recency ← `lifecycle.fold_lifecycle` (`last_event_ts`, `record_id == slice_id`) ∩ `retrieval_set.active_record_ids`.
- map ← T7 `knowledge/<project>-moc.md` (frontmatter stripped).
- capture ← existing importer (`cli ingest`), new `capture_scope="pre_compact"`, `_SCOPE_RANK["pre_compact"]=0`.

## Data model
- Brief markdown: `# Memory wake-up — <project>` / `## Map` (MOC body, tail-truncated to budget) / `## Recent` (`- [[<stem>]] — <summary> (<ts>)`, newest first, active-only, ≤K).
- Empty brief when `project == _unknown` or no MOC and no recent slices.

## Guardrails
- Fail-open: session-start hooks always emit valid JSON + exit 0; precompact hooks never raise/block compaction.
- Deterministic: `now` injected; recent ordering by `last_event_ts` (ISO8601 lexical) with `slice_id` tie-break.
- Read-only wake-up: no knowledge writes, no ledger writes.
- Budget: Recent reserved before Map; only Map tail trimmed with `…(truncated)`; final brief hard-capped at `char_budget`.

## Testing
TDD with fixtures, no real CLI/LLM: builder (map+recent order, active-only, budget, empty, deterministic), CLI (explicit/cwd/unknown), session-start hooks (additionalContext shape + fail-open), precompact hooks (pre_compact payload + fail-open), scope-rank.
