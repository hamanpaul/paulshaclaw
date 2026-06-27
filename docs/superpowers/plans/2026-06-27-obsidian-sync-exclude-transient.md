# Obsidian Sync 排除 transient 記憶層 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓 WSL `ob` 只同步 `paulshaclaw/memory/knowledge`，排除其餘 6 個 transient 層，並清掉雲端/Windows 舊副本、把排除設定固化進啟動流程。

**Architecture:** 用 Obsidian Sync 原生 `ob sync-config --excluded-folders`（存為 config 的 `ignoreFolders`）排除；結構完全不動。已驗證設排除不會刪遠端舊副本（orphan），故清理由 Windows 端發動；固化以冪等 `ensure_excluded_folders` 寫進 guard，service 啟動時自動補。

**Tech Stack:** `obsidian-headless` v0.0.8（`ob` CLI / Node v22）、systemd user service `obsidian-sync.service`、bash guard `~/.local/bin/obsidian_sync_guard.sh`（live source = `ref/custom-skills/obs-service-wsl-handler/bin/obsidian_sync_guard.sh`）、`tar`。

**Spec:** `docs/superpowers/specs/2026-06-27-obsidian-sync-exclude-transient-design.md` ｜ **Issue:** #153

**排除清單（單一真相，6 層，vault 相對、無前導/結尾斜線、大小寫須完全相符）：**
```
paulshaclaw/memory/inbox,paulshaclaw/memory/runtime,paulshaclaw/memory/archive,paulshaclaw/memory/hooks,paulshaclaw/memory/log,paulshaclaw/memory/work-centric
```

---

## Task 1: 備份 transient 6 層（先做，非破壞性）

**Files:** 無 repo 變更（產出 `~/.agents/backup/obsidian-transient-<ts>.tar.gz`）

- [ ] **Step 1: 建備份目錄並打包 6 層**

```bash
ts="$(date +%Y%m%d-%H%M%S)"
mkdir -p ~/.agents/backup
tar -czf ~/.agents/backup/obsidian-transient-$ts.tar.gz \
  -C ~/notes/paulshaclaw/memory \
  inbox runtime archive hooks log work-centric
```

- [ ] **Step 2: 驗證備份完整可解**

Run:
```bash
tar -tzf ~/.agents/backup/obsidian-transient-$ts.tar.gz | sed 's#/.*##' | sort -u
ls -lh ~/.agents/backup/obsidian-transient-$ts.tar.gz
```
Expected: 列出 `archive inbox hooks log runtime work-centric` 六個頂層；檔案大小約 ~30M。

> 不需 commit（備份在 vault 外、非 repo 內容）。WSL 本機資料本就保留，此快照為 Windows 刪除前的額外保險。

---

## Task 2: 套用 excluded-folders + 重啟 + 驗證（非破壞性）

**Files:** 無 repo 變更（改 machine-local `~/.config/obsidian-headless/sync/<vaultId>/config.json` 的 `ignoreFolders`）

- [ ] **Step 1: 記下套用前狀態（回溯用）**

Run:
```bash
NODE=~/.nvm/versions/node/v22.20.0/bin/node; OB=~/.nvm/versions/node/v22.20.0/bin/ob
"$NODE" "$OB" sync-status --path /home/paul_chen/notes 2>&1 | sed -n '1,12p'
```
Expected: 無 `Excluded folders:` 行（目前未設）。

- [ ] **Step 2: 套用排除（取代式，目前無其他排除，等同設定這 6 層）**

```bash
NODE=~/.nvm/versions/node/v22.20.0/bin/node; OB=~/.nvm/versions/node/v22.20.0/bin/ob
"$NODE" "$OB" sync-config --path /home/paul_chen/notes \
  --excluded-folders "paulshaclaw/memory/inbox,paulshaclaw/memory/runtime,paulshaclaw/memory/archive,paulshaclaw/memory/hooks,paulshaclaw/memory/log,paulshaclaw/memory/work-centric"
```
Expected: 印出含 `Excluded folders: paulshaclaw/memory/inbox, ...` 的更新後設定。

- [ ] **Step 3: 重啟 service 讓 --continuous 重讀 filter**

```bash
systemctl --user restart obsidian-sync.service
sleep 3
systemctl --user is-active obsidian-sync.service
```
Expected: `active`。

- [ ] **Step 4: 驗證排除生效、knowledge 仍同步**

Run:
```bash
NODE=~/.nvm/versions/node/v22.20.0/bin/node; OB=~/.nvm/versions/node/v22.20.0/bin/ob
"$NODE" "$OB" sync-status --path /home/paul_chen/notes 2>&1 | grep -i "excluded"
ls ~/notes/paulshaclaw/memory/        # 本機 6 層仍在（排除不刪本機）
```
Expected: `Excluded folders:` 列出 6 層且**不含 knowledge**；本機 `ls` 仍顯示全部 7 個資料夾（含 knowledge）。

> 此步非破壞性、可回溯（`--excluded-folders ""` 清空還原）。完成後即可通知使用者「排除已生效，可在 Windows 刪」。

---

## Task 3: 固化 `ensure_excluded_folders` 進 guard（程式變更 + redeploy）

**Files:**
- Modify: `ref/custom-skills/obs-service-wsl-handler/bin/obsidian_sync_guard.sh`（live source；於 `clear_terminal_stop_flag` 後插入）
- Redeploy: 複製到 `~/.local/bin/obsidian_sync_guard.sh`

> 說明：guard 是 vendored 外部 skill 的 live 副本（與 deployed 完全一致）。在此加冪等補設最 DRY（config/vault/OB_BIN 此處已解析）。若日後要避免與 upstream 分歧，替代法為 systemd drop-in `ExecStartPre`（記錄於此，不採用）。

- [ ] **Step 1: 在 guard 插入 PSC_EXCLUDED_FOLDERS 常數與函式**

在 `obsidian_sync_guard.sh` 的 `clear_terminal_stop_flag` 行之後、`prepare_start_state()` 定義之前，插入：

```bash
PSC_EXCLUDED_FOLDERS="${PSC_EXCLUDED_FOLDERS:-paulshaclaw/memory/inbox,paulshaclaw/memory/runtime,paulshaclaw/memory/archive,paulshaclaw/memory/hooks,paulshaclaw/memory/log,paulshaclaw/memory/work-centric}"

ensure_excluded_folders() {
  local merged
  merged="$(CONFIG_FILE="$LOADED_CONFIG_FILE" WANT="$PSC_EXCLUDED_FOLDERS" python3 - <<'PY'
import json, os
cfg = os.environ["CONFIG_FILE"]
want = [x.strip() for x in os.environ["WANT"].split(",") if x.strip()]
try:
    cur = json.load(open(cfg)).get("ignoreFolders", []) or []
except Exception:
    cur = []
missing = [w for w in want if w not in cur]
print("" if not missing else ",".join(list(cur) + missing))
PY
)"
  if [ -z "$merged" ]; then
    log "excluded-folders already satisfied"
    return 0
  fi
  log "applying excluded-folders (union): $merged"
  if [ -n "${OB_NODE_BIN:-}" ]; then
    "$OB_NODE_BIN" "$OB_BIN" sync-config --path "$LOADED_VAULT_PATH" --excluded-folders "$merged" >>"$LOG_PATH" 2>&1 || log "warning: sync-config failed (continuing)"
  else
    "$OB_BIN" sync-config --path "$LOADED_VAULT_PATH" --excluded-folders "$merged" >>"$LOG_PATH" 2>&1 || log "warning: sync-config failed (continuing)"
  fi
}
```

- [ ] **Step 2: 在 sync 啟動前呼叫**

在 `log "starting continuous sync for $LOADED_VAULT_PATH"` 之前插入一行：

```bash
ensure_excluded_folders
```

- [ ] **Step 3: 語法檢查**

Run: `bash -n ref/custom-skills/obs-service-wsl-handler/bin/obsidian_sync_guard.sh`
Expected: 無輸出（語法正確）。

- [ ] **Step 4: 冪等性驗證（排除已存在時應為 no-op）**

Run（模擬：config 已含 6 層後跑函式判斷）：
```bash
CONFIG_FILE=~/.config/obsidian-headless/sync/*/config.json \
WANT="paulshaclaw/memory/inbox,paulshaclaw/memory/runtime,paulshaclaw/memory/archive,paulshaclaw/memory/hooks,paulshaclaw/memory/log,paulshaclaw/memory/work-centric" \
python3 -c 'import json,os,glob;cfg=glob.glob(os.environ["CONFIG_FILE"])[0];want=os.environ["WANT"].split(",");cur=json.load(open(cfg)).get("ignoreFolders",[]) or [];print("NOOP" if all(w in cur for w in want) else "WOULD-SET")'
```
Expected: `NOOP`（Task 2 已套用後，固化判定為無需變更）。

- [ ] **Step 5: Redeploy 並重啟**

```bash
cp ref/custom-skills/obs-service-wsl-handler/bin/obsidian_sync_guard.sh ~/.local/bin/obsidian_sync_guard.sh
systemctl --user restart obsidian-sync.service
sleep 3
grep -a "excluded-folders already satisfied\|applying excluded-folders" ~/.local/state/obsidian-automation/obsidian-sync-guard.log | tail -2
```
Expected: log 出現 `excluded-folders already satisfied`（因 Task 2 已設）。

- [ ] **Step 6: Commit**

```bash
git add ref/custom-skills/obs-service-wsl-handler/bin/obsidian_sync_guard.sh
git commit -m "feat(memory): #153 guard 啟動時冪等補設 ob excluded-folders（固化）"
```

---

## Task 4: 清理雲端/Windows 舊副本（使用者手動，須在 Task 2 之後）

> 這步**不是跑指令就清乾淨**——已驗證 WSL `ob` 只 skip、留 orphan，不會刪遠端。清理須由 Windows 端發動。

- [ ] **Step 1（前提）：** 確認 Task 2 Step 4 已顯示 6 層 excluded。
- [ ] **Step 2（使用者於 Windows Obsidian）：** 刪除 vault 內 `paulshaclaw/memory/` 下 6 個資料夾（`inbox` `runtime` `archive` `hooks` `log` `work-centric`）。Obsidian Sync 將刪除推送至 server。
- [ ] **Step 3: 驗證 WSL 本機未受影響**

Run: `ls ~/notes/paulshaclaw/memory/`
Expected: 6 層 + `knowledge` 仍完整（WSL 因 ignore 不理會該遠端刪除）。

- [ ] **Step 4: 驗證 knowledge 仍正常雙向**：在 Windows 端確認 `knowledge` 內容仍在且會更新。

---

## Task 5: 收尾

- [ ] **Step 1: 開 PR（body 寫 `Closes #153`，zh-tw）**

```bash
git push -u origin feature/153-obsidian-sync-exclude-transient
gh pr create --base main --head feature/153-obsidian-sync-exclude-transient \
  --title "feat(memory): #153 Obsidian sync 只上 knowledge（排除 transient 層 + 固化）" \
  --body "Closes #153

- ob sync-config --excluded-folders 排除 6 個 transient 記憶層，只同步 knowledge
- guard 啟動時冪等補設（固化）
- 清理舊副本為 Windows 端手動（已驗證 ob 不刪遠端 orphan）
- 結構不動：symlink/真實資料/wikilink 皆不變"
```

- [ ] **Step 2: 確認 Policy Check CI 綠**（R-12 分支名、R-10 title、R-19/R-20）後再 merge（依使用者偏好，不自動 merge）。

---

## Self-Review

- **Spec coverage：** §6.1→Task 2；§6.2→Task 1(備份)+Task 4(清理)；§6.3→Task 3；§7 風險（順序、金鑰、格式）已落在各 Task 前提與驗證；§8 不改動→各 Task 皆無結構變更。✓
- **Placeholder scan：** 無 TBD；Task 3 含完整 shell。✓
- **一致性：** 6 層 CSV 在 header / Task 2 / Task 3 / Task 4 完全一致。✓
- **本次執行範圍：** 依使用者指示，現在只做 **Task 1 + Task 2**；Task 3（固化）、Task 4（使用者 Windows 刪）、Task 5（PR）為後續。
