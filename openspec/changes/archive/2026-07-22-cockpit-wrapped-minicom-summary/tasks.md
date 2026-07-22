## 1. TDD — RED

- [x] 1.1 在 `tests/test_stage11_operator_cockpit.py` 新增測試：無 title、`command="bash"`、`pane_tty` 有 minicom 的 pane，`derive_summary` 應回 `minicom COMx`（用 monkeypatch stub `_minicom_summary` 或 `subprocess.run`/`ps`，不依賴真 tty）。跑測試確認 RED 且失敗原因是「回傳 cwd basename 而非 minicom COMx」。
- [x] 1.2 新增測試：無 title、`command="bash"`、tty 上無 minicom（`_minicom_summary` 回 None）→ `derive_summary` 應退回 `pane_current_path` basename。確認此案在改動前既有行為（RED 前應已通過或隨實作維持綠）。
- [x] 1.3 新增測試：無 title、`command="minicom"` → 走既有直接偵測路徑不變（回歸保護）。

## 2. 實作 — GREEN

- [x] 2.1 `paulshaclaw/cockpit/tmux.py`：定義 shell 名集合常數（`{bash, sh, zsh, dash, ash, fish}`）。
- [x] 2.2 `derive_summary`：在 `command == "minicom"` 分支之後、`pane_current_path` 分支之前，插入「title 不可用且 command ∈ shell 集合 → 試 `_minicom_summary(pane.pane_tty)`，非 None 才回傳」的邏輯；未命中透明落到既有 cwd basename。既有 minicom 分支與其餘分支不動。
- [x] 2.3 跑 1.1–1.3 測試轉綠。

## 3. 驗證與回歸

- [x] 3.1 `~/.local/bin/pytest tests/test_stage11_operator_cockpit.py -q` 全綠。
- [x] 3.2 全 cockpit 測試套件無回歸：`~/.local/bin/pytest tests/test_cockpit_*.py tests/test_stage11_operator_cockpit*.py -q`。
- [x] 3.3 `.venv/bin/python` 對 live tmux 實跑 `derive_summary`（%3/%4）確認回 `minicom COM0`/`COM1`（人工佐證，fail-soft）。

## 4. 收尾

- [x] 4.1 `openspec validate cockpit-wrapped-minicom-summary --strict` 通過。
- [x] 4.2 archive change、policy gate、conventional-commit（local commit；未經明確要求不 push/PR）。
