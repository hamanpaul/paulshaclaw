## ADDED Requirements

### Requirement: Stage 8 cost snapshot CLI

Stage 8 SHALL provide a cost snapshot CLI invocable as `python -m paulshaclaw.cost --once`. The CLI MUST emit a single JSON object containing generation time, configured timezone, cache status, and provider entries for Codex (`cdx`), Claude Code (`cc`), and GitHub Copilot (`cpt`). The CLI MUST NOT print secrets or credential file contents.

#### Scenario: Snapshot CLI emits provider-neutral JSON

- **WHEN** an operator runs `python -m paulshaclaw.cost --once`
- **THEN** stdout MUST contain valid JSON with `generated_at`, `timezone`, `cache_status`, and `providers`
- **THEN** `providers` MUST be keyed by provider abbreviations such as `cdx`, `cc`, and `cpt`

#### Scenario: Missing credentials degrade without secret leakage

- **WHEN** provider credentials are absent
- **THEN** the snapshot MUST mark the affected provider `source_status` as `unknown` or `error`
- **THEN** stdout and logs MUST NOT contain secret values, tokens, or credential file contents

### Requirement: Tmux footer status command

Stage 8 SHALL provide a tmux footer status command invocable as `python -m paulshaclaw.cost.status`. The command MUST print one line suitable for tmux `status-right`, MUST exit 0 for normal degraded display cases, and MUST preserve tmux responsiveness by reading cache before attempting provider refresh.

#### Scenario: Footer renders the balanced format

- **WHEN** the snapshot contains Codex 5h usage `18` with reset display `15:21`, weekly usage `41` with reset display `3d`, Claude unknown data, and two Copilot accounts `haman=724` and `arc=127`
- **THEN** the footer MUST include `cdx 5h:18%(15:21) wk:41%(3d)`
- **THEN** the footer MUST include `cc 5h:-- wk:--`
- **THEN** the footer MUST include `cpt haman:724 arc:127`

#### Scenario: Stale provider is marked

- **WHEN** a provider is rendered from stale cache
- **THEN** the footer MUST append `~` to that provider abbreviation, such as `cdx~`

### Requirement: Provider windows and reset displays

Stage 8 SHALL render Codex and Claude Code 5-hour and weekly quota windows when trusted provider data exists. The 5-hour reset display MUST use the configured timezone and `HH:MM` format. The weekly reset display MUST use a relative format such as `3d`. If trusted data is unavailable, the field MUST render as `--` rather than an estimate.

#### Scenario: Five-hour reset uses configured timezone

- **WHEN** the configured timezone is `Asia/Taipei` and a provider reset timestamp converts to `15:21`
- **THEN** the footer MUST render the 5-hour window as `5h:<used>%(15:21)`

#### Scenario: Unknown quota window is not estimated

- **WHEN** Codex or Claude Code does not provide trusted 5-hour or weekly quota data
- **THEN** the corresponding footer field MUST render `--`

### Requirement: Config-driven Copilot accounts

Stage 8 SHALL load Copilot accounts from configuration. Runtime behavior MUST support zero, one, or many accounts and MUST NOT hardcode `hamanpaul`, `org-a`, `haman`, or `arc`. Each account MAY define `id`, `label`, `kind`, `monthly_allowance`, and provider-specific billing scope such as `org` or enterprise identifiers.

#### Scenario: No Copilot accounts omit the cpt segment

- **WHEN** Copilot account config is empty
- **THEN** the footer MUST omit the `cpt` segment

#### Scenario: One Copilot account renders one label

- **WHEN** Copilot account config contains one account with label `haman` and usage `724`
- **THEN** the footer MUST include `cpt haman:724`

#### Scenario: Multiple Copilot accounts preserve config order

- **WHEN** Copilot account config contains labels `haman` and `arc` in that order
- **THEN** the footer MUST render `cpt haman:<usage> arc:<usage>` in the same order

### Requirement: Copilot online usage source priority

Stage 8 SHALL treat GitHub Copilot account usage as account-level data, not host-local data. For personal accounts, the adapter MUST prefer GitHub user billing premium request usage reports. For company-managed accounts, the adapter MUST prefer configured organization or enterprise billing/report sources. Local Copilot session logs MAY be used only as fallback and MUST be marked as `local_observed`.

#### Scenario: Personal account uses user billing source

- **WHEN** a Copilot account is configured with `kind=personal`
- **THEN** the adapter MUST attempt a user-level GitHub billing/report source before local observed logs

#### Scenario: Company account uses organization or enterprise source

- **WHEN** a Copilot account is configured with `kind=company` and an organization or enterprise scope
- **THEN** the adapter MUST attempt that configured organization or enterprise source before local observed logs

#### Scenario: Local fallback is marked partial

- **WHEN** Copilot usage is derived from local session logs
- **THEN** the account snapshot MUST set `source` to `local_observed`

### Requirement: Snapshot cache behavior

Stage 8 SHALL cache snapshots under the agent state tree with a default TTL of 120 seconds. A busy cache lock MUST cause the status command to read an existing cache instead of blocking. Provider refresh failure MUST preserve the previous snapshot when available and mark affected data stale.

#### Scenario: Fresh cache is reused

- **WHEN** a snapshot cache is younger than 120 seconds
- **THEN** the footer status command MUST read the cache instead of refreshing provider sources

#### Scenario: Lock contention does not block tmux

- **WHEN** the snapshot lock is busy and an older snapshot exists
- **THEN** the footer status command MUST render from the older snapshot

#### Scenario: Refresh failure preserves old snapshot

- **WHEN** provider refresh fails after a previous snapshot exists
- **THEN** Stage 8 MUST keep the old snapshot and mark affected provider data stale or error

### Requirement: Footer color thresholds

Stage 8 SHALL apply tmux style coloring by usage threshold. Usage below 70 percent MUST use the low-risk style. Usage from 70 through 89 percent MUST use the warning style. Usage at or above 90 percent MUST use the critical style. Unknown or error data MUST use a neutral or dim style.

#### Scenario: Threshold boundaries are deterministic

- **WHEN** provider usage is 69, 70, 89, and 90 percent
- **THEN** Stage 8 MUST classify them as low-risk, warning, warning, and critical respectively

#### Scenario: Copilot color uses allowance without showing max

- **WHEN** a Copilot account has `used_requests=270` and `monthly_allowance=300`
- **THEN** Stage 8 MUST classify that account as critical
- **THEN** the footer MUST display the used request count without displaying `/300`
