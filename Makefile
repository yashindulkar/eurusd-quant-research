PYTHON_BOOTSTRAP ?= python3.12
VENV ?= .venv
PYTHON := $(VENV)/bin/python

.PHONY: setup validate-environment format lint typecheck test test-unit test-integration coverage check register-data audit-raw-data generate-coverage prepare-task04-v211-integrity prepare-task04-v211-registration validate-task04-v211-schemas create-task04-registration-receipt validate-task04-registration-receipt validate-task04-preregistration generate-task04-candidate reconcile-task04-v211

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

generate-coverage:
	$(PYTHON) -m eurusd_research.research

prepare-task04-v211-integrity:
	$(PYTHON) scripts/prepare_task04_v211_integrity_evidence.py

prepare-task04-v211-registration:
	$(PYTHON) scripts/prepare_task04_v211_registration.py

validate-task04-v211-schemas:
	$(PYTHON) scripts/validate_task04_v211_schemas.py

create-task04-registration-receipt:
	$(PYTHON) scripts/create_task04_registration_receipt.py

validate-task04-registration-receipt:
	$(PYTHON) scripts/validate_task04_registration_receipt.py

validate-task04-preregistration:
	$(PYTHON) scripts/validate_task04_preregistration.py

generate-task04-candidate:
	$(PYTHON) -m eurusd_research.studies

reconcile-task04-v211:
	$(PYTHON) scripts/reconcile_task04_v211.py
