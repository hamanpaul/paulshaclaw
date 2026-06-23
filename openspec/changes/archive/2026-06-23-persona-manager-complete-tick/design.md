## Context

Phase B（#112）落地了 coordinator 派工側：`autonomy.dispatch_ready` 算就緒集（`dispatch:auto ∧ 有 plan ∧ depends_on 全滿足`），對每個就緒單位經 headless `AgentLauncher` 啟動 agent，`JobRegistry` 記 `executor/session_name/pid/log_path`。完成偵測 `dispatcher.poll_headless_done`（exit sentinel + 末筆 JSONL → `classify_completion`）與 handoff manifest 讀寫（`persona.handoff`）、釋放判定 `autonomy.default_is_satisfied`（讀 `runtime/handoff/<slice>.json` 的 `gate_status=='passed'`）皆已存在——但**沒有任何 loop 把它們串起來**，所以 fan-out 的相依不會自己前進。

完整脈絡見 `docs/superpowers/specs/2026-06-23-persona-manager-complete-tick-design.md`。

## Goals / Non-Goals

**Goals:**
- 新增 `complete_tick` 純編排函式，把「輪詢 in-flight → 偵測完成 → 寫 completion manifest」串成一趟，使下一趟 `dispatch_ready` 能釋放下游。
- CLI `complete` 子命令作手動／Phase C timer 入口。
- 全 reuse 既有積木、零重造；不動派工側與互動路徑。

**Non-Goals:**
- 合併 fanout+complete 單一 tick、systemd timer、`--require-idle`（Phase C #122）。
- builder→reviewer handoff-message schema gate 作為釋放依據（Phase C ② gate）。
- failed job 的 retry / requeue。

## Decisions

- **釋放判定來源 = exit-code 主導 + shadow gate**（#104 留開放的決策）。`gate_status='passed' if completion=='done' else 'failed'`；persona diff gate 以 shadow 跑、存入 `gate_verdict` 觀測欄位、永不改 `gate_status`。
  - *為何不選真 handoff-schema gate*：headless 流程中沒有 builder→reviewer manifest，要求 agent 端額外吐 artifact 會牽動 relay hook、擴出 Phase B 範圍。shadow 對齊 Phase B 定位、最小可動。
  - *為何不選 merged-to-main*：需查 GitHub/merge 狀態、耦合 CI；`default_is_satisfied`/`ready_units` 已收注入 predicate，未來換來源只需換注入物，介面不變。
- **completion manifest 與 handoff 訊息分流**：兩者共用 `runtime/handoff/` 目錄但語意不同——前者唯一被依賴的欄位是 `gate_status`（給 `default_is_satisfied`），後者是 `validate_handoff_message` schema（Phase C）。設計上以 `gate_status` 欄位區隔。
- **reconciliation**：work set 含「終態但缺 manifest」者，補救「狀態已更新但 manifest 未寫成」的中斷，否則下游永遠卡死。
- **`complete_tick(dispatcher, ...)` 經 `dispatcher._registry` 取 registry**（沿 `autonomy._record_launcher_job` 既有存取慣例）；`gate_runner`/`clock` 可注入以求測試決定性。`metas` 可選，傳入才觀測算出 `released`。

## Risks / Trade-offs

- [shadow gate 不擋越界] → 與 Phase B 一致的暫時取捨；enforce 翻牌歸 #124。
- [exit-code 主導可能放行「跑完但成果不對」的 job] → done 由 `classify_completion`（exit 0 + 末筆 JSONL 非 `ok:false`）判定，已比 sentinel 猜測可靠；嚴格語意 gate 留 Phase C。
- [reconciliation 與冪等靠 manifest 檔存在性] → `write_manifest` 為 mkdir+write；同一 slice 重跑不覆寫（先檢查 `is_file()`）。
- [`released` 觀測需合法 metas] → 為可選輸入；CLI 預設不傳，不影響核心釋放（釋放由 manifest + 下一趟 dispatch 隱性達成）。

## Open Questions

- #104：depends_on 滿足來源長期是否改 merged-to-main——本票先採 handoff gate_status，介面保留可換。

## 已知限制（對抗式 review，留 Phase C）

對抗式 review 揭露三項，皆落在 dispatch 側 / retry 語意（#121 明訂 Phase C non-goal），文件化 + follow-up，不擴本票 scope：
- **#131**：`_default_gate_runner` 需 `dispatch_head`，但 headless 派工未存 baseline → 真實 job `gate_verdict` 恒 null（downstream 釋放靠 exit-code，不受影響）。
- **#132**：manifest 僅以 slice_id 為 key，Phase C retry/requeue（同 slice 多 job）下舊結果會卡住新結果。
- `handoff.write_manifest` 非原子寫（persona 模組既有問題），Phase C systemd 常駐前處理。
