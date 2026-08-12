---
type: feat
---
JOBS 面板顯示層去贅詞（#302，owner 指定字面）：`workflow-tracked` → `[wf]-tracked`、`subagent-build` → `[sub]-build`（單列主欄、多 phase 群狀態列、phase 子行一體適用）、branch 前綴 `feature/` → `feat/`（於 `_fit_trailer` 寬度計算前替換，省下的欄位實際回收）。縮寫表集中於 `_LABEL_ABBREVS` 一處；model 層屬性、style key 與 detail 行的可複製命令維持原始字串，cortex 資料契約零變更。
