---
type: fix
scope: launcher
issue: 334
---
修復 pipx release wheel 未包含 `core/commands.json`、launcher 未辨識 Cortex nested manager lock，以及頂層 `paulshaclaw --no-cockpit` 參數不相容，並補齊 installed runtime 從非 repo 目錄啟動與乾淨停止的驗證證據。
