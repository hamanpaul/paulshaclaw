# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to Semantic Versioning.

## [Unreleased]

### Added
- `paulshiabro-telegram-reply` skill 升級：新增 `scripts/reply_bridge.py` standalone 橋接工具與對應測試，移除對 repo venv 的依賴
- `tmate.start()` 加入 `_wait_until_ready()`：呼叫 `tmate wait tmate-ready` 確保連結就緒，timeout 回傳 pending 狀態
- 初始骨架：`.paul-project.yml`、`README.md`、`CHANGELOG.md`、`VERSION`
- Agent convention files：`CLAUDE.md`、`AGENTS.md`、`GEMINI.md`、`.github/copilot-instructions.md`
- CI workflow：`.github/workflows/policy-check.yml`（雙鎖定 paulsha-conventions SHA）
