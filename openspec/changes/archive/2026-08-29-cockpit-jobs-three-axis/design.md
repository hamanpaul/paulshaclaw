## Context

已核准的 #322 程式碼、測試與 changelog 都在 candidate 上：

- `paulshaclaw/cockpit/{app,models,jobs_panel}.py`
- `tests/test_stage11_operator_cockpit.py`
- `tests/test_cockpit_jobs_panel.py`
- `tests/test_cockpit_jobs_ux.py`
- `changelog.d/cockpit-jobs-three-axis.md`
- `changelog.d/322-cockpit-jobs-three-axis.md`

缺的是交付 bookkeeping：

1. `stage11-multi-session-pane-listing-v2/tasks.md` 被借來掛 #322 專屬任務
2. `stage11-operator-cockpit` 沒有專屬的 JOBS 三軸 spec delta
3. Stage 11 也沒有對應的 workstream todo 把上述交付串起來

## Goals / Non-Goals

**Goals**

- 把 #322 JOBS 三軸 follow-up 從 `stage11-multi-session-pane-listing-v2` 拆出成專用 change
- 用 spec delta 描述既有 code/tests 已實現的行為
- 補一份 Stage 11 workstream todo，把 change 與 changelog fragment 關聯起來
- 保持 tasks/todo 僅描述 pre-archive work

**Non-Goals**

- 重做 #322 的 cockpit 程式碼
- 修改 pinned input 計畫文件
- 在本 card 內 archive change、宣告 merge、或替 Manager 關閉 issue

## Decisions

1. **把 #322 勾選項移出無關的 active change**
   - `openspec/changes/stage11-multi-session-pane-listing-v2/tasks.md` 只保留它自己的
     multi-session pane listing 任務。
   - #322 的 RED regression / review follow-up / changelog fragment 改由新 change 承接。

2. **專用 change 只 formalize 已落地行為**
   - `cockpit-jobs-three-axis` 的 proposal/design/spec/tasks 都描述既有程式與測試
     已落地的事實，不在文件裡虛構新的實作工作。
   - tasks 全部限制在 spec/workstream/delivery bookkeeping，避免提前宣告 archive。

3. **workstream 用 todo 作為最小關聯來源**
   - 新增 `docs/superpowers/workstreams/stage11-operator-cockpit/todo.md`。
   - 只補 todo，不回填不存在的 plan/review/evidence，避免把這張 card 沒做過的流程補寫成
     既成事實。

4. **補 canonical changelog，同時保留既有 #322 fragment**
   - archive gate 需要與 change slug 同名的 `changelog.d/cockpit-jobs-three-axis.md`；
     補最小片段即可。
   - `changelog.d/322-cockpit-jobs-three-axis.md` 仍保留原檔，延續已核准的 #322 cockpit
     交付紀錄，不搬動、不覆寫。

## Risks / Trade-offs

- 新 change 的 tasks 可以全勾，但那只代表 pre-archive 文件補齊，不代表 Manager 已完成
  archive / merge / issue closure。
- workstream 採 todo-only 是刻意的最小差異；若未來要補更完整 Stage 11 workstream 文檔，
  應另開 change。
