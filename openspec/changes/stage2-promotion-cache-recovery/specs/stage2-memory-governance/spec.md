## ADDED Requirements

### Requirement: Promotion failure clears the poisoned LLM cache

When session promotion fails with a `PromoteError` under an LLM promoter backed by a caching agent client, the atomizer pipeline SHALL clear the cached raw output for that session's fragments (cache key `<agent>:<session>__<sha256(fragments)>`) before leaving the session in `split` state **only when that failed attempt actually produced cached raw output**. Failures that occur before any cache write (for example an underlying `AgentExecError` transport failure) MUST leave the retry counter unchanged, MUST NOT claim poisoned-cache retention, and MUST keep the session eligible for a real LLM call on the next atomize run. Cache clearing MUST NOT occur for non-LLM promoters, MUST NOT occur in dry-run mode, and MUST only unlink files inside `runtime/cache/atomize/` after validating the cache key.

#### Scenario: Poisoned cache is cleared on promote failure

- **WHEN** an LLM promoter with a caching agent client produces unparseable output for a split session (a `PromoteError`)
- **THEN** the session MUST remain in `split` state with a `left in split` warning
- **THEN** the cache file for that session's fragments MUST no longer exist under `runtime/cache/atomize/`

#### Scenario: Next run re-invokes the LLM and recovers

- **WHEN** the first atomize run fails promotion with bad LLM output and a second run's LLM output is valid
- **THEN** the second run MUST invoke the underlying agent again (no cache replay of the bad output)
- **THEN** the session MUST reach `promoted` state on the second run

#### Scenario: Transport failure leaves no cache and no retry-budget mutation

- **WHEN** the underlying agent command fails before any raw output is cached for a split session
- **THEN** no `.json` cache file may be created and no `.retries` sidecar may be created or incremented for that failed attempt
- **THEN** the warning text MUST describe a transport / no-cache retry state and MUST NOT claim poisoned-cache retention
- **THEN** a later run MUST still invoke the underlying agent again

#### Scenario: Identity promoter failures do not touch the cache

- **WHEN** a non-LLM promoter raises during promotion for a session
- **THEN** no file under `runtime/cache/atomize/` may be created or deleted by the failure handling

#### Scenario: Dry-run backlog preview does not mutate cache or retry budget

- **WHEN** `dry_run=True`, the raw inbox document for a session has already been archived, and that session remains in `split` with an existing cache file and `.retries` sidecar
- **THEN** the cache file MUST remain present and the `.retries` sidecar MUST remain unchanged after the dry-run
- **THEN** the underlying agent MUST NOT be invoked

### Requirement: Empty proposal output is a terminal promoted state

The LLM output parser SHALL treat an empty JSON array (including one wrapped in a fenced code block and surrounded by prose) as a valid result meaning "no extractable knowledge", returning zero proposals instead of raising. The atomizer pipeline SHALL bring such a session to `state=promoted` with `slices=0`, archive its fragments, clear its cache, and emit no `left in split` warning. A non-empty JSON array whose every proposal is schema-invalid MUST still raise (`no salvageable proposals`).

#### Scenario: Bare empty array parses to zero proposals

- **WHEN** the raw agent output is `[]`
- **THEN** parsing MUST return an empty proposal list without raising

#### Scenario: Fenced empty array with reasoning prose parses to zero proposals

- **WHEN** the raw agent output is a fenced ```json``` block containing `[]` followed by reasoning prose
- **THEN** parsing MUST return an empty proposal list without raising

#### Scenario: Session with empty LLM output reaches promoted with zero slices

- **WHEN** an LLM promoter returns zero slices for a split session
- **THEN** the processing ledger MUST record `state=promoted` with `slices: 0` for that session
- **THEN** the session's fragments MUST be archived out of `inbox/_slices/` and its cache cleared
- **THEN** no `left in split` warning may be emitted for that session

#### Scenario: All-invalid proposals still fail closed

- **WHEN** the raw agent output is a non-empty JSON array in which every proposal violates the schema
- **THEN** parsing MUST raise an error mentioning `no salvageable proposals`

### Requirement: Bounded LLM retry budget per stuck session

The atomizer pipeline SHALL bound LLM re-invocations for a repeatedly **content-failing** session using a persistent retry counter stored as `runtime/cache/atomize/<cache_key>.retries`. On each `PromoteError` under an LLM promoter (non-dry-run), the counter MUST be incremented only when the cached raw-output file exists for that failed attempt; transport failures that leave no cached raw output MUST leave the counter unchanged. The poisoned cache MUST be cleared only while the incremented count is at or below the budget (5). Once the count exceeds the budget, the poisoned cache MUST be retained so later runs fail at parse time without invoking the LLM, while still emitting a warning that identifies the exhausted budget. Successful promotion MUST remove the retry counter together with the cache file. Retry-counter file paths MUST pass the same cache-key validation and directory-containment checks as cache files.

#### Scenario: Failure within budget increments the counter and clears the cache

- **WHEN** a split session fails promotion for the first time under an LLM promoter
- **THEN** `runtime/cache/atomize/<cache_key>.retries` MUST contain `1`
- **THEN** the cache file MUST be cleared so the next run re-invokes the LLM

#### Scenario: First post-outage content failure starts at retry 1

- **WHEN** one or more transport failures happened without writing cached raw output and a later LLM response fails after being cached
- **THEN** `runtime/cache/atomize/<cache_key>.retries` MUST contain `1`
- **THEN** the cache file MUST be cleared so the session still retains the remaining content retry budget

#### Scenario: Exhausted budget parks on the poisoned cache

- **WHEN** a session's retry counter already equals the budget and promotion fails again
- **THEN** the counter MUST be incremented past the budget and the cache file MUST be retained
- **THEN** a subsequent run MUST NOT invoke the underlying agent for that session (cache replay only) and MUST still record a warning

#### Scenario: Success clears the retry counter

- **WHEN** a session with an existing retry counter is successfully promoted
- **THEN** both the cache file and the `.retries` sidecar for its cache key MUST be removed

### Requirement: Dream record surfaces pass warnings

The dream orchestrator SHALL include warning text in the per-pass summary written to the dream ledger: when a pass returns a non-empty warnings list, the pass summary MUST contain `warnings` (the first 10 warning strings, each truncated to at most 500 characters) and `warnings_total` (the full count). When the warnings list is empty or absent, the pass summary MUST NOT contain these keys. Recorded warning text MUST NOT include raw prompts or raw LLM output bodies.

#### Scenario: Warning text reaches the dream ledger

- **WHEN** the atomize pass returns warnings `["claude:s1: llm promote failed: ...; session claude:s1 left in split"]`
- **THEN** the persisted dream record MUST contain that warning string in `passes.atomize.warnings`
- **THEN** `passes.atomize.warnings_total` MUST equal `1` and the run status MUST be `partial`

#### Scenario: Warning overflow is truncated but counted

- **WHEN** a pass returns 45 warnings
- **THEN** `passes.<pass>.warnings` MUST contain exactly 10 entries and `warnings_total` MUST equal `45`

#### Scenario: Clean pass summary is unchanged

- **WHEN** a pass returns an empty warnings list
- **THEN** its pass summary MUST NOT contain `warnings` or `warnings_total` keys
