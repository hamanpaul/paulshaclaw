---
work_item: install-prerequisites
---

# README 安裝前置修正

對應 hamanpaul/paulshaclaw#325。

保持 git+SHA distribution；此件只進件，不 start、不加 auto label。只有 #324 PR 已 merge 且歷史 RED 證據可查，operator 才能解除等待。

## Current Sprint

- [ ] 依本 work item 的 accepted spec/design/plan 實作並提交 scope 內變更。
- [ ] 完成 focused tests、完整 preflight、獨立 review 與 PR。
- [ ] 核對合併、正式 artifacts 與適用的 installed/runtime evidence 後結案。

## Handoff

工作 C：#325 README 前置修正

建議 branch：`feature/325-install-prerequisites`；開始條件：#324 已 merge，且歷史 RED report 可查。

- [ ] README §A 明列 Ubuntu/Debian 的 `python3 python3-venv git`；說明 git 是 git+SHA dependencies 所需。pipx 段補安裝 pipx、git、ensurepath 與新 shell 驗證。
- [ ] 安裝步驟要求 pip 非零即停，補查 venv console script、`Cannot find command 'git'` 與 PATH 問題的排錯；不要用 `pipx upgrade` 暗示能從 PyPI 取得本 repo 的 release。
- [ ] release-contract distribution 節與新 release notes 同步前置。不要更改既有 artifact 或為消除 git 需求擴張 distribution 範圍。
- [ ] 用 candidate README 重跑 #324 的 TC-1／TC-1p → GREEN；TC-1c／TC-1g 維持 GREEN。歷史 README + 舊 artifact 仍保留精確 RED oracle，current README + candidate wheel 不允許 expected failure。

驗收：僅按文件宣告的套件建立容器即可完成 venv／pipx 安裝，完整 entry points 與 CLI exits 正確；#325 PR 附 RED/GREEN 對照與各自 README revision。
