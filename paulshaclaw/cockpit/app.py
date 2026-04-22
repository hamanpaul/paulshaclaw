from __future__ import annotations

try:
    from textual.app import App
    from textual.widgets import Footer, Header, Static
except Exception:  # pragma: no cover - fallback when textual not installed
    """Fallback stubs so the module is importable when textual isn't installed.

    The real Textual types are required at runtime to run the UI, but tests
    that only import the module (e.g. the CLI --help smoke test) shouldn't
    fail with ModuleNotFoundError. Provide minimal no-op stand-ins.
    """
    from typing import Any, Generic, TypeVar

    T = TypeVar("T")

    class App(Generic[T]):
        """Very small stub to allow subclassing in tests."""
        pass

    class _Widget:
        def __init__(self, *args: Any, **kwargs: Any) -> None:  # pragma: no cover - noop
            pass

    Footer = _Widget
    Header = _Widget
    Static = _Widget


class CockpitApp(App[None]):
    """Minimal Stage 11 shell; real widgets arrive in later tasks."""

    TITLE = "PaulShiaBro Stage 11 Cockpit"

    def compose(self):
        yield Header()
        yield Static("Stage 11 operator cockpit bootstrap", id="stage11-bootstrap")
        yield Footer()
