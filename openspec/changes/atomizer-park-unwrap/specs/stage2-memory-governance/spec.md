## ADDED Requirements

### Requirement: Object-wrapped JSON array unwrap in promotion parsing

The atomizer JSON extraction SHALL unwrap a top-level JSON object whose only array-valued key is drawn from the whitelist {`findings`, `slices`, `proposals`, `atoms`}, treating that array as the proposals payload. Extraction of a bare top-level array and of multiple valid arrays MUST continue to behave exactly as before this change.

#### Scenario: Object-wrapped non-empty array extracts to slices

- **WHEN** the model returns `{"findings": [ {…}, {…} ]}`
- **THEN** the parser unwraps the `findings` array and extracts the two slice proposals

#### Scenario: Object-wrapped empty array reaches the slices=0 terminal state

- **WHEN** the model returns `{"findings": []}`
- **THEN** the parser yields an empty array and the session reaches the `slices=0` terminal state (promoted, fragments archived, cache cleared) rather than being parked

#### Scenario: Bare array and multiple arrays are unchanged

- **WHEN** the output is a bare top-level JSON array, or contains multiple valid top-level arrays
- **THEN** extraction behaves identically to the pre-change parser

#### Scenario: Object with multiple or non-whitelisted array keys is not unwrapped

- **WHEN** the top-level object has more than one array-valued key, or its array key is not in the whitelist
- **THEN** the parser does NOT unwrap it (no false-positive extraction)

### Requirement: Atomizer prompt forbids execution and prose

The atomize-knowledge-slice prompt SHALL instruct the model to return only an inline JSON array, and to NOT perform file create/write actions and NOT return prose, so that "wrong-task" replies (which produce no JSON) are prevented at the source.

#### Scenario: Prompt states the inline-array-only contract

- **WHEN** the atomizer prompt is rendered for a promotion attempt
- **THEN** it explicitly requires an inline JSON array response and forbids file-creating/writing actions and prose narration
