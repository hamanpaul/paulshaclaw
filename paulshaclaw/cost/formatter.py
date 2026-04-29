from __future__ import annotations

from paulshaclaw.cost.models import CopilotAccountUsage, CostSnapshot, ProviderSnapshot, UsageWindow

TMUX_COLOR_BY_LEVEL = {
    "low": "fg=green",
    "warning": "fg=yellow",
    "critical": "fg=red",
    "neutral": "fg=colour245",
}


def classify_usage(value: int | None) -> str:
    if value is None:
        return "neutral"
    if value < 70:
        return "low"
    if value < 90:
        return "warning"
    return "critical"


def _provider_label(name: str, provider: ProviderSnapshot) -> str:
    return f"{name}~" if provider.source_status == "stale" else name


def _wrap(text: str, level: str, use_tmux_style: bool) -> str:
    if not use_tmux_style:
        return text
    return f"#[{TMUX_COLOR_BY_LEVEL[level]}]{text}#[default]"


def _format_window(window: UsageWindow | None, use_tmux_style: bool) -> str:
    if window is None or window.used_percent is None or not window.display_reset:
        return _wrap("--", "neutral", use_tmux_style)
    text = f"{window.used_percent}%({window.display_reset})"
    return _wrap(text, classify_usage(window.used_percent), use_tmux_style)


def _format_window_provider(name: str, provider: ProviderSnapshot, use_tmux_style: bool) -> str:
    windows = provider.windows
    return (
        f"{_provider_label(name, provider)} "
        f"5h:{_format_window(windows.get('five_hour'), use_tmux_style)} "
        f"wk:{_format_window(windows.get('weekly'), use_tmux_style)}"
    )


def _account_level(account: CopilotAccountUsage) -> str:
    if account.used_requests is None or not account.monthly_allowance:
        return "neutral"
    percent = int((account.used_requests / account.monthly_allowance) * 100)
    return classify_usage(percent)


def _format_copilot_provider(name: str, provider: ProviderSnapshot, use_tmux_style: bool) -> str:
    parts = [_provider_label(name, provider)]
    for account in provider.accounts:
        used = "--" if account.used_requests is None else str(account.used_requests)
        parts.append(_wrap(f"{account.label}:{used}", _account_level(account), use_tmux_style))
    return " ".join(parts)


def format_footer(snapshot: CostSnapshot, use_tmux_style: bool) -> str:
    segments: list[str] = []
    for name in ("cdx", "cc"):
        provider = snapshot.providers.get(name)
        if provider is not None:
            segments.append(_format_window_provider(name, provider, use_tmux_style))

    provider = snapshot.providers.get("cpt")
    if provider is not None:
        segments.append(_format_copilot_provider("cpt", provider, use_tmux_style))

    return "  ".join(segments)
