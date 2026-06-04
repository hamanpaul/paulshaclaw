# Stage 2 — paulshaclaw 專用 SkillOpt 層（atomize-skill 自我精煉）設計

- 日期：2026-06-04
- 範圍：在 paulshaclaw 內新增 code module `paulshaclaw/memory/skillopt/`，把 evolve 的通用 SkillOpt 閉環 **vendor（複製＋rename）** 進來，並補上 atomize 任務專用的 rollout / scorer / val_set，呼叫 `optimize_skill` 精煉 `paulshaclaw/memory/atomizer/skills/atomize-knowledge-slice.md`。
- 命名：`paulsha-memory` = Stage 2 整體（`~/.agents/memory` 維護者，非 skill）；本層是 **code module**，非 skill；唯一被優化的 SKILL.md = `atomize-knowledge-slice.md`。
- 模式：同 `obs-auto-moc → paulsha-mem-moc`。`evolve`（custom-skills，通用）先長出 generic SkillOpt 能力；paulshaclaw base 在其上，**把 loop 複製過來 rename 成自己的樣子**（不跨 repo 呼叫）。
- 前置（皆已完成並 merge）：
  - evolve generic SkillOpt（`custom-skills/evolve/scripts/skillopt.py` + `skillopt_optimizer_acp.py` + `codex_exec_acp_adapter.py`，PR #5）。
  - T2 importer（`paulshaclaw/memory/importer/`：session 掃描、`project_resolver` 專案解析、inbox 寫出）。
  - T3 / T3.2 atomizer（`paulshaclaw/memory/atomizer/`：`Fragment`、`build_prompt(skill_text, fragments, known_projects)`、`LLMPromoter.promote`、`agent_exec`）。
- 參考：microsoft/SkillOpt（trainable skill artifact + validation gate）；`~/notes`（Obsidian vault）**僅作 reference rubric**，非 gold、非 input 來源。

---

## 0. 與 Stage 2 其他 topic 的邊界（headline）

SkillOpt 層**只新增三件、零重複**，既有能力一律重用：

| 能力 | 擁有者（既有 topic） | 本層怎麼用（不重做） |
|---|---|---|
| session 掃描 → 寫 `inbox/<bucket>/<tool>/<day>/<session>.md` | importer (T2) | val_set builder **讀 inbox**，不碰 session 檔 |
| project 解析（含**不同 folder 同專案**，依 `projects.yaml` roots/remotes） | importer/`project_resolver` (T2) | 直接讀 inbox frontmatter 的 `project` 分層，**不重解** |
| atomize rollout：`build_prompt(skill_text, fragments, known_projects)` + `LLMPromoter.promote` | atomizer (T3/T3.2) | rollout = 注入候選 `skill_text` 呼叫既有 LLMPromoter，**不另寫拆分器** |
| 每日 atomize + janitor + moc 編排 | dream (T5) | SkillOpt 是**獨立離線 CLI**，本 change **不**接進 dream loop |

**關鍵修正：**「不同 folder 同專案（看 repo）」是 `project_resolver` 用 roots/remotes 設定**確定性**解掉的，**不是 LLM-judge 的工作**。故 judge 職責收斂為單純的原子化品質四項（§4）。project 歸屬不進 judge。

---

## 1. 範圍與邊界

### In scope
- `paulshaclaw/memory/skillopt/loop.py`：vendor 自 `evolve/scripts/skillopt.py`（機械複製＋rename，行為不改）。
- `paulshaclaw/memory/skillopt/optimizer_acp.py` + `codex_exec_acp_adapter.py`：vendor 自 evolve 對應檔（optimizer = codex ACP，提 bounded skill edit）。
- `paulshaclaw/memory/skillopt/rollout.py`：atomize rollout adapter（注入候選 `skill_text` → `LLMPromoter`（gemma4 via `agent_exec`）→ slices）。
- `paulshaclaw/memory/skillopt/scorer.py`：結構分（train 排序）+ LLM-judge（val gate，四項品質）。
- `paulshaclaw/memory/skillopt/valset.py`：讀 inbox fragments，依 `project` 分層做確定性 train/val 切，配 `~/notes` reference rubric 為 `gold`。
- `paulshaclaw/memory/skillopt/cli.py`：driver，組 rollout/score/val_set 呼叫 `optimize_skill`；CLI entry `psc memory skillopt run`。

### Out of scope
- ❌ 重做 session 掃描 / project 解析（importer 已有）。
- ❌ project 歸屬進 LLM-judge（`project_resolver` 確定性處理）。
- ❌ 接進 dream / `self_evolve_cycle` 每日 loop（後續 change）。
- ❌ 多 epoch / 大 budget / learning-rate 排程（先最小閉環 budget=1）。
- ❌ 改 atomizer / importer 任何既有行為（只**讀**其輸出、**注入** skill_text）。

### 約束（核心，繼承自 generic）
- **gate 嚴格**：候選只在 `val` 平均分 **嚴格 > baseline + threshold** 且 skill 合法才覆寫 → 非確定性 rollout/judge **不可能讓 skill 變差**（最壞=不動）。這是 SkillOpt 能立刻出貨、堵住「LLM 一直被推遲」的核心。
- **確定性**：注入 `now`（不取牆鐘）；train/val 切分以 `session_id+fragment_index` 排序後雜湊，跨次重現。
- **可回滾**：`optimize_skill` 覆寫前備份舊版到 `skillopt-history/`。
- **單一寫者**：`atomize-knowledge-slice.md` 由 SkillOpt 寫、atomizer 讀；無並發寫。

---

## 2. 架構與元件

```
paulshaclaw/memory/skillopt/
├── __init__.py
├── loop.py                  # vendor: optimize_skill() 通用閉環（不改行為）
├── optimizer_acp.py         # vendor: make_acp_optimizer（codex ACP 提 bounded edit）
├── codex_exec_acp_adapter.py# vendor: codex ACP 呼叫器（optimizer 依賴）
├── rollout.py               # atomize rollout：skill_text → LLMPromoter → slices
├── scorer.py                # structural（train）+ LLM-judge（val gate）
├── valset.py                # inbox fragments → 依 project 分層 train/val + reference gold
└── cli.py                   # driver：組 hook 呼叫 optimize_skill；psc memory skillopt run
```

| 元件 | 職責 | 依賴 | 主要介面 |
|---|---|---|---|
| `loop.py` | 通用最小閉環 + record（vendored，零修改） | stdlib | `optimize_skill(skill_path, *, rollout, score, train_set, val_set, optimizer, budget=1, accept_threshold, now, record_path, failure_count) -> dict` |
| `optimizer_acp.py` | codex ACP → optimizer hook | `codex_exec_acp_adapter` | `make_acp_optimizer(*, runner=...) -> Callable[[str, list], str]` |
| `rollout.py` | 注入 skill_text 跑 atomize | atomizer（`LLMPromoter`/`build_prompt`/`Fragment`）、`agent_exec` | `make_atomize_rollout(agent_client, known_projects, config) -> Callable[[skill_text, input], output]` |
| `scorer.py` | 結構分 + LLM-judge | judge agent_client（注入） | `structural_score(output, gold) -> float`；`make_hybrid_score(judge_client) -> Callable[[output, gold], float]` |
| `valset.py` | inbox → 分層 train/val + reference gold | importer 輸出（讀檔）、`~/notes` reference | `build_valset(*, inbox_root, reference_root, val_ratio=0.2) -> dict{"train":[...],"val":[...]}` |
| `cli.py` | driver + CLI | 上列全部 | `psc memory skillopt run [--budget N] [--dry-run]` |

### 三種模型角色（皆可注入 → 測試用 fake）
- **rollout = gemma4**（via `agent_exec` 跑 `LLMPromoter`）：依候選 skill 把 fragments 拆成 slices。
- **optimizer = codex ACP**（vendored）：讀低分案例，提一個 bounded skill edit。
- **judge = 注入 agent_client**（建議較強模型 / codex；可設定）：val gate 評原子化品質。

---

## 3. 資料模型

### val item（沿用 generic `{"id","input","gold"}` 介面）
```python
{
  "id": "<session_id>#<fragment_index>",     # 確定性 id
  "input": [Fragment, ...],                   # 該單元的 inbox fragments（importer 產出）
  "gold": {                                    # reference rubric，非 1:1 目標
    "project": "<slug>",                       # importer 已解析（分層用）
    "reference_slices": [ {"title","body","tags"} , ... ]  # ~/notes 同域範例（語意內容，忽略 frontmatter）
  },
}
```

- `gold` 取自 `~/notes` 的「語意內容」（title + body + 概念），**忽略 Obsidian frontmatter 格式**（先前確認方案 a）。judge 拿它當「好原子化長相」的標竿，不做欄位比對。
- `~/notes` 無對應域時 `reference_slices` 可為空 → judge 退回純 skill principles 評分（仍可運作）。

### train/val 切分（確定性、按 project 分層）
1. 掃 importer 產出的 inbox fragments，依 frontmatter `project` 分組。
2. 每 project 內：item 依 `(session_id, fragment_index)` 排序 → 對 `sha256(id)` 取模做 80/20，前 20% 進 val、其餘 train。
3. 結果合併：`train` = 各 project train 聯集；`val` = 各 project val 聯集 → val 同含各域。
4. 跨次重現（同輸入 → 同切分）；無牆鐘、無亂數。

### gold reference 來源（`~/notes`，僅 reference）
- 掃 `~/notes/{TechVault,WorkVault,ObsToolsVault}` 帶 `atomized_from` 的子筆記，抽語意內容；PersonalVault 排除（隱私）。
- 與 input 的配對採「同域近似」：依 tags / 關鍵詞把 reference 歸到最接近的 project bucket 當該域標竿（**僅供 judge 參考**，非評測答案，故不需精準）。

### optimizer 契約 / `optimize_skill` 回傳 / record JSONL
- 全部沿用 generic（見 `evolve/docs/skillopt-design.md` §3）：回傳含 `accepted/baseline_score/candidate_score/improvement/reason/...`；record 只存 scores/counts/decision；error 結果 sanitized / fail-closed。
- `record_path` = `~/.agents/memory/runtime/ledger/skillopt.jsonl`（append-only）。

---

## 4. Scorer 設計

沿用 generic 的 `score(output, gold) -> float`（絕對分 0–1），**不改通用迴圈**。output = rollout 產出的 slices；gold = §3 的 reference rubric。

### (A) 結構分 — 用於 train 失敗排序（便宜、呼叫多次免費）
確定性、無 LLM。`structural_score(output, gold) -> float`，加權平均下列訊號（0–1）：
- **顆粒度接近度**：`output` slice 數 vs `gold.reference_slices` 數的接近度。
- **概念覆蓋率**：gold 概念（title 關鍵詞）有多少在某個 output slice 出現。
- **one-concept-per-slice**：每個 output slice 是否聚焦單一概念（標題/段落啟發式）。
- **relation 有無**：slice 是否帶 relation/連結欄位（atomize skill 要求之一）。

train 階段以結構分對 train_set 排序，取最低 N 筆當 failures 餵 optimizer（generic 已實作）。

### (B) LLM-judge — 僅用於 val gate（貴而準，決定採納與否）
`make_hybrid_score(judge_client)` 回傳的 score = `α·structural + (1-α)·judge`（預設 α=0.4）。judge 對 output 給 0–1，**只評原子化品質四項**：
1. **子功能切分顆粒度**：同一 project 內的子功能是否被切到恰當大小（不過粗、不過碎）。
2. **概念邊界**：每片是否單一清晰概念，無跨概念混雜。
3. **one-concept-per-slice**：對照 skill 原則。
4. **relation 合理性**：slice 間關係是否正確、無孤島。

judge prompt 附上 `gold.reference_slices` 當「好原子化長相」標竿 + 被評 skill 的原則；**不評 project 歸屬**（importer 已定）。judge 失敗（逾時/例外）→ 由 generic 的 fail-closed 包住（該次回 error、skill 不變）。

> gate 用絕對分：baseline skill 與候選 skill 對**同一 val_set** 各算平均 `score`，候選嚴格更高才採納。保持 vendored 迴圈零修改（不採用需改介面的 pairwise）。

---

## 5. 資料流

```
psc memory skillopt run --budget 1
1. valset.build_valset(inbox_root, reference_root) → {train, val}   # 讀 importer 輸出，依 project 分層
2. rollout = make_atomize_rollout(gemma4_client, known_projects, cfg)
3. score   = make_hybrid_score(judge_client)                        # structural + judge
4. optimizer = make_acp_optimizer()                                 # codex ACP（vendored）
5. optimize_skill(
       skill_path = atomizer/skills/atomize-knowledge-slice.md,
       rollout=rollout, score=score, train_set=train, val_set=val,
       optimizer=optimizer, budget=1, now=<injected>,
       record_path = runtime/ledger/skillopt.jsonl,
   )
   # generic 內部：baseline(val) → train 結構分排序取 failures → codex 提 1 edit
   #   → 候選 valid? → 候選(val) hybrid 分 → gate 嚴格變好才備份+覆寫 skill
6. 印出 result（accepted / baseline / candidate / improvement / reason）
```

- `--dry-run`：只算 baseline、不呼叫 optimizer（等同 budget=0），印分數供觀察。
- atomizer 下次跑時自動讀到被精煉的 `atomize-knowledge-slice.md`（單一 artifact、單一寫者）。

---

## 6. 錯誤處理 & Guardrails

繼承 generic 全部 guardrail（G1 validation gate / G2 attempts 上限 / G3 備份+record safety / G4 task-agnostic / G5 fail-closed sanitized / G6 record 最小化），本層補充：

| 失敗 | 處置 |
|---|---|
| inbox 為空（系統剛部署） | val_set 為空 → `optimize_skill` raise `SkillOptError`（硬前置：沒資料不最佳化）；CLI 友善訊息「先跑 importer 累積 inbox」 |
| 某 project 樣本過少（<最小門檻） | 該 project 全進 train、不進 val（避免 val 單樣本噪音）；log 標明被降級的 project |
| `~/notes` reference 缺對應域 | `reference_slices=[]`；judge 退回 skill principles 評分（不中止） |
| gemma4 / codex / judge 任一逾時或例外 | generic fail-closed：該次回 `reason="error"`、skill 不變、record 只存 scores/counts/decision |
| `atomize-knowledge-slice.md` 缺/不可讀 | generic 回 sanitized error；skill 不變 |

| # | Guardrail | 保證 |
|---|---|---|
| L1 | 零重複既有能力 | session/project/atomize 一律重用 importer/atomizer，本層只讀其輸出 + 注入 skill_text |
| L2 | judge 不碰 project | project 由 `project_resolver` 確定性決定；judge 只評原子化品質四項 |
| L3 | 確定性切分 | train/val 依 `sha256(session_id#fragment_index)`；無牆鐘無亂數 → 跨次重現 |
| L4 | 離線、不影響線上 | SkillOpt 為獨立 CLI，不接 dream；最壞情況對線上 pipeline 零影響 |

---

## 7. 測試策略（TDD，注入 fake → 確定性）

| 測試檔 | 覆蓋 |
|---|---|
| `test_skillopt_loop.py` | vendored `optimize_skill` 行為與 evolve 一致（accept / reject 無改善 / reject 非法 / fail-closed / record 最小化 / `now` 注入）——確保複製未走樣 |
| `test_skillopt_rollout.py` | `make_atomize_rollout`：注入 `FakeAgentClient` → 候選 skill_text 確實傳入 `build_prompt`；輸出 slices 結構正確 |
| `test_skillopt_scorer.py` | `structural_score` 四訊號（顆粒度/覆蓋/one-concept/relation）確定性；`make_hybrid_score` 以 fake judge 驗 α 加權；judge 例外 → 由 loop fail-closed |
| `test_skillopt_valset.py` | inbox fixtures → 依 project 分層；確定性 80/20（同輸入同切分）；小樣本 project 全進 train；`~/notes` 缺域 → reference 空；PersonalVault 排除 |
| `test_skillopt_cli.py` | `psc memory skillopt run` 串接（注入 fake rollout/score/optimizer）；`--dry-run` 只算 baseline；空 inbox 友善錯誤 |
| `test_skillopt_doc.py`（可選） | 模組 README 文件化 gate / fail-closed / 不接 dream / judge 不碰 project |

- 全程注入 fake/mocked，**不呼叫真 codex/gemma4**。
- 跑法：`python3 -m unittest discover -s paulshaclaw/memory/tests`（沿用既有 test 佈局）。

---

## 8. 解鎖的後續（非本 change）
- 接進 dream / `self_evolve_cycle`：每日（或週期）自動跑一輪最小閉環。
- 調高 budget / 多 epoch；judge 改 pairwise（需擴充迴圈介面）。
- val_set 來源從 inbox 升級為 `~/.agents/memory/knowledge/<project>/` 人工複核過的成品（更貼真實 gold），`~/notes` 完全退場。
