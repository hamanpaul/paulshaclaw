---
type: change
issue: 264
---
cockpit JOBS 面板改以 workflow 分組摘要顯示（#264）：現場資料天然是 `project → workflow → phase` 三層，攤平後同一個 workflow 的 3~4 個 phase 各佔一列，把面板行數吃光——實測 51 列其實只有 22 群、11 筆 `needs_human` 只代表 6 件事，收攏後 10 行預算裝得下全部要人動手的群。多 phase 群顯示為 `4 phase 全待裁決`，phase 明細與共同原因移到細節行；`held` 這類會自己解開的不佔細節行（其 reasons 攤開實測可達 500+ 字）；缺 reason 以次要欄附註標示而非獨佔一行。另補上 `needs_human` 缺失的狀態樣式——最該亮起來的狀態先前是中性灰點。
cockpit JOBS 面板現在標示每筆 job 屬於哪個 project（#264）：manager 是跨 repo 派工的，同一個面板會混進別的 repo 的 workflow——現場 10 筆 `needs_human` 全屬 `paulsha-cortex`、paulshaclaw 一筆都沒有，但畫面上完全看不出來。`repo` / `workflow_repo` 以前向相容方式讀取並顯示為次要欄首位；上游未提供時留白，不猜歸屬。
cockpit JOBS 面板改以「要人動手的先講」排序並帶出可執行下一步（#264）：`needs_human` 排到最前面（現場 51 列 / 11 列等人工時，原本一列都露不出來）、attention 與 held 本來就有的 `reason` / `next_actions` / `job_id` / `branch` 不再被丟棄、`recent_done • needs_human` 標示為「待裁決」而 attention 標示為「阻塞中」以區分兩種語意、`wf-<hash>-` 執行環境前綴降為次要欄。有 `next_actions` 時直接給可複製執行的 `cortex slice-action … --actor $USER`；上游未帶 reason／action 時明說是契約缺口，不留無意義狀態列；被行數預算截掉的列數也會顯示出來。
