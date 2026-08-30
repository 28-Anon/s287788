"""Tests for section segmentation.

The two fixtures below are shaped like the real thing: a US agreement with a table of
contents in front of it, and an English/LMA agreement with completely different numbering.
Both traditions are in the corpus, so both have to work.
"""

import pytest

from covenant_evals.corpus.sections import (
    LEVEL_ARTICLE,
    LEVEL_PARAGRAPH,
    LEVEL_SECTION,
    LEVEL_SUBPARAGRAPH,
    SEGMENTER_VERSION,
    find_spans,
    segment,
    verify_span,
)

US_DOC = """TABLE OF CONTENTS

SECTION 7.01. Indebtedness ......... 44

SECTION 7.02. Liens ......... 45

ARTICLE VII

NEGATIVE COVENANTS

SECTION 7.01. Indebtedness.

The Borrower shall not incur Indebtedness except:

(a) Indebtedness existing on the Closing Date;

(b) Indebtedness in an aggregate principal amount not to exceed the greater of
$35,000,000 and 25% of Consolidated EBITDA, provided that:

(i) no Default has occurred and is continuing; and

(ii) the Leverage Ratio does not exceed 4.00:1.00.

SECTION 7.02. Liens.

The Borrower shall not create any Lien upon any of its property.
"""

LMA_DOC = """23. NEGATIVE COVENANTS

23.1 Financial Indebtedness

(a) The Borrower shall not incur any Financial Indebtedness.

(b) Paragraph (a) above does not apply to:

(i) any Permitted Financial Indebtedness;

(ii) Financial Indebtedness not exceeding GBP 20,000,000.

23.2 Negative Pledge

The Borrower shall not create or permit to subsist any Security.
"""


# -- US style --------------------------------------------------------------------


def test_finds_articles_and_sections():
    result = segment(US_DOC)
    labels = [s.label for s in result if s.level <= LEVEL_SECTION]
    assert labels == ["VII", "7.01", "7.02"]


def test_article_is_the_parent_of_its_sections():
    article = segment(US_DOC).sections[0]
    assert article.level == LEVEL_ARTICLE
    assert [c.label for c in article.children] == ["7.01", "7.02"]


def test_section_title_is_captured():
    assert segment(US_DOC).find("7.02").title == "Liens"


def test_section_text_starts_at_its_heading_and_stops_at_the_next():
    result = segment(US_DOC)
    section = result.find("7.01")
    text = section.text(US_DOC)

    assert text.startswith("SECTION 7.01.")
    assert "Closing Date" in text
    assert "shall not create any Lien" not in text, "7.01 must not run into 7.02"


def test_body_excludes_the_heading():
    body = segment(US_DOC).find("7.02").body(US_DOC)
    assert "SECTION 7.02" not in body
    assert "shall not create any Lien" in body


def test_offsets_point_where_they_claim_to():
    result = segment(US_DOC)
    section = result.find("7.02")
    assert US_DOC[section.start : section.end] == section.text(US_DOC)
    assert US_DOC[section.start :].startswith("SECTION 7.02")


# -- the table of contents problem -----------------------------------------------


def test_contents_entries_are_dropped():
    result = segment(US_DOC)
    assert result.toc_entries_dropped == 2

    # The surviving 7.01 must be the covenant, not the line in the contents list.
    section = result.find("7.01")
    assert "shall not incur Indebtedness" in section.text(US_DOC)
    assert "....." not in section.text(US_DOC)


def test_a_document_with_no_contents_list_loses_nothing():
    assert segment(LMA_DOC).toc_entries_dropped == 0


# -- paragraph nesting, and the (i) problem --------------------------------------


def test_lettered_paragraphs_hang_off_their_section():
    section = segment(US_DOC).find("7.01")
    assert [c.label for c in section.children] == ["(a)", "(b)"]


def test_roman_sub_paragraphs_nest_under_the_paragraph_that_opened_them():
    paragraph = segment(US_DOC).find("7.01(b)")
    assert [c.label for c in paragraph.children] == ["(i)", "(ii)"]
    assert paragraph.children[0].level == LEVEL_SUBPARAGRAPH


def test_i_after_h_is_a_letter_not_a_roman_numeral():
    doc = "SECTION 5.01. Test.\n\n(g) seven;\n\n(h) eight;\n\n(i) nine;\n\n(j) ten.\n"
    section = segment(doc).find("5.01")
    assert [c.label for c in section.children] == ["(g)", "(h)", "(i)", "(j)"]
    assert all(c.level == LEVEL_PARAGRAPH for c in section.children)


def test_i_not_after_h_opens_a_roman_sub_list():
    doc = "SECTION 5.01. Test.\n\n(a) one, provided that:\n\n(i) first;\n\n(ii) second.\n"
    paragraph = segment(doc).find("5.01(a)")
    assert [c.label for c in paragraph.children] == ["(i)", "(ii)"]


def test_uppercase_letters_nest_below_roman_numerals():
    doc = "SECTION 5.01. Test.\n\n(a) one:\n\n(i) first:\n\n(A) alpha;\n\n(B) beta.\n"
    roman = segment(doc).find("5.01(a)(i)")
    assert [c.label for c in roman.children] == ["(A)", "(B)"]


# -- English / LMA style ---------------------------------------------------------


def test_lma_clause_numbering_is_understood():
    result = segment(LMA_DOC)
    assert [s.label for s in result if s.level <= LEVEL_SECTION] == ["23", "23.1", "23.2"]


def test_lma_clause_is_the_parent_of_its_sub_clauses():
    clause = segment(LMA_DOC).sections[0]
    assert clause.title == "NEGATIVE COVENANTS"
    assert [c.label for c in clause.children] == ["23.1", "23.2"]


def test_lma_paragraphs_resolve_by_address():
    paragraph = segment(LMA_DOC).find("23.1(b)")
    assert paragraph is not None
    assert "does not apply to" in paragraph.text(LMA_DOC)
    assert [c.label for c in paragraph.children] == ["(i)", "(ii)"]


# -- addressing ------------------------------------------------------------------


@pytest.mark.parametrize(
    "address,expected",
    [
        ("7.02", "7.02"),
        ("§7.02", "7.02"),
        ("  7.02  ", "7.02"),
        ("7.01(b)", "(b)"),
        ("7.01(b)(ii)", "(ii)"),
    ],
)
def test_addresses_resolve(address, expected):
    assert segment(US_DOC).find(address).label == expected


@pytest.mark.parametrize("address", ["9.99", "7.01(z)", "7.01(b)(ix)", "", "nonsense"])
def test_unknown_addresses_return_none_rather_than_guessing(address):
    assert segment(US_DOC).find(address) is None


def test_a_bare_paragraph_is_not_an_address():
    # "(b)" on its own is ambiguous across the document, so it must not resolve.
    assert segment(US_DOC).find("(b)") is None


# -- cross-references must not be mistaken for headings --------------------------


def test_a_reference_mid_sentence_is_not_a_heading():
    doc = (
        "SECTION 7.01. Indebtedness.\n\n"
        "Except as permitted by Section 7.02 and subject to Article VII, the Borrower "
        "shall not incur Indebtedness.\n"
    )
    result = segment(doc)
    assert [s.label for s in result if s.level <= LEVEL_SECTION] == ["7.01"]


def test_a_long_line_starting_with_a_number_is_not_a_heading():
    long_line = (
        "7.02 is referenced throughout this Agreement and in each case shall be read as "
        "though it were set out in full at this point, which makes this line far too long "
        "to be a heading by any reasonable measure whatsoever.\n"
    )
    assert segment("SECTION 5.01. Test.\n\n" + long_line).find("7.02") is None


# -- diagnostics -----------------------------------------------------------------


def test_a_document_with_no_headings_warns_loudly():
    result = segment("This document has no headings at all, just prose.\n" * 20)
    assert result.sections == ()
    assert any("no sections found" in w for w in result.warnings)


def test_too_few_sections_warns():
    result = segment(US_DOC)
    assert any("only 3 sections" in w for w in result.warnings)


def test_a_giant_section_warns_that_headings_are_being_missed():
    doc = "SECTION 1.01. Definitions.\n\n" + ("filler text that goes on and on. " * 2000)
    assert any("headings are probably being missed" in w for w in segment(doc).warnings)


def test_segmenter_version_is_recorded():
    # If this fails you changed the rules. Bump SEGMENTER_VERSION: section boundaries can
    # move even though character offsets do not, so "7.02(b)" may now resolve elsewhere.
    assert SEGMENTER_VERSION == 1


# -- locating a quote, which is what labelling actually needs --------------------


def test_find_spans_returns_the_offsets_of_a_quote():
    quote = "shall not create any Lien"
    spans = find_spans(US_DOC, quote)
    assert len(spans) == 1
    start, end = spans[0]
    assert US_DOC[start:end] == quote


def test_find_spans_tolerates_the_line_break_you_copied_over():
    quote = "not to exceed the greater of $35,000,000"
    spans = find_spans(US_DOC, quote)
    assert len(spans) == 1
    assert "\n" in US_DOC[spans[0][0] : spans[0][1]], "the match should span the line break"


def test_an_ambiguous_quote_returns_every_match():
    doc = "the Borrower shall not\n\nand again the Borrower shall not\n"
    assert len(find_spans(doc, "the Borrower shall not")) == 2


def test_a_quote_that_is_not_there_returns_nothing():
    assert find_spans(US_DOC, "the Borrower may do whatever it likes") == []


def test_verify_span_accepts_a_correct_citation():
    spans = find_spans(US_DOC, "shall not create any Lien")
    assert verify_span(US_DOC, spans[0], "shall not create any Lien")


def test_verify_span_ignores_whitespace_differences_only():
    spans = find_spans(US_DOC, "not to exceed the greater of $35,000,000")
    assert verify_span(US_DOC, spans[0], "not to exceed the greater  of $35,000,000")


def test_verify_span_rejects_a_span_that_does_not_contain_the_quote():
    assert not verify_span(US_DOC, (0, 20), "shall not create any Lien")


@pytest.mark.parametrize("span", [(-1, 10), (10, 5), (0, 10**6), (5, 5)])
def test_verify_span_rejects_nonsense_offsets(span):
    assert not verify_span(US_DOC, span, "anything")


# -- regressions found by running the CLI on a realistic document ----------------
#
# Both of these passed the unit tests above and still corrupted a real document. They are
# the reason `corpus sections --check` exists.


def test_a_financial_ratio_on_its_own_line_is_not_a_section():
    # "does not exceed\n4.00 to 1.00;" — line wrapping puts a decimal at the start of a
    # line, where it looks exactly like an LMA clause number. It swallowed the rest of the
    # section as its children.
    doc = (
        "SECTION 7.01. Indebtedness.\n\n"
        "(b) provided that the Consolidated Leverage Ratio does not exceed\n"
        "4.00 to 1.00;\n\n"
        "(c) Indebtedness owing to the Borrower.\n"
    )
    result = segment(doc)
    assert result.find("4.00") is None
    assert [c.label for c in result.find("7.01").children] == ["(b)", "(c)"]


def test_a_wrapped_cross_reference_is_not_a_heading():
    # "...except as permitted by\nSection 7.03(b) and subject to Article VII." The second
    # line begins with "Section 7.03(", which parsed as the heading for 7.03 — so every
    # item citing 7.03 pointed at a sentence in 7.01 instead.
    doc = (
        "SECTION 7.01. Indebtedness.\n\n"
        "The Borrower shall not incur Indebtedness except as permitted by\n"
        "Section 7.03(b) and subject to Article VII.\n\n"
        "SECTION 7.03. Restricted Payments.\n\n"
        "The Borrower shall not declare any Restricted Payment.\n"
    )
    result = segment(doc)
    section = result.find("7.03")
    assert section.title == "Restricted Payments"
    assert "shall not declare any Restricted Payment" in section.text(doc)


def test_a_parenthetical_aside_is_not_a_paragraph():
    doc = "SECTION 7.01. Test.\n\n(a) any Permitted Lien\n(as defined below) securing debt.\n"
    section = segment(doc).find("7.01")
    assert [c.label for c in section.children] == ["(a)"]


def test_relaxed_mode_is_used_only_when_strict_finds_nothing_and_says_so():
    # A document whose markup produced no blank lines at all.
    doc = (
        "SECTION 7.01. Indebtedness.\nThe Borrower shall not incur Indebtedness.\n"
        "SECTION 7.02. Liens.\nThe Borrower shall not create Liens.\n"
        "SECTION 7.03. Restricted Payments.\nThe Borrower shall not pay dividends.\n"
        "SECTION 7.04. Investments.\nThe Borrower shall not invest.\n"
    )
    strict = segment(doc, require_blank_line=True)
    auto = segment(doc)

    assert len([s for s in strict if s.level <= LEVEL_SECTION]) == 1, "strict finds only the first"
    assert len([s for s in auto if s.level <= LEVEL_SECTION]) == 4, "auto falls back and finds all"
    assert any("relaxed rules were used" in w for w in auto.warnings)


def test_a_short_but_well_formed_document_does_not_trigger_the_fallback():
    # Three real sections is a short document, not a failed parse. Falling back here would
    # trade correct output for false positives.
    assert not any("relaxed rules" in w for w in segment(US_DOC).warnings)
