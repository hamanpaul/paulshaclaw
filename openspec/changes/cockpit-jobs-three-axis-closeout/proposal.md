## Why

Issue #330 is a docs-only Stage 11 closeout follow-up after PR #329 merged and
issue #322 closed. The active OpenSpec change needs proposal metadata and an
explicit docs-only marker so strict validation can represent the pre-archive
bookkeeping work without inventing a spec delta.

## What Changes

- Add the missing OpenSpec proposal and docs-only change metadata for
  `cockpit-jobs-three-axis-closeout`.
- Keep the Stage 11 closeout bookkeeping limited to the existing todo updates
  and dedicated tracking artifacts.
- Leave archive, merge, and issue closure to the later Manager-controlled flow.

## Capabilities

### New Capabilities

- None. This change introduces no new runtime or user-facing behavior.

### Modified Capabilities

- None. This is a docs-only closeout change; `.openspec.yaml` sets
  `skip_specs: true`.

## Impact

- `openspec/changes/cockpit-jobs-three-axis-closeout/`
- `docs/superpowers/workstreams/stage11-operator-cockpit/todo.md`
- `docs/superpowers/workstreams/cockpit-jobs-three-axis-closeout/todo.md`
- No source code, dependency, runtime, or archive content changes
