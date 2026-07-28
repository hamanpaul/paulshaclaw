---
type: fix
issue: 88
---
`daemon.route_to_agent()` 的去程 `tmux send-keys` 不再是無 ack、無 queue、無重試的 fire-and-forget（#88）：改走 `paulshaclaw/core/bro_queue.py` 單一序列化出口——訊息先落地成 per-pane JSONL 佇列，send-keys 後用 `tmux capture-pane -J` 驗證文字真的出現才視為送達；沒驗到就整批保留（不越級），交由下一則訊息或 agent Stop hook（`scripts/gemma4-hooks/bro_out.py`）結束當下重試消化。實測 claude/gemma4 這類 TUI 畫面尾行恆是自己的 footer、不會以 `$`/`>` 結尾，「送前偵測 busy」不可靠，因此改採「送後驗證」而非猜測。`route_to_agent` 簽章新增 `pane_id: str | None = None`（未給時維持既有自動偵測），為 #34 的多 pane 路由預留落點。
