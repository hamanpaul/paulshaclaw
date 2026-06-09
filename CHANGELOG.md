# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to Semantic Versioning.

## [Unreleased]

### Changed
- **`/agent start` 改吃 pane id 參數**：`/agent start %pane` / `/agent startf %pane` 在呼叫端指定的既有 pane 啟動 claude-gemma4 agent（取代原本 `split-window` 切新 pane）。啟動前驗證該 pane 為 idle shell——非 shell 或被 claude/minicom 等佔用、pane id 未以 `%` 開頭、帶多個 pane id 皆拒絕並回報原因。修正先前切新 pane「不 work」、agent 未穩定常駐導致 Telegram 回覆斷線的問題。
- **同步 policy 1.0.1**：`policy_version` 1.0.0 → 1.0.1（`.paul-project.yml` + 四份 agent 檔 + `managed-by@v1.0.1`），caller `policy-check` workflow 的 `uses:` 與 `policy_engine_ref` 重新雙重釘選至 `hamanpaul/paulsha-conventions@4ff59b6c35a46a87af3c3e641975743ee8fa0858`（含 R-17 / R-18）；agent 檔追加 R-17 / R-18 與語言規範說明

### Fixed
- **footer cpt arc 顯示 AI Credit (AIU) 用量**：copilot 帳號歸屬改為 metric-based（依 project-usage-assess skill 規則：`data.totalNanoAiu/1e9` → `paulc-arc`、`totalPremiumRequests` → `hamanpaul`），不再依賴 `gh` active account。arc 終於從本地 `~/.copilot/**/events.jsonl` 顯示本月 AI credits；footer 大數字以 k/M 縮寫（如 `arc:55.8k`）。
- **footer cdx 數值（codex 5h/weekly）終於顯示**：codex 的可信額度改讀本地最新 session 的 `payload.rate_limits`（network endpoint 常回 403），並修正兩個解析錯誤——auth token 在 `tokens.{access_token,account_id}` 巢狀層（auth_mode=chatgpt），本地 token 統計在 `info.total_token_usage.total_tokens`。已重置的視窗（`resets_at` 過期）會略過而非顯示過時值。（cc 仍需 statusline sidecar writer 才有 trusted 來源；arc 需真實 org/token。）
- **測試不再污染 live footer**：`tests/test_start_sh.py` 的 `_run_lifecycle_test` 改為隔離 tmux（fake `tmux` 上 PATH + 私有 `TMUX` socket），避免在 tmux session 內跑 `pytest tests/` 時，真實 `start.sh` 的 `apply_stage8_footer` 覆蓋使用者的 `status-right`。
- **bro 回覆 off-by-one**：`bro_out` Stop hook 先前抓「transcript 最後一則 assistant 文字」，但當下這輪的 assistant 記錄常還沒寫入 transcript，使 Telegram 收到「前一次的回覆」。改為擷取「最後一筆 user 記錄之後」的 assistant 文字（即本輪回覆），尚未 flush 時短暫輪詢等待（`current_turn_reply` + poll）。
- **claude-gemma4 skill 鏡像支援「容器目錄」攤平**：launcher 先前把 `~/.agents/skills/<容器>`（如 superpowers，真正的 skill 在子層）整包鏡像成單一 `skills/<容器>`，因頂層無 `SKILL.md` 無法被 Claude Code 載入 → gem「找不到」brainstorming 等 superpowers skill。改為偵測無頂層 `SKILL.md` 的容器，把其下每個含 `SKILL.md` 的子 skill 攤平成扁平 user skill（同名跳過）。

### Added
- `paulshiabro-telegram-reply` skill 升級：新增 `scripts/reply_bridge.py` standalone 橋接工具與對應測試，移除對 repo venv 的依賴
- `tmate.start()` 加入 `_wait_until_ready()`：呼叫 `tmate wait tmate-ready` 確保連結就緒，timeout 回傳 pending 狀態
- 初始骨架：`.paul-project.yml`、`README.md`、`CHANGELOG.md`、`VERSION`
- Agent convention files：`CLAUDE.md`、`AGENTS.md`、`GEMINI.md`、`.github/copilot-instructions.md`
- CI workflow：`.github/workflows/policy-check.yml`（雙鎖定 paulsha-conventions SHA）
