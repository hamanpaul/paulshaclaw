from paulshaclaw.memory.atomizer import pipeline as apipe
from paulshaclaw.memory.atomizer.config import (
    is_safe_path_component,
    load_config,
    sanitize_project_component,
)


def test_sanitize_url_project_is_path_safe():
    out = sanitize_project_component("github.com/hamanpaul/serialwrap")
    assert is_safe_path_component(out)
    assert "/" not in out
    assert out == "github.com__hamanpaul__serialwrap"


def test_sanitize_plain_slug_unchanged():
    assert sanitize_project_component("paulshaclaw") == "paulshaclaw"


def test_sanitize_rejects_traversal():
    assert ".." not in sanitize_project_component("../etc/passwd")


def test_url_project_session_is_not_skipped(tmp_path):
    inbox = tmp_path / "inbox" / "sessions" / "claude-code" / "2026-06-16"
    inbox.mkdir(parents=True)
    (inbox / "s1.md").write_text(
        "---\nmemory_layer: inbox\nproject: github.com/hamanpaul/serialwrap\n"
        "source_agent: claude-code\nsource_session: s1\ncaptured_at: 2026-06-16\n---\n"
        "## Summary\nUART 修復\n\n## Prompts\n1. 修 UART\n",
        encoding="utf-8",
    )
    cfg, config_hash = load_config()
    out = apipe.run(tmp_path, config=cfg, config_hash=config_hash, now="2026-06-16T00:00:00Z")

    # The slash-containing project must NOT trigger an unsafe-path skip.
    assert out["summary"]["split_sessions"] >= 1
    assert not any("unsafe path" in w for w in out["warnings"])

    # Files land under the sanitized (slash-free) project dir; no slash dir is created.
    files = [str(p) for p in tmp_path.rglob("*") if p.is_file()]
    assert any("github.com__hamanpaul__serialwrap" in s for s in files)
    assert not any("github.com/hamanpaul/serialwrap" in s for s in files)


def test_url_project_session_promotes_to_knowledge_with_content(tmp_path):
    inbox = tmp_path / "inbox" / "sessions" / "claude-code" / "2026-06-16"
    inbox.mkdir(parents=True)
    (inbox / "s1.md").write_text(
        "---\nmemory_layer: inbox\nproject: github.com/hamanpaul/serialwrap\n"
        "source_agent: claude-code\nsource_session: s1\ncaptured_at: 2026-06-16\n---\n"
        "## Summary\nUART 修復完成\n\n## Prompts\n1. 修 UART\n",
        encoding="utf-8",
    )
    cfg, config_hash = load_config()
    out = apipe.run(tmp_path, config=cfg, config_hash=config_hash, now="2026-06-16T00:00:00Z")

    # Regression: a slash-project session must promote ALL THE WAY to knowledge, not
    # just split. The first sanitize fix missed _read_fragment, leaving promote at
    # slices:0 so backfilled content never reached the knowledge layer.
    assert out["summary"]["slices"] >= 1
    knowledge = list((tmp_path / "knowledge").rglob("*.md"))
    assert knowledge
    bodies = "\n".join(p.read_text(encoding="utf-8") for p in knowledge)
    assert "UART 修復完成" in bodies or "修 UART" in bodies
