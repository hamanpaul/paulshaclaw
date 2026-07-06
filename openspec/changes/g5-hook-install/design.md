## Context

完整設計：`docs/superpowers/specs/2026-07-06-g5-hook-install-design.md`。複製部署模型維持（symlink 語意變更風險不取），把「同步」自動化、把「漂移」可檢查化。`launcher.py:179` 已注入 `PSC_REPO_ROOT` 為 abspath 既例。

## Goals / Non-Goals

**Goals:** 一鍵冪等裝好全部 hooks；--verify 抓壞點與 stale；hook 零硬編碼路徑。
**Non-Goals:** 改 symlink 部署；hook 業務邏輯變更。

## Decisions

1. **清單集中宣告**：hooks 複製清單單點維護，新 hook（如 P0-1 warn hook）只加一行。
2. **--verify 四檢**：語法/import、settings 註冊、env/secret 存在（沿 deploy split，值不印）、**內容 sha256 比對 repo↔部署**列 stale——治「改了忘同步」的本。
3. **abspath 雙軌**：shell → `${PSC_REPO_ROOT}`；Python → `paulshaclaw.config.paths`（依賴 P2）；verify 內建 lint 擋回歸。
4. **fail-loud**：未知 settings 格式不猜、verify 非零即部署不完整。

## Risks / Trade-offs

- 三家 agent settings 格式演進：reconcile 以既有測試釘住。
- hash 誤報：內容 sha256 為準、權限另列。
