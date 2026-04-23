## 1. Stage 11 scaffolding

- [ ] 1.1 Decide and add the Stage 11 cockpit entry point and package/module layout
- [ ] 1.2 Add the terminal UI dependency and any minimal runtime wiring needed to launch the cockpit
- [ ] 1.3 Create the Stage 11 module boundaries for UI, cockpit store, tmux adapter, artifact adapter, and layout action service

## 2. tmux and cockpit state

- [ ] 2.1 Implement tmux pane discovery and metadata loading for live pane state
- [ ] 2.2 Implement startup active-slot selection from the largest non-cockpit pane with self-pane exclusion
- [ ] 2.3 Implement cockpit store/state for active slot, selection, segmented work list, and degraded flags

## 3. Interactive cockpit behavior

- [ ] 3.1 Build the Textual cockpit layout for active slot, work list, selected pane detail, and global jobs
- [ ] 3.2 Implement keyboard navigation for pane selection and explicit return to the cockpit pane
- [ ] 3.3 Implement `Enter`-triggered swap between selected pane and active slot with post-swap tmux reconciliation and default focus jump to the new active pane

## 4. Artifact merge and validation

- [ ] 4.1 Implement artifact-backed job/trace loading with best-effort fallback for unmapped panes
- [ ] 4.2 Add degraded-state handling for missing artifact coverage and lost active slot
- [ ] 4.3 Add unit tests for active-slot selection, self-pane exclusion, work-list segmentation, and fallback state handling
- [ ] 4.4 Add integration or end-to-end tests covering swap behavior, tmux reconciliation, focus jump, and return-to-cockpit flow
