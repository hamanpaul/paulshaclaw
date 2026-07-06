## Context

完整設計：`docs/superpowers/specs/2026-07-06-p1-memory-three-gaps-design.md`。#197 三缺口；三案互不依賴、3 PR 平行、worker 各自 worktree（共用 checkout race 為既知坑）。

## Goals / Non-Goals

**Goals:**
- ① retrieval 覆蓋恢復（testpilot/serialwrap ~35%→>90%，paulshaclaw 不退化）+ 排除率遙測。
- ③ janitor reactivation 對 ledger 壞行免疫。
- ② park 地板收斂至 transport-only 或逐筆判定真無知識。

**Non-Goals:**
- 新 classifier 規則（① 是接線修正，用既有 `corpus_for_roots()`）。
- read 訊號回授 relevance/decay（#148 另案）。

## Decisions

1. **① scoped corpus 的 fallback 語意 = 不排除**：project 查無 roots → 空 corpus → 零排除。寧可多索引（噪音已有生產端過濾層），不再重演 silent 半盲。
2. **① 遙測門檻 40% WARN**：上次 65% 靜默排除三週才被發現；門檻進 build 輸出與 log，非 dashboard 專屬。
3. **② ops 先行、code 條件觸發**：先辨明殘留（快取時戳 < #190 merge）vs 新生；殘留只需清快取+reset budget 交背景 loop（**禁手動 dream run**——併發撞背景 loop 為既知坑）。step 2 才動 parser/prompt。
4. **② prose 容忍抽取的 fail-closed 邊界**：僅當散文中存在**唯一**頂層 JSON array 才抽取；多 array 或無 array → 維持現行失敗路徑。不放寬 schema 驗證。
5. **③ 容錯範圍限 import ledger 讀取路徑**：壞行 skip+計數入 warning；不改寫入端、不做 ledger 修復工具（YAGNI，live 壞行由 ops 一次清）。

## Risks / Trade-offs

- ① rebuild 後短清單構成改變（兩桶內容湧入）——offer 品質靠 #182 已上的排序/去重層承接；觀察一週。
- ② 清快取屬 runtime mutation：先備份 6 session 的 cache 檔；判定與處置逐筆記錄附回 #197。
- ③ skip 壞行可能掩蓋系統性寫入損壞 → warning 帶 skipped 計數，計數 >1 即值得人工看寫入端。
