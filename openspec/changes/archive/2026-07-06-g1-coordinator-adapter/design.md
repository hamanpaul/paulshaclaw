## Context

完整設計＋審查修正：`docs/superpowers/specs/2026-07-06-g1-coordinator-adapter-design.md`。本檔僅收斂裁決。現行契約：`REQUEST_TYPES={"tick","fanout"}`（contract.py:12）、status 正規化鍵無 held（client.py read_status）、`/dispatch`→UnavailableCoordinator（listener.py:213-226）。

## Goals / Non-Goals

**Goals:** `/dispatch <slice>` e2e 真 job；held backlog 穿透到 operator 路徑；specs_dir 接 repo 真相源。
**Non-Goals:** persona enforce（G2）；fanout 策略調整；production spec 翻 auto；cockpit held 呈現（另案小 change）。

## Decisions

1. **擴充既有契約，不造第二條 queue**（父件裁決）：dispatch 為第三種 request 型別，沿 requests/done/status+lock 檔案協定與冪等語意。
2. **hold 預設 fail-closed、覆蓋顯式留痕**（審查修正）：與 autonomy「只認字面 auto」哲學一致；`force_hold: true`＋done 稽核欄 `{override, requested_by}`。
3. **already-active guard**：維持「一 slice 一活躍 job」不變量（G4 overwrite 正確性前提）；terminal 後重下＝requeue。
4. **held 必須穿透消費端**（審查修正）：read_status 正規化鍵加 held（舊檔→[]）；`/manager status` 顯示摘要——否則 operator 永遠看不到。
5. **backend selection fail-closed**：`coordinator.backend` 未設→Unavailable（現狀零回歸）；env 覆寫 `PSC_COORDINATOR_BACKEND`。
6. **specs_dir=repo 路徑參數化**，不 sync 副本（複製漂移坑型）；default `~/.agents/specs` 不變。

## Risks / Trade-offs

- 遠端誤派面：fail-closed＋顯式 force＋全程留痕收斂。
- additive 欄位相容：consumer dict.get 風格＋相容測試把關。
- adapter 回覆即時性：create_job 回 req_id 即返，job_id 由 done 檔／status 面呈現（非同步語意如實呈現，不假裝同步）。
