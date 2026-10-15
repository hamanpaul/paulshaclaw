## Why

JOBS 目前只有角色，operator 看不到 Cortex 記錄的 executor／model，也無法區分上次執行與預定身份。

## What Changes

- 接收 Cortex status 的 additive identity fields，保留 typed fallback。
- 在工作列展開後顯示完整 executor、model、來源、執行狀態、card 與 job。
- 固定已交付 producer SHA，加入同源 fixture、隔離安裝整合與 Textual 刷新測試。

## Impact

影響 Stage 11 JOBS consumer 與 Cortex dependency pin；不修改 Cortex registry 或服務。
跨 repo 身份綁定仍由 producer 負責；已知上游缺口見本變更 tasks 與整合證據。
