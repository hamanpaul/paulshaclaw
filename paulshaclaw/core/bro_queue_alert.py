"""bro-queue 積壓超時告警（#275）。

#88（PR #274）把訊息落地成 per-pane JSONL 佇列，`flush()` 只送最前面一筆並用
`capture-pane` 驗證送達；沒驗到就整批保留，交由下一則訊息或 agent Stop hook 重試。
`FlushResult.pending_seconds` 雖已算出最前筆等了多久，卻沒有「無人互動時誰去看它」
——若使用者不再傳訊息、agent 也卡死，佇列會靜靜積壓。

本模組掛在 bot listener 既有的 polling 迴圈上：每輪檢查各 pane 佇列年齡，超過
門檻就主動推一則告警到已綁定的 Telegram chat。刻意不新增常駐進程，也不碰
operator shell / cortex 治理面邊界。

設計取捨：
- **門檻預設 600 秒（10 分鐘）**：積壓超過 10 分鐘代表 agent 確實卡住、不是單純
  正在產生輸出；太短會在正常長回合中被誤觸發。
- **同一筆積壓只告警一次**：以佇列最前筆的 `(pane_id, queued_at)` 作為去重識別。
  佇列前進（最前筆換人）或清空後，舊識別一併清除，新最前筆累積超過門檻才會再告警。
  不做「持續積壓每 M 分鐘再提醒」——預設不要吵，需要時再擴。
- **告警失敗絕不中斷 listener**：送出與讀取佇列的例外一律吞掉 + log，由 listener
  端再加一層 try/except 保護既有訊息路由與 agent 執行。
"""
from __future__ import annotations

import logging
import os
import time
from typing import Callable, Mapping, Protocol, Sequence

from paulshaclaw.core import bro_queue

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD_SECONDS = 600.0


def alert_threshold_seconds(env: Mapping[str, str] | None = None) -> float:
    """從 `PSC_BRO_QUEUE_ALERT_THRESHOLD_SECONDS` 讀門檻；未設走預設 600 秒。"""
    resolved_env = os.environ if env is None else env
    raw = resolved_env.get("PSC_BRO_QUEUE_ALERT_THRESHOLD_SECONDS", "").strip()
    if not raw:
        return DEFAULT_THRESHOLD_SECONDS
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_THRESHOLD_SECONDS
    if value <= 0:
        return DEFAULT_THRESHOLD_SECONDS
    return value


# 為了不耦合 `bot.reply`（另一個 agent 的範圍），這裡只定義告警需要的最小介面。
class _AlertSender(Protocol):
    def send_message(self, *, chat_id: int, text: str) -> None: ...


class _BindingStore(Protocol):
    def lookup_chat_id(self, user_id: int) -> int | None: ...


class BroQueueAlerter:
    """檢查各 pane 佇列年齡並對超時積壓推告警。

    可注入 `now`、`list_backlogs` 便於測試；`check_and_alert()` 預期由 listener
    polling 迴圈每輪呼叫一次，本身吞掉所有非 KeyboardInterrupt/SystemExit 例外。
    """

    def __init__(
        self,
        *,
        sender: _AlertSender,
        bindings: _BindingStore,
        allowed_user_ids: Sequence[int],
        threshold_seconds: float | None = None,
        now: Callable[[], float] | None = None,
        list_backlogs: Callable[..., list[bro_queue.PaneBacklog]] | None = None,
    ) -> None:
        self.sender = sender
        self.bindings = bindings
        self.allowed_user_ids = tuple(int(uid) for uid in allowed_user_ids)
        self.threshold_seconds = (
            DEFAULT_THRESHOLD_SECONDS if threshold_seconds is None else float(threshold_seconds)
        )
        self.now = now or _epoch_now
        self._list_backlogs = list_backlogs or bro_queue.list_backlogs
        # 已告警過的最前筆識別：(pane_id, queued_at)。佇列前進/清空時會被清理。
        self._alerted_heads: set[tuple[str, float]] = set()

    def check_and_alert(self) -> None:
        """讀佇列年齡 → 超門檻且未告警過者推告警；例外吞掉不外炸。"""
        try:
            backlogs = self._list_backlogs(now=self.now)
        except Exception as error:  # noqa: BLE001 - 佇列讀取失敗不可中斷 polling
            logger.error("BRO_QUEUE_ALERT_READ_ERROR error=%s", error)
            return

        now = self.now()
        stale = [
            b
            for b in backlogs
            if b.pending_seconds is not None and b.pending_seconds >= self.threshold_seconds
        ]
        # 清掉已不在最前位的舊識別：佇列前進或清空後才允許新最前筆再次告警。
        current_heads = {
            (b.pane_id, b.head_queued_at)
            for b in stale
            if b.head_queued_at is not None
        }
        self._alerted_heads &= current_heads

        new_alerts = [
            b for b in stale
            if b.head_queued_at is not None
            and (b.pane_id, b.head_queued_at) not in self._alerted_heads
        ]
        if not new_alerts:
            return

        text = format_alert(new_alerts, threshold_seconds=self.threshold_seconds)
        for chat_id in self._resolve_chat_ids():
            try:
                self.sender.send_message(chat_id=chat_id, text=text)
            except Exception as error:  # noqa: BLE001 - 送出失敗不可中斷 listener
                logger.error("BRO_QUEUE_ALERT_SEND_ERROR chat=%d error=%s", chat_id, error)

        for b in new_alerts:
            if b.head_queued_at is not None:
                self._alerted_heads.add((b.pane_id, b.head_queued_at))

    def _resolve_chat_ids(self) -> list[int]:
        """對所有 allowed user 查綁定的 chat；查無任何綁定時靜默不送。"""
        chat_ids: list[int] = []
        for user_id in self.allowed_user_ids:
            try:
                chat_id = self.bindings.lookup_chat_id(user_id)
            except Exception as error:  # noqa: BLE001 - 綁定檔壞掉不可中斷
                logger.error("BRO_QUEUE_ALERT_BINDING_ERROR user=%d error=%s", user_id, error)
                continue
            if chat_id is not None:
                chat_ids.append(int(chat_id))
        return chat_ids


def format_alert(
    backlogs: Sequence[bro_queue.PaneBacklog], *, threshold_seconds: float
) -> str:
    """組 zh-tw 告警文字：列出各超時 pane 與等待分鐘數。"""
    lines = [
        f"⚠️ bro-queue 積壓超時（門檻 {int(threshold_seconds // 60)} 分鐘未消化）",
    ]
    for b in backlogs:
        minutes = int((b.pending_seconds or 0) // 60)
        lines.append(
            f"• pane {b.pane_id}：尚有 {b.remaining} 筆待送，最前筆已等待 {minutes} 分鐘"
        )
    lines.append("agent 可能卡住或無回應，請確認 pane 狀態")
    return "\n".join(lines)


def _epoch_now() -> float:
    return time.time()