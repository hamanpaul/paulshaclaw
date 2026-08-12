---
type: fix
---
移除孤兒 hook `scripts/gemma4-hooks/psc-bro-return.py` 與其專屬測試（#289）。forensics 證實它不存在於任何 hook 註冊表（claude/codex/copilot/gemini），`~/.agents/log/bro-hook.log` 的 203 筆 `本輪回覆讀不到` 失敗全部是測試套件副作用——`tests/test_psc_bro_return.py` 的 reply=None 案例以未隔離的真實 log 路徑寫入，每跑一次全套測試就多一筆，從無任何生產呼叫。
- Telegram 回程的 live 管線不變：Claude 走 `bro_in.py`/`bro_out.py`（launcher 注入），cortex 派工走 `psc-relay-hook.sh` → `reply_bridge.py`；`paulsha-cortex` 早已在 hook 模板移除 psc-bro-return glue，本次把留在本 repo 的殘骸拔掉。
- 同步刪除 live spec 中 mandate 此 hook 的 Requirement 區塊（`openspec/specs/agent-conversation-routing/spec.md`），並修正 `custom-skills/bro/tests/test_reply_bridge.py` docstring 的過期引用（測試本體保留，仍守護「呼叫端不傳路徑」的現役行為）。runtime 側 `bro-hook.log` 於部署時歸檔，寫入者歸零後不再累積。
