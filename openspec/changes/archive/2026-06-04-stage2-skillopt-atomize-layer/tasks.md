## 1. Vendor the generic SkillOpt loop (mechanical copy + rename)

- [x] 1.1 Add `test_skillopt_loop.py` mirroring evolve's `test_skillopt.py` cases: `_mean_score`; accept path (fake optimizer returns better skill + fake score high → gate accepts, skill written, history backup, record accepted); reject no-improvement (candidate==baseline → unchanged); reject invalid skill (no frontmatter → unchanged); fail-closed (empty val raise, rollout raise aborts unchanged, optimizer raise aborts unchanged); failures take lowest N; record append only scores/counts; `now` injected into ts/history filename.
- [x] 1.2 Vendor `custom-skills/evolve/scripts/skillopt.py` → `paulshaclaw/memory/skillopt/loop.py` (copy verbatim; only adjust module docstring/imports as needed). Run 1.1 to PASS.
- [x] 1.3 Vendor `skillopt_optimizer_acp.py` → `paulshaclaw/memory/skillopt/optimizer_acp.py` and `codex_exec_acp_adapter.py` → `paulshaclaw/memory/skillopt/codex_exec_acp_adapter.py`; fix the `_ADAPTER` / `_REPO_ROOT` path constants for the new location.
- [x] 1.4 Add `paulshaclaw/memory/skillopt/__init__.py` exporting `optimize_skill`, `SkillOptError`, `make_acp_optimizer`.

## 2. Atomize rollout adapter

- [x] 2.1 Add `test_skillopt_rollout.py`: inject `FakeAgentClient`; assert the candidate `skill_text` is the one passed into `build_prompt`; assert output slices have expected structure; assert empty fragments raise/short-circuit cleanly.
- [x] 2.2 Implement `paulshaclaw/memory/skillopt/rollout.py::make_atomize_rollout(agent_client, known_projects, config) -> Callable[[skill_text, input], output]` reusing `LLMPromoter` + `build_prompt` from `paulshaclaw/memory/atomizer/` (no new splitter).

## 3. Scorer (structural + LLM-judge)

- [x] 3.1 Add `test_skillopt_scorer.py`: `structural_score` deterministic on fixtures for all four signals (granularity balance, concept-boundary clarity, one-concept-per-slice, relation presence); `make_hybrid_score` with a fake judge verifies `α·structural + (1-α)·judge` (α=0.4); judge exception surfaces so the loop fail-closes.
- [x] 3.2 Implement `paulshaclaw/memory/skillopt/scorer.py`: `structural_score(output, gold) -> float` (weighted four signals) and `make_hybrid_score(judge_client, *, alpha=0.4) -> Callable[[output, gold], float]`; judge prompt scores atomization quality only (no project assignment) and includes `gold.reference_slices` as rubric.

## 4. val_set builder (project-stratified from inbox)

- [x] 4.1 Add `test_skillopt_valset.py` with inbox fixtures: stratify by `project` frontmatter; deterministic 80/20 (same input → same split, via `sha256(id)` mod); per-project below min sample → all-to-train (log downgrade); `~/notes` missing domain → `reference_slices=[]`; PersonalVault excluded.
- [x] 4.2 Implement `paulshaclaw/memory/skillopt/valset.py::build_valset(*, inbox_root, reference_root, val_ratio=0.2, min_project_sample=2) -> {"train":[...],"val":[...]}` reading importer-produced inbox fragments and `~/notes` reference exemplars (semantic content only, ignore frontmatter).

## 5. CLI driver

- [x] 5.1 Add `test_skillopt_cli.py`: `psc memory skillopt run` wires build_valset + rollout + score + optimizer into `optimize_skill` (inject fakes); `--dry-run` computes baseline only (budget=0); empty inbox → friendly error mentioning "run importer first".
- [x] 5.2 Implement `paulshaclaw/memory/skillopt/cli.py`: argparse `run [--budget N] [--dry-run]`; load `~/.agents/config/skillopt.yaml` (judge command, alpha, val_ratio, min sample) with sane defaults; inject `now`; `record_path = ~/.agents/memory/runtime/ledger/skillopt.jsonl`; target skill `paulshaclaw/memory/atomizer/skills/atomize-knowledge-slice.md`.
- [x] 5.3 Register `skillopt` subcommand under the existing `psc memory` CLI entry point.

## 6. Docs, policy, integration gate

- [x] 6.1 Add `paulshaclaw/memory/skillopt/README.md` documenting: gate (worst case = unchanged), fail-closed, not wired into dream, judge scores atomization quality only (project owned by importer), `~/notes` reference-only.
- [x] 6.2 Run full suite `python3 -m unittest discover -s paulshaclaw/memory/tests` → all PASS; run repo policy/lint gate green.
- [x] 6.3 openspec-archive this change after merge.
