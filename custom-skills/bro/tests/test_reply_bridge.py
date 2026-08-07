from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.request import Request
from unittest import mock

import importlib.util


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "reply_bridge.py"
SPEC = importlib.util.spec_from_file_location("reply_bridge", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load {SCRIPT_PATH}")
reply_bridge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = reply_bridge
SPEC.loader.exec_module(reply_bridge)

# reply_bridge.py 本身不可 import paulshaclaw.*（見檔內註解），但「這個測試檔」
# 只在 repo venv 裡跑，可以合法 import facade 來比對兩邊是否仍一致——這就是
# issue #90 要補的「工具提醒」：facade 改了預設路徑而 reply_bridge.py 沒跟著改時，
# 這裡會紅燈，而不是等到人肉發現漂移。
from paulshaclaw.bot import reply as bot_reply


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class FakeOpener:
    def __init__(self, responses: list[dict[str, object]]) -> None:
        self.responses = list(responses)
        self.requests: list[dict[str, object]] = []

    def __call__(self, request: Request, timeout: float) -> FakeResponse:
        self.requests.append(
            {
                "url": request.full_url,
                "data": request.data or b"",
                "timeout": timeout,
            }
        )
        if not self.responses:
            raise AssertionError("no fake response queued")
        return FakeResponse(self.responses.pop(0))


class ReplyBridgeTests(unittest.TestCase):
    def _write_runtime_files(self, tmpdir: str) -> tuple[Path, Path, Path]:
        config_path = Path(tmpdir) / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "daemon_name": "psc",
                    "default_project": "demo",
                    "allowed_user_ids": [7, 8],
                    "coordinator": {"phase": "stage1", "default_payload": {}},
                    "pane_assignments": [
                        {"pane_id": "%0", "title": "cockpit", "task_id": "task-1", "status": "ready"}
                    ],
                }
            ),
            encoding="utf-8",
        )
        secret_env_path = Path(tmpdir) / "telegram.env"
        secret_env_path.write_text("PSC_TELEGRAM_BOT_TOKEN=fake-token\n", encoding="utf-8")
        bindings_path = Path(tmpdir) / "bindings.json"
        bindings_path.write_text(json.dumps({"7": 1001, "8": 1002}), encoding="utf-8")
        return config_path, secret_env_path, bindings_path

    def test_send_reply_uses_bound_source_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path, secret_env_path, bindings_path = self._write_runtime_files(tmpdir)
            opener = FakeOpener([{"ok": True, "result": {"message_id": 1}}])

            targets = reply_bridge.send_reply(
                text="skill-local reply",
                source_user_id=7,
                config_path=config_path,
                secret_env_path=secret_env_path,
                bindings_path=bindings_path,
                opener=opener,
            )

            self.assertEqual(targets, [reply_bridge.ReplyTarget(user_id=7, chat_id=1001)])
            self.assertEqual(
                json.loads(opener.requests[0]["data"].decode("utf-8")),
                {"chat_id": 1001, "text": "skill-local reply"},
            )

    def test_send_reply_dry_run_avoids_network(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path, secret_env_path, bindings_path = self._write_runtime_files(tmpdir)

            targets = reply_bridge.send_reply(
                text="dry run",
                source_user_id=None,
                config_path=config_path,
                secret_env_path=secret_env_path,
                bindings_path=bindings_path,
                dry_run=True,
            )

            self.assertEqual(
                targets,
                [
                    reply_bridge.ReplyTarget(user_id=7, chat_id=1001),
                    reply_bridge.ReplyTarget(user_id=8, chat_id=1002),
                ],
            )

    def test_main_reports_clean_error(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(reply_bridge, "send_reply", side_effect=reply_bridge.TelegramApiError("Bad Request")),
            mock.patch("sys.stdout", stdout),
            mock.patch("sys.stderr", stderr),
        ):
            exit_code = reply_bridge.main(["--text", "hello"])

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("錯誤: Bad Request", stderr.getvalue())

    def test_default_paths_match_facade(self) -> None:
        """issue #90：reply_bridge.py 的四個字面預設常數必須與
        paulshaclaw.bot.reply 的 default_*_path() facade 一致——兩邊本是
        同一組慣例路徑的獨立副本（standalone 工具不可 import facade），
        漂移只能靠這個測試攔，不會有其他工具提醒。"""
        self.assertEqual(reply_bridge.DEFAULT_CONFIG_PATH, bot_reply.default_config_path())
        self.assertEqual(reply_bridge.DEFAULT_SECRET_ENV_PATH, bot_reply.default_secret_env_path())
        self.assertEqual(reply_bridge.DEFAULT_BINDINGS_PATH, bot_reply.default_bindings_path())
        self.assertEqual(reply_bridge.DEFAULT_MESSAGE_PANE_MAP_PATH, bot_reply.default_message_pane_map_path())

    def test_default_config_path_priority_arg_beats_env_beats_default(self) -> None:
        """優先序回歸（issue #90 約束4）：--config 參數 > PSC_STAGE1_CONFIG
        env > 內建預設，順序不可變——因為正式環境（如 systemd 多實例部署）
        會靠 PSC_STAGE1_CONFIG 覆寫成 per-instance 路徑。"""
        explicit = Path("/tmp/explicit-config.json")
        env_with_override = {"PSC_STAGE1_CONFIG": "/tmp/env-config.json"}

        self.assertEqual(
            reply_bridge._default_config_path(config_path=explicit, env=env_with_override),
            explicit,
        )
        self.assertEqual(
            reply_bridge._default_config_path(config_path=None, env=env_with_override),
            Path("/tmp/env-config.json"),
        )
        self.assertEqual(
            reply_bridge._default_config_path(config_path=None, env={}),
            reply_bridge.DEFAULT_CONFIG_PATH,
        )

    def test_default_secret_env_path_priority_env_beats_default(self) -> None:
        """同上，secret-env 版本：PSC_TELEGRAM_SECRET_ENV 設了就不看
        DEFAULT_SECRET_ENV_PATH 是否存在；都沒有時，預設檔不存在則回傳
        None（讓呼叫端可改用已注入的 PSC_TELEGRAM_BOT_TOKEN，不強制報錯）。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / "env-secret.env"
            env_path.write_text("PSC_TELEGRAM_BOT_TOKEN=x\n", encoding="utf-8")

            self.assertEqual(
                reply_bridge._default_secret_env_path({"PSC_TELEGRAM_SECRET_ENV": str(env_path)}),
                env_path,
            )

        with mock.patch.object(reply_bridge, "DEFAULT_SECRET_ENV_PATH", Path(tempfile.gettempdir()) / "psc-90-nonexistent.env"):
            self.assertIsNone(reply_bridge._default_secret_env_path({}))

    def test_send_reply_resolves_defaults_without_explicit_paths(self) -> None:
        """回歸測試（issue #90 約束2 的實際生產情境）：
        scripts/gemma4-hooks/bro_out.py 與 psc-bro-return.py 呼叫
        reply_bridge.py 時目前只傳 --source-user-id / --text，不傳任何路徑
        參數。此測試把整支 script 當 subprocess 跑、只覆寫 HOME，證明在
        「呼叫端不傳路徑」的情境下，reply_bridge 仍能從 DEFAULT_*_PATH
        指向的慣例位置（$HOME 底下）正確解析設定——而不是必須靠呼叫端
        傳路徑才能動。"""
        with tempfile.TemporaryDirectory() as home_dir:
            home = Path(home_dir)
            config_path = home / ".config" / "paulshaclaw" / "paulshaclaw.state.json"
            secret_env_path = home / ".config" / "paulshaclaw" / "paulshaclaw.telegram.secret.env"
            bindings_path = home / ".agents" / "state" / "telegram-chat-bindings.json"
            for path in (config_path, secret_env_path, bindings_path):
                path.parent.mkdir(parents=True, exist_ok=True)
            config_path.write_text(json.dumps({"allowed_user_ids": [7]}), encoding="utf-8")
            secret_env_path.write_text("PSC_TELEGRAM_BOT_TOKEN=fake-token\n", encoding="utf-8")
            bindings_path.write_text(json.dumps({"7": 1001}), encoding="utf-8")

            env = dict(os.environ)
            env["HOME"] = str(home)
            for key in ("PSC_STAGE1_CONFIG", "PSC_TELEGRAM_SECRET_ENV", "PSC_TELEGRAM_BINDINGS_PATH"):
                env.pop(key, None)

            result = subprocess.run(
                [sys.executable, str(SCRIPT_PATH), "--source-user-id", "7", "--text", "hi", "--dry-run"],
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("user=7 chat=1001", result.stdout)
