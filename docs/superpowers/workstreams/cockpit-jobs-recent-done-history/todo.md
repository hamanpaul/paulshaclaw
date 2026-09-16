---
status: proposed
work_item: cockpit-jobs-recent-done-history
issue: 369
---

# cockpit JOBS 面板：recent_done 歷史不得計入工作數，state 需翻成人可讀

對應 [hamanpaul/paulshaclaw#369](https://github.com/hamanpaul/paulshaclaw/issues/369)。
上游契約缺口另票 hamanpaul/paulsha-cortex#912（本 work item **不依賴**它，先做 UI 面修正）。

## Problem

2026-09-16 實測（paulshaclaw 0.2.9、cortex daemon v0.1.10）：cortex `status` 為
`in_flight=0 ready=0 held=0 attention=1 recent_done=10 not_claimable=2`，JOBS 面板卻顯示
「13 件」，operator 誤以為有 13 個 job 在管線裡；真阻塞只有 1 筆（attention）。

原因在 `paulshaclaw/cockpit/app.py` 與 `paulshaclaw/cockpit/models.py`：

1. `app.py` 的 ingest（`recent_done = status.get("recent_done")` 那段，約 L390–L410）把
   manager status 的 `recent_done`——**最近 10 個 exited job 的滑動視窗，純歷史**——逐筆
   投影成 `JobRow(source_section="recent_done", state=item["gate_status"], ...)`。
2. `state` 直接用上游 `gate_status`，面板上顯示 manager 內部 token `workflow-tracked`，
   operator 看不出這是「已完成」。
3. 這些 row `phase=""`，經 `_legacy_group_key_from_slice_id` 折成 `wf-<hash>` 群
   （例：`wf-eb777c996d 3 件`、`wf-08c8ef0541 3 件`），`JobGroup.item_count`（群組標題
   「N 件」）把歷史算進工作數；`_group_rank` 只把 recent_done 群「沉底」，沒有排除或標記。
4. 上游 `recent_done` 每筆只有 `at／branch／card／execution_state／executor／gate_reason／
   gate_status／identity_source／job_id／model／repo／slice_id`；`at` 是 status 刷新時間
   （非 job `exited_at`），無 `run_id`／run 終態。已 retire／superseded 的 run 的 job
   仍會出現。cockpit 端目前無法靠欄位判斷歷史，只能靠 `source_section == "recent_done"`。

## Requirements

- R1 recent_done row **不計入** `JobGroup.item_count` 與群組標題「N 件」；`summary_trailer`
  對純 recent_done 群跟著收合後的實際群組狀態：正常完成顯示「N 已完成」，`needs_human`
  保留「待裁決」，未知完成 token 依群組摘要改標「已結束」。面板頂層若有總計，同樣排除
  recent_done。
- R2 recent_done row 的顯示 state 由 `gate_status` 映射：`workflow-tracked`／`passed`／
  `done` → 「已完成」；未知 token → 「已結束」（中性字樣），**不得**原樣顯示內部 token。
  `JobRow.human_state` 對 recent_done 且 `needs_human` 的既有「待裁決」語意保留不變。
- R3 recent_done 群預設收合（Tree 節點 collapsed），群組標題標明「最近完成」；展開後才列
  各 job。`_group_rank` 沉底規則不變。
- R4 上游若日後補 `exited_at`／`run_status` 欄位（cortex#912），cockpit 前向相容讀取：
  `run_status ∈ {superseded, done}` 的 recent_done row 直接不列；欄位缺席時維持 R1–R3 行為。
  本 work item 只需預留讀取點與測試，不等上游。
- R5 attention／in_flight／ready／held／slices／not_claimable 的既有投影、排序、needs_human
  detail 行為逐字元不變（既有測試 `tests/test_cockpit_jobs_panel.py`、
  `tests/test_cockpit_jobs_three_axis.py`、`tests/test_cockpit_jobs_ux.py` 全綠）。

## Tasks

- [ ] T1 RED：在 `tests/test_cockpit_jobs_panel.py`（或新檔 `tests/test_cockpit_jobs_recent_done.py`）
      以 fixture status（attention 1、recent_done 10、not_claimable 2，欄位形狀照上文第 4 點）
      建 rows／groups，斷言：recent_done 不計入 `item_count`／「N 件」；state 顯示「已完成」
      而非 `workflow-tracked`；recent_done 群預設 collapsed；`run_status="superseded"` 的
      row 不列。先確認以現行程式碼失敗。
- [ ] T2 `models.py`：新增 `JobRow.is_recent_done`／顯示 state 映射；`JobGroup.item_count`
      改為排除 recent_done（或新增 `work_count` 供標題使用），`summary_trailer` 依 R1 輸出。
- [ ] T3 `app.py`：ingest 時讀取 `run_status`／`exited_at`（缺席容錯），`superseded`／`done`
      直接略過；`jobs_panel.py` 對純 recent_done 群預設 collapsed 並標題「最近完成」。
- [ ] T4 既有測試全綠；新增 `changelog.d/369-cockpit-jobs-recent-done-history.md`
      （frontmatter `type: fix`，`issue: 369`）。
- [ ] T5 PR body `Closes #369`，帶 PR 上下文跑 policy_check fail: 0。

## Boundary

- 只改 `paulshaclaw/cockpit/{app.py,models.py,jobs_panel.py}`、對應 tests 與 changelog 碎片。
- 不改 manager status 契約的讀取以外行為、不改 WORK 面板、不改 not_claimable／attention 的
  投影語意（#322／#669 既定）。
- 不修改 cortex；上游欄位補齊由 hamanpaul/paulsha-cortex#912 承接。
