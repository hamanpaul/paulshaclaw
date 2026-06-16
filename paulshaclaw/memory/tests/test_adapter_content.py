from pathlib import Path
from paulshaclaw.memory.importer.adapters import base

FIX = Path(__file__).parent / "fixtures"


def test_read_claude_transcript_extracts_prompts_summary_touched():
    out = base.read_claude_transcript(FIX / "claude_transcript.jsonl")
    assert out["user_prompts"] == ["幫我修 UART 升級流程"]
    assert out["assistant_summary"] == "已修好 UART 升級流程並加上重試。"
    assert out["touched_files"] == ["/repo/uart.py"]  # deduped, order-preserved


def test_read_claude_transcript_missing_file_is_empty():
    out = base.read_claude_transcript(FIX / "does_not_exist.jsonl")
    assert out == {"user_prompts": [], "assistant_summary": "", "touched_files": []}


def test_read_copilot_history_extracts_from_chatmessages(tmp_path):
    d = tmp_path / ".copilot" / "history-session-state"
    d.mkdir(parents=True)
    (d / "session_cop-1_123.json").write_text((FIX / "copilot_history.json").read_text(), encoding="utf-8")
    out = base.read_copilot_history(tmp_path, "cop-1")
    assert out["user_prompts"] == ["列出 PON HLAPI"]
    assert out["assistant_summary"] == "已整理 PON HLAPI 對照表。"


def test_read_codex_rollout_extracts_prompts_only():
    out = base.read_codex_rollout(FIX / "codex_rollout.jsonl")
    assert out["user_prompts"] == ["請幫我產生 codex 範例"]
    # assistant summary comes from the queue payload's last_assistant_message,
    # not from the rollout file — read_codex_rollout returns prompts only.
    assert "assistant_summary" not in out
