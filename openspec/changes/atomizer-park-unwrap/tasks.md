## 1. Parser unwrap (Fix A)

- [ ] 1.1 RED: in `test_llm_output.py`, add failing tests — `{"findings":[{…}]}` → N proposals; `{"findings":[]}` → empty array (slices=0 terminal); bare array unchanged; multiple valid arrays unchanged; object with >1 array key or non-whitelisted key NOT unwrapped
- [ ] 1.2 Implement the unwrap in `atomizer/llm_output.py`: when a top-level object has exactly one array-valued key from {`findings`,`slices`,`proposals`,`atoms`}, yield that array from `_iter_json_arrays`
- [ ] 1.3 Confirm `_parse_proposals` / `parse` route the unwrapped empty array to #179's existing `slices=0` terminal state (no park); add/adjust the assertion

## 2. Prompt hardening (Fix B)

- [ ] 2.1 Update `atomizer/skills/atomize-knowledge-slice.md`: require inline-JSON-array-only output; forbid file create/write actions; forbid prose
- [ ] 2.2 Add a test/assertion that the rendered prompt contains the inline-array-only + no-file-write + no-prose contract

## 3. Verify & regression

- [ ] 3.1 Full suite green via `~/.local/bin/pytest paulshaclaw/memory/tests/` (avoid `unittest discover` — drops `def test(tmp_path)` style)
- [ ] 3.2 Regression: do NOT change #179's retry-budget parking; existing empty-array / fail-closed behavior unchanged

## 4. Ops recovery note (doc only, no code)

- [ ] 4.1 Document in the PR/plan the one-time recovery for parked object-wrapped sessions: clear `.retries` sidecar + cache for those session+fragment keys, rerun dream, expect promote (incl. slices=0)
