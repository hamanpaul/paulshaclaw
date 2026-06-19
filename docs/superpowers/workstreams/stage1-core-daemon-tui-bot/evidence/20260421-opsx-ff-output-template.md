# Stage1 Blocker 解鎖證據：opsx:ff 固定輸出格式

- 日期：2026-04-21
- 來源：
  - `.github/prompts/opsx-ff.prompt.md`
  - `.claude/commands/opsx/ff.md`

## 結論

- `/opsx:ff` 已定義固定輸出模板，包含 6 段固定區塊：
  1. `Preflight`
  2. `規範檢查`
  3. `Fleet 切分`
  4. `實作前命令`
  5. `Guardrails`
  6. `結論`

## 檢查重點

- prompt 與 command 內容一致（除 frontmatter）。
- 模板要求 `PASS | FAIL`、`READY | BLOCKED`，並強制附上證據路徑與下一步行動。
