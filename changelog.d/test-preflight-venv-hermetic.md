---
type: fix
scope: tests
---
- `test_preflight_uses_system_python_when_worktree_has_no_operator_venv` 未剝除呼叫端的 `VIRTUAL_ENV`，而 `start.sh` 依設計優先用 `$VIRTUAL_ENV/bin/python`；在 cortex gate（`cortex-manager.env` 帶 `VIRTUAL_ENV=<repo>/.venv`）下會跑到真 pytest 回 rc 5 而非假 `python3`，使任何派進本 repo 的 cortex build 在 worktree-isolation 卡即 `GateContradictionError`。測試改為同時 `env.pop("VIRTUAL_ENV")`，本機與 gate env 皆綠。
