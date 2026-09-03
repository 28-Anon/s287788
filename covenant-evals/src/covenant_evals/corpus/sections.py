"""Finding sections inside a credit agreement.

Every item you label cites a section — "no section, no item" — so the code has to be able
to turn "7.02(b)" into a place in the text and back again. That is all this module does.

It is heuristic, and it says so loudly. There is no schema for a credit agreement: the
numbering comes from whichever law firm drafted it, and the two big traditions do not even
agree on the shape of a heading:

    US style                        English / LMA style
    ------------------------------  --------------------------------
    ARTICLE VII                     23. NEGATIVE COVENANTS
    SECTION 7.02. Liens.            23.1 Financial Indebtedness
        (a) ...                         (a) ...
            (i) ...                         (i) ...

Both are supported, because the corpus deliberately contains both. Where the heuristics
are uncertain they emit a warning rather than guessing quietly — `corpus sections --check`
exists so you find out on 25 documents at once, not on item 180.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: Bump when the rules below change. Section *boundaries* can move even though character
#: offsets do not, so an item that cites "7.02(b)" may resolve somewhere new. The manifest
#: records the version each document was segmented with, and `corpus status` flags drift.
SEGMENTER_VERSION = 1

LEVEL_ARTICLE = 0
LEVEL_SECTION = 1
LEVEL_PARAGRAPH = 2  # (a) (b) (c)
LEVEL_SUBPARAGRAPH = 3  # (i) (ii) (iii)
LEVEL_CLAUSE = 4  # (A) (B) (C)

# ---------------------------------------------------------------------------
# Heading patterns. Anchored to line starts: a cross-reference in the middle of a
# sentence ("as provided in Section 7.02") must never be mistaken for a heading.
# ---------------------------------------------------------------------------

_ARTICLE = re.compile(r"^ARTICLE\s+([IVXLCDM]+|\d{1,2})\b[.:]?\s*(.*)$", re.IGNORECASE)

#: "23. NEGATIVE COVENANTS" — LMA top-level clause. Requires a shouted title, which is
#: what keeps it from matching an ordinary numbered list item.
_LMA_CLAUSE = re.compile(r"^(\d{1,2})\.\s+([A-Z][A-Z0-9 ,&'()/\-]{3,80})$")

#: "SECTION 7.02. Liens." — US style, with or without the word SECTION.
#: The lookahead is load-bearing. Without it, a line-wrapped cross-reference —
#: "...except as permitted by\nSection 7.03(b) and subject to Article VII" — parses as the
#: heading for 7.03, and every item citing 7.03 then points at the wrong text.
_US_SECTION = re.compile(
    r"^SECTION\s+(\d{1,2}\.\d{1,3}[A-Za-z]?)(?=[\s.:\-–—]|$)\s*[.:\-–—]?\s*(.*)$",
    re.IGNORECASE,
)

#: "7.02 Liens" / "23.1 Financial Indebtedness" — bare decimal. The length cap is doing
#: the work: a real heading is short, a sentence that happens to start with a number is not.
#: The title must start with a capital and must not read as a sentence fragment. Without
#: that, "does not exceed\n4.00 to 1.00;" parses as section 4.00 — a financial ratio
#: wrapped onto its own line looks exactly like a decimal heading.
_DECIMAL = re.compile(r"^(\d{1,2}\.\d{1,3})\s+([A-Z][^;,]{0,110})$")

#: A single letter or a roman numeral, nothing else. "(as defined below)" at the start of
#: a wrapped line would otherwise parse as paragraph "(as)".
_PARENTHESISED = re.compile(r"^\(([A-Za-z]|[ivxlcdm]{2,5}|[IVXLCDM]{2,5})\)\s*(.*)$")

_ROMAN = re.compile(r"^[ivxlcdm]+$")

#: A page number trailing a heading is the giveaway for a table of contents entry:
#: "SECTION 7.02. Liens ......... 45"
_TOC_TAIL = re.compile(r"(?:\.{2,}|\s)\s*\d{1,4}\s*$")

#: Ambiguous single letters: (i) is roman one, but also follows (h). Same for v and x.
_AMBIGUOUS_AFTER = {"i": "h", "v": "u", "x": "w"}


@dataclass(frozen=True)
class Section:
    """One section, with offsets into the normalised text it came from."""

    label: str  # "7.02", "23.1", "(b)"
    title: str  # "Liens" — often empty
    level: int
    start: int  # first character of the heading
    body_start: int  # first character after the heading line
    end: int  # exclusive; runs to the next heading at this level or above
    children: tuple[Section, ...] = ()

    @property
    def span(self) -> tuple[int, int]:
        return (self.start, self.end)

    @property
    def char_count(self) -> int:
        return self.end - self.start

    def text(self, document: str) -> str:
        """The section including its heading."""
        return document[self.start : self.end]

    def body(self, document: str) -> str:
        """The section without its heading."""
        return document[self.body_start : self.end]

    def walk(self):
        """This section and every descendant, depth first."""
        yield self
        for child in self.children:
            yield from child.walk()

    def path(self) -> str:
        """The address you would write in an item file, e.g. "7.02(b)"."""
        return self.label


@dataclass
class Segmentation:
    """The result of segmenting one document."""

    sections: tuple[Section, ...] = ()
    warnings: list[str] = field(default_factory=list)
    toc_entries_dropped: int = 0

    def __iter__(self):
        for section in self.sections:
            yield from section.walk()

    @property
    def count(self) -> int:
        return sum(1 for _ in self)

    def find(self, address: str) -> Section | None:
        """Resolve an address like "7.02(b)" or "23.1(a)(ii)".

        Splits on the parentheses and walks down, so a paragraph is only ever found inside
        the section that owns it — "(b)" alone is not an address, deliberately.
        """
        parts = _split_address(address)
        if not parts:
            return None

        candidates: tuple[Section, ...] = self.sections
        found: Section | None = None

        for part in parts:
            found = next((s for s in _flatten(candidates) if s.label == part), None)
            if found is None:
                return None
            candidates = found.children

        return found


def _flatten(sections: tuple[Section, ...]) -> list[Section]:
    """Sections at this level, plus articles' children — articles are containers only."""
    out: list[Section] = []
    for section in sections:
        out.append(section)
        if section.level == LEVEL_ARTICLE:
            out.extend(section.children)
    return out


def _split_address(address: str) -> list[str]:
    """ "7.02(b)(ii)" -> ["7.02", "(b)", "(ii)"]"""
    address = address.strip().replace("§", "").strip()
    if not address:
        return []
    head, *rest = re.split(r"(?=\()", address)
    parts = [head.strip()] if head.strip() else []
    parts.extend(part.strip() for part in rest if part.strip())
    return parts


def _paragraph_level(label: str, previous_paragraph_label: str | None) -> int:
    """Decide whether "(i)" means roman one or the letter after "(h)".

    The rule: an ambiguous letter is treated as a continuation of the lettered list only
    if the previous paragraph at that level was the letter immediately before it. So
    (g) (h) (i) is a letter list, while (a) ... (i) (ii) is a roman sub-list.

    Failure mode, stated so it can be checked: a document that ends a lettered list at (h)
    and opens a roman sub-list immediately afterwards will be read wrongly. That is rare
    enough to accept and cheap enough to spot when you read the section.
    """
    if label.isupper():
        return LEVEL_CLAUSE

    lowered = label.lower()

    if len(lowered) > 1:
        return LEVEL_SUBPARAGRAPH if _ROMAN.match(lowered) else LEVEL_PARAGRAPH

    expected_predecessor = _AMBIGUOUS_AFTER.get(lowered)
    if expected_predecessor is not None:
        if previous_paragraph_label == expected_predecessor:
            return LEVEL_PARAGRAPH
        return LEVEL_SUBPARAGRAPH

    return LEVEL_PARAGRAPH


@dataclass
class _RawHeading:
    label: str
    title: str
    level: int
    start: int
    body_start: int
    looks_like_toc: bool


def _scan_headings(document: str, *, require_blank_line: bool = True) -> list[_RawHeading]:
    """Find every line that looks like a heading.

    `require_blank_line` is the single most effective false-positive filter available: a
    real heading is set off from the text around it, whereas a cross-reference or a
    financial ratio that happens to land at the start of a wrapped line is not. It is
    relaxed only as a fallback, for documents whose markup produced no blank lines.
    """
    headings: list[_RawHeading] = []
    previous_paragraph_label: str | None = None
    previous_line_blank = True  # the first line of a document counts as set off
    offset = 0

    for line in document.splitlines(keepends=True):
        stripped = line.strip()
        line_start = offset
        offset += len(line)

        if not stripped:
            previous_line_blank = True
            continue

        set_off = previous_line_blank or not require_blank_line
        previous_line_blank = False

        label: str | None = None
        title = ""
        level = LEVEL_SECTION

        if set_off and (match := _ARTICLE.match(stripped)):
            label, title, level = match.group(1).upper(), match.group(2), LEVEL_ARTICLE
            previous_paragraph_label = None
        elif set_off and (match := _US_SECTION.match(stripped)):
            label, title, level = match.group(1), match.group(2), LEVEL_SECTION
            previous_paragraph_label = None
        elif set_off and (match := _LMA_CLAUSE.match(stripped)):
            label, title, level = match.group(1), match.group(2), LEVEL_ARTICLE
            previous_paragraph_label = None
        elif set_off and (match := _DECIMAL.match(stripped)):
            label, title, level = match.group(1), match.group(2), LEVEL_SECTION
            previous_paragraph_label = None
        elif match := _PARENTHESISED.match(stripped):
            raw_label = match.group(1)
            level = _paragraph_level(raw_label, previous_paragraph_label)
            label, title = f"({raw_label})", ""
            if level == LEVEL_PARAGRAPH:
                previous_paragraph_label = raw_label.lower()

        if label is None:
            continue

        headings.append(
            _RawHeading(
                label=label,
                title=title.strip(" .–—-"),
                level=level,
                start=line_start,
                body_start=line_start + len(line),
                looks_like_toc=bool(_TOC_TAIL.search(stripped)),
            )
        )

    return headings


def _drop_table_of_contents(
    headings: list[_RawHeading],
) -> tuple[list[_RawHeading], int, list[str]]:
    """Remove table-of-contents entries.

    Nearly every credit agreement opens with a contents list that repeats every heading in
    the document. Left in, it produces a phantom copy of the whole structure at the front,
    and "7.02" resolves to a line in the contents rather than the covenant.

    Two signals, and both are needed because either alone is unreliable:

    1. the line ends in what looks like a page number, and
    2. the same label appears again later in the document.

    When a label still appears more than once after that, the last occurrence wins — a
    contents list precedes the body it describes. Documents that genuinely restate a
    section number later (some amendments do) will lose the earlier copy, so this emits a
    warning rather than doing it silently.
    """
    warnings: list[str] = []
    positions: dict[str, list[int]] = {}
    for index, heading in enumerate(headings):
        if heading.level <= LEVEL_SECTION:
            positions.setdefault(heading.label, []).append(index)

    drop: set[int] = set()

    for indices in positions.values():
        if len(indices) < 2:
            continue
        for index in indices[:-1]:
            if headings[index].looks_like_toc:
                drop.add(index)

    toc_dropped = len(drop)

    remaining: dict[str, list[int]] = {}
    for index, heading in enumerate(headings):
        if index in drop or heading.level > LEVEL_SECTION:
            continue
        remaining.setdefault(heading.label, []).append(index)

    duplicate_labels = [label for label, idx in remaining.items() if len(idx) > 1]
    for label in duplicate_labels:
        for index in remaining[label][:-1]:
            drop.add(index)

    if duplicate_labels:
        warnings.append(
            f"{len(duplicate_labels)} label(s) appeared more than once after removing "
            f"contents entries ({', '.join(sorted(duplicate_labels)[:5])}"
            f"{'...' if len(duplicate_labels) > 5 else ''}). Kept the last occurrence of "
            "each — check these by hand before labelling against them."
        )

    return [h for i, h in enumerate(headings) if i not in drop], toc_dropped, warnings


def _build_tree(headings: list[_RawHeading], document_length: int) -> tuple[Section, ...]:
    """Turn a flat list of headings into a tree, computing each section's end offset."""
    ends: list[int] = []
    for index, heading in enumerate(headings):
        end = document_length
        for later in headings[index + 1 :]:
            if later.level <= heading.level:
                end = later.start
                break
        ends.append(end)

    def build(start_index: int, level: int, stop: int) -> tuple[list[Section], int]:
        built: list[Section] = []
        index = start_index

        while index < stop:
            heading = headings[index]
            if heading.level < level:
                break
            if heading.level > level:
                index += 1
                continue

            child_stop = stop
            for lookahead in range(index + 1, stop):
                if headings[lookahead].level <= level:
                    child_stop = lookahead
                    break

            children, _ = build(index + 1, level + 1, child_stop)
            built.append(
                Section(
                    label=heading.label,
                    title=heading.title,
                    level=heading.level,
                    start=heading.start,
                    body_start=heading.body_start,
                    end=ends[index],
                    children=tuple(children),
                )
            )
            index = child_stop

        return built, index

    if not headings:
        return ()

    top_level = min(h.level for h in headings)
    sections, _ = build(0, top_level, len(headings))
    return tuple(sections)


#: Below this many top-level sections, the strict rules are assumed to have failed
#: outright rather than merely found a short document.
_FALLBACK_THRESHOLD = 3


def _segment_once(document: str, *, require_blank_line: bool) -> Segmentation:
    headings = _scan_headings(document, require_blank_line=require_blank_line)
    headings, toc_dropped, warnings = _drop_table_of_contents(headings)
    sections = _build_tree(headings, len(document))
    return Segmentation(sections=sections, warnings=warnings, toc_entries_dropped=toc_dropped)


def _top_level_count(segmentation: Segmentation) -> int:
    return sum(1 for s in segmentation if s.level <= LEVEL_SECTION)


def segment(document: str, *, require_blank_line: bool | None = None) -> Segmentation:
    """Split a normalised credit agreement into a tree of sections.

    By default this runs the strict rules first, and only falls back to relaxed heading
    detection if they found essentially nothing — which happens when a filing's markup used
    <br> rather than <p> and the normaliser produced no blank lines to key off.

    The fallback is announced in the warnings rather than applied quietly: relaxed mode
    trades false negatives for false positives, and you should know which one you are
    looking at before you label against it. Pass require_blank_line explicitly to pin it.
    """
    if require_blank_line is not None:
        result = _segment_once(document, require_blank_line=require_blank_line)
        result.warnings.extend(_diagnose(result, document))
        return result

    strict = _segment_once(document, require_blank_line=True)

    if _top_level_count(strict) < _FALLBACK_THRESHOLD:
        relaxed = _segment_once(document, require_blank_line=False)
        if _top_level_count(relaxed) >= _FALLBACK_THRESHOLD:
            relaxed.warnings.insert(
                0,
                "strict heading detection found almost nothing, so relaxed rules were used. "
                "Relaxed mode admits false positives — cross-references and wrapped lines "
                "can appear as sections. Read this document's tree before labelling it.",
            )
            relaxed.warnings.extend(_diagnose(relaxed, document))
            return relaxed

    strict.warnings.extend(_diagnose(strict, document))
    return strict


def _diagnose(segmentation: Segmentation, document: str) -> list[str]:
    """Signals that segmentation went wrong. Cheap to compute, expensive to skip."""
    warnings: list[str] = []
    top = [s for s in segmentation if s.level <= LEVEL_SECTION]

    if not top:
        warnings.append(
            "no sections found — this document's headings do not match any known style. "
            "Read it and either add a pattern or drop it from the corpus."
        )
        return warnings

    if len(top) < 10:
        warnings.append(
            f"only {len(top)} sections found in {len(document):,} characters. A credit "
            "agreement usually has dozens; headings are probably being missed."
        )

    biggest = max(top, key=lambda s: s.char_count)
    if biggest.char_count > len(document) * 0.25 and len(document) > 20_000:
        warnings.append(
            f"section {biggest.label} spans {biggest.char_count:,} characters "
            f"({biggest.char_count / len(document):.0%} of the document) — headings are "
            "probably being missed inside it."
        )

    numeric = [s for s in top if s.level == LEVEL_SECTION and re.fullmatch(r"\d+\.\d+", s.label)]
    out_of_order = sum(
        1
        for earlier, later in zip(numeric, numeric[1:], strict=False)
        if _as_tuple(later.label) < _as_tuple(earlier.label)
    )
    if out_of_order > len(numeric) * 0.1 and out_of_order > 2:
        warnings.append(
            f"{out_of_order} section numbers go backwards. Either the contents list was "
            "not fully removed, or this document restates sections."
        )

    return warnings


def _as_tuple(label: str) -> tuple[int, ...]:
    return tuple(int(part) for part in label.split(".") if part.isdigit())


# ---------------------------------------------------------------------------
# Locating a quote — what you will actually use while labelling
# ---------------------------------------------------------------------------


def find_spans(document: str, quote: str, *, limit: int = 10) -> list[tuple[int, int]]:
    """Every place a quote appears, as character spans.

    Whitespace-tolerant: a quote copied out of the text file spans line breaks, and the
    line breaks will not match. Everything else must match exactly — straightening a quote
    mark here would let a citation pass that does not actually appear in the document.

    Returns a list because **a quote appearing more than once is a labelling hazard**. If
    your citation is ambiguous, the span you record may not be the one you meant. Quote
    more context until there is exactly one match.
    """
    tokens = [re.escape(token) for token in quote.split()]
    if not tokens:
        return []

    pattern = re.compile(r"\s+".join(tokens))
    return [(m.start(), m.end()) for m in list(pattern.finditer(document))[:limit]]


def verify_span(document: str, span: tuple[int, int], quote: str) -> bool:
    """Does this span actually contain this quote, ignoring whitespace differences?

    This is the check that makes grounded accuracy mean something: a citation is only
    verified if the text is really there, at the offsets recorded.
    """
    start, end = span
    if not (0 <= start < end <= len(document)):
        return False
    return " ".join(document[start:end].split()) == " ".join(quote.split())


# ---------------------------------------------------------------------------
# Diagnosing a document the segmenter cannot read
# ---------------------------------------------------------------------------


def pattern_census(document: str) -> dict[str, object]:
    """Count how many lines match each heading pattern, and how many are set off.

    This is the diagnostic for "the segmenter found nothing", and it separates the two
    causes that look identical from the outside:

    - `matched` high but `set_off` near zero -> the document has no blank lines, so the
      strict rule rejects every real heading. A normalisation problem.
    - `matched` zero                         -> the headings do not look like any known
      style. A pattern problem, and the samples show what to add.

    Filings are public documents, so the samples are shareable — but they are truncated
    regardless, because a diagnostic should carry the shape of the text and not its
    substance.
    """
    patterns = {
        "article": _ARTICLE,
        "us_section": _US_SECTION,
        "lma_clause": _LMA_CLAUSE,
        "decimal": _DECIMAL,
        "parenthesised": _PARENTHESISED,
    }

    counts = {name: {"matched": 0, "set_off": 0} for name in patterns}
    samples: dict[str, list[str]] = {name: [] for name in patterns}

    lines = document.splitlines()
    blank = 0
    previous_blank = True

    for line in lines:
        stripped = line.strip()
        if not stripped:
            blank += 1
            previous_blank = True
            continue

        for name, pattern in patterns.items():
            if pattern.match(stripped):
                counts[name]["matched"] += 1
                if previous_blank:
                    counts[name]["set_off"] += 1
                if len(samples[name]) < 3:
                    samples[name].append(stripped[:90])
                break

        previous_blank = False

    non_blank = len(lines) - blank
    return {
        "lines": len(lines),
        "blank_lines": blank,
        "blank_line_ratio": round(blank / len(lines), 3) if lines else 0.0,
        "mean_line_length": round(len(document) / non_blank, 1) if non_blank else 0.0,
        "counts": counts,
        "samples": samples,
        "first_lines": [ln.strip()[:90] for ln in lines[:20] if ln.strip()][:8],
    }
