## Context

完整設計＋審查修正：`docs/superpowers/specs/2026-07-06-g2-persona-enforce-design.md`。現行 scope_ci：`find_latest_manifest`＝mtime 最新（非 PR-bound）、no-manifest→skip、全路徑 shadow 恆 exit 0。

## Goals / Non-Goals

**Goals:** builder 先 enforce；違規 PR 被擋；省略 manifest 不再是繞過。
**Non-Goals:** persona/write_paths 內容調整；一次全 persona 翻牌；required check 自動化（owner 手動）。

## Decisions

1. **PR-bound manifest**（審查修正）：以 head branch↔slice_id 匹配取 manifest；不匹配/多筆→視同無 manifest。mtime-latest 可被無關 manifest 汙染，棄用。
2. **no-manifest fail-closed on governed paths**（審查修正，關鍵）：enforce 下變更 ∩ enforce-personas write_paths 聯集 ≠ ∅ 且無 PR-bound manifest → exit 1；豁免只走顯式 label。「治理資產被無身分變更觸碰」不得因缺 manifest 放行。
3. **分批 rollout**：首翻 builder（write_paths 最窄）；governed 聯集＝builder 範圍，誤傷面最小；每加一 persona 前重估。
4. **未知 enforcement 值→shadow＋warning**（fail-safe：設定錯字不誤殺）。
5. **required check 為 owner 手動步驟**：試點 ≥1 週誤傷記錄於 #124 後才設。

## Risks / Trade-offs

- 人工 PR 觸 governed paths 需 label：顯式豁免的摩擦是設計代價，試點期統計。
- governed 聯集過寬放大誤傷：由分批 rollout 控制。
