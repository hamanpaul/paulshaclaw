## ADDED Requirements

### Requirement: Executable sync-back gate

Stage 2 SHALL provide an executable sync-back gate in `paulshaclaw/memory/syncback/` that programmatically evaluates the five documented sync-back conditions and returns a structured verdict. The gate MUST evaluate: (1) importer/classifier/replay tests pass, (2) decayed/reactivation tests pass and evidence is present, (3) evidence files exist and are non-empty, (4) `review.md` contains a non-blocking conclusion, (5) `lifecycle.schema.REQUIRED_FRONTMATTER_FIELDS` is a subset of the Stage 3 canonical set `{slice_id, artifact_kind, supersedes, checksum, phase}`. The verdict MUST report each condition's pass/fail with a non-sensitive detail and an overall `ok` that is true only when all conditions pass. The gate MUST be exposed as `psc memory syncback check` returning exit 0 on pass and non-zero otherwise. The gate MUST be read-only: it MUST NOT copy the package into `custom-skills/paulsha-memory/` nor push to `hamanpaul/custom-skills`.

#### Scenario: All conditions pass yields exit zero and a sync manifest

- **WHEN** all five conditions hold and an operator runs `psc memory syncback check`
- **THEN** the verdict `ok` MUST be true and the command MUST exit zero
- **THEN** a sync manifest listing the installable package paths MUST be reported (informational; not executed)

#### Scenario: Any failing condition blocks the gate

- **WHEN** any one of the five conditions fails
- **THEN** the verdict `ok` MUST be false, the command MUST exit non-zero, and the sync manifest MUST be empty

### Requirement: Sync-back gate is fail-closed and deterministic

The sync-back gate MUST be fail-closed: a missing or unreadable file, a test runner that raises, a `review.md` lacking a conclusion section, or any inability to determine a condition MUST cause that condition to fail and therefore the gate to fail — never a default pass. The gate MUST be deterministic: the timestamp MUST be injected rather than read from the wall clock inside the evaluator, and the test runner MUST be injectable so the gate's own unit tests do not invoke the real test suite. Condition details MUST NOT contain secrets or raw exception text.

#### Scenario: Test runner failure fails closed

- **WHEN** the injected test runner raises or reports failure
- **THEN** the corresponding test condition MUST fail and the gate MUST fail

#### Scenario: Skipping tests is not a pass

- **WHEN** the gate is run with test execution disabled
- **THEN** the test conditions MUST be reported as failed (governance does not allow skipping tests)

#### Scenario: Missing review conclusion fails closed

- **WHEN** `review.md` has no conclusion section
- **THEN** the review condition MUST fail
