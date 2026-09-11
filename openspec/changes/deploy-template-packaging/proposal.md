## Why

Stage 7 deploy templates are release assets, but source-tree success alone does not prove that
wheel, sdist, and an sdist-rebuilt wheel carry the same usable template set. Install and upgrade
also need a fail-closed preflight boundary so a missing template cannot create partial host state.

## What Changes

- Declare deploy templates as package data with a setuptools floor that supports the recursive
  pattern used by the package.
- Use one stdlib-only artifact checker from PR CI, the local release entry point, and the tag
  release workflow for source/wheel/sdist parity and forbidden-content checks.
- Render every install/upgrade template before host writes or checkpoints; preserve checksum
  failures as exit 2 and report template failures as one JSON document with exit 1.
- Exercise the installed wheel outside the checkout and keep no-systemd verification honest.
- Make the pytest and local preflight environments install the build frontend before packaging
  acceptance tests run.

## Capabilities

### New Capabilities

<!-- 無；本 change 強化既有 Stage 7 deploy capability。 -->

### Modified Capabilities

- `stage7`: release template packaging, artifact verification, and pre-write deployment
  validation become explicit parts of the deploy contract.

## Impact

- Packaging: `pyproject.toml`, release workflows, and shared artifact checking.
- Runtime: deploy install/upgrade preflight and machine-readable failure reports.
- Verification: packaging, clean-venv installed-wheel, and existing Stage 7 tests.
- Lifecycle boundary: this active change contains implementation and pre-archive verification
  only; archive, merge, release publication, and issue closure are outside its scope.
