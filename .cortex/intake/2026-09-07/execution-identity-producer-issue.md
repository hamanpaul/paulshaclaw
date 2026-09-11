# Cortex workflow status 實際執行身份

## 背景

支援 hamanpaul/paulshaclaw#328 的上游 producer 工作，源自 operator 2026-09-07「派入 cortex 開始平行作業」指令。下游 issue 由 paulshaclaw 的 consumer PR 結案，本件不得提前關閉下游 issue。

## 範圍

只修改 paulsha-cortex 的 status projection、job/run/card/attempt 身份解析、測試與契約文件；不寫 paulshaclaw，不改共享 runtime／service，不清理既有 workflows。

- 從 registry 的實際 job 取得 executor/model_id；不可從 phase 或 persona 猜模型。
- 相同 run 當前 card 的綁定 in-flight job 優先，其次同卡最後實際執行；無證據顯示 unknown／未派工。
- additive 公開欄位涵蓋 executor、model、job_id、card、identity_source 與執行狀態；先核對既有契約避免破壞相容性。
- planned、actual、last execution 必須明確區分，阻塞後上次執行者不得顯示為仍在跑。
- 所有 workflow status sections 一致涵蓋，保留既有欄位。

## 驗收

- [ ] 測試多卡同 phase、retry 換模型、缺值、未派工、deterministic、needs_human、完成及跨 repo/run 綁定。
- [ ] producer fixture 與契約文件可供 paulshaclaw consumer 使用。
- [ ] focused/full tests、policy/preflight、異家 review 通過；最小 scope PR merge。
- [ ] 交付 immutable merge SHA 與去識別化 fixture，供下游固定 pin 後做 installed producer→consumer 驗收。

禁止直接發布新版、改 operator config、部署 service 或跨 repo 實作。遵循本 repo OpenSpec/changelog/PR 政策及 Cortex 正式交付 gates。
