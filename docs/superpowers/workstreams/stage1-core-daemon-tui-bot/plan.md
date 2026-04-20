# stage1-core-daemon-tui-bot / plan

## Scope

- Stage: 1
- 目標: 建立 PaulShiaBro daemon + TUI + Telegram bot 最小可跑版
- 先決依賴: Stage 0 baseline
- In scope: `paulshaclaw/core/`、`paulshaclaw/tui/`、`paulshaclaw/bot/`
- Out of scope: Stage 2+ 規格檔、Stage 6 security 實作

## Steps

### Phase 1: Core daemon
1. 建立 daemon 啟動入口、設定載入、最小任務派工入口。

### Phase 2: TUI + Telegram
1. 建立 TUI pane/任務對照視圖。
2. 建立 Telegram 最小指令集與授權檢查。

### Phase 3: Stage1 收斂
1. 串接 coordinator dispatch（不含 Stage 3 gate）。
2. 完成 stage1 smoke test。

## Relevant files

- `paulshaclaw/core/`
- `paulshaclaw/tui/`
- `paulshaclaw/bot/`
- `docs/superpowers/workstreams/stage1-core-daemon-tui-bot/task.md`

## Verification

1. daemon 可啟動且可接收最小指令。
2. TUI 可列出 pane 與任務對照。
3. Telegram 指令可回應且僅允許授權使用者。
4. Stage1 smoke test 通過。

## Decisions

- Stage 1 先提供可跑基線，不在此階段整合完整 lifecycle gate。
