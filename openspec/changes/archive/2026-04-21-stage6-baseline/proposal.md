## Why

Stage 6 `ops-companion` 安全治理基線已於 `wt/stage6-ops-companion-security` 完成（commit `604f0b0` + fixup `fdb229a`），但尚未以 OpenSpec archive 反向記錄，導致與 Stage 0/1/2 的收斂格式不一致。為避免後續 Stage 7/安全擴展缺少 canonical diff 原點，本 change 將 Stage 6 已落地成果追認為 `stage6-security-governance` capability。

## What Changes

- 追認 `paulshaclaw/security/ops_companion.py` 為 Stage 6 安全核心實作：approval gate、redaction、append-only audit、gate→audit 封裝
- 追認 `tests/test_ops_companion_security.py` 為 Stage 6 baseline 驗證（最終 8 tests）
- 追認 `openspec/specs/stage6/README.md` 的規格描述為 Stage 6 設計基線
- 追認 `docs/superpowers/workstreams/stage6-ops-companion-security/{task,todo,review}.md` 與 `evidence/*` 為交付證據
- 追認 `custom-skills/ops-companion/README.md` 為 sync-back staging scaffold
- 新增 canonical spec：`openspec/specs/stage6-security-governance/spec.md`
- 無 BREAKING

## Capabilities

### New Capabilities

- `stage6-security-governance`: Stage 6 安全治理基線能力，涵蓋高風險 approval gate、redaction/classification、append-only audit、decision-to-audit 封裝與 sync-back gate。

### Modified Capabilities

- 無。

## Impact

- **Specs**
  - `openspec/specs/stage6/README.md`
  - `openspec/specs/stage6-security-governance/spec.md`
- **Code**
  - `paulshaclaw/security/ops_companion.py`
  - `tests/test_ops_companion_security.py`
- **Workstream artifacts**
  - `docs/superpowers/workstreams/stage6-ops-companion-security/{task,todo,review}.md`
  - `docs/superpowers/workstreams/stage6-ops-companion-security/evidence/*`
  - `docs/superpowers/archive/stage6-ops-companion-security-20260420T1855570800.md`
- **Sync-back target**
  - `custom-skills/ops-companion/README.md`
