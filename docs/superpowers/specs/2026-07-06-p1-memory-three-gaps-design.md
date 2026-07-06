---
dispatch: hold
slice_id: p1-memory-three-gaps
plan: docs/superpowers/plans/2026-07-06-p1-memory-three-gaps.md
depends_on: []
---

# P1 — Stage 2 記憶中樞三缺口修復 設計

> 日期：2026-07-06 ｜ 狀態：草案（待覆審）｜ 對應 issue：#197（2026-07-05 運作評估）
> 交付形態：**3 個獨立 change / 3 PR，可平行派工**（沿用 #174–#178 多 worker 模式；互不依賴，merge 序自由）

## 0. 共同背景

2026-07-05 線上評估（#197）：整條 capture→atomize→LLM 蒸餾→knowledge→MOC→retrieval→consumption 鏈健康，殘留三缺口。本 spec 一檔三案，各自可獨立實作與驗收。

---

## Gap ①：retrieval 索引半盲（M）——功能紅利最大

### 問題
`retrieval.db` 僅索引 166/344（48%）knowledge slices。根因：`build_index` 的噪音排除用**全域 broad instruction corpus**（`instruction_corpus.load_corpus()` 預設），把 testpilot／serialwrap 兩大桶各 ~65% 的「AGENTS.md 內嵌真架構知識」誤判為 doc-fragment 排除於檢索之外（純檢索側排除、可恢復）。prompt-time 短清單對這兩桶半盲。

### 改法
- `build_index` 改 **per-project scoped corpus**：對每個 project 桶，只用**該 project 自己的 instruction roots**（`~/.agents/config/projects.yaml` 的 root 映射）經既有 `corpus_for_roots()` 建 corpus 做比對；查不到 roots 的 project → 空 corpus（不排除，寧可多索引）。
- 本質是**接線修正**：`corpus_for_roots()` 於 #147 已交付，本案不新增 classifier 規則。
- `pool_exclude_reason` 語意保留；rebuild index 為交付步驟之一。

### 防再犯（遙測）
- index build 記 per-project `indexed / excluded / exclude_rate`；**exclude_rate > 40% 即 WARN**（進 build 輸出與 log）。上次 65% 靜默排除半盲三週——不允許 silent cap。

### 測試與驗收
- 單元：兩 project fixture，A 的 instruction 內容出現在 B 的 slice → B 不因 A 的 corpus 被排除（scoped 隔離）；roots 缺席 → 零排除。
- 驗收：rebuild 後 testpilot/serialwrap 覆蓋 ~35%→>90%；paulshaclaw 桶不退化；`retrieval.db` 列數 ≈ 磁碟 slices − 真噪音；prompt-time 短清單能 offer 兩桶內容；WARN 遙測在人工造 50% 排除的 fixture 上觸發。

---

## Gap ③：janitor reactivation 被 import ledger 壞行整段中止（S）——最便宜

### 問題
`import.jsonl` 一行損毀（空行）→ janitor reactivation 掃描直接 abort（每輪 warning `import.jsonl unreadable; reactivation signals skipped`），`decayed`/`reactivated` 恆 0，reactivation 實質失效。

### 改法
- ledger 逐行解析改**容錯**：壞行（空行／壞 JSON）skip + 計數，warning 改報 `skipped N bad line(s)`，其餘行照常處理；不再 raise 中止整段。
- ops 收尾：清掉 live `import.jsonl` 現存壞行（單行、可逆，先備份）。

### 測試與驗收
- 單元：fixture 含（空行、壞 JSON、正常行）混排 → 正常行全處理、skip 計數正確。
- 驗收：live janitor 該 warning 消失；reactivation 恢復可產生非零結果的能力。

---

## Gap ②：LLM promote park 地板複驗（S~M）——先診斷後動刀

### 問題
`dream status` = partial、backlog 13：~6 session content-park（「no JSON array found」23–33 次、budget 耗盡、poisoned cache retained）+ 4 session transport timeout（正常自愈路徑）。#185 已由 #190（物件包殼 unwrap + prompt 加固）close，但線上地板仍在——**殘留 vs 新生未辨明**。

### 改法（兩步，step 2 條件觸發）
- **step 1（ops，無 code）**：對 6 個 parked session 檢查 `runtime/cache/atomize/` 快取時間戳與 retry budget sidecar——
  - 快取早於 #190 merge → 判**殘留**：清該 session 快取 + reset retry budget → 讓**背景 loop**以 #190 新碼自然重試。**禁止手動觸發 dream run**（與背景 loop 撞併發為既知坑）。
  - 產出：複驗記錄（session × 判定 × 處置）附回 #197。
- **step 2（僅當 step 1 後仍有 session 以 #190 新碼失敗）**：
  - atomizer prompt 對「散文誤答」類再加固（模型把任務當執行而非回傳 JSON 的模式）。
  - parser 增加 prose 包 JSON 的容忍抽取（在既有 unwrap 之上，僅當散文中存在唯一頂層 JSON array 時取用；歧義即 fail 保持 fail-closed）。

### 測試與驗收
- step 2 若觸發：parser 新容忍路徑的正反向單元測試（唯一 array 抽取成功／多 array 歧義拒絕）。
- 驗收：backlog 收斂至 transport 類 only；content-park = 0 或逐筆判定「真無知識」記錄在案。

---

## 交付與風險

- 3 PR 平行；worker 各自 worktree（共用 checkout race 為既知坑）。
- Gap ① 動 `build_index` 需 rebuild：屬檢索側、knowledge 檔零觸碰，可逆。
- Gap ② step 1 是 ops：动 runtime cache 前備份該 6 session 的 cache 檔。
