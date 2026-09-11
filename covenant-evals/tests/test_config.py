"""Tests for the offline setup check.

The failure this command exists to catch is the confusing one: a .env saved as .env.txt is
ignored in silence, and the 403 that follows looks like an SEC problem rather than a
filename problem.
"""

import pytest

from covenant_evals.cli import cmd_config_check, mask_email


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """A fake repo root, with the environment cleared so .env is the only source."""
    monkeypatch.setattr("covenant_evals.cli.REPO_ROOT", tmp_path)
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".gitignore").write_text(".env\n__pycache__/\n")
    return tmp_path


def test_a_correct_setup_passes(repo, capsys):
    (repo / ".env").write_text('EDGAR_USER_AGENT="Ada Lovelace ada@analytical-engine.org"\n')
    assert cmd_config_check() == 0
    out = capsys.readouterr().out
    assert "[FAIL]" not in out
    assert "corpus doctor" in out


def test_a_missing_env_file_is_reported(repo, capsys):
    assert cmd_config_check() == 1
    assert "no .env at" in capsys.readouterr().out


def test_a_notepad_mangled_filename_is_caught(repo, capsys):
    # The exact trap: "Save as type" left on Text Documents.
    (repo / ".env.txt").write_text('EDGAR_USER_AGENT="Ada Lovelace ada@analytical-engine.org"\n')
    assert cmd_config_check() == 1
    out = capsys.readouterr().out
    assert ".env.txt" in out
    assert "Rename-Item" in out, "must give the Windows fix, not just the diagnosis"


def test_a_user_agent_without_an_email_is_rejected_before_edgar_sees_it(repo, capsys):
    (repo / ".env").write_text("EDGAR_USER_AGENT=Salah\n")
    assert cmd_config_check() == 1
    assert "will be rejected" in capsys.readouterr().out


def test_a_placeholder_user_agent_is_rejected(repo, capsys):
    (repo / ".env").write_text('EDGAR_USER_AGENT="Your Name your.email@example.com"\n')
    assert cmd_config_check() == 1
    assert "will be rejected" in capsys.readouterr().out


def test_env_not_gitignored_fails(repo, capsys):
    (repo / ".env").write_text('EDGAR_USER_AGENT="Ada Lovelace ada@analytical-engine.org"\n')
    (repo / ".gitignore").write_text("__pycache__/\n")
    assert cmd_config_check() == 1
    assert "NOT gitignored" in capsys.readouterr().out


def test_the_api_key_is_optional_this_early(repo, capsys):
    (repo / ".env").write_text('EDGAR_USER_AGENT="Ada Lovelace ada@analytical-engine.org"\n')
    assert cmd_config_check() == 0
    assert "nothing needs it until week 8" in capsys.readouterr().out


# -- masking ---------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("Ada Lovelace ada@site.org", "Ada Lovelace a**@site.org"),
        ("Salah Missana salahmissana@icloud.com", "Salah Missana s***********@icloud.com"),
        ("No Email Here", "No Email Here"),
    ],
)
def test_addresses_are_masked_so_the_output_is_safe_to_paste(raw, expected):
    assert mask_email(raw) == expected


def test_masking_keeps_the_domain_so_a_typo_is_still_visible():
    # The point is to let you check the address is right, not to hide it from you.
    assert mask_email("Ada ada@gmial.com").endswith("@gmial.com")
