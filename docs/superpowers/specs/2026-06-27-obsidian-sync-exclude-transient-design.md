# Obsidian Sync 只上 knowledge：排除 transient 記憶層設計

> 日期：2026-06-27 ｜ 來源：brainstorming（#153）
> 前置：`~/.agents/memory`（symlink → `~/notes/paulshaclaw/memory`）整棵被 `ob sync` 上傳到 Obsidian；只有 Dream-mode 整理後的 `knowledge/` 有保留價值，其餘為本機 transient。

## 1. 背景與問題

`~/notes` 即 Obsidian vault。WSL 上的 systemd user service `obsidian-sync.service`（經 `~/.local/bin/obsidian_sync_guard.sh` 啟動 `ob sync --continuous --path /home/paul_chen/notes`）把**整棵 memory** 上傳。但只有一層有價值：

| 層 | 性質 | 上同步？ |
|---|---|---|
| `knowledge/` | Dream-mode LLM wiki 化（MOC + atomic notes，~1.2M） | ✅ |
| `inbox/` `runtime/` `archive/` `hooks/` `log/` `work-centric/` | 本機過渡資料（intake / 狀態 / 封存 / 部署碼 / 日誌） | ❌ |

需求：像 `.gitignore` 一樣排除 transient 層，**結構不動**（`~/.agents/memory` 維持 symlink、真實資料維持在 `~/notes`、現有 wikilink 不變）。

## 2. 同步機制現況（已驗證）

- sync client = `obsidian-headless` v0.0.8（`ob` CLI，Node v22，跑在 **WSL/Linux** 端；Windows Obsidian 只是 GUI 下拉，非上傳端）。
- sync config：`~/.config/obsidian-headless/sync/<vaultId>/config.json`（vault `obs_vault`，root `/home/paul_chen/notes`，device `arc-wsl`）。**目前無 `ignoreFolders` 欄位** → 故全上傳。
- 該 config 內含 e2e 加密金鑰；**本設計與後續 commit 一律不得引用其值**，只以路徑指涉。

## 3. 決策（brainstorming 拍板）

| 決策 | 選擇 | 理由 |
|---|---|---|
| 排除機制 | **原生 `ob sync-config --excluded-folders`** | 工具內建選擇性同步；零搬移、零 symlink 重整、符合「結構不動」。優於 symlink 重整與資料夾搬移兩個替代方案。 |
| 舊副本清理 | **(a) 主動刪雲端/Windows 舊副本** | 設排除只擋未來、舊副本會 orphan 殘留；主動清達「乾淨」。先備份再刪。 |
| 可復現性 | **固化進設定流程** | `ignoreFolders` 存 machine-local config（不在 git），重設會遺失 → 設定流程冪等補設。 |

## 4. 目標與非目標

**目標**
- `ob` 不再上傳 6 個 transient 層，只同步 `paulshaclaw/memory/knowledge`。
- 清掉雲端 + Windows 端已上傳的舊 transient 副本。
- 排除設定可在 sync 重設後由設定流程自動恢復。

**非目標**
- 不改變 memory 目錄結構（symlink / 真實資料位置 / wikilink）。
- 不改任何 Python memory 程式（全走 `PSC_MEMORY_ROOT` + `memory_root/"knowledge"`，與本案無關）。
- 不處理 vault 內其他與 memory 無關的同步議題（如 `hooks/.venv` 以外的既有噪音）。

## 5. 已驗證事實（讀 `cli.js` + 對抗式覆驗）

1. `--excluded-folders <csv>` → 存為 config 欄位 **`ignoreFolders`**（`split(",").map(trim)` 之字串陣列）；傳空字串 `""` 會 `delete` 該欄位（清空）。
2. **路徑比對格式**：`_allowSyncFile` 為 `if ((t && e===r) || e.startsWith(r+"/")) return false`（`e`=vault 相對路徑、`t`=isFolder）。⇒ 條目須為 **vault 相對、無前導斜線、無結尾斜線、大小寫敏感**；命中該資料夾本身與其下所有內容。
3. **刪除語意（安全關鍵）**：reconcile 迴圈對「本機已不存在」的 server 檔，在形成刪除候選**之前**先 `if(!allowSyncFile(p)) continue;`。⇒ 被排除的 server 檔**永不進入 `"Deleting remote file"` 推送 → 變 orphan 殘留，設排除本身不會刪雲端/Windows 舊副本**。對「本機仍存在但被排除」的檔，另一迴圈條件亦含 `allowSyncFile`，同樣不推送 → 本機與遠端皆不動。
4. ⇒ 推論：**WSL `ob` 不會幫你刪舊副本**；清理須由「未被 ignore 的一方」發動（Windows 端刪除 → 同步把 server 端刪掉），且因 WSL 已 ignore，WSL 本機真實資料不受該遠端刪除影響（保留）。

## 6. 設計

### 6.1 套用排除（一次性）
```bash
ob sync-config --path /home/paul_chen/notes \
  --excluded-folders "paulshaclaw/memory/inbox,paulshaclaw/memory/runtime,paulshaclaw/memory/archive,paulshaclaw/memory/hooks,paulshaclaw/memory/log,paulshaclaw/memory/work-centric"
systemctl --user restart obsidian-sync.service   # --continuous 於啟動時 init filter，需重啟重讀
```
驗收：`ob sync-status --path /home/paul_chen/notes` 顯示 `Excluded folders:` 含 6 層；`knowledge` 不在內。

### 6.2 清理舊副本（choice a；順序重要）
1. **先備份**：`tar` 快照 `~/notes/paulshaclaw/memory/{inbox,runtime,archive,hooks,log,work-centric}` 至 vault 外（如 `~/.agents/backup/`）。WSL 本機本就保留這些資料，快照為額外保險。
2. **確認 6.1 排除已生效**（service 已重啟、`sync-status` 顯示 excluded）—— 必須先排除，Windows 刪除才不會被 WSL 重新上傳。
3. **在 Windows Obsidian 刪除** `paulshaclaw/memory/` 下那 6 個資料夾 → Obsidian Sync 將刪除推送至 server。WSL 因 ignore 不理會該遠端刪除，本機真實資料保留。
4. 驗收：Windows 端與 server 端不再有 6 層；WSL 本機 `ls ~/notes/paulshaclaw/memory/` 仍完整；`knowledge` 正常更新。
   - （替代自動化：暫時把 transient 移出 vault 讓 WSL `ob` 推送遠端刪除、設排除後再移回——與運行中 daemon 時序耦合、風險較高，**不採用**，僅記錄。）

### 6.3 固化進設定流程
- 在既有 obsidian sync 設定/啟動腳本（repo 內 `obsidian_sync_*.sh` 來源；plan 階段定位確切檔案）加入**冪等** `ensure_excluded_folders`：service 啟動前比對 `config.json` 之 `ignoreFolders`，**缺漏才 `ob sync-config` 補設**（避免每次重啟改寫 config / 製造 device version 噪音）。
- 6 層清單集中為單一常數，供 6.1 與 6.3 共用，避免漂移。

## 7. 風險與緩解

| 風險 | 緩解 |
|---|---|
| Windows 刪除誤傳回 WSL 刪本機 | 已驗證 WSL ignore 該路徑 → 不honor 遠端刪除；另有 6.2-1 tar 快照。 |
| 排除設定漂移／重設遺失 | 6.3 冪等固化於啟動流程。 |
| 順序錯（先 Windows 刪、後排除）導致 WSL 重新上傳 | 6.2 明列順序：先排除生效、再 Windows 刪。 |
| 金鑰外洩 | config.json 只以路徑指涉，不入 spec/commit/log。 |
| 路徑格式錯（誤帶結尾斜線）排除失效 | 依 §5.2：無結尾/前導斜線、大小寫須完全相符；套用後以 `sync-status` 驗證。 |

## 8. 不改動
`~/.agents/memory` 仍為 symlink、真實資料仍在 `~/notes/paulshaclaw/memory`、現有 wikilink 路徑不變、Python memory 程式不動。
