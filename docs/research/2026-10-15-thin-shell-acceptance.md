# Claw 薄操作層：有界驗收與停止決議

本紀錄完成 [issue 337](https://github.com/hamanpaul/paulshaclaw/issues/337) 的剩餘查核，
保留 bot／cockpit／通知／診斷入口。Cortex 持有 execution、model 與 completion 權威；
Claw 只讀取並呈現。安裝與維運的唯一現行契約仍是 [release-contract](../release-contract.md)
搭配 README；本文只保存一次實驗，不建立另一套 upgrade guide 或 umbrella implementation 清單。

## 1. 既有票與範圍核對

2026-10-15 以 `gh issue view <N> --repo hamanpaul/paulshaclaw --json number,title,state,url`
核對。原票對若干編號的描述與 GitHub 現況不符；不能用那些描述推定某段 cleanup／resolver
實作已完成。以下列出實際類型、標題與處置：

| 來源 | 即時類型／狀態與標題 | 本票處置 |
|---|---|---|
| [296](https://github.com/hamanpaul/paulshaclaw/issues/296) | issue CLOSED；bro 雙副本收斂 | 已由 [PR 362](https://github.com/hamanpaul/paulshaclaw/pull/362) 處理；不重做 |
| [287](https://github.com/hamanpaul/paulshaclaw/pull/287) | PR MERGED；裁切 0.1.0 | 並非 sibling-install issue；安裝操作以現行 release-contract 為準 |
| [313](https://github.com/hamanpaul/paulshaclaw/pull/313) | PR MERGED；v0.2.5 | 並非 archived-executor issue；歷史文件不當現行操作入口 |
| [319](https://github.com/hamanpaul/paulshaclaw/pull/319) | PR MERGED；v0.2.7 | 並非維運文件 issue；不以此號另開文件工程 |
| [320](https://github.com/hamanpaul/paulshaclaw/issues/320)、[321](https://github.com/hamanpaul/paulshaclaw/pull/321) | issue CLOSED／PR MERGED；policy 1.0.15 → 1.0.17 | 不是 legacy resolver／noqa 議題；不從錯誤編號推導新的 cleanup |
| [322](https://github.com/hamanpaul/paulshaclaw/issues/322) | issue CLOSED；JOBS 丟棄 workflow_run attention | 沿用已交付的 ingestion；core 全樹抽離仍依 337 STOP 決議停止 |
| [324](https://github.com/hamanpaul/paulshaclaw/issues/324) | issue OPEN；TestPilot Docker 安裝回歸 | 9/14 park 已由本輪 operator 明確恢復為 test-only 工作；獨立 owner 推進，本文不代為驗收 |
| [325](https://github.com/hamanpaul/paulshaclaw/issues/325) | issue CLOSED；README 缺 git 前置，wheel 安裝失敗 | 原票「future wheel 計畫」為誤讀；依 [PR 361](https://github.com/hamanpaul/paulshaclaw/pull/361) 與 337 的 9/14 更正，不把已修安裝 bug 改寫成未來需求 |

不新增通用 Agent OS、scheduler、model registry、quota policy、memory lifecycle、terminal
completion authority、core extraction 或自動 updater。未來獨立發行／升級擴張仍須具體使用者、
owner 與 rollback 需求；不由上述錯引編號推定已滿足恢復條件。

## 2. 已安裝 runtime：實測與邊界

[去識別化原始摘要](./evidence/337/installed-runtime.json) 保留 2026-10-15 05:25 UTC 的
entrypoint、shebang、distribution 與 import origin。從 checkout 外 `/tmp` 使用實際 pipx
venv 的 Python `-I -B` 執行，未安裝、升級、啟停服務或接管 tmux：

- `paulshaclaw --version`：0.2.9；local wheel、非 editable；`paulshaclaw`／`psc` 都指向
  pipx 的同一安裝。Claw／Cortex／Hippo import 全位於該 venv 的 site-packages。
- 安裝依賴為 Cortex 0.1.10（commit 739cde17b5b891bcdd575cb98ea07280f428ebaf）及
  Hippo 0.1.1（commit 96513bcf298f22dfb94ff5e85c3836dd781486b0）。
- 真正可用的公開 Python API 為 `paulsha_cortex.control.client.read_status()`；讀取真實
  control snapshot，schema=1、degraded=false。此安裝沒有 `paulsha_cortex.sdk` namespace。
- Python audit guard 記錄 0 次寫入嘗試、0 次 subprocess、0 次 socket；只有檔案讀取與
  `kill(pid, 0)` 活性探測。未輸出 token、環境內容、完整私有 snapshot、工作 ID 或帳號。

這證明已安裝 API 能讀到狀態，不證明候選程式已部署，也不等同目前常駐服務載入版本。
正反例測試使用受控資料；真實 snapshot 當時沒有 submitted/running/failed 各種狀態，
不能把測試矩陣冒稱那些 lifecycle 都已在現場發生。未進行 Telegram 遠端送訊或 TUI 接管。

## 3. Truthful projection 的正反例

[回歸測試](../../tests/test_truthful_status_projection.py) 透過真正的 projection／router／API
serializer 驗證；只有 control snapshot 或遠端 HTTP 邊界使用測試資料。修正前先觀察到
24 個 assertion failures，之後對 archived pending decision、缺失 failure reason、hint 與
長訊息各自執行 RED → GREEN；[測試紀錄](./evidence/337/tdd.txt) 保留結果。

| 輸入證據 | 應有投影／反例防線 |
|---|---|
| submitted／running／blocked／failed／completed 明確 state | 保留上游原值；不能由 submitted 推論 running 或 completed |
| in_flight／workflow_run／slices／recent_done 的 state 缺失、null、空白或非文字 | 顯示 unknown 與中性顏色；不從所在 collection 猜 running／done |
| recent_done failed／error | 保留失敗文字與紅色；歷史仍不算 active 工作 |
| run_status=archived 且 gate passed／needs_human | 同時顯示 archived 與「已完成」／「待裁決」，不把 archive 當 live |
| bot attention 含 reason／blocking_reason.detail、next_actions、next_step_hint | 顯示權威給定的原因與選項；失敗原因缺失時明示 unknown |
| tick 已提交、沒有 done record | queued；指向 status 查詢，不宣稱執行成功 |
| 空 done record 或空 status/result | unknown；不以空字串／空 dict fallback 為 done |
| 長度超限的摘要、CJK／emoji／HTML-like literal | listener 分段保留原文與順序，每段最多 4,000 UTF-16 units；以 plain text 送出，不啟用 parse_mode／entities |

Telegram 的 [sendMessage 契約](https://core.telegram.org/bots/api#sendmessage) 上限為 4,096
字元；本實測 14 筆 attention 的完整摘要超過此限制，分段屬本次正確性修復必要部分。
HTTP payload 測試沒有真的呼叫 Telegram。snapshot 的 `updated_at` 持續顯示；過時或
degraded 的資料只能當該時間的投影，不以 UI 更新或成功讀檔推論工作仍活著。

## 4. 實際操作任務與負擔量測

觀測者是 Agent。選取本輪確實執行的三個維運任務：查目前是否有工作執行、找卡住原因、
找可選決策。計時使用 `time.perf_counter()`；CLI 從 checkout 外以 `subprocess.run(...,
capture_output=True)` 各跑五次，完整回應只在記憶體解析，再保存匿名摘要。
[完整數值與方法](./evidence/337/operator-measurements.json) 可核對。

CLI 量測時三條入口指向相同真實 snapshot：updated_at=2026-10-15T05:26:22.077650+00:00，
degraded=false，in_flight=0、attention=14、not_claimable=2、recent_done=10。
14 筆 attention 都具有原因、next_actions 與 next_step_hint。Native CLI JSON 為 69,521 字元。

| 入口 | 五次耗時 ms | 中位數 ms | 計時含括 |
|---|---|---:|---|
| 已安裝 `psc coordinator status` | 205.785、203.750、199.424、189.472、202.863 | 202.863 | Python／CLI 啟動、讀取、JSON 輸出 |
| 已安裝 `cortex status` | 206.053、192.521、204.479、206.695、217.545 | 206.053 | 同上；獨立 Cortex pipx 安裝 |
| 已安裝 control API read_status | 0.469、0.371、0.441、0.359、0.349 | 0.371 | 僅已 import 後的 API 呼叫 |
| 已安裝 bot formatter | 0.014、0.009、0.007、0.006、0.005 | 0.007 | 同一真實 snapshot 的本地格式化 |
| 候選 bot formatter | 0.052、0.041、0.034、0.031、0.040 | 0.040 | 同上；不含 Telegram 網路或人工閱讀 |

Presentation 比較另於 05:30 UTC 取樣，兩版本 snapshot digest 相同（見 JSON）。
已安裝 0.2.9 摘要只有 663 字元，14 筆 attention 的原因／選項／hint 呈現數全為 0；
候選摘要 8,443 字元，三種資訊都呈現 14/14。候選是 source code 加已安裝依賴，
**不是部署完成**。其 cockpit 投影 16 列、安裝版 26 列的差異包含主線先前 recent_done
修正，不將這個跨版本差異計為本次新功能的效益。

下列步數依本次取得判斷資料的 procedure 計算；一個步驟是一個命令或一次明確欄位查找。
它不是人類受試記錄；閱讀、捲動、判斷與 Telegram 往返時間未測，不能推算人的節省分鐘數。

| 實際任務 | 原生 CLI／直接 API procedure | Claw procedure 與資料結果 |
|---|---|---|
| 查目前是否有工作執行 | ① `cortex status`；② 讀 updated_at/degraded/in_flight。2 步，0 筆 in_flight | ① `psc coordinator status`；② 讀同欄位。2 步、同結果；沒有證明 alias 減少操作 |
| 找卡住原因 | ① `cortex status`；② 定位 attention；③ 讀 blocking_reason.detail／reason。3 步、14 筆有原因 | bot procedure：① `/manager status`；② 讀 attention 的 reason。候選本地驗證 14/14；舊版找不到，必須再走原生路徑。未實測聊天 UI 步時 |
| 找所需決策 | ① 讀 snapshot；② 定位 attention 工作；③ 讀 next_actions／next_step_hint。3 步、14 筆有候選動作 | 候選與原因同列給上游動作／hint；本地資料檢索不需第二份 state。提示不保證可直接執行，authority／expected-run 等仍由 Cortex 驗證 |

直接 API 的對照步驟是以 **已安裝 interpreter** import `control.client.read_status`、呼叫
一次，再讀同樣欄位。其約 0.4 ms 不能拿來和 CLI 約 200 ms 比為「人工快 500 倍」；兩者
計時邊界不同。bot 的 8,443 字摘要仍可能造成閱讀負擔，沒有證據支持擴張 dashboard 或 widget。

維護成本：保留兩種 projection（cockpit／bot）即須同時維護 unknown、歷史／live、failure
與缺欄位契約；新增的 status regression 35 cases，加現有相關檔案共 155 tests + 6 subtests，
本機 focused run 1.70 秒。完整 preflight 另包含 OpenSpec／policy／全套測試，不能拿 focused
數字當全套成本。Telegram、Textual 與 Cortex API 的相容性仍是維護面；本輪不新增 state DB、
常駐掃描器或調度權威。工程人工時與長期維護工時未量測，不作淨 ROI 宣稱。

## 5. 保留、停止與後續維運界線

修正真實資訊遺漏和假成功；保留現用的 bot／cockpit／通知入口。`psc coordinator status`
只是相容轉接，本次兩個 CLI 的步數相同、耗時差不足以證明效益，預設不再擴張 shim 功能；
需要完整 authority／故障資料時使用 `cortex status` 或已安裝的 control API。

停止新增平台、core 全樹抽離、第二份 model resolver、scheduler 或自動 installer。未淘汰
任何已使用介面；若未來要淘汰，先給原生 CLI/API 替代、相容性通知與回復舊入口方式，再由
operator 決定。此次程式的回復路徑是回到前一候選 commit；已安裝版本不因本 PR 改動。
若日後部署新 release，使用 release-contract §6 的前版 wheel 回滾，state／secret 仍保留。

本次沒有執行部署、服務重啟、真實 Telegram 發送或操控現有 tmux。已安裝 API 實測、候選
projection 使用真實 snapshot、合成 lifecycle 回歸與人體操作效益各自標示，互不代替。
