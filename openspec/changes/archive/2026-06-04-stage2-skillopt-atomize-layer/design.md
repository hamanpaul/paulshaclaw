# Design — Stage 2 paulshaclaw SkillOpt atomize layer

Full design: `docs/superpowers/specs/2026-06-04-stage2-skillopt-atomize-layer-design.md`. This file mirrors the decisions that bind the OpenSpec delta.

## Architecture

New code module `paulshaclaw/memory/skillopt/` (NOT a skill), parallel to `atomizer/`, `importer/`, `dream/`, `moc/`. It vendors the evolve generic SkillOpt loop and supplies atomize-specific hooks, then calls `optimize_skill` on `atomizer/skills/atomize-knowledge-slice.md`. Runs as an offline CLI (`psc memory skillopt run`); not wired into the dream loop in this change.

```
paulshaclaw/memory/skillopt/
├── loop.py                   # vendor of evolve skillopt.py — optimize_skill(), behavior unchanged
├── optimizer_acp.py          # vendor — make_acp_optimizer (codex ACP bounded edit)
├── codex_exec_acp_adapter.py # vendor — codex ACP caller (optimizer dependency)
├── rollout.py                # make_atomize_rollout: inject skill_text → LLMPromoter → slices
├── scorer.py                 # structural_score (train) + make_hybrid_score (val gate)
├── valset.py                 # build_valset: inbox → stratify by project → train/val + reference gold
└── cli.py                    # driver; psc memory skillopt run
```

## Model roles (all injectable → fakes in tests)
- rollout = gemma4 via `agent_exec` running existing `LLMPromoter` with the candidate `skill_text`.
- optimizer = codex ACP (vendored) proposing one bounded skill edit.
- judge = injected agent_client (stronger model recommended) scoring atomization quality at the val gate.

## Boundaries (zero duplication)
- session scan + project resolution (incl. cross-folder-same-project via `projects.yaml` roots/remotes) → owned by importer (T2); SkillOpt reads inbox + `project` frontmatter, never re-scans or re-resolves.
- atomize rollout → owned by atomizer (T3/T3.2); SkillOpt injects `skill_text`, never forks the splitter.
- LLM-judge scores atomization quality ONLY (granularity / concept boundary / one-concept-per-slice / relations). Project assignment is NOT a judge task.

## Data model
- train item = generic `{"id": "<session_id>#<fragment_index>", "input": [Fragment...], "gold": {"project": slug}}`.
- val item = generic `{"id": "<session_id>#<fragment_index>", "input": [Fragment...], "gold": {"project": slug, "reference_slices": [{title,body,tags}...]}}`.
- validation-only `reference_slices` come from `~/notes` semantic content (ignore Obsidian frontmatter); they are judge rubric, not a 1:1 target; empty when no domain match (judge falls back to skill principles).
- train/val split = per project, deterministic via `sha256("<session_id>#<fragment_index>")` mod → 20% val / 80% train; reproducible, no wall-clock, no RNG.

## Scorer
- structural_score (deterministic): weighted granularity balance, concept-boundary clarity, one-concept-per-slice, relation presence. Used for train failure ranking and does not depend on `~/notes`.
- hybrid score = `α·structural + (1-α)·judge` (α default 0.4), used for the val gate. Absolute 0–1 per output → keeps the vendored loop's `score(output, gold)` contract unchanged (no pairwise).

## Guardrails (inherit generic G1–G6; add)
- L1 zero-duplication of existing capabilities. L2 judge never touches project. L3 deterministic split. L4 offline (not in dream → zero online impact).
- Empty inbox → `optimize_skill` raises `SkillOptError` (friendly CLI message). Per-project sample below threshold → all-to-train (avoid single-sample val noise). Any model timeout/exception → generic fail-closed (skill unchanged, sanitized record).

## Testing
TDD, inject fakes (no real codex/gemma4). Cover: vendored loop parity, rollout skill_text injection, structural signals + hybrid α, deterministic stratified split, CLI wiring + `--dry-run` + empty-inbox error.
