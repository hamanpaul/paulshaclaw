## Why

Claw 的缺失狀態 fallback 會把未提供的權威資料顯示成 running／done，bot 又漏掉 attention。此 change 補登 issue 337 已實作與 TDD 驗證的有界修復；GitHub review 指出原 PR 直接改 canonical spec，故以 delta 保留規格演進紀錄，不宣稱先前已完成此步驟。

## What Changes

- 保留未知、失敗與 archived／live 差異，投影上游決策資料。
- 空 tick record 不宣稱完成；完整狀態摘要超過 Telegram 限制時分段保留純文字。
- 沿用既有 35 個正反例與 installed-runtime／真實 snapshot 證據，不新增平台責任。

## Impact

- 規格：manager-control-plane、stage11-operator-cockpit。
- 程式：cockpit app/models/jobs_panel、core daemon、bot listener。
- 驗證：tests/test_truthful_status_projection.py、既有全套 preflight。
- 候選版本尚未部署；live smoke 的版本界線與原始數值保存在 docs/research/2026-10-15-thin-shell-acceptance.md。
