from __future__ import annotations

from dataclasses import dataclass

from .models import PaneRecord, SlotAnchor


def choose_startup_slot(panes: tuple[PaneRecord, ...], *, cockpit_pane_id: str) -> SlotAnchor:
    candidates = tuple(pane for pane in panes if pane.pane_id != cockpit_pane_id)
    if not candidates:
        raise ValueError("no non-cockpit panes available for Stage 11 active slot")
    winner = max(candidates, key=lambda pane: (pane.area, pane.width, pane.height, pane.pane_id))
    return winner.anchor


@dataclass(frozen=True)
class CockpitState:
    cockpit_pane_id: str
    slot_anchor: SlotAnchor
    panes: tuple[PaneRecord, ...]
    selected_index: int
    degraded_reason: str | None

    @classmethod
    def from_panes(cls, panes: tuple[PaneRecord, ...], *, cockpit_pane_id: str) -> "CockpitState":
        return cls(
            cockpit_pane_id=cockpit_pane_id,
            slot_anchor=choose_startup_slot(panes, cockpit_pane_id=cockpit_pane_id),
            panes=panes,
            selected_index=0,
            degraded_reason=None,
        )

    @property
    def active_section(self) -> tuple[PaneRecord, ...]:
        return tuple(
            pane for pane in self.panes if pane.pane_id != self.cockpit_pane_id and pane.anchor == self.slot_anchor
        )

    @property
    def candidate_section(self) -> tuple[PaneRecord, ...]:
        return tuple(
            pane for pane in self.panes if pane.pane_id != self.cockpit_pane_id and pane.anchor != self.slot_anchor
        )
