## Context

完整設計＋審查修正：`docs/superpowers/specs/2026-07-06-g4-complete-tick-idempotency-design.md`。病灶：`manager.py` `if manifest_path.is_file(): continue`。消費端以 `runtime/handoff/<slice_id>.json` 讀 gate_status——檔名契約不可動。

## Goals / Non-Goals

**Goals:** requeue 新結果落地；同 run 真冪等；消費端零改。
**Non-Goals:** manifest 檔名/位置變更；重試策略（dispatcher/registry 語意）；審計歷史（registry 為真相源）。

## Decisions

1. **job_id 進 manifest、檔名不動**：以內容欄位辨 run，不破壞 `<slice_id>.json` 消費契約。
2. **三態規則**：同 job_id→skip；異 job_id→overwrite（新 run 勝）；壞檔/舊格式→overwrite（無法證明同 run 即視舊帳）。
3. **不變量顯式化**（審查修正）：overwrite 良定義依賴「一 slice 一活躍 job」——run_tick 既有 active 過濾（自動路徑，現況成立）＋ G1 `already-active` guard（手動路徑，G1 落地前不存在故無破口）。異常雙 terminal：後掃者勝＋log warning `same-slice concurrent terminals`，不加鎖（YAGNI，防線在 dispatch 側）。
4. **released 觀測語意不變**：failed→passed 的 overwrite 正確反映於本輪 released。

## Risks / Trade-offs

- overwrite 抹掉首輪失敗快照：manifest 定位為「最新裁決」，歷史在 registry/log。
