## 1. Seed atomization skill (authoring)

- [ ] 1.1 Sample representative `atomized_from` notes from `~/notes/TechVault` (120) and `WorkVault` (29); extract splitting principles (one-concept-per-slice, cross-fragment merge, min atomic size, shared-preamble handling, naming, tag inheritance, relation patterns) — principles only, no verbatim note content. Exclude PersonalVault.
- [ ] 1.2 Write `paulshaclaw/memory/atomizer/skills/atomize-knowledge-slice.md`: adapt the `obsidian-atomize` 6-phase workflow to paulshaclaw knowledge slices; include project-attribution guidance (pick from known projects or `_unknown`), tag strategy, relation guidance, and the mandatory JSON output contract.
- [ ] 1.3 Add `test_atomize_skill.py`: assert the skill file exists, has frontmatter, and contains an output-contract section listing the required JSON fields.

## 2. agent_exec backend

- [ ] 2.1 Add failing `test_agent_exec.py`: `AgentExecClient` runs a stub command and returns stdout; timeout → raise; non-zero exit → raise; command-not-found → raise; `FakeAgentClient.run` returns its canned string.
- [ ] 2.2 Implement `paulshaclaw/memory/atomizer/agent_exec.py` (`AgentClient` ABC, `AgentExecClient`, `FakeAgentClient`).
- [ ] 2.3 Add a stub fixture script `paulshaclaw/memory/tests/fixtures/atomizer/fake-agent.py` that reads stdin and prints canned slice JSON (for integration check + agent_exec tests).

## 3. LLM output contract

- [ ] 3.1 Add failing `test_llm_output.py`: parse a valid JSON array → `SliceProposal[]`; extract JSON from a fenced block / surrounding prose; reject malformed JSON, missing fields, bad `artifact_kind`, unknown `project`, empty `body`.
- [ ] 3.2 Implement `paulshaclaw/memory/atomizer/llm_output.py` (`SliceProposal`, `parse(raw, known_projects)`).

## 4. Prompt assembly

- [ ] 4.1 Add failing `test_atomizer_prompt.py`: `build_prompt` includes skill text + each fragment body + the known-projects list; deterministic given inputs.
- [ ] 4.2 Implement `paulshaclaw/memory/atomizer/prompt.py` (`build_prompt(skill_text, fragments, known_projects)`).

## 5. slice_frontmatter from proposal

- [ ] 5.1 Extend `test_slice_frontmatter.py`: `build_from_proposal(proposal, session_meta)` produces union frontmatter + `tags`, content-derived `slice_id = sl-<sha256(agent|session|sha256(body))[:16]>`, `checksum == sha256(body)`, `source_fragments`, `distilled_from`; passes Stage 3 ∪ Topic 4 validation.
- [ ] 5.2 Implement `build_from_proposal` in `paulshaclaw/memory/atomizer/slice_frontmatter.py` (and extend `Slice` with an optional `relations` field defaulting to `[]`).

## 6. Per-session Promoter interface + LLMPromoter

- [ ] 6.1 Update `test_atomizer_promoter.py`: `Promoter.promote(fragments, config)`; `IdentityPromoter` returns one slice per fragment under the per-session signature.
- [ ] 6.2 Modify `paulshaclaw/memory/atomizer/promoter.py`: widen ABC to per-session; adapt `IdentityPromoter` (loop fragments, 1:1, `relations=[]`).
- [ ] 6.3 Add failing `test_llm_promoter.py` (with `FakeAgentClient`): two-slice JSON → two slices with relations; merge case (2 fragments → 1 slice, `source_fragment_indices=[0,1]`); invalid output → fail-closed raise.
- [ ] 6.4 Implement `paulshaclaw/memory/atomizer/llm_promoter.py` (`LLMPromoter(agent_client)`; `promote` = build prompt → run → parse → build_from_proposal → validate; raise on any failure).

## 7. Pipeline integration + cache

- [ ] 7.1 Extend `test_atomizer_pipeline.py`: `promote_pass` with `LLMPromoter(fake)` writes slices, `relates_to`/`mentions` edges, and a `promoted` record with `promoter=llm`/`model`/`skill_hash`; merge case yields fewer slices than fragments; fail-closed leaves session in `split`; crash-resume reuses cache (fake called once).
- [ ] 7.2 Modify `paulshaclaw/memory/atomizer/pipeline.py`: feed whole-session fragments to the promoter; add the `runtime/cache/atomize/<session_key>__<fragments_hash>.json` get-or-create cache; resolve and append semantic edges; record `promoter`/`model`/`skill_hash`; keep step order product→ledger→archive→clear-cache.

## 8. Config + CLI + /agent unification

- [ ] 8.1 Extend `test_atomizer_config.py`: load `agent_exec` (command/timeout/model), `promoter` default, and `known_projects` source; override + hash determinism.
- [ ] 8.2 Modify `atomizer.yaml`/`config.py`: add `agent_exec`, `promoter`, `known_projects` keys.
- [ ] 8.3 Modify `cli.py`: add `--promoter llm|identity`; construct `LLMPromoter(AgentExecClient(config))` when `llm`.
- [ ] 8.4 Migrate the paulshiabro `/agent` launcher to read the shared `agent_exec.command` config (config unification only); add/adjust a test asserting the command is not hardcoded. If `/agent` is otherwise broken, record it as a separate debug item — do not block this change.

## 9. End-to-end + integration + regression

- [ ] 9.1 Extend `test_atomizer_e2e.py`: full `atomize --promoter llm` (fake/stub) over a fixture session → knowledge slices pass `python3 -m paulshaclaw.lifecycle.gate`; relations contain `relates_to`/`mentions`; flow-through holds; ledgers contain no raw body.
- [ ] 9.2 Add `test_atomizer_llm_live.py` guarded by `@skipUnless(os.environ.get("PSC_ATOMIZE_LIVE"))` exercising the real `claude-gemma4` exec.
- [ ] 9.3 Extend `stage2_integration_check.sh` with `atomize --promoter llm --dry-run` pointing `agent_exec.command` at the stub fixture script; assert a slice count in the summary.
- [ ] 9.4 Run `python3 -m unittest discover -s paulshaclaw/memory/tests -v` (all green) and `python3 -m unittest discover -s tests -v` (only pre-existing unrelated failures).
- [ ] 9.5 Update `paulshaclaw/memory/routing.md` for the LLM promoter path; mark OpenSpec tasks complete and record the verification summary below.

## Verification Summary

(To be filled at end of implementation: focused atomizer/LLM test results, full memory-suite result, integration-check output, `lifecycle.gate` conformance, opt-in live-exec note, and `tests/` regression status.)
