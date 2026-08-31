## Context

The release entry point already uses the installed interpreter and does not import
the repository worktree. Live evidence therefore isolates three independent
failures: incomplete wheel package data, manager-lock path drift after Cortex
instance extraction, and a CLI/documentation mismatch. All three must be fixed
before a successful source-tree test can support an installed-runtime claim.

## Goals / Non-Goals

**Goals:**

- Make the wheel self-contained for command registry loading.
- Reuse a live Cortex manager instead of starting the release fallback.
- Preserve both documented and existing `--no-cockpit` invocation forms.
- Prove startup and cleanup using the pipx-installed executable outside the repo.

**Non-Goals:**

- No new `ready` or `clean-stop` CLI commands.
- No change to Cortex ownership, deployment, or lock acquisition.
- No repo-worktree import fallback for missing wheel data.
- No silent skip of Telegram or manager readiness failures.

## Decisions

### Package immutable runtime data explicitly

Declare `commands.json` as package data for `paulshaclaw.core`. A regression test
builds a wheel and inspects the archive, so passing from a source checkout cannot
mask a broken release artifact.

### Probe both supported manager-lock layouts

The supervisor checks the Cortex instance layout and the legacy flat layout. A
file's existence is not success: each candidate is considered live only when a
non-blocking exclusive flock fails. An absent or stale file remains free. The
launcher does not take ownership of Cortex lock creation.

### Keep CLI compatibility at one entry point

Argparse accepts `--no-cockpit` before the implicit default command and after the
explicit `up` command. Both normalize to `_cmd_up(no_cockpit=True)`. `down` and
`status` retain their current behavior, and no status-word subcommands are added.

### Separate deterministic gates from live acceptance

Unit tests cover archive contents, flag normalization, and lock behavior. Final
acceptance rebuilds and force-reinstalls the wheel into pipx, records executable,
import path, version, and wheel digest, then starts the installed command from two
non-repo directories. One run uses top-level `--no-cockpit`; one bare run uses a
controlled tmux pane. Each run must reach ready state and leave no child or stale
start lock after termination.

## Risks / Trade-offs

- Probing two lock layouts could mistake a stale file for a daemon. Kernel flock
  prevents that: only a held lock counts as live.
- Building a wheel in tests adds bounded test time. It is necessary because the
  defect exists only in the artifact boundary.
- Live startup touches local runtime processes. It is reserved for final
  verification and must always perform explicit cleanup.

## Migration Plan

1. Add and observe RED tests for each confirmed defect.
2. Apply the minimal packaging, lock-probe, and parser changes.
3. Run focused and full test gates.
4. Build a wheel and inspect its contents.
5. Force-reinstall the wheel into the existing pipx environment.
6. Run and cleanly stop installed startup probes from two non-repo directories.

Rollback is reinstalling the prior wheel. Runtime state under `~/.agents/` is not
migrated or deleted.

## Open Questions

No blocking question remains. The installed-runtime evidence, not source-tree
behavior, decides completion.
