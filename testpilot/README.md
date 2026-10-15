# 安裝回歸 TestPilot plugin

本子專案只驗證部署契約，不加入 operator shell wheel 或 runtime dependencies。
它沿用既有 Cortex 候選並補齊歷史輸入、逐步結果、Docker CI 與精確 oracle。

目前 README 已經補上 `git` 前置；本測試固定 **v0.2.7 歷史 README**
（commit `ddc4ab74f77e680ecb621a2ba511af5e4041828a`）與當時的 release wheel，
保留已證實的缺 git 故障。原始安裝報告仍為 **FAIL**；CI 另外檢查它是否完整
符合歷史故障，任何網路、checksum、timeout、缺步驟、控制組或清理失敗都擋住 CI。

| Case | 環境與驗收 |
|---|---|
| TC-1 | Ubuntu 24.04，歷史 README 的 python3/venv 基線，無 git；S1-4 exit 1 且 stderr 含缺 git、S1-6 exit 127，原始 FAIL |
| TC-1c | Ubuntu 24.04，無 git、`--no-deps`；entry points、精確版本與 help PASS，只證明入口完整 |
| TC-1g | Ubuntu 22.04／24.04 各跑一次，明確加入 git；全部安裝、版本、status、help、psc usage gates PASS |
| TC-1p | Ubuntu 24.04，基線加 pipx、無 git；install exit 1 且缺 git，新 login shell 命令 exit 127，原始 FAIL |

TC-1p 使用獨立 HOME；fresh login shell 明確加入該 HOME 的 `.local/bin`，
隔離 PATH 缺口，避免把沒有重開 shell 當成缺 git。歷史 README 未要求 ensurepath，
本案也不藉它修改安裝流程。每個測試命令獨立 `docker exec`，不透過 pipe 取 exit。
安裝失敗仍收後續診斷；container run／exec／rm 都有 timeout，只清理本次建立的 ID。

TestPilot Core 固定 **0.3.7 / API 1.2**，plugin 宣告相容的 API 1.1，
只引用公開 `testpilot.api`。使用已驗證 SHA 的官方 wheel 安裝，沒有替代 API fallback。
`DockerTransport` 實作 `TransportBase`；cases 透過 `PluginBase` 發現，custom runner
避免一般 runner 的 fail-fast 與 retry 改變回歸觀測。單元測試使用真實 Core `StubTransport`。

## 本機 gates 與安裝 discovery

從 repo root 執行：

```bash
./testpilot/scripts/preflight.sh
```

腳本在 `testpilot/.venv` 建獨立環境，從 GitHub 安裝 checksum 固定的 core wheel，
安裝 plugin wheel 後離開 checkout 執行 `list-plugins`、`list-cases` 和 API 檢查，
再執行 plugin pytest。此 gate 已加入 `.project-policy.yml`，不改 operator venv。

## Docker 歷史矩陣

需要可用 Docker daemon，以及 Ubuntu apt、PyPI、GitHub 網路。所有 wheel／checksum
預放同一個專用目錄；歷史 wheel SHA 必須是
`cc2e0771ba09030b23280ba1ab19a898ce147f8ef4e942a226bf10ddcd2be13f`。
Ubuntu 22.04／24.04 image digest 均固定於 YAML，必要時 Docker 會拉取。

```bash
gh release download v0.2.7 --repo hamanpaul/paulshaclaw --dir /tmp/deploy-artifacts \
  --pattern 'paulshaclaw-0.2.7-py3-none-any.whl' --pattern checksums-sha256.txt
testpilot/.venv/bin/python testpilot/scripts/run_historical.py \
  --artifact-dir /tmp/deploy-artifacts --report-dir /tmp/deploy-reports
```

成功最後印 `PASS: historical RED and GREEN controls verified; raw report retains FAIL`。
報告包含五個 container 的 ID、image digest、README SHA/commit、實際套件、artifact SHA、
每步 command/exit/stdout/stderr/timeout，以及 cleanup 結果；Markdown 可點到完整 JSON。
CI 的 `Deploy TestPilot` job 實跑同一矩陣並上傳 `deploy-regression-reports` artifact。

也可複製 `paulshaclaw_deploy/testbed.yaml.example` 設定絕對 artifact 路徑後，直接用 Core CLI：

```bash
TESTPILOT_TESTBED=/tmp/testbed.yaml TESTPILOT_REPORT_DIR=/tmp/deploy-reports \
  testpilot/.venv/bin/testpilot run paulshaclaw_deploy --case tc1-readme-a-venv-install
```

Core CLI 顯示原始 FAIL；完整矩陣才可交給 `scripts/check_expected_red_oracle.py <report.json>`
判定預期歷史 RED。README 的解析只接受 §A 的明確 `apt install` 套件宣告；沒有宣告時
保留 python3/venv 基線，且不執行 Markdown。candidate artifact 有獨立欄位及唯讀 mount，
不得覆寫歷史 wheel；這次交付只驗歷史四案，不宣稱驗證 candidate release。
