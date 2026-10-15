# JOBS 執行身份

在 JOBS 工作列按 Enter／Space 或點展開箭頭，即可查看 executor、model、來源、執行狀態、card 與 job。三個分組軸都提供同樣明細；模型名稱完整保留，超寬可水平捲動。角色 persona 與既有 reason／next_actions／run_id 繼續保留。

| 顯示 | 意義 |
| --- | --- |
| 執行中 | producer 提供目前 running job 的身份 |
| 已派工 | producer 提供目前 in-flight job 的身份，狀態另列 |
| 上次執行 | 當前卡最後一次執行；不代表仍在跑 |
| 預定／未派工 | step 明示的預定身份，尚未建立實際 job |
| 未派工／身份未提供 | 缺乏可用身份；executor/model 以未提供呈現 |

舊 Cortex 快照、null、型別錯誤與未知來源皆使用 typed fallback；不把 persona、phase 或單獨存在的 job_id 當成身份證據。新的 executor 名稱與模型內容視為純文字，包含 CJK 或 `[bold]` 都不解析為 markup。

## 固定 producer 與驗收邊界

Cortex 候選 pin 為 `8d077b1dd3dbf1b0319bd9426a2b1be557d35c97`（[producer PR](https://github.com/hamanpaul/paulsha-cortex/pull/865)）。`tests/fixtures/workflow-execution-identity-828-status.json` 原樣來自該 SHA，SHA-256 為 `a843963af3547a95b1f61283c99058afa93722b61907ea40d25aa40e0724a575`。

consumer 測試包含三個 status sections、四種身份來源、新舊 schema、缺值與非法型別、長模型 literal、三軸顯示及 Textual refresh；隔離安裝的 producer 實跑 registry 建立多卡、retry、不同 repo／phase job，驗證顯示目前或上次實際執行者。

2026-10-15 本機驗證：新增回歸先見 12 failed，修正後 focused／alignment 為 69 passed；完整 gate 為 1058 passed、34 subtests passed，僅既有 tarfile deprecation warning。preflight 的 policy、OpenSpec 與完整 tests 全部 PASS。另建 wheel 安裝於隔離 venv，以 `python -I` 確認 consumer 來自 site-packages，再跑同源 fixture、實際 producer 與 Textual 刷新，輸出 `INSTALLED PRODUCER -> INSTALLED CONSUMER PASS`。有界獨立 consumer review 無新 finding。

尚未完成的 producer 驗收：該 SHA 與已核對的 Cortex main `4572f19ddad68e09e8ca23f64c7cb38909c28d66` 仍接受缺 repo 的 job，且 manifest 有 run_id、缺 card 時會忽略明示的 repo／phase 不符。consumer status 缺少完整來源 binding，無法自行補證；這項缺口須由 Cortex 修正並更新 pin 後才可完成端到端結案。服務與共享 runtime 未部署。
