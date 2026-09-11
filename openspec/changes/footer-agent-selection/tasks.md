## 1. --footer 選擇與回報

- [x] 1.1 RED：install / installed-wheel regression 覆蓋 `--footer` flag、`skipped(no-tty)`、`skipped(plan-only)`，並要求 report 含 `detected_agents` 與 `footer_selection`
- [x] 1.2 GREEN：實作 `--footer` 解析與決策矩陣，讓 plan-only、無 TTY 與顯式旗標都回報正確 footer selection
- [x] 1.3 GREEN：補上 conftest 的 deploy 測試模組前綴，讓 footer selection 回歸測試受家目錄隔離防線保護
