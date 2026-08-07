# Release Contract 與 Distribution Strategy

> 本文件定義 `paulshaclaw` 正式版本發布的契約、前置 gate、失敗與重跑規則，
> 並裁決第一階段的 distribution authority。涵蓋 issue #280 的 A（release contract）
> 與 D（distribution strategy）。
>
> E（artifact-driven deployment）依序須在 artifact 交付邊界建立後再做，不在本文範圍。

## 1. 適用範圍

- 本 repo `paulshaclaw`（operator shell）。
- 記憶平面 `paulsha-hippo` 與治理平面 `paulsha-cortex` 是**外部依賴**，由各自 repo 的 release
  lifecycle 管理；本 repo 的 release artifact 透過 `pyproject.toml` 的 `git+<SHA>` pin 引回，
  不在本文定義的發布邊界內。

## 2. 版本來源與一致性契約（A）

### 2.1 四個版本來源

正式 release 的版本號必須在以下四個來源**完全一致**，任一不一致即視為 release 失敗：

| 來源 | 檔案 / ref | 說明 |
|---|---|---|
| 1 | `VERSION` | 單行純文字 SemVer，不帶 `v` 前綴 |
| 2 | `pyproject.toml` | `[project].version`，與 `VERSION` 相同 |
| 3 | Git tag `vX.Y.Z` | 帶 `v` 前綴；必須指向 release commit（HEAD） |
| 4 | `CHANGELOG.md` | 存在 `## [X.Y.Z]` release section（Keep a Changelog 格式） |

### 2.2 一致性 gate

`scripts/check-release-consistency.py` 為權威實作：

- 不帶 `--tag`：只檢查來源 1 == 來源 2（一般 CI／本機 preflight 可隨時跑）。
- 帶 `--tag vX.Y.Z`：完整 release gate，比對四個來源，並驗證 tag 指向 HEAD
  （source revision 一致），任一不符即非零退出（fail-closed）。

`tests/test_release_consistency.py` 覆蓋每種不一致情境。

### 2.3 SemVer 裁切規則

遵循 [Semantic Versioning](https://semver.org/)：`MAJOR.MINOR.PATCH`。

- `0.x.y` 階段：初始開發期，任何 breaking change 可進 `MINOR`；`PATCH` 僅用於向下相容的修正。
- 目前基線 `0.1.0`（與 `VERSION` / `pyproject.toml` 一致）；第一次正式 release 由 owner 裁決版本號。
- pre-release / build metadata（`-alpha.1` / `+build.5`）暫不使用，待有需求再於本契約增補。

### 2.4 Release authority

- **唯一 release authority 為 owner**：只有 owner 可以 cut tag、決定版本號與 release 時機。
- release workflow（`.github/workflows/release.yml`）由 `vX.Y.Z` tag push 觸發，**不**由一般
  `main` push 觸發——一般 `main` push 不會發布正式版本。
- workflow 權限最小化為 `permissions: contents: write`（建立 Release 的最小需求）。

## 3. 前置 gate（A）

正式 tag push 前，依序須通過：

1. **CI / policy / security gate**：`tests.yml`（pytest）+ `policy-check.yml`。
2. **版本一致性 gate**：`scripts/check-release-consistency.py`（本機 preflight 與 release workflow 都會跑）。
3. **本機 release dry-run**：`scripts/release-artifacts.sh`（build wheel+sdist、metadata/content
   檢查、乾淨 venv 安裝 smoke test）。可加 `--no-install` 跳過乾淨 venv 安裝（離線環境）。
4. **#270 de-identification gate**：第一次正式 public release 前必須完成，避免正式 artifact
   將新識別資訊永久固化。
5. **#265 history rewrite 裁決**：第一次穩定 tag 前 owner 須明確裁決；若要 force-push 改寫歷史，
   應先完成改寫再建立正式 tag。

## 4. 失敗行為、重跑與撤銷（A）

### 4.1 fail-closed 原則

- release workflow 在任一 gate（一致性、build、content、smoke）失敗時**不建立** GitHub Release，
  也不留下半成品 artifact 紀錄。
- **同一 tag 不得靜默覆寫不同 artifact**：workflow 建立 Release 前先檢查既有 release 是否存在，
  存在即 FAIL（不使用 `--force`）。覆寫需 owner 明確裁決並手動移除既有 release。

### 4.2 重跑規則

- **一致性／build／smoke 失敗**：修正 source 後重新 cut tag（或以同一 commit 重打 tag），
  再次 push tag 觸發 workflow。
- **GitHub Release 建立失敗（但 artifact 已 build 通過）**：可手動以 `gh release create` 補上
  已 build 的 artifact；須確保 tag 指向同一 commit。
- **tag 已 push 但 release 未建立**：workflow 可由 `workflow_dispatch` dry-run 驗證後再決定補建立。

### 4.3 撤回（rollback）

撤回不等於「刪除 GitHub Release」。建議的撤回路徑：

1. **標記撤回**：在 GitHub Release 說明加上 `⚠️ 已撤回（原因）`，保留 artifact 供稽核與復原比對。
2. **停止推薦安裝**：在 README / CHANGELOG 標註該版本不建議安裝，並指向可回滾的上一穩定版本。
3. **安裝端 rollback**：使用者依本文 §6「Release recovery / 撤回」從上一穩定版本重新安裝。
4. **刪除 Release（最後手段）**：只有當 artifact 含安全或法務風險、且稽核無價值時，才由 owner
   手動刪除 GitHub Release 與 tag；刪除前應備份 artifact checksum 與 release notes。

> 刪除 tag 會破壞「tag = immutable source revision」假設；非必要不做。

## 5. Distribution strategy 裁決（D）

### 5.1 裁決

**第一階段以 GitHub Release artifacts 為唯一 distribution authority。**

正式 wheel 與 sdist 附於 `vX.Y.Z` GitHub Release，附 SHA-256 checksums 與 release notes；
使用者從 Release artifact 安裝（`pip install <wheel>`）。不發布到 PyPI 或其他 registry。

### 5.2 實測依據

`pyproject.toml` 對 `paulsha-hippo` / `paulsha-cortex` 是 `git+<url>@<SHA>` 形式的
direct reference：

```
Requires-Dist: paulsha-hippo @ git+https://github.com/hamanpaul/paulsha-hippo@eb2ccb86...
Requires-Dist: paulsha-cortex @ git+https://github.com/hamanpaul/paulsha-cortex@3dfea79f...
```

實測（`python -m build` 產出 wheel 後檢視 `*.dist-info/METADATA`）確認 built artifact 的
metadata 確實帶有 direct URL `Requires-Dist`。PyPI 上傳政策**不接受 direct URL 參照**
（`git+...` 的 dependency specifier），上傳會被 PyPI 拒絕；`twine check` 雖不會在上傳前
直接擋下，但 server 端會拒絕。因此現階段不可能上 PyPI。

### 5.3 硬性禁止

**絕對不可**為了能發 PyPI 而把 plane dependencies 偷偷改成浮動 branch/tag 或省略 SHA pin。
`pyproject.toml` 的 `git+SHA` pin 是 immutable dependency 的來源，改動會破壞可重現性，
違反 issue #280 明文禁止。若未來要上 registry，應另開 cross-repo child issues 處理
hippo/cortex 的 package publication，不在本 umbrella 內隱性擴張。

### 5.4 升級路徑

當 plane repos 各自具備 registry publication（Trusted Publishing 或等價短期憑證）後，
本 repo 可將 `git+SHA` 改為 version pin + hash，並重新評估 PyPI 發布；該決策另開 issue，
不在本階段執行。

## 6. Release recovery / 撤回（與 README 操作面對應）

使用者端的版本回滾：

1. 確認目前安裝版本：`pip show paulshaclaw` 或 `python -c "import paulshaclaw; print(paulshaclaw.__version__)"`（待 `__version__` 補上後；目前以 `pip show` 為準）。
2. 從上一穩定版本的 GitHub Release 下載 wheel。
3. 在目標 venv `pip install --force-reinstall <舊版 wheel>`。
4. runtime 狀態（`~/.agents/`）**不隨 artifact 變動**，回滾 operator shell 不會動到 state/secret。

> 完整的 artifact-driven `install --version` / `upgrade` / `rollback` 屬於 E 節，本次不實作。

## 7. 相關檔案

| 角色 | 檔案 |
|---|---|
| 一致性 gate | `scripts/check-release-consistency.py` |
| 本機 dry-run | `scripts/release-artifacts.sh` |
| Release workflow | `.github/workflows/release.yml` |
| 一致性測試 | `tests/test_release_consistency.py` |
| 既有版本測試 | `tests/test_version_consistency.py` |
| 版本來源 | `VERSION`、`pyproject.toml`、`CHANGELOG.md` |