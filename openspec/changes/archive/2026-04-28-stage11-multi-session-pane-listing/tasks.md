## 1. Pane Model And Tmux Enumeration

- [x] 1.1 Extend `PaneRecord` with `session_name` and `window_index`
- [x] 1.2 Update `LIST_PANES_FORMAT` to include `#{session_name}` and `#{window_index}`
- [x] 1.3 Change `TmuxClient.list_panes()` to call `tmux list-panes -a -F <format>`
- [x] 1.4 Update `parse_list_panes()` to parse and validate the expanded all-session format
- [x] 1.5 Update existing tmux parser tests and add all-session list command coverage

## 2. Cockpit State Semantics

- [x] 2.1 Add `cockpit_session_name` to `CockpitState`
- [x] 2.2 Update `CockpitState.from_panes()` and `choose_startup_slot()` to require `cockpit_session_name`
- [x] 2.3 Scope active-slot startup selection and refresh reconciliation to the cockpit session
- [x] 2.4 Keep all non-cockpit non-active panes in the candidate section and sort by `(session_name, window_index, pane_id)`
- [x] 2.5 Add state tests for cross-session active-slot filtering, anchor collisions, candidate sorting, and refresh behavior

## 3. Startup And UI Rendering

- [x] 3.1 Derive `cockpit_session_name` in `paulshaclaw/cockpit/__main__.py` from the cockpit pane record
- [x] 3.2 Preserve the existing exit status `1` path when the cockpit pane cannot be found
- [x] 3.3 Update active-slot and candidate labels to include `session:window` origin
- [x] 3.4 Add startup and UI tests for session derivation and rendered labels

## 4. Hotkey Help

- [x] 4.1 Add descriptions for the existing cockpit bindings
- [x] 4.2 Add the `?` binding and `action_show_help()`
- [x] 4.3 Create `paulshaclaw/cockpit/help.py` with `HelpModal`
- [x] 4.4 Add help modal tests for opening, escape dismissal, and binding text coverage

## 5. Validation And Handoff

- [x] 5.1 Add a multi-session e2e smoke test where a pane from another session appears in the candidate list
- [x] 5.2 Run `.venv/bin/python -m pytest tests/test_stage11_operator_cockpit.py tests/test_stage11_operator_cockpit_e2e.py -v`
- [x] 5.3 Update implementation notes or workstream evidence if the implementation changes from this design
