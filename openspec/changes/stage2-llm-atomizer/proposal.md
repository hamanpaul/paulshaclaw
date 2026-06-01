## Why

Topic 3 (merged) populates `knowledge/` with deterministic 1:1 slices: one structural fragment becomes one knowledge slice. That is structurally correct but semantically coarse — a session that mixes a method, an incident, and a decision becomes one big slice instead of three atomic ones, and there are no semantic relations or precise project attribution. The whole point of the memory hub is to retrieve precise, reusable, related facts; coarse 1:1 slices undercut Topic 7 retrieval.

Topic 3 deliberately put the semantic work behind a single `Promoter` seam. This change (T3.2) replaces that seam with an LLM promoter that splits/merges a session's fragments into atomic, well-attributed, tagged, and related knowledge slices — using a local model, no API cost, fail-closed, and fully testable via an injected fake. It deliberately stays per-session; cross-session evolution lineage and the global entity graph remain Topic 5, and the skill-optimization loop (SkillOpt-style) remains a separate follow-up.

## What Changes

- Widen the Topic 3 `Promoter` interface from per-fragment to per-session (`promote(fragments, config) -> list[Slice]`); keep `IdentityPromoter` selectable and 1:1.
- Add `paulshaclaw.memory.atomizer.agent_exec` (configurable one-shot subprocess client + injectable fake), defaulting to `scripts/claude-gemma4` (local model, no API key).
- Add a seed atomization skill document `paulshaclaw/memory/atomizer/skills/atomize-knowledge-slice.md`, adapted from `obsidian-atomize` and distilled from real `atomized_from` examples in `~/notes/TechVault` and `WorkVault`.
- Add `prompt`, `llm_output`, and `llm_promoter` modules: assemble the prompt (skill + fragments + known projects), parse and schema-validate the agent's JSON, build and dual-validate slices.
- Add a `tags` slice frontmatter field and `relates_to` / `mentions` semantic edge types to `relations.jsonl`.
- Derive `slice_id` from content (session + body) so re-imports produce new slices; stale slices are left to the Topic 4 janitor.
- Cache raw LLM output per session+fragments-hash for crash-resume determinism; record `promoter`/`model`/`skill_hash` in the `promoted` ledger record.
- Migrate the paulshiabro `/agent` launcher to read the shared `agent_exec.command` config (config unification only).

## Capabilities

### New Capabilities

None. This change extends the existing `stage2-memory-governance` capability with the LLM semantic promotion contract.

### Modified Capabilities

- `stage2-memory-governance`: Add per-session LLM promoter, configurable agent-exec backend, seed atomization skill, LLM output contract and slice assembly, semantic relations and tags, frozen-output crash-resume determinism, and the redaction trust-boundary limitation.

## Impact

- Affected runtime code (new): `paulshaclaw/memory/atomizer/{agent_exec,prompt,llm_output,llm_promoter}.py`, `paulshaclaw/memory/atomizer/skills/atomize-knowledge-slice.md`.
- Affected runtime code (modified): `paulshaclaw/memory/atomizer/{promoter,pipeline,config,cli}.py`, `paulshaclaw/memory/atomizer/atomizer.yaml`, `paulshaclaw/memory/atomizer/slice_frontmatter.py` (add `build_from_proposal`).
- Affected layout (new write targets): `knowledge/<project>/<slice_id>.md` with `tags`; `runtime/cache/atomize/`; new `relates_to`/`mentions` edges in `runtime/ledger/relations.jsonl`.
- Cross-component: reads `~/.agents/config/projects.yaml` (known projects, same source as Topic 2 project_resolver); reuses Topic 3 `slice_frontmatter`/ledgers/flow-through; consumes Topic 8 redacted inbox fragments.
- Affected Stage 1: `/agent` launcher migrates to shared `agent_exec.command` config (config unification; any tmux-session breakage is a separate debug item).
- Affected tests: `llm_output`, `prompt`, `agent_exec`, `slice_frontmatter` (proposal), `llm_promoter`, per-session `promoter`, pipeline/E2E with fake client, opt-in live test, integration check with a stub agent command, `lifecycle.gate` conformance.
- Non-Goals: SkillOpt optimization loop (separate follow-up on `evolve`); cross-session evolution lineage and global entity graph (Topic 5); dream scheduler (Topic 5); new API/SDK client; tmux live-pane dispatch; output-side secret rescan (future `distilled_to_canonical`).
