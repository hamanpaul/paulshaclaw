### Fixed
- 修復 operator shell 啟動與既有機器 cutover（#243）：Python resolver 以 repo `PYTHONPATH` 驗證 cortex CLI、PyYAML cost config 與 Textual cockpit 的完整 closure，並讓 repo `.venv` 優先於 system Python；standalone service scripts 共用同一 resolver。安裝提示與 README 改為 PEP 668-safe repo `.venv`，cutover 以 `--upgrade --force-reinstall` 對齊 pyproject pins，且必要的 plane 安裝與 systemd restart/active gates 改為 fail-closed。
