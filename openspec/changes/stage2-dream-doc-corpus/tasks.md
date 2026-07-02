## 1. dream run `--instruction-root` 佈線（CLI parser + dream/cli）

- [x] 1.1 RED：新增 `paulshaclaw/memory/tests/test_dream_cli_instruction_root.py`——(a) plumbing：patch `dream.cli.atomizer_pipeline.run` 截取 kwargs，帶 `--instruction-root <doc>` 時 `doc_corpus` 為非空 `DocCorpus` 且含預期 heading；不帶時 `doc_corpus` 為 falsy（行為契約）；(b) e2e（identity promoter、`_isolated_home`）：帶旗標時 doc-fragment session 被 drop（`passes.atomize.noise_dropped==1`、knowledge 無該內容、真知識 session 照常寫入）；不帶旗標時 echo 照舊寫入且 `noise_dropped==0`（回歸鎖，預期先綠）。跑 `PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_dream_cli_instruction_root.py -q` 確認帶旗標的測試以 argparse `unrecognized arguments` 失敗。
- [x] 1.2 GREEN：`paulshaclaw/memory/cli.py` dream run parser（cli.py:81-89 區塊內、`set_defaults` 前）加 repeatable `--instruction-root`（`action="append", default=None`，help 沿 atomize 措辭）；**diff 限縮在 dream run parser 區塊**（#177 同檔動其他區塊）。
- [x] 1.3 GREEN：`paulshaclaw/memory/dream/cli.py` 頂部 import `corpus_for_roots`，`_run` 內以 `getattr(args, "instruction_root", None)` 組 `doc_corpus`，`atomize_fn` 對 `atomizer_pipeline.run` 傳 `doc_corpus=doc_corpus`。測試全綠後 commit。

## 2. start.sh 生產 dream loop 傳語料 roots

- [x] 2.1 RED：新增 `paulshaclaw/memory/tests/test_start_sh_dream_flags.py`——讀 `scripts/start.sh`，擷取 `memory dream run` 命令段（至 `>>"$dream_log"` 止），assert 含 `--promoter llm`、`--instruction-root` 恰 9 個、且含 `$HOME/.claude/CLAUDE.md`、`$HOME/CLAUDE.md`、`$HOME/prj_pri`、`$HOME/prj_arc` 四個關鍵 root。確認 FAIL。
- [x] 2.2 GREEN：`scripts/start.sh` dream run 命令（現行 :195-196）補 9 行 `--instruction-root`（= `instruction_corpus.default_roots()` 集合），其餘行不動。`bash -n scripts/start.sh` 通過、guard test 綠後 commit。

## 3. 回歸與收尾

- [x] 3.1 本機全套：`cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q` 全綠（既有 dream/atomizer 測試零回歸）。
- [ ] 3.2 CI 等效：`python -m pytest tests/ paulshaclaw/memory/tests/ -q` 全綠。
- [x] 3.3 依 Delivery 段開 PR（branch `feature/176-stage2-dream-doc-corpus`、body 含 `Closes #176`、不 merge）；驗證摘要記錄於本檔底部。

## Verification Summary

- RED：`cd /home/paul_chen/prj_pri/psc-wt-176 && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_dream_cli_instruction_root.py -q` → `2 failed, 2 passed`；兩個 failing tests 皆因 `psc: error: unrecognized arguments: --instruction-root ...`。
- GREEN（Task 1）：`cd /home/paul_chen/prj_pri/psc-wt-176 && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_dream_cli_instruction_root.py paulshaclaw/memory/tests/test_dream_cli.py paulshaclaw/memory/tests/test_dream_e2e.py paulshaclaw/memory/tests/test_dream_cli_moc_warnings.py -q` → `10 passed in 0.47s`。
- RED：`cd /home/paul_chen/prj_pri/psc-wt-176 && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_start_sh_dream_flags.py -q` → `1 failed, 1 passed`；failing test 為 `cmd.count("--instruction-root") == 9`（實際 0）。
- GREEN（Task 2）：`cd /home/paul_chen/prj_pri/psc-wt-176 && bash -n scripts/start.sh && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_start_sh_dream_flags.py -q` → `2 passed in 0.03s`。
- 全套 memory tests：`cd /home/paul_chen/prj_pri/psc-wt-176 && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q` → `775 passed, 1 skipped, 87 subtests passed in 26.80s`。
- CI 等效：`cd /home/paul_chen/prj_pri/psc-wt-176 && python -m pytest tests/ paulshaclaw/memory/tests/ -q` → `2 failed, 1457 passed, 15 skipped, 112 subtests passed in 107.64s`；失敗位於 `tests/test_stage11_operator_cockpit.py`，超出本 change boundary。
- PR：`https://github.com/hamanpaul/paulshaclaw/pull/181`
