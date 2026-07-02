## 1. rekey 遷移模組

- [x] 1.1 新增 failing tests `paulshaclaw/memory/tests/test_rekey.py`：dry-run 產 manifest 不動檔；apply 搬檔＋改 frontmatter＋run_moc 重建；conflict fail-safe（source 不 stamp）；他 project 不受影響；不安全 slug raise `RekeyError`；apply 收尾清空的舊 key 目錄與孤兒 moc。
- [x] 1.2 實作 `paulshaclaw/memory/rekey.py`：`rekey_project(memory_root, *, old_key, new_slug, now, apply) -> dict`，仿 `retitle.py` 的 manifest／dry-run／apply／run_moc 模式。

## 2. rekey CLI 子命令

- [x] 2.1 新增 failing CLI tests（`test_rekey.py` 內 `RekeyCliTests`）：`memory knowledge rekey --from <old> --to <slug> --apply` 走通；`--to` 含 `/` → exit code 2。
- [x] 2.2 `paulshaclaw/memory/cli.py`：`knowledge` subparser 下加 `rekey`（`--from` dest=`from_key`、`--to` dest=`to_slug`、`--now`、互斥 `--dry-run`/`--apply`）＋ `_rekey` handler（捕 `RekeyError` → stderr ＋ return 2）。

## 3. prune-noise 固定清單模式

- [x] 3.1 擴充 failing tests `paulshaclaw/memory/tests/test_prune_noise.py`（`PruneListedTests`）：listed apply 只刪清單內（未列清單的 noise 保留）；dry-run 不刪；清單含不存在路徑 → rc 2 且整批不刪；清單含 knowledge root 外檔案 → rc 2；`--paths` 與 `--project` 併用 → rc 2。
- [x] 3.2 `paulshaclaw/memory/cli.py`：`prune-noise` 加 `--paths` 參數＋ `_prune_listed(root, paths_file, *, now, apply)`（fail-closed 驗證、manifest before unlink、reason=`listed`、apply 後 `build_mocs`）。

## 4. janitor lint 規則

- [ ] 4.1 擴充 failing tests `paulshaclaw/memory/tests/test_janitor_rules.py`（`LintRuleTests` ＋ `LintFieldExtractionTests`）：untitled 命中、raw-remote key 命中、乾淨 record 零 findings、單筆雙中、deterministic 排序；`iter_records` 抽取 `title`/`project`。
- [ ] 4.2 `janitor/record_source.py`：`KnowledgeRecord` 尾端加 `title: str = ""`、`project: str = ""`，`_build_record` 抽取；`janitor/rules.py`：新增純函式 `plan_lint(records) -> list[dict]` 與 rule 常數。

## 5. janitor scanner 接線

- [ ] 5.1 擴充 failing tests `paulshaclaw/memory/tests/test_janitor_scanner.py`（`ScannerLintTests`）：`summary["lint"]` counts、`lint:` warnings、乾淨樹零 counts、lint 不動檔案不寫 lifecycle。
- [ ] 5.2 `janitor/scanner.py`：`run_scan` 呼叫 `rules.plan_lint`，counts 進 `summary["lint"]`、findings 逐筆 append warnings。

## 6. 回歸驗證與收尾

- [ ] 6.1 全套測試綠：`cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q`（CI 等效 `python -m pytest tests/ paulshaclaw/memory/tests/ -q`）。
- [ ] 6.2 勾選本檔全部 checkbox 並在下方補 Verification Summary（測試輸出摘要）。

## Verification Summary

（實作完成後填：focused pytest 輸出、全套結果、rekey/prune dry-run 示範輸出。）
