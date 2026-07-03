## 1. Ledger-traced reconcile dedup

- [ ] 1.1 RED: in `test_moc_naming.py`, add a failing test — dedup of a duplicate `slice_id` appends a lifecycle event (`event_type="superseded"`, `record_id=<slice_id>`, metadata has `deleted_path`/`kept_path`); assert the kept file is identical to the pre-change behavior
- [ ] 1.2 Implement in `moc/naming.py::reconcile`: before each dedup/overwrite `unlink` (`:61`, `:63`, `:71`), call `ledger/lifecycle.py::append_event` (mirror `janitor/scanner.py::_persist_event`: `source`/`actor="moc-reconcile"`, resolve lifecycle path from `memory_root`)
- [ ] 1.3 RED + impl: a lifecycle append failure is caught → the pass continues (degrades to the existing warning) and does not raise

## 2. Verify & regression

- [ ] 2.1 Full suite green via `~/.local/bin/pytest paulshaclaw/memory/tests/` (esp. `test_moc_naming.py`, `test_ledger_lifecycle.py`); **avoid `unittest discover`**
- [ ] 2.2 Regression: reconcile's deletion *selection* is unchanged; existing warnings still returned; the janitor is untouched

## 3. Close the loop on the rekey case

- [ ] 3.1 Verify the #177/#183 rekey same-`slice_id`-conflict scenario now leaves a ledger trace when the parked file is deduped (reuse the `conflict_next_pass` repro from #184); note the before/after in the PR body
