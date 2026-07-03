## ADDED Requirements

### Requirement: MOC reconcile dedup deletions are recorded in the lifecycle ledger

When the MOC naming reconcile pass deletes a file to resolve a duplicate `slice_id` (or removes an older file it overwrites during rename), it SHALL append a lifecycle event to `runtime/ledger/lifecycle.jsonl` via the lifecycle ledger API, recording the deletion with `event_type` `superseded`, the `slice_id` as `record_id`, a `reason` identifying the moc dedup, and metadata identifying the deleted and kept paths. No reconcile deletion may be unrecorded.

The reconcile pass's choice of **which** file survives MUST remain identical to the pre-change behavior — only the ledger trace is added. These audit-only lifecycle events MUST NOT change the slice's effective lifecycle state or lifecycle-based recency semantics. A lifecycle-ledger write failure MUST NOT abort the pass; it degrades to the existing warning and the pass continues.

#### Scenario: Duplicate slice_id dedup emits a lifecycle event

- **WHEN** reconcile finds two files with the same `slice_id` and deletes the older one
- **THEN** a lifecycle event recording the deletion (`slice_id`, deleted path, kept path, reason) is appended to the lifecycle ledger, and the surviving file is the same one reconcile would have kept before this change

#### Scenario: Ledger write failure does not abort the pass

- **WHEN** the lifecycle ledger append raises during a reconcile dedup
- **THEN** reconcile still completes the pass (degrading to the existing warning) and does not propagate the error

#### Scenario: Deletion selection is unchanged

- **WHEN** reconcile dedups duplicate `slice_id`s
- **THEN** which file is deleted versus kept is identical to the behavior before this change (the ledger trace is purely additive)
