## 1. cockpit-jobs-recent-done-history

- [x] T1 (RED): Add fixture status data reproducing `recent_done` jobs and write a failing test asserting exclusion from active counts / collapsed UI state, confirming current behavior fails before implementation.
- [ ] T2: Implement `JobRow.is_recent_done` and state-mapping logic in `models.py`.
- [ ] T3: Update ingestion and `jobs_panel.py` to apply collapsed default view and tolerant handling of optional fields (`exited_at`, `run_status`).
- [ ] T4: Run and verify the existing test suite plus new tests pass with zero regressions.
- [ ] T5: Finalize governance deliverables:
  - [ ] Add changelog fragment `changelog.d/369-cockpit-jobs-recent-done-history.md`.
  - [ ] Include `Closes #369` in PR metadata.
  - [ ] Ensure `policy_check` passes with zero failures before merge.
