.PHONY: test lint validate budget corpus-search corpus-add corpus-fetch corpus-status all

test:
	pytest -q

lint:
	ruff check src tests
	ruff format --check src tests

validate:
	python -m covenant_evals.cli validate

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

all: lint test validate
