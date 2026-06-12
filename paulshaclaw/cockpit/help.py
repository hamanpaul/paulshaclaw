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


class HelpModal(ModalScreen[None]):
    BINDINGS = [Binding("escape", "dismiss_help", "Close")]

    def __init__(self, bindings: list[Binding]) -> None:
        super().__init__()
        self.help_text = self.render_help_text(bindings)

    @staticmethod
    def render_help_text(bindings: list[Binding]) -> str:
        rows = []
        for binding in bindings:
            key = getattr(binding, "key", "")
            description = getattr(binding, "description", "")
            if key and description:
                rows.append(f"{key}: {description}")
        return "\n".join(
            [
                "Stage 11 Cockpit Help",
                "",
                "Keys:",
                *rows,
                "",
                "Multi-session behavior:",
                "The work list includes panes from all local tmux sessions.",
                "Enter swaps the selected pane with the cockpit-session active slot.",
                "The active slot is never inferred from another session with matching geometry.",
            ]
        )

    def compose(self) -> ComposeResult:
        yield Static(self.help_text, id="help-modal")

    def action_dismiss_help(self) -> None:
        callback = getattr(self.app, "_on_help_closed", None)
        if callable(callback):
            callback()
        self.dismiss()
