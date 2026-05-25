## ADDED Requirements

### Requirement: Stage 2 memory policy boundary contract

Stage 2 SHALL define a memory security policy boundary contract with the canonical boundary identifiers `external_to_raw`, `raw_to_distilled`, `distilled_to_canonical`, `canonical_to_indexed`, and `indexed_to_consumer`. The boundary identifiers SHALL reuse the existing Stage 2 memory layer model and SHALL NOT redefine the physical memory tree. MVP execution MUST enforce policy at `external_to_raw` and `raw_to_distilled`; the other boundaries MUST be reserved in policy schema for future Stage 2 components.

#### Scenario: Boundary schema lists all five identifiers

- **WHEN** an operator reads `paulshaclaw/memory/policy/boundaries.yaml`
- **THEN** it MUST list `external_to_raw`, `raw_to_distilled`, `distilled_to_canonical`, `canonical_to_indexed`, and `indexed_to_consumer`
- **THEN** `external_to_raw` and `raw_to_distilled` MUST be marked mandatory for MVP execution
- **THEN** the remaining three boundaries MUST be marked deferred

### Requirement: Policy artifacts and effective policy hash

Stage 2 SHALL store default policy artifacts in `paulshaclaw/memory/policy/secrets.yaml`, `classification.yaml`, and `boundaries.yaml`. Stage 2 SHALL support a local override file at `~/.config/paulshaclaw/policy.override.yaml`. The policy loader MUST merge defaults and local override into an effective policy and compute a deterministic `effective_policy_hash`. Ledger and audit records written by the policy layer MUST include both `policy_version` and `effective_policy_hash`.

#### Scenario: Local override participates in effective hash

- **WHEN** a local override disables a rule for a session
- **THEN** the effective policy hash MUST change
- **THEN** dry-run, audit, and ledger output for that session MUST include the changed hash

#### Scenario: Unsupported major version fails closed

- **WHEN** a consumer loads a policy with an unsupported major `policy_version`
- **THEN** fail-closed boundaries MUST reject processing
- **THEN** no inbox artifact MAY be published

### Requirement: Redaction at ingress boundaries

Stage 2 SHALL run cheap regex redaction at `external_to_raw` before hook scripts write queue payloads. Stage 2 SHALL run the full policy library and gitleaks detector at `raw_to_distilled` before importer writes `inbox/`. Redaction action MUST be line-level: every line with one or more hits MUST be replaced with `[REDACTED LINE: <rule-id> x<count>]` or an equivalent multi-rule placeholder. The memory system MUST NOT store matched secret text or original matched lines in `inbox/`, ledger, audit, `archive/queue/`, or `runtime/queue/_failed/`.

#### Scenario: Hook redacts before queue write

- **WHEN** a hook payload contains an obvious GitHub PAT fixture
- **THEN** the queue payload MUST contain a redacted line placeholder
- **THEN** the queue payload MUST NOT contain the original token

#### Scenario: Gitleaks-only hit is not archived raw

- **WHEN** gitleaks finds a secret in a queue payload that hook regex missed
- **THEN** the importer MUST write only redacted content to `inbox/`
- **THEN** any `archive/queue/` copy MUST be redacted
- **THEN** the original queue payload MUST be unlinked after successful processing

### Requirement: Classification tagging for distilled artifacts

Stage 2 SHALL classify every distilled `inbox/` artifact with `classification_level`, `classification_reason`, `classification_policy_hash`, and `classification_source`. Allowed levels MUST be `public`, `private`, and `secret`. Unknown projects MUST default to `private`. Any artifact with redaction hits MUST be classified as `private` unless a more restrictive rule applies. Classification failure MUST fail open with warning by writing the artifact as `private` and recording `classification-warning`.

#### Scenario: Unknown project defaults private

- **WHEN** the project resolver returns `_unknown`
- **THEN** the inbox artifact MUST contain `classification_level: private`
- **THEN** `classification_reason` MUST indicate the unknown-project fallback

#### Scenario: Redaction hit downgrades classification

- **WHEN** a session would otherwise be `public` but has any redaction hit
- **THEN** the final inbox artifact MUST be classified `private`

### Requirement: Policy audit and ledger records

Stage 2 SHALL record session-level policy summaries in the importer ledger and rule-level events in `~/.agents/memory/runtime/audit/policy.jsonl`. Both record types MUST include `session_ref`, `policy_version`, and `effective_policy_hash`. Audit records MUST include boundary, component, rule ID, detector, line number when available, and action. Audit and ledger records MUST NOT contain matched secret text or original line content.

#### Scenario: Audit contains rule metadata but no secret

- **WHEN** a redaction rule matches a token fixture
- **THEN** `policy.jsonl` MUST contain the rule ID, detector, boundary, action, and line number
- **THEN** `policy.jsonl` MUST NOT contain the matched token or original line text

### Requirement: Policy failure behavior

Stage 2 SHALL treat redaction failures at `external_to_raw` and `raw_to_distilled` as fail-closed with retry. Retry exhaustion MUST write only a metadata failure stub under `runtime/queue/_failed/`, unlink the queue payload, avoid publishing inbox output, and write `policy-error` to the ledger when the ledger is available. If the ledger is unavailable, the failure stub MUST say `ledger_status: unavailable` and the component MUST write a best-effort warning to `~/.agents/memory/log/policy.log`. Classification failures MUST fail open with `private` fallback and warning.

#### Scenario: Gitleaks missing fails closed

- **WHEN** gitleaks is enabled but unavailable
- **THEN** `raw_to_distilled` MUST retry according to `boundaries.yaml`
- **THEN** retry exhaustion MUST NOT write an inbox artifact
- **THEN** `_failed/` MUST contain only metadata stub fields, not the original payload

#### Scenario: Ledger unavailable does not claim policy-error was recorded

- **WHEN** a fail-closed policy error occurs and ledger append fails after retry
- **THEN** the failure stub MUST include `ledger_status: unavailable`
- **THEN** no requirement MAY claim a ledger `policy-error` entry exists for that event

### Requirement: Local override and dry-run policy workflow

Stage 2 SHALL support audited local override through `~/.config/paulshaclaw/policy.override.yaml`. Overrides MAY disable rules globally, disable rules for specific sessions, append local regex rules, append local classification rules, and override project defaults. Stage 2 SHALL provide `psc memory dry-run-policy <session-id>` that reports rule IDs, detector, line number, action, classification result, and effective policy hash without writing inbox output or printing matched strings.

#### Scenario: Rule disabled for one session

- **WHEN** local override disables `rule-x` for `session-a`
- **THEN** dry-run for `session-a` MUST report `rule-x` as skipped
- **THEN** dry-run for another session MUST still apply `rule-x`
- **THEN** audit output MUST include an override event without secret text

### Requirement: Consumer policy API enforcement

Stage 2 SHALL provide `paulshaclaw.memory.policy` as the only supported policy execution API. Memory consumers MUST NOT parse policy YAML directly, implement their own detector, or write policy audit records by hand. The repository SHALL include CI lint that fails when a memory consumer writes or emits memory across a declared boundary without calling the policy boundary API.

#### Scenario: Consumer bypass is caught by lint

- **WHEN** a Python memory consumer fixture writes to a memory boundary without calling `paulshaclaw.memory.policy`
- **THEN** `paulshaclaw/memory/lint/policy_consumer_lint.py` MUST exit non-zero

