---
type: feat
scope: bot
---
新增 `/agent attach %pane` 與 `/agent detach`：可把既有、正在跑 agent 的 tmux pane（例如 Claude Code session）固定為控制 agent，非 reply 的 Telegram 訊息改送進該 pane，優先於 claude-gemma4 自動偵測；reply-to 指定的 pane 仍最優先。attach 目標為 idle shell 或不存在時拒絕；attach 後若 pane 消失或 agent 退回 shell，訊息不送出並提示重新 attach 或 detach。attach 只存在 daemon 記憶體，listener 重啟後需重新 attach。
