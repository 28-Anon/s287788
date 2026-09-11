"""A browsable HTML view of the corpus, written to a local file.

Twenty-five documents, each with a section tree and possibly a segmentation warning, is not
something to read down a terminal. This writes one self-contained page you open in a
browser: what is in the corpus, how each document segmented, what needs attention, and a
link to each filing on EDGAR.

It is generated from local data and never leaves your machine.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime
from pathlib import Path

from .fetch import load_text
from .manifest import DEFAULT_CACHE, Manifest
from .sections import LEVEL_SECTION, explain_no_sections, pattern_census, segment

_CSS = """
:root { --ink:#16191d; --muted:#5d6b66; --rule:#dfe5e2; --paper:#f7f9f8; --card:#fff;
        --good:#1f5e52; --warn:#8a6a1f; --bad:#a0402a; }
@media (prefers-color-scheme: dark) {
  :root { --ink:#eef2f0; --muted:#93a09b; --rule:#2b3330; --paper:#121614; --card:#191e1c;
          --good:#6fc0ac; --warn:#d5ac5c; --bad:#e08e76; }
}
* { box-sizing:border-box }
body { margin:0; background:var(--paper); color:var(--ink); font:15px/1.55 system-ui,
       -apple-system, "Segoe UI", sans-serif; }
.wrap { max-width:1100px; margin:0 auto; padding:32px 24px 80px }
h1 { font-size:26px; margin:0 0 4px; letter-spacing:-.02em }
.sub { color:var(--muted); margin:0 0 28px; font-size:13px }
.tiles { display:grid; grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); gap:1px;
         background:var(--rule); border:1px solid var(--rule); margin-bottom:32px }
.tile { background:var(--card); padding:14px 16px }
.tile b { display:block; font-size:24px; letter-spacing:-.02em }
.tile span { color:var(--muted); font-size:12px }
.doc { background:var(--card); border:1px solid var(--rule); margin-bottom:14px; padding:16px 18px }
.doc h2 { font-size:15px; margin:0 0 2px; font-weight:600 }
.meta { color:var(--muted); font-size:12.5px; margin-bottom:8px }
.meta a { color:inherit }
.pill { display:inline-block; font-size:11px; padding:1px 7px; border:1px solid currentColor;
        margin-right:6px; vertical-align:1px }
.ok { color:var(--good) } .warn { color:var(--warn) } .bad { color:var(--bad) }
.note { font-size:13px; color:var(--muted); margin:6px 0 0 }
.secs { margin-top:10px; font:12.5px ui-monospace,Menlo,Consolas,monospace; color:var(--muted);
        max-height:150px; overflow:auto; border-top:1px solid var(--rule); padding-top:8px }
.secs span { display:inline-block; margin:0 10px 3px 0 }
.msg { font-size:13px; margin-top:8px; padding:8px 10px; border-left:2px solid currentColor }
"""


def _tile(value: object, label: str) -> str:
    return (
        f'<div class="tile"><b>{html.escape(str(value))}</b><span>{html.escape(label)}</span></div>'
    )


def build(manifest: Manifest, *, cache_dir: Path = DEFAULT_CACHE) -> str:
    """Render the whole corpus as one HTML page."""
    agreements = sorted(manifest.agreements, key=lambda a: a.ref)
    fetched = [a for a in agreements if a.is_fetched]
    provisional = [a for a in agreements if "PROVISIONAL" in a.note]
    english = [a for a in agreements if a.governing_law == "English"]

    body: list[str] = []
    unreadable = 0

    for agreement in agreements:
        pills: list[str] = []
        detail = ""

        if not agreement.is_fetched:
            pills.append('<span class="pill warn">not fetched</span>')
        else:
            try:
                text = load_text(agreement, cache_dir=cache_dir)
            except FileNotFoundError:
                text = ""

            if text:
                result = segment(text)
                top = [s for s in result if s.level <= LEVEL_SECTION]
                if top:
                    pills.append(f'<span class="pill ok">{len(top)} sections</span>')
                    labels = "".join(
                        f"<span>{html.escape(s.label)}"
                        f"{' ' + html.escape(s.title[:40]) if s.title else ''}</span>"
                        for s in top[:60]
                    )
                    detail += f'<div class="secs">{labels}</div>'
                else:
                    unreadable += 1
                    pills.append('<span class="pill bad">no sections</span>')
                    diagnosis = explain_no_sections(pattern_census(text))
                    detail += f'<p class="msg bad">{html.escape(diagnosis)}</p>'

                for warning in result.warnings[:2]:
                    detail += f'<p class="msg warn">{html.escape(warning)}</p>'

        law = agreement.governing_law or "law unchecked"
        law_class = "ok" if agreement.governing_law else "warn"
        pills.append(f'<span class="pill {law_class}">{html.escape(law)}</span>')
        if agreement.split:
            pills.append(f'<span class="pill">{html.escape(agreement.split)}</span>')
        if "PROVISIONAL" in agreement.note:
            pills.append('<span class="pill warn">not reviewed</span>')

        body.append(
            '<div class="doc">'
            f"<h2>{html.escape(agreement.company or agreement.ref)}</h2>"
            f'<p class="meta">{html.escape(agreement.ref)} &middot; {html.escape(agreement.form)}'
            f" &middot; filed {html.escape(agreement.filed)}"
            f" &middot; {agreement.char_count:,} chars &middot; "
            f'<a href="{html.escape(agreement.url())}">read on EDGAR</a></p>'
            f"<p>{''.join(pills)}</p>"
            f'<p class="note">{html.escape(agreement.note)}</p>'
            f"{detail}</div>"
        )

    tiles = "".join(
        [
            _tile(len(agreements), "documents"),
            _tile(len(fetched), "fetched"),
            _tile(len(english), "English law"),
            _tile(len(provisional), "not reviewed"),
            _tile(unreadable, "no sections"),
            _tile(f"{sum(a.char_count for a in fetched) // 1000:,}k", "characters"),
        ]
    )

    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "<!doctype html><html lang=en><meta charset=utf-8>"
        '<meta name=viewport content="width=device-width,initial-scale=1">'
        "<title>covenant-evals corpus</title>"
        f"<style>{_CSS}</style>"
        '<div class="wrap"><h1>Corpus</h1>'
        f'<p class="sub">generated {generated} &middot; local file, nothing left this machine</p>'
        f'<div class="tiles">{tiles}</div>'
        f"{''.join(body) if body else '<p>Nothing in the manifest yet.</p>'}"
        "</div></html>"
    )


def write(manifest: Manifest, path: Path, *, cache_dir: Path = DEFAULT_CACHE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build(manifest, cache_dir=cache_dir), encoding="utf-8")
    return path
