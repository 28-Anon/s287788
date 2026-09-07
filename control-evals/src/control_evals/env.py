"""Finding the API key, and saying where it came from.

Ported from covenant-evals, which learned this the hard way: on Windows a `.env` saved by
Notepad becomes `.env.txt`, is ignored in silence, and the resulting failure looks like a
bad key rather than a missing file. Every function here is dependency-free and every failure
names the exact file it looked in.

**Existing environment variables always win.** `$env:ANTHROPIC_API_KEY="..."` in the shell
overrides any file, so a one-off run never has to touch a saved secret.
"""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = PROJECT_ROOT.parent

#: Where a key may live, in the order searched. `covenant-evals/.env` is included because
#: that project asked for the key first and this one should not make you save it twice.
ENV_FILES = (
    PROJECT_ROOT / ".env",
    REPO_ROOT / ".env",
    REPO_ROOT / "covenant-evals" / ".env",
)

#: A `.env` that Notepad or Explorer has quietly renamed. Worth naming explicitly, because
#: the symptom is indistinguishable from having no key at all.
STRAY_NAMES = (".env.txt", ".env.env", "env", ".env.example.txt")


def read_env_file(path: Path) -> dict[str, str]:
    """KEY=value lines from one file. Blank lines and `#` comments ignored."""
    if not path.exists():
        return {}

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip("\"'")
    return values


def load_dotenv(files: tuple[Path, ...] | None = None) -> Path | None:
    """Load the first file that defines ANTHROPIC_API_KEY. Returns the file used, or None.

    Uses ``setdefault``, so anything already in the environment wins.
    """
    if os.environ.get("ANTHROPIC_API_KEY"):
        return None

    for path in files or ENV_FILES:
        values = read_env_file(path)
        for key, value in values.items():
            os.environ.setdefault(key, value)
        if values.get("ANTHROPIC_API_KEY"):
            return path
    return None


def strays(files: tuple[Path, ...] | None = None) -> list[Path]:
    """Mis-saved env files sitting next to where a real one should be."""
    found: list[Path] = []
    for path in files or ENV_FILES:
        for name in STRAY_NAMES:
            candidate = path.parent / name
            if candidate.exists():
                found.append(candidate)
    return found


def missing_key_message(files: tuple[Path, ...] | None = None) -> str:
    """What to print when no key turned up. Names every file, and the fix."""
    searched = "\n".join(f"    {path}" for path in (files or ENV_FILES))
    message = (
        "no ANTHROPIC_API_KEY found.\n\n"
        "Looked in the environment, then these files:\n"
        f"{searched}\n\n"
        "Fix, either way:\n"
        '    $env:ANTHROPIC_API_KEY="sk-ant-..."          (this shell only)\n'
        "    Add ANTHROPIC_API_KEY=sk-ant-... to control-evals\\.env   (persists)\n"
    )

    mis_saved = strays(files)
    if mis_saved:
        listed = ", ".join(str(p) for p in mis_saved)
        message += (
            f"\nHeads up: found {listed}. A .env saved as .env.txt is ignored in silence, "
            "and looks exactly like having no key at all.\n"
            "    PowerShell: Rename-Item .env.txt .env\n"
        )
    return message
