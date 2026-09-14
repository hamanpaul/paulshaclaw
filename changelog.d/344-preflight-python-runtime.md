---
type: fix
scope: scripts
issue: 344
---
`scripts/preflight-tests.sh` 在沒有 `.venv` 的 checkout（Cortex preflight worktree、乾淨 clone）會選到只有 pytest、缺 repo runtime 的系統 python3，讓 11 個 collection error 淹沒真正原因。`preflight_python_has_runtime()` 改為一次驗 `import pytest, paulsha_cortex, textual`，驗不過就換下一個候選；候選順序在 `PSC_PYTHON` 之後、repo `.venv` 之前加入 `$VIRTUAL_ENV/bin/python`（僅 `VIRTUAL_ENV` 非空時），治理引擎 sanitized env 只放行 `VIRTUAL_ENV` 也能指到 operator runtime。全部候選都不合格時 `resolve_preflight_python` 會把試過的每個候選與各自缺的模組印到 stderr，`preflight-tests.sh` 的錯誤訊息改為明講所需模組並提示可設 `VIRTUAL_ENV` 或 `PSC_PYTHON`。
