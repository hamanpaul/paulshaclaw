# Change: 獨立部署安裝回歸 TestPilot plugin

## Why

歷史 v0.2.7 README 未要求 git，wheel 的 VCS dependency 在乾淨機器安裝失敗。
目前 README 已修，但缺少可重跑的 repo-owned regression case 與完整報告。

## What Changes

- 新增獨立 testpilot 子專案與四個 YAML cases，固定歷史 README、wheel SHA 與 Ubuntu digest。
- Docker 每步保存真實 exit/stdout/stderr，歷史 RED 與 GREEN 控制組分開驗收。
- preflight 驗證安裝 discovery 與 stub tests；CI 實跑五容器矩陣並保存原始證據。

## Impact

- Affected specs: deploy-testpilot
- Affected code: testpilot/、.github/workflows/deploy-testpilot.yml、.project-policy.yml
- 不改 operator shell runtime dependencies、production installer 或目前 README 安裝契約。
