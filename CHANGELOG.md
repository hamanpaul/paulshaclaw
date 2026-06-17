# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to Semantic Versioning.

## [Unreleased]

### Changed
- **`/agent start` 改吃 pane id 參數**：`/agent start %pane` / `/agent startf %pane` 在呼叫端指定的既有 pane 啟動 claude-gemma4 agent（取代原本 `split-window` 切新 pane）。啟動前驗證該 pane 為 idle shell——非 shell 或被 claude/minicom 等佔用、pane id 未以 `%` 開頭、帶多個 pane id 皆拒絕並回報原因。修正先前切新 pane「不 work」、agent 未穩定常駐導致 Telegram 回覆斷線的問題。
- **同步 policy 1.0.2**：`policy_version` 1.0.1 → 1.0.2（`.paul-project.yml` + 四份 agent 檔 + `managed-by@v1.0.2`），caller `policy-check` workflow 的 `uses:` 與 `policy_engine_ref` 重新雙重釘選至 `hamanpaul/paulsha-conventions@98487868a098e22647074c677a58633ce4fa19be`，並在 agent 檔追加 R-19 / R-20（CI 測試要求與 workflow `policy_version` 同步規則）。
- **同步 policy 1.0.1**：`policy_version` 1.0.0 → 1.0.1（`.paul-project.yml` + 四份 agent 檔 + `managed-by@v1.0.1`），caller `policy-check` workflow 的 `uses:` 與 `policy_engine_ref` 重新雙重釘選至 `hamanpaul/paulsha-conventions@4ff59b6c35a46a87af3c3e641975743ee8fa0858`（含 R-17 / R-18）；agent 檔追加 R-17 / R-18 與語言規範說明

### Fixed
- **per-session 標題 surface 到 MOC / wake-up**：gemma4 標題原只在 summary 切片 body，MOC/wake-up 顯示的還是 facet 檔名（`prompts--sl-…`）。改為把 session 標題沿 atomize 鏈傳播成切片 `session_title` frontmatter（splitter→\_render\_fragment→\_read\_fragment→slice\_frontmatter），moc\_builder 與 wakeup.build\_brief 以它當 wikilink alias 顯示（`[[stem|修復 serialwrap MCU 韌體]]`，無標題時維持原檔名故不影響既有測試）。title 截斷時順手把 `:`/`#` 換全形以保 frontmatter YAML 安全。
- **補完 atomize 斜線消毒（moc / wakeup）**：sanitize 還漏兩處——`moc_builder` 用 rich project（含斜線）寫 `knowledge/{project}-moc.md` → 父目錄不存在 → `FileNotFoundError` 使整個 MOC pass 失敗、wake-up 不更新；`wakeup.build_brief` 同樣以 rich project 讀 per-project MOC 與 knowledge 目錄。兩處改用 `sanitize_project_component`，並補 `_write_moc` 的 parent mkdir。補 build_mocs 斜線 project 回歸測試。
- **補完 atomize 斜線消毒 + 標題無內容處理**：(1) `pipeline._read_fragment` 仍用 `is_safe_path_component` 檢查含斜線的 rich project（如 `github.com/owner/repo`、`.codex/memories`）→ 回 None → promote 讀不到 fragment、`atomize.slices:0`、backfill 內容進不了 knowledge；改為只檢 agent/session（project 為 metadata，僅在當路徑時才消毒）。(2) `title.generate_title` 對 prompt+summary 皆空的 session 不再打 gemma4（會回「由於您尚未提供…」抱怨被當標題存），改回中性 `(無內容)`。補一個 split→promote→knowledge 整鏈回歸測試擋此類遺漏。
- **修正 per-session 標題 gemma4 可達性誤判**：`title._gemma4_reachable()` 原硬寫檢查 `127.0.0.1:8001`（該處無服務），導致即使 gemma4 上線（upstream `192.168.199.199:8001` / 本機 proxy `127.0.0.1:18080`）標題仍全走 fallback。改為解析 `PSC_CLAUDE_GEMMA4_UPSTREAM_URL`（與 `claude-gemma4-proxy` 同預設）檢查真實 upstream host:port。實測產出真標題「修復 serialwrap MCU 韌體」（20 字、source=gemma4）。
- **cockpit TUI 退出路徑與 help modal guard 補強（#9 / #11 review follow-up）**：`q` / `Ctrl+Q` 保留單一路徑，不再因 app `BINDINGS` 與 `on_key` 重複 dispatch 觸發兩次 `exit()`；help modal 開啟期間會攔下 `c` / `Enter` / `q` / `Ctrl+Q` 等背景操作，關閉時再補跑一次 light refresh，避免 modal 期間錯過 tick 後最長 stale 30 秒。
- **work list 選取/高亮保持一致（#10 review follow-up）**：`ListView` 的 highlight 與 `CockpitState.selected_pane` 持續同步；若誤把 highlight 落到 `[ACTIVE]` 列，游標會回到原本選取的 candidate，而不是固定跳回第一個候選；pane refresh 重新排序時，只要原本選取的 pane 還在，選取就會依 pane id 保留下來，右側 detail / preview 也維持對齊。
- **OOM 啟動鏈加固（#82，F1–F10 + review follow-up）**：`start.sh` 新增 singleton lock、dream 首輪延後與 monitor/telegram/cockpit 啟動 stagger；monitor socket 改成先探測 live/stale 再決定是否接管，watch 範圍收斂為 project root 非遞迴 + git control paths、補 HEAD lockfile rename 偵測與 timeout 視為 live 的保守拒絕；MOC index 改分批寫入並重用單次 lifecycle events、wake-up brief 補 frontmatter 64KB 上限/`stat()` fail-open/剩餘 budget 讀取夾限、atomizer inbox oversize skip 改為首輪記錄後靜默略過重跑；Claude/Codex 本地成本掃描補 64MB/mtime 邊界；dream 排程與 wrapper 釘死 `--promoter identity`，`claude-gemma4` 預設加上 3GB Node heap cap。
- **cockpit TUI 即時更新 + 工作摘要修正**：(1) cockpit 先前只在啟動時抓一次 pane 快照、之後僅在按 Enter（swap）才重載，新開/改名的 pane 不會出現；改為每 `REFRESH_INTERVAL_SECONDS`(30s) 定時重抓 pane 清單；且**清單內容（標籤＋選取游標）沒變就不重建 ListView**，idle 重抓不會閃爍（detail/preview 仍每輪更新）。每輪 bounded——一次 `list-panes` + 僅對無標題 minicom pane 跑短 timeout 的 `ps`，preview 只抓選取中的 pane（與 footer 那次無邊界掃描當機相反，刻意維持小而固定）。(2) 工作摘要先前只用 `pane_title`，minicom 不設標題故一片空白；新增 `derive_summary` fallback：無標題的 minicom 從其 argv（`-C …/mini_COM<N>_…`／`-D <device>`）解析出 `minicom COM0`/`COM1`，其他無標題 pane 顯示 `[command]`。
- **footer cpt 改顯示 plan 用量百分比**：copilot 帳號改讀 GitHub Copilot plan-quota endpoint（`/copilot_internal/user` 的 `quota_snapshots.premium_interactions`，與 Copilot CLI statusline 同源），footer 顯示 `haman:21%`，business/enterprise 無上限顯示 `arc:∞`。單次便宜 HTTP GET、**不掃任何本地 log**，取代先前從 `events.jsonl` 累加 AIU/premium 計數的作法（計數路徑保留為離線後備）。
- **防止 footer 掃描拖垮 WSL（OOM 當機）**：tmux footer 改以 `--no-refresh` 純讀快取（不在每次 `#()` render 重建 snapshot）；snapshot 由 `start.sh` 中隨生命週期收束的 cost refresh loop 節流重建（`PSC_COST_REFRESH_DISABLED=1` 可停）。`events.jsonl` 後備掃描加上邊界：依 mtime 跳過目標月份以前的舊檔（先前 3.3GB、單檔上看 442MB 的歸檔全部跳過）、單檔超過 64MB 直接略過——即使後備路徑被觸發也不會 OOM。
- **footer 長度被裁切**：`apply_stage8_footer` 設定 `status-right-length 200`（tmux 預設 40 會把 footer 從中間切掉，如 `cc~ 5h:82%`）。
- **footer cdx 數值（codex 5h/weekly）終於顯示**：codex 的可信額度改讀本地最新 session 的 `payload.rate_limits`（network endpoint 常回 403），並修正兩個解析錯誤——auth token 在 `tokens.{access_token,account_id}` 巢狀層（auth_mode=chatgpt），本地 token 統計在 `info.total_token_usage.total_tokens`。已重置的視窗（`resets_at` 過期）會略過而非顯示過時值。（cc 仍需 statusline sidecar writer 才有 trusted 來源；arc 需真實 org/token。）
- **測試不再污染 live footer**：`tests/test_start_sh.py` 的 `_run_lifecycle_test` 改為隔離 tmux（fake `tmux` 上 PATH + 私有 `TMUX` socket），避免在 tmux session 內跑 `pytest tests/` 時，真實 `start.sh` 的 `apply_stage8_footer` 覆蓋使用者的 `status-right`。
- **bro 回覆 off-by-one**：`bro_out` Stop hook 先前抓「transcript 最後一則 assistant 文字」，但當下這輪的 assistant 記錄常還沒寫入 transcript，使 Telegram 收到「前一次的回覆」。改為擷取「最後一筆 user 記錄之後」的 assistant 文字（即本輪回覆），尚未 flush 時短暫輪詢等待（`current_turn_reply` + poll）。
- **claude-gemma4 skill 鏡像支援「容器目錄」攤平**：launcher 先前把 `~/.agents/skills/<容器>`（如 superpowers，真正的 skill 在子層）整包鏡像成單一 `skills/<容器>`，因頂層無 `SKILL.md` 無法被 Claude Code 載入 → gem「找不到」brainstorming 等 superpowers skill。改為偵測無頂層 `SKILL.md` 的容器，把其下每個含 `SKILL.md` 的子 skill 攤平成扁平 user skill（同名跳過）。

### Added
- **Stage 2 記憶內容擷取（Phase 1）**：修復「部署完成但功能空心」——三家 adapter（claude/codex/copilot）改為實際讀 `transcript_path`/history 擷取 prompts/touched_files；import 時用本機 gemma4 產每 session ≤20 字繁中標題（gemma4 離線以 TCP 快速可達性檢查瞬間 fallback、不阻塞 import）；atomizer 新增 `sanitize_project_component` 消毒含斜線 project，不再 skip URL 形專案（`atomize.slices:0` 根因）；新增 `importer/backfill.py` 三家強制回填（繞 checksum、`--dry-run`、可重入）。promoter→LLM 蒸餾留 Phase 2。
- **新增 pytest CI workflow（`.github/workflows/tests.yml`）**：PR 與 main push 時於 GitHub Actions（ubuntu, Python 3.12）執行完整測試套件——`tests/` + `paulshaclaw/memory/tests/`（1042 tests + 112 subtests）。live LLM 測試維持 `PSC_ATOMIZE_LIVE` guard 自動跳過；依賴自 `requirements-stage9.txt` + `requirements-stage11.txt` 安裝。在此之前 CI 僅跑 policy check，測試從未在 PR gate 上執行。
- `paulshiabro-telegram-reply` skill 升級：新增 `scripts/reply_bridge.py` standalone 橋接工具與對應測試，移除對 repo venv 的依賴
- `tmate.start()` 加入 `_wait_until_ready()`：呼叫 `tmate wait tmate-ready` 確保連結就緒，timeout 回傳 pending 狀態
- 初始骨架：`.paul-project.yml`、`README.md`、`CHANGELOG.md`、`VERSION`
- Agent convention files：`CLAUDE.md`、`AGENTS.md`、`GEMINI.md`、`.github/copilot-instructions.md`
- CI workflow：`.github/workflows/policy-check.yml`（雙鎖定 paulsha-conventions SHA）
