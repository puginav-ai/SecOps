"""Загрузчик .env и хелперы окружения."""

from __future__ import annotations

import os

import pytest

from config.env import env, env_bool, env_int, env_list, load_dotenv


def test_load_dotenv_parses_file_and_environment_wins(tmp_path, monkeypatch):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        'FOO=from-file\n# comment\nBAR="quoted"\nEMPTY=\nBROKEN-LINE\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("FOO", "from-env")

    parsed = load_dotenv(dotenv)

    assert parsed["FOO"] == "from-file"
    assert parsed["BAR"] == "quoted"
    assert parsed["EMPTY"] == ""
    assert "BROKEN-LINE" not in parsed
    assert os.environ["FOO"] == "from-env"  # реальное окружение приоритетнее файла


def test_load_dotenv_missing_file_returns_empty(tmp_path):
    assert load_dotenv(tmp_path / "nope.env") == {}


def test_env_helpers(monkeypatch):
    monkeypatch.setenv("TEST_INT", "42")
    monkeypatch.setenv("TEST_BOOL", "yes")
    monkeypatch.setenv("TEST_LIST", "a, b,,")
    monkeypatch.delenv("TEST_BOOL_DEFAULT", raising=False)

    assert env_int("TEST_INT", 0) == 42
    assert env_bool("TEST_BOOL") is True
    assert env_bool("TEST_BOOL_DEFAULT") is False
    assert env_list("TEST_LIST") == ["a", "b"]
    assert env("TEST_MISSING", "fallback") == "fallback"
    with pytest.raises(RuntimeError):
        env("TEST_MISSING_NO_DEFAULT")
