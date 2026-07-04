## Why

The 2026-07-02 memory audit (issue #174) confirmed that 45 sessions are permanently stuck in `split` state (504 fragments held back from `knowledge/`), with a 79% stuck rate for new sessions since 06-30 and the backlog diverging by +11~21 per day. Root cause is a poisoned-cache loop with no terminal state for "no knowledge" sessions:

1. `paulshaclaw/memory/atomizer/agent_exec.py:93-94` — `CachingAgentClient.run_cached` writes raw gemma4 output to `runtime/cache/atomize/` **before** any schema validation, so one bad output is frozen forever.
2. `paulshaclaw/memory/atomizer/pipeline.py:405-409` — the `PromoteError` path only appends a warning and `continue`s; the cache is never cleared on failure (`_clear_cache_key` is only called on success paths `:381`/`:498`, and `LLMPromoter.clear_cache_for_fragments` has zero callers). The cache key is `session + fragments hash`, stable across runs, so every hourly dream run deterministically replays the same poisoned cache.
3. `paulshaclaw/memory/atomizer/llm_output.py:235-236` — `_parse_proposals` raises on an empty JSON array. 26 of the 45 stuck sessions are gemma4 legitimately answering `[]` (no extractable knowledge), but that valid answer is treated as a hard error, so a "no knowledge" session has no terminal state.
4. `paulshaclaw/memory/dream/orchestrator.py:36-49` — `_run_pass` discards all warning text, keeping only `skipped` counts, so the whole failure mode was invisible in `dream.jsonl` (`status=partial`, `errors=[]`).

## What Changes

- `atomizer/pipeline.py`: on `PromoteError` for an `LLMPromoter`, clear that session's fragments cache so the next dream run genuinely re-invokes the LLM instead of replaying the poisoned output (transient failures self-heal).
- `atomizer/llm_output.py`: `_parse_proposals` returns `[]` early for an empty JSON array (per the audit's VERIFY correction: merely removing the non-empty check is not enough — `data=[]` would fall through to the `no salvageable proposals` raise at `:249-250`). The pipeline already handles `promoted=[]` correctly (`state=promoted`, `slices=0`, fragments archived, cache cleared) — no pipeline change needed, but a regression test locks that behavior.
- `dream/orchestrator.py`: `_run_pass` records the first 10 warning strings (each truncated) plus a `warnings_total` count into the per-pass summary of the dream record, ending the silence.
- `atomizer/pipeline.py`: bounded retry budget — a `.retries` sidecar counter next to the cache file caps LLM re-invocations per stuck session (budget 5); once exhausted the poisoned cache is retained on purpose so subsequent runs fail cheaply (replay + parse) without further LLM calls.
- Existing tests asserting the old behavior are updated: `test_llm_output.py::test_empty_array_raises`, `test_llm_promoter.py::test_empty_output_fails_closed`, `test_atomizer_pipeline.py::test_llm_empty_output_leaves_session_split_without_archiving_fragments`.
- One-time recovery of the 45-session backlog cache files is an ops action documented in the plan's Deployment/Ops notes — it is NOT part of this change's code.

## Capabilities

### New Capabilities

None. This change extends the existing `stage2-memory-governance` capability with promotion failure-recovery requirements.

### Modified Capabilities

- `stage2-memory-governance`: Add promotion cache recovery on failure, empty-proposal terminal state, bounded LLM retry budget, and dream-record warning surfacing requirements.

## Impact

- **Affected code**:
  - `paulshaclaw/memory/atomizer/pipeline.py` (PromoteError path + retry counter helpers + success-path counter cleanup)
  - `paulshaclaw/memory/atomizer/llm_output.py` (`_parse_proposals` empty-list early return)
  - `paulshaclaw/memory/dream/orchestrator.py` (`_run_pass` warning surfacing)
- **Affected tests**: `paulshaclaw/memory/tests/test_atomizer_pipeline.py`, `test_llm_output.py`, `test_llm_promoter.py`, `test_dream_orchestrator.py`.
- **Not touched**: `agent_exec.py` (validate-before-cache-write was considered and rejected — clearing on failure achieves the same recovery with a smaller diff and keeps the cache useful for post-mortems until the retry decision), hook scripts, CI workflows, `atomizer.yaml`.
- **Runtime**: dream loop runs the working tree via `PYTHONPATH` (`scripts/start.sh`), so merge + pull deploys; no hook reinstall required.
- **Expected effect**: 26/45 backlogged sessions reach `promoted`/`slices=0` on the next dream run (their cached `[]` replays now parse successfully); the remaining 19 self-heal via cache clearing + bounded retry, capped at 6 LLM calls each.
