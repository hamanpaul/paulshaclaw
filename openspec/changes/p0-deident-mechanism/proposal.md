## Why

repo 已 PUBLIC，但 tracked 檔殘留去識別化資訊（21 命中 / 12 檔，見 #201；含內網 FQDN、供應商名、個人工作樹目錄名），且 policy engine R-21 因 tier 未宣告從未掃描本 repo——洩漏面每天擴大，違反 AI-SEC-001 紅線。

## What Changes

- Stage A 止血：#201 清單 12 檔字面值換中性佔位；`memory/instruction_corpus.py` 與 `scripts/start.sh` 的第 2 corpus root 改 env 供給（`PSC_EXTRA_CORPUS_ROOT`）。
- 長效機制（上游正主）：paulsha-conventions #45 修 R-21（visibility 綁定、嚴重度分層、marker env 擴充點、輸出遮蔽）→ release → 本 repo policy-check pin bump，gate 併入既有 Policy Check（零新 CI job）。
- 安全驗證器：de-ident 驗收只出計數與遮蔽代號，永不印命中行文字（禁 raw `git grep` 當 oracle）。
- authoring-time 第二層：PostToolUse(Write|Edit) warn-only hook，字面表在 `~/.config/paulshaclaw/`（不入版控）。
- 明確排除：Stage B（git 歷史改寫）另案待授權。

## Capabilities

### New Capabilities
- `deident-governance`: 公開 repo 去識別化治理——tracked 檔零識別資訊、安全驗證器語意、authoring hook 警告、上游 R-21 gate 生效條件。

### Modified Capabilities
<!-- 無既有 capability 的 requirement 變更；dream --instruction-root 行為不變（僅供給來源 env 化） -->

## Impact

- 受影響碼：`paulshaclaw/memory/instruction_corpus.py`、`scripts/start.sh`、2 個 test fixture、8 份 docs/openspec 歷史文件（字面替換）、hooks 安裝面（新 warn hook）。
- 跨 repo 依賴：paulsha-conventions #45（引擎修復與 release 先行）；本 repo `.github/workflows/policy-check.yml` pin bump。
- 不動 `~/.agents/memory`（記憶內容在 repo 外，不受影響）。
