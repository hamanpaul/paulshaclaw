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

### 3.2 `scope_ci.py` 行為（review 修正：關閉 no-manifest 繞過）
- **manifest 綁定改 PR-bound**：棄 `find_latest_manifest`（mtime 最新＝可被無關 manifest 汙染/替換），改「head branch ↔ slice」綁定——取 head branch 名中匹配 `runtime/handoff/<slice_id>.json` 的 manifest（dispatch 產物分支本就以 slice 命名）；多筆或不匹配 → 視同無 manifest。
- 解析 effective enforcement 後：
  - `shadow`：現行為完全不變（恆 exit 0、印 verdict annotate）。
  - `enforce` ＋ PR-bound manifest：verdict 違規（越界 write_paths）→ 印 verdict + **exit 1**；catalog 壞檔 → exit 1（fail-closed：執法時規則不可信即擋）。
  - `enforce` ＋ **無 PR-bound manifest**：計算變更集 ∩ **governed paths**（＝所有 enforce persona 的 `write_paths` 聯集）——
    - 有交集 → **exit 1（fail-closed）**：治理資產被無 persona 身分的變更觸碰，不得因「沒附 manifest」而放行（這正是繞過面）。人工 PR 的豁免走**顯式** `policy-exempt:persona-scope` label（既有白名單路徑），不是靠省略 manifest。
    - 無交集 → exit 0（與治理資產無關的 PR 不受影響）。
- mode 欄位如實回報 `"enforce"`／`"shadow"`（遙測不得謊報，沿 no-stale-telemetry 原則）。

### 3.3 workflow 與 required check
- `persona-scope.yml` 移除「恆 exit 0」註記，改「exit code 由 scope_ci 依 personas.yaml 決定」。
- required check 翻牌為 **owner 手動步驟**（branch protection UI／`gh api`），文件化於 runbook；順序：builder enforce 落地 → 試點 ≥1 週（誤傷記錄於 issue #124）→ 無誤傷才設 required。
- 豁免：`policy-exempt:persona-scope` label 既有文件化路徑不變。

## 4. 測試

- 設定：per-persona override 解析（builder=enforce、manager 繼承 shadow）；未知值 → 視為 shadow（fail-safe）＋ warning。
- scope_ci：enforce+違規 → exit 1；enforce+乾淨 → 0；**enforce+無 manifest+觸 governed paths → 1**；enforce+無 manifest+未觸 → 0；**manifest 非 PR-bound（branch 不匹配 slice）→ 視同無 manifest**；enforce+catalog 壞 → 1；label 豁免路徑 → 0；shadow 全路徑零回歸（既有測試不動）。
- workflow smoke：本機 `python -m paulshaclaw.persona.scope_ci` 於 fixture repo 各態驗證。

## 5. 風險

- 誤傷（builder 合法改動被擋、或人工 PR 觸 governed paths 需 label）：試點期不設 required、僅紅燈觀察；誤傷即修 write_paths／補 label 或降回 shadow（單行 yaml、可即回滾）；人工 PR 的 label 摩擦是**顯式豁免的代價**，試點期統計。
- governed paths 聯集過寬會放大誤傷：首翻只有 builder（write_paths 最窄明確），聯集＝builder 範圍；每加一個 enforce persona 前重估交集面。
