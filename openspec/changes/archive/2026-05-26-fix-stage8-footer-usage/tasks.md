## 1. Test-First Coverage

- [x] 1.1 Add formatter tests for `source_status=estimated`, `?` provider suffix, and estimated tmux style.
- [x] 1.2 Add Claude collector tests for trusted statusline sidecar parsing, malformed/missing sidecar fallback, local estimated fallback, and gemma4/vLLM exclusion.
- [x] 1.3 Add Codex collector tests for trusted quota payload parsing, auth/HTTP/schema failure fallback, and local estimated fallback.
- [x] 1.4 Add Copilot tests for current-month local observed filtering and estimated provider status when billing API is unavailable.
- [x] 1.5 Add status/degraded tests proving configured Copilot accounts render as `cpt label:--` when no snapshot is available.
- [x] 1.6 Add cache permission test for owner-only cost cache directory behavior on POSIX systems.

## 2. Formatter and Model Semantics

- [x] 2.1 Extend provider label rendering so `estimated` providers use a `?` suffix while preserving `~` for stale providers.
- [x] 2.2 Add estimated tmux color/style support without changing low/warning/critical threshold classification for trusted values.
- [x] 2.3 Ensure `CostSnapshot` serialization/deserialization preserves `source_status=estimated` and local fallback source notes without secrets.

## 3. Provider Configuration

- [x] 3.1 Add backward-compatible Claude provider config for statusline sidecar path, local fallback controls, and max age.
- [x] 3.2 Add backward-compatible Codex provider config for enabling trusted quota lookup, auth path, endpoint/base URL, local fallback controls, and max age.
- [x] 3.3 Keep existing Copilot account config unchanged while adding any internal knobs needed for month-bounded local observed fallback.

## 4. Provider Collectors

- [x] 4.1 Implement Claude trusted sidecar reader that maps `five_hour` and `seven_day` rate limits into `UsageWindow` entries.
- [x] 4.2 Implement Claude estimated fallback that uses only Claude Code local data and excludes gemma4/vLLM/OpenAI-compatible local model records.
- [x] 4.3 Implement Codex trusted quota reader that maps primary and secondary quota windows into `five_hour` and `weekly`.
- [x] 4.4 Implement Codex estimated fallback from local Codex session/token data without treating it as trusted quota.
- [x] 4.5 Update Copilot local observed fallback to count only current-month events and mark local observed output as estimated.
- [x] 4.6 Update `collect_all()` to pass provider config into Claude/Codex collectors while preserving existing no-config degraded behavior.

## 5. Status, Cache, and Security

- [x] 5.1 Update degraded snapshot/fallback construction so configured Copilot accounts stay visible as `cpt label:--` where config is available.
- [x] 5.2 Harden `SnapshotCache` directory creation to owner-only permissions on POSIX systems.
- [x] 5.3 Ensure provider errors do not print tokens, credential contents, or sensitive auth payloads to stdout/stderr/cache.

## 6. Documentation and Validation

- [x] 6.1 Update Stage 8 docs/spec notes that currently describe Claude/Codex as pure stubs.
- [x] 6.2 Run `python3 -m unittest tests.test_stage8_cost -v` from the worktree and fix regressions.
- [x] 6.3 Run OpenSpec validation/status checks for `fix-stage8-footer-usage`.
- [x] 6.4 Prepare the change for code review, archive after implementation, then run policy checks before commit/push/PR.
