"""#88：驗證 bro_queue 的序列化送出＋到達驗證機制。

核心情境：pane 忙碌/無回應時訊息不會遺失（留在佇列檔上可查）、佇列消化後真的
送達、佇列保序不越級（避免訊息倒序抵達）。busy-idle 偵測本身不在測試範圍內
——這裡刻意只測「send 之後 capture 有沒有驗到文字」這個機械式比對，不測任何
「猜 pane 忙不忙」的邏輯（因為我們沒做這件事，見模組 docstring 的實測結論）。
"""
from __future__ import annotations

import json

import pytest

from paulshaclaw.core import bro_queue


@pytest.fixture(autouse=True)
def _isolated_state_root(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_AGENTS_ROOT", str(tmp_path / "agents"))


def test_queue_file_path_strips_percent_and_uses_state_path():
    path = bro_queue.queue_file("%7")

    assert path.name == "7.jsonl"
    assert path.parent.name == "bro-queue"


def test_enqueue_then_flush_delivers_when_capture_confirms_immediately():
    bro_queue.enqueue("%9", "[bro:1] hello")

    result = bro_queue.flush(
        "%9",
        send=lambda pane_id, message: True,
        capture=lambda pane_id: "some screen text ... [bro:1] hello ... more",
    )

    assert result.delivered == 1
    assert result.remaining == 0
    assert bro_queue._read_entries(bro_queue.queue_file("%9")) == []


def test_flush_keeps_message_queued_when_never_confirmed():
    """pane 忙碌／無回應（capture 永遠驗不到訊息文字）——訊息必須還在佇列上，
    不能無聲蒸發（#88 的核心抱怨）。"""
    bro_queue.enqueue("%9", "[bro:1] hello")

    result = bro_queue.flush(
        "%9",
        send=lambda pane_id, message: True,
        capture=lambda pane_id: "",  # 畫面上永遠驗不到
        confirm_timeout=0.05,
        confirm_interval=0.01,
        sleep=lambda seconds: None,
    )

    assert result.delivered == 0
    assert result.remaining == 1
    entries = bro_queue._read_entries(bro_queue.queue_file("%9"))
    assert entries[0]["message"] == "[bro:1] hello"


def test_flush_does_not_skip_ahead_when_head_unconfirmed():
    """兩則訊息排隊；第一筆驗不到時，即使 capture 剛好會命中第二筆的文字，
    也不可以先送第二筆——保序，不能讓訊息倒著抵達。"""
    bro_queue.enqueue("%9", "[bro:1] first")
    bro_queue.enqueue("%9", "[bro:1] second")

    sent_messages: list[str] = []

    def fake_send(pane_id: str, message: str) -> bool:
        sent_messages.append(message)
        return True

    result = bro_queue.flush(
        "%9",
        max_attempts=5,
        send=fake_send,
        capture=lambda pane_id: "screen only ever shows ... second ...",
        confirm_timeout=0.02,
        confirm_interval=0.01,
        sleep=lambda seconds: None,
    )

    assert result.delivered == 0
    assert result.remaining == 2
    assert sent_messages == ["[bro:1] first"]  # 從沒試過送第二筆


def test_flush_confirms_after_a_few_polls_within_one_attempt():
    bro_queue.enqueue("%9", "[bro:1] hello")
    capture_calls = {"count": 0}

    def flaky_capture(pane_id: str) -> str:
        capture_calls["count"] += 1
        if capture_calls["count"] < 3:
            return ""  # 畫面還沒 render 出來
        return "[bro:1] hello"

    result = bro_queue.flush(
        "%9",
        send=lambda pane_id, message: True,
        capture=flaky_capture,
        confirm_timeout=1.0,
        confirm_interval=0.0,
        sleep=lambda seconds: None,
    )

    assert result.delivered == 1
    assert capture_calls["count"] == 3


def test_flush_drains_multiple_pending_entries_in_one_call():
    """模擬 Stop hook 消化積壓：agent 忙碌期間排了 3 則，一次 flush 應該全部送完。"""
    for i in range(3):
        bro_queue.enqueue("%9", f"[bro:1] msg-{i}")

    delivered_messages: list[str] = []

    def fake_send(pane_id: str, message: str) -> bool:
        delivered_messages.append(message)
        return True

    result = bro_queue.flush(
        "%9",
        max_attempts=10,
        send=fake_send,
        capture=lambda pane_id: delivered_messages[-1] if delivered_messages else "",
    )

    assert result.delivered == 3
    assert result.remaining == 0
    assert delivered_messages == ["[bro:1] msg-0", "[bro:1] msg-1", "[bro:1] msg-2"]


def test_flush_stops_and_keeps_queue_when_send_itself_fails():
    bro_queue.enqueue("%9", "[bro:1] hello")

    result = bro_queue.flush(
        "%9",
        send=lambda pane_id, message: False,  # tmux 層級失敗（pane 不存在等）
        capture=lambda pane_id: "unreachable",
    )

    assert result.delivered == 0
    assert result.remaining == 1


def test_flush_on_empty_queue_is_a_noop_and_never_calls_send_or_capture():
    calls: list[str] = []

    result = bro_queue.flush(
        "%9",
        send=lambda *a: calls.append("send") or True,
        capture=lambda *a: calls.append("capture") or "",
    )

    assert result.delivered == 0
    assert result.remaining == 0
    assert calls == []


def test_corrupted_queue_line_is_skipped_without_dropping_other_entries(tmp_path):
    path = bro_queue.queue_file("%9")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "not json at all\n" + json.dumps({"message": "[bro:1] ok", "queued_at": 1.0}) + "\n",
        encoding="utf-8",
    )

    result = bro_queue.flush(
        "%9",
        send=lambda pane_id, message: True,
        capture=lambda pane_id: "[bro:1] ok",
    )

    assert result.delivered == 1
    assert result.remaining == 0


def test_flush_persists_partial_progress_when_a_later_attempt_raises():
    """daemon 的 send 介面對硬性 tmux 失敗會直接 raise（保留既有語意，見
    `_send_to_pane_confirmed`）；多筆 attempts 裡前面幾筆已經確認送達後，
    後面那筆才炸掉的話，已送達的部份不能因為這個例外又跑回佇列裡重送一次。"""
    for i in range(3):
        bro_queue.enqueue("%9", f"[bro:1] msg-{i}")

    delivered_messages: list[str] = []

    def flaky_send(pane_id: str, message: str) -> bool:
        if message == "[bro:1] msg-1":
            raise ValueError("tmux not found")
        delivered_messages.append(message)
        return True

    with pytest.raises(ValueError):
        bro_queue.flush(
            "%9",
            max_attempts=10,
            send=flaky_send,
            capture=lambda pane_id: delivered_messages[-1] if delivered_messages else "",
        )

    assert delivered_messages == ["[bro:1] msg-0"]
    remaining = bro_queue._read_entries(bro_queue.queue_file("%9"))
    assert [entry["message"] for entry in remaining] == ["[bro:1] msg-1", "[bro:1] msg-2"]


def test_normalize_survives_line_wrapped_capture():
    """`_default_capture` 用 `tmux capture-pane -J` 把軟斷行重新接回同一邏輯行，
    保留斷行處原有的空白；剩下的 `\\n` 都是畫面上真實存在的行界（例如我們的
    訊息剛好落在輸入框邊界旁邊），驗證比對要能攤平這些行界再比對一次。"""
    bro_queue.enqueue("%9", "[bro:1] hello world")

    result = bro_queue.flush(
        "%9",
        send=lambda pane_id, message: True,
        capture=lambda pane_id: "prefix\n[bro:1] hello \nworld\nsuffix",
    )

    assert result.delivered == 1
    assert result.remaining == 0
