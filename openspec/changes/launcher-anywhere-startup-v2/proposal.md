## Why

The pipx-installed `paulshaclaw 0.2.7` resolves through the correct console entry
point, but cannot complete release startup from an arbitrary directory. The wheel
omits the command registry JSON, the supervisor misses the live Cortex instance
lock and starts an obsolete fallback manager, and the documented top-level
`--no-cockpit` form is rejected by argparse. Source-tree tests currently do not
guard these installed-artifact boundaries.

## What Changes

- Package `paulshaclaw/core/commands.json` in built wheels and add a wheel-content
  regression test.
- Recognize the Cortex instance manager lock under
  `~/.agents/control/cortex/manager.lock` while preserving the existing flat lock
  contract and kernel-flock truth model.
- Accept both `paulshaclaw --no-cockpit` and the existing
  `paulshaclaw up --no-cockpit` form without adding new lifecycle subcommands.
- Add installed-wheel and launcher regressions, then validate the rebuilt pipx
  runtime from two non-repository directories, including ready and clean stop.

## Capabilities

### New Capabilities

None. This change repairs the existing release launcher and deployment contract.

### Modified Capabilities

- `stage1-core-runtime`: Align release launcher CLI and Cortex manager detection.
- `stage7`: Require release wheels to contain the runtime command registry and
  require installed-artifact startup acceptance.

## Impact

- Runtime code: `paulshaclaw/launcher/cli.py`,
  `paulshaclaw/launcher/supervisor.py`.
- Packaging: `pyproject.toml`.
- Tests: launcher CLI, supervisor lock detection, built-wheel content, and local
  installed-runtime smoke evidence.
- Compatibility: existing `up`, `down`, and `status` commands remain supported;
  no `ready` or `clean-stop` subcommand is introduced.
