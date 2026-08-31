## 1. RED Regression Tests

- [x] 1.1 Add a test that builds the wheel and asserts
  `paulshaclaw/core/commands.json` is present in the archive.
- [x] 1.2 Add supervisor tests for held and stale nested Cortex instance locks,
  preserving the legacy flat lock behavior.
- [x] 1.3 Add CLI tests for both top-level and explicit-`up` `--no-cockpit` forms;
  do not add `ready` or `clean-stop` commands.
- [x] 1.4 Run the RED tests and record that each fails for its intended defect.

## 2. Minimal Implementation

- [x] 2.1 Add the command registry JSON to setuptools package data.
- [x] 2.2 Extend manager-lock detection to the Cortex instance layout while
  retaining kernel-flock semantics.
- [x] 2.3 Normalize both supported `--no-cockpit` invocation forms to the same
  supervisor call.

## 3. Deterministic Verification

- [x] 3.1 Run focused launcher, supervisor, and wheel-content tests.
- [x] 3.2 Run the full pytest suite and policy/OpenSpec gates.
- [ ] 3.3 Complete standard and adversarial review; any unaddressed root cause or
  installed-artifact gap is a failing finding.

## 4. Installed Runtime Acceptance

- [x] 4.1 Build the wheel, record its SHA-256, and verify archive contents.
- [x] 4.2 Force-reinstall that wheel into pipx and record executable, import path,
  and version.
- [x] 4.3 From `/tmp`, start the installed top-level
  `paulshaclaw --no-cockpit`, observe ready state, terminate, and verify cleanup.
- [x] 4.4 From a second non-repository directory, start bare installed
  `paulshaclaw` in a controlled tmux pane, observe cockpit ready state, terminate,
  and verify cleanup.
