PYTHON_BOOTSTRAP ?= python3.12
VENV ?= .venv
PYTHON := $(VENV)/bin/python

.PHONY: setup validate-environment format lint typecheck test test-unit test-integration coverage check register-data audit-raw-data

setup:
	$(PYTHON_BOOTSTRAP) -m venv $(VENV)
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e ".[dev]"

validate-environment:
	$(PYTHON) scripts/validate_environment.py

format:
	$(PYTHON) -m ruff format src scripts tests
	$(PYTHON) -m ruff check --fix src scripts tests

lint:
	$(PYTHON) -m ruff check src scripts tests
	$(PYTHON) -m ruff format --check src scripts tests

typecheck:
	$(PYTHON) -m mypy

test-unit:
	$(PYTHON) -m pytest tests/unit

test-integration:
	$(PYTHON) -m pytest tests/integration

coverage:
	$(PYTHON) -m pytest --cov=eurusd_research --cov-report=term-missing --cov-report=xml

test: coverage

check: lint typecheck test validate-environment

register-data:
	$(PYTHON) scripts/register_raw_dataset.py

audit-raw-data:
	$(PYTHON) -m eurusd_research.data
