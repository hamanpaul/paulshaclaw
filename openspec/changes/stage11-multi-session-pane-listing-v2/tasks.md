## 1. Pane Model And Tmux Enumeration

- [ ] 1.1 Extend `PaneRecord` with `session_name` and `window_index`
- [ ] 1.2 Update `LIST_PANES_FORMAT` to include `#{session_name}` and `#{window_index}`
- [ ] 1.3 Change `TmuxClient.list_panes()` to call `tmux list-panes -a -F <format>`
- [ ] 1.4 Update `parse_list_panes()` to parse and validate the expanded all-session format
- [ ] 1.5 Update existing tmux parser tests and add all-session list command coverage

## 2. Cockpit State Semantics

- [ ] 2.1 Add `cockpit_session_name` to `CockpitState`
- [ ] 2.2 Update `CockpitState.from_panes()` and `choose_startup_slot()` to require `cockpit_session_name`
- [ ] 2.3 Scope active-slot startup selection and refresh reconciliation to the cockpit session
- [ ] 2.4 Keep all non-cockpit non-active panes in the candidate section and sort by `(session_name, window_index, pane_id)`
- [ ] 2.5 Add state tests for cross-session active-slot filtering, anchor collisions, candidate sorting, and refresh behavior

## 3. Startup And UI Rendering

- [ ] 3.1 Derive `cockpit_session_name` in `paulshaclaw/cockpit/__main__.py` from the cockpit pane record
- [ ] 3.2 Preserve the existing exit status `1` path when the cockpit pane cannot be found
- [ ] 3.3 Update active-slot and candidate labels to include `session:window` origin
- [ ] 3.4 Add startup and UI tests for session derivation and rendered labels

## 4. Hotkey Help

- [ ] 4.1 Add descriptions for the existing cockpit bindings
- [ ] 4.2 Add the `?` binding and `action_show_help()`
- [ ] 4.3 Create `paulshaclaw/cockpit/help.py` with `HelpModal`
- [ ] 4.4 Add help modal tests for opening, escape dismissal, and binding text coverage

## 5. Validation And Handoff

- [ ] 5.1 Add a multi-session e2e smoke test where a pane from another session appears in the candidate list
- [ ] 5.2 Run `.venv/bin/python -m pytest tests/test_stage11_operator_cockpit.py tests/test_stage11_operator_cockpit_e2e.py -v`
- [ ] 5.3 Update implementation notes or workstream evidence if the implementation changes from this design
