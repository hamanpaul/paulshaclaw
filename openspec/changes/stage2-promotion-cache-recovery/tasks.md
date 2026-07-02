## 1. PromoteError path clears poisoned cache

- [ ] 1.1 Add failing tests in `paulshaclaw/memory/tests/test_atomizer_pipeline.py`: (a) promote failure with a caching LLM promoter leaves session `split` AND removes the cache `.json`; (b) two-run recovery — run 1 bad output / run 2 valid output ends `promoted` with a second real agent call; (c) non-LLM promoter failure creates/deletes nothing under `runtime/cache/atomize/`.
- [ ] 1.2 Implement: in `pipeline.py::_promote_pass` non-dry-run `except PromoteError` handler, call `promoter.clear_cache_for_fragments([fragment for _, fragment in fragments])` when `isinstance(promoter, LLMPromoter)`.

## 2. Empty JSON array becomes terminal promoted state

- [ ] 2.1 Update `test_llm_output.py`: replace `test_empty_array_raises` with empty-array-returns-`[]` tests (bare `[]` and fenced-with-reasoning variants); add all-invalid-proposals still raises `no salvageable proposals`.
- [ ] 2.2 Update `test_llm_promoter.py`: replace `test_empty_output_fails_closed` with `promote(...) == []` on `[]` output.
- [ ] 2.3 Implement: `llm_output.py::_parse_proposals` early `return []` when `data == []` (do NOT merely remove the non-empty check — `data=[]` would fall to the `no salvageable proposals` raise).
- [ ] 2.4 Replace `test_atomizer_pipeline.py::test_llm_empty_output_leaves_session_split_without_archiving_fragments` with a regression test: `[]` output → `state=promoted`, `slices=0`, fragments archived, cache cleared, no `left in split` warning (no pipeline code change expected).

## 3. Dream record surfaces warnings

- [ ] 3.1 Add failing tests in `test_dream_orchestrator.py`: warning text lands in `passes.<pass>.warnings` + `warnings_total`; 45 warnings truncate to 10 recorded / total 45; clean pass summary keeps exact old shape (no new keys).
- [ ] 3.2 Implement: `dream/orchestrator.py::_run_pass` copies the summary and, when warnings is a non-empty list, adds `warnings` (first 10, each ≤500 chars) and `warnings_total`.

## 4. Bounded retry budget

- [ ] 4.1 Add failing tests in `test_atomizer_pipeline.py`: first failure writes `.retries` = `1` and clears cache; seeded `.retries` = `5` + failure → counter `6`, cache retained, later run does not re-invoke the agent; successful promotion removes the `.retries` sidecar.
- [ ] 4.2 Implement in `pipeline.py`: `_LLM_PROMOTE_MAX_RETRIES = 5`, `_retry_counter_path()` (cache-key validation + containment), failure-path increment + conditional clear, success-path sidecar removal alongside `_clear_cache_key`.

## 5. Regression & wrap-up

- [ ] 5.1 Full local suite green: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. /home/paul_chen/.local/bin/pytest paulshaclaw/memory/tests/ -q` (do not use `unittest discover` — it silently skips pytest-style tests).
- [ ] 5.2 CI-equivalent check: `python -m pytest tests/ paulshaclaw/memory/tests/ -q`. Known pre-existing local noise (unrelated, do NOT touch): 2 failures in `tests/test_stage11_operator_cockpit.py` from local textual version drift; `paulshaclaw/memory/tests/` must be fully green and CI is authoritative.
- [ ] 5.3 Record verification summary below; deliver per plan Delivery section (branch `feature/174-stage2-promotion-cache-recovery`, PR body `Closes #174`, no merge).

## Verification Summary

(To be filled at end of implementation: focused test invocations, full suite result.)
