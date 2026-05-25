## ADDED Requirements

### Requirement: Claude Code quota source priority
Stage 8 SHALL collect Claude Code (`cc`) quota windows from a configured Claude Code statusline sidecar before using any local fallback. The collector MUST map Claude Code `five_hour` rate limit data to the `five_hour` footer window and `seven_day` rate limit data to the `weekly` footer window. The collector MUST NOT include local gemma4, vLLM, or OpenAI-compatible local model usage in Claude Code quota output.

#### Scenario: Claude sidecar provides trusted windows
- **WHEN** a Claude Code statusline sidecar contains 5-hour and 7-day `rate_limits` with used percentages and reset timestamps
- **THEN** the `cc` provider snapshot MUST set `source_status` to `fresh`
- **THEN** the `cc` provider snapshot MUST populate `windows.five_hour` and `windows.weekly`

#### Scenario: Claude local model usage is excluded
- **WHEN** local usage records include gemma4, vLLM, or OpenAI-compatible local model calls
- **THEN** Stage 8 MUST NOT count those records as Claude Code (`cc`) quota usage

### Requirement: Codex quota source priority
Stage 8 SHALL collect Codex (`cdx`) quota windows from the Codex CLI ChatGPT quota source when available. The collector MUST map the primary quota window to `five_hour` and the secondary quota window to `weekly`. If authentication, endpoint access, or response schema validation fails, the collector MUST degrade without interrupting snapshot or footer output.

#### Scenario: Codex endpoint provides trusted windows
- **WHEN** the Codex quota source returns primary and secondary windows with used percentages and reset timestamps
- **THEN** the `cdx` provider snapshot MUST set `source_status` to `fresh`
- **THEN** the `cdx` provider snapshot MUST populate `windows.five_hour` and `windows.weekly`

#### Scenario: Codex trusted source fails safely
- **WHEN** Codex auth is missing, expired, inaccessible, or the quota response is malformed
- **THEN** Stage 8 MUST continue building the snapshot
- **THEN** the `cdx` provider MUST fall back to estimated local data if available, otherwise `unknown`

### Requirement: Estimated fallback display
Stage 8 SHALL allow local token or session data to be displayed only as estimated fallback when trusted provider data is unavailable. Estimated provider output MUST be visually distinct from fresh and stale trusted output by appending `?` to the provider abbreviation and using the estimated tmux style.

#### Scenario: Estimated provider is visibly marked
- **WHEN** a provider value is derived from local token or session data because the trusted source is unavailable
- **THEN** the provider `source_status` MUST be `estimated`
- **THEN** the footer MUST append `?` to the provider abbreviation, such as `cc?` or `cdx?`
- **THEN** the estimated value MUST use the configured estimated style instead of the normal low/warning/critical quota style

#### Scenario: Trusted refresh replaces estimated data
- **WHEN** a provider previously rendered estimated data
- **AND** a later refresh obtains trusted provider data
- **THEN** the new snapshot MUST use the trusted provider data
- **THEN** the footer MUST remove the `?` marker for that provider

### Requirement: Cost cache state permissions
Stage 8 SHALL create and maintain the cost cache directory with owner-only permissions on POSIX systems. Snapshot and lock files MUST NOT require group or world access.

#### Scenario: Cache directory is owner-only
- **WHEN** Stage 8 writes or locks the cost snapshot cache
- **THEN** the cache directory permissions MUST be restricted to the owner on POSIX systems

## MODIFIED Requirements

### Requirement: Provider windows and reset displays

Stage 8 SHALL render Codex and Claude Code 5-hour and weekly quota windows when trusted provider data exists. The 5-hour reset display MUST use the configured timezone and `HH:MM` format. The weekly reset display MUST use a relative format such as `3d`. If trusted data is unavailable but local token or session fallback data exists, Stage 8 MAY render an estimated value only with `source_status=estimated` and the estimated footer marker. If neither trusted nor estimated data is available, the field MUST render as `--`.

#### Scenario: Five-hour reset uses configured timezone

- **WHEN** the configured timezone is `Asia/Taipei` and a provider reset timestamp converts to `15:21`
- **THEN** the footer MUST render the 5-hour window as `5h:<used>%(15:21)`

#### Scenario: Unknown quota window is not estimated

- **WHEN** Codex or Claude Code does not provide trusted 5-hour or weekly quota data
- **AND** no local token or session fallback is available
- **THEN** the corresponding footer field MUST render `--`

#### Scenario: Local fallback is marked estimated

- **WHEN** Codex or Claude Code uses local token or session data because trusted quota data is unavailable
- **THEN** the corresponding provider MUST render with the estimated `?` marker

### Requirement: Copilot online usage source priority

Stage 8 SHALL treat GitHub Copilot account usage as account-level data, not host-local data. For personal accounts, the adapter MUST prefer GitHub user billing premium request usage reports. For company-managed accounts, the adapter MUST prefer configured organization or enterprise billing/report sources. Local Copilot session logs MAY be used only as fallback, MUST be bounded to the current billing month when deriving current-month request usage, and MUST be marked as `local_observed` with estimated provider status.

#### Scenario: Personal account uses user billing source

- **WHEN** a Copilot account is configured with `kind=personal`
- **THEN** the adapter MUST attempt a user-level GitHub billing/report source before local observed logs

#### Scenario: Company account uses organization or enterprise source

- **WHEN** a Copilot account is configured with `kind=company` and an organization or enterprise scope
- **THEN** the adapter MUST attempt that configured organization or enterprise source before local observed logs

#### Scenario: Local fallback is marked partial

- **WHEN** Copilot usage is derived from local session logs
- **THEN** the account snapshot MUST set `source` to `local_observed`
- **THEN** the provider snapshot MUST indicate the value is estimated rather than fresh

#### Scenario: Local fallback is month bounded

- **WHEN** local Copilot session logs include shutdown events from previous months and the current month
- **THEN** Stage 8 MUST count only events belonging to the current billing month for current-month fallback usage

### Requirement: Footer color thresholds

Stage 8 SHALL apply tmux style coloring by usage threshold. Usage below 70 percent MUST use the low-risk style. Usage from 70 through 89 percent MUST use the warning style. Usage at or above 90 percent MUST use the critical style. Unknown or error data MUST use a neutral or dim style. Estimated data MUST use the estimated style so operators can distinguish fallback estimates from trusted quota values.

#### Scenario: Threshold boundaries are deterministic

- **WHEN** provider usage is 69, 70, 89, and 90 percent
- **THEN** Stage 8 MUST classify them as low-risk, warning, warning, and critical respectively

#### Scenario: Copilot color uses allowance without showing max

- **WHEN** a Copilot account has `used_requests=270` and `monthly_allowance=300`
- **THEN** Stage 8 MUST classify that account as critical
- **THEN** the footer MUST display the used request count without displaying `/300`

#### Scenario: Estimated values use estimated style

- **WHEN** a provider has `source_status=estimated`
- **THEN** the footer MUST render that provider's estimated values using the estimated style instead of low-risk, warning, or critical styles
