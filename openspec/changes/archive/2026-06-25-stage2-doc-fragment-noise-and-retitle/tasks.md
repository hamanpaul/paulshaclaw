## 1. doc-fragment classifier + corpus（#147 判準）

- [x] 1.1 RED：`test_noise.py` 加——提供涵蓋 CLAUDE.md/AGENTS.md 的 `doc_corpus` 時，`## 6. 自主維護規則…` 編號碎片與 `## 動工前` 段落碎片判 `doc-fragment`；真知識編號小節（內容未命中語料）判非 noise；未傳 `doc_corpus` 時行為與既有一致。watch fail。
- [x] 1.2 RED：`test_instruction_corpus.py`——`build_corpus(texts)` 正確抽 heading 集合與內容行集合（normalized）；`discover_instruction_docs(roots)` 限深 + skip-list（含 `.copilot`/`.git`）只收 CLAUDE.md/AGENTS.md/GEMINI.md。watch fail。
- [x] 1.3 GREEN：新增 `instruction_corpus.py`（`DocCorpus` 用 `noise.py` 型別、`build_corpus`、`discover_instruction_docs`、`load_corpus`）；`noise.py` 加 `DocCorpus`、doc-fragment 規則（heading 命中 + ≥2 內容行命中），`classify_noise` 加 `doc_corpus` 選用參數、規則排於 structural-echo/placeholder/empty 之後。
- [x] 1.4 確認 1.1/1.2 全綠、既有 `test_noise` 無回歸。

## 2. 產生端過濾共用語料（#147 防新生）

- [x] 2.1 RED：`test_atomizer_pipeline`——傳入語料時，body 為 instruction 逐字章節的 slice 經 promote 後不入 knowledge、`noise_dropped` 計數正確；未傳語料時行為不變（既有測試）。watch fail。
- [x] 2.2 GREEN：`atomizer/pipeline.py::_promote_pass` 加 `doc_corpus=None` 參數、傳入 `classify_noise`；`atomizer/cli.py`/run 入口組裝語料（`--instruction-root` 選用，預設 curated 探測）並下傳。
- [x] 2.3 確認 2.1 全綠，且既有 atomizer/pipeline/cli 測試無回歸。

## 3. 回溯 prune 接語料（#147 清既有）

- [x] 3.1 RED：`test_prune_noise`——提供語料時 doc-fragment 被列入/刪除、真知識保留、manifest reason `doc-fragment`；不提供語料時與既有一致。watch fail。
- [x] 3.2 GREEN：`cli.py::_prune_noise` 組裝語料（`--instruction-root` 選用 + curated 預設）傳入 `classify_noise`；prune subparser 加 `--instruction-root`（repeatable）。
- [x] 3.3 確認 3.1 全綠。

## 4. slugify 保留 CJK（#151 根因）

- [x] 4.1 RED：`test_moc_naming`——`slugify("動工前")` 非空且含 CJK、`slugify("CI gating note")=="ci-gating-note"`、`slugify("---")=="untitled"`。watch fail。
- [x] 4.2 GREEN：`naming.slugify` 改 `[^\w]+`（re.UNICODE）保留 CJK，空則 fallback `untitled`。
- [x] 4.3 確認 4.1 全綠、既有 naming/moc 測試無回歸（零 churn）。

## 5. retitle migration（#151 重生 + 改名）

- [x] 5.1 RED：`test_retitle`——注入式 runner 對 `untitled--<sid>.md` 真知識重生標題、檔名改為 `<slug>--<sid>.md`（slice_id/body 不變）、stamp `title`/`atom_title`、manifest 落 `runtime/ledger/retitle-<now>.jsonl`；doc-fragment 候選被 skip；runner 離線 slice skip 不失敗；`--dry-run` 不動檔。watch fail。
- [x] 5.2 GREEN：新增 `retitle.py`（`retitle_untitled(memory_root, *, now, apply, runner, doc_corpus)`）；`importer/title.py` 加 body 蒸餾 `generate_atom_title(body, *, runner)`；`cli.py` 加 `knowledge retitle-untitled`（`--memory-root`/`--now`/`--dry-run`/`--apply`/`--instruction-root`），apply 後 `run_moc` 重建。
- [x] 5.3 確認 5.1 全綠。

## 6. 驗證、回溯清理與收尾

- [x] 6.1 跑 memory 測試套件全綠（pytest），確認無回歸。
- [x] 6.2 live `prune-noise --dry-run` 核 manifest（預期 ~126：102 編號 + ~24 untitled-AGENTS），確認不誤含真知識 → `--apply` 清除 + 重建 MOC。
- [x] 6.3 live `retitle-untitled --dry-run` 核新標題（gemma4 上線）→ `--apply` 重生 + 改名 + 重建 MOC；確認 wakeup raw brief 不再含 `untitled--` / `1--`/`N-agent-managed--` target。
- [x] 6.4 requesting-code-review；修 finding 後 re-review。
- [x] 6.5 openspec archive；conventional commit；push；開 PR（Closes #147 / Closes #151）。
