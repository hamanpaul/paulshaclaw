"""主機可用記憶體低水位告警（#379）。

長時間 agent session 搭配 headless 瀏覽器自動化時，曾把 20 GB 主機的
`MemAvailable` 吃到約 1 GB；Claude Code 在記憶體不足時會回收背景 shell，
正在等待的背景工作因此被停掉。cockpit `sysmon` 只顯示 Mem meter，人不在
TUI 前面時看不到；cortex 的容量治理（#113 轉移）目前也沒有記憶體數據。

本模組比照 `bro_queue_alert`（#275）：掛在 bot listener 既有的 polling 迴圈上，
每輪讀一次 `/proc/meminfo`，跌破門檻就推一則 Telegram 告警。**只做量測與通知**，
不砍程序、不擋 spawn、不控速——容量治理依 #113 仍屬 paulsha-cortex。

設計取捨：
- **遲滯式門檻**：低於 `low_mb`（預設 3072）告警一次；回到 `recover_mb`
  （預設 4096）以上才解除並送恢復通知。避免水位在門檻附近來回時洗版。
- **RSS 前幾名依程序名稱彙總**：瀏覽器一個分頁一個程序，單看 PID 看不出是誰；
  只在告警當下才掃 `/proc/*/status`，平常不付這個成本。
- **失敗一律吞掉**：讀不到 `/proc`、送出失敗都只記 log，絕不中斷 listener。
  送出失敗仍視為已告警，不在每輪 polling 重送。
"""
from __future__ import annotations

import logging
import os
from typing import Callable, Mapping, Protocol, Sequence

from paulshaclaw.cockpit.sysmon import parse_meminfo

logger = logging.getLogger(__name__)

DEFAULT_LOW_MB = 3072
DEFAULT_RECOVER_MB = 4096
DEFAULT_TOP_N = 3


def _positive_int(raw: str | None, default: int) -> int:
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def thresholds_from_env(env: Mapping[str, str] | None = None) -> tuple[int, int]:
    """讀 `PSC_MEM_ALERT_LOW_MB`／`PSC_MEM_ALERT_RECOVER_MB`；無效值退回預設。

    恢復門檻低於告警門檻時夾到告警門檻，維持遲滯語意。
    """
    resolved = os.environ if env is None else env
    low = _positive_int(resolved.get("PSC_MEM_ALERT_LOW_MB"), DEFAULT_LOW_MB)
    recover = _positive_int(resolved.get("PSC_MEM_ALERT_RECOVER_MB"), DEFAULT_RECOVER_MB)
    return low, max(low, recover)


def is_disabled(env: Mapping[str, str] | None = None) -> bool:
    resolved = os.environ if env is None else env
    return resolved.get("PSC_MEM_ALERT_DISABLED", "").strip() == "1"


def read_mem_kb(proc: str = "/proc") -> tuple[int | None, int | None]:
    """回 (MemAvailable, MemTotal)，單位 kB；讀不到或缺欄位回 None。"""
    try:
        with open(f"{proc}/meminfo", encoding="utf-8") as f:
            info = parse_meminfo(f.read())
    except OSError:
        return None, None
    return info.get("MemAvailable"), info.get("MemTotal")


def top_rss_by_name(proc: str = "/proc", n: int = DEFAULT_TOP_N) -> list[tuple[str, int]]:
    """掃 `/proc/<pid>/status`，依程序名稱加總 VmRSS（kB），回前 n 名。"""
    totals: dict[str, int] = {}
    try:
        entries = os.listdir(proc)
    except OSError:
        return []
    for entry in entries:
        if not entry.isdigit():
            continue
        name = None
        rss = None
        try:
            with open(f"{proc}/{entry}/status", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if line.startswith("Name:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("VmRSS:"):
                        rss = int(line.split()[1])
                        break
        except (OSError, ValueError, IndexError):
            continue  # 程序在掃描途中結束是常態
        if name and rss:
            totals[name] = totals.get(name, 0) + rss
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:n]


def _gb(kb: int) -> str:
    return f"{kb / 1024 / 1024:.1f} GB"


def format_alert(
    available_kb: int, total_kb: int | None, top: Sequence[tuple[str, int]], *, low_mb: int
) -> str:
    total = f" / {_gb(total_kb)}" if total_kb else ""
    lines = [
        f"⚠️ 主機可用記憶體偏低：{_gb(available_kb)}{total}（門檻 {_gb(low_mb * 1024)}）",
    ]
    if top:
        lines.append("用量最高（依程序名稱彙總）：")
        lines.extend(f"• {name}：{_gb(kb)}" for name, kb in top)
    lines.append("記憶體再低下去，背景 shell 可能被回收；可先關閉不用的分頁或程序")
    return "\n".join(lines)


def format_recovery(available_kb: int, total_kb: int | None, *, recover_mb: int) -> str:
    total = f" / {_gb(total_kb)}" if total_kb else ""
    return f"✅ 主機可用記憶體已恢復：{_gb(available_kb)}{total}（解除門檻 {_gb(recover_mb * 1024)}）"


# 與 bro_queue_alert 相同：只定義告警需要的最小介面，不耦合 bot.reply。
class _AlertSender(Protocol):
    def send_message(self, *, chat_id: int, text: str) -> object: ...


class _BindingStore(Protocol):
    def lookup_chat_id(self, user_id: int) -> int | None: ...


class MemPressureAlerter:
    """每輪 polling 呼叫一次 `check_and_alert()`；本身吞掉所有一般例外。"""

    def __init__(
        self,
        *,
        sender: _AlertSender,
        bindings: _BindingStore,
        allowed_user_ids: Sequence[int],
        low_mb: int | None = None,
        recover_mb: int | None = None,
        read_mem: Callable[[], tuple[int | None, int | None]] | None = None,
        read_top: Callable[[], list[tuple[str, int]]] | None = None,
        disabled: bool = False,
    ) -> None:
        self.sender = sender
        self.bindings = bindings
        self.allowed_user_ids = tuple(int(uid) for uid in allowed_user_ids)
        self.low_mb = DEFAULT_LOW_MB if low_mb is None else int(low_mb)
        self.recover_mb = max(self.low_mb, DEFAULT_RECOVER_MB if recover_mb is None else int(recover_mb))
        self._read_mem = read_mem or read_mem_kb
        self._read_top = read_top or top_rss_by_name
        self.disabled = disabled
        self.alerting = False

    def check_and_alert(self) -> None:
        if self.disabled:
            return
        try:
            available_kb, total_kb = self._read_mem()
        except Exception as error:  # noqa: BLE001 - /proc 讀取失敗不可中斷 polling
            logger.error("MEM_PRESSURE_ALERT_READ_ERROR error=%s", error)
            return
        if available_kb is None:
            return

        if not self.alerting and available_kb < self.low_mb * 1024:
            try:
                top = self._read_top()
            except Exception as error:  # noqa: BLE001 - 程序清單失敗仍要告警
                logger.error("MEM_PRESSURE_ALERT_TOP_ERROR error=%s", error)
                top = []
            self._broadcast(format_alert(available_kb, total_kb, top, low_mb=self.low_mb))
            self.alerting = True
        elif self.alerting and available_kb >= self.recover_mb * 1024:
            self._broadcast(format_recovery(available_kb, total_kb, recover_mb=self.recover_mb))
            self.alerting = False

    def _broadcast(self, text: str) -> None:
        for chat_id in self._resolve_chat_ids():
            try:
                self.sender.send_message(chat_id=chat_id, text=text)
            except Exception as error:  # noqa: BLE001 - 送出失敗不可中斷 listener
                logger.error("MEM_PRESSURE_ALERT_SEND_ERROR chat=%d error=%s", chat_id, error)

    def _resolve_chat_ids(self) -> list[int]:
        chat_ids: list[int] = []
        for user_id in self.allowed_user_ids:
            try:
                chat_id = self.bindings.lookup_chat_id(user_id)
            except Exception as error:  # noqa: BLE001 - 綁定檔壞掉不可中斷
                logger.error("MEM_PRESSURE_ALERT_BINDING_ERROR user=%d error=%s", user_id, error)
                continue
            if chat_id is not None:
                chat_ids.append(int(chat_id))
        return chat_ids
