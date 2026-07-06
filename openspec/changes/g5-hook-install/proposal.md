## Why

hooks 部署為複製非 symlink——改 repo 檔後不重跑 install 即漂移（多次踩坑）；hook 內 abspath 寫法不一（#128）。拆包後 install story 依賴此件（站穩閘 G5）。

## What Changes

- install.sh hooks 段冪等化：複製清單集中宣告（含 P0-1 warn hook）、`install -m 700` 冪等覆蓋、三家 settings reconcile 不重複註冊。
- 新增 `install.sh --verify`：hook 語法/import 健檢＋settings 註冊檢查＋env/secret 檔存在性（沿 deploy 三分 split，不印值）＋ **repo↔部署 hash 比對列 stale 清單**（把「忘記同步」變可檢查狀態）。
- abspath 一致性：shell hooks 一律 `${PSC_REPO_ROOT}`；Python hooks 一律 P2 facade；verify 內建 grep lint（hooks 目錄零 `/home/` 字面、零 `Path.home()` 直呼）。

## Capabilities

### New Capabilities
<!-- 無 -->

### Modified Capabilities
- `stage7`: 部署平面新增 hooks 安裝冪等與 verify 健檢（含 stale 偵測與 abspath lint）要求。

## Impact

- 受影響碼：`install.sh`（hooks 段＋--verify）、hooks 檔（abspath 統一）、reconcile 函式測試。
- 依賴：**p2-usability-phase0**（Python hooks 走 facade）。
- 依據：`docs/superpowers/specs/2026-07-06-g5-hook-install-design.md`。
