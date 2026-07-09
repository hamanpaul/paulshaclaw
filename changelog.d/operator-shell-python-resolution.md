### Fixed
- operator shell（`scripts/start.sh` 與 `service-*.sh`）不再硬預設 repo `.venv` 的 python——改為優先挑能 `import paulsha_cortex` 的直譯器（`PSC_PYTHON` 可覆寫，預設系統 `python3`＝planes 裝在 `~/.local`），找不到 planes 時 fail-fast 給安裝指引，避免 `.venv` 缺 `paulsha_cortex`/`paulsha_hippo` 時 bot 於 `import` 崩潰、telegram readiness timeout。
