# Release Contract 與 Distribution Strategy

> 本文件定義 `paulshaclaw` 正式版本發布的契約、前置 gate、失敗與重跑規則，
> 並裁決第一階段的 distribution authority。涵蓋 issue #280 的 A（release contract）
> 與 D（distribution strategy）。
>
> E（artifact-driven deployment）依序須在 artifact 交付邊界建立後再做，不在本文範圍。
>
> **補充（#280 E 節完成後）**：E 節實作見 §8「Artifact-driven deployment」。

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

1. 確認目前安裝版本：`pip show paulshaclaw` 或 `python -c "from paulshaclaw import launcher; print(launcher.__version__)"`（`launcher.__version__` 已於 #288 提供，來源為 `importlib.metadata`；未安裝的原始碼樹直跑會回 `0+unknown`）。
2. 從上一穩定版本的 GitHub Release 下載 wheel。
3. 在目標 venv `pip install --force-reinstall <舊版 wheel>`。
4. runtime 狀態（`~/.agents/`）**不隨 artifact 變動**，回滾 operator shell 不會動到 state/secret。

> 完整的 artifact-driven `install --version` / `upgrade` / `rollback` 屬於 E 節，本次不實作。
>
> **E 節已完成**：`install` / `upgrade` / `uninstall` / `rollback` / `status` 實作於
> `paulshaclaw/deploy/`，詳見 §8。

## 7. 相關檔案

| 角色 | 檔案 |
|---|---|
| 一致性 gate | `scripts/check-release-consistency.py` |
| 本機 dry-run | `scripts/release-artifacts.sh` |
| Release workflow | `.github/workflows/release.yml` |
| 一致性測試 | `tests/test_release_consistency.py` |
| 既有版本測試 | `tests/test_version_consistency.py` |
| 版本來源 | `VERSION`、`pyproject.toml`、`CHANGELOG.md` |

## 8. Artifact-driven deployment（E）

> 實作：`paulshaclaw/deploy/`（`installer.py` / `__main__.py`）。
> 把 immutable artifact 套用到 host 的那一半；release artifact 的交付邊界由 §1~§5 定義。

### 8.1 安裝來源記錄（E1）

`install` / `upgrade` 可指定版本與 artifact 來源：

```
python -m paulshaclaw.deploy install --apply --verify \
  --instance <name> --root-dir <dir> \
  --version 0.1.0 --artifact <path-or-url> --artifact-sha256 <hex>
```

- `--version`：記錄套用的正式版本（SemVer）。
- `--artifact`：本地路徑或 URL。本地檔案會計算 SHA-256 並記錄；URL 僅記錄來源字串
  （本階段不下載驗證，屬非目標）。
- `--artifact-sha256`：期望 checksum；指定後與實際計算不符即 **fail-closed**（exit 2）。
- 指定本地 artifact 但檔案不存在亦 fail-closed。
- **只給 `--artifact-sha256` 而不給 `--artifact` 同樣 fail-closed**：沒有 artifact 可算，
  記下來的 checksum 會讓 operator 誤以為驗證過。
- report / record 的 `verified` 欄位誠實標示該 sha256 是否真的算過：只有本地檔案實算
  才是 `true`；URL 來源（本階段不下載）與未指定 artifact 皆為 `false`。

安裝紀錄寫入 `~/.agents/state/config/<instance>.install-record.json`（state plane，
不寫進 repo、不寫進 secret plane），內容含 `version`、`artifact_source`、
`artifact_sha256`、`applied_at`、`command`。

查詢入口：

```
python -m paulshaclaw.deploy status --instance <name> --root-dir <dir>
```

回傳目前安裝的正式版本、來源與 checksum；無紀錄時印 `{}`。

### 8.2 machine-readable verification report（E2）

`install` / `upgrade` / `uninstall` / `rollback` 的實際執行路徑（`--apply`）皆輸出
結構化 JSON report，沿用 `run_install()` 既有形狀擴充，至少含：

- `command`、`instance_name`、`root_dir`、`status`。
- 套用 / 跳過的檔案（`applied_files` / `skipped_existing` / `removed_core_files`）。
- `artifact`（來源與 checksum）、`verification`（env catalog + systemd unit 驗證結果）。
- `rollback_triggered`（upgrade 失敗自動 rollback 時為 `true`）與 `rollback` 還原摘要。
- `checkpoint`（snapshot 位置）、`snapshot`（備份清單）。

### 8.3 upgrade 實際執行（E3）

```
python -m paulshaclaw.deploy upgrade --apply --verify \
  --instance <name> --root-dir <dir> [--version X.Y.Z] [--artifact ...]
```

依 planner 已宣告的 steps 落實：

1. `snapshot-existing-core`：將現有 core plane（systemd unit + runtime env）複製到
   `~/.agents/deploy-checkpoints/<instance>/upgrade-<timestamp>/`。
2. `render-core-templates`：以 `apply_install_plan()` 重新套用模板——
   **沿用 `_asset_is_overwritable()` 的 create-only 規則**：只有 `core/systemd/**`
   被覆寫，core runtime env / state / secret 存在即跳過。
3. `preserve-state-plane` / `preserve-secret-plane`：由 create-only 規則保證，不另刪改。
4. `restart-service-unit`：對每個 `verify_units` 跑 `systemctl --user restart`（systemd
   不可用時 skip）。**任一 unit 重啟失敗即 fail-closed**：拋錯 → 自動 rollback →
   report `status: failed` + exit 1。只記錄 returncode 而回報成功會讓 operator
   誤以為升級完成，但服務其實是停的。
5. `verify-systemd-user-units`：沿用 `verify_install_plan()`。

### 8.4 rollback（E4）

- checkpoint 存放於 `~/.agents/deploy-checkpoints/<instance>/<command>-<timestamp>/`，
  含 `manifest.json` 與鏡射的 core 檔案；可清理、不污染 repo。timestamp 到微秒且
  撞名時補遞增序號——秒級目錄會讓同一秒內的兩次 upgrade 共用 checkpoint，
  後者的 snapshot 覆寫前者，rollback 就會還原到已被改過的內容。
- `restore-core-from-checkpoint` 把 core 檔案逐檔還原到升級前內容。
- **rollback 刻意繞過 `_asset_is_overwritable()` 的 create-only 判準**（#285）：
  create-only 防的是「用模板 placeholder 覆寫使用者的真實設定值」；而 rollback
  寫回的是**使用者自己在 checkpoint 當下的真實內容**，還原 runtime env 正是
  rollback 的目的。故 `restore_core_from_checkpoint()` 對 `core/systemd` 與
  `core/runtime` 一律 `shutil.copy2()` 覆寫，不經 create-only 判準。此刻意例外
  由 `test_rollback_restores_runtime_env_from_checkpoint` 測試守住——日後在此路徑
  加判準會被測試擋下。
- **`rollback` 命令可指定較舊的 checkpoint**：`--from-command` 選最新或指定
  command 的 checkpoint，可能早於當前狀態。那會把當前 runtime env 蓋回舊內容——
  這是 operator 明確要求的行為（明確 rollback 即明確接受還原到該時間點），
  但請留意還原後的內容可能比當前版本舊。
- **upgrade 執行途中失敗自動 rollback**：`run_upgrade()` 在套用階段拋例外時（含
  unit 重啟失敗），自動從當次 checkpoint 還原 core，report 標記
  `rollback_triggered: true` 並回 exit 1。
- **`--verify` 階段失敗不自動 rollback**：此時 core 已套用完成且服務已重啟，
  verify 回報的是「檢查沒過」而非「套用失敗」。report 標 `status: failed` + exit 1，
  是否還原交由 operator 以下方的 rollback 命令明確決定。
- 明確 rollback 入口：

  ```
  python -m paulshaclaw.deploy rollback --instance <name> --root-dir <dir> \
    [--from-command upgrade]
  ```

  從最新（或指定 command）的 checkpoint 還原 core plane。

### 8.5 uninstall 實際執行（E5）

```
python -m paulshaclaw.deploy uninstall --apply \
  --instance <name> --root-dir <dir> [--purge-state] [--purge-secret]
```

依 planner steps 落實：

1. `snapshot-existing-core`：同 upgrade，先建立 checkpoint 供 rollback。
2. `disable-service-unit` / `stop`：對 `verify_units` 跑 `systemctl --user disable/stop`。
3. `remove-core-plane`：移除 systemd unit 與 runtime env。
4. `preserve-state-plane` / `preserve-secret-plane`：**預設保留** state 與 secret。
   只有 operator 明確 `--purge-state` / `--purge-secret` 才清除，且預設值為保留。

### 8.6 三平面邊界與非目標

- operator shell **不**重新擁有 Hippo / Cortex 的 service lifecycle authority：
  `deploy` 只操作本 repo 的 core/systemd unit 與 runtime env，不 enable/disable/restart
  hippo 或 cortex 的 unit，不碰 `scripts/start.sh`、`scripts/cutover-to-planes.sh`。
- create-only 規則不因升級放寬（#219 對抗審查結論）。
- 不實作自動部署到遠端主機、不在部署流程裡管理或遷移使用者 secret 內容。
- 所有 `systemctl` / `systemd-analyze` 呼叫走既有 `_run_command()`；測試以 fake bin
  + PATH 注入 + 假 HOME 隔離，不碰真實 systemd。

### 8.7 家目錄隔離防線（#285）

deploy 的家目錄根 `paths.home_root()` 預設回 `Path.home()`，但優先吃
`PSC_HOME_ROOT` 環境變數覆寫（仿 `repo_root()` 的 `PSC_REPO_ROOT` 慣例）。
CLI 的 `install` / `upgrade` / `uninstall` / `status` / `rollback` 皆接受
`--home-dir`，顯式指定時落點全部在該目錄下、不命中真實家目錄。

測試層具備**第二道防線**：`tests/conftest.py` 的 session autouse fixture 把
`PSC_HOME_ROOT` 指向 pytest 的暫存目錄，任一呼叫點漏帶隔離時 deploy 也只會寫進
tmp 而非真實 host。各 stage7 測試的 `deploy_env()` 仍顯式把 `PSC_HOME_ROOT` 設成
該測試的假 `HOME`，避免 conftest 的 tmp 與測試自己假 HOME 不一致導致斷言找不到檔案。

反例測試 `tests/test_home_isolation.py` 守住：
- `home_root()` 在 `PSC_HOME_ROOT` 設定時回傳該值；
- CLI 帶 `--home-dir` 時所有落點都在該目錄下、不在真實 `Path.home()`。

### 8.8 現場殘留產物清理（#285，僅說明、不自動執行）

若曾因隔離失效讓測試 fixture 寫進真實家目錄（例如 issue #285 現場觀察到的
`demo-agent` 部署產物），可手動清理下列路徑。**本 repo 不會自動刪除使用者的
任何檔案**——清理由 operator 決定後執行。

```
# core/runtime（每個逃逸 instance 一份 env）
rm -f ~/.agents/core/runtime/demo-agent.env \
      ~/.agents/core/runtime/demo-agent-cost.env \
      ~/.agents/core/runtime/demo-agent-telegram.env

# core/systemd user units
rm -f ~/.config/systemd/user/demo-agent-cost.service \
      ~/.config/systemd/user/demo-agent-telegram.service
systemctl --user daemon-reload

# state plane
rm -f ~/.agents/state/config/demo-agent.install-record.json \
      ~/.agents/state/config/demo-agent.state.json

# secret plane
rm -f ~/.config/paulshaclaw/demo-agent.secret.env \
      ~/.config/paulshaclaw/demo-agent.telegram.secret.env
```

清理前請先確認該 instance 確非你實際使用的部署；若有意保留的 state/secret 內容，
先備份再刪。`~/.agents/core/runtime/cortex-manager.env` 若被 `scripts/start.sh`
改寫成錯誤的 `PSC_REPO_ROOT`，以 paulsha-cortex checkout 下重新跑
`python -m paulsha_cortex.cli install service` 導正（#285 問題 B 的 start.sh 側已加
fail-closed 檢查，不會再覆寫指向別 repo 的 env）。
## 9. 啟動路徑契約（#288）

> 實作：`paulshaclaw/launcher/`（`lock.py` / `services.py` / `supervisor.py` / `cli.py`）；
> 測試：`tests/test_launcher_lock.py`、`test_launcher_services.py`、`test_launcher_cli.py`、
> `test_launcher_takeover_integration.py`。

### 9.1 兩條啟動路徑職責分離（issue #288 owner 裁決）

| 路徑 | 定位 | 來源 | 版本 |
|---|---|---|---|
| `scripts/start.sh` | **開發驗證** | repo checkout | 跟著工作樹，隨時可變 |
| `paulshaclaw`（console script） | **正式啟動** | 已安裝的 release artifact | **只 pin 該 release 的版本** |

- 兩者**不互用**：release 路徑不依賴 repo `scripts/`（systemd 模板 ExecStart 為
  `__PYTHON__ -m paulshaclaw.launcher.services <role>`，render 時代入安裝 venv 的
  直譯器）；dev 路徑不改走 artifact。
- 兩者**二擇一**：同一台機器同時間只有一套 operator shell 在跑。
- **後起的為主**：新啟動方接管（停掉）既有持有者後才啟動，而非拒絕啟動。

### 9.2 start lock 與 metadata schema

lock 檔：`paulshaclaw-start.lock`，路徑解析順序 `PSC_START_LOCK` >
`XDG_RUNTIME_DIR` > `/run/user/<uid>`（存在且可寫）> `/tmp`。

- **flock 為活性真相**：kernel flock 才代表有人活著持有；crash 殘留的 stale
  檔案會被正確判為 free。
- 檔內 metadata（單行 JSON，schema v1）只用於辨識持有者與停法：

```json
{"schema": 1, "holder": "dev|release", "pid": 123, "pgid": 123,
 "stop": {"kind": "process", "pid": 123},
 "version": "0.1.0 或 dev@<repo>", "started_at": "..."}
```

`stop.kind` 亦可為 `{"kind": "systemd", "unit": "<unit>"}`——systemd 持有者
**必須走 `systemctl --user stop`**（直接 kill 會被 `Restart=on-failure` 拉回，
造成兩套並存的假象循環）。

### 9.3 接管流程與 fail-closed 條款

1. 停操作面 units：僅 `<operator-instance>-cost.service` / `-telegram.service`
   （instance 取 `PSC_OPERATOR_INSTANCE`，預設 `paulshaclaw`；白名單建構）。
2. flock 探測：free 即直接取鎖；被持有則讀 metadata——**unreadable / corrupt
   即 fail-closed**，不盲殺。
3. 依 `stop.kind` 停現任持有者（process → SIGTERM；systemd → systemctl stop）。
4. 每 0.2s 輪詢 flock 至 timeout（預設 30s，`PSC_TAKEOVER_TIMEOUT_SECONDS`
   覆寫）；**逾時即 fail-closed** 並回報持有者 metadata，不升級為 KILL。

**三平面邊界**：接管僅停操作面自己的行程與 units；cortex / hippo 由 systemd
常駐的服務不受影響（stop 目標含 `manager` / `monitor` 字樣或 `cortex-` /
`hippo-` 前綴一律 fail-closed 拒絕）。

### 9.4 B 節裁決紀錄：service 交付選方案 2（指令自承 loop）

理由（對照 issue #288 B 節兩案）：

1. `scripts/service-*.sh` 與 repo 佈局深耦合（自身位置推 REPO、source
   `start.sh --source-only`、以 repo 路徑注入模組搜尋路徑），納入 package data
   仍須整段重寫。
2. wheel 對 package data 的執行位元與安裝路徑無契約保證，shell script 交付
   在 wheel 語境是二等公民。
3. Python loop（`launcher/services.py`）可單元測試，ready-gate / backoff /
   偵測順序皆有測試釘住。
4. `__PYTHON__` render（`installer.render_template`，預設 `sys.executable`）讓
   unit ExecStart 直指安裝 venv，版本 pin 自動閉合。

### 9.5 release 路徑與 dev 路徑的明確差異裁決

- release supervisor **不跑 `cortex install service`**：該動作綁 repo checkout
  （`--repo-root`），屬治理面部署。release 路徑只做偵測（`manager.lock` flock
  探測＋monitor pgrep），缺者以本 venv 起 local fallback。
- `paulshaclaw` 執行期**不讀 repo 工作樹**：全程 `sys.executable`＋安裝 venv
  內套件（`tests/test_launcher_cli.py` 以原始碼掃描釘住）。
- dev 路徑 `scripts/start.sh`＋`service-*.sh` 定位不變；start.sh 偵測到既有
  實例由「拒絕啟動」改為呼叫共用模組 `-m paulshaclaw.launcher.lock takeover`
  接管後重取鎖。
