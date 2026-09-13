from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Iterable, Sequence

from paulshaclaw.cost.config import CostConfig

if TYPE_CHECKING:  # pragma: no cover - annotations only
    from .agents import DetectedAgent

try:
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.widgets import Footer, Header, SelectionList, Static
except ImportError:  # pragma: no cover - textual is a runtime dependency, keep importable in thin envs
    from typing import Any, Generic, TypeVar

    T = TypeVar("T")
    ComposeResult = Iterable[Any]

    class Binding:  # pragma: no cover - noop
        def __init__(
            self,
            key: str,
            action: str,
            description: str = "",
            show: bool = True,
            key_display: str | None = None,
            priority: bool = False,
        ) -> None:
            self.key = key
            self.action = action
            self.description = description

    class App(Generic[T]):  # pragma: no cover - noop
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def run(self, *args: Any, **kwargs: Any) -> T | None:
            return None

        def exit(self, result: T | None = None, return_code: int = 0, message: object | None = None) -> None:
            pass

        def query_one(self, *args: Any, **kwargs: Any) -> Any:
            raise LookupError

    class Header:  # pragma: no cover - noop
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class Footer:  # pragma: no cover - noop
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

    class Static:  # pragma: no cover - noop
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def update(self, *args: Any, **kwargs: Any) -> None:
            pass

    class SelectionList:  # pragma: no cover - noop
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.selected: tuple[str, ...] = ()

        def focus(self) -> None:
            pass

_PROVIDER_ORDER = ("codex", "claude", "copilot", "agy")


@dataclass(frozen=True)
class FooterSelectionOption:
    label: str
    value: str
    selected: bool = False


def _provider_value(provider: str) -> str:
    return f"provider:{provider}"


def _account_value(provider: str, label: str) -> str:
    return f"account:{provider}:{label}"


def _detected_lookup(
    detected_agents: Sequence["DetectedAgent"],
) -> dict[str, "DetectedAgent"]:
    return {agent.name: agent for agent in detected_agents}


def _agent_is_detected(agent: object | None) -> bool:
    if agent is None:
        return False
    return getattr(agent, "binary", None) is not None and bool(
        getattr(agent, "state_present", False)
    )


def _selection_raw(providers: dict[str, dict[str, object]]) -> str | None:
    if not providers:
        return "none"

    tokens: list[str] = []
    for provider in _PROVIDER_ORDER:
        details = providers.get(provider)
        if not isinstance(details, dict):
            continue
        if provider in ("copilot", "agy"):
            labels = list(details.get("labels", []))
            if details.get("all_accounts"):
                tokens.append(provider)
            elif labels:
                tokens.append(provider + ":" + ":".join(labels))
            continue
        tokens.append(provider)
    return ",".join(tokens)


def selection_from_values(selected_values: set[str]) -> dict[str, object]:
    if not selected_values:
        return {"raw": "none", "disable_all": True, "providers": {}}

    providers: dict[str, dict[str, object]] = {}
    for provider in _PROVIDER_ORDER:
        provider_selected = _provider_value(provider) in selected_values
        labels = sorted(
            value.split(":", 2)[2]
            for value in selected_values
            if value.startswith(f"account:{provider}:")
        )
        if provider in ("copilot", "agy"):
            if provider_selected or labels:
                details: dict[str, object] = {"enabled": True}
                if labels:
                    details["labels"] = labels
                if provider_selected and not labels:
                    details["all_accounts"] = True
                providers[provider] = details
            continue
        if provider_selected:
            providers[provider] = {"enabled": True}

    return {
        "raw": _selection_raw(providers),
        "disable_all": False,
        "providers": providers,
    }


def _provider_suffix(provider: str, detected_agents: dict[str, object]) -> str:
    if not _agent_is_detected(detected_agents.get(provider)):
        return " (未偵測)"
    return ""


def build_selection_options(
    *,
    detected_agents: Sequence["DetectedAgent"],
    config: CostConfig,
) -> list[FooterSelectionOption]:
    detected_by_name = _detected_lookup(detected_agents)
    codex_detected = _agent_is_detected(detected_by_name.get("codex"))
    claude_detected = _agent_is_detected(detected_by_name.get("claude"))
    copilot_detected = _agent_is_detected(detected_by_name.get("copilot"))
    agy_detected = _agent_is_detected(detected_by_name.get("agy"))
    options = [
        FooterSelectionOption(
            label=f"codex{_provider_suffix('codex', detected_by_name)}",
            value=_provider_value("codex"),
            selected=config.codex.enabled and codex_detected,
        ),
        FooterSelectionOption(
            label=f"claude{_provider_suffix('claude', detected_by_name)}",
            value=_provider_value("claude"),
            selected=config.claude.enabled and claude_detected,
        ),
        FooterSelectionOption(
            label=f"copilot{_provider_suffix('copilot', detected_by_name)}",
            value=_provider_value("copilot"),
            selected=any(account.enabled for account in config.copilot_accounts) and copilot_detected,
        ),
    ]
    options.extend(
        FooterSelectionOption(
            label=f"  └─ copilot:{account.label}",
            value=_account_value("copilot", account.label),
            selected=account.enabled and copilot_detected,
        )
        for account in config.copilot_accounts
    )
    options.append(
        FooterSelectionOption(
            label=f"agy{_provider_suffix('agy', detected_by_name)}",
            value=_provider_value("agy"),
            selected=config.agy.effective_enabled and agy_detected,
        )
    )
    options.extend(
        FooterSelectionOption(
            label=f"  └─ agy:{account.label}",
            value=_account_value("agy", account.label),
            selected=config.agy.enabled and account.enabled and agy_detected,
        )
        for account in config.agy.accounts
    )
    return options


class FooterSelectionApp(App[dict[str, object] | None]):
    BINDINGS = [
        Binding("enter", "confirm", "Apply", priority=True),
        Binding("escape", "cancel", "Cancel", priority=True),
    ]

    def __init__(
        self,
        *,
        options: Sequence[FooterSelectionOption],
        preview_builder: Callable[[set[str]], str] | None = None,
    ) -> None:
        super().__init__()
        self._options = list(options)
        self._preview_builder = preview_builder
        self.result: dict[str, object] | None = None

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        yield Static("preview: none", id="footer-preview")
        yield SelectionList(
            *[(option.label, option.value, option.selected) for option in self._options],
            id="footer-selection-list",
        )
        yield Footer()

    def on_mount(self) -> None:
        try:
            self.query_one("#footer-selection-list", SelectionList).focus()
        except Exception:
            pass
        self._refresh_preview()

    def on_selection_list_selected_changed(self, _event: object) -> None:
        self._refresh_preview()

    def on_selection_list_selection_toggled(self, _event: object) -> None:
        self._refresh_preview()

    def _selected_values(self) -> set[str]:
        try:
            return set(self.query_one("#footer-selection-list", SelectionList).selected)
        except Exception:
            return set()

    def _refresh_preview(self) -> None:
        preview = "none"
        if self._preview_builder is not None:
            try:
                preview = self._preview_builder(self._selected_values()) or "none"
            except Exception:
                preview = "none"
        try:
            self.query_one("#footer-preview", Static).update(f"preview: {preview}")
        except Exception:
            pass

    def action_confirm(self) -> None:
        self.result = selection_from_values(self._selected_values())
        self.exit(result=self.result)

    def action_cancel(self) -> None:
        self.result = None
        self.exit(result=None)


def run_footer_selection(
    *,
    options: Sequence[FooterSelectionOption],
    preview_builder: Callable[[set[str]], str] | None = None,
) -> dict[str, object] | None:
    app = FooterSelectionApp(options=options, preview_builder=preview_builder)
    return app.run()
