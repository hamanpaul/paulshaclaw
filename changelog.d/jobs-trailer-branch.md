---
type: feat
---
JOBS 面板 workflow job 的次要欄（trailer）新增 **branch**（#292）：排在 project 之後、workflow id 之前，`recent_done`／`attention` 條目的 `feature/<N>-<slug>` 分支名直接可見，operator 不用開 handoff manifest 就能辨識 job 屬於哪個 issue——上游 `repo` 因 hamanpaul/paulsha-cortex#465 目前全為 null，branch 是唯一的歸屬線索。多 phase 群組 lead 優先、lead 沒值（in_flight／ready／held 上游不帶 branch）時取第一個有值的 phase；寬度不足時沿用 `_fit_trailer` 既有「從尾端整項丟棄、標示省略」語意，不硬切分支名。cortex#465 落地後同列 project 欄自動補上 repo 名，兩者互不衝突。
