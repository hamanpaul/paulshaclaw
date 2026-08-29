## 1. #322 follow-up formalization

- [x] 1.1 新增專用 spec-driven change `cockpit-jobs-three-axis`，承接已落地的 JOBS 三軸 follow-up
- [x] 1.2 補 Stage 11 spec delta：workflow_run / `not_claimable` ingest、project / stage / agent 三軸、排序 / 計數、detail 安全呈現
- [x] 1.3 從 `openspec/changes/stage11-multi-session-pane-listing-v2/tasks.md` 移除無關的 #322 candidate-only 任務

## 2. Workstream correlation

- [x] 2.1 建立 `docs/superpowers/workstreams/stage11-operator-cockpit/todo.md`，串起本 change、`changelog.d/cockpit-jobs-three-axis.md` 與既有 `changelog.d/322-cockpit-jobs-three-axis.md`
- [x] 2.2 補上 canonical preflight fragment `changelog.d/cockpit-jobs-three-axis.md`，並保留 `changelog.d/322-cockpit-jobs-three-axis.md` 作為 #322 既有交付碎片
- [x] 2.3 保持 handoff 為 pre-archive 範圍，不在 tasks / todo 提前宣告 archive、merge 或 issue closure

## 3. Delivery handoff hygiene

- [x] 3.1 讓 `scripts/preflight-tests.sh` 共用 operator runtime resolver，worktree 缺 `.venv` 時仍可重跑全套 pytest preflight
- [x] 3.2 將 Stage 11 workstream todo 的 change 路徑對齊 archived location，並只保留 merge / issue closure 待 Manager 執行的 handoff 語意

## 4. Review repair alignment

- [x] 4.1 將 archived proposal 的 Impact 改寫為如實描述：此 candidate 以 OpenSpec / bookkeeping 為主，但同時包含已核准的 #322 cockpit 程式、`scripts/preflight-tests.sh` 收尾修正與相關測試
- [x] 4.2 更新 `tests/test_cortex_alignment.py` 的 worktree override case，顯式提供 `PSC_REPO_ROOT` 以對齊 pinned Cortex 的 fail-closed `worktree_root()` 契約
