## Context

Issue #174. The Stage 2 dream loop (`scripts/start.sh:184-196`, hourly, `--promoter llm`) promotes `split` sessions via `LLMPromoter` + `CachingAgentClient`. The cache key is `<agent>:<session>__<sha256(fragments)>` (`llm_promoter.py:47-52`) — stable across runs for a stuck session because fragment files never change. `run_cached` (`agent_exec.py:83-95`) freezes raw output before validation, and the pipeline's `PromoteError` handler (`pipeline.py:405-409`) never clears the cache, so a single bad LLM output deterministically re-fails every hour, forever. Audit replay of `runtime/cache/atomize/` showed 45/45 backlogged sessions with poisoned caches: 26 empty-array (`[]`, a legitimate "no knowledge" answer), 14 no-JSON chatter, 2 multiple JSON arrays, 3 schema drift. Meanwhile `dream/orchestrator.py::_run_pass` drops all warning text, so `dream.jsonl` showed only `skipped: 45`, `errors: []`, `status: partial`.

All findings below follow the audit's **VERIFY corrections** where they overrode the original recommendation (notably: empty-array fix must be an early `return []`, not removal of the non-empty check; the pipeline needs no change for `promoted=[]`).

## Goals / Non-Goals

**Goals:**

- A promotion failure must not permanently freeze a session: the poisoned cache is cleared so the next run re-invokes the LLM.
- gemma4's legitimate `[]` answer becomes a terminal state: `state=promoted`, `slices=0`, fragments archived, cache cleared.
- Promotion failures become observable: warning text reaches the dream ledger record.
- LLM re-invocation after a cached bad output is bounded (no unbounded hourly LLM spend on chatter-prone sessions that already produced replayable output).

**Non-Goals:**

- No validate-before-cache-write change in `agent_exec.py` (bigger diff; clearing-on-failure achieves recovery and keeps evidence for triage until the retry decision).
- No prompt/skill hardening for the chatter sessions (tracked as an open question).
- No janitor path for the 31 orphan cache files of non-backlog sessions (follow-up).
- No relaxation of the multiple-JSON-arrays parser rule.
- The one-time deletion of the 45 backlog caches is ops, not code (see plan Deployment/Ops notes); with cache clearing in place it only accelerates recovery by one dream cycle.

## Decisions

### Clear the poisoned cache in the pipeline's PromoteError path (LLM promoter only)

`pipeline.py` already owns success-path cache clearing (`:381`, `:498`), so failure-path clearing lives there too, symmetric and testable — but only for failures that actually materialized cached raw output. In the `except PromoteError` handler of `_promote_pass` (non-dry-run branch), compute the session cache key and inspect the corresponding `.json`: if it exists, this was a content attempt and the cached bad output should be cleared/re-budgeted; if it does not exist, the failure came from the transport path (`AgentExecError`) and both cache / retry state stay untouched. Identity promoter failures are untouched. The dry-run branch now returns before the live event loop, so both newly split previews and existing split backlog stay mutation-free by design.

### Empty proposal array is a valid terminal result — early `return []` in `_parse_proposals`

Per VERIFY correction #5: removing only the non-empty check at `llm_output.py:235-236` would let `data=[]` fall through the build loop into the `no salvageable proposals` raise at `:249-250`. The fix is an early `return []` at the top of `_parse_proposals` when `data` is an empty list. Downstream: `parse("[]")` returns `[]`; `LLMPromoter.promote` returns `[]`; `_promote_pass` with `promoted=[]` already runs its validation/write loops zero times and reaches `append_state(state="promoted", slices=0)` + fragment archive + cache clear — verified against current code, so **no pipeline change**, only a regression test to lock it.

Known behavior change accepted: raw output containing BOTH an empty array and a non-empty valid array previously returned the non-empty one (the empty one raised and was swallowed as `last_error`); it now raises `multiple valid JSON arrays`. This is rare (the 2/45 multiple-array sessions had multiple non-empty arrays and already failed), and with failure-path cache clearing the session retries instead of freezing.

### Surface warnings into the dream record, bounded

`_run_pass` adds `warnings` (first 10 strings, each truncated to 500 chars) and `warnings_total` to the pass summary **only when the warnings list is non-empty**, preserving the exact-equality assertions of existing orchestrator tests for clean passes. Warning strings come from pipeline/janitor/moc code and contain exception class/schema messages, never raw prompts or LLM output bodies, so the existing redaction property (`test_failure_record_redacts_exception_message`) is preserved. The summary dict is copied before mutation so callers' `result["summary"]` is not aliased.

### Bounded retry via a `.retries` sidecar counter; exhausted budget parks on the poisoned cache

State must survive across dream runs; the smallest persistent store aligned with the failure unit is a sidecar file `runtime/cache/atomize/<cache_key>.retries` holding an integer. On `PromoteError` (LLM promoter, non-dry-run), first resolve the cache path. If the `.json` exists, the failure counts as a content attempt: increment the counter, then clear the cache only while `attempts <= 5` (`_LLM_PROMOTE_MAX_RETRIES = 5`, module constant — config plumbing rejected to keep the boundary small). Once `attempts > 5`, the poisoned cache is deliberately retained: subsequent runs replay it and fail at parse time without any LLM call — the cache becomes a cheap parking state, still warned about every run (and now visible in the dream record). If the `.json` does not exist, the failure came from the transport path; the warning stays truthful (`transport failure; no cache written; retry budget unchanged`) and the sidecar is left untouched. Counter paths are validated with the same `is_valid_cache_key` + parent-directory containment used by `_clear_cache_key` (hostile ledger/key hardening precedent). On success, `_clear_cache_key` also removes the sidecar so a later identical session starts with a fresh budget. Total LLM calls per content-stuck session: at most 6 (initial + 5 retries after the first cached bad output); pure transport outages keep the pre-PR natural retry behavior because there is no cheap parking state without cached output.

Sequencing note: a poisoned cache left by the pre-fix code counts its first post-deploy replay as attempt 1 and is then cleared — the backlog therefore self-heals without ops action; the ops deletion in the plan merely skips that one replay cycle.

## Risks / Trade-offs

- **Chatter sessions may burn their whole retry budget** (LLM never produces valid JSON). Accepted: bounded at 6 calls, then cheap parking; prompt hardening is a follow-up. Manual reset = delete the `.json` + `.retries` pair.
- **Transport outages are still retried every dream run.** Accepted: without cached output there is nothing to park on, so we preserve the pre-PR natural retry semantics instead of fabricating budget usage.
- **`warnings` enlarge dream.jsonl records.** Bounded: ≤10 entries × ≤500 chars per pass.
- **Retained poisoned cache after budget exhaustion looks like the old bug.** Distinguished by the `.retries` sidecar and by the warning text in the dream record; documented in the plan.
- **Pipeline-level Phase-2 validation failures (`pipeline.py:412-419`) do not clear the cache.** For `LLMPromoter` these are practically unreachable (promote() already validates every slice and raises `PromoteError`, which is covered); left out to keep the diff minimal.

## Migration Plan

| Step | Action |
|---|---|
| 1 | Land code + tests; CI green (`python -m pytest tests/ paulshaclaw/memory/tests/ -q`). |
| 2 | Merge PR; runtime picks up working tree via `PYTHONPATH` on next dream run (no hook reinstall — none of the changed files are hook scripts). |
| 3 | (Ops, optional accelerator) delete the 45 backlog sessions' cache files per the plan's Deployment/Ops notes. |
| 4 | Observe `runtime/ledger/dream.jsonl`: `atomize.skipped` should fall from 45 as empty-array sessions collapse to `promoted/slices=0` and retryable sessions drain; warnings text now present in `passes.atomize.warnings`. |

Rollback: revert the commit; behavior returns to warn-and-freeze. `.retries` sidecar files are inert to the old code (glob patterns target `*.json`).

## Open Questions

1. Do the 14 chatter sessions ever produce valid JSON within 5 retries, or do they need prompt/skill hardening? (Watch dream.jsonl after deploy; follow-up issue if they all exhaust the budget.)
2. Janitor cleanup for orphan cache/`.retries` files of already-promoted or long-dead sessions (31 orphans observed) — separate change.
3. Should the multiple-JSON-arrays rule prefer the single non-empty array when exactly one exists? Deferred; recoverable now via retry.
