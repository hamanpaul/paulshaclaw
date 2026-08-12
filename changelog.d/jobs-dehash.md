---
type: feat
---
JOBS 面板去 wf-hash（#305）：多 phase 群主欄改放 branch（`feat/` 縮寫＋中段省略；無 branch 才退回 workflow id），單列 trailer 的 workflow_id 改為「有 branch 就不顯示、無 branch 才當最後身分」，job_id 一律退場。機器 id 對 operator 是噪音；對帳用的原始 slice_id 仍在 needs_human detail 行的可複製命令裡。取捨：同 branch 的兩次 workflow run 在面板上不再可區分，精確對帳走 detail 與 manifest。
