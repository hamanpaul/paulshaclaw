<!-- managed-by: hamanpaul/paulsha-conventions@v1.0.1 -->
policy_version: 1.0.1

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

## v1.0.1 新增規則（issue 連結 / docs 對齊 / 語言）
> 本段於 policy 1.0.1 隨 R-17 / R-18 與語言規範新增。

- **R-17（PR↔issue，FAIL gate）**：PR body 引用 issue（`#N`）時必須為 closing-keyword 形式（`Closes` / `Fixes` / `Resolves #N`），merge 由 GitHub 原生自動關閉 issue 並留下 cross-reference；只引用不關閉時上 `policy-exempt:issue-link`。
- **R-18（docs 對齊，WARN，不擋 merge）**：`code_paths` 有變動但 `README.md` / `docs/**` 未同步時提醒；純內部變動可上 `policy-exempt:docs-sync`。
- **語言規範（checklist）**：依 repo 來源決定語言——`github.com/hamanpaul/*`、`github.com/paulc-arc/*` → zh-tw；arcadyan GitLab → en_US。涵蓋 PR 標題／內文與所有 comment。本 repo 屬 `hamanpaul` → zh-tw。
- **動工前（軟性，不打斷流程）**：若任務對應某 issue，`gh issue view <N>` 核對相關性後分支可命名 `feature/<N>-<slug>`，開 PR 於 body 寫 `Closes #N`；查無對應 issue 照常進行，不另開、不停。
- **Exemption 白名單新增**：`policy-exempt:issue-link`（R-17）、`policy-exempt:docs-sync`（R-18）。
