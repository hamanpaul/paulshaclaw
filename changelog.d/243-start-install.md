### Fixed
- 修復 operator shell 啟動與既有機器 cutover（#243）：Python resolver 現在驗證 `paulsha_cortex` + `textual` 完整 closure，僅在 pipx cortex shebang 的直譯器也具備 cockpit runtime 時才採用；安裝提示與 README 改為 PEP 668-safe repo `.venv`，cutover 以 `--upgrade --force-reinstall` 對齊 pyproject pins。
