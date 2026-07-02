# Stage 2 dream 路徑接上 doc-fragment 語料（#176）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修復 issue #176——dream 生產路徑的 doc-fragment 噪音規則永遠 inert（`dream/cli.py` 未傳 `doc_corpus`、`memory dream run` 無 `--instruction-root`、`noise.py:143-144` 空語料直接 return False，`noise_dropped` 恆 0 成假遙測）。給 `memory dream run` 加 opt-in `--instruction-root`（沿 `memory atomize` 既有慣例），dream atomize pass 下傳 `doc_corpus`，`scripts/start.sh` 生產 dream loop 補語料 roots。**不傳旗標時行為必須與現行完全一致（行為契約，測試鎖定）。**

**Architecture:** 零新判定邏輯——`classify_noise` 的 doc-fragment 規則（`paulshaclaw/memory/noise.py:134-157`）、`corpus_for_roots`（`paulshaclaw/memory/instruction_corpus.py:107-113`，falsy roots → 空語料 → 規則惰性）、`atomizer_pipeline.run` 的 `doc_corpus` 參數（`paulshaclaw/memory/atomizer/pipeline.py:504`）全部既有。本 change 只做三段佈線：CLI parser（`paulshaclaw/memory/cli.py:81-89` dream run 區塊）→ dream cli（`paulshaclaw/memory/dream/cli.py:37-45` 的 `atomize_fn`）→ 生產呼叫端（`scripts/start.sh:195-196`）。start.sh 傳的 roots 比照 `instruction_corpus.default_roots()`（`instruction_corpus.py:74-87`），與 #156 index 端（`moc/runner.py:21` broad corpus pool-exclude）同一組來源。

**Tech Stack:** Python 3.12、pytest（本機 `~/.local/bin/pytest`；**勿用 `unittest discover`——會靜默跳過 pytest 風格測試**）、argparse、bash（start.sh）。

**Spec:** OpenSpec change `openspec/changes/stage2-dream-doc-corpus/`（proposal / design / specs / tasks）｜issue #176

---

## Boundary（可改檔案白名單）

只允許改動下列檔案，超出即停：

- `paulshaclaw/memory/cli.py` — **僅** dream run parser 區塊（現行 :81-89）；不動 import、不動其他 subparser。注意：#177 也會動本檔（新 subcommand），diff 限縮以降低 merge 衝突。
- `paulshaclaw/memory/dream/cli.py` — import 一行 + `_run` 內佈線。
- `scripts/start.sh` — **僅** `start_dream_loop()` 內的 `memory dream run` 命令（現行 :195-196）。
- `paulshaclaw/memory/tests/test_dream_cli_instruction_root.py` — 新增。
- `paulshaclaw/memory/tests/test_start_sh_dream_flags.py` — 新增。
- `openspec/changes/stage2-dream-doc-corpus/tasks.md` — 只勾 checkbox 與填 Verification Summary。

明確**不可**動：`paulshaclaw/memory/noise.py`、`paulshaclaw/memory/instruction_corpus.py`、`paulshaclaw/memory/atomizer/**`、`paulshaclaw/memory/dream/scripts/**`、`paulshaclaw/memory/dream/systemd/**`、`.github/workflows/**`、`.paul-project.yml`、任何 `policy_version`。

---

## File Structure

- Create: `paulshaclaw/memory/tests/test_dream_cli_instruction_root.py` — plumbing 單測 ×2 + e2e ×2。
- Create: `paulshaclaw/memory/tests/test_start_sh_dream_flags.py` — start.sh dream 命令旗標 guard。
- Modify: `paulshaclaw/memory/cli.py` — dream run parser 加 `--instruction-root`（repeatable）。
- Modify: `paulshaclaw/memory/dream/cli.py` — `corpus_for_roots` 組 `doc_corpus` 傳入 `atomizer_pipeline.run`。
- Modify: `scripts/start.sh` — dream run 命令補 9 個 `--instruction-root`。

測試指令一律：
`cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q`（全套）；單檔則把路徑換成該測試檔。CI 等效：`python -m pytest tests/ paulshaclaw/memory/tests/ -q`。

---

## 背景（worker 必讀的行為契約）

1. `corpus_for_roots(None)` / `corpus_for_roots([])` 回傳空 `DocCorpus`（`bool()` 為 False）→ `classify_noise` 的 doc-fragment 規則不啟用（`noise.py:143-144`）。所以「不帶旗標 = 行為不變」由既有程式保證，本 plan 只要求以測試鎖定。
2. doc-fragment 判準（既有，勿改）：body strip 後第一行為 markdown heading 且 heading 文字（normalized）命中語料 heading 集合，**且** 其後 ≥2 條內容行逐字（normalized whitespace）命中語料行集合（`noise.py:134-157`、`_DOC_FRAGMENT_MIN_CONTENT_HITS=2`）。
3. drop 計入 `atomizer_pipeline.run` 回傳 summary 的 `noise_dropped`（`pipeline.py:511-513`），dream orchestrator 把該 summary 原樣放進 record 的 `passes.atomize`（`dream/orchestrator.py:46`）並寫 `runtime/ledger/dream.jsonl`。drop 只記 `LOGGER.info`，**不進 warnings、不算 skipped**（`pipeline.py:448-451`）。
4. `memory atomize` 的既有旗標措辭（`cli.py:72-75`）是本次 dream run 旗標的樣板；`atomizer/cli.py:104-107` 的 `_instruction_corpus` 是佈線樣板（用 `getattr` 防禦式讀取）。
5. 現行 dream run parser（`paulshaclaw/memory/cli.py:81-89`）如下，新 argument 插在 `--agent-command` 之後、`set_defaults` 之前：

```python
    dream_run = dream_subparsers.add_parser("run")
    dream_run.add_argument("--memory-root", required=True)
    dream_run.add_argument("--now", default=None)
    dream_run.add_argument("--dry-run", action="store_true")
    dream_run.add_argument("--require-idle", action="store_true")
    dream_run.add_argument("--max-load", type=float, default=1.0)
    dream_run.add_argument("--promoter", choices=["identity", "llm"], default=None)
    dream_run.add_argument("--agent-command", default=None)
    dream_run.set_defaults(func=_dream)
```

6. 現行 `dream/cli.py:37-45` 的 `atomize_fn`（未傳 `doc_corpus`，這就是斷點）：

```python
    def atomize_fn() -> dict[str, object]:
        return atomizer_pipeline.run(
            memory_root,
            config=atom_cfg,
            config_hash=atom_hash,
            now=now,
            dry_run=args.dry_run,
            promoter=promoter,
        )
```

7. 現行 `scripts/start.sh:195-197` 的 dream 命令（:194 是其上方的 `sleep "$interval"`，勿動）：

```bash
      PYTHONPATH="$REPO" "$PY" -m paulshaclaw.memory.cli memory dream run \
        --memory-root "$dream_root" --require-idle --promoter llm \
        >>"$dream_log" 2>&1 || true
```

---

## Task 1: `memory dream run --instruction-root` 佈線（CLI parser + dream/cli）

**Files:**
- Test: `paulshaclaw/memory/tests/test_dream_cli_instruction_root.py`（新增）
- Modify: `paulshaclaw/memory/cli.py`（dream run parser 區塊）
- Modify: `paulshaclaw/memory/dream/cli.py`

- [ ] **Step 1: Write the failing test**

新增檔案，完整內容如下：

```python
# paulshaclaw/memory/tests/test_dream_cli_instruction_root.py
"""#176: dream 路徑接上 doc-fragment 語料（opt-in --instruction-root）。

行為契約：不帶 --instruction-root 時 dream run 行為與變更前完全一致
（空語料 → doc-fragment 規則惰性 → echo slice 照舊寫入、noise_dropped=0）。
"""
from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
from unittest.mock import patch

from paulshaclaw.memory import cli

_REPO_ROOT = Path(__file__).resolve().parents[3]

# 模擬 instruction 文件（語料來源）。「分支政策」段 = 會被 echo 的目標。
_DOC = """# fake-project 開發規範

## 分支政策
- 一律從 main 開 feature/<slug> 分支
- 禁止直接 push 到 main

## 測試政策
- 每個 PR 必須跑完整測試
"""

# echo session：body 為上述文件「分支政策」段逐字內容
# （首行 heading 命中語料 heading + 2 條內容行逐字命中 ≥ _DOC_FRAGMENT_MIN_CONTENT_HITS=2）。
_ECHO_RAW = """---
memory_layer: inbox
project: paulshaclaw
source_agent: claude
source_session: s-echo
source_artifact: research
captured_at: "2026-07-02T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
## 分支政策
- 一律從 main 開 feature/<slug> 分支
- 禁止直接 push 到 main
"""

# 真知識 session：不命中語料，任何情況都必須照常寫入 knowledge。
_REAL_RAW = """---
memory_layer: inbox
project: paulshaclaw
source_agent: claude
source_session: s-real
source_artifact: research
captured_at: "2026-07-02T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/y.md
---
# gh pr checks 的 CI 判定
gh 2.45.0 的 pr checks 沒有 --json，要用 pr view --json statusCheckRollup 判 CI。
"""


def _seed(root: Path, name: str, raw: str) -> None:
    p = root / "inbox" / "research" / "claude" / "2026-07-02" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(raw, encoding="utf-8")


@contextmanager
def _isolated_home(root: Path):
    # moc pass 會用 instruction_corpus.load_corpus() 掃 HOME 下 curated roots；
    # 隔離 HOME 讓測試 hermetic（沿 test_dream_e2e.py 慣例）。
    home = root / "home"
    home.mkdir(parents=True, exist_ok=True)
    with mock.patch.dict(os.environ, {"HOME": str(home)}):
        yield


def _tmp_dir() -> TemporaryDirectory[str]:
    return TemporaryDirectory(dir=_REPO_ROOT)


class DreamCliInstructionRootPlumbingTests(unittest.TestCase):
    """dream/cli 佈線：--instruction-root → corpus_for_roots → pipeline.run(doc_corpus=...)"""

    def _run_with_captured_pipeline(self, extra_argv: list[str]) -> dict:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            doc = root / "AGENTS.md"
            doc.write_text(_DOC, encoding="utf-8")
            captured: dict = {}

            def fake_run(memory_root, **kwargs):
                captured.update(kwargs)
                return {"summary": {"split_sessions": 0, "slices": 0, "skipped": 0,
                                    "noise_dropped": 0, "config_hash": "x", "dry_run": True},
                        "warnings": []}

            argv = ["memory", "dream", "run", "--memory-root", str(root),
                    "--now", "2026-07-02T05:00:00Z", "--dry-run"]
            argv += [a.replace("__DOC__", str(doc)) for a in extra_argv]
            buf = io.StringIO()
            with patch("paulshaclaw.memory.dream.cli.atomizer_pipeline.run",
                       side_effect=fake_run), redirect_stdout(buf):
                rc = cli.main(argv)
            self.assertEqual(rc, 0)
            return captured

    def test_flag_builds_corpus_and_passes_doc_corpus(self):
        captured = self._run_with_captured_pipeline(["--instruction-root", "__DOC__"])
        corpus = captured.get("doc_corpus")
        self.assertTrue(corpus, "帶 --instruction-root 時 doc_corpus 必須為非空語料")
        self.assertIn("分支政策", corpus.headings)

    def test_no_flag_keeps_doc_fragment_rule_inert(self):
        # 行為契約（回歸鎖）：不帶旗標 → falsy 語料 → doc-fragment 規則惰性。
        captured = self._run_with_captured_pipeline([])
        self.assertFalse(captured.get("doc_corpus"),
                         "不帶 --instruction-root 時 doc_corpus 必須為 falsy（規則惰性）")


class DreamRunDocCorpusE2ETests(unittest.TestCase):
    """真 pipeline（identity promoter）端到端驗證 drop / 不 drop。"""

    def _dream_run(self, root: Path, extra_argv: list[str]) -> dict:
        buf = io.StringIO()
        with _isolated_home(root), redirect_stdout(buf):
            rc = cli.main(["memory", "dream", "run", "--memory-root", str(root),
                           "--now", "2026-07-02T05:00:00Z", "--promoter", "identity",
                           *extra_argv])
        self.assertEqual(rc, 0)
        return json.loads(buf.getvalue())

    def _knowledge_bodies(self, root: Path) -> list[str]:
        return [p.read_text(encoding="utf-8")
                for p in (root / "knowledge").rglob("*.md")
                if not p.name.endswith("-moc.md")]

    def test_with_instruction_root_drops_doc_fragment_keeps_real(self):
        with _tmp_dir() as tmp:
            root = Path(tmp)
            doc = root / "AGENTS.md"
            doc.write_text(_DOC, encoding="utf-8")
            _seed(root, "s-echo.md", _ECHO_RAW)
            _seed(root, "s-real.md", _REAL_RAW)
            payload = self._dream_run(root, ["--instruction-root", str(doc)])
            self.assertEqual(payload["passes"]["atomize"]["noise_dropped"], 1)
            bodies = self._knowledge_bodies(root)
            self.assertTrue(any("statusCheckRollup" in b for b in bodies),
                            "真知識 slice 必須照常寫入 knowledge")
            self.assertFalse(any("分支政策" in b for b in bodies),
                             "doc-fragment slice 不得寫入 knowledge")

    def test_without_instruction_root_behavior_unchanged(self):
        # 行為契約（回歸鎖，變更前後皆須綠）：不帶旗標時 echo 照舊寫入。
        with _tmp_dir() as tmp:
            root = Path(tmp)
            _seed(root, "s-echo.md", _ECHO_RAW)
            payload = self._dream_run(root, [])
            self.assertEqual(payload["passes"]["atomize"]["noise_dropped"], 0)
            self.assertTrue(any("分支政策" in b for b in self._knowledge_bodies(root)),
                            "不帶旗標時 doc-fragment 規則必須惰性、slice 照舊寫入")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_dream_cli_instruction_root.py -q`
Expected: **RED** —— `test_flag_builds_corpus_and_passes_doc_corpus` 與 `test_with_instruction_root_drops_doc_fragment_keeps_real` 因 argparse `error: unrecognized arguments: --instruction-root ...`（SystemExit: 2）失敗；兩個「不帶旗標」的回歸鎖測試**預期已綠**（它們鎖定的是現行行為）。

- [ ] **Step 3a: cli.py dream run parser 加 argument**

`paulshaclaw/memory/cli.py`，在 `dream_run.add_argument("--agent-command", default=None)`（:88）與 `dream_run.set_defaults(func=_dream)`（:89）之間插入（措辭沿 atomize 的 :72-75）：

```python
    dream_run.add_argument(
        "--instruction-root", action="append", default=None,
        help="agent-instruction doc root/file; when given, the atomize pass drops "
             "doc-fragment slices (verbatim instruction-doc sections) at produce "
             "time. Repeatable; omit to keep doc-fragment detection off.")
```

不動本檔其他任何行（含 import 區、`knowledge` / `atomize` 等其他 parser 區塊）。

- [ ] **Step 3b: dream/cli.py 佈線**

`paulshaclaw/memory/dream/cli.py`：

(1) import 區：在 `from ..atomizer import pipeline as atomizer_pipeline`（:9）之後、`from ..janitor import config as janitor_config`（:10）**之前**插入一行（`instruction_corpus` 按字母序排在 `atomizer` 之後、`janitor` 之前，維持既有 import 排序）：

```python
from ..instruction_corpus import corpus_for_roots
```

(2) `_run` 內、`now = args.now`（:35）之後加一行（`getattr` 防禦式讀取——`dream status` 與外部建構的 Namespace 沒有此欄位）：

```python
    doc_corpus = corpus_for_roots(getattr(args, "instruction_root", None))
```

(3) `atomize_fn` 的 `atomizer_pipeline.run(...)` 呼叫在 `promoter=promoter,` 之後加：

```python
            doc_corpus=doc_corpus,
```

改完的 `atomize_fn` 全貌：

```python
    def atomize_fn() -> dict[str, object]:
        return atomizer_pipeline.run(
            memory_root,
            config=atom_cfg,
            config_hash=atom_hash,
            now=now,
            dry_run=args.dry_run,
            promoter=promoter,
            doc_corpus=doc_corpus,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_dream_cli_instruction_root.py paulshaclaw/memory/tests/test_dream_cli.py paulshaclaw/memory/tests/test_dream_e2e.py paulshaclaw/memory/tests/test_dream_cli_moc_warnings.py -q`
Expected: **GREEN**（新檔 4 tests + 既有 dream cli/e2e 測試零回歸）。

- [ ] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add paulshaclaw/memory/cli.py paulshaclaw/memory/dream/cli.py paulshaclaw/memory/tests/test_dream_cli_instruction_root.py
git commit -m "feat(memory): dream run 加 --instruction-root 接上 doc-fragment 語料（#176）"
```

---

## Task 2: start.sh 生產 dream loop 傳語料 roots

**Files:**
- Test: `paulshaclaw/memory/tests/test_start_sh_dream_flags.py`（新增）
- Modify: `scripts/start.sh`（僅 dream run 命令）

- [ ] **Step 1: Write the failing test**

新增檔案，完整內容如下（風格沿 `test_dream_systemd_template.py`——以檔案內容 guard 鎖生產配置）：

```python
# paulshaclaw/memory/tests/test_start_sh_dream_flags.py
"""#176 guard: 生產 dream loop（scripts/start.sh）必須傳 doc-fragment 語料 roots。

roots 集合 = instruction_corpus.default_roots()（與 #156 moc/runner 的 index 端
broad corpus 同一組來源）：index 排除什麼、產生端就擋什麼。
"""
from __future__ import annotations

import unittest
from pathlib import Path

_START_SH = Path(__file__).resolve().parents[3] / "scripts" / "start.sh"


class StartShDreamFlagsTests(unittest.TestCase):
    def _dream_cmd(self) -> str:
        text = _START_SH.read_text(encoding="utf-8")
        i = text.index("memory dream run")
        j = text.index('>>"$dream_log"', i)  # dream run 命令以此結尾
        return text[i:j]

    def test_dream_run_keeps_existing_flags(self):
        cmd = self._dream_cmd()
        self.assertIn("--require-idle", cmd)
        self.assertIn("--promoter llm", cmd)

    def test_dream_run_passes_default_instruction_roots(self):
        cmd = self._dream_cmd()
        # 與 instruction_corpus.default_roots() 一致：共 9 個 root。
        self.assertEqual(cmd.count("--instruction-root"), 9)
        for root in ('"$HOME/.claude/CLAUDE.md"', '"$HOME/CLAUDE.md"',
                     '"$HOME/AGENTS.md"', '"$HOME/GEMINI.md"',
                     '"$HOME/.codex"', '"$HOME/.agents"', '"$HOME/.gemini"',
                     '"$HOME/prj_pri"', '"$HOME/prj_arc"'):
            self.assertIn(f"--instruction-root {root}", cmd)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_start_sh_dream_flags.py -q`
Expected: **RED** —— `test_dream_run_passes_default_instruction_roots` 失敗（count 0 != 9）；`test_dream_run_keeps_existing_flags` 已綠。

- [ ] **Step 3: Modify start.sh（最小 diff）**

`scripts/start.sh` 的 `start_dream_loop()` 內，把現行（:195-197）：

```bash
      PYTHONPATH="$REPO" "$PY" -m paulshaclaw.memory.cli memory dream run \
        --memory-root "$dream_root" --require-idle --promoter llm \
        >>"$dream_log" 2>&1 || true
```

改為（只在 `--promoter llm \` 與 `>>"$dream_log"` 之間插入 9 行 + 上方 2 行註解；其餘一字不動）：

```bash
      # #176: doc-fragment 產生端過濾。roots = instruction_corpus.default_roots()，
      # 與 moc/runner 的 index 端 broad corpus 同源——index 排除什麼、產生端就擋什麼。
      PYTHONPATH="$REPO" "$PY" -m paulshaclaw.memory.cli memory dream run \
        --memory-root "$dream_root" --require-idle --promoter llm \
        --instruction-root "$HOME/.claude/CLAUDE.md" \
        --instruction-root "$HOME/CLAUDE.md" \
        --instruction-root "$HOME/AGENTS.md" \
        --instruction-root "$HOME/GEMINI.md" \
        --instruction-root "$HOME/.codex" \
        --instruction-root "$HOME/.agents" \
        --instruction-root "$HOME/.gemini" \
        --instruction-root "$HOME/prj_pri" \
        --instruction-root "$HOME/prj_arc" \
        >>"$dream_log" 2>&1 || true
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
cd /home/paul_chen/prj_pri/paulshaclaw && bash -n scripts/start.sh \
  && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_start_sh_dream_flags.py -q
```
Expected: `bash -n` 無輸出（語法 OK）、guard test **GREEN**（2 tests）。

- [ ] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add scripts/start.sh paulshaclaw/memory/tests/test_start_sh_dream_flags.py
git commit -m "feat(memory): start.sh dream loop 傳 instruction roots 啟用 doc-fragment 過濾（#176）"
```

---

## Task 3: 回歸與收尾

- [ ] **Step 1: 本機全套 pytest**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q`
Expected: 全綠、零回歸（**勿用 `unittest discover`**——會靜默跳過 pytest 風格的函式測試）。

- [ ] **Step 2: CI 等效命令**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && python -m pytest tests/ paulshaclaw/memory/tests/ -q`
Expected: 全綠（與 `.github/workflows/tests.yml` 同口徑）。

- [ ] **Step 3: 勾 OpenSpec tasks 與 Verification Summary**

把 `openspec/changes/stage2-dream-doc-corpus/tasks.md` 的已完成項勾為 `[x]`，並在底部 Verification Summary 填入實際跑過的指令與結果摘要。

- [ ] **Step 4: 依 Delivery 段 push 並開 PR（不 merge）**

---

## Delivery（repo 分支 / PR 政策，必守）

- **Branch**：`feature/176-stage2-dream-doc-corpus`（R-12：PR 進 main 的 head 必須 `feature/<slug>`）。動工前先 `git pull --ff-only`（失敗再 `git fetch --all --prune`）。
- **Commit**：conventional commit、zh-TW（如上各 Task 的 commit 訊息）。
- **PR title**：conventional、zh-TW，例：`feat(memory): dream 路徑接上 doc-fragment 噪音規則（--instruction-root）`（R-10）。
- **PR body**：zh-TW；必含 closing keyword **`Closes #176`**（R-17）；**不得有任何未勾選 checkbox `- [ ]`**（R-11——不要把本 plan 或 tasks.md 的 checkbox 原樣貼進 PR body）；簡述三段佈線 + 行為契約（不帶旗標行為不變）+ 測試證據（pytest 全綠輸出摘要）。
- **禁區**：不碰 `.github/workflows/**`、不碰任何 `policy_version` / `.paul-project.yml`（R-20）。
- 完成 push 後開 PR，**不 merge**（等 CI 綠與人工 review；「修好」的定義到 PR 為止）。
- CI 綠判定：`gh pr view <N> --json statusCheckRollup`（gh 2.45.0 的 `pr checks` 無 `--json`）。

---

## Deployment/Ops notes（不屬於本 PR 的動作）

以下為 merge 後的營運動作，**不得**寫成 implementation task、不在 PR 內執行：

1. **部署**：`scripts/start.sh` 由 repo 工作樹直接執行（dream loop 以 `PYTHONPATH="$REPO"` 跑 working tree），**非** install.sh 複製路徑——main 更新後重啟 start.sh（tmux 慣例：對 start.sh pid 送 `kill -TERM` 再 relaunch）即生效，無 hooks 重新同步需求。本 change 未動 `paulshaclaw/memory/hooks/*`。
2. **生效驗證**：下一輪 dream run 後看 `~/.agents/memory/runtime/ledger/dream.jsonl` 尾筆 `passes.atomize.noise_dropped`（遇 doc-fragment 時 >0），以及 `~/.agents/log/dream.log` 的 `atomize: dropped noise slice ...(doc-fragment)` 行。
3. **存量 92 筆 doc-fragment 清理是 ops、不入本 PR**：serialwrap 48 / testpilot 44（identity 時代殘留）。**勿對 serialwrap 以現行 AGENTS.md 全桶 `prune-noise`**——audit 實測該 manifest 會出 ~34 筆、混入 mcu-flash-55 類「使用者先寫筆記、後併入 AGENTS.md」的真知識 echo（#147 過刪教訓）；正確路徑是固定清單逐筆核 manifest，見 **#177** 的處理範圍。任何 `--apply` 前必先 `--dry-run` 核 manifest，數字超預估即停。

---

## Self-Review

- **Spec coverage**：delta spec 5 個 scenario ↔ 測試對映——「dream run 帶旗標 drop」→ `test_with_instruction_root_drops_doc_fragment_keeps_real` + `test_flag_builds_corpus_and_passes_doc_corpus`；「不帶旗標行為不變」→ `test_no_flag_keeps_doc_fragment_rule_inert` + `test_without_instruction_root_behavior_unchanged`；「生產 loop 傳 roots」→ `test_dream_run_passes_default_instruction_roots`；既有「產生端阻斷／回溯 prune」scenario 由既有測試（`test_atomizer_pipeline` / `test_prune_noise`）持續覆蓋，本 change 不動其實作。
- **VERIFY corrections 對齊**：audit 修正版指出 retrieval index 已排噪（#156），本 plan 的動機敘述據此定調為「wakeup brief / MOC 淨化 + dream 路徑防再犯 + 遙測恢復真實」，未沿用被推翻的「污染 retrieval pool / offer shortlist」舊敘述；存量清理遵 corrections（勿全桶 prune）列為 ops。
- **Placeholder scan**：所有 Step 皆含完整測試碼／精確 diff／絕對路徑指令／預期輸出，無 TODO/TBD。
- **Type consistency**：`--instruction-root`（`action="append"` → `args.instruction_root: list[str] | None`）→ `corpus_for_roots(...) -> DocCorpus` → `pipeline.run(doc_corpus=...)` → `classify_noise(..., doc_corpus=...)` 全鏈一致；`DocCorpus.__bool__` 使空語料 falsy，plumbing 測試據此斷言。
