# WSL 磁碟容量監控

bot listener 每輪 polling 呼叫容量監控；啟動後首次立即檢查，之後以 monotonic clock 每 20 分鐘檢查一次。bot 未啟動時不監控。這是 Stage 5 的量測與通知功能，容量治理仍由 Cortex 負責。

狀態固定寫入 `paths.state_path("space-monitor.json")`，預設為 `$HOME/.agents/state/space-monitor.json`；遵循 `PSC_STATE_ROOT`、`PSC_AGENTS_ROOT` 與 `PSC_HOME_ROOT`。每次成功量測以原子替換更新 JSON；讀取容量失敗會保留上次狀態，因此 agent 必須檢查 `checked_at`。通知先於掃描及寫檔，磁碟滿導致寫檔失敗仍會嘗試 Telegram；錯誤只記錄 log。沒有另一份 LOW 旗標，因為同一磁碟上的旗標也可能無法寫入。

## 數值與遲滯

使用 `df -BG --output=avail,used,size /` 的 GiB 整數，`use_pct` 為 used / size 向上取整百分比。這是 ext4 檔案系統量測，與 Windows VHDX 檔案長度不同。`level` 在可用空間 ≥ warn 時為 `ok`、低於 warn 為 `warn`、低於 critical 為 `critical`。預設邊界為 100 / 50 GiB。

每個告警週期只通知一次 warn 與一次 critical；critical → warn → critical 不重送。回到 recover（預設 120 GiB）才送恢復通知並重設週期。遲滯狀態與 memory monitor 一樣只存在記憶體中，重啟後重新判定。`level: ok` 與 `alerting: true` 可以同時出現，表示已離開 warn、但尚未達恢復門檻。Telegram 發給 allowed users 已綁定的 chat，重複 chat 去重；送出失敗只記 log，不在每輪重送。

VHDX 不呼叫 Windows 命令，也不推測檔案位置；未設定可靠路徑時 `size_gb: null`、註記「未知」。可由 `PSC_SPACE_VHDX_PATH` 提供 WSL 可直接讀取的檔案路徑，這只回報檔案長度，不能保證 Windows 已配置的實體磁碟區塊數。Windows 實機路徑與實際回收效果未驗證。若需壓縮，應先保存工作並停止 WSL，再由操作人員在 Windows 執行 `Optimize-VHD` 或 `diskpart compact vdisk`。

## 掃描與建議

掃描在短生命週期 worker 內執行，預設整輪最多 10 秒；逾時會終止整個 worker process group（含 Git、du、find）。個別命令最多 2 秒且不得超過剩餘預算；最多接受 256 個目錄候選、32768 個 `/proc` 項目。量測逾時仍保留 root 水位與告警，`scan_errors` 表示結果不完整，該輪不輸出回收建議。

`PSC_SPACE_SCAN_ROOTS` 的每個項目是目錄或非遞迴 glob，精確選取 repo、linked worktree、target、cache 或 `*-tmp`；repo/worktree 會額外量測其 `target`。預設使用 `$HOME/prj_pri/*`、`$HOME/prj_pri/*-worktrees/*`、`$HOME/.cargo`、`$HOME/.cache`；不含專案專用路徑。`*-worktrees` 容器本身不重複計入 top_dirs。暫存目錄由操作人員明確加入掃描根，例如 `/workspace/jobs/*-tmp`。

量測使用 `du -s -B1`，輸出 GiB 數值而非 `du -sh` 的人讀字串，按大小取前 N 名。busy 檢查 `/proc` 的 cwd、cmdline、exe，解析 symlink 與相對路徑；無法判斷仍存在的程序時一律保守視為 busy。程序已結束可略過。這是觀察當下的結果，不能作為稍後刪除的授權或鎖；任何人工操作前都須重新確認使用狀態。

建議順序為：

1. `remove_worktree`：linked worktree 乾淨、HEAD 已是指定目標的祖先、非 locked/prunable、沒有 busy 行程或被排除的子路徑，若有 target，所有後代亦須超過 target 閒置時間。附本地 branch 名稱。
2. `remove_target`：乾淨 linked worktree 中，所有後代超過 target 閒置時間且無 busy 行程。主 repo 的 target 保留。
3. `remove_tmp`：名稱為 `*-tmp`、所有後代超過 tmp 閒置時間且無 busy 行程。
4. `remove_remote_branch`：符合一次性 CI branch 樣式，`git ls-remote --heads origin` 即時回傳的 HEAD 已合併至指定目標。若目標為 `origin/...`，本地目標 SHA 必須與即時遠端一致；過期 ref、缺 commit、Git 失敗時不列建議。監控不 fetch、不 prune。

Git status 包含所有未追蹤檔，不特殊忽略 `.codex`。`PSC_SPACE_EXCLUDES` 的路徑及其後代不掃描，排除 worktree 子目錄也會保留該父 worktree。Git 或掃描證據不完整時 `suggestions` 留空，`reclaimable` 為 false。所有輸出只供觀察：不執行 `rm`、`git worktree remove`、刪 branch 或其他回收，即使設定 `PSC_SPACE_AUTO_RECLAIM=1`，`auto_reclaim` 仍是 false。

## 環境變數

| 變數 | 預設 | 用途 |
|---|---|---|
| `PSC_SPACE_WARN_GB` | 100 | 可用 GiB 低於此值進入 warn |
| `PSC_SPACE_CRITICAL_GB` | 50 | 可用 GiB 低於此值進入 critical；上限夾到 warn |
| `PSC_SPACE_RECOVER_GB` | 120 | 恢復門檻；下限夾到 warn |
| `PSC_SPACE_INTERVAL_SECONDS` | 1200 | 兩次檢查的最小間隔秒數 |
| `PSC_SPACE_SCAN_SECONDS` | 10 | 整輪掃描時間上限秒數 |
| `PSC_SPACE_TOP_N` | 10 | 最大目錄清單長度 |
| `PSC_SPACE_TARGET_IDLE_HOURS` | 24 | target 全部後代的閒置小時數 |
| `PSC_SPACE_TMP_IDLE_HOURS` | 6 | `*-tmp` 全部後代的閒置小時數 |
| `PSC_SPACE_SCAN_ROOTS` | 見上文 | 以 `:` 分隔的目錄 / glob；支援 `~`、環境變數 |
| `PSC_SPACE_EXCLUDES` | 空 | 以 `:` 分隔的排除路徑 / glob |
| `PSC_SPACE_MERGE_TARGET` | `origin/main` | 明確合併目標；不使用候選自身的 upstream |
| `PSC_SPACE_CI_BRANCH_PATTERNS` | `ci/*:*-ci-*` | 一次性遠端 CI 分支 glob，`:` 分隔 |
| `PSC_SPACE_VHDX_PATH` | 空 | 已確認可讀的 VHDX 檔案路徑；空值回報未知 |
| `PSC_SPACE_DISABLED` | 空 | 值為 `1` 時停用量測、寫檔與告警 |

數字須為正整數，其他值退回預設。自訂路徑不要包含 `:`。若需要超出預設掃描預算，可縮小掃描根或調整秒數；不完整結果不可視為完整磁碟清單。

[範例 JSON](../examples/space-monitor.json) 是測試水位 99 GiB 的示意輸出，非作者主機實測。測試包含實際 Git repositories、真實長時間 subprocess 的 cwd、cmdline/exe/symlink、四類建議及 worker 硬逾時。
