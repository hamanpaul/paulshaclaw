## Context

完整設計見 `docs/superpowers/specs/2026-06-25-stage2-promoter-noise-governance-design.md`（brainstorming 產出）。Stage 2 knowledge 553 slice 中 86% 為結構/空殼噪音；噪音的精準訊號為「slice body 第一行是 importer 結構段落 heading」。#139 P0/P1（escaping + 韌性）已於 #141 merge，本 change 處理 P2 品質段。

## Goals / Non-Goals

**Goals:**
- 產生端阻斷結構 echo / 空殼 / placeholder 寫入 knowledge。
- 回溯 hard delete 既有 474 噪音、出稽核 manifest、重建 MOC。
- 判準單一真相源、以 body 內容為準、不誤刪有真內容者。

**Non-Goals:**
- splitter 層跳過結構段落（未來最佳化）。
- title 重生、project 重解析（untitled / no-project 的品質問題另案）。
- promoter prompt 調校。

## Decisions

- **Approach A：共用 `classify_noise` + 產生端 skip + 一次性 prune CLI**。否決 B（修 splitter/importer：耦合模板、抓不到 LLM echo）、C（只 MOC 表面隱藏：與 hard delete 不符）。
- **module 落點** `paulshaclaw/memory/noise.py`（中性純函式，producer 與 CLI 共用）。
- **回溯 hard delete + manifest**：source session 在 archive 為真相源、產生端修好後不再生 → 安全。
- **判定僅看 body 第一行 heading**（不推斷段落範圍），對得上實據；`## Summary` 列入 structural-echo。
- **prune 不改 append-only ledger**：`build_mocs._active_slices` 只讀現存檔，刪檔後自然不入 MOC；dangling slice_id 變 inert。

## Risks / Trade-offs

- **誤刪風險**：以 body 內容（非 metadata）為準、untitled/no-project 真內容保留，降低誤刪；`--dry-run` 預設 + manifest 提供人工關卡與稽核回溯。
- **hard delete 不可逆**：以 source session archive 保底（必要時可重跑 atomize 重建），並要求 `--apply` 顯式觸發。
- **`## Summary` 納入刪除**：可能犧牲極少數有意義的 1 行摘要；經決策取捨後接受（非知識粒度）。
