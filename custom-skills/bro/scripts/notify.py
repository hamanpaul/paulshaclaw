#!/usr/bin/env python3
"""One-way PaulShiaBro Telegram notification (fire-and-forget status pings).

`reply_bridge.py` 是「回覆」流程（回給 source user / 綁定用戶）。本工具是
「單向通知」——長跑任務進度、告警、里程碑那種只需要送達、不需要對話語境的
訊息。送達策略有兩層，任一成功即算送達：

1. **本地 max gateway（快路徑）**：若 127.0.0.1:7777 有 listener，POST `/notify`
   （`Authorization: Bearer $(cat ~/.max/api-token)`）。gateway 常沒開，探測不到
   就直接跳過、不算失敗。
2. **direct fallback**：復用 `reply_bridge.send_reply()` 走 canonical paulshaclaw
   config（`~/.config/paulshaclaw/*` secret + bindings）直打 Telegram Bot API，
   fan-out 給所有綁定用戶（或以 `--source-user-id` 限單一用戶）。

兩層用同一個 PaulShiaBro bot，送達目的地一致；gateway 只是本地優化。任一路成功
即 exit 0；兩路都失敗才 exit 1。祕密只在 runtime 讀取、絕不輸出。
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import socket
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Sequence

_SCRIPT_DIR = Path(__file__).resolve().parent
MAX_API_TOKEN_PATH = Path.home() / ".max" / "api-token"
MAX_GATEWAY_HOST = "127.0.0.1"
MAX_GATEWAY_PORT = 7777
MAX_GATEWAY_URL = f"http://{MAX_GATEWAY_HOST}:{MAX_GATEWAY_PORT}/notify"


def _load_reply_bridge():
    """Load the sibling reply_bridge module without requiring a package install."""
    path = _SCRIPT_DIR / "reply_bridge.py"
    spec = importlib.util.spec_from_file_location("reply_bridge", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"無法載入 {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def gateway_listening(host: str = MAX_GATEWAY_HOST, port: int = MAX_GATEWAY_PORT, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def send_via_gateway(text: str, *, url: str = MAX_GATEWAY_URL, token_path: Path | None = None,
                     opener=urllib.request.urlopen, timeout: float = 10.0) -> bool:
    """POST to the local max gateway. Returns True only on HTTP 200 + ok:true."""
    if token_path is None:
        token_path = MAX_API_TOKEN_PATH
    try:
        token = token_path.read_text().strip()
    except OSError:
        return False
    if not token:
        return False
    body = json.dumps({"text": text}).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        with opener(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", "ignore")
            status = getattr(response, "status", 200)
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
    return status == 200 and '"ok":true' in raw.replace(" ", "").lower()


def notify(
    text: str,
    *,
    source_user_id: int | None = None,
    use_gateway: bool = True,
    reply_bridge=None,
    gateway_probe=gateway_listening,
    gateway_sender=send_via_gateway,
    dry_run: bool = False,
) -> str:
    """Send a one-way notification. Returns the delivery path used:
    'gateway' | 'direct' | 'dry-run'. Raises RuntimeError if all paths fail."""
    if not text.strip():
        raise ValueError("notify text 不可為空")
    if dry_run:
        return "dry-run"
    if use_gateway and gateway_probe():
        if gateway_sender(text):
            return "gateway"
    bridge = reply_bridge or _load_reply_bridge()
    try:
        bridge.send_reply(text=text, source_user_id=source_user_id)
    except Exception as error:  # noqa: BLE001 - surface any bridge failure as delivery failure
        raise RuntimeError(f"direct fallback 送達失敗: {error}") from error
    return "direct"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Send a one-way PaulShiaBro Telegram notification (gateway-first, direct fallback)")
    parser.add_argument("--text", help="通知內容（省略則從 stdin 讀）")
    parser.add_argument("--source-user-id", type=int, help="direct fallback 只送給此綁定用戶（省略=fan-out 全部）")
    parser.add_argument("--no-gateway", action="store_true", help="跳過本地 gateway，直接走 direct")
    parser.add_argument("--dry-run", action="store_true", help="不實送，僅回報將採用的路徑")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    text = args.text if args.text is not None else sys.stdin.read()
    text = (text or "").strip()
    if not text:
        print("錯誤: 空訊息", file=sys.stderr)
        return 2
    try:
        path = notify(
            text,
            source_user_id=args.source_user_id,
            use_gateway=not args.no_gateway,
            dry_run=args.dry_run,
        )
    except (ValueError, RuntimeError) as error:
        print(f"錯誤: {error}", file=sys.stderr)
        return 1
    print(f"已送達（{path}）", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
