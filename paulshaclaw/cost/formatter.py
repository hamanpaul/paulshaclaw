from __future__ import annotations

from paulshaclaw.cost.models import CopilotAccountUsage, CostSnapshot, ProviderSnapshot, UsageWindow

# Usage colours (all readable on tmux's default bg=green status bar):
# <70% blue, 70–85% orange, >85% red. (A green "low" foreground would be
# invisible green-on-green, which is why low is blue rather than green.)
TMUX_COLOR_BY_LEVEL = {
    "low": "fg=colour33",       # blue
    "warning": "fg=colour208",  # orange
    "critical": "fg=red",       # red
    "neutral": "fg=colour245",
    "estimated": "fg=magenta",
    "separator": "fg=colour238",  # dark grey: low-chroma, stands out on green
}
# Carried-forward (stale) values get a dark-green background until fresh data
# returns, so kept-but-unconfirmed numbers are visually distinct.
_STALE_BG = "bg=colour22"


def classify_usage(value: int | None) -> str:
    if value is None:
        return "neutral"
    if value < 70:
        return "low"
    if value < 85:
        return "warning"
    return "critical"


def _provider_label(name: str, provider: ProviderSnapshot) -> str:
    if provider.source_status == "stale":
        return f"{name}~"
    if provider.source_status == "estimated" or any(
        account.source == "local_observed" and account.used_requests is not None
        for account in provider.accounts
    ):
        return f"{name}?"
    return name


def _wrap(text: str, level: str, use_tmux_style: bool, *, stale: bool = False) -> str:
    if not use_tmux_style:
        return text
    style = TMUX_COLOR_BY_LEVEL[level]
    if stale:
        style = f"{style},{_STALE_BG}"
    return f"#[{style}]{text}#[default]"


def _provider_window_level(provider: ProviderSnapshot, value: int | None) -> str:
    if provider.source_status == "estimated" and value is not None:
        return "estimated"
    return classify_usage(value)


def _format_window(
    window: UsageWindow | None,
    use_tmux_style: bool,
    *,
    provider: ProviderSnapshot,
) -> str:
    stale = provider.source_status == "stale"
    if window is None or window.used_percent is None or not window.display_reset:
        return _wrap("--", "neutral", use_tmux_style, stale=stale)
    # Colour only the percentage (the usage signal); keep the reset time dim so
    # it reads as context rather than a usage level.
    percent = _wrap(
        f"{window.used_percent}%",
        _provider_window_level(provider, window.used_percent),
        use_tmux_style,
        stale=stale,
    )
    reset = _wrap(f"({window.display_reset})", "neutral", use_tmux_style, stale=stale)
    return f"{percent}{reset}"


def _format_window_provider(name: str, provider: ProviderSnapshot, use_tmux_style: bool) -> str:
    windows = provider.windows
    return (
        f"{_provider_label(name, provider)} "
        f"5h:{_format_window(windows.get('five_hour'), use_tmux_style, provider=provider)} "
        f"wk:{_format_window(windows.get('weekly'), use_tmux_style, provider=provider)}"
    )


def _account_level(provider: ProviderSnapshot, account: CopilotAccountUsage) -> str:
    if account.unlimited:
        return "low"
    if account.percent_used is not None:
        return classify_usage(account.percent_used)
    if (
        provider.source_status == "estimated" or account.source == "local_observed"
    ) and account.used_requests is not None:
        return "estimated"
    if account.used_requests is None or not account.monthly_allowance:
        return "neutral"
    percent = int((account.used_requests / account.monthly_allowance) * 100)
    return classify_usage(percent)


def _abbrev_count(value: int) -> str:
    # Keep the footer narrow: premium-request counts stay small, but AI-credit
    # (AIU) totals run to tens of thousands, so abbreviate large values.
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{value / 1_000:.1f}k"
    return str(value)


def _account_value(account: CopilotAccountUsage) -> str:
    # Prefer the plan-quota view (matches the Copilot CLI statusline); fall back
    # to a raw request count only when the quota endpoint was unavailable.
    if account.unlimited:
        return "∞"
    if account.percent_used is not None:
        return f"{account.percent_used}%"
    if account.used_requests is None:
        return "--"
    return _abbrev_count(account.used_requests)


def _format_copilot_provider(name: str, provider: ProviderSnapshot, use_tmux_style: bool) -> str:
    stale = provider.source_status == "stale"
    parts = [_provider_label(name, provider)]
    for account in provider.accounts:
        value = _account_value(account)
        # Colour only the value; the label stays default. `∞` (no limit) is blue
        # like a healthy usage level, to stand out from the dim reset times.
        level = "low" if account.unlimited else _account_level(provider, account)
        parts.append(f"{account.label}:{_wrap(value, level, use_tmux_style, stale=stale)}")
    return " ".join(parts)


def format_footer(snapshot: CostSnapshot, *, use_tmux_style: bool = True) -> str:
    segments: list[str] = []
    for name in ("cdx", "cc"):
        provider = snapshot.providers.get(name)
        if provider is not None:
            segments.append(_format_window_provider(name, provider, use_tmux_style))

    provider = snapshot.providers.get("cpt")
    if provider is not None and provider.accounts:
        segments.append(_format_copilot_provider("cpt", provider, use_tmux_style))

    # Divider between cdx / cc / cpt so the segments don't blur together, plus a
    # trailing space so the line doesn't sit flush against the terminal edge.
    separator = _wrap("|", "separator", use_tmux_style)
    joined = f" {separator} ".join(segments)
    return f"{joined} " if joined else joined


# --- cockpit rendering: ANSI fg-only (no background) ---------------------------
# The cockpit banner renders via rich's ``Text.from_ansi``. The tmux footer uses
# ``#[fg=…,bg=…]`` status-bar codes; convert them to ANSI 256-colour *foreground*
# escapes and drop the background so the cost line inherits the panel background.
import re as _re

_TMUX_NAMED_256 = {
    "black": 0, "red": 1, "green": 2, "yellow": 3,
    "blue": 4, "magenta": 5, "cyan": 6, "white": 7,
}
_TMUX_STYLE_RE = _re.compile(r"#\[([^\]]*)\]")
_ANSI_RESET = "\033[0m"


def _tmux_fg_to_ansi(fg: str) -> str:
    fg = fg.strip()
    if fg.startswith("colour"):
        num = fg[len("colour"):]
    elif fg in _TMUX_NAMED_256:
        num = str(_TMUX_NAMED_256[fg])
    else:
        return ""
    return f"\033[38;5;{num}m"


def tmux_to_ansi_fg(text: str) -> str:
    """Convert tmux status-bar style codes to ANSI foreground escapes, dropping bg.

    ``#[default]`` (and an empty ``#[]``) reset; ``#[fg=…,bg=…]`` keeps only the
    foreground. Text with no ``#[`` markers is returned unchanged.
    """

    def _repl(match: "_re.Match[str]") -> str:
        body = match.group(1).strip()
        if body in ("", "default"):
            return _ANSI_RESET
        fg: str | None = None
        for part in body.split(","):
            key, _, value = part.partition("=")
            if key.strip() == "fg":
                fg = value
        if fg is None:
            return ""
        return _tmux_fg_to_ansi(fg)

    return _TMUX_STYLE_RE.sub(_repl, text)


def _format_cockpit_cpt(provider: ProviderSnapshot) -> str:
    """cockpit 版 cpt 段：只顯示第一個帳號的值（如 haman），標為 ``cpt: N%``，
    不列帳號名、也不列其餘帳號（如 arc）。無帳號回空字串。"""
    if not provider.accounts:
        return ""
    account = provider.accounts[0]
    value = _account_value(account)
    level = "low" if account.unlimited else _account_level(provider, account)
    return f"cpt: {_wrap(value, level, True)}"


def _join_cockpit_segments(segments: list[str]) -> str:
    """以 dim 分隔符 ` | ` 串接非空段，轉 ANSI 前景色（無背景）。全空回空字串。"""
    separator = _wrap("|", "separator", True)
    joined = f" {separator} ".join(seg for seg in segments if seg)
    return tmux_to_ansi_fg(joined)


def format_cockpit_cdx(snapshot: CostSnapshot) -> str:
    """cockpit cost 列的 cdx 段（含 reset 時間），ANSI 前景色。無 cdx 回空字串。

    供 banner 把 cdx 併到 Net 那一行。"""
    provider = snapshot.providers.get("cdx")
    if provider is None:
        return ""
    return _join_cockpit_segments([_format_window_provider("cdx", provider, True)])


def format_cockpit_rest(snapshot: CostSnapshot) -> str:
    """cockpit cost 列的 cc + cpt 段（cdx 除外），ANSI 前景色。無資料回空字串。

    供 banner 放在 Net（含 cdx）的下一行。"""
    segments: list[str] = []
    cc = snapshot.providers.get("cc")
    if cc is not None:
        segments.append(_format_window_provider("cc", cc, True))
    cpt = snapshot.providers.get("cpt")
    if cpt is not None:
        segments.append(_format_cockpit_cpt(cpt))
    return _join_cockpit_segments(segments)


def format_cockpit_footer(snapshot: CostSnapshot) -> str:
    """整條 cockpit cost 列（cdx | cc | cpt），ANSI 前景色、無背景色。

    cdx/cc windows 含 reset 時間；cpt 收斂成單一 ``cpt: N%``（只取主帳號）。
    """
    cdx = format_cockpit_cdx(snapshot)
    rest = format_cockpit_rest(snapshot)
    separator = tmux_to_ansi_fg(_wrap("|", "separator", True))
    parts = [part for part in (cdx, rest) if part]
    return f" {separator} ".join(parts)
