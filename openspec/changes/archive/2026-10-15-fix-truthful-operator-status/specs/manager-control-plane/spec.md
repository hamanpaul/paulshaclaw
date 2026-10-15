## ADDED Requirements

### Requirement: Operator summaries preserve uncertainty and decision evidence
Claw frontends SHALL project the Cortex snapshot without claiming execution or completion from
request submission alone. Bot status SHALL include attention identifiers, supplied state, reason,
next_actions and next_step_hint, while retaining snapshot updated_at. Missing state and missing
failure reasons MUST be explicit unknown. Empty tick records MUST NOT fabricate a done result.

#### Scenario: Attention is visible in the bot summary
- **WHEN** Cortex supplies attention items with blocking reasons and available decisions
- **THEN** the bot SHALL present those upstream facts, without inventing executable recovery commands

#### Scenario: Submission has no completion record
- **WHEN** the tick request has been submitted and its completion record is not yet available
- **THEN** the frontend SHALL report queued and direct the operator to status
- **AND** a present but empty result record SHALL report unknown rather than done

#### Scenario: Long operator reply fits the transport contract
- **WHEN** a plain-text status reply exceeds a Telegram message limit
- **THEN** the listener SHALL send bounded chunks preserving all Unicode code points and text order
- **AND** it SHALL keep plain-text delivery without HTML or Markdown interpretation
