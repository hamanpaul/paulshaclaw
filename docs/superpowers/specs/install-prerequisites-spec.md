---
work_item: install-prerequisites
status: accepted
---

# README 安裝前置修正

## Requirements

對應 hamanpaul/paulshaclaw#325。

本工作源自 2026-09-07 使用者核可的五件 issue 修正計畫與 Cortex 平行派工指令。accepted 僅表示規格可執行，不表示程式或驗收已完成。

使用 Cortex 管理的隔離 branch/worktree；不得清理、stage 或覆寫 operator checkout 的既有變更。只處理本件 issue；所有實作、測試、OpenSpec、文件及 changelog 限本件 scope。不同工作線的 pyproject／CI／README 等共用檔須在各自 branch 修改，交由整合者處理衝突，不跨 worker worktree 寫入。

採 RED → 最小修正 → GREEN → 獨立 review → policy/preflight → PR 的受治理流程；未處置缺陷為 FAIL，接受風險需明文、有界且可追溯。禁止跳 gate 或手改 Cortex registry。部署、發布與本機 skill target 切換由 operator 整合驗收後執行，不由本 worker 自行進行；不得對外送 Telegram、覆寫既有 release、變更共享 service/config。PR 可依 Cortex 既有授權 gate 交付；不得僅憑 worker exit 0 宣告完成。

工作 C：#325 README 前置修正

建議 branch：`feature/325-install-prerequisites`；開始條件：#324 已 merge，且歷史 RED report 可查。

- [ ] README §A 明列 Ubuntu/Debian 的 `python3 python3-venv git`；說明 git 是 git+SHA dependencies 所需。pipx 段補安裝 pipx、git、ensurepath 與新 shell 驗證。
- [ ] 安裝步驟要求 pip 非零即停，補查 venv console script、`Cannot find command 'git'` 與 PATH 問題的排錯；不要用 `pipx upgrade` 暗示能從 PyPI 取得本 repo 的 release。
- [ ] release-contract distribution 節與新 release notes 同步前置。不要更改既有 artifact 或為消除 git 需求擴張 distribution 範圍。
- [ ] 用 candidate README 重跑 #324 的 TC-1／TC-1p → GREEN；TC-1c／TC-1g 維持 GREEN。歷史 README + 舊 artifact 仍保留精確 RED oracle，current README + candidate wheel 不允許 expected failure。

驗收：僅按文件宣告的套件建立容器即可完成 venv／pipx 安裝，完整 entry points 與 CLI exits 正確；#325 PR 附 RED/GREEN 對照與各自 README revision。
