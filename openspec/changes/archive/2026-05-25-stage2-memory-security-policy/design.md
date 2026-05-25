## Context

Stage 2 Topic 1 defines the memory substrate layers and Topic 2 defines the importer MVP. Topic 8 is the memory security policy layer that every Stage 2 component must use. The full design rationale lives at `docs/superpowers/specs/2026-05-24-stage2-memory-security-policy-design.md`; this OpenSpec design summarizes the implementation shape and references that document for detail.

## Decisions

### Policy is a cross-cutting contract, not importer-local behavior

`paulshaclaw.memory.policy` is the single supported API for policy execution. The importer is the first consumer, but later `paulsha-mem-moc`, retrieval, wake-up, and dream / janitor components must use the same boundary API and audit semantics.

### Boundary vocabulary follows the existing Stage 2 layer model

The policy layer defines five boundary IDs: `external_to_raw`, `raw_to_distilled`, `distilled_to_canonical`, `canonical_to_indexed`, and `indexed_to_consumer`. MVP only executes the two ingress boundaries. The other three are schema placeholders for future sub-specs.

### Policy artifacts are repo defaults plus local override

Defaults live under `paulshaclaw/memory/policy/` as `secrets.yaml`, `classification.yaml`, and `boundaries.yaml`. Local user-specific rules live in `~/.config/paulshaclaw/policy.override.yaml`. The loader merges them and computes `effective_policy_hash`; ledger and audit records include that hash.

### Redaction is line-level and raw-secret persistence is forbidden

Hooks apply cheap regex line redaction before writing queue payloads. Importer-side gitleaks runs at `raw_to_distilled`; if it finds a secret missed by hook regex, only redacted output may be written to inbox or archive. `archive/queue/` and `runtime/queue/_failed/` MUST NOT store original matched lines. Policy-error failures write metadata stubs only and unlink queue payloads.

### Classification is rule-based and conservative

Classification levels are `public`, `private`, and `secret`. Unknown projects default to `private`; any redaction hit downgrades to `private`; `secret` must not enter indexed or consumer boundaries. Classification failure is fail-open with `private` fallback and warning because it is recoverable.

### Audit is split by question

Importer ledger records session-level decisions. `~/.agents/memory/runtime/audit/policy.jsonl` records rule-level policy events. Both include session reference, policy version, and effective policy hash, but neither may include matched secret text or original line content.

### False-positive handling is local override plus dry-run

Operators use `psc memory dry-run-policy <session-id>` to inspect rule IDs, line numbers, detectors, and actions without writing inbox. They can then add audited local overrides and replay the session. Overrides are local-only and become part of the effective policy hash.

### Enforcement combines API ownership and CI lint

Consumers must call `paulshaclaw.memory.policy` for owned boundaries. CI lint prevents new memory consumers from bypassing the policy API. Cross-language enforcement is deferred until non-Python memory components exist.

## Risks / Trade-offs

- **Queue payload semantics change**: Topic 2 described queue archives as raw payload archives. Topic 8 tightens that for policy-hit and policy-error paths: memory tooling may not preserve original matched lines. Tests must encode this precedence.
- **gitleaks dependency**: Importer-side policy requires gitleaks. Install must either provide a pinned binary/package or validate an existing binary before enabling importer processing.
- **False positives**: Line-level redaction may remove useful context. Dry-run and local overrides provide an auditable recovery loop without storing secret values.
- **Audit write failures**: Since audit / ledger are required for safe publishing, fail-closed boundaries cannot publish output if audit or ledger append fails after retry.
- **CI lint brittleness**: Initial lint can be conservative and Python-only. Future non-Python consumers need a separate enforcement story.

## Migration Plan

| Step | Action |
|---|---|
| 1 | Add policy default YAML files and loader with effective hash computation. |
| 2 | Add redaction engine with regex detector and gitleaks detector wrapper. |
| 3 | Wire hooks to run cheap regex before queue write. |
| 4 | Wire importer `raw_to_distilled` policy call before inbox write and archive move. |
| 5 | Add classification frontmatter fields and importer metadata. |
| 6 | Add audit JSONL writer and ledger metadata extensions. |
| 7 | Add override loader, dry-run command, and replay integration. |
| 8 | Add policy consumer CI lint. |
| 9 | Run focused policy tests plus existing Stage 2 importer tests. |

Rollback: disable policy integration by reverting hook/importer wiring. Do not delete local policy audit or ledger records. Since raw memory content remains outside the repository, rollback only affects tooling behavior.

## Open Questions

1. Should future `paulsha-mem-moc` promotion allow `private` artifacts into canonical memory or keep them inbox-only for some projects?
2. Should policy audit rotation belong to Topic 8 follow-up or the dream / janitor sub-spec?
