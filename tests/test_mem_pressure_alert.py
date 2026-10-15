"""#379：驗證主機可用記憶體低水位告警（`mem_pressure_alert`）。

核心情境：
- 正常水位不告警
- 跌破低水位告警一次，持續低水位不重複
- 在低水位與恢復門檻之間波動不重複告警
- 回到恢復門檻以上送一次恢復通知，之後再次跌破才再告警
- RSS 依程序名稱彙總、取前 N 名
- 讀取失敗／欄位缺漏／送出失敗一律吞例外
- 門檻與停用開關可由環境變數設定，無效值退回預設
"""
from __future__ import annotations

from pathlib import Path

from paulshaclaw.core import mem_pressure_alert as mpa
from paulshaclaw.core.mem_pressure_alert import MemPressureAlerter

MB = 1024  # kB


class _FakeSender:
    def __init__(self, *, raises: bool = False) -> None:
        self.sent: list[dict[str, object]] = []
        self.raises = raises

    def send_message(self, *, chat_id: int, text: str) -> None:
        if self.raises:
            raise RuntimeError("telegram down")
        self.sent.append({"chat_id": chat_id, "text": text})


class _FakeBindings:
    def __init__(self, mapping: dict[int, int] | None = None) -> None:
        self.mapping = {1: 100} if mapping is None else mapping

    def lookup_chat_id(self, user_id: int) -> int | None:
        return self.mapping.get(user_id)


class _MemFeed:
    """依序回傳 (available_kb, total_kb)；用來模擬水位變化。"""

    def __init__(self, values: list[tuple[int | None, int | None]]) -> None:
        self.values = list(values)
        self.calls = 0

    def __call__(self) -> tuple[int | None, int | None]:
        value = self.values[min(self.calls, len(self.values) - 1)]
        self.calls += 1
        return value


def _alerter(feed, *, sender=None, bindings=None, top=None, low_mb=3072, recover_mb=4096):
    return MemPressureAlerter(
        sender=sender or _FakeSender(),
        bindings=bindings or _FakeBindings(),
        allowed_user_ids=[1],
        low_mb=low_mb,
        recover_mb=recover_mb,
        read_mem=feed,
        read_top=top or (lambda: [("chrome", 13_000 * MB), ("python3", 600 * MB)]),
    )


TOTAL = 20_000 * MB


def test_no_alert_when_memory_is_healthy():
    sender = _FakeSender()
    alerter = _alerter(_MemFeed([(10_000 * MB, TOTAL)]), sender=sender)
    alerter.check_and_alert()
    assert sender.sent == []


def test_alert_once_when_below_low_watermark_and_no_repeat():
    sender = _FakeSender()
    alerter = _alerter(_MemFeed([(1_000 * MB, TOTAL), (900 * MB, TOTAL), (800 * MB, TOTAL)]), sender=sender)
    for _ in range(3):
        alerter.check_and_alert()
    assert len(sender.sent) == 1
    text = sender.sent[0]["text"]
    assert sender.sent[0]["chat_id"] == 100
    assert "可用記憶體偏低" in text
    assert "chrome" in text and "python3" in text


def test_fluctuation_between_watermarks_does_not_realert():
    sender = _FakeSender()
    feed = _MemFeed([(2_000 * MB, TOTAL), (3_500 * MB, TOTAL), (2_500 * MB, TOTAL), (3_900 * MB, TOTAL)])
    alerter = _alerter(feed, sender=sender)
    for _ in range(4):
        alerter.check_and_alert()
    assert len(sender.sent) == 1


def test_recovery_notice_then_realert_on_next_drop():
    sender = _FakeSender()
    feed = _MemFeed([
        (1_000 * MB, TOTAL),   # 告警
        (5_000 * MB, TOTAL),   # 恢復通知
        (6_000 * MB, TOTAL),   # 正常，不送
        (2_000 * MB, TOTAL),   # 再次告警
    ])
    alerter = _alerter(feed, sender=sender)
    for _ in range(4):
        alerter.check_and_alert()
    texts = [m["text"] for m in sender.sent]
    assert len(texts) == 3
    assert "可用記憶體偏低" in texts[0]
    assert "已恢復" in texts[1]
    assert "可用記憶體偏低" in texts[2]


def test_top_consumers_only_read_when_alerting():
    calls: list[int] = []

    def top():
        calls.append(1)
        return [("chrome", 1 * MB)]

    alerter = _alerter(_MemFeed([(10_000 * MB, TOTAL), (10_000 * MB, TOTAL)]), top=top)
    alerter.check_and_alert()
    alerter.check_and_alert()
    assert calls == []


def test_missing_meminfo_fields_do_not_alert():
    sender = _FakeSender()
    alerter = _alerter(_MemFeed([(None, None)]), sender=sender)
    alerter.check_and_alert()
    assert sender.sent == []


def test_read_failure_is_swallowed():
    def boom():
        raise OSError("no /proc")

    sender = _FakeSender()
    alerter = _alerter(boom, sender=sender)
    alerter.check_and_alert()  # 不得拋出
    assert sender.sent == []


def test_top_read_failure_still_sends_alert_without_list():
    def boom():
        raise OSError("ps failed")

    sender = _FakeSender()
    alerter = _alerter(_MemFeed([(1_000 * MB, TOTAL)]), sender=sender, top=boom)
    alerter.check_and_alert()
    assert len(sender.sent) == 1
    assert "可用記憶體偏低" in sender.sent[0]["text"]


def test_send_failure_is_swallowed_and_not_retried_every_tick():
    sender = _FakeSender(raises=True)
    feed = _MemFeed([(1_000 * MB, TOTAL), (1_000 * MB, TOTAL)])
    alerter = _alerter(feed, sender=sender)
    alerter.check_and_alert()  # 不得拋出
    alerter.check_and_alert()
    assert alerter.alerting is True


def test_no_bound_chat_is_silent():
    sender = _FakeSender()
    alerter = _alerter(_MemFeed([(1_000 * MB, TOTAL)]), sender=sender, bindings=_FakeBindings({}))
    alerter.check_and_alert()
    assert sender.sent == []


def test_disabled_alerter_never_reads():
    feed = _MemFeed([(1_000 * MB, TOTAL)])
    alerter = MemPressureAlerter(
        sender=_FakeSender(), bindings=_FakeBindings(), allowed_user_ids=[1],
        read_mem=feed, read_top=lambda: [], disabled=True,
    )
    alerter.check_and_alert()
    assert feed.calls == 0


# ---------------------------------------------------------------------------
# 環境變數設定
# ---------------------------------------------------------------------------


def test_thresholds_default_and_override():
    assert mpa.thresholds_from_env({}) == (3072, 4096)
    assert mpa.thresholds_from_env({"PSC_MEM_ALERT_LOW_MB": "2048", "PSC_MEM_ALERT_RECOVER_MB": "3000"}) == (2048, 3000)


def test_invalid_thresholds_fall_back_to_defaults():
    assert mpa.thresholds_from_env({"PSC_MEM_ALERT_LOW_MB": "abc", "PSC_MEM_ALERT_RECOVER_MB": "-5"}) == (3072, 4096)


def test_recover_below_low_is_clamped_to_low():
    assert mpa.thresholds_from_env({"PSC_MEM_ALERT_LOW_MB": "5000", "PSC_MEM_ALERT_RECOVER_MB": "4000"}) == (5000, 5000)


def test_disabled_flag():
    assert mpa.is_disabled({"PSC_MEM_ALERT_DISABLED": "1"}) is True
    assert mpa.is_disabled({}) is False


# ---------------------------------------------------------------------------
# /proc 讀取（以假的 proc 目錄驗證）
# ---------------------------------------------------------------------------


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_read_mem_kb_from_meminfo(tmp_path):
    _write(tmp_path / "meminfo", "MemTotal:       20479000 kB\nMemFree:  100 kB\nMemAvailable:    1048576 kB\n")
    assert mpa.read_mem_kb(str(tmp_path)) == (1048576, 20479000)


def test_read_mem_kb_missing_file(tmp_path):
    assert mpa.read_mem_kb(str(tmp_path)) == (None, None)


def test_top_rss_by_name_aggregates_and_sorts(tmp_path):
    _write(tmp_path / "10" / "status", "Name:\tchrome\nVmRSS:\t 6000000 kB\n")
    _write(tmp_path / "11" / "status", "Name:\tchrome\nVmRSS:\t 1000000 kB\n")
    _write(tmp_path / "12" / "status", "Name:\tnode\nVmRSS:\t  600000 kB\n")
    _write(tmp_path / "13" / "status", "Name:\tkthreadd\n")  # kernel thread：無 VmRSS
    _write(tmp_path / "self" / "status", "Name:\tignored\nVmRSS:\t 9 kB\n")  # 非數字目錄略過
    top = mpa.top_rss_by_name(str(tmp_path), n=2)
    assert top == [("chrome", 7_000_000), ("node", 600_000)]


def test_format_alert_mentions_numbers():
    text = mpa.format_alert(1_048_576, 20_480_000, [("chrome", 13_000 * MB)], low_mb=3072)
    assert "1.0 GB" in text
    assert "3.0 GB" in text
    assert "chrome" in text
