"""Telegram → agent pane 的送出序列化與到達驗證（#88）。

`daemon._send_to_pane()` 原本是無條件 `tmux send-keys`：pane busy 時字元會插進
agent 現有輸入中間，daemon 也無從得知有沒有真的送達，agent 卡死/OOM 時訊息就
無聲蒸發。這裡改成單一序列化出口：每則訊息先落地成 per-pane JSONL 佇列，
`flush()` 永遠只嘗試佇列最前面那一筆，send-keys 之後短暫輪詢 `capture-pane`
確認文字真的出現在畫面上；沒確認到就整批留在佇列裡（保序、不越級），交給下一次
呼叫（下一則使用者訊息，或 agent Stop hook 結束當下）重試。

busy-idle 偵測本身刻意不做：對現場 tmux pane 實測過，claude/gemma4 這類 TUI
（非 shell）畫面最後一行恆是自己的 footer／輸入框，不會以 `$`/`>` 結尾；輸入框
內文字（idle 佔位、或使用者已輸入但尚未送出的暫存訊息）與「正在產生輸出」在單張
截圖上經常無法可靠分辨。把這種猜測包裝成「偵測到 busy」只會製造假安全感，比不做
還糟——因此改用「送出後驗證有沒有出現」取代「送出前猜測忙不忙」。

驗證機制的邊界（實測結論，別誤讀成「保證恰好一次」）：

- shell pane 送出後文字會 echo，**忙碌中送出也驗得到**，且忙完真的只執行一次
  （實測：`sleep` 執行中 send-keys → `delivered=1`，sleep 結束後訊息被執行一次）。
- pane 不存在時 send 硬失敗，佇列原樣保留，不會遺失。
- 但目標程式若**不原樣回顯**收到的文字，就會驗不到而保守失敗：實測 `less` 會把
  輸入當自己的命令吃掉、畫面只剩殘句，於是訊息其實已經送達卻仍留在佇列，下次
  flush 會**重送一次**。也就是說重送的觸發條件不只「render 慢於確認視窗」，
  而是「畫面上找不到原字串」的所有情形。這個取捨是刻意的：寧可偶爾重複，也不要
  像改版前那樣有時完全遺失且零痕跡。
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from paulshaclaw.config import paths


def queue_file(pane_id: str) -> Path:
    """單一 pane 的送出佇列檔路徑——JSONL，一行一則待送訊息。"""
    safe_name = pane_id.lstrip("%") or "unknown"
    return paths.state_path("bro-queue", f"{safe_name}.jsonl")


@contextlib.contextmanager
def _locked(pane_id: str) -> Iterator[None]:
    """跨程序鎖：daemon（route_to_agent）與 Stop hook 都可能同時碰同一個佇列檔。"""
    lock_path = queue_file(pane_id).with_suffix(".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


def _read_entries(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    entries: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except (json.JSONDecodeError, ValueError):
            continue  # 壞掉的單行不拖垮整個佇列
    return entries


def _write_entries(path: Path, entries: list[dict[str, object]]) -> None:
    if not entries:
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(entry, ensure_ascii=False) for entry in entries) + "\n",
        encoding="utf-8",
    )


def enqueue(pane_id: str, message: str) -> Path:
    """把訊息接到 pane 佇列尾端；回傳佇列檔路徑供呼叫端記錄／除錯。"""
    with _locked(pane_id):
        path = queue_file(pane_id)
        entries = _read_entries(path)
        entries.append({"message": message, "queued_at": time.time()})
        _write_entries(path, entries)
    return path


def _default_send(pane_id: str, message: str) -> bool:
    try:
        subprocess.run(
            ["tmux", "send-keys", "-t", pane_id, "-l", message],
            check=True, capture_output=True,
        )
        subprocess.run(
            ["tmux", "send-keys", "-t", pane_id, "Enter"],
            check=True, capture_output=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False
    return True


def _default_capture(pane_id: str, *, lines: int = 200) -> str:
    try:
        result = subprocess.run(
            # -J：把因 pane 寬度造成的軟斷行重新接回同一邏輯行（保留斷行處的空白），
            # 避免長訊息單純因為剛好卡在換行位置就被誤判成沒送達。
            ["tmux", "capture-pane", "-p", "-J", "-t", pane_id, "-S", f"-{lines}"],
            check=True, capture_output=True, text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    return result.stdout


def _normalize(text: str) -> str:
    # tmux 依 pane 寬度換行，長訊息可能被截成兩個畫面行；比對前先攤平，
    # 避免單純因為斷行位置就誤判成「沒送達」。
    return text.replace("\r", "").replace("\n", "")


@dataclass(frozen=True)
class FlushResult:
    delivered: int
    remaining: int
    pending_seconds: float | None  # 佇列最前面那筆已經等了多久


def flush(
    pane_id: str,
    *,
    max_attempts: int = 1,
    send: Callable[[str, str], bool] = _default_send,
    capture: Callable[[str], str] = _default_capture,
    confirm_timeout: float = 0.25,
    confirm_interval: float = 0.05,
    sleep: Callable[[float], None] = time.sleep,
) -> FlushResult:
    """嘗試把佇列最前面的訊息送出並驗證；一次呼叫最多處理 `max_attempts` 筆。

    `send` 失敗（例外或回傳 False）與驗證逾時都會讓迴圈在該筆停下並保留佇列——
    刻意不嘗試佇列裡更後面的項目，避免跳號造成訊息倒序抵達。
    """
    with _locked(pane_id):
        path = queue_file(pane_id)
        entries = _read_entries(path)
        delivered = 0
        try:
            for _ in range(max_attempts):
                if not entries:
                    break
                head = entries[0]
                message = str(head.get("message", ""))
                if not send(pane_id, message):
                    break
                deadline = time.monotonic() + confirm_timeout
                confirmed = False
                while True:
                    if _normalize(message) in _normalize(capture(pane_id)):
                        confirmed = True
                        break
                    if time.monotonic() >= deadline:
                        break
                    sleep(confirm_interval)
                if not confirmed:
                    break
                entries.pop(0)
                delivered += 1
        finally:
            # `send` 若是會 raise 的實作（daemon 對硬性 tmux 失敗維持既有語意），
            # 例外會從這裡繼續往外炸；但無論如何，這個 finally 先把目前為止已經
            # 確認送達的項目寫回磁碟，不讓多筆 attempts 裡的部份進度因為後面
            # 那筆的例外而遺失、造成下次重複重送。
            _write_entries(path, entries)
        pending_seconds = None
        if entries:
            queued_at = entries[0].get("queued_at")
            if isinstance(queued_at, (int, float)):
                pending_seconds = max(0.0, time.time() - queued_at)
    return FlushResult(delivered=delivered, remaining=len(entries), pending_seconds=pending_seconds)
