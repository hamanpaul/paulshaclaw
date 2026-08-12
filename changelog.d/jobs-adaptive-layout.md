---
type: feat
---
JOBS 面板三合一（#308，owner 指定）：(1) **整列寬度自適應**——state／name 欄依本批 rows 自然寬伸縮（state 6..20、name 下限 12），剩餘全給 trailer，寬面板全名不省略、省略號成為最後手段；`JobsPanel` 快取 groups 並新增 `on_resize`，resize 立即以新寬度重排不等 status tick；欄間距由模板固定空格保證。(2) 狀態 label `N phase` → `N ph`。(3) `status_style` 改五桶制、glyph 統一 `•`：wait-for-start 白／working 綠／broke 紅／wait-confirm 橘／finished 灰，未知維持中性藍灰；WORK／DETAIL 共用同一純函式一併統一。
