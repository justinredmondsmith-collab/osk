PYTHON ?= python

.PHONY: install-dev install-all lint format-check test build check

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"

install-all:
	$(PYTHON) -m pip install -e ".[dev,intelligence]"

lint:
	ruff check .
	ruff format --check .

format-check: lint

test:
	pytest -q

build:
	$(PYTHON) -m build

check: lint test build
