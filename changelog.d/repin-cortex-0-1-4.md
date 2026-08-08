---
type: fix
---
`paulsha-cortex` pin 改指向正式 release **v0.1.4** 的 SHA（`b868760`），取代前一輪暫時指向的未發版 main commit `ea4cd53`。內容完全相同（v0.1.4 就是把該 commit 的 lifecycle 詞彙聯集收攏發版），此變更只是讓 pin 對齊「部署以 release 為主」的原則——本機 systemd 服務用的 pipx 也已升到 v0.1.4，pin 與部署版本自此一致。
- `paulsha-hippo` 本輪**不動**，續留 main SHA `96513bc`：詞彙聯集已進 hippo main 但尚未收進任何 tag。已在 `pyproject.toml` 該行上方註明「下次 hippo 發版時改指向該 tag 的 SHA」，避免這個暫時狀態被誤讀為常態。hippo 不進 systemd 服務、只進本 repo 的 `.venv`，影響面小於治理平面。
