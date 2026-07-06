## Why

persona 治理 100% shadow（scope_ci 恆 exit 0、workflow 明文不得設 required check）——「persona-governed」只觀測不執法，越界寫入無實際攔阻（#124）。站穩閘 G2＝enforce 可分批翻牌且不可繞過。

## What Changes

- `personas.yaml`：全域 `enforcement` 為 default，`roles.<name>.enforcement` per-persona override；首翻 builder。
- `scope_ci.py`：manifest 綁定改 **PR-bound**（head branch↔slice 匹配，棄 mtime-latest）；enforce＋違規→exit 1；enforce＋**無 PR-bound manifest 且變更觸 governed paths（enforce personas write_paths 聯集）→ exit 1（fail-closed，關閉省略 manifest 的繞過）**；人工 PR 豁免走顯式 `policy-exempt:persona-scope` label；catalog 壞檔於 enforce → exit 1。
- `persona-scope.yml`：移除「恆 exit 0」註記；required check 翻牌為 owner 手動步驟（試點 ≥1 週無誤傷後）。

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `stage4`: persona scope 檢查新增 enforce 模式語意（per-persona 翻牌、PR-bound manifest、governed-paths fail-closed、label 豁免）。

## Impact

- 受影響碼：`paulshaclaw/persona/{scope_ci.py,personas.yaml}`、`.github/workflows/persona-scope.yml`。
- 依賴：**g1-coordinator-adapter**（enforce 試點需真 dispatch 流量產生 PR-bound manifest）。
- 依據：`docs/superpowers/specs/2026-07-06-g2-persona-enforce-design.md`（含 codex 審查修正：繞過面關閉）。
