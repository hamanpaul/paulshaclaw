# Stage 2 — Topic 9：sync-back gate（可執行治理關卡）設計

- 日期：2026-06-06
- 範圍：T9 = 把「sync-back gate」從**文件條件**做成**可執行/可驗的關卡**。治理「何時可把專案調校過的 paulsha-memory 套件回寫 `hamanpaul/custom-skills`」。Stage 2 最後一塊。
- 命名：`paulsha-memory` = Stage 2 整體系統(code modules,非 skill)。**「paulsha-memory skill」概念已退場**(roadmap v0.5):消費走 hook(強制)+ MCP(可選);故 sync-back 的**實體 = 可安裝套件**(memory 模組 + hooks + install.sh + 將來 MCP server),非 SKILL.md。
- 範圍界定:本 change **只做 gate checker**(驗 5 條件 → verdict + 報告 + sync manifest;不自動複製進 staging、不 push 外部 repo)。實際複製/推送留人工(對外操作先確認)。
- 前置(皆完成):T1–T8 + SkillOpt + T6。既有素材:`stage2-memory-governance` spec 的 5 條 gate requirement、`custom-skills/paulsha-memory/README.md` staging scaffold、`docs/superpowers/workstreams/stage2-paulsha-memory/{evidence/,review.md}`、`stage2_integration_check.sh`。

---

## 0. 與既有素材的關係(headline)

T9 **零重複**:把已存在的「文件條件」轉成程式化檢查,重用既有資產:

| gate 條件 | 既有素材 | T9 怎麼驗 |
|---|---|---|
| (1) importer/classifier/replay 過測 | 既有 test 模組 | **實跑** unittest 目標模組,斷言全綠 |
| (2) decayed/reactivation 規則+證據 | janitor 測試 + evidence 檔 | 跑對應測試 + 檢查 evidence 在位 |
| (3) evidence 在位 | `…/stage2-paulsha-memory/evidence/` | 檢查必要檔存在且非空 |
| (4) review.md 無 blocking | `…/stage2-paulsha-memory/review.md` | 解析 `## 結論` 段:有可合併結論且無阻斷標記 |
| (5) 未擴充 Stage 3 frontmatter | `lifecycle.schema.REQUIRED_FRONTMATTER_FIELDS` | 斷言必填欄位集 ⊆ Stage 3 canonical `{slice_id, artifact_kind, supersedes, checksum}`(+phase),Stage 2 沒新增必填欄 |

---

## 1. 範圍

### In scope
- `paulshaclaw/memory/syncback/gate.py`：`evaluate_gate(repo_root, *, now, run_tests=True) -> GateVerdict`,逐條驗 5 條件,回結構化 verdict。
- `paulshaclaw/memory/syncback/cli.py`：`psc memory syncback check`,印 verdict + 報告 + sync manifest,exit 0(全過)/非 0(任一 fail)。
- 註冊 `syncback` 子命令於 `paulshaclaw/memory/cli.py`。
- `paulshaclaw/memory/syncback/README.md`。

### Out of scope
- ❌ 實際複製進 `custom-skills/paulsha-memory/`(repo 內 staging)。
- ❌ push 到 `hamanpaul/custom-skills` 外部 repo(對外、人工授權)。
- ❌ 套件打包/匯出工具。
- ❌ 改 importer/atomizer/janitor 等既有行為。

### 約束
- **fail-closed**(與 wake-up 相反):任何讀不到檔、測試 error、解析失敗 → 該條 FAIL → gate FAIL。governance gate 寧可錯擋不錯放。
- **決定性**:`now` 注入;條件檢查為純函式(條件 1/2 跑測試是受控 subprocess,結果只取 pass/fail)。
- **唯讀**:gate 不寫 canonical、不改任何被驗素材;只讀 + 跑測試 + 輸出報告。

---

## 2. 架構與元件

```
paulshaclaw/memory/syncback/
├── __init__.py        # 匯出 evaluate_gate, GateVerdict
├── gate.py            # 5 條件檢查 + verdict 聚合
├── cli.py             # psc memory syncback check
└── README.md
```

| 元件 | 職責 | 依賴 | 介面 |
|---|---|---|---|
| `gate.py` | 逐條驗 5 條件、聚合 verdict、組 sync manifest | unittest(subprocess)、`lifecycle.schema`、stdlib | `evaluate_gate(repo_root, *, now, run_tests=True, test_runner=...) -> GateVerdict` |
| `cli.py` | CLI 入口、印報告、決定 exit code | gate | `psc memory syncback check [--no-run-tests] [--json]` |

- **`test_runner` 可注入**:預設用 subprocess 跑 `python3 -m unittest <modules>`;測試時注入 fake runner → 全閉環確定性,不真跑測試。

---

## 3. 資料模型

### GateVerdict
```python
@dataclass(frozen=True)
class ConditionResult:
    id: str            # "tests" | "decay_evidence" | "evidence_present" | "review_clear" | "schema_unextended"
    name: str
    passed: bool
    detail: str        # 人讀說明(通過/失敗原因);永不含密鑰

@dataclass(frozen=True)
class GateVerdict:
    ok: bool                       # 全條件 passed 才 True
    ts: str                        # 注入的 now
    conditions: tuple[ConditionResult, ...]
    sync_manifest: tuple[str, ...] # ok 時列「會回寫哪些路徑」;非 ok 為空
```

### 5 條件判定細節
- **(1) tests**：跑 importer/classifier/replay 測試模組(預設 `test_adapters`/`test_classifier`/`test_*importer*`/`test_*replay*`/`test_*selector*`);runner 回傳非 0 或 raise → fail。
- **(2) decay_evidence**：跑 decayed/reactivation 相關測試(janitor scanner/lifecycle)+ 檢查 evidence 目錄含對應證據檔;任一缺 → fail。
- **(3) evidence_present**：`docs/superpowers/workstreams/stage2-paulsha-memory/evidence/` 下必要檔(`README.md`、`stage2-integration-template.md`)存在且非空。
- **(4) review_clear**：`…/review.md` 必須有 `## 結論` 段;判定 pass iff 結論含可合併語意(`可合併`/`mergeable`)且**無**阻斷標記(出現「阻斷性問題」且未被「無」否定、或 `BLOCKING`/`BLOCKER`)→ 否則 fail。
- **(5) schema_unextended**：`set(lifecycle.schema.REQUIRED_FRONTMATTER_FIELDS)` ⊆ canonical `{slice_id, artifact_kind, supersedes, checksum, phase}`;若 Stage 2 端新增了任何必填欄位(超集)→ fail。

### sync manifest(ok 時)
列出「通過後**會被回寫**的套件路徑」(供人工確認,不執行):
`paulshaclaw/memory/**`(模組)、`paulshaclaw/memory/hooks/**`、`install.sh`/`uninstall.sh`、(將來)MCP server。實際路徑由 gate 從一份 `syncback-manifest`(常數清單)產出。

---

## 4. 資料流

```
psc memory syncback check
  → evaluate_gate(repo_root, now=<注入>, run_tests=True)
       逐條跑 5 檢查(fail-closed:例外即該條 fail)
       聚合 ok = all(passed)
       ok ? sync_manifest = 套件清單 : ()
  → 印報告(每條 ✓/✗ + detail)+ manifest
  → exit 0 if ok else 1
（任何條件無法判定 → 該條 fail、gate fail、exit 1;絕不誤放）
```

---

## 5. 錯誤處理 & Guardrails

| 失敗 | 處置(fail-closed) |
|---|---|
| 測試 runner raise / 非 0 | 該條 fail、detail 記原因(不含密鑰)、gate fail |
| evidence/review.md 缺或不可讀 | 該條 fail |
| review.md 無 `## 結論` 段 | review_clear fail(寧可錯擋) |
| `lifecycle.schema` import 失敗 | schema_unextended fail |
| repo_root 不對 | 各檔檢查 fail → gate fail |

| # | Guardrail | 保證 |
|---|---|---|
| S1 | fail-closed | 任何不確定 → fail;治理關卡不誤放 |
| S2 | 唯讀 | gate 不寫 canonical、不複製、不 push |
| S3 | 決定性 | `now` 注入;test_runner 可注入 → 測試閉環不真跑 |
| S4 | 不洩漏 | detail 永不含密鑰/例外堆疊原文 |
| S5 | 零重複 | 重用既有測試、`lifecycle.schema`、既有 evidence/review.md |

---

## 6. 測試策略(TDD,注入 fake runner → 確定性)

| 測試檔 | 覆蓋 |
|---|---|
| `test_syncback_gate.py` | 全綠路徑(fake runner 全 pass + fixtures 齊 → ok、manifest 非空、exit 邏輯);逐條 fail(測試 fail、evidence 缺、review 有阻斷、schema 被擴充);fail-closed(runner raise、檔缺、review 無結論 → 對應條 fail);`now` 注入;detail 不含敏感字 |
| `test_syncback_cli.py` | `check` 全過 → rc 0;任一 fail → rc 1;`--json` 輸出 GateVerdict;`--no-run-tests` 跳過條件 1/2 的實跑(標 skipped→視為 fail,因 governance 不可略測)|
| `test_syncback_doc.py`(可選) | README 文件化 fail-closed、唯讀、不自動推外部、5 條件 |

- 全程注入 fake test_runner,**不真跑** unittest;真跑路徑由 `psc memory syncback check` 手動驗。
- 跑法:`python3 -m unittest discover -s paulshaclaw/memory/tests`。

---

## 7. 解鎖的後續(非本 change)
- `psc memory syncback stage`：通過後複製套件進 `custom-skills/paulsha-memory/`(repo 內 staging)。
- `psc memory syncback push`:人工授權後 push 外部 `hamanpaul/custom-skills`。
- 套件打包/匯出(含 MCP server)。
- 接進 CI:PR 觸發 syncback gate 作為回寫前的硬 gate。
