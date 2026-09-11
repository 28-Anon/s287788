.PHONY: test lint validate budget corpus-search corpus-add corpus-fetch corpus-status corpus-sections corpus-section corpus-locate corpus-check corpus-doctor items-check items-stats splits-freeze splits-check splits-status all

test:
	pytest -q

lint:
	ruff check src tests
	ruff format --check src tests

validate:
	python -m covenant_evals.cli items check --schema-only

# Full check: schema, plus every item against the document it cites. Needs the corpus
# on disk, so this is the one to run before committing labels.
items-check:
	python -m covenant_evals.cli items check

items-stats:
	python -m covenant_evals.cli items stats

# Cut the dev/test/heldout split. Once. Commit data/splits.json immediately after.
splits-freeze:
	python -m covenant_evals.cli splits freeze

splits-check:
	python -m covenant_evals.cli splits check

# Composition of each split, and whether heldout has ever been opened.
splits-status:
	python -m covenant_evals.cli splits status

budget:
	python -m covenant_evals.cli budget

corpus-search:
	python -m covenant_evals.cli corpus search --query $(Q) $(if $(FORMS),--forms $(FORMS),)

corpus-add:
	python -m covenant_evals.cli corpus add $(REF) --cik $(CIK) \
		$(if $(LAW),--governing-law $(LAW),) $(if $(NOTE),--note "$(NOTE)",)

corpus-fetch:
	python -m covenant_evals.cli corpus fetch

corpus-status:
	python -m covenant_evals.cli corpus status

# Prove the EDGAR pipeline works against the live SEC. Run this FIRST, before adding
# any document: every endpoint shape in edgar.py came from documentation, not from a
# live response. PASTE=1 adds a structure-only block that is safe to share.
corpus-doctor:
	python -m covenant_evals.cli corpus doctor $(if $(PASTE),--paste,)

# REF is any unique part of an accession:filename, e.g. REF=0000950170-24-012345
corpus-sections:
	python -m covenant_evals.cli corpus sections $(REF) $(if $(OFFSETS),--offsets,)

# ADDR is a section address, e.g. ADDR='7.02(b)'
corpus-section:
	python -m covenant_evals.cli corpus section $(REF) $(ADDR)

# Q is the text you want to cite. Prints a gold_span line ready to paste into an item.
corpus-locate:
	python -m covenant_evals.cli corpus locate $(REF) $(Q)

# Segment every fetched document and report anything suspicious. Run after ANY change
# to the segmenter: a rule that fixes one document and breaks three is the normal outcome.
corpus-check:
	python -m covenant_evals.cli corpus sections --check

all: lint test validate
