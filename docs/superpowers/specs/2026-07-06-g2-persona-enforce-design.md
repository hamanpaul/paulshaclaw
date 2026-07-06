---
dispatch: hold
slice_id: g2-persona-enforce
plan: null
depends_on: [g1-coordinator-adapter]
---

# G2 — persona enforce 翻牌（shadow→enforce，分批） 設計

> 日期：2026-07-06 ｜ 狀態：草案（待覆審）｜ 對應：#124
> 父件：`2026-07-06-p3-standup-gates-umbrella-design.md`。依賴 G1：enforce 試點需要真 dispatch 流量才有意義的誤傷資料。

## 1. 背景與問題

persona 治理 100% shadow：`personas.yaml:2` 全域 `enforcement: shadow`、`scope_ci.py` 四處「shadow 仍恆放行」硬編碼、`persona-scope.yml` 明文「恆 exit 0、MUST NOT 設 required check」。「persona-governed」只觀測不執法，越界寫入無實際攔阻。

## 2. 目標與非目標

**目標**：enforce 可 per-persona 漸進開啟；builder 先翻；違規 PR 被 CI 擋下。
**非目標**：新 persona／write_paths 內容調整（沿現值）；G1 的 dispatch 語意；一次全 persona 翻牌（明確反目標——分批是設計核心）。

## 3. 設計

### 3.1 設定模型（`personas.yaml`）
- 全域 `enforcement:` 保留＝default；`roles.<name>.enforcement:` 新增 per-persona override（值域 `shadow|enforce`，缺省繼承全域）。
- 首翻：`roles.builder.enforcement: enforce`（write_paths 最明確、流量最大）；manager/其他維持 shadow。

### 3.2 `scope_ci.py` 行為
- 解析 manifest 對應 persona 的 effective enforcement：
  - `shadow`：現行為完全不變（恆 exit 0、印 verdict annotate）。
  - `enforce`：verdict 違規（越界 write_paths）→ 印 verdict + **exit 1**；無 manifest → **skip（exit 0）**——沒有 persona 派工的 PR（人工/一般 PR）不受影響；catalog 壞檔在 enforce persona 下 → exit 1（fail-closed：執法時規則不可信即擋）。
- mode 欄位如實回報 `"enforce"`／`"shadow"`（遙測不得謊報，沿 no-stale-telemetry 原則）。

### 3.3 workflow 與 required check
- `persona-scope.yml` 移除「恆 exit 0」註記，改「exit code 由 scope_ci 依 personas.yaml 決定」。
- required check 翻牌為 **owner 手動步驟**（branch protection UI／`gh api`），文件化於 runbook；順序：builder enforce 落地 → 試點 ≥1 週（誤傷記錄於 issue #124）→ 無誤傷才設 required。
- 豁免：`policy-exempt:persona-scope` label 既有文件化路徑不變。

## 4. 測試

- 設定：per-persona override 解析（builder=enforce、manager 繼承 shadow）；未知值 → 視為 shadow（fail-safe）＋ warning。
- scope_ci：enforce+違規 → exit 1；enforce+乾淨 → 0；enforce+無 manifest → 0（skip）；enforce+catalog 壞 → 1；shadow 全路徑零回歸（既有測試不動）。
- workflow smoke：本機 `python -m paulshaclaw.persona.scope_ci` 於 fixture repo 兩態驗證。

## 5. 風險

- 誤傷（builder 合法改動被擋）：試點期不設 required、僅紅燈觀察；誤傷即修 write_paths 或降回 shadow（單行 yaml、可即回滾）。
- 無 manifest skip 是繞過面：G1 後 dispatch 皆產 manifest；人工 PR 本就不屬 persona 執法對象——邊界如實記錄於 spec delta。
