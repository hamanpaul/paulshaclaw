from __future__ import annotations

import pytest

from paulshaclaw.deck.compile import DeckCompileError, slugify_task, specs_dir


def test_slugify_basic():
    assert slugify_task("Add LED Blink Mode!") == "add-led-blink-mode"


def test_slugify_length_cap_60():
    assert len(slugify_task("x" * 200)) <= 60


def test_slugify_empty_rejected():
    with pytest.raises(DeckCompileError):
        slugify_task("！！！")


def test_specs_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("PSC_MANAGER_SPECS_DIR", str(tmp_path))
    assert specs_dir() == tmp_path


def test_specs_dir_equals_manager_default(monkeypatch):
    from paulshaclaw.coordinator.manager_daemon import default_specs_dir

    monkeypatch.delenv("PSC_MANAGER_SPECS_DIR", raising=False)
    assert str(specs_dir()) == default_specs_dir()
