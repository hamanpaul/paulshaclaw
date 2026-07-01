from __future__ import annotations

from dataclasses import dataclass

from .models import PaneRecord, SlotAnchor


def choose_startup_slot(
    panes: tuple[PaneRecord, ...],
    *,
    cockpit_pane_id: str,
    cockpit_session_name: str,
) -> SlotAnchor | None:
    """The active slot = the largest non-cockpit pane **in the cockpit's own window**.

    Candidates elsewhere (other windows/sessions) remain selectable in the work list,
    but "active / in front of me" is a per-window notion: a bigger pane in a window the
    operator isn't looking at must not become the swap target (that made Enter appear to
    do nothing / swap panes across windows). Falls back to session-scope only when the
    cockpit pane's window can't be determined. Returns None (not raise) when the cockpit
    is alone in its window — the cockpit still runs, swap just has nowhere to land.
    """
    cockpit_window = next(
        (pane.window_index for pane in panes if pane.pane_id == cockpit_pane_id), None
    )
    candidates = tuple(
        pane
        for pane in panes
        if pane.pane_id != cockpit_pane_id
        and pane.session_name == cockpit_session_name
        and (cockpit_window is None or pane.window_index == cockpit_window)
    )
    if not candidates:
        return None
    winner = max(candidates, key=lambda pane: (pane.area, pane.width, pane.height, pane.pane_id))
    return winner.anchor


@dataclass(frozen=True)
class CockpitState:
    cockpit_pane_id: str
    cockpit_session_name: str
    slot_anchor: SlotAnchor | None
    panes: tuple[PaneRecord, ...]
    selected_index: int
    degraded_reason: str | None
    # The cockpit pane's window; the active slot is scoped to this window (None = unknown
    # → fall back to session-scope). Stable for the session; carried through refresh.
    cockpit_window_index: str | None = None

    @classmethod
    def from_panes(
        cls,
        panes: tuple[PaneRecord, ...],
        *,
        cockpit_pane_id: str,
        cockpit_session_name: str,
    ) -> "CockpitState":
        cockpit_window_index = next(
            (pane.window_index for pane in panes if pane.pane_id == cockpit_pane_id), None
        )
        slot_anchor = choose_startup_slot(
            panes,
            cockpit_pane_id=cockpit_pane_id,
            cockpit_session_name=cockpit_session_name,
        )
        return cls(
            cockpit_pane_id=cockpit_pane_id,
            cockpit_session_name=cockpit_session_name,
            slot_anchor=slot_anchor,
            panes=panes,
            selected_index=0,
            # No slot at all (cockpit alone in its window) is a normal "nowhere to
            # swap" state, NOT a lost active — don't cry "active-slot-lost".
            degraded_reason=None if slot_anchor is not None else "no-active-slot",
            cockpit_window_index=cockpit_window_index,
        )

    def _is_active_slot_pane(self, pane: PaneRecord) -> bool:
        return (
            self.slot_anchor is not None
            and pane.pane_id != self.cockpit_pane_id
            and pane.session_name == self.cockpit_session_name
            and (
                self.cockpit_window_index is None
                or pane.window_index == self.cockpit_window_index
            )
            and pane.anchor == self.slot_anchor
        )

    @property
    def active_section(self) -> tuple[PaneRecord, ...]:
        return tuple(pane for pane in self.panes if self._is_active_slot_pane(pane))

    @property
    def candidate_section(self) -> tuple[PaneRecord, ...]:
        candidates = (
            pane
            for pane in self.panes
            if pane.pane_id != self.cockpit_pane_id and not self._is_active_slot_pane(pane)
        )
        return tuple(
            sorted(
                candidates,
                key=lambda pane: (
                    pane.session_name,
                    int(pane.window_index) if pane.window_index.isdigit() else 0,
                    pane.pane_id,
                ),
            )
        )

    @property
    def active_pane(self) -> PaneRecord | None:
        for pane in self.active_section:
            return pane
        return None

    @property
    def selected_pane(self) -> PaneRecord | None:
        if not self.candidate_section:
            return None
        clamped = min(self.selected_index, len(self.candidate_section) - 1)
        return self.candidate_section[clamped]

    def move_selection(self, delta: int) -> "CockpitState":
        if not self.candidate_section:
            return self
        count = len(self.candidate_section)
        next_index = (self.selected_index + delta) % count
        return self.set_selection(next_index)

    def set_selection(self, index: int) -> "CockpitState":
        if not self.candidate_section:
            return self
        count = len(self.candidate_section)
        next_index = max(0, min(index, count - 1))
        return CockpitState(
            cockpit_pane_id=self.cockpit_pane_id,
            cockpit_session_name=self.cockpit_session_name,
            slot_anchor=self.slot_anchor,
            panes=self.panes,
            selected_index=next_index,
            degraded_reason=self.degraded_reason,
            cockpit_window_index=self.cockpit_window_index,
        )

    def refresh(self, panes: tuple[PaneRecord, ...]) -> "CockpitState":
        previous_selected = self.selected_pane
        # Self-heal against live layout changes (adversarial-review findings 1/2/3):
        # re-derive the cockpit's window from the fresh snapshot (survives window
        # renumber/move), and if the current slot no longer maps to a pane
        # (resize/zoom/split, or we started alone and panes have since appeared)
        # re-pick it — so swapping recovers instead of staying permanently degraded.
        # A slot that still maps to a pane is kept, so a pane swapped into it
        # predictably remains active.
        cockpit_window = next(
            (pane.window_index for pane in panes if pane.pane_id == self.cockpit_pane_id),
            self.cockpit_window_index,
        )

        def _rebuilt(anchor: SlotAnchor | None) -> "CockpitState":
            return CockpitState(
                cockpit_pane_id=self.cockpit_pane_id,
                cockpit_session_name=self.cockpit_session_name,
                slot_anchor=anchor,
                panes=panes,
                selected_index=self.selected_index,
                degraded_reason=None,
                cockpit_window_index=cockpit_window,
            )

        refreshed = _rebuilt(self.slot_anchor)
        if refreshed.active_pane is None:
            recovered = choose_startup_slot(
                panes,
                cockpit_pane_id=self.cockpit_pane_id,
                cockpit_session_name=self.cockpit_session_name,
            )
            if recovered is not None:
                refreshed = _rebuilt(recovered)

        candidate_count = len(refreshed.candidate_section)
        next_index = self.selected_index
        if candidate_count == 0:
            next_index = 0
        elif previous_selected is not None:
            for index, pane in enumerate(refreshed.candidate_section):
                if pane.pane_id == previous_selected.pane_id:
                    next_index = index
                    break
            else:
                next_index = min(next_index, candidate_count - 1)
        elif next_index >= candidate_count:
            next_index = candidate_count - 1
        # Distinguish "a slot existed but its pane vanished" (active-slot-lost) from
        # "there is no slot at all" (no-active-slot, e.g. cockpit alone in its window)
        # — the latter is normal, not a lost active (Copilot review PR #173).
        if refreshed.active_pane is not None:
            degraded_reason = None
        elif refreshed.slot_anchor is not None:
            degraded_reason = "active-slot-lost"
        else:
            degraded_reason = "no-active-slot"
        return CockpitState(
            cockpit_pane_id=self.cockpit_pane_id,
            cockpit_session_name=self.cockpit_session_name,
            slot_anchor=refreshed.slot_anchor,
            panes=panes,
            selected_index=next_index,
            degraded_reason=degraded_reason,
            cockpit_window_index=cockpit_window,
        )
