## 1. PromoteError path clears poisoned cache

- [x] 1.1 Add failing tests in `paulshaclaw/memory/tests/test_atomizer_pipeline.py`: (a) promote failure with a caching LLM promoter leaves session `split` AND removes the cache `.json`; (b) two-run recovery — run 1 bad output / run 2 valid output ends `promoted` with a second real agent call; (c) non-LLM promoter failure creates/deletes nothing under `runtime/cache/atomize/`.
- [x] 1.2 Implement: in `pipeline.py::_promote_pass` non-dry-run `except PromoteError` handler, call `promoter.clear_cache_for_fragments([fragment for _, fragment in fragments])` when `isinstance(promoter, LLMPromoter)`.

## 2. Empty JSON array becomes terminal promoted state

- [x] 2.1 Update `test_llm_output.py`: replace `test_empty_array_raises` with empty-array-returns-`[]` tests (bare `[]` and fenced-with-reasoning variants); add all-invalid-proposals still raises `no salvageable proposals`.
- [x] 2.2 Update `test_llm_promoter.py`: replace `test_empty_output_fails_closed` with `promote(...) == []` on `[]` output.
- [x] 2.3 Implement: `llm_output.py::_parse_proposals` early `return []` when `data == []` (do NOT merely remove the non-empty check — `data=[]` would fall to the `no salvageable proposals` raise).
- [x] 2.4 Replace `test_atomizer_pipeline.py::test_llm_empty_output_leaves_session_split_without_archiving_fragments` with a regression test: `[]` output → `state=promoted`, `slices=0`, fragments archived, cache cleared, no `left in split` warning (no pipeline code change expected).

## 3. Dream record surfaces warnings

- [x] 3.1 Add failing tests in `test_dream_orchestrator.py`: warning text lands in `passes.<pass>.warnings` + `warnings_total`; 45 warnings truncate to 10 recorded / total 45; clean pass summary keeps exact old shape (no new keys).
- [x] 3.2 Implement: `dream/orchestrator.py::_run_pass` copies the summary and, when warnings is a non-empty list, adds `warnings` (first 10, each ≤500 chars) and `warnings_total`.

## 4. Bounded retry budget

- [x] 4.1 Add failing tests in `test_atomizer_pipeline.py`: first failure writes `.retries` = `1` and clears cache; seeded `.retries` = `5` + failure → counter `6`, cache retained, later run does not re-invoke the agent; successful promotion removes the `.retries` sidecar.
- [x] 4.2 Implement in `pipeline.py`: `_LLM_PROMOTE_MAX_RETRIES = 5`, `_retry_counter_path()` (cache-key validation + containment), failure-path increment + conditional clear, success-path sidecar removal alongside `_clear_cache_key`.

## 5. Regression & wrap-up

- [x] 5.1 Full local suite green: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. /home/paul_chen/.local/bin/pytest paulshaclaw/memory/tests/ -q` (do not use `unittest discover` — it silently skips pytest-style tests).
- [x] 5.2 CI-equivalent check: `python -m pytest tests/ paulshaclaw/memory/tests/ -q`. Known pre-existing local noise (unrelated, do NOT touch): 2 failures in `tests/test_stage11_operator_cockpit.py` from local textual version drift; `paulshaclaw/memory/tests/` must be fully green and CI is authoritative.
- [x] 5.3 Record verification summary below; deliver per plan Delivery section (branch `feature/174-stage2-promotion-cache-recovery`, PR body `Closes #174`, no merge).

## Verification Summary

- `cd /home/paul_chen/prj_pri/psc-wt-174 && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_atomizer_pipeline.py -q -k "PromoteFailureCacheRecovery"` → RED：`2 failed, 1 passed`；GREEN（在 `pipeline.py` 清 cache 後）改跑全檔 `.../test_atomizer_pipeline.py -q` → `36 passed`。
- `cd /home/paul_chen/prj_pri/psc-wt-174 && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_llm_output.py paulshaclaw/memory/tests/test_llm_promoter.py -q ; PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_atomizer_pipeline.py -q -k "empty_output_reaches_promoted"` → RED：前段 `3 failed, 44 passed, 18 subtests passed`、後段 `1 failed`；GREEN：`.../test_llm_output.py .../test_llm_promoter.py .../test_atomizer_pipeline.py -q` → `83 passed, 18 subtests passed`。
- `cd /home/paul_chen/prj_pri/psc-wt-174 && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_dream_orchestrator.py -q` → RED：`3 failed, 7 passed`；GREEN：`.../test_dream_orchestrator.py .../test_dream_cli.py .../test_dream_cli_moc_warnings.py .../test_dream_e2e.py -q` → `16 passed`。
- `cd /home/paul_chen/prj_pri/psc-wt-174 && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_atomizer_pipeline.py -q -k "PromoteFailureCacheRecovery"` → RED：`3 failed, 3 passed, 33 deselected`；GREEN（加入 `.retries` sidecar/預算 5 後）`.../test_atomizer_pipeline.py -q` → `39 passed`。
- `cd /home/paul_chen/prj_pri/psc-wt-174 && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q` → `781 passed, 1 skipped, 87 subtests passed in 26.70s`。
- `cd /home/paul_chen/prj_pri/psc-wt-174 && PYTHONPATH=. python -m pytest tests/ paulshaclaw/memory/tests/ -q` → `1463 passed, 15 skipped, 112 subtests passed`，另有 plan 已知本機雜訊 `tests/test_stage11_operator_cockpit.py::{test_on_mount_schedules_pane_and_sysmon_ticks,test_refresh_skips_work_list_rebuild_when_content_unchanged}` 2 失敗；`paulshaclaw/memory/tests/` 全綠，未超出既有噪音範圍。
