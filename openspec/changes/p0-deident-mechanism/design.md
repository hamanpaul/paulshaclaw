## Context

完整設計：`docs/superpowers/specs/2026-07-06-p0-deident-mechanism-design.md`（已過 codex adversarial review，4 findings 修正於 `f4d8862`）。本檔僅收斂實作級決策。

現況：repo PUBLIC；R-21 因 tier 未宣告回 PASS-not-applicable（從未掃描）；21 命中 / 12 檔（#201 逐檔清單）；字面禁詞不得出現在任何公開 tracked 檔（含本 change 的所有 artifact）。

## Goals / Non-Goals

**Goals:**
- tracked 檔識別資訊歸零（安全驗證器證明，非 raw grep）。
- 長效 gate = 上游修復後的 R-21，併入既有 Policy Check；本 repo 零自製 CI lint。
- authoring-time warn hook（第二層，不阻塞寫入）。

**Non-Goals:**
- git 歷史抹除（Stage B 另案待授權）。
- gitleaks/trufflehog 整合（上游 #45 item 3，後續引擎版本）。
- 他 repo 內容清理。

## Decisions

1. **機制正主 = 上游 R-21（paulsha-conventions #45）**：visibility 綁定（PUBLIC 一律掃）、嚴重度分層（結構/憑證 FAIL、字面 marker WARN 起步）、marker env 擴充點、輸出遮蔽。本 repo 只 pin bump 消費。理由：owner 同時擁有兩 repo；避免造會丟掉的 interim lint；gate 藏在既有流程 = 不影響開發節奏。
2. **工作序鎖死**（防「先開掃描後清理」把盤點印進公開 CI log）：上游修復+release → 本機 dry-run（= #201 驗收掃描）→ Stage A 清理 → pin bump → hook。
3. **字面 marker 只走 secret 通道**：CI 用 secret env 餵引擎擴充點；本機 hook 讀 `~/.config/paulshaclaw/deident-markers.txt`。任何公開 yml/spec/issue 永不含字面值。
4. **安全驗證器**：讀 secret 字面表 + 結構 regex，輸出僅計數/遮蔽代號/檔案路徑，永不印命中行（review finding ①）。
5. **env 化命名**：第 2 corpus root 過渡 env `PSC_EXTRA_CORPUS_ROOT`，P2 facade 落地後收編為別名一版再移除。

## Risks / Trade-offs

- 上游 release 時程為關鍵路徑——paulshaclaw 側 Stage A 可先行（清理不依賴引擎），僅 pin bump 等 release。
- 字面 marker WARN 起步（非 FAIL）：新字面洩漏短期只警告——由 authoring hook + review 補位，baseline 清零後上游再升 FAIL。
- pin bump 後誤報無 policy-exempt 逃生（R-21 對 public 無豁免設計）→ 逃生門 = revert pin + 回 #45 補 fixture。
