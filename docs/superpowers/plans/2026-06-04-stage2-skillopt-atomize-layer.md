# Stage 2 paulshaclaw SkillOpt Atomize Layer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `paulshaclaw/memory/skillopt/` — a gate-protected loop that refines the atomizer's `atomize-knowledge-slice.md` SKILL against real imported sessions, where a candidate skill is only accepted if it strictly beats the baseline on a project-stratified validation set (worst case = unchanged).

**Architecture:** Vendor (copy + rename) the `evolve` generic SkillOpt loop into the module, then supply atomize-specific hooks: a rollout that injects a candidate `skill_text` into the existing `LLMPromoter`, a hybrid scorer (deterministic structural for train ranking + LLM-judge for the val gate), and a val_set builder that reads importer-produced inbox fragments and stratifies by `project`. `~/notes` is read-only reference rubric. Runs as an offline CLI; not wired into dream in this change.

**Tech Stack:** Python 3 stdlib, `unittest`; reuse `paulshaclaw/memory/atomizer/` (`Fragment`, `splitter.split`, `prompt.build_prompt`, `LLMPromoter`, `agent_exec`) and `paulshaclaw/memory/importer/` outputs (inbox markdown with `project` frontmatter). Vendored source: `~/prj_pri/custom-skills/evolve/scripts/{skillopt.py,skillopt_optimizer_acp.py,codex_exec_acp_adapter.py}`.

---

## File Structure

- Create: `paulshaclaw/memory/skillopt/__init__.py` — exports `optimize_skill`, `SkillOptError`, `make_acp_optimizer`, `make_atomize_rollout`, `structural_score`, `make_hybrid_score`, `build_valset`.
- Create: `paulshaclaw/memory/skillopt/loop.py` — verbatim vendor of evolve `skillopt.py`.
- Create: `paulshaclaw/memory/skillopt/optimizer_acp.py` — vendor of evolve `skillopt_optimizer_acp.py` (path constants fixed).
- Create: `paulshaclaw/memory/skillopt/codex_exec_acp_adapter.py` — vendor of evolve adapter (optimizer dependency).
- Create: `paulshaclaw/memory/skillopt/rollout.py` — `make_atomize_rollout(...)`.
- Create: `paulshaclaw/memory/skillopt/scorer.py` — `structural_score`, `make_hybrid_score`.
- Create: `paulshaclaw/memory/skillopt/valset.py` — `build_valset(...)`, `load_inbox_items`, `load_reference_slices`.
- Create: `paulshaclaw/memory/skillopt/cli.py` — `psc memory skillopt run`.
- Create: `paulshaclaw/memory/skillopt/README.md`.
- Create tests under `paulshaclaw/memory/tests/`: `test_skillopt_loop.py`, `test_skillopt_rollout.py`, `test_skillopt_scorer.py`, `test_skillopt_valset.py`, `test_skillopt_cli.py`.

**Existing symbols to reuse (do NOT re-implement):**
- `paulshaclaw/memory/atomizer/splitter.py`: `@dataclass(frozen=True) Fragment(project, source_agent, source_session, source_artifact, captured_at, provenance: dict, fragment_index: int, body: str)`; `split(body: str, config: AtomizerConfig) -> list[str]`.
- `paulshaclaw/memory/atomizer/prompt.py`: `build_prompt(skill_text, fragments, known_projects) -> str`.
- `paulshaclaw/memory/atomizer/llm_promoter.py`: `LLMPromoter(agent_client, skill_text, known_projects, *, model="unknown").promote(fragments, config) -> list[Slice]`.
- `paulshaclaw/memory/atomizer/slice_frontmatter.py`: `@dataclass(frozen=True) Slice(slice_id, frontmatter: dict, body, title=None, relations: tuple=())`.
- `paulshaclaw/memory/atomizer/agent_exec.py`: `AgentClient`, `AgentExecClient(command, timeout=600)`, `FakeAgentClient`.
- `paulshaclaw/memory/atomizer/config.py`: `AtomizerConfig`, `load_config`.

---

## Task 1: Vendor the generic SkillOpt loop

**Files:**
- Create: `paulshaclaw/memory/skillopt/loop.py`, `optimizer_acp.py`, `codex_exec_acp_adapter.py`, `__init__.py`
- Test: `paulshaclaw/memory/tests/test_skillopt_loop.py`

- [x] **Step 1: Write the failing test (loop parity)**

Mirror evolve's `test_skillopt.py`. Create `paulshaclaw/memory/tests/test_skillopt_loop.py`:

```python
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from paulshaclaw.memory.skillopt.loop import optimize_skill, SkillOptError

VALID = "---\nname: s\n---\nbody\n"
BETTER = "---\nname: s\n---\nbetter body\n"

def _write(p: Path, text: str) -> Path:
    p.write_text(text, encoding="utf-8")
    return p

class TestOptimizeSkill(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.skill = _write(self.root / "atomize-knowledge-slice.md", VALID)
        self.train = [{"id": "t1", "input": "i", "gold": "g"}]
        self.val = [{"id": "v1", "input": "i", "gold": "g"}]

    def tearDown(self):
        self._tmp.cleanup()

    def _rollout(self, skill_text, _input):
        return skill_text  # identity: output == skill so score can key on it

    def test_accept_when_candidate_strictly_better(self):
        score = lambda out, gold: 1.0 if out == BETTER else 0.0
        res = optimize_skill(
            self.skill, rollout=self._rollout, score=score,
            train_set=self.train, val_set=self.val,
            optimizer=lambda text, failures: BETTER,
            budget=1, now="2026-06-04T00:00:00Z",
            record_path=self.root / "rec.jsonl",
        )
        self.assertTrue(res["accepted"])
        self.assertEqual(self.skill.read_text(encoding="utf-8"), BETTER)
        self.assertIn("history_backup", res)
        rec = json.loads((self.root / "rec.jsonl").read_text().splitlines()[-1])
        self.assertTrue(rec["accepted"])
        self.assertNotIn("input", rec)  # record holds scores/counts/decision only

    def test_reject_no_improvement_leaves_skill_unchanged(self):
        res = optimize_skill(
            self.skill, rollout=self._rollout, score=lambda o, g: 0.5,
            train_set=self.train, val_set=self.val,
            optimizer=lambda t, f: VALID, budget=1, now="2026-06-04T00:00:00Z",
        )
        self.assertFalse(res["accepted"])
        self.assertEqual(self.skill.read_text(encoding="utf-8"), VALID)

    def test_reject_invalid_candidate(self):
        res = optimize_skill(
            self.skill, rollout=self._rollout, score=lambda o, g: 1.0 if o == BETTER else 0.0,
            train_set=self.train, val_set=self.val,
            optimizer=lambda t, f: "no frontmatter", budget=1, now="2026-06-04T00:00:00Z",
        )
        self.assertFalse(res["accepted"])
        self.assertEqual(self.skill.read_text(encoding="utf-8"), VALID)

    def test_empty_val_raises(self):
        with self.assertRaises(SkillOptError):
            optimize_skill(
                self.skill, rollout=self._rollout, score=lambda o, g: 1.0,
                train_set=self.train, val_set=[],
                optimizer=lambda t, f: BETTER, budget=1, now="2026-06-04T00:00:00Z",
            )

    def test_rollout_exception_fails_closed_unchanged(self):
        def boom(skill_text, _input):
            raise RuntimeError("rollout boom")
        res = optimize_skill(
            self.skill, rollout=boom, score=lambda o, g: 1.0,
            train_set=self.train, val_set=self.val,
            optimizer=lambda t, f: BETTER, budget=1, now="2026-06-04T00:00:00Z",
        )
        self.assertEqual(res["reason"], "error")
        self.assertIsNone(res["baseline_score"])
        self.assertEqual(self.skill.read_text(encoding="utf-8"), VALID)

if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run the test to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_skillopt_loop -v`
Expected: FAIL with `ModuleNotFoundError: paulshaclaw.memory.skillopt.loop`.

- [x] **Step 3: Vendor `loop.py` verbatim**

Copy `~/prj_pri/custom-skills/evolve/scripts/skillopt.py` to `paulshaclaw/memory/skillopt/loop.py` unchanged:

```bash
cp ~/prj_pri/custom-skills/evolve/scripts/skillopt.py \
   ~/prj_pri/paulshaclaw/paulshaclaw/memory/skillopt/loop.py
```

The file's public API is `optimize_skill`, `SkillOptError`, `_mean_score`, `_is_valid_skill` — keep all. No edits needed (it is stdlib-only and self-contained).

- [x] **Step 4: Vendor the optimizer + adapter, fix path constants**

```bash
cp ~/prj_pri/custom-skills/evolve/scripts/skillopt_optimizer_acp.py \
   ~/prj_pri/paulshaclaw/paulshaclaw/memory/skillopt/optimizer_acp.py
cp ~/prj_pri/custom-skills/evolve/scripts/codex_exec_acp_adapter.py \
   ~/prj_pri/paulshaclaw/paulshaclaw/memory/skillopt/codex_exec_acp_adapter.py
```

In `optimizer_acp.py`, the constants near the top read:
```python
_ADAPTER = Path(__file__).resolve().parent / "codex_exec_acp_adapter.py"
_REPO_ROOT = Path(__file__).resolve().parents[2]
```
`_ADAPTER` is correct (adapter sits beside it). Verify `_REPO_ROOT` resolves to the paulshaclaw repo root from the new location `paulshaclaw/memory/skillopt/optimizer_acp.py` → `parents[2]` = repo root; if the package nesting differs, set it to the repo root that contains `scripts/`. Keep `make_acp_optimizer` and `_default_runner` otherwise unchanged.

- [x] **Step 5: Create `__init__.py`**

```python
from .loop import optimize_skill, SkillOptError
from .optimizer_acp import make_acp_optimizer

__all__ = ["optimize_skill", "SkillOptError", "make_acp_optimizer"]
```

- [x] **Step 6: Run the test to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_skillopt_loop -v`
Expected: PASS (all 5 cases).

- [ ] **Step 7: Commit**

```bash
git add paulshaclaw/memory/skillopt/{loop,optimizer_acp,codex_exec_acp_adapter,__init__}.py \
        paulshaclaw/memory/tests/test_skillopt_loop.py
git commit -m "feat(skillopt): vendor generic SkillOpt loop into paulshaclaw"
```

---

## Task 2: Atomize rollout adapter

**Files:**
- Create: `paulshaclaw/memory/skillopt/rollout.py`
- Test: `paulshaclaw/memory/tests/test_skillopt_rollout.py`

- [x] **Step 1: Write the failing test**

```python
import unittest
from paulshaclaw.memory.skillopt.rollout import make_atomize_rollout
from paulshaclaw.memory.atomizer.splitter import Fragment

class RecordingAgent:
    """Captures the prompt so we can assert the candidate skill_text was used."""
    def __init__(self):
        self.last_prompt = None
    def run(self, prompt):
        self.last_prompt = prompt
        # minimal valid LLM output: one slice JSON the parser accepts
        return '[{"title": "T", "body": "B", "project": "paulshaclaw", "source_fragments": [0]}]'

def _fragment(i=0):
    return Fragment(
        project="paulshaclaw", source_agent="claude", source_session="s1",
        source_artifact="sessions", captured_at="2026-06-04T00:00:00Z",
        provenance={}, fragment_index=i, body="some session body",
    )

class TestAtomizeRollout(unittest.TestCase):
    def test_candidate_skill_text_is_injected_into_prompt(self):
        agent = RecordingAgent()
        rollout = make_atomize_rollout(agent, known_projects=["paulshaclaw"])
        candidate = "---\nname: atomize\n---\nCANDIDATE-MARKER principles\n"
        out = rollout(candidate, [_fragment(0)])
        self.assertIn("CANDIDATE-MARKER", agent.last_prompt)
        self.assertTrue(len(out) >= 1)  # produced at least one slice

    def test_empty_fragments_returns_empty(self):
        rollout = make_atomize_rollout(RecordingAgent(), known_projects=["paulshaclaw"])
        self.assertEqual(rollout("---\nx: y\n---\nz\n", []), [])

if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_skillopt_rollout -v`
Expected: FAIL (`ModuleNotFoundError` / `make_atomize_rollout` undefined).

- [x] **Step 3: Implement `rollout.py`**

```python
from __future__ import annotations
from typing import Any, Callable

from paulshaclaw.memory.atomizer.config import AtomizerConfig, load_config
from paulshaclaw.memory.atomizer.llm_promoter import LLMPromoter
from paulshaclaw.memory.atomizer.splitter import Fragment


def make_atomize_rollout(
    agent_client: Any,
    known_projects: list[str],
    *,
    config: AtomizerConfig | None = None,
) -> Callable[[str, list[Fragment]], list]:
    """Return rollout(skill_text, fragments) -> list[Slice].

    The candidate skill_text is injected into LLMPromoter so each rollout
    evaluates the candidate skill (reuses the existing atomizer; no fork).
    """
    cfg = config or load_config()

    def rollout(skill_text: str, fragments: list[Fragment]) -> list:
        if not fragments:
            return []
        promoter = LLMPromoter(agent_client, skill_text, list(known_projects))
        return promoter.promote(fragments, cfg)

    return rollout
```

If `load_config()` requires arguments in this tree, pass the atomizer's default config path; the test constructs `config` is None → ensure `load_config` has a no-arg/default path or inject a config in the test instead. (If `load_config` is not no-arg, change the test to pass `config=load_config(<default path>)` and keep the signature.)

- [x] **Step 4: Run to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_skillopt_rollout -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/skillopt/rollout.py paulshaclaw/memory/tests/test_skillopt_rollout.py
git commit -m "feat(skillopt): atomize rollout injecting candidate skill_text"
```

---

## Task 3: Scorer (structural + LLM-judge)

**Files:**
- Create: `paulshaclaw/memory/skillopt/scorer.py`
- Test: `paulshaclaw/memory/tests/test_skillopt_scorer.py`

Output of rollout = `list[Slice]`. Gold = `{"project": str, "reference_slices": [{"title","body","tags"}, ...]}`.

- [x] **Step 1: Write the failing test**

```python
import unittest
from paulshaclaw.memory.skillopt.scorer import structural_score, make_hybrid_score
from paulshaclaw.memory.atomizer.slice_frontmatter import Slice

def _slice(title, body, relations=()):
    return Slice(slice_id="x", frontmatter={}, body=body, title=title, relations=relations)

GOLD = {"project": "p", "reference_slices": [
    {"title": "WSP_EN sync", "body": "wps_state sync issue", "tags": ["debug"]},
    {"title": "hostapd reload", "body": "vendor adapter reload", "tags": ["debug"]},
]}

class TestStructuralScore(unittest.TestCase):
    def test_score_is_between_0_and_1(self):
        out = [_slice("WSP_EN sync", "wps_state sync issue", relations=({"target": "y"},)),
               _slice("hostapd reload", "vendor adapter reload")]
        s = structural_score(out, GOLD)
        self.assertGreaterEqual(s, 0.0)
        self.assertLessEqual(s, 1.0)

    def test_better_granularity_scores_higher(self):
        good = [_slice("WSP_EN sync", "wps_state sync issue"),
                _slice("hostapd reload", "vendor adapter reload")]
        lumped = [_slice("everything", "wps_state sync issue vendor adapter reload")]
        self.assertGreater(structural_score(good, GOLD), structural_score(lumped, GOLD))

    def test_deterministic(self):
        out = [_slice("a", "b")]
        self.assertEqual(structural_score(out, GOLD), structural_score(out, GOLD))

class TestHybridScore(unittest.TestCase):
    def test_alpha_weighting(self):
        class FakeJudge:
            def run(self, prompt):
                return "0.8"   # judge returns 0.8
        out = [_slice("WSP_EN sync", "wps_state sync issue"),
               _slice("hostapd reload", "vendor adapter reload")]
        score = make_hybrid_score(FakeJudge(), alpha=0.4)
        struct = structural_score(out, GOLD)
        expected = 0.4 * struct + 0.6 * 0.8
        self.assertAlmostEqual(score(out, GOLD), expected, places=6)

    def test_judge_exception_propagates(self):
        class BoomJudge:
            def run(self, prompt):
                raise RuntimeError("judge down")
        score = make_hybrid_score(BoomJudge(), alpha=0.4)
        with self.assertRaises(Exception):
            score([_slice("a", "b")], GOLD)

if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_skillopt_scorer -v`
Expected: FAIL (module/functions undefined).

- [x] **Step 3: Implement `scorer.py`**

```python
from __future__ import annotations
import re
from typing import Any, Callable

_WORD = re.compile(r"[0-9a-z_]+", re.IGNORECASE)

def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD.findall(text or "")}

def _granularity_balance(out: list, gold: dict) -> float:
    del gold
    count = len(out)
    if count == 0:
        return 0.0
    if 2 <= count <= 6:
        count_score = 1.0
    elif count == 1:
        count_score = 0.5
    else:
        count_score = max(0.0, 1.0 - ((count - 6) / 6.0))
    mean_body_length = sum(len((getattr(s, "body", "") or "").strip()) for s in out) / count
    if mean_body_length <= 0:
        length_score = 0.0
    elif mean_body_length < 80.0:
        length_score = mean_body_length / 80.0
    elif mean_body_length > 1600.0:
        length_score = 1600.0 / mean_body_length
    else:
        length_score = 1.0
    return 0.6 * count_score + 0.4 * length_score

def _concept_boundary_clarity(out: list, gold: dict) -> float:
    del gold
    if not out:
        return 0.0
    token_sets = [_tokens((getattr(s, "title", None) or "") + " " + (getattr(s, "body", "") or "")) for s in out]
    if len(token_sets) == 1:
        return 0.5 if token_sets[0] else 0.0
    overlaps = []
    for i, left in enumerate(token_sets):
        for right in token_sets[i + 1:]:
            union = left | right
            overlaps.append(1.0 if not union else len(left & right) / len(union))
    return 1.0 if not overlaps else 1.0 - (sum(overlaps) / len(overlaps))

def _one_concept_per_slice(out: list, gold: dict) -> float:
    del gold
    if not out:
        return 0.0
    oks = 0
    for s in out:
        title = (getattr(s, "title", None) or "").strip()
        body = (getattr(s, "body", "") or "").strip()
        if title and body and len(body) <= 1800:
            oks += 1
    return oks / len(out)

def _relation_presence(out: list, gold: dict) -> float:
    if not out:
        return 0.0
    with_rel = sum(1 for s in out if getattr(s, "relations", ()) )
    return with_rel / len(out)

_WEIGHTS = {"granularity": 0.35, "boundary": 0.35, "one_concept": 0.20, "relation": 0.10}

def structural_score(output: list, gold: dict) -> float:
    parts = {
        "granularity": _granularity_balance(output, gold),
        "boundary": _concept_boundary_clarity(output, gold),
        "one_concept": _one_concept_per_slice(output, gold),
        "relation": _relation_presence(output, gold),
    }
    return sum(_WEIGHTS[k] * parts[k] for k in _WEIGHTS)


_JUDGE_PROMPT = """You are scoring how well an atomizer split a session into atomic knowledge slices.
Judge ONLY atomization quality, NOT project assignment. Consider: slice granularity (sub-features
sized right, not too coarse/fine), concept boundaries (one clear concept each), one-concept-per-slice,
and relation soundness (no orphan islands).

Reference examples of good atomization for this domain (rubric, not a 1:1 target):
{reference}

Candidate slices to score:
{candidate}

Return ONLY a single float between 0 and 1 (1 = excellent), no other text.
"""

def _fmt_slices(slices: list) -> str:
    return "\n".join(
        f"- {getattr(s,'title',None) or '(untitled)'}: {(getattr(s,'body','') or '')[:300]}"
        for s in slices
    ) or "(none)"

def _fmt_reference(gold: dict) -> str:
    refs = gold.get("reference_slices", [])
    return "\n".join(f"- {r.get('title','')}: {str(r.get('body',''))[:300]}" for r in refs) or "(none)"

def _parse_float(raw: str) -> float:
    m = re.search(r"-?\d+(?:\.\d+)?", raw or "")
    if not m:
        raise ValueError(f"judge returned no float: {raw!r}")
    return max(0.0, min(1.0, float(m.group(0))))

def make_hybrid_score(judge_client: Any, *, alpha: float = 0.4) -> Callable[[list, dict], float]:
    def score(output: list, gold: dict) -> float:
        struct = structural_score(output, gold)
        prompt = _JUDGE_PROMPT.format(reference=_fmt_reference(gold), candidate=_fmt_slices(output))
        judge = _parse_float(judge_client.run(prompt))
        return alpha * struct + (1.0 - alpha) * judge
    return score
```

- [x] **Step 4: Run to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_skillopt_scorer -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/skillopt/scorer.py paulshaclaw/memory/tests/test_skillopt_scorer.py
git commit -m "feat(skillopt): structural + LLM-judge hybrid scorer"
```

---

## Task 4: val_set builder (project-stratified from inbox)

**Files:**
- Create: `paulshaclaw/memory/skillopt/valset.py`
- Test: `paulshaclaw/memory/tests/test_skillopt_valset.py`

- [x] **Step 1: Write the failing test**

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from paulshaclaw.memory.skillopt.valset import build_valset

INBOX_DOC = """---
project: {project}
source_agent: claude
source_session: {sid}
captured_at: 2026-06-04T00:00:00Z
---
{body}
"""

def _write_inbox(root: Path, project: str, sid: str, body: str):
    d = root / "inbox" / "sessions" / "claude" / "2026-06-04"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{sid}.md").write_text(INBOX_DOC.format(project=project, sid=sid, body=body), encoding="utf-8")

class TestBuildValset(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.refs = self.root / "notes"   # empty reference vault by default
        self.refs.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_deterministic_split(self):
        for i in range(10):
            _write_inbox(self.root / "mem", "paulshaclaw", f"s{i}", f"body number {i} " * 50)
        a = build_valset(inbox_root=self.root / "mem" / "inbox", reference_root=self.refs)
        b = build_valset(inbox_root=self.root / "mem" / "inbox", reference_root=self.refs)
        self.assertEqual([x["id"] for x in a["val"]], [x["id"] for x in b["val"]])
        self.assertEqual([x["id"] for x in a["train"]], [x["id"] for x in b["train"]])

    def test_sparse_project_all_to_train(self):
        _write_inbox(self.root / "mem", "wifi8-nvram", "w1", "tiny body " * 50)  # 1 item < min
        for i in range(10):
            _write_inbox(self.root / "mem", "paulshaclaw", f"s{i}", f"b {i} " * 50)
        ds = build_valset(inbox_root=self.root / "mem" / "inbox", reference_root=self.refs,
                          min_project_sample=2)
        val_projects = {x["gold"]["project"] for x in ds["val"]}
        self.assertNotIn("wifi8-nvram", val_projects)

    def test_missing_reference_domain_gives_empty_reference(self):
        for i in range(4):
            _write_inbox(self.root / "mem", "paulshaclaw", f"s{i}", f"b {i} " * 50)
        ds = build_valset(inbox_root=self.root / "mem" / "inbox", reference_root=self.refs)
        for item in ds["train"] + ds["val"]:
            self.assertEqual(item["gold"]["reference_slices"], [])

    def test_empty_inbox_yields_empty_sets(self):
        ds = build_valset(inbox_root=self.root / "mem" / "inbox", reference_root=self.refs)
        self.assertEqual(ds["train"], [])
        self.assertEqual(ds["val"], [])

if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_skillopt_valset -v`
Expected: FAIL (module undefined).

- [x] **Step 3: Implement `valset.py`**

Reuse the atomizer's frontmatter parsing and splitter — do NOT write a new splitter.

```python
from __future__ import annotations
import hashlib
from pathlib import Path
from typing import Any

from paulshaclaw.memory.atomizer.config import load_config
from paulshaclaw.memory.atomizer.splitter import Fragment, split

_PERSONAL = "PersonalVault"

def _parse_frontmatter(text: str) -> tuple[dict, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    fm: dict[str, Any] = {}
    i = 1
    while i < len(lines) and lines[i].strip() != "---":
        if ":" in lines[i]:
            k, _, v = lines[i].partition(":")
            fm[k.strip()] = v.strip()
        i += 1
    body = "\n".join(lines[i + 1:]) if i < len(lines) else ""
    return fm, body

def load_inbox_items(inbox_root: Path) -> list[dict]:
    """Read importer inbox markdown → val items (input = list[Fragment])."""
    cfg = load_config()
    items: list[dict] = []
    if not inbox_root.exists():
        return items
    for path in sorted(inbox_root.rglob("*.md")):
        if "_slices" in path.parts:
            continue
        fm, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
        project = fm.get("project")
        sid = fm.get("source_session")
        if not project or not sid:
            continue
        bodies = split(body, cfg)
        fragments = [
            Fragment(
                project=str(project), source_agent=str(fm.get("source_agent", "unknown")),
                source_session=str(sid), source_artifact=str(fm.get("source_artifact", "sessions")),
                captured_at=str(fm.get("captured_at", "")), provenance={},
                fragment_index=idx, body=chunk,
            )
            for idx, chunk in enumerate(bodies)
        ]
        if not fragments:
            continue
        items.append({
            "id": f"{sid}#0",
            "project": str(project),
            "input": fragments,
        })
    return items

def load_reference_slices(reference_root: Path) -> list[dict]:
    """Read ~/notes atomized child notes → semantic content only (frontmatter ignored)."""
    refs: list[dict] = []
    if not reference_root.exists():
        return refs
    for path in sorted(reference_root.rglob("*.md")):
        if _PERSONAL in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        fm, body = _parse_frontmatter(text)
        if "atomized_from" not in fm:
            continue
        refs.append({
            "title": fm.get("title", path.stem).strip('"'),
            "body": body.strip()[:1000],
            "tags": [],
            "_path": str(path),
        })
    return refs

def _domain_reference(item: dict, references: list[dict]) -> list[dict]:
    """Approximate domain match by token overlap (reference rubric only; precision not required)."""
    import re
    def toks(s: str) -> set:
        return {w.lower() for w in re.findall(r"[0-9a-z_]+", s, re.IGNORECASE)}
    body_tokens = set().union(*[toks(f.body) for f in item["input"]]) if item["input"] else set()
    scored = []
    for r in references:
        overlap = len(toks(r["title"] + " " + r["body"]) & body_tokens)
        if overlap:
            scored.append((overlap, r))
    scored.sort(key=lambda x: (-x[0], x[1]["_path"]))
    return [{"title": r["title"], "body": r["body"], "tags": r["tags"]} for _, r in scored[:5]]

def build_valset(*, inbox_root: Path, reference_root: Path,
                 val_ratio: float = 0.2, min_project_sample: int = 2) -> dict:
    inbox_root = Path(inbox_root)
    reference_root = Path(reference_root)
    references = load_reference_slices(reference_root)
    items = load_inbox_items(inbox_root)

    by_project: dict[str, list[dict]] = {}
    for it in items:
        by_project.setdefault(it["project"], []).append(it)

    train: list[dict] = []
    val: list[dict] = []
    bucket = max(1, int(round(1 / val_ratio))) if val_ratio > 0 else 0
    for project, project_items in sorted(by_project.items()):
        project_items.sort(key=lambda it: it["id"])
        for it in project_items:
            gold = {"project": project, "reference_slices": _domain_reference(it, references)}
            record = {"id": it["id"], "input": it["input"], "gold": gold}
            if len(project_items) < min_project_sample or bucket == 0:
                train.append(record)
                continue
            h = int(hashlib.sha256(it["id"].encode("utf-8")).hexdigest(), 16)
            (val if h % bucket == 0 else train).append(record)
    return {"train": train, "val": val}
```

- [x] **Step 4: Run to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_skillopt_valset -v`
Expected: PASS. (If `load_config()` is not no-arg in this tree, give it the atomizer default config path.)

- [ ] **Step 5: Commit**

```bash
git add paulshaclaw/memory/skillopt/valset.py paulshaclaw/memory/tests/test_skillopt_valset.py
git commit -m "feat(skillopt): project-stratified val_set builder from inbox"
```

---

## Task 5: CLI driver

**Files:**
- Create: `paulshaclaw/memory/skillopt/cli.py`
- Test: `paulshaclaw/memory/tests/test_skillopt_cli.py`
- Modify: the existing `psc memory` CLI entry to register the `skillopt` subcommand.

- [x] **Step 1: Write the failing test**

```python
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from paulshaclaw.memory.skillopt import cli

class TestSkilloptCli(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty_inbox_friendly_error(self):
        (self.root / "inbox").mkdir(parents=True)
        rc = cli.run_optimize(
            inbox_root=self.root / "inbox", reference_root=self.root / "notes",
            skill_path=self.root / "skill.md", record_path=self.root / "rec.jsonl",
            now="2026-06-04T00:00:00Z",
            make_rollout=lambda: (lambda s, i: []),
            make_score=lambda: (lambda o, g: 0.0),
            make_optimizer=lambda: (lambda t, f: t),
            budget=1,
        )
        self.assertNotEqual(rc, 0)  # non-zero, friendly "run importer first"

    def test_dry_run_computes_baseline_only(self):
        # one inbox doc, valid skill; dry-run never calls optimizer
        (self.root / "skill.md").write_text("---\nn: a\n---\nbody\n", encoding="utf-8")
        d = self.root / "inbox" / "sessions" / "claude" / "2026-06-04"
        d.mkdir(parents=True)
        (d / "s0.md").write_text(
            "---\nproject: p\nsource_agent: claude\nsource_session: s0\n---\n" + ("word " * 80),
            encoding="utf-8")
        called = {"opt": 0}
        def make_opt():
            def opt(t, f):
                called["opt"] += 1
                return t
            return opt
        rc = cli.run_optimize(
            inbox_root=self.root / "inbox", reference_root=self.root / "notes",
            skill_path=self.root / "skill.md", record_path=self.root / "rec.jsonl",
            now="2026-06-04T00:00:00Z",
            make_rollout=lambda: (lambda s, i: []),
            make_score=lambda: (lambda o, g: 0.5),
            make_optimizer=make_opt, budget=1, dry_run=True,
        )
        self.assertEqual(rc, 0)
        self.assertEqual(called["opt"], 0)  # optimizer never called on dry-run

if __name__ == "__main__":
    unittest.main()
```

- [x] **Step 2: Run to verify it fails**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_skillopt_cli -v`
Expected: FAIL.

- [x] **Step 3: Implement `cli.py`**

```python
from __future__ import annotations
import argparse
import datetime as _dt
from pathlib import Path
from typing import Callable

from .loop import optimize_skill, SkillOptError
from .valset import build_valset

DEFAULT_SKILL = "paulshaclaw/memory/atomizer/skills/atomize-knowledge-slice.md"

def run_optimize(*, inbox_root: Path, reference_root: Path, skill_path: Path,
                 record_path: Path, now: str,
                 make_rollout: Callable[[], Callable],
                 make_score: Callable[[], Callable],
                 make_optimizer: Callable[[], Callable],
                 budget: int = 1, dry_run: bool = False) -> int:
    ds = build_valset(inbox_root=Path(inbox_root), reference_root=Path(reference_root))
    if not ds["val"]:
        print("skillopt: no validation items. Run the importer first to populate inbox "
              "(~/.agents/memory/inbox).")
        return 2
    effective_budget = 0 if dry_run else budget
    try:
        result = optimize_skill(
            Path(skill_path),
            rollout=make_rollout(), score=make_score(),
            train_set=ds["train"], val_set=ds["val"],
            optimizer=make_optimizer(), budget=effective_budget,
            now=now, record_path=Path(record_path),
        )
    except SkillOptError as exc:
        print(f"skillopt: cannot optimize: {exc}")
        return 2
    print(f"skillopt: accepted={result['accepted']} baseline={result['baseline_score']} "
          f"candidate={result['candidate_score']} improvement={result['improvement']} "
          f"reason={result['reason']}")
    return 0

def _memory_root() -> Path:
    return Path.home() / ".agents" / "memory"

def _build_default_hooks(config):
    from paulshaclaw.memory.atomizer.agent_exec import AgentExecClient
    from paulshaclaw.memory.atomizer.config import load_config
    from .rollout import make_atomize_rollout
    from .scorer import make_hybrid_score
    from .optimizer_acp import make_acp_optimizer
    atom_cfg = load_config()
    gemma = AgentExecClient(tuple(atom_cfg.agent_exec_command), timeout=atom_cfg.agent_exec_timeout)
    judge = AgentExecClient(tuple(config["judge_command"]), timeout=config.get("judge_timeout", 600))
    known = list(getattr(atom_cfg, "known_projects", []) or [])
    return (
        lambda: make_atomize_rollout(gemma, known, config=atom_cfg),
        lambda: make_hybrid_score(judge, alpha=config.get("alpha", 0.4)),
        lambda: make_acp_optimizer(),
    )

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="psc memory skillopt")
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run", help="optimize the atomize skill")
    run.add_argument("--budget", type=int, default=1)
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--skill-path", default=DEFAULT_SKILL)
    run.add_argument("--reference-root", default=str(Path.home() / "notes"))
    args = parser.parse_args(argv)

    mem = _memory_root()
    now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # config defaults; load ~/.agents/config/skillopt.yaml when present.
    config = {"judge_command": ["scripts/claude-gemma4"], "alpha": 0.4}
    mk_roll, mk_score, mk_opt = _build_default_hooks(config)
    return run_optimize(
        inbox_root=mem / "inbox", reference_root=Path(args.reference_root),
        skill_path=Path(args.skill_path), record_path=mem / "runtime" / "ledger" / "skillopt.jsonl",
        now=now, make_rollout=mk_roll, make_score=mk_score, make_optimizer=mk_opt,
        budget=args.budget, dry_run=args.dry_run,
    )

if __name__ == "__main__":
    raise SystemExit(main())
```

Note: `now` is computed at the CLI boundary only (so the core loop stays deterministic via injection). Tests pass `now` explicitly.

- [x] **Step 4: Run to verify it passes**

Run: `python3 -m unittest paulshaclaw.memory.tests.test_skillopt_cli -v`
Expected: PASS.

- [x] **Step 5: Register the subcommand on the `psc memory` entry**

Find the existing `psc memory` dispatcher (grep for the `memory` subcommands, e.g. `importer`, `atomizer`, `dream`, `moc` registrations) and add a `skillopt` branch that calls `paulshaclaw.memory.skillopt.cli.main(remaining_argv)`. Mirror exactly how `moc`/`dream` are wired.

Run: `python3 -m paulshaclaw... memory skillopt run --dry-run` (using the real entry) and confirm it reaches the friendly empty-inbox message on a machine with no inbox.

- [ ] **Step 6: Commit**

```bash
git add paulshaclaw/memory/skillopt/cli.py paulshaclaw/memory/tests/test_skillopt_cli.py <entry-file>
git commit -m "feat(skillopt): CLI driver and psc memory skillopt subcommand"
```

---

## Task 6: Docs, full suite, policy gate

**Files:**
- Create: `paulshaclaw/memory/skillopt/README.md`

- [x] **Step 1: Write `README.md`**

Document: the validation gate (worst case = unchanged), fail-closed on any model error, the module is offline and NOT wired into dream in this change, the LLM judge scores atomization quality only (project ownership belongs to the importer's `project_resolver`), and `~/notes` is read-only reference rubric (never gold, never written, PersonalVault excluded). Note model roles: rollout=gemma4, optimizer=codex ACP, judge=configurable agent.

- [x] **Step 2: Run the full memory suite**

Run: `python3 -m unittest discover -s paulshaclaw/memory/tests`
Expected: all PASS (including the 5 new test modules).

- [x] **Step 3: Run the repo policy / lint gate**

Run the repo's policy check and frontmatter lint exactly as other Stage 2 changes do (see `paulshaclaw/memory/lint/` and the CI policy script). Expected: green. Branch name `feature/stage2-skillopt-atomize-layer` satisfies R-12 (no dots).

- [ ] **Step 4: Commit docs**

```bash
git add paulshaclaw/memory/skillopt/README.md
git commit -m "docs(skillopt): module README (gate, fail-closed, judge scope)"
```

- [x] **Step 5: openspec-archive after merge**

After the PR merges, archive the change: move `openspec/changes/stage2-skillopt-atomize-layer/` into `openspec/changes/archive/` per the repo's archive convention (mirror the most recent archived stage2 change).

---

## Self-Review notes (for the implementer)
- The vendored `loop.py` MUST stay byte-faithful to evolve except imports/docstring — `test_skillopt_loop.py` is the parity guard.
- Determinism: never call wall-clock inside the loop, scorer, valset, or rollout. `now` enters only at `cli.main`. Split keys off `sha256(id)`.
- Zero duplication: rollout calls the real `LLMPromoter`; valset uses the real `splitter.split`; project comes from inbox frontmatter (importer). The judge never sees a project-assignment task.
- If `load_config()` requires an explicit path in this tree, thread the atomizer default path through `make_atomize_rollout(config=...)` and `valset.load_inbox_items` rather than changing behavior.
