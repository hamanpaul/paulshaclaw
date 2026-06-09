# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to Semantic Versioning.

## [Unreleased]

### Changed
- **同步 policy 1.0.1**：`policy_version` 1.0.0 → 1.0.1（`.paul-project.yml` + 四份 agent 檔 + `managed-by@v1.0.1`），caller `policy-check` workflow 的 `uses:` 與 `policy_engine_ref` 重新雙重釘選至 `hamanpaul/paulsha-conventions@4ff59b6c35a46a87af3c3e641975743ee8fa0858`（含 R-17 / R-18）；agent 檔追加 R-17 / R-18 與語言規範說明

### Fixed
- **bro 回覆 off-by-one**：`bro_out` Stop hook 先前抓「transcript 最後一則 assistant 文字」，但當下這輪的 assistant 記錄常還沒寫入 transcript，使 Telegram 收到「前一次的回覆」。改為擷取「最後一筆 user 記錄之後」的 assistant 文字（即本輪回覆），尚未 flush 時短暫輪詢等待（`current_turn_reply` + poll）。

### Added
- `paulshiabro-telegram-reply` skill 升級：新增 `scripts/reply_bridge.py` standalone 橋接工具與對應測試，移除對 repo venv 的依賴
- `tmate.start()` 加入 `_wait_until_ready()`：呼叫 `tmate wait tmate-ready` 確保連結就緒，timeout 回傳 pending 狀態
- 初始骨架：`.paul-project.yml`、`README.md`、`CHANGELOG.md`、`VERSION`
- Agent convention files：`CLAUDE.md`、`AGENTS.md`、`GEMINI.md`、`.github/copilot-instructions.md`
- CI workflow：`.github/workflows/policy-check.yml`（雙鎖定 paulsha-conventions SHA）
