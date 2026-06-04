## Why

The atomizer (T3/T3.2) drives slice quality off a single hand-written `atomize-knowledge-slice.md` SKILL. There is no mechanism to measure or improve that skill against real data, so atomization quality is frozen at whatever the author guessed. The `evolve` generic SkillOpt capability (custom-skills, PR #5) now provides a gate-protected `optimize_skill` loop that treats any `SKILL.md` as a trainable artifact. This change vendors that loop into paulshaclaw and wires the atomize-specific hooks (rollout / scorer / val_set) so the atomize skill can self-refine against real imported sessions — with a strict validation gate guaranteeing the skill can never get worse (worst case = unchanged).

## What Changes

- Add `paulshaclaw/memory/skillopt/` code module (NOT a skill): vendor (copy + rename) the evolve generic loop (`loop.py`, `optimizer_acp.py`, `codex_exec_acp_adapter.py`) with behavior unchanged.
- Add atomize rollout adapter: inject a candidate `skill_text` into the existing `build_prompt` + `LLMPromoter` (gemma4 via `agent_exec`) → slices.
- Add hybrid scorer: deterministic structural score for train-failure ranking; structural + LLM-judge for the val gate. Judge evaluates atomization quality only (granularity, concept boundary, one-concept-per-slice, relations).
- Add val_set builder: read importer-produced inbox fragments, stratify by `project` (from inbox frontmatter), deterministic 80/20 train/val split; pair each item with `~/notes` reference exemplars as judge rubric (reference only).
- Add `psc memory skillopt run` CLI driver calling `optimize_skill` on `atomizer/skills/atomize-knowledge-slice.md`, recording to `runtime/ledger/skillopt.jsonl`.
- Reuse importer (session scan + project resolution incl. cross-folder-same-project) and atomizer (rollout) with zero duplication; SkillOpt only reads their outputs and injects skill_text.
- Defer: wiring into dream / `self_evolve_cycle`, multi-epoch / larger budget, pairwise judge, knowledge-tier gold — all Non-Goals.

## Capabilities

### New Capabilities

None. Extends the existing `stage2-memory-governance` capability with skill-optimization requirements for the atomizer.

### Modified Capabilities

- `stage2-memory-governance`: Add gate-protected atomize-skill optimization (vendored loop, atomize rollout, hybrid scorer, project-stratified val_set from inbox, reference-only `~/notes`, offline CLI not wired into dream).

## Impact

- Affected runtime code (new): `paulshaclaw/memory/skillopt/{__init__,loop,optimizer_acp,codex_exec_acp_adapter,rollout,scorer,valset,cli}.py`.
- Affected artifact (optimized in place, single writer): `paulshaclaw/memory/atomizer/skills/atomize-knowledge-slice.md` (+ `skillopt-history/` backups).
- Affected config: optional `~/.agents/config/skillopt.yaml` (judge model command, α weight, val_ratio, min project sample); reuses existing `projects.yaml`.
- Affected ledger: new append-only `~/.agents/memory/runtime/ledger/skillopt.jsonl` (scores/counts/decision only).
- Affected tests: new `paulshaclaw/memory/tests/test_skillopt_{loop,rollout,scorer,valset,cli}.py`.
- Dependencies: none new (reuses `agent_exec`, atomizer, importer, stdlib).
- External system: codex ACP (optimizer) and gemma4 (rollout) via existing `agent_exec` / vendored adapter; all injectable → deterministic tests use fakes.
- Reference only: `~/notes` (Obsidian vault) read read-only as judge rubric; never gold, never written.
- Non-Goals: dream/`self_evolve_cycle` wiring, multi-epoch, pairwise judge, knowledge-tier gold, project assignment by judge (importer owns it).
