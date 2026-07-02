## 1. generic 標題判定與非刪除級池排除（noise.py）

- [ ] 1.1 在 `paulshaclaw/memory/tests/test_noise.py` 追加 failing tests：`is_generic_title` 的命中/不命中矩陣（exact + prefix + 正規化；`overview-of-uart-pinmux` 等僅包含者不命中）、`pool_exclude_reason` 對 `atom_title`/`title` generic 回 `generic-title`、`session_title` generic 不觸發。
- [ ] 1.2 在 `paulshaclaw/memory/noise.py` **檔尾**新增獨立區塊：`_GENERIC_EXACT_TITLES` frozenset、`_GENERIC_TITLE_PREFIX` regex、`is_generic_title(title)`；`pool_exclude_reason` 於 `return None` 前插入單一 generic-title 分支（與 #177 diff 隔離）。
- [ ] 1.3 `PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_noise.py -q` 綠。

## 2. 檢索 index 排除整合驗證（test-only，search.py 不改）

- [ ] 2.1 在 `paulshaclaw/memory/tests/test_moc_search.py` 追加 failing test：knowledge 含 generic 標題 slice 與具體標題 slice，`build_index` 後檢索僅命中具體者，generic 檔仍存在於磁碟（非刪除級）。
- [ ] 2.2 確認既有 `build_index` 的 `pool_exclude_reason` 呼叫點（`moc/search.py:71`）使 Task 1 規則自動生效；`test_moc_search.py` 全綠。

## 3. session 內去重 + 摘要行資訊量（hooks/_shortlist_common.py）

- [ ] 3.1 在 `paulshaclaw/memory/tests/test_shortlist_common.py` 追加 failing tests：同 session 重複 prompt 次佳補位、候選枯竭不注入不記錄、新 session 不受影響、映射損毀 fail-open、`_summary` 跳過 title echo 行/全 echo 回空/首行非 echo 行為不變。
- [ ] 3.2 實作：`SHORTLIST_FETCH_K=12` 過取、`_offered_map_path` / `_load_offered_ids` helper、`build_shortlist_and_record` 過濾已 offer sl_id 後取前 K、`_record_offered` 改用 `_offered_map_path`、`_summary(path, title)` 正規化跳過 title echo。
- [ ] 3.3 `PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_shortlist_common.py -q` 綠（含既有案例無回歸）。

## 4. retitle 掃描條件擴到 generic 標題（retitle.py）

- [ ] 4.1 在 `paulshaclaw/memory/tests/test_retitle.py` 追加 failing tests：generic 標題 slice 被列為候選並可 retitle；具體標題 slice 不被掃入。
- [ ] 4.2 實作：`retitle.py` import `is_generic_title`，`_is_untitled` 追加 generic 判定；模組 docstring 補一行 #178 擴充說明。
- [ ] 4.3 `PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_retitle.py -q` 綠。

## 5. 回歸與收尾

- [ ] 5.1 全套件：`cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q` 全綠（CI 等效：`python -m pytest tests/ paulshaclaw/memory/tests/ -q`）。
- [ ] 5.2 確認未動 boundary 外檔案（`moc/search.py`、`cli.py`、`.github/workflows/**` 皆零 diff）。
- [ ] 5.3 依 plan Delivery 段開 PR（`Closes #178`、zh-TW、無未勾 checkbox），不 merge。
