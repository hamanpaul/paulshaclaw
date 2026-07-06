## ADDED Requirements

### Requirement: manifest 冪等以 job_id 三態判定
complete_tick SHALL 於 manifest 寫入時附 `job_id`；既存 manifest 之處置 SHALL 依 job_id 比對：相同 → skip（不重寫）；不同 → overwrite（新 run 之 gate_status/verdict/completed_at 全量重算重寫）；manifest 損毀或缺 job_id → overwrite；manifest 檔名與位置（`runtime/handoff/<slice_id>.json`）SHALL 不變。

#### Scenario: 同 run 重掃真冪等
- **WHEN** 同一 terminal job 於兩輪 complete_tick 被掃到
- **THEN** 第二輪 skip，manifest 內容與 mtime 不變

#### Scenario: requeue 新結果落地
- **WHEN** slice 首輪 job 以 failed 寫入 manifest 後，同 slice 新 job 達 done
- **THEN** manifest overwrite 為新 job_id 且 gate_status=passed，`default_is_satisfied` 由 False 轉 True

#### Scenario: 舊格式自然升級
- **WHEN** 既存 manifest 無 job_id 欄位且該 slice 有新 terminal job
- **THEN** overwrite 為含 job_id 之新格式

#### Scenario: 異常雙 terminal 釘住
- **WHEN** 同 slice 兩 job 同輪皆 terminal（不變量被繞過之異常）
- **THEN** 依 registry 確定性序後者勝，並記 warning `same-slice concurrent terminals`
