---
dispatch: hold
slice_id: g5-hook-install
plan: null
depends_on: [p2-usability-phase0]
---

# G5 — hook 安裝自動化 + abspath 一致性 設計

> 日期：2026-07-06 ｜ 狀態：草案（待覆審）｜ 對應：#128
> 父件：`2026-07-06-p3-standup-gates-umbrella-design.md`。依賴 P2（`p2-usability-phase0`）：Python hooks 的路徑統一走 facade。

## 1. 背景與問題

hooks 部署是「複製非 symlink」：改 repo 內 hook 檔後 `git pull` 不生效，須重跑 install 同步——多次踩坑（含 #182 單檔手動 `install -m 700` 補救、P0-1 新增 warn hook 又加一筆）。hook 內 abspath 寫法不一（部分硬編碼、部分 `${PSC_REPO_ROOT}`），部署複製後路徑漂移風險常在。#128 要求：安裝自動化 + abspath/`${PSC_REPO_ROOT}` 一致性。

## 2. 目標與非目標

**目標**：install.sh 一鍵冪等裝好全部 hooks（三家 agent reconcile）；新增 `--verify` 健檢；hook 內路徑零硬編碼。
**非目標**：改為 symlink 部署（跨檔案系統/權限語意變更風險，維持複製模型但把「同步」自動化）；hook 業務邏輯變更。

## 3. 設計

### 3.1 install.sh hooks 段冪等化
- hooks 複製清單集中宣告（單一陣列，含 P0-1 warn hook）；每檔 `install -m 700` 冪等覆蓋；settings reconcile（Claude UserPromptSubmit/PostToolUse、codex/copilot 對應）重複執行不重複註冊（既有 reconcile 函式沿用，補測試）。
- 新增 `install.sh --verify`：逐 hook import/語法健檢（python hooks `py_compile`、shell hooks `bash -n`）＋ settings 註冊存在性檢查＋ `EnvironmentFile`／secret 檔存在性檢查（值不印出）；exit 非零＝部署不完整。

### 3.2 abspath 一致性
- shell hooks：一律 `${PSC_REPO_ROOT}`（launcher.py:179 已注入之既例；本機互動 session 由 env 檔提供）。
- Python hooks：一律 `paulshaclaw.config.paths` facade（P2 交付）；禁 `Path.home()` 直呼（P2 DoD 已涵蓋，本件把 hooks 目錄納入同一 grep-zero 檢查範圍）。
- lint：`--verify` 內含 `grep` 檢查 hooks 目錄零 `/home/` 字面與零 `Path.home()`（facade 檔除外）。

### 3.3 部署同步提醒（治本補丁）
- repo 內 hooks 檔案變更時的「需重跑 install」提醒：`--verify` 比對 repo 版與已部署版 hash，不一致列出 stale 清單——把「忘記同步」從記憶負擔變成可檢查狀態。

## 4. 測試

- 冪等：假 `$HOME` 環境跑 install hooks 段兩次 → 第二次零變更、settings 無重複註冊。
- `--verify`：完好部署 → exit 0；人為弄壞（缺檔/壞語法/stale hash）三情境 → exit 非零且訊息指名壞點。
- abspath lint：植入 `/home/` 字面的 fixture hook → verify 抓到。
- 乾淨環境 e2e（DoD）：假 `$HOME` 一鍵 `install.sh --skip-venv` → `--verify` 綠。

## 5. 風險

- 三家 agent settings 格式演進：reconcile 函式以既有測試釘住；未知格式 fail-loud 不猜。
- hash 比對誤報（行尾/權限差異）：以檔案內容 sha256 為準、權限另列檢查項。
