---
type: feat
---
新增 `paulshaclaw` console script 作為**正式啟動路徑**（#288）：安裝 release wheel 後即可在全新機器啟動 operator shell，行為與 `scripts/start.sh` 對等（cost／telegram／dream／cortex fallback／cockpit），執行期鎖定自身安裝版本、不讀取 repo 工作樹。
- systemd unit 模板 `ExecStart` 改為 `__PYTHON__ -m paulshaclaw.launcher.services <role>`（render 時代入安裝 venv 直譯器），release artifact 不再依賴 repo `scripts/`。
- 兩條啟動路徑共用 `paulshaclaw-start.lock` 互斥、**後起的為主**：新啟動方自動停掉既有 operator shell（process 持有者送 SIGTERM；systemd unit 持有者走 `systemctl --user stop`），停不掉即 fail-closed 明確報告；接管邊界僅及操作面自身行程與 units，不波及 cortex／hippo 常駐服務。
- `scripts/start.sh` 維持開發驗證路徑定位，偵測到既有實例由「拒絕啟動」改為「接管」。
- `paulshaclaw.__version__` 補上（`importlib.metadata`，未安裝時 `0+unknown`），release-contract §6 的回滾步驟自此可直接查版本（#280 審計缺口）。
