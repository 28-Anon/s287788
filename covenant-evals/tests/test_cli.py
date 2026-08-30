"""Tests for the CLI's argument wiring and the .env loader."""

import os

from covenant_evals.cli import build_parser, load_dotenv


def test_corpus_search_requires_a_query():
    parser = build_parser()
    args = parser.parse_args(["corpus", "search", "--query", '"credit agreement"'])
    assert args.command == "corpus"
    assert args.corpus_command == "search"
    assert args.forms == "8-K"
    assert args.limit == 20


def test_corpus_add_requires_a_cik():
    args = build_parser().parse_args(
        ["corpus", "add", "0000950170-24-012345:ex101.htm", "--cik", "320123"]
    )
    assert args.ref.endswith("ex101.htm")
    assert args.cik == "320123"


def test_fetch_force_flag_defaults_off():
    assert build_parser().parse_args(["corpus", "fetch"]).force is False
    assert build_parser().parse_args(["corpus", "fetch", "--force"]).force is True


def test_dotenv_reads_values(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('EDGAR_USER_AGENT="Ada Lovelace ada@analytical-engine.org"\n# comment\n\n')
    monkeypatch.delenv("EDGAR_USER_AGENT", raising=False)

    load_dotenv(env)
    assert os.environ["EDGAR_USER_AGENT"] == "Ada Lovelace ada@analytical-engine.org"


def test_existing_environment_wins_over_dotenv(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("EDGAR_USER_AGENT=from-file\n")
    monkeypatch.setenv("EDGAR_USER_AGENT", "from-shell")

    load_dotenv(env)
    assert os.environ["EDGAR_USER_AGENT"] == "from-shell"


def test_missing_dotenv_is_not_an_error(tmp_path):
    load_dotenv(tmp_path / "absent")
