# Design — Stage 2 Topic 3.2 LLM Semantic Atomizer

> Canonical design: `docs/superpowers/specs/2026-06-02-stage2-llm-atomizer-design.md`. This file captures the change-scoped architecture and key decisions.

## Context

- Topic 3 (merged) ships `paulshaclaw/memory/atomizer/` with a `Promoter` seam, `IdentityPromoter` (1:1), `slice_frontmatter`, a two-pass `pipeline`, and `processing`/`relations` ledgers.
- Fragments in `inbox/_slices/` are already redacted at the Topic 8 `raw_to_distilled` boundary.
- Stage 3 (`paulshaclaw/lifecycle/schema.py`) owns the frontmatter schema and ignores extra fields, so Topic-4 and `tags` fields coexist on a Stage-3-valid slice.
- A local model is served via vLLM; `scripts/claude-gemma4` already wraps an agent against it.

## Key Decisions

1. **Replace only the Promoter seam.** Splitter, ledgers, flow-through, and pipeline structure are unchanged. The seam widens from per-fragment to per-session to allow cross-fragment merge.
2. **Configurable agent-exec, not an SDK.** The LLM is reached by a one-shot subprocess (`agent_exec.command`, default `scripts/claude-gemma4`) — no API key, no per-token cost. The same command config is shared with the `/agent` launcher.
3. **Behavior lives in a skill document.** `skills/atomize-knowledge-slice.md` (seeded from `obsidian-atomize` + distilled from TechVault/WorkVault `atomized_from` examples) holds the atomization rules and the mandatory output contract. `prompt.py` only assembles; this makes the skill the single artifact a future SkillOpt loop refines.
4. **Strict JSON contract + fail-closed.** The agent returns a JSON array of slice proposals; parsing/schema failure, validation failure, or agent failure leaves the session in `split` (all-or-nothing per session) for next-run retry.
5. **Content-derived slice_id; stale handled by Topic 4.** `slice_id = sl-<sha256(agent|session|sha256(body))[:16]>`. Re-import with changed content yields new slices; the old ones become stale and are decayed by the Topic 4 janitor.
6. **Frozen output for crash-resume.** Raw agent output is cached per `session_key + fragments_hash`; resume reuses it so the non-deterministic step is idempotent and not re-billed/re-run. Corrupt cache → miss.
7. **Determinism in tests.** `LLMPromoter` takes an injectable `AgentClient`; unit/pipeline/E2E tests use `FakeAgentClient` or a stub command; the real exec is an opt-in (`PSC_ATOMIZE_LIVE`) manual test.
8. **Traceability for SkillOpt.** `processing.promoted` records `promoter`, `model`, `skill_hash`.

## Component Boundaries

- `agent_exec.py` — `AgentClient` interface, `AgentExecClient` (subprocess + timeout), `FakeAgentClient`.
- `prompt.py` — assemble prompt from skill + fragments + known projects.
- `llm_output.py` — extract and schema-validate JSON → `SliceProposal[]`.
- `llm_promoter.py` — `LLMPromoter.promote(fragments, config)`: exec → parse → `slice_frontmatter.build_from_proposal` → dual-validate; returns slices carrying resolved relations.
- `promoter.py` (modified) — per-session ABC; `IdentityPromoter` adapted.
- `pipeline.py` (modified) — `promote_pass` feeds whole sessions; LLM-output cache; semantic relation edges.
- `slice_frontmatter.py` (modified) — add `build_from_proposal` (union + `tags`, content-derived `slice_id`).

## Error / Guardrail Posture

LLM failures (unavailable, bad JSON, schema/validation failure) collapse to session-level fail-closed (`split`, warn, retry). Cache corruption and dangling `relates_to` degrade rather than fail. Inputs are trusted as already-redacted; output is not re-scanned in this change (documented limitation). Logs never carry raw model output or session bodies.

## Out of Scope

SkillOpt optimization loop (follow-up on `evolve`); cross-session evolution lineage and global entity graph (Topic 5); dream scheduler (Topic 5); new API/SDK client; tmux live-pane dispatch; output-side secret rescan.
