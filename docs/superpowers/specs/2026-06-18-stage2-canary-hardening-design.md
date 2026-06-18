# Stage 2 Canary 強化 — 設計（projects.yaml 登記 + lenient LLM 驗證）

> 日期：2026-06-18 ｜ 狀態：草案（待覆審）｜ 分支：`feature/stage2-canary-hardening`（疊在 `feature/stage2-phase2-llm-promoter` / PR #98 之上）
> 前置脈絡：[[2026-06-17-stage2-phase2-llm-promoter-design]]（Phase 2a canary）

## 1. 背景

Phase 2a canary 翻開後，把 LLM promoter 拉去跑真 gemma4（隔離 `/tmp` root，5 個真 session）量得：

- **內容品質好**（蒸餾 body 結構清楚、標題夠細、`atom_title`/`session_title` frontmatter 落地）。
- 但 **~40% session fail-closed**（5 個 2 個 skipped），全是 gemma4 不守 JSON 契約的軟錯：
  - `unknown source_fragment_indices [20,28]`——引用不存在的 fragment index（stochastic，同 session 兩跑分別 `[8..42]`、`[20,28]`）。
  - relation `type: "mentations"`——拼錯 `mentions`，**單一 typo 讓整 session 零落地**（all-or-nothing）。
- **project 100% 歸錯成 `paulshaclaw`**：5 個樣本實際是 MTK PON / OCP-0602 / codex 等，但 `~/.agents/config/projects.yaml` 只登 3 個專案（paulshaclaw / obs-auto-moc / serialwrap），gemma4 `known_projects` 沒得選 → 全塞最近的 paulshaclaw。

兩個根因、兩個 follow-up：projects.yaml 太瘦（config）、驗證太硬（code）。

## 2. 目標與非目標

**目標**：
- **Part A**：登記所有活躍專案到 `projects.yaml`，讓 resolver 映乾淨 slug + gemma4 `known_projects` 擴張、歸屬正確。
- **Part B**：LLM 驗證由 all-or-nothing fail-closed 改為 **repair-soft / drop-hard-per-proposal / session-fail-only-if-empty**，把 ~40% 假性失敗壓下來。

**非目標**：
- SkillOpt（練 skill 讓 gemma4 更守契約）——後續。
- Phase 2b 全量回填——獨立、canary 判過關才動。
- 改 splitter / ledger / pipeline 骨架。

## 3. Part A — project 歸屬修正（config + 小 resolver fix）

**根因（讀 resolver + 實機 payload 確認）**：raw payload **不帶 `remote_url/remote/repo`（全 None）**，只有 `cwd`。`resolve_project` 流程：① root 前綴比對（最長贏）② remote 比對（需 `remote_url`，這裡沒有 → 跳過）③ git fallback：`git_toplevel(cwd)` 在 import 機跑出 repo 的 remote，但 **line 106 直接 `return` 原始 URL，不查 projects.yaml** → 這就是 corpus URL 形式的來源（Phase 1 memo 說的 whack-a-mole）。所以「登 remotes」單靠 config 不會生效；roots-only 又要逐子目錄列（脆）。

**修法 = config + 3 行 resolver fix**：

### A1 — `projects.yaml` 登記（本機 config，可逆）
交付 repo 用 `remotes`（靠 A2 的 fallback 映射，對所有子目錄 robust）；工作區資料夾用 slug-only（空 roots，靠 basename fallback 落乾淨名 + 進 known_projects）。

| slug | 性質 | remotes（正規化形） | roots |
|---|---|---|---|
| `airoha` | 交付 repo | `vcs-sw2.arcadyan.com.tw/airoha/airoha_openwrt_feed` | `OCP-0602/airoha`（備援） |
| `ot-ti-mirror` | 交付 repo | `vcs-sw2.arcadyan.com.tw/mcu/ti/ot-ti-mirror` | `prj_arc/userspace/ot-ti-mirror`（備援） |
| `mtk-pon-llapi` | 交付 repo（封存留經驗） | `github.com/hamanpaul/mtk-pon-llapi` | `OCP-0602/mtk-pon-llapi-repo` |
| `OCP-0602` | ref 工作區 | — | （空，靠 basename fallback） |
| `MCU-Octopus` | ref 工作區 | — | （空，靠 basename fallback） |
| `custom-skills` | repo | `github.com/hamanpaul/custom-skills` | `~/prj_pri/custom-skills` |
| `testpilot` | repo | `github.com/hamanpaul/testpilot` | `~/prj_arc/testpilot` |
| `paulsha-conventions` | repo | `github.com/hamanpaul/paulsha-conventions` | `~/prj_pri/paulsha-conventions` |

外加：既有 `serialwrap` entry 補 remote `github.com/hamanpaul/serialwrap`。排除 noise（`paul_chen` home-dir、`.codex/memories`）。**不登 OCP-0602/MCU-Octopus 的 roots**——否則 root 前綴會在 git fallback 前先把底下的 airoha 吞進 OCP-0602。

### A2 — resolver git-fallback 映射 slug（repo code，TDD）
`project_resolver.py` git fallback 算出 `remote` 後，**先查 projects.yaml remotes 映成 slug 再回**，查無才回原始 URL：
```python
if remote:
    for project in loaded_projects.projects:
        if any(normalize_remote(r) == remote for r in project.remotes):
            return project.slug
    return remote
```
這是 URL-form 洩漏的根因修正，讓 remote 登記對所有子目錄 robust。

**驗證**：A1+A2 後重跑那組 5-session live sample，斷言 project 不再全是 paulshaclaw（airoha/OCP-0602/ot-ti-mirror 等正確出現）。

## 4. Part B — lenient LLM 驗證（repo code → PR）

**策略**：repair 軟錯、per-proposal drop 硬錯、session 只在空時才 fail。

| 層 | 檔案 | 現況（硬） | 改為（lenient） |
|---|---|---|---|
| relation 驗證 | `llm_output.py:144-173` `_validate_relation` | 不支援 type / 壞 shape → `raise LlmOutputError` | drop 該 edge（回 `None`，parse 過濾掉）；**不猜 typo**（`mentations` 直接丟） |
| project 歸屬 | `llm_output.py` parse | 不在 known → raise（推測） | **coerce 成 `_unknown`**（保住 atom） |
| proposal 硬錯 | `llm_output.py` parse | 任一 body/title 空、artifact_kind 非法 → raise | **skip 該 proposal**、留其餘 |
| fragment indices | `llm_promoter.py:114-117` | unknown indices → `raise PromoteError` | 與有效集**取交集丟未知**；交集空仍保留（slice_id 內容派生、provenance 盡力） |

**session 只在以下才 fail-closed**：零 proposal 存活、輸出非 JSON 陣列、agent 報錯。

> **實作補正（live 驗證揭露）**：promoter「unknown indices 取交集」若**交集為空**（gemma4 全部 index 越界），slice 仍需 ≥1 source fragment（`pipeline._referenced_fragments` 會 `KeyError`）→ 改為交集空時 **fallback 整個 session 的 valid set**，把 atom 歸屬整 session 而非丟棄。

## Part C — atomize prompt session-project 軟 hint（repo code，TDD）

**live 驗證揭露的第三個根因**：A1 把 `known_projects` 擴張到 11 個後，重跑 sample **仍 100% 歸 paulshaclaw**。`prompt.build_prompt` 只給 gemma4 `known_projects` 清單 + fragment 內文，**從不告知 session 已解析出的 project**（`fragment.project`，A1+A2 後已正確，如 MTK PON session = `OCP-0602`）→ gemma4 純靠內容猜、預設 paulshaclaw。

修法：prompt 加一段 session-project 軟 hint（僅當該 project 在 known_projects 時）：「This session was captured in project: \<X\>. Prefer it for each slice unless the content clearly belongs to a different known project.」gemma4 預設歸該專案、內容明顯跨專案才改（保留 multi-project 拆分彈性）。

## 5. Live 驗證結果

A1+A2+B+C 後重跑 5-session live sample：
- **A2**：`airoha-mcu-clean` → `airoha`、`ot-ti-mirror` → `ot-ti-mirror`（原洩漏 raw URL）。✓
- **歸屬**：不再全 paulshaclaw——MTK PON session 正確產 OCP-0602 原子、codex session → custom-skills、其餘真 paulshaclaw 維持。✓
- **fail-closed**：contract-violation（relation typo / 越界 index）已 salvage；剩餘 skip 是 gemma4 stochastic「no JSON array found」——**lenient 無法修**（沒 JSON 可救），屬 model 輸出層、需 retry 或 SkillOpt，列為已知殘留 floor。

**可觀測性**：每筆 repair/drop **WARN log 進 `atomizer.log`**（類別 + proposal index + session_key，**不記原文**）。「no silent salvage」——丟了什麼要看得到。

**契約變更**：這軟化了 Phase 2a `stage2-llm-distillation` 的「Fail-closed distillation」requirement（從 all-or-nothing 改為「整 session 只在空時 fail，個別問題 repair/drop」）。因 #98 spec 尚未進 main，本期以本設計文件 + PR 說明 + 測試為準，待 #98 merge 後再對齊 spec。

**測試（TDD）**：一份含「壞 relation + 越界 indices + 一個空 body proposal」的 LLM 輸出 → 斷言可救 atom 出來（edge 丟、indices 取交集、壞 proposal skip）、不 raise；另斷言「全壞 → 零 proposal → session fail-closed」仍成立。`FakeAgentClient` 確定性、CI 不碰真 gemma4。

## 6. 順序與邊界

1. **A1 先**（`projects.yaml` 本機 config）。
2. **A2 + B**（repo code，同一 PR、base `main`、疊在 #98 上、PR body 註明依賴）：resolver fallback 映射 + lenient 驗證，皆 TDD。
3. A1+A2 落地後**重跑 live sample 驗證**歸屬改善 + fail-closed 率下降。

不開 openspec change（避免在未 merge 的 #98 spec 上做 MODIFIED delta 的混亂）；spec 對齊待 #98 進 main 後處理。本期以本設計文件 + PR 說明 + 測試為準。

## 7. 風險

- Part A：分桶是使用者個人 taxonomy；以「交付 repo 為主桶」對齊使用者意圖，noise 明確排除。可逆（config）。
- Part B：軟化 fail-closed 可能讓「品質差但格式合法」的 atom 落地（原本會被連坐丟掉）——以「硬錯仍 drop proposal」+ WARN log 緩解，品質把關交 canary 人工判 + 未來 SkillOpt。
- 疊在未 merge 的 #98 上：若 #98 先 merge，Part B 自動縮成乾淨 diff；若 Part B 先 merge 需注意 llm_promoter.py 不衝突（touch 不同行）。
