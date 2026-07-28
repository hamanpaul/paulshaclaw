---
type: fix
issue: 243
---
修復 operator shell 啟動與既有機器 cutover（#243）：Python resolver 以 repo `PYTHONPATH` 驗證 cortex CLI、PyYAML cost config 與 Textual cockpit 的完整 closure，並讓 repo `.venv` 優先於 system Python；standalone service scripts 共用同一 resolver。安裝提示與 README 改為 PEP 668-safe repo `.venv`，cutover 以 `--upgrade --force-reinstall` 對齊 pyproject pins；operator/plane/hippo 安裝、monitor config 寫入、legacy unit 除役及 systemd restart/settled-active gates 全部改為 fail-closed。
