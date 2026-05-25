## Why

Stage 2 memory is becoming a real runtime subsystem under `~/.agents/memory/`. The importer MVP deliberately deferred secret redaction, classification governance, and consumer safety to sub-spec #8. Without a shared security policy layer, each future component (`importer`, `paulsha-mem-moc`, retrieval, wake-up, dream / janitor) would have to reinvent secret handling and classification rules, making leaks likely and audits inconsistent.

This change defines Topic 8 as the cross-cutting security contract for Stage 2 memory. It keeps actual memory content outside the repository, but gives all memory tooling in `paulshaclaw` one policy API, one set of policy artifacts, one audit contract, and one failure model.

## What Changes

- Add `paulshaclaw.memory.policy` as the only supported policy execution API for memory components.
- Add policy defaults under `paulshaclaw/memory/policy/{secrets,classification,boundaries}.yaml` plus local override at `~/.config/paulshaclaw/policy.override.yaml`.
- Define five boundary identifiers aligned with the existing Stage 2 layer model: `external_to_raw`, `raw_to_distilled`, `distilled_to_canonical`, `canonical_to_indexed`, `indexed_to_consumer`.
- Enforce MVP policy at the two ingress boundaries:
  - hook-side cheap regex at `external_to_raw`;
  - importer-side gitleaks + line redaction + classification tagging at `raw_to_distilled`.
- Write policy execution to both importer ledger and rule-level audit log without storing matched secret text.
- Add override / dry-run workflows for false-positive handling.
- Add CI lint so new memory consumers must call the policy boundary API.
- Clarify fail-closed behavior for redaction, fail-open-with-private-fallback behavior for classification, retry handling, and no-raw-secret persistence in queue archive / `_failed/`.

## Capabilities

### New Capabilities

None. This change extends the existing `stage2-memory-governance` capability with security policy requirements.

### Modified Capabilities

- `stage2-memory-governance`: Add memory security policy artifacts, boundary policy API, redaction, classification, audit, override, fail-mode, and CI enforcement requirements.

## Impact

- Affected runtime code (new): `paulshaclaw/memory/policy/`, `paulshaclaw/memory/policy_engine.py` or package equivalent, `paulshaclaw/memory/lint/policy_consumer_lint.py`.
- Affected importer code: hook queue writer and importer pipeline must call `paulshaclaw.memory.policy`, redact lines before inbox writes, write policy metadata, and use policy-safe failure stubs.
- Affected CLI: `psc memory dry-run-policy <session-id>` and `psc memory replay --session <session-id>`.
- Affected config: `~/.config/paulshaclaw/policy.override.yaml`; install validation for gitleaks.
- Affected tests: policy loader, redaction, gitleaks path, classification defaults, audit/ledger writes, override, dry-run, CI lint, fail-closed retry.
- Dependencies: gitleaks binary or pinned install path for importer-side scanning; PyYAML for policy files.
- Non-Goals: publish guard, `paulsha-mem-moc` rewrite, canonical/indexed boundary execution, cross-language policy SDK, ML classifier, event-bus integration, kill-switch.
