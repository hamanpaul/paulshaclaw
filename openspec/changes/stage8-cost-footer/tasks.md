## 1. Stage 8 module scaffolding

- [x] 1.1 Create `paulshaclaw/cost/` package with import-safe modules for models, config, cache, providers, formatter, and CLI entry points.
- [x] 1.2 Add dataclasses and JSON serialization for provider-neutral cost snapshots, provider windows, and Copilot account usage.
- [x] 1.3 Add config loading for Stage 8 defaults: timezone `Asia/Taipei`, cache TTL `120`, tmux refresh interval `30`, color thresholds `70/90`, and config-driven Copilot accounts.

## 2. Provider adapters

- [x] 2.1 Implement Codex adapter with local session parsing style compatible with existing `token_count` session records and unknown output for missing trusted quota windows.
- [x] 2.2 Implement Claude Code adapter as best-effort 5h/weekly source with credential-safe access, timeout handling, and stale-cache fallback.
- [x] 2.3 Implement Copilot account adapter with config-driven account definitions and source priority for personal user billing, company org/enterprise billing, premium request reports, and local observed fallback.
- [x] 2.4 Ensure provider errors are isolated so one failed provider does not remove other provider data from the snapshot.

## 3. Cache and formatter

- [x] 3.1 Implement snapshot cache under `~/.agents/state/cost/` with `snapshot.json`, `snapshot.lock`, TTL reuse, lock-busy fallback, and stale preservation on refresh failure.
- [x] 3.2 Implement footer formatter for `cdx`, `cc`, and `cpt` with balanced one-line output, stale marker `~`, unknown marker `--`, and config-order Copilot account rendering.
- [x] 3.3 Implement tmux style color classification for low, warning, critical, and neutral/error states without displaying Copilot max allowance.

## 4. CLI and startup integration

- [x] 4.1 Implement `python -m paulshaclaw.cost --once` JSON snapshot output.
- [x] 4.2 Implement `python -m paulshaclaw.cost.status` one-line tmux footer output that exits 0 for degraded display cases.
- [x] 4.3 Update `scripts/start.sh` to apply session-local Stage 8 `status-right` and `status-interval 30` before launching Stage 11 cockpit, while preserving existing `status-right`.

## 5. Tests and validation

- [x] 5.1 Add unit tests for snapshot schema serialization, config-driven Copilot accounts, provider fallback status, reset display formatting, and threshold boundaries.
- [x] 5.2 Add cache tests for fresh reuse, stale refresh, lock-busy old-cache read, refresh failure preservation, and secret redaction.
- [x] 5.3 Add CLI contract tests for `--once`, `.status`, missing credentials, and provider-specific failure isolation.
- [x] 5.4 Add `scripts/start.sh` tests for session-local tmux options, status interval, existing `status-right` preservation, and no `~/.tmux.conf` writes.
- [x] 5.5 Run focused Stage 8 tests plus full `python -m unittest discover -s tests -v`, then record any tmux-environment-only skip or failure.

## 6. Documentation and handoff

- [x] 6.1 Update user-facing docs or config samples with Stage 8 config fields and Copilot account examples.
- [x] 6.2 Add evidence notes for commands run and any provider limitations found during implementation.
- [x] 6.3 Re-run `openspec status --change stage8-cost-footer` and `openspec validate stage8-cost-footer --strict` before implementation handoff.
