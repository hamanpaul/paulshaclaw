---
type: change
scope: deploy
---

### Changed

- 模板打包 e2e 測試不再對 installer 硬編碼 `--version 0.2.7`，改讓乾淨 venv 內的 `detect_installed_version()` 自動偵測並斷言 install record 的版本等於 checkout 的 `VERSION`，補上 checkout 之外靠 `importlib.metadata` 取版本這條路徑的覆蓋。
