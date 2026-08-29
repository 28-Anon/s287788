.PHONY: test lint validate budget all

test:
	pytest -q

lint:
	ruff check src tests
	ruff format --check src tests

validate:
	python -m covenant_evals.cli validate

budget:
	python -m covenant_evals.cli budget

all: lint test validate
