<!-- managed-by: hamanpaul/paulsha-conventions@v1.0.0 -->
policy_version: 1.0.0

# Gemini Instructions（paulshaclaw）

本檔供 Gemini CLI / Gemini Code Assist 讀取專案 agent 規範。
詳細指令與路由規則見 [`CLAUDE.md`](./CLAUDE.md)。

## 專案定位
- `paulshaclaw`：個人 agent 工作流設計文件庫（docs-first，非部署應用）
- Runtime 狀態：`~/.agents/`
- Secrets：`~/.config/paulshaclaw/`

## 硬規範
- 禁止輸出任何密鑰、密碼、Token。
- 未經明確要求，不得執行破壞性操作。
- 修改以最小 diff 為原則。
