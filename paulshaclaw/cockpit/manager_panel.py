from __future__ import annotations

try:
    from textual.app import ComposeResult
    from textual.binding import Binding
    from textual.screen import ModalScreen
    from textual.widgets import Static
except Exception:  # pragma: no cover - fallback when textual not installed
    from typing import Any, Generic, Iterable, TypeVar

    T = TypeVar("T")
    ComposeResult = Iterable[Any]

    class Binding:  # pragma: no cover - noop
        def __init__(self, key: str, handler: str, description: str) -> None:
            self.key = key
            self.handler = handler
            self.description = description

    class ModalScreen(Generic[T]):  # pragma: no cover - noop
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def dismiss(self) -> None:
            pass

    class Static:  # pragma: no cover - noop
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass


def render_manager_status_text(status: dict[str, object]) -> str:
    daemon = status.get("daemon") if isinstance(status, dict) else None
    daemon = daemon if isinstance(daemon, dict) else {}
    ready = list(status.get("ready", [])) if isinstance(status, dict) else []
    in_flight = list(status.get("in_flight", [])) if isinstance(status, dict) else []
    recent_done = list(status.get("recent_done", [])) if isinstance(status, dict) else []

    lines = ["manager status", ""]
    if status.get("degraded"):
        lines.append(f"degraded: {status.get('degraded_reason') or '--'}")
    lines.extend(
        [
            f"updated_at: {status.get('updated_at') or '--'}",
            f"daemon: pid={daemon.get('pid', '--')} idle={daemon.get('idle', '--')} last_tick_at={daemon.get('last_tick_at', '--')}",
            f"ready({len(ready)}): {', '.join(str(item) for item in ready) if ready else '--'}",
            "in_flight:"
            + (
                "".join(
                    f"\n- {item.get('slice_id', '--')} ({item.get('state', '--')})"
                    for item in in_flight
                    if isinstance(item, dict)
                )
                if in_flight
                else " --"
            ),
            "recent_done:"
            + (
                "".join(
                    f"\n- {item.get('slice_id', '--')} ({item.get('gate_status', '--')})"
                    for item in recent_done
                    if isinstance(item, dict)
                )
                if recent_done
                else " --"
            ),
        ]
    )
    return "\n".join(lines)


class ManagerModal(ModalScreen[None]):
    BINDINGS = [Binding("escape", "dismiss_manager", "Close")]

    def __init__(self, status: dict[str, object]) -> None:
        super().__init__()
        self.status_text = render_manager_status_text(status)

    def update_status(self, status: dict[str, object]) -> None:
        self.status_text = render_manager_status_text(status)
        try:
            self.query_one("#manager-modal", Static).update(self.status_text)
        except Exception:
            pass

    def compose(self) -> ComposeResult:
        card = Static(self.status_text, id="manager-modal")
        try:
            card.border_title = "🦞 Cockpit · Manager"
            card.border_subtitle = "esc 關閉"
        except Exception:
            pass
        yield card

    def action_dismiss_manager(self) -> None:
        self.dismiss()
