## Why

Issue #330 is a docs-only Stage 11 closeout follow-up after PR #329 merged and
issue #322 closed. The closeout needed explicit OpenSpec metadata so strict
validation could represent this docs-only bookkeeping work without inventing a
spec delta.

## What Changes

- Record the docs-only closeout metadata in
  `openspec/changes/archive/2026-08-29-cockpit-jobs-three-axis-closeout/`.
- Keep the Stage 11 closeout bookkeeping limited to the existing todo updates,
  archived OpenSpec record, and closeout changelog fragment.
- Leave merge, and the GitHub auto-closure triggered by `Closes #330`, to the
  Manager-controlled merge flow.

## Capabilities

### New Capabilities

- None. This change introduces no new runtime or user-facing behavior.

### Modified Capabilities

- None. This is a docs-only closeout change; `.openspec.yaml` sets
  `skip_specs: true`.

## Impact

- `openspec/changes/archive/2026-08-29-cockpit-jobs-three-axis-closeout/`
- `changelog.d/cockpit-jobs-three-axis-closeout.md`
- `docs/superpowers/workstreams/stage11-operator-cockpit/todo.md`
- `docs/superpowers/workstreams/cockpit-jobs-three-axis-closeout/todo.md`
- No source code, dependency, or runtime changes; this closeout only updates
  docs-only bookkeeping artifacts
