from paulshaclaw.memory.importer import title


def test_generate_uses_runner_and_truncates_to_20():
    long = "這是一個非常長的標題會超過二十個中文字所以一定要被截斷對吧真的很長"
    out, source = title.generate_title(
        {"user_prompts": ["問題"], "assistant_summary": "答案"},
        runner=lambda text, cmd, timeout: long,
    )
    assert source == "gemma4"
    assert len(out) <= 20


def test_generate_falls_back_when_runner_raises():
    out, source = title.generate_title(
        {"user_prompts": ["幫我修 UART 升級流程很長很長很長很長很長很長很長"], "assistant_summary": "x"},
        runner=lambda text, cmd, timeout: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    assert source == "fallback"
    assert len(out) <= 20
    assert out.startswith("幫我修")


def test_default_runner_fails_fast_when_backend_unreachable(monkeypatch):
    import paulshaclaw.memory.importer.title as t

    monkeypatch.setattr(t, "_gemma4_reachable", lambda *a, **k: False)
    out, source = t.generate_title({"user_prompts": ["主題"], "assistant_summary": "y"})
    assert source == "fallback"
    assert out == "主題"


def test_generate_falls_back_on_empty_llm_output():
    out, source = title.generate_title(
        {"user_prompts": ["主題"], "assistant_summary": "y"},
        runner=lambda text, cmd, timeout: "   ",
    )
    assert source == "fallback"


def test_apply_caches_and_sets_fields(tmp_path):
    calls = []

    def runner(text, cmd, timeout):
        calls.append(1)
        return "簡短標題"

    sess = {"session_id": "s9", "user_prompts": ["a"], "assistant_summary": "b"}
    s1 = title.apply(dict(sess), memory_root=tmp_path, runner=runner)
    title.apply(dict(sess), memory_root=tmp_path, runner=runner)
    assert s1["assistant_summary"] == "簡短標題"
    assert s1["title_source"] == "gemma4"
    assert len(calls) == 1  # second call hit cache


def test_pipeline_injects_title_into_inbox(tmp_path, monkeypatch):
    import json as _json
    from pathlib import Path
    from paulshaclaw.memory.importer import pipeline

    monkeypatch.setattr(
        "paulshaclaw.memory.importer.title._default_runner",
        lambda text, cmd, timeout: "UART 升級修復",
    )
    fix = Path(__file__).parent / "fixtures" / "claude_transcript.jsonl"
    qdir = tmp_path / "inbox-queue"
    qdir.mkdir()
    qp = qdir / "q.json"
    qp.write_text(_json.dumps({"tool": "claude-code", "session_id": "s1", "cwd": "/repo",
                               "transcript_path": str(fix)}), encoding="utf-8")
    decision = pipeline.ingest_queue_item(qp, memory_root=tmp_path, dry_run=True)
    rendered = decision["rendered"]
    assert "title: UART 升級修復" in rendered
    assert "title_source: gemma4" in rendered
    assert "## Summary\nUART 升級修復" in rendered
