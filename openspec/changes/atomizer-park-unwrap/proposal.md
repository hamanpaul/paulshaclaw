## Why

The #174 poisoned-cache fix (PR #179) drained the dream promotion backlog from 67 stuck sessions to a **park floor** (~9, of which 5 have `retries>5` and are parked) that will not reach 0. The floor's root cause is NOT the poisoned cache and NOT "sessions with no knowledge" — it is **gemma4 producing malformed output for some sessions**. #179's bounded retry budget (`_LLM_PROMOTE_MAX_RETRIES=5`) correctly parks them (retains cache, stops retrying, no infinite loop), but their knowledge never reaches `knowledge/`.

Two failure modes (instances in `runtime/cache/atomize/`):

1. **Object-wrapped array (parser-recoverable)** — `claude-code:ee5fb45b…` (fragments=9) → gemma4 returns `{"findings": []}`. `llm_output.py::_iter_json_arrays` (`:47/:54`) only recognizes a **top-level bare array** (`isinstance(candidate, list)` `:62`); `_parse_proposals` (`:233-234`) requires `isinstance(data, list)`, so an object-wrapped payload falls to `parse` (`:278`) "no JSON array found" → `PromoteError` → retry → park. Even a wrapped **empty** result `{"findings":[]}` — which should reach #179's empty-array → `slices=0` terminal state — parks because the outer layer is an object.
2. **Wrong-task prose (needs prompt hardening, not parser)** — `claude-code:1abd65d0…` (fragments=7) / `claude-code:335dd389…` (fragments=28) → "Done. Here's the summary of what I did: 1. Created new memory file…". The model thinks it must **execute** the extraction (create/write files) rather than **return** inline JSON → no JSON at all → parser cannot help → park.

## What Changes

- `atomizer/llm_output.py`: `_iter_json_arrays` gains an **unwrap** path — when the top-level parse yields a dict with a single array-valued key from a whitelist (`findings` / `slices` / `proposals` / `atoms`), unwrap and yield that array. Effects: `{"findings":[{…}]}` → extracts to slices; `{"findings":[]}` → empty array → #179's `slices=0` terminal state (no longer parks); bare arrays and multiple-valid-array behavior unchanged.
- `atomizer/skills/atomize-knowledge-slice.md` (**Fix B**, prompt hardening): explicitly require "return ONLY an inline JSON array; do NOT perform file create/write actions; do NOT return prose," blocking the wrong-task mode.
- One-time recovery of currently-parked "object-wrapped" sessions (clear `.retries` sidecar + cache, rerun dream) is an ops action documented in the plan, NOT code.

## Capabilities

### New Capabilities

None. This change extends the existing `stage2-memory-governance` capability.

### Modified Capabilities

- `stage2-memory-governance`: add object-wrapped-array unwrap in promotion JSON extraction and atomizer prompt hardening, to reduce the promote park floor while leaving #179's retry-budget parking mechanism unchanged.

## Impact

- **Affected code**: `paulshaclaw/memory/atomizer/llm_output.py` (`_iter_json_arrays` / `_iter_json_array_candidates` unwrap), `paulshaclaw/memory/atomizer/skills/atomize-knowledge-slice.md` (prompt).
- **Affected tests**: `paulshaclaw/memory/tests/test_llm_output.py` — object-wrapped non-empty → N slices; object-wrapped empty → `slices=0` terminal; bare array + multiple-arrays unchanged.
- **Non-goal**: does NOT change #179's retry-budget parking (bounded, no loop, correct). This reduces the fraction that falls into park (parser-recoverable ones), not the parking mechanism.
- **Relates**: #174 (fixed), #179 (PR merged), audit (wf memory 五項根因).
