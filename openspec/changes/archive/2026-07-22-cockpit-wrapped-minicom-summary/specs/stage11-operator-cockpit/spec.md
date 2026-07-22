## ADDED Requirements

### Requirement: Work list identifies minicom panes even under a wrapper process
The Stage 11 cockpit SHALL label a pane that is running `minicom` by its serial console identity (e.g. `minicom COM0`) even when `minicom` was launched indirectly through a wrapper process, such that tmux reports the pane's current command as a shell (`bash`/`sh`/`zsh`/`dash`/`ash`/`fish`) rather than `minicom`.

When a pane has no usable title (empty, or equal to the host short name) and its tmux command is a shell, the cockpit SHALL attempt tty-based minicom detection (scanning the pane's tty for a `minicom` process and reading its COM port from its arguments) and, when a minicom process is found, SHALL use the derived `minicom COMx` label. When no minicom process is found on that tty, the cockpit SHALL fall back to the existing current-path (cwd basename) label. Panes whose tmux command is already `minicom` MUST keep their existing direct detection behavior unchanged.

#### Scenario: Wrapped minicom pane is labeled by its COM port
- **WHEN** a candidate pane has an empty title, its tmux `pane_current_command` is `bash` (a `serialwrap-minicom` wrapper), and a `minicom` process bound to `COM0` is running on that pane's tty
- **THEN** the cockpit MUST derive the pane summary as `minicom COM0` and MUST NOT fall back to the current-path basename

#### Scenario: Non-minicom shell pane still falls back to current path
- **WHEN** a candidate pane has an empty title, its tmux `pane_current_command` is `bash`, and no `minicom` process is running on that pane's tty
- **THEN** the cockpit MUST fall back to the current-path basename for the pane summary

#### Scenario: Directly launched minicom keeps existing detection
- **WHEN** a candidate pane has an empty title and its tmux `pane_current_command` is `minicom`
- **THEN** the cockpit MUST derive the pane summary from the existing minicom detection path unchanged
