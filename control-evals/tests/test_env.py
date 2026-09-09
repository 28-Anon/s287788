"""Finding the API key, and failing usefully when it is not there.

Worth its own file because the failure this prevents is the confusing kind. The SDK does
not raise when there is no credential — it defers auth to the first request — so a keyless
sweep used to "succeed": every run failed inside the loop, was recorded as an error, and the
report came back all n/a with nothing saying why.
"""

import os

import pytest

from control_evals.env import (
    ENV_FILES,
    load_dotenv,
    missing_key_message,
    read_env_file,
    strays,
)


@pytest.fixture
def clean_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return monkeypatch


def write(path, text):
    path.write_text(text, encoding="utf-8")
    return path


def test_reads_key_value_lines(tmp_path):
    env = write(tmp_path / ".env", "ANTHROPIC_API_KEY=sk-ant-abc\nOTHER=2\n")
    assert read_env_file(env) == {"ANTHROPIC_API_KEY": "sk-ant-abc", "OTHER": "2"}


def test_ignores_comments_blank_lines_and_junk(tmp_path):
    env = write(
        tmp_path / ".env",
        "# a comment\n\n  \nANTHROPIC_API_KEY=sk-ant-abc\nnot a pair\n",
    )
    assert read_env_file(env) == {"ANTHROPIC_API_KEY": "sk-ant-abc"}


def test_strips_quotes_people_actually_type(tmp_path):
    env = write(tmp_path / ".env", "ANTHROPIC_API_KEY=\"sk-ant-abc\"\nB='x'\n")
    assert read_env_file(env) == {"ANTHROPIC_API_KEY": "sk-ant-abc", "B": "x"}


def test_a_missing_file_is_not_an_error(tmp_path):
    assert read_env_file(tmp_path / "absent") == {}


def test_loads_the_first_file_that_has_a_key(tmp_path, clean_env):
    first = write(tmp_path / "one.env", "SOMETHING=else\n")
    second = write(tmp_path / "two.env", "ANTHROPIC_API_KEY=sk-ant-second\n")

    used = load_dotenv((first, second))

    assert used == second
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-second"
    assert os.environ["SOMETHING"] == "else", "earlier files still contribute their values"


def test_the_environment_always_wins(tmp_path, clean_env):
    clean_env.setenv("ANTHROPIC_API_KEY", "sk-ant-from-shell")
    env = write(tmp_path / ".env", "ANTHROPIC_API_KEY=sk-ant-from-file\n")

    assert load_dotenv((env,)) is None, "no file was needed"
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-from-shell"


def test_no_key_anywhere_returns_none(tmp_path, clean_env):
    assert load_dotenv((tmp_path / "absent",)) is None
    assert "ANTHROPIC_API_KEY" not in os.environ


def test_the_failure_message_names_every_file_it_looked_in(tmp_path):
    files = (tmp_path / "a.env", tmp_path / "b.env")
    message = missing_key_message(files)
    for path in files:
        assert str(path) in message
    assert "$env:ANTHROPIC_API_KEY" in message, "the fix, in the shell he actually uses"


def test_a_dot_env_saved_as_dot_env_txt_is_called_out(tmp_path):
    """The Windows failure that looks exactly like having no key at all."""
    write(tmp_path / ".env.txt", "ANTHROPIC_API_KEY=sk-ant-abc\n")
    files = (tmp_path / ".env",)

    assert strays(files) == [tmp_path / ".env.txt"]
    message = missing_key_message(files)
    assert ".env.txt" in message
    assert "Rename-Item" in message


def test_the_search_path_includes_the_other_project(tmp_path):
    """The key was asked for by covenant-evals first; do not make him save it twice.

    Compared as path components, not as a string ending in "control-evals/.env". That
    separator is `\\` on Windows, which is where this project is developed and where the
    string form of this assertion failed while CI on ubuntu stayed green — the same shape
    as the run id that contained a colon. `ENV_FILES` was right both times; the test was
    the thing that could not run on the author's machine.
    """
    assert any(p.parent.name == "control-evals" and p.name == ".env" for p in ENV_FILES)
    assert any("covenant-evals" in p.parts for p in ENV_FILES)


def test_no_key_value_is_ever_put_in_a_message(tmp_path):
    write(tmp_path / ".env", "ANTHROPIC_API_KEY=sk-ant-secret-value\n")
    assert "sk-ant-secret-value" not in missing_key_message((tmp_path / ".env",))
