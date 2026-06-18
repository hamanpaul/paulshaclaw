## ADDED Requirements

### Requirement: Per-session LLM atomic distillation

When the atomizer runs with `promoter: llm`, the system SHALL distill one session's fragments into one or more knowledge atoms via the configured agent (gemma4), allowing cross-fragment merge and single-fragment split, and SHALL attach per-batch `relates_to` and `mentions` relations and `tags`. Promotion MUST be per-session all-or-nothing: every produced atom MUST pass `slice_frontmatter.validate` (Stage 3 ∪ T4) or the whole session is not written. Each atom's `slice_id` MUST be content-derived so identical content yields a stable id across re-runs. The processing ledger record MUST carry `promoter="llm"`, `model`, and `skill_hash`.

#### Scenario: Session distilled into multiple atoms
- **WHEN** a session with multiple concepts is promoted with `promoter: llm`
- **THEN** the agent output is parsed into one or more knowledge atoms written under `knowledge/`, each with content-derived `slice_id`, `tags`, and per-batch relations, and the processing ledger records `promoter=llm` with `model` and `skill_hash`

#### Scenario: Validation failure aborts the whole session
- **WHEN** any produced atom fails `slice_frontmatter.validate`
- **THEN** no atom for that session is written, the session stays in `split`, and the failure is logged without recording the raw agent output or session content

### Requirement: Bounded distillation output window

The atomize LLM call SHALL set the agent subprocess output-token ceiling from configuration so multi-atom JSON is not truncated. The `AgentExecClient` MUST support an environment override and pass `CLAUDE_CODE_MAX_OUTPUT_TOKENS` derived from `agent_exec.max_output_tokens` (default 8192). When no override is configured the client MUST inherit the parent environment unchanged (backward compatible).

#### Scenario: Output ceiling raised for atomize
- **WHEN** the LLM promoter invokes the agent subprocess
- **THEN** the subprocess environment contains `CLAUDE_CODE_MAX_OUTPUT_TOKENS` equal to the configured `agent_exec.max_output_tokens` (default 8192)

#### Scenario: No override preserves inherited environment
- **WHEN** `AgentExecClient` is constructed without an env override
- **THEN** the subprocess runs with the parent environment unchanged

### Requirement: Fail-closed distillation under agent unavailability

LLM distillation MUST be fail-closed: when the agent command is missing, times out, exits non-zero, returns empty output, or returns unparseable/invalid JSON, the session SHALL remain in `split`, be retried on the next dream cycle, and lose no data. Logs MUST NOT contain raw agent output or session content.

#### Scenario: gemma4 unreachable leaves session for retry
- **WHEN** the agent subprocess fails or times out because gemma4 is unreachable
- **THEN** the session remains in `split`, no partial atoms are written, and the next dream cycle retries it

### Requirement: Forward-only canary rollout

Switching the dream loop to `promoter: llm` SHALL apply LLM distillation to newly imported sessions only; existing `identity` slices SHALL remain untouched until backfill. The system MUST tolerate a mixed knowledge layer of `identity` and `llm` slices during the canary period without error.

#### Scenario: New session uses LLM while old slices remain
- **WHEN** the dream loop runs with `promoter: llm` after the switch
- **THEN** newly imported sessions produce LLM atoms while previously promoted `identity` slices are left in place, and the pipeline completes without error

### Requirement: Two-layer MOC rendering of distilled atoms

The MOC builder SHALL render a per-session title as the navigational spine with that session's distilled atoms nested beneath it, resolved via the `distilled_from` relation. Sessions without distilled atoms SHALL render as a title-only entry. Rendering MUST remain deterministic and MUST NOT fail on a mixed `identity`/`llm` knowledge layer.

#### Scenario: Session with atoms renders hierarchically
- **WHEN** the MOC builder renders a session that has distilled atoms
- **THEN** the session title appears as the parent entry with its atoms listed beneath, linked by wikilink

#### Scenario: Session without atoms renders title-only
- **WHEN** the MOC builder renders a session that has no distilled atoms
- **THEN** only the per-session title entry is rendered and no error occurs
