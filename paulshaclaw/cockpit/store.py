from __future__ import annotations

from dataclasses import dataclass

from .models import PaneRecord, SlotAnchor


def choose_startup_slot(
    panes: tuple[PaneRecord, ...],
    *,
    cockpit_pane_id: str,
    cockpit_session_name: str,
) -> SlotAnchor:
    candidates = tuple(
        pane
        for pane in panes
        if pane.pane_id != cockpit_pane_id and pane.session_name == cockpit_session_name
    )
    if not candidates:
        raise ValueError("no non-cockpit panes available for Stage 11 active slot")
    winner = max(candidates, key=lambda pane: (pane.area, pane.width, pane.height, pane.pane_id))
    return winner.anchor


@dataclass(frozen=True)
class CockpitState:
    cockpit_pane_id: str
    cockpit_session_name: str
    slot_anchor: SlotAnchor
    panes: tuple[PaneRecord, ...]
    selected_index: int
    degraded_reason: str | None

    @classmethod
    def from_panes(
        cls,
        panes: tuple[PaneRecord, ...],
        *,
        cockpit_pane_id: str,
        cockpit_session_name: str,
    ) -> "CockpitState":
        return cls(
            cockpit_pane_id=cockpit_pane_id,
            cockpit_session_name=cockpit_session_name,
            slot_anchor=choose_startup_slot(
                panes,
                cockpit_pane_id=cockpit_pane_id,
                cockpit_session_name=cockpit_session_name,
            ),
            panes=panes,
            selected_index=0,
            degraded_reason=None,
        )

    def _is_active_slot_pane(self, pane: PaneRecord) -> bool:
        return (
            pane.pane_id != self.cockpit_pane_id
            and pane.session_name == self.cockpit_session_name
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
        return CockpitState(
            cockpit_pane_id=self.cockpit_pane_id,
            cockpit_session_name=self.cockpit_session_name,
            slot_anchor=self.slot_anchor,
            panes=self.panes,
            selected_index=next_index,
            degraded_reason=self.degraded_reason,
        )

    def refresh(self, panes: tuple[PaneRecord, ...]) -> "CockpitState":
        refreshed = CockpitState(
            cockpit_pane_id=self.cockpit_pane_id,
            cockpit_session_name=self.cockpit_session_name,
            slot_anchor=self.slot_anchor,
            panes=panes,
            selected_index=self.selected_index,
            degraded_reason=None,
        )
        candidate_count = len(refreshed.candidate_section)
        next_index = self.selected_index
        if candidate_count == 0:
            next_index = 0
        elif next_index >= candidate_count:
            next_index = candidate_count - 1
        active_exists = refreshed.active_pane is not None
        return CockpitState(
            cockpit_pane_id=self.cockpit_pane_id,
            cockpit_session_name=self.cockpit_session_name,
            slot_anchor=self.slot_anchor,
            panes=panes,
            selected_index=next_index,
            degraded_reason=None if active_exists else "active-slot-lost",
        )
