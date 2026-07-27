### Changed
- cockpit JOBS 面板改以「要人動手的先講」排序並帶出可執行下一步（#264）：`needs_human` 排到最前面（現場 51 列 / 11 列等人工時，原本一列都露不出來）、attention 與 held 本來就有的 `reason` / `next_actions` / `job_id` / `branch` 不再被丟棄、`recent_done • needs_human` 標示為「待裁決」而 attention 標示為「阻塞中」以區分兩種語意、`wf-<hash>-` 執行環境前綴降為次要欄。有 `next_actions` 時直接給可複製執行的 `cortex slice-action … --actor $USER`；上游未帶 reason／action 時明說是契約缺口，不留無意義狀態列；被行數預算截掉的列數也會顯示出來。
