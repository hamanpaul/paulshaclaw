---
type: feat
issue: 34
---
Telegram reply 路由回來源 pane：PaulShiaBro 送出 agent 回覆時記錄 Telegram
message_id → pane_id 對應（pane_id 取自 TMUX_PANE），listener 收到 reply
引用時查表路由回該 pane，查無對應 fallback 原自動偵測。對應表為檔案型 state
（~/.agents/state/telegram-message-pane-map.json），flock 序列化，7 天 TTL
與 500 筆上限。reply_bridge.py（standalone）與 reply.py（repo）各自維護
副本，路徑一致性由 test_default_paths_match_facade 把關。