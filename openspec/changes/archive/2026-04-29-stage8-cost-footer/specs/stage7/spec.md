## ADDED Requirements

### Requirement: Local startup applies Stage 8 cost footer

Stage 7 SHALL ensure local startup can apply the Stage 8 cost footer to the current tmux session before launching the Stage 11 cockpit. The startup path MUST use session-local tmux options, MUST set `status-interval` to the configured Stage 8 refresh interval, MUST preserve any existing `status-right` value, and MUST NOT modify global `~/.tmux.conf`.

#### Scenario: Startup preserves existing status-right

- **WHEN** `scripts/start.sh` runs inside tmux and the current session already has a `status-right` value
- **THEN** the script MUST append or wrap the Stage 8 footer command without discarding the existing value

#### Scenario: Startup avoids global tmux config

- **WHEN** `scripts/start.sh` applies the Stage 8 footer
- **THEN** it MUST use session-local tmux settings rather than global `tmux set-option -g`
- **THEN** it MUST NOT write to `~/.tmux.conf`
