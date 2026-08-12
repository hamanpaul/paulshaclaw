"""paulshaclaw package."""
from __future__ import annotations

from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _version

try:
    __version__ = _version("paulshaclaw")
except PackageNotFoundError:  # 未安裝（直跑原始碼樹）時的 fallback
    __version__ = "0+unknown"
