---
type: change
scope: cost
issue: 343
---
`cost.providers.agy.accounts[]` 比照 copilot 開放多帳號宣告（`{id, label, enabled}`），但只承接使用者的顯式宣告（yaml 或 `--footer agy:<label>[:<label>...]`）——絕不主動枚舉或讀取 `~/.gemini/google_accounts.json` 等任何帳號檔，#341 R4 零讀取守衛不變。`agy -p "/usage"` 本身不含帳號識別，故多帳號模式下的用量一律附掛到第一個 enabled 帳號（`active_account`）；`accounts[]` 非空但全部 disabled 時 agy 視為未生效，不 collect、不出現在 footer，即使頂層 `enabled: true`。footer／cockpit 呈現：宣告 `accounts[]` 後 segment 名稱從 `agy` 換成 `agy/<active 帳號 label>`，未宣告時逐字元不變仍是 `agy`。install TUI 與 `--footer agy:<label>` 對齊 copilot 語法，但與 copilot 不同的是——遇到尚未宣告的 label 會直接新建一筆 `{id, label, enabled: true}` 條目而非報錯；TUI 本身在 `agy` 父列下展開既有帳號子列，只能 toggle、不會新建。JSON report 的 `footer_selection.enabled.agy`：`accounts[]` 非空時改成 `{<account_id>: bool}`（與 `enabled.copilot` 同形狀），未宣告時維持既有的 bool 不變。
