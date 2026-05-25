## 1. Policy Artifact Loader

- [x] 1.1 Add failing tests for loading `secrets.yaml`, `classification.yaml`, `boundaries.yaml`, and missing-file errors.
- [x] 1.2 Implement `paulshaclaw.memory.policy.load_defaults()` and stable policy dataclasses / TypedDicts.
- [x] 1.3 Add local override fixture tests for `~/.config/paulshaclaw/policy.override.yaml` merge behavior.
- [x] 1.4 Implement deterministic `effective_policy_hash` over defaults + override.
- [x] 1.5 Add unsupported-major-version test and fail-closed behavior.

## 2. Redaction Engine

- [x] 2.1 Add regex detector fixtures for GitHub PAT, OpenAI / Anthropic keys, AWS key, JWT, bearer token, and private-key block marker.
- [x] 2.2 Implement cheap regex detector with rule IDs and line-level hit output.
- [x] 2.3 Add gitleaks wrapper tests using sanitized fixtures and mocked binary failures.
- [x] 2.4 Implement gitleaks detector wrapper and install-time binary validation.
- [x] 2.5 Implement line-level redaction merge for multiple hits on the same line.
- [x] 2.6 Assert redacted output never contains matched token fixtures.

## 3. Hook Boundary Integration (`external_to_raw`)

- [x] 3.1 Add failing hook tests: payload with obvious token writes redacted queue payload.
- [x] 3.2 Wire hook scripts to call cheap regex before atomic queue write.
- [x] 3.3 Add hook metadata for `redaction_stage=hook`, hit counts, and effective policy hash.
- [x] 3.4 Ensure hook failure still exits zero to host CLI but writes safe logs only.

## 4. Importer Boundary Integration (`raw_to_distilled`)

- [x] 4.1 Add failing importer tests for gitleaks-only hit missed by hook regex.
- [x] 4.2 Wire importer to call `policy.check_boundary("raw_to_distilled", ...)` before frontmatter / inbox write.
- [x] 4.3 Ensure inbox receives redacted content and redaction metadata.
- [x] 4.4 Ensure `archive/queue/` stores only redacted queue snapshots for policy-hit items.
- [x] 4.5 Ensure original queue payload is unlinked after successful policy-hit processing.

## 5. Classification

- [x] 5.1 Add fixtures for known `paulshaclaw` project, unknown project, redaction-hit session, and override project.
- [x] 5.2 Implement `classification.yaml` defaults with levels `public`, `private`, `secret`.
- [x] 5.3 Add frontmatter fields `classification_level`, `classification_reason`, `classification_policy_hash`, `classification_source`.
- [x] 5.4 Implement fail-open classification fallback to `private` with warning.
- [x] 5.5 Add rule ensuring any redaction hit downgrades classification to `private`.

## 6. Audit and Ledger

- [x] 6.1 Add failing tests for policy audit JSONL shape and no matched string persistence.
- [x] 6.2 Implement `~/.agents/memory/runtime/audit/policy.jsonl` writer.
- [x] 6.3 Extend importer ledger records with redaction / classification / policy hash metadata.
- [x] 6.4 Enforce publish ordering: sanitized output prepared → audit + ledger append → atomic inbox publish.
- [x] 6.5 Add ledger-unavailable test: output not published, failure stub written, policy log warning emitted.

## 7. Fail-Closed and `_failed/` Stubs

- [x] 7.1 Add tests for policy load failure, gitleaks missing, gitleaks non-zero, audit write failure, ledger write failure.
- [x] 7.2 Implement retry policy from `boundaries.yaml`.
- [x] 7.3 Implement metadata-only failure stubs in `runtime/queue/_failed/`.
- [x] 7.4 Assert `_failed/` stubs never contain original payload, matched strings, or conversation lines.

## 8. Override, Dry-Run, Replay

- [x] 8.1 Add override tests for `disable_rules` and `disable_rules_for_session`.
- [x] 8.2 Implement local override loader and merge validation.
- [x] 8.3 Implement `psc memory dry-run-policy <session-id>` output with rule ID, detector, line number, action, classification result, and effective hash.
- [x] 8.4 Assert dry-run does not write inbox and does not print matched strings.
- [x] 8.5 Wire `psc memory replay --session <session-id>` to rerun importer with current effective policy.

## 9. Consumer Enforcement

- [x] 9.1 Define memory consumer marker / discovery convention for Python modules.
- [x] 9.2 Add failing CI lint fixture for a consumer that writes memory without policy API call.
- [x] 9.3 Implement `paulshaclaw/memory/lint/policy_consumer_lint.py`.
- [x] 9.4 Wire lint into existing Stage 2 integration check or documented verification command.

## 10. Documentation and Verification

- [x] 10.1 Update importer MVP docs to reference Topic 8 redaction/classification contract.
- [x] 10.2 Update README with design spec and OpenSpec change paths.
- [x] 10.3 Run focused policy test suite.
- [x] 10.4 Run existing repository tests that are present.
- [x] 10.5 Record verification summary at the bottom of this file.

## Verification Summary

- Focused Topic 8 suite: `python3 -m unittest tests.test_stage2_memory_policy tests.test_stage2_memory_policy_cli tests.test_stage2_memory_policy_lint -v` → 49 tests passed.
- Stage 2 integration guard: `bash paulshaclaw/memory/tests/stage2_integration_check.sh` → `[stage2] ok`.
- Full repository suite: `python3 -m unittest discover -s tests -v` → 301 tests run, 1 known pre-existing worktree-specific failure in `tests/test_stage9_project_monitor.py::Stage9SnapshotTests::test_paulshaclaw_self_snapshot_matches_known_state`; no new Topic 8 regressions.
- Task-level subagent review loop: loader, boundary engine, and CLI/lint all passed spec compliance review and code-quality review after follow-up fixes.
- Final code review: no remaining critical/important issues after fixing gitleaks temp-file location and wiring runtime audit emission.
- Policy check: `policy_check unavailable` in this environment; relied on focused suites + full-suite regression signal instead.
