# stage6-security-governance Specification

## Purpose
TBD - created by archiving change stage6-baseline. Update Purpose after archive.

## Requirements

### Requirement: High-risk approval gate

Stage 6 SHALL provide a high-risk approval gate for `ops-companion`. Commands in the `ship-command`, `git-push`, `deploy-command`, `package-install`, and `remote-operation` families MUST be blocked by default until explicit approval is granted. `/ship` MUST require `interactive-approval`. Package install matching MUST include `install`, `get`, and `add` subcommands for `pip/pip3/npm/pnpm/yarn/apt/apt-get/brew/go`.

#### Scenario: High-risk command denied without approval

- **WHEN** a caller evaluates `/ship stage6 --dry-run` or `git push origin main` without approval
- **THEN** the decision MUST return `allowed=false` and a matching high-risk `rule_id`

#### Scenario: Package add commands are covered

- **WHEN** a caller evaluates `npm add express`, `pnpm add express`, and `yarn add express`
- **THEN** each command MUST match `package-install` and be denied without approval

### Requirement: Redaction and classification baseline

Stage 6 SHALL provide redaction rules for at least `Authorization: Bearer ...`, `password=...`, and GitHub token shapes (`ghp_...`, `github_pat_...`). Redaction MUST mask raw secret values and MUST return both `rule_hits` and `classifications`.

#### Scenario: Secret strings are masked

- **WHEN** redaction is run on payloads containing bearer token, password assignment, and GitHub token
- **THEN** the output MUST NOT contain original secrets and MUST include `credential` classification

### Requirement: Append-only audit trail

Stage 6 SHALL provide an append-only audit trail with `GENESIS` anchor and per-entry hash chaining. Each entry MUST contain `actor`, `action`, `target`, `approved`, `classifications`, `occurred_at`, `previous_hash`, and `entry_hash`. Verification MUST fail on tampering and report the broken entry index.

#### Scenario: Hash chain verification succeeds

- **WHEN** two valid entries are appended in order
- **THEN** `verify()` MUST return `ok=true` and the second entry MUST reference the first `entry_hash`

#### Scenario: Tampering is detected

- **WHEN** an existing audit line is modified after write
- **THEN** `verify()` MUST return `ok=false` with non-null `broken_index`

### Requirement: Gate decision must be auditable

Stage 6 SHALL expose a unified gate-to-audit helper (`record_approval_decision`) that records both deny and approve decisions. Deny and approve actions MUST be distinguishable in `action` and `classifications`.

#### Scenario: Deny decision recorded

- **WHEN** `record_approval_decision` records a denied `/ship` decision
- **THEN** the resulting audit action MUST contain `ship-command.denied`

#### Scenario: Approve decision recorded

- **WHEN** `record_approval_decision` records an approved `/ship` decision
- **THEN** the resulting audit action MUST contain `ship-command.approved`

### Requirement: Stage 6 evidence and sync-back gate

Stage 6 SHALL keep implementation evidence under `docs/superpowers/workstreams/stage6-ops-companion-security/evidence/`, and SHALL keep a stage archive note under `docs/superpowers/archive/stage6-ops-companion-security-*.md`. `custom-skills/ops-companion/` MUST exist as the sync-back staging target, and sync-back MUST remain gated by passing Stage 6 tests with retained evidence.

#### Scenario: Workstream evidence exists

- **WHEN** a reviewer lists the Stage 6 evidence directory
- **THEN** it MUST contain red/green traces and final test outputs for approval, audit integration, and package-add coverage

#### Scenario: Sync-back staging path exists

- **WHEN** a reviewer checks `custom-skills/ops-companion/`
- **THEN** `README.md` MUST exist and describe sync-back gate conditions
