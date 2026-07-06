# Stage 2 project key rekey 遷移 + untitled 固定清單清理 + janitor lint Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付 issue #177 的三個工具（工具就緒、ops 另議）：(1) 一次性 rekey 遷移 CLI `memory knowledge rekey --from <old-key> --to <slug>`（dry-run 產 manifest 不動檔；apply 改 frontmatter project + 搬檔到 `knowledge/<slug>/` + 觸發 run_moc 重建，勿手改 retrieval.db）；(2) `memory knowledge prune-noise` 加 `--paths` 固定清單模式（只刪清單內檔案、超出即錯）；(3) janitor lint：掃到 `title: untitled` 或 project 含 `/` 的 raw-remote key → dream ledger 告警（不自動改）。

**Architecture:** rekey 仿 `paulshaclaw/memory/retitle.py` 的 one-shot migration 模式（manifest / dry-run / apply / run_moc）；固定清單 prune 是 `cli.py::_prune_noise` 旁的獨立 listed 模式（fail-closed 驗證 → manifest before unlink → 刪除 → build_mocs）；lint 是 `janitor/rules.py` 的純函式 `plan_lint(records)`，由 `janitor/scanner.py::run_scan` 接進 `summary["lint"]` 與 warnings——dream orchestrator（`dream/orchestrator.py:36-49`）只把 summary 落 dream ledger、丟棄 warnings 文字，所以 counts 必須在 summary 裡才會出現在 `dream.jsonl` 的 `passes.janitor`。

**Tech Stack:** Python 3.12、pytest（測試檔沿用既有 unittest.TestCase 風格、pytest 執行）、PyYAML、既有 `moc/frontmatter_io.py`、`moc/runner.py::run_moc`、`atomizer/config.py::{sanitize_project_component,is_safe_path_component}`。

**Spec:** OpenSpec change `openspec/changes/stage2-key-rekey-untitled-cleanup/`｜issue #177｜audit `untitled-and-orphan-dirs`（PARTIAL，VERIFY corrections 已納入本 plan）。

---

## Boundary（可改檔案白名單）

只允許改動以下檔案，超出即 scope violation（先停手、回報協調者）：

- Create: `paulshaclaw/memory/rekey.py`
- Create: `paulshaclaw/memory/tests/test_rekey.py`
- Modify: `paulshaclaw/memory/cli.py`
- Modify: `paulshaclaw/memory/janitor/record_source.py`
- Modify: `paulshaclaw/memory/janitor/rules.py`
- Modify: `paulshaclaw/memory/janitor/scanner.py`
- Modify: `paulshaclaw/memory/tests/test_prune_noise.py`
- Modify: `paulshaclaw/memory/tests/test_janitor_rules.py`
- Modify: `paulshaclaw/memory/tests/test_janitor_scanner.py`
- Modify: `openspec/changes/stage2-key-rekey-untitled-cleanup/tasks.md`（勾 checkbox 用）

**禁止事項（VERIFY 推翻，絕不可繞回）：**
- 嚴禁實作或在任何文件/註解建議「拿現行 serialwrap AGENTS.md 當 corpus 對 serialwrap 全桶 prune」——審計實測 manifest 會出 ~34 列、掃進 26 筆有標題真筆記；13 筆 untitled 的清理只能走固定清單模式（ops 執行、不在本 PR）。
- 嚴禁直接讀寫 `runtime/indexes/retrieval.db`；index 一律由 `run_moc` / `build_mocs` 重建。
- 不碰 `.github/workflows/**`、`policy_version`、hooks、`importer/project_resolver.py`、`noise.py`、`retitle.py`。

---

## 背景契約（實作前必讀的 file:line）

- `paulshaclaw/memory/retitle.py:41-120` — rekey 要仿的模式：rglob 掃 `knowledge/`、跳過 `-moc.md`、`_fio.read` 解析、`memory_layer != "knowledge"` 跳過、manifest 原子寫入 `runtime/ledger/`、apply 有成功筆數才 `run_moc(memory_root, now)`。
- `paulshaclaw/memory/cli.py:141-173` — `knowledge` subparser 現有 `prune-noise` / `retitle-untitled` 兩個子命令；新 `rekey` 加在此區。`cli.py:292-357` — `_prune_noise` handler（`--paths` 分流點）。`cli.py:284-289` — `_write_manifest`（原子寫入，直接重用）。
- `paulshaclaw/memory/atomizer/config.py:157-179` — `is_safe_path_component`（`--to` 驗證）與 `sanitize_project_component`（project → 磁碟目錄名：`/`→`__`；`github.com/hamanpaul/testpilot` → `github.com__hamanpaul__testpilot`）。
- `paulshaclaw/memory/moc/search.py:100`（`AND m.project = ?`）與 `paulshaclaw/memory/wakeup/builder.py:88-112`（sanitize 後掃 `knowledge/<safe>/` 目錄＋frontmatter project 相等）— 這就是 rekey 必須「frontmatter＋搬檔」雙管齊下的原因。
- `paulshaclaw/memory/moc/runner.py:10-27` — `run_moc`：reconcile（會把檔名整回 `<slugify(title)>--<slice_id>.md`，slice_id 不變、安全）→ linker → `build_mocs`（寫 `knowledge/<safe_project>-moc.md`）→ faceout → `search.build_index`。
- `paulshaclaw/memory/janitor/record_source.py:22-30`（`KnowledgeRecord` frozen dataclass）與 `:80-133`（`_build_record`：目前只抽 slice_id/supersedes/source_key/captured_at/provenance）。
- `paulshaclaw/memory/janitor/rules.py:202-264` — `plan_scan` 純函式風格（sorted by record_id、deterministic）；`plan_lint` 比照。
- `paulshaclaw/memory/janitor/scanner.py:125-201` — `run_scan`：`records, warnings = record_source.iter_records(...)`、`record_skipped = len(warnings)` 在最前面先取（lint warnings 之後 append 不影響 `skipped` 計數）、summary dict 組裝點在 `:180-188`。
- `paulshaclaw/memory/dream/orchestrator.py:36-49` — `_run_pass`：`passes[name] = summary`（只有 summary 落 dream ledger）；`clean = not warnings and not summary.get("skipped")` → lint findings 存在時 janitor pass 仍會是 not-clean；但 live dream 另有 `atomize.skipped` backlog，因此整體 dream status 不是驗收訊號。驗收只看 `passes.janitor.lint` 與 `lint:` warnings 是否歸零。

**測試執行方式（勿用 unittest discover——會靜默跳過 pytest 風格測試）：**

- 本機單檔：`cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_rekey.py -q`
- 本機全套：`cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q`
- CI 等效：`python -m pytest tests/ paulshaclaw/memory/tests/ -q`

---

## File Structure

- Create: `paulshaclaw/memory/rekey.py` — `RekeyError`、`rekey_project()`、`_write_manifest()`。
- Create: `paulshaclaw/memory/tests/test_rekey.py` — 模組測試 + CLI 測試。
- Modify: `paulshaclaw/memory/cli.py` — `knowledge rekey` subparser + `_rekey` handler；`prune-noise --paths` + `_prune_listed`。
- Modify: `paulshaclaw/memory/janitor/record_source.py` — `KnowledgeRecord` 加 `title`/`project`（尾端、預設 `""`）。
- Modify: `paulshaclaw/memory/janitor/rules.py` — `plan_lint()` + rule 常數。
- Modify: `paulshaclaw/memory/janitor/scanner.py` — `run_scan` 接 lint。
- Test: `paulshaclaw/memory/tests/test_prune_noise.py`（+`PruneListedTests`）、`test_janitor_rules.py`（+`LintRuleTests`/`LintFieldExtractionTests`）、`test_janitor_scanner.py`（+`ScannerLintTests`）。

---

## Task 1: rekey 遷移模組

**Files:**
- Test: `paulshaclaw/memory/tests/test_rekey.py`（新）
- Create: `paulshaclaw/memory/rekey.py`

- [ ] **Step 1: Write the failing test**

```python
# paulshaclaw/memory/tests/test_rekey.py
from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory import rekey
from paulshaclaw.memory.moc import frontmatter_io as fio

OLD_KEY = "github.com/hamanpaul/testpilot"
OLD_DIR = "github.com__hamanpaul__testpilot"   # sanitize_project_component(OLD_KEY)


def _slice(root: Path, dirname: str, project: str, name: str, body: str,
           *, title: str = "uart-fix") -> Path:
    p = root / "knowledge" / dirname / name
    p.parent.mkdir(parents=True, exist_ok=True)
    sid = name.split("--")[-1].replace(".md", "")
    p.write_text(
        f"---\nslice_id: {sid}\nmemory_layer: knowledge\n"
        f"project: {project}\nartifact_kind: report\ntitle: {title}\n---\n{body}\n",
        encoding="utf-8")
    return p


class RekeyProjectTests(unittest.TestCase):
    def test_dry_run_writes_manifest_and_touches_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            p = _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", "真實筆記內容一。")
            summary = rekey.rekey_project(root, old_key=OLD_KEY, new_slug="testpilot",
                                          now="2026-07-02T00:00:00Z", apply=False)
            self.assertTrue(p.exists())
            fm, _ = fio.read(p.read_text(encoding="utf-8"))
            self.assertEqual(fm["project"], OLD_KEY)          # frontmatter 不動
            self.assertEqual(summary["planned"], 1)
            self.assertEqual(summary["rekeyed"], 0)
            manifests = list((root / "runtime" / "ledger").glob("rekey-*.jsonl"))
            self.assertEqual(len(manifests), 1)
            rows = [json.loads(l) for l in manifests[0].read_text().splitlines() if l.strip()]
            self.assertEqual(rows[0]["status"], "dry-run")
            self.assertEqual(rows[0]["from"], OLD_KEY)
            self.assertEqual(rows[0]["to"], "testpilot")

    def test_apply_moves_file_updates_frontmatter_and_rebuilds_moc(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            body = "真實筆記內容：UART2 pinmux 設錯時靜默失效。"
            p = _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", body)
            summary = rekey.rekey_project(root, old_key=OLD_KEY, new_slug="testpilot",
                                          now="2026-07-02T00:00:00Z", apply=True)
            self.assertFalse(p.exists())
            target = root / "knowledge" / "testpilot" / "uart-fix--sl-a1.md"
            self.assertTrue(target.exists())
            fm, new_body = fio.read(target.read_text(encoding="utf-8"))
            self.assertEqual(fm["project"], "testpilot")
            self.assertEqual(fm["slice_id"], "sl-a1")         # slice_id 保留
            self.assertEqual(new_body.strip(), body)          # body 逐字不變
            self.assertEqual(summary["rekeyed"], 1)
            # run_moc 已觸發：新 slug 的 project MOC 存在
            self.assertTrue((root / "knowledge" / "testpilot-moc.md").exists())

    def test_apply_removes_emptied_source_dir_and_orphan_moc(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", "內容")
            orphan = root / "knowledge" / f"{OLD_DIR}-moc.md"
            orphan.write_text("---\nmemory_layer: moc\n---\nstale\n", encoding="utf-8")
            summary = rekey.rekey_project(root, old_key=OLD_KEY, new_slug="testpilot",
                                          now="2026-07-02T00:00:00Z", apply=True)
            self.assertFalse((root / "knowledge" / OLD_DIR).exists())
            self.assertFalse(orphan.exists())
            self.assertTrue(summary["removed_source_dir"])
            self.assertTrue(summary["removed_orphan_moc"])

    def test_conflict_target_is_skipped_and_source_not_stamped(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            src = _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", "舊 key 內容")
            _slice(root, "testpilot", "testpilot", "uart-fix--sl-a1.md", "同名既有檔")
            summary = rekey.rekey_project(root, old_key=OLD_KEY, new_slug="testpilot",
                                          now="2026-07-02T00:00:00Z", apply=True)
            self.assertTrue(src.exists())                     # source 原地
            fm, _ = fio.read(src.read_text(encoding="utf-8"))
            self.assertEqual(fm["project"], OLD_KEY)          # frontmatter 不 stamp
            self.assertEqual(summary["conflicts"], 1)
            self.assertEqual(summary["rekeyed"], 0)

    def test_other_projects_untouched(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            # title 必須與檔名 slug 一致（"note"）：apply 會觸發 run_moc，其
            # naming.reconcile 依 <slugify(title)>--<slice_id>.md 重命名，
            # title/檔名不一致會讓本斷言誤判成「被 rekey 動到」。
            other = _slice(root, "vendor-b", "vendor-b", "note--sl-b1.md", "vendor-b 真筆記",
                           title="note")
            _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", "內容")
            rekey.rekey_project(root, old_key=OLD_KEY, new_slug="testpilot",
                                now="2026-07-02T00:00:00Z", apply=True)
            self.assertTrue(other.exists())
            fm, _ = fio.read(other.read_text(encoding="utf-8"))
            self.assertEqual(fm["project"], "vendor-b")

    def test_unsafe_new_slug_raises(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(rekey.RekeyError):
                rekey.rekey_project(root, old_key=OLD_KEY, new_slug="a/b",
                                    now="2026-07-02T00:00:00Z", apply=False)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_rekey.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'paulshaclaw.memory.rekey'`

- [ ] **Step 3: Write minimal implementation**

```python
# paulshaclaw/memory/rekey.py
"""One-shot migration: re-key knowledge slices from a legacy raw-remote project
key to a registered short slug (#177).

Before projects.yaml hardening (2026-06-18), resolve_project fell back to the
normalized raw git remote (project_resolver.py:114), e.g.
``github.com/hamanpaul/testpilot``. Recall filters by strict project equality
(moc/search.py:100; wakeup/builder.py:88-112 scans knowledge/<sanitized>/), so
those slices are invisible to short-slug sessions. This migration rewrites
frontmatter ``project`` to the new slug AND moves the file into
``knowledge/<slug>/`` (both are required — either alone leaves a torn state),
then triggers run_moc so MOC and the retrieval index are rebuilt. It never
touches runtime/indexes/retrieval.db directly. Conflicting targets are skipped
untouched (no frontmatter stamp) and recorded honestly in the manifest.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from .atomizer.config import is_safe_path_component, sanitize_project_component
from .moc import frontmatter_io as _fio
from .moc.runner import run_moc


class RekeyError(ValueError):
    """Raised when rekey arguments are invalid (unsafe slug / empty key)."""


def _write_manifest(manifest: Path, rows: list[dict]) -> None:
    manifest.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    tmp = manifest.with_name(f".{manifest.name}.tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(manifest)


def rekey_project(
    memory_root: Path,
    *,
    old_key: str,
    new_slug: str,
    now: str,
    apply: bool,
) -> dict:
    """Re-key every knowledge slice whose frontmatter project == ``old_key`` to
    ``new_slug``. Returns a summary dict and always writes an audit manifest to
    ``runtime/ledger/rekey-<now>.jsonl``."""
    if not is_safe_path_component(new_slug):
        raise RekeyError(f"--to must be a path-safe slug (no '/'): {new_slug!r}")
    if not old_key.strip() or old_key == new_slug:
        raise RekeyError("--from must be a non-empty key different from --to")

    knowledge = memory_root / "knowledge"
    target_dir = knowledge / sanitize_project_component(new_slug)
    rows: list[dict] = []

    for path in sorted(knowledge.rglob("*.md")) if knowledge.exists() else []:
        if path.name.endswith("-moc.md"):
            continue
        try:
            fm, _body = _fio.read(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        if fm.get("memory_layer") != "knowledge":
            continue
        if str(fm.get("project", "")) != old_key:
            continue

        target = target_dir / path.name
        base = {"slice_id": str(fm.get("slice_id", "")), "from": old_key,
                "to": new_slug, "path": str(path), "target": str(target)}
        if not apply:
            rows.append({**base, "status": "dry-run"})
            continue
        if target != path and target.exists():
            # Fail-safe: stamping frontmatter without the move (or vice versa)
            # would tear recall apart (dir scan vs frontmatter grouping); skip
            # the slice entirely and leave the resolution to a human.
            rows.append({**base, "status": "conflict"})
            continue
        _fio.update(path, {"project": new_slug})
        target_dir.mkdir(parents=True, exist_ok=True)
        if target != path:
            path.rename(target)
        rows.append({**base, "status": "rekeyed"})

    manifest = memory_root / "runtime" / "ledger" / f"rekey-{now.replace(':', '')}.jsonl"
    _write_manifest(manifest, rows)

    counts = Counter(r["status"] for r in rows)
    removed_source_dir = False
    removed_orphan_moc = False
    if apply and counts.get("rekeyed", 0):
        # Tidy up ONLY what this migration itself emptied: the canonical old-key
        # directory and its now-orphaned project MOC (run_moc rebuilds MOCs for
        # projects that still exist; it never deletes stale ones).
        src_dir = knowledge / sanitize_project_component(old_key)
        if src_dir.is_dir() and not any(src_dir.iterdir()):
            src_dir.rmdir()
            removed_source_dir = True
        orphan_moc = knowledge / f"{sanitize_project_component(old_key)}-moc.md"
        if orphan_moc.exists():
            orphan_moc.unlink()
            removed_orphan_moc = True
        run_moc(memory_root, now)

    return {
        "candidates": len(rows),
        "applied": apply,
        "rekeyed": counts.get("rekeyed", 0),
        "planned": counts.get("dry-run", 0),
        "conflicts": counts.get("conflict", 0),
        "removed_source_dir": removed_source_dir,
        "removed_orphan_moc": removed_orphan_moc,
        "manifest": str(manifest),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_rekey.py -q`
Expected: PASS（6 tests）

- [ ] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add paulshaclaw/memory/rekey.py paulshaclaw/memory/tests/test_rekey.py
git commit -m "feat(memory): #177 rekey 遷移模組（dry-run/apply + manifest + run_moc 重建）"
```

---

## Task 2: rekey CLI 子命令

**Files:**
- Test: `paulshaclaw/memory/tests/test_rekey.py`（新增 `RekeyCliTests` class）
- Modify: `paulshaclaw/memory/cli.py`

- [ ] **Step 1: Write the failing test**

在 `test_rekey.py` 檔尾（`if __name__` 之前）加：

```python
class RekeyCliTests(unittest.TestCase):
    def test_cli_apply_moves_file(self):
        from paulshaclaw.memory.cli import main
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            _slice(root, OLD_DIR, OLD_KEY, "uart-fix--sl-a1.md", "內容")
            rc = main(["memory", "knowledge", "rekey", "--memory-root", str(root),
                       "--from", OLD_KEY, "--to", "testpilot",
                       "--now", "2026-07-02T00:00:00Z", "--apply"])
            self.assertEqual(rc, 0)
            self.assertTrue((root / "knowledge" / "testpilot" / "uart-fix--sl-a1.md").exists())

    def test_cli_rejects_slash_in_to(self):
        from paulshaclaw.memory.cli import main
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            rc = main(["memory", "knowledge", "rekey", "--memory-root", str(root),
                       "--from", OLD_KEY, "--to", "a/b",
                       "--now", "2026-07-02T00:00:00Z", "--dry-run"])
            self.assertEqual(rc, 2)
            # 零副作用：不得產生 manifest
            self.assertFalse(list((root / "runtime" / "ledger").glob("rekey-*.jsonl"))
                             if (root / "runtime" / "ledger").exists() else [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_rekey.py::RekeyCliTests -q`
Expected: FAIL — argparse `invalid choice: 'rekey'` 導致 `SystemExit: 2` 從 `parse_args` 冒出（pytest 將測試內冒出的 SystemExit 記為 failure，兩個測試都 FAILED）。

- [ ] **Step 3: Implement**

3a. `paulshaclaw/memory/cli.py` 的 `_build_parser`，在 `retitle.set_defaults(func=_retitle_untitled)`（cli.py:173）之後、`usage_p = ...` 之前插入：

```python
    rekey_p = knowledge_subparsers.add_parser("rekey")
    rekey_p.add_argument("--memory-root", required=True)
    rekey_p.add_argument("--from", dest="from_key", required=True,
                         help="舊 project key（可含 '/'，如 github.com/hamanpaul/testpilot）。嚴格相等比對。")
    rekey_p.add_argument("--to", dest="to_slug", required=True,
                         help="新短 slug（path-safe，不得含 '/'）。")
    rekey_p.add_argument("--now", default=None)
    kgroup = rekey_p.add_mutually_exclusive_group()
    kgroup.add_argument("--dry-run", action="store_true")
    kgroup.add_argument("--apply", action="store_true")
    rekey_p.set_defaults(func=_rekey)
```

3b. handler（放在 `_retitle_untitled` 之後）：

```python
def _rekey(args: argparse.Namespace) -> int:
    from . import rekey as rekey_mod

    root = Path(args.memory_root)
    now = (args.now or datetime.now(timezone.utc).isoformat()).replace("+00:00", "Z")
    apply = bool(getattr(args, "apply", False))
    try:
        summary = rekey_mod.rekey_project(
            root, old_key=args.from_key, new_slug=args.to_slug, now=now, apply=apply)
    except rekey_mod.RekeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, ensure_ascii=False))
    return 0
```

（`datetime`/`timezone`/`sys`/`json`/`Path` 皆已在 cli.py import，勿重複 import。）

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_rekey.py -q`
Expected: PASS（8 tests）

- [ ] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add paulshaclaw/memory/cli.py paulshaclaw/memory/tests/test_rekey.py
git commit -m "feat(memory): #177 memory knowledge rekey CLI 子命令"
```

---

## Task 3: prune-noise 固定清單模式（--paths）

**Files:**
- Test: `paulshaclaw/memory/tests/test_prune_noise.py`（新增 `PruneListedTests` class）
- Modify: `paulshaclaw/memory/cli.py`

- [ ] **Step 1: Write the failing test**

在 `test_prune_noise.py` 檔尾（`if __name__` 之前）加（沿用該檔既有 `_slice` helper 與 `main` import）：

```python
class PruneListedTests(unittest.TestCase):
    def _seed(self, root: Path):
        # untitled 殘留：body 是「heading+1 行」——classify_noise 依設計判不了它
        # （noise.py:92 _DOC_FRAGMENT_MIN_CONTENT_HITS=2），固定清單即刪除權威。
        listed = _slice(root, "serialwrap", "untitled--sl-u1.md",
                        "## 語言政策\n所有溝通使用 zh-TW。")
        # 可判 noise 但未列清單 -> 固定清單模式下必須保留
        unlisted_noise = _slice(root, "serialwrap", "cwd--sl-n2.md", "## CWD\n/home/x")
        good = _slice(root, "serialwrap", "real--sl-g9.md", "真實筆記：devmem 驗證暫存器。")
        return listed, unlisted_noise, good

    def test_listed_apply_deletes_only_listed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            listed, unlisted_noise, good = self._seed(root)
            paths_file = root / "cleanup.txt"
            paths_file.write_text(f"# 固定清單\n{listed}\n", encoding="utf-8")
            rc = main(["memory", "knowledge", "prune-noise", "--memory-root", str(root),
                       "--now", "2026-07-02T00:00:00Z", "--paths", str(paths_file), "--apply"])
            self.assertEqual(rc, 0)
            self.assertFalse(listed.exists())
            self.assertTrue(unlisted_noise.exists())   # 不在清單 -> 保留（即使是 noise）
            self.assertTrue(good.exists())
            manifests = list((root / "runtime" / "ledger").glob("prune-*.jsonl"))
            self.assertEqual(len(manifests), 1)
            rows = [json.loads(l) for l in manifests[0].read_text().splitlines() if l.strip()]
            self.assertEqual(len(rows), 1)              # manifest 恰等於清單筆數
            self.assertEqual(rows[0]["reason"], "listed")
            self.assertEqual(rows[0]["status"], "deleted")

    def test_listed_dry_run_deletes_nothing(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            listed, _noise, _good = self._seed(root)
            paths_file = root / "cleanup.txt"
            paths_file.write_text(f"{listed}\n", encoding="utf-8")
            rc = main(["memory", "knowledge", "prune-noise", "--memory-root", str(root),
                       "--now", "2026-07-02T00:00:00Z", "--paths", str(paths_file), "--dry-run"])
            self.assertEqual(rc, 0)
            self.assertTrue(listed.exists())
            manifests = list((root / "runtime" / "ledger").glob("prune-*.jsonl"))
            rows = [json.loads(l) for l in manifests[0].read_text().splitlines() if l.strip()]
            self.assertEqual(rows[0]["status"], "dry-run")

    def test_listed_missing_path_fails_closed(self):
        # 清單含不存在路徑 -> rc=2 且整批（含有效的那筆）不刪
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            listed, _noise, _good = self._seed(root)
            paths_file = root / "cleanup.txt"
            paths_file.write_text(f"{listed}\n{root}/knowledge/serialwrap/ghost--sl-x.md\n",
                                  encoding="utf-8")
            rc = main(["memory", "knowledge", "prune-noise", "--memory-root", str(root),
                       "--now", "2026-07-02T00:00:00Z", "--paths", str(paths_file), "--apply"])
            self.assertEqual(rc, 2)
            self.assertTrue(listed.exists())

    def test_listed_outside_knowledge_root_fails_closed(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._seed(root)
            outside = root / "outside.md"
            outside.write_text("---\nmemory_layer: knowledge\n---\nx\n", encoding="utf-8")
            paths_file = root / "cleanup.txt"
            paths_file.write_text(f"{outside}\n", encoding="utf-8")
            rc = main(["memory", "knowledge", "prune-noise", "--memory-root", str(root),
                       "--now", "2026-07-02T00:00:00Z", "--paths", str(paths_file), "--apply"])
            self.assertEqual(rc, 2)
            self.assertTrue(outside.exists())

    def test_paths_mutually_exclusive_with_scan_filters(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            listed, _noise, _good = self._seed(root)
            paths_file = root / "cleanup.txt"
            paths_file.write_text(f"{listed}\n", encoding="utf-8")
            rc = main(["memory", "knowledge", "prune-noise", "--memory-root", str(root),
                       "--now", "2026-07-02T00:00:00Z", "--paths", str(paths_file),
                       "--project", "serialwrap", "--dry-run"])
            self.assertEqual(rc, 2)
            self.assertTrue(listed.exists())
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_prune_noise.py::PruneListedTests -q`
Expected: FAIL — argparse `unrecognized arguments: --paths ...` 導致 `SystemExit: 2`，5 個測試全部 FAILED（含 `test_paths_mutually_exclusive...`：它預期的 rc=2 是 handler 回傳值，RED 階段的 SystemExit 同樣記為 failure）。

- [ ] **Step 3: Implement**

3a. `cli.py` `_build_parser` 的 prune 段（`prune.add_argument("--project", ...)` 之後）加：

```python
    prune.add_argument(
        "--paths", default=None,
        help="固定清單檔：每行一個 knowledge slice 絕對路徑（# 開頭與空行忽略）。"
             "給定時清單即刪除權威（不經 classify_noise），與 --instruction-root/--project 互斥；"
             "任一路徑無效即整批中止（fail-closed）。")
```

3b. `_prune_noise` handler 開頭（`corpus = ...` 之前），在算出 `root`/`now`/`apply` 後插入分流：

```python
    paths_file = getattr(args, "paths", None)
    if paths_file:
        if getattr(args, "instruction_root", None) or getattr(args, "project", None):
            print("error: --paths 與 --instruction-root/--project 互斥", file=sys.stderr)
            return 2
        return _prune_listed(root, Path(paths_file), now=now, apply=apply)
```

3c. 新增 `_prune_listed`（放在 `_prune_noise` 之後）：

```python
def _prune_listed(root: Path, paths_file: Path, *, now: str, apply: bool) -> int:
    """Fixed-list prune (#177): the human-curated list is the whole authority.

    Fail-closed: EVERY entry must resolve to an existing knowledge-slice file
    under <memory-root>/knowledge/ (never a -moc.md, frontmatter must be
    memory_layer: knowledge). Any violation aborts with rc=2 BEFORE any delete.
    """
    knowledge = (root / "knowledge").resolve()
    try:
        raw_lines = paths_file.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        print(f"error: cannot read --paths file: {exc}", file=sys.stderr)
        return 2
    listed = [ln.strip() for ln in raw_lines if ln.strip() and not ln.strip().startswith("#")]
    if not listed:
        print("error: --paths file is empty", file=sys.stderr)
        return 2

    rows: list[dict] = []
    problems: list[str] = []
    for entry in listed:
        try:
            rp = Path(entry).resolve(strict=True)
        except OSError:
            problems.append(f"missing: {entry}")
            continue
        if not rp.is_file() or rp.suffix != ".md" or rp.name.endswith("-moc.md"):
            problems.append(f"not-a-slice: {entry}")
            continue
        if knowledge not in rp.parents:
            problems.append(f"outside-knowledge-root: {entry}")
            continue
        try:
            fm, _body = _fio.read(rp.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError) as exc:
            problems.append(f"unreadable: {entry}: {exc}")
            continue
        if fm.get("memory_layer") != "knowledge":
            problems.append(f"not-knowledge-layer: {entry}")
            continue
        rows.append({"slice_id": str(fm.get("slice_id", "")),
                     "project": str(fm.get("project", "")), "path": str(rp),
                     "reason": "listed", "status": "planned" if apply else "dry-run"})
    if problems:
        for p in problems:
            print(f"error: {p}", file=sys.stderr)
        return 2

    ledger_dir = root / "runtime" / "ledger"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    manifest = ledger_dir / f"prune-{now.replace(':', '')}.jsonl"
    # #139 finding 2：任何 unlink 之前 manifest 先落盤。
    _write_manifest(manifest, rows)

    if apply:
        deleted = False
        for row in rows:
            try:
                Path(row["path"]).unlink()
                row["status"] = "deleted"
                deleted = True
            except OSError as exc:
                row["status"] = "error"
                row["error"] = str(exc)
        _write_manifest(manifest, rows)
        if deleted:
            _moc_builder.build_mocs(root, now=now)

    stats = Counter(r["reason"] for r in rows)
    print(json.dumps({"scanned_noise": len(rows), "applied": apply, "mode": "listed",
                      "by_reason": dict(stats), "manifest": str(manifest)},
                     ensure_ascii=False))
    return 0
```

（`_write_manifest`/`_fio`/`_moc_builder`/`Counter`/`sys` 皆已在 cli.py 頂部就位；掃描模式 `_prune_noise` 的既有輸出格式不變，僅 listed 模式多 `"mode": "listed"`。）

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_prune_noise.py -q`
Expected: PASS（既有 7 + 新 5 = 12 tests）

- [ ] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add paulshaclaw/memory/cli.py paulshaclaw/memory/tests/test_prune_noise.py
git commit -m "feat(memory): #177 prune-noise 固定清單模式（--paths，fail-closed）"
```

---

## Task 4: janitor lint 規則（title-untitled / raw-remote-key）

**Files:**
- Test: `paulshaclaw/memory/tests/test_janitor_rules.py`（新增兩個 class）
- Modify: `paulshaclaw/memory/janitor/record_source.py`、`paulshaclaw/memory/janitor/rules.py`

- [ ] **Step 1: Write the failing test**

在 `test_janitor_rules.py` 檔尾（`if __name__` 之前）加。檔頭已有 `rules`/`KnowledgeRecord`/`Path` import；另補 `from tempfile import TemporaryDirectory` 與 `from paulshaclaw.memory.janitor import record_source` 兩行到 import 區：

```python
def _lint_rec(rid="sl-1", title="真標題", project="paulshaclaw"):
    return KnowledgeRecord(record_id=rid, supersedes=(), source_key="claude:s1",
                           captured_at="2026-06-01T00:00:00Z",
                           provenance={"repo": "r", "commit": "c", "path": "docs/x.md"},
                           path=Path("/tmp/x.md"), title=title, project=project)


class LintRuleTests(unittest.TestCase):
    def test_untitled_title_is_flagged(self):
        findings = rules.plan_lint([_lint_rec(rid="sl-u1", title="untitled")])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule"], "title-untitled")
        self.assertEqual(findings[0]["record_id"], "sl-u1")

    def test_raw_remote_project_key_is_flagged(self):
        findings = rules.plan_lint(
            [_lint_rec(rid="sl-r1", project="github.com/hamanpaul/testpilot")])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0]["rule"], "raw-remote-key")
        self.assertEqual(findings[0]["project"], "github.com/hamanpaul/testpilot")

    def test_clean_record_yields_no_findings(self):
        self.assertEqual(rules.plan_lint([_lint_rec()]), [])

    def test_both_rules_can_fire_on_one_record(self):
        findings = rules.plan_lint([_lint_rec(title="untitled", project="a/b")])
        self.assertEqual({f["rule"] for f in findings},
                         {"title-untitled", "raw-remote-key"})

    def test_findings_are_deterministic_and_sorted(self):
        a = _lint_rec(rid="sl-2", title="untitled")
        b = _lint_rec(rid="sl-1", title="untitled")
        f1 = rules.plan_lint([a, b])
        f2 = rules.plan_lint([b, a])
        self.assertEqual(f1, f2)
        self.assertEqual([f["record_id"] for f in f1], ["sl-1", "sl-2"])


class LintFieldExtractionTests(unittest.TestCase):
    def test_iter_records_extracts_title_and_project(self):
        with TemporaryDirectory() as tmp:
            kroot = Path(tmp) / "knowledge"
            kroot.mkdir(parents=True)
            (kroot / "untitled--sl-1.md").write_text(
                "---\nmemory_layer: knowledge\nslice_id: sl-1\ntitle: untitled\n"
                "project: github.com/hamanpaul/testpilot\nsource_agent: claude\n"
                'source_session: s1\ncaptured_at: "2026-06-22T00:00:00Z"\n---\nbody\n',
                encoding="utf-8")
            records, warnings = record_source.iter_records(kroot)
            self.assertEqual(warnings, [])
            self.assertEqual(records[0].title, "untitled")
            self.assertEqual(records[0].project, "github.com/hamanpaul/testpilot")

    def test_missing_fields_default_to_empty(self):
        # 既有建構呼叫（無 title/project）不破：預設空字串、lint 不誤報
        rec = _rec()
        self.assertEqual(rec.title, "")
        self.assertEqual(rec.project, "")
        self.assertEqual(rules.plan_lint([rec]), [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_janitor_rules.py -q`
Expected: FAIL（7 個新測試全紅）— `TypeError: KnowledgeRecord.__init__() got an unexpected keyword argument 'title'`；`AttributeError: module ... has no attribute 'plan_lint'`。既有 Decay/Reactivation/Determinism 測試維持 PASS（18 passed）。

- [ ] **Step 3: Implement**

3a. `janitor/record_source.py` 的 `KnowledgeRecord`（record_source.py:22-30）**尾端**加兩欄（frozen dataclass，必須放最後、帶預設值，既有 positional/keyword 建構不破）：

```python
@dataclass(frozen=True)
class KnowledgeRecord:
    """A knowledge layer record."""
    record_id: str
    supersedes: tuple[str, ...]
    source_key: str
    captured_at: str
    provenance: Mapping[str, str]
    path: Path
    # Hygiene-lint fields (#177): advisory only, "" when absent.
    title: str = ""
    project: str = ""
```

3b. `_build_record`（record_source.py:80-133）在 `captured_at = ...` 之後加抽取、並傳入建構：

```python
    # Hygiene-lint fields (#177)
    title = _clean_string(data.get("title")) or ""
    project = _clean_string(data.get("project")) or ""
```

`KnowledgeRecord(...)` 建構呼叫尾端補 `title=title, project=project,`。

3c. `janitor/rules.py` 檔尾加：

```python
# --- Hygiene lint (#177): advisory findings, never mutates anything ---

LINT_TITLE_UNTITLED = "title-untitled"
LINT_RAW_REMOTE_KEY = "raw-remote-key"


def plan_lint(records: list[KnowledgeRecord]) -> list[dict[str, Any]]:
    """Flag slices whose title generation failed (``title: untitled``) or whose
    project is a legacy raw-remote key (contains '/'). Pure and read-only:
    returns finding rows sorted by record_id; repair belongs to the rekey /
    retitle / prune-noise CLIs, never to the janitor.
    """
    findings: list[dict[str, Any]] = []
    for record in sorted(records, key=lambda r: r.record_id):
        if record.title == "untitled":
            findings.append({"rule": LINT_TITLE_UNTITLED, "record_id": record.record_id,
                             "path": str(record.path), "project": record.project})
        if "/" in record.project:
            findings.append({"rule": LINT_RAW_REMOTE_KEY, "record_id": record.record_id,
                             "path": str(record.path), "project": record.project})
    return findings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_janitor_rules.py paulshaclaw/memory/tests/test_janitor_record_source.py -q`
Expected: PASS（新 7 tests + 既有全部；record_source 既有測試不受預設欄位影響）

- [ ] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add paulshaclaw/memory/janitor/record_source.py paulshaclaw/memory/janitor/rules.py paulshaclaw/memory/tests/test_janitor_rules.py
git commit -m "feat(memory): #177 janitor lint 規則（title-untitled / raw-remote-key）"
```

---

## Task 5: janitor scanner 接線（summary.lint + warnings）

**Files:**
- Test: `paulshaclaw/memory/tests/test_janitor_scanner.py`（新增 `ScannerLintTests` class）
- Modify: `paulshaclaw/memory/janitor/scanner.py`

- [ ] **Step 1: Write the failing test**

在 `test_janitor_scanner.py` 檔尾（`if __name__` 之前）加（沿用該檔既有 `_setup` helper）：

```python
_UNTITLED_RECORD = """---
memory_layer: knowledge
slice_id: sl-u1
project: github.com/hamanpaul/testpilot
title: untitled
source_agent: claude
source_session: s2
source_artifact: b.md
captured_at: "2026-06-22T00:00:00Z"
provenance:
  repo: paulshaclaw
  commit: c
  path: docs/x.md
---
## 語言政策
所有溝通使用 zh-TW。
"""


class ScannerLintTests(unittest.TestCase):
    def test_lint_counts_and_warnings_surface(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            kroot = root / "knowledge"
            kroot.mkdir(parents=True)
            slice_path = kroot / "untitled--sl-u1.md"
            slice_path.write_text(_UNTITLED_RECORD, encoding="utf-8")
            cfg, cfg_hash = janitor_config.load_config(override_path=None)
            result = scanner.run_scan(root, knowledge_root=kroot, config=cfg,
                                      config_hash=cfg_hash, now="2026-07-02T00:00:00Z",
                                      dry_run=True, source_path_exists=lambda r: True)
            self.assertEqual(result["summary"]["lint"],
                             {"untitled": 1, "raw_remote_key": 1})
            lint_warnings = [w for w in result["warnings"] if w.startswith("lint:")]
            self.assertEqual(len(lint_warnings), 2)
            # 告警不自動改：檔案原封不動、lifecycle 無 lint 事件
            self.assertTrue(slice_path.exists())
            self.assertEqual(
                lifecycle.read_events(root / "runtime" / "ledger" / "lifecycle.jsonl"), [])

    def test_clean_tree_has_zero_lint(self):
        with TemporaryDirectory() as tmp:
            root, kroot = _setup(tmp)
            cfg, cfg_hash = janitor_config.load_config(override_path=None)
            result = scanner.run_scan(root, knowledge_root=kroot, config=cfg,
                                      config_hash=cfg_hash, now="2026-05-31T00:00:00Z",
                                      source_path_exists=lambda r: True)
            self.assertEqual(result["summary"]["lint"],
                             {"untitled": 0, "raw_remote_key": 0})
            self.assertFalse([w for w in result["warnings"] if w.startswith("lint:")])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_janitor_scanner.py -q`
Expected: FAIL — `KeyError: 'lint'`（summary 尚無此 key）；既有 3 個 Scanner 測試維持 PASS。

- [ ] **Step 3: Implement**

`janitor/scanner.py` 的 `run_scan`，在 `events = rules.plan_scan(...)` 之後、count 統計之前插入：

```python
    # Hygiene lint (#177): advisory only. Counts go into summary (the dream
    # orchestrator persists ONLY each pass's summary to the dream ledger —
    # orchestrator.py:36-49 drops warning text), per-finding lines go into
    # warnings for CLI visibility. Findings still mark the janitor pass
    # not-clean, but live dream can remain partial because atomize.skipped has
    # its own backlog; acceptance must key off passes.janitor.lint + vanished
    # lint: warnings, not overall dream status. Lint never writes lifecycle
    # events.
    lint_findings = rules.plan_lint(records)
    for finding in lint_findings:
        warnings.append(
            f"lint:{finding['rule']}: {finding['path']} (project={finding['project']})")
```

summary dict（scanner.py:180-188）加一鍵：

```python
        "lint": {
            "untitled": sum(1 for f in lint_findings
                            if f["rule"] == rules.LINT_TITLE_UNTITLED),
            "raw_remote_key": sum(1 for f in lint_findings
                                  if f["rule"] == rules.LINT_RAW_REMOTE_KEY),
        },
```

注意：`record_skipped = len(warnings)` 在 `run_scan` 開頭已先取值（scanner.py:153-154），lint warnings 之後才 append，`summary["skipped"]` 語義不變。lint findings **不得**產生 lifecycle 事件（不進 `events`）。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/test_janitor_scanner.py paulshaclaw/memory/tests/test_janitor_cli.py paulshaclaw/memory/tests/test_janitor_e2e.py paulshaclaw/memory/tests/test_dream_orchestrator.py paulshaclaw/memory/tests/test_dream_cli.py -q`
Expected: PASS（新 2 tests + janitor/dream 相關既有測試全綠——dream ledger 端經 orchestrator 既有 summary passthrough 自動帶上 `passes.janitor.lint`，無需改 orchestrator）。

- [ ] **Step 5: Commit**

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add paulshaclaw/memory/janitor/scanner.py paulshaclaw/memory/tests/test_janitor_scanner.py
git commit -m "feat(memory): #177 janitor scan 接 lint 進 summary 與 warnings"
```

---

## Task 6: 回歸驗證與收尾

- [ ] **Step 1: 全套 memory 測試**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. ~/.local/bin/pytest paulshaclaw/memory/tests/ -q`
Expected: 全綠（無 fail；skip 屬既有環境性 skip 可接受）。

- [ ] **Step 2: CI 等效全套**

Run: `cd /home/paul_chen/prj_pri/paulshaclaw && PYTHONPATH=. python -m pytest tests/ paulshaclaw/memory/tests/ -q`
Expected: 全綠。

- [ ] **Step 3: 勾選 OpenSpec tasks 並補 Verification Summary**

編輯 `openspec/changes/stage2-key-rekey-untitled-cleanup/tasks.md`：勾選全部 checkbox、在 Verification Summary 段貼上 Step 1/2 的輸出摘要（`Ran ... passed` 行）。

```bash
cd /home/paul_chen/prj_pri/paulshaclaw
git add openspec/changes/stage2-key-rekey-untitled-cleanup/tasks.md
git commit -m "docs(openspec): #177 stage2-key-rekey-untitled-cleanup tasks 勾選與驗證摘要"
```

---

## Deployment / Ops notes（不屬於本 PR；工具 merge 後由使用者另議執行）

以下動作**不得**寫成 implementation task、**不得**在 PR 或 CI 內執行，全部針對 live `~/.agents/memory/`：

1. **13 筆 untitled 固定清單刪除**：
   `ls ~/.agents/memory/knowledge/serialwrap/untitled--*.md > /tmp/untitled-cleanup.txt`（核對恰 13 行）→
   `python3 -m paulshaclaw.memory.cli memory knowledge prune-noise --memory-root ~/.agents/memory --paths /tmp/untitled-cleanup.txt --dry-run` → **核 manifest 恰 13 列、reason 全 `listed`，超出即停** → 同命令改 `--apply`。
   ⚠️ **嚴禁**改走 `--instruction-root ~/prj_pri/serialwrap/AGENTS.md` 全桶 corpus prune——audit 驗證實測會出 ~34 列 manifest、掃進 26 筆有標題真筆記。
2. **8 筆 rekey**（各自 dry-run 核 manifest 恰 4 列再 apply）：
   `... memory knowledge rekey --memory-root ~/.agents/memory --from github.com/hamanpaul/testpilot --to testpilot --dry-run` → `--apply`；
   `... memory knowledge rekey --memory-root ~/.agents/memory --from git.example.com/vendor-b/vendor-b_openwrt_feed --to vendor-b --dry-run` → `--apply`。
   rekey apply 會自動觸發 run_moc 重建 MOC 與 retrieval index——**勿手改 `runtime/indexes/retrieval.db`**。
3. **12 空目錄＋孤兒 `-moc.md`**：`find ~/.agents/memory/knowledge -maxdepth 1 -type d -empty` 產清單、與 audit 的 12 個名單核對後刪除，連同對應 `<key>-moc.md`（rekey apply 已自動清掉 testpilot/vendor-b 舊 key 那兩組）。
4. **驗證**：ops 完成後跑一輪 `memory dream run`，確認 `dream.jsonl` 末筆 `passes.janitor.lint == {"untitled": 0, "raw_remote_key": 0}`，且 janitor CLI / ledger 不再出現 `lint:` warnings；`memory search <關鍵字> --memory-root ~/.agents/memory --project testpilot` 可召回 06-17 舊筆記。
5. **hooks 不涉及**：本 change 無 `hooks/*` 變更，無 install.sh 重佈署需求（package 模組屬 editable install 自動生效）。
6. **告警語義**：live dream 目前另有 `atomize.skipped` backlog，所以整體 status 可能持續 `partial`；不要把 dream status 當驗收訊號，也不要為了讓 dream 回綠而移除 lint。

---

## Delivery（分支 / commit / PR 政策）

- 分支：由 `main` 開 `feature/177-stage2-key-rekey-untitled-cleanup`（R-12：head 必須 `feature/<slug>`）。實作前先 `git pull --ff-only`；每個寫檔步驟前確認 HEAD 在本分支（共用工作樹曾有被切走的 race）。
- Commit：conventional（zh-TW），如各 Task Step 5 所示（R-10）。
- PR title：`feat(memory): #177 rekey 遷移工具 + 固定清單 prune + janitor lint`（conventional）。
- PR body：zh-TW，必含 `Closes #177`（R-17 closing keyword），描述三個工具與 VERIFY corrections 依據；**不得有未勾選 checkbox**（R-11）——驗收清單請寫成敘述句或已勾 `- [x]`。
- 不碰 `.github/workflows/**` 與任何 `policy_version` 字面值（R-20）。
- 本 change 為純內部工具變更，`README.md`/`docs/**` 無需同步；若 Policy Check 對 R-18 出 WARN，屬預期（WARN 不擋 merge，可由維護者決定是否上 `policy-exempt:docs-sync`）。
- 完成後 push、開 PR，**不 merge**（等 CI 綠 + 對抗性驗證；merge 由使用者決定）。
- CI 驗證：`gh pr view <N> --json statusCheckRollup` 確認全 SUCCESS（gh 2.45.0 的 `pr checks` 無 `--json`）。

---

## Self-Review

- **Spec coverage**：Requirement「Project key rekey migration」→ Task 1/2；「Fixed-list prune mode」→ Task 3；「Janitor hygiene lint」→ Task 4/5。三 requirement 全覆蓋，scenario 與測試一一對應（dry-run/apply/conflict/unsafe-slug/dir-cleanup；listed-only/fail-closed/dry-run/互斥；flagged/clean/不自動改）。
- **VERIFY corrections 遵循**：plan 全文無任何「serialwrap AGENTS.md 當 corpus 全桶 prune」流程（已列為禁止事項）；13 筆清理走固定清單且為 ops、非 task。
- **Placeholder scan**：各 step 均含完整測試碼、實作碼、絕對路徑命令與預期輸出，無 TODO/TBD。
- **Type consistency**：`RekeyError`、`rekey_project(memory_root, *, old_key, new_slug, now, apply) -> dict`、manifest 欄位 `slice_id/from/to/path/target/status`、`_prune_listed(root, paths_file, *, now, apply) -> int`、`plan_lint(records) -> list[dict]`（`rule/record_id/path/project`）、`summary["lint"] = {"untitled": N, "raw_remote_key": M}` 全文一致。
- **最小 diff**：不改 orchestrator（summary passthrough 既有）、不改 `_prune_noise` 掃描模式輸出、`KnowledgeRecord` 以尾端預設欄位擴充避免破壞既有建構。
