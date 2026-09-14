---
type: fix
scope: deploy
issue: 345
---
`install --apply`／`upgrade --apply` 的互動式 footer 選擇在缺 `textual` 套件的環境，先前會因 noop stub 的 `App.run()` 回 `None` 而被誤判成使用者按 esc，report 寫成 `footer_selection.mode == "cancelled"` 靜默取消。現改為在進 TUI 前依模組旗標明確判斷：report 回報 `{"mode": "skipped", "reason": "textual-missing"}`（與既有 `plan-only`／`no-tty` 的 skipped 條目同形狀），stderr 提示「請安裝 textual 或改用 `--footer <spec>`」，config 不動、exit code 維持 0（install 本身未失敗）。
