PYTHON ?= python

.PHONY: install run-mock compute-index train score serve lint test ingest-ais aggregate-dwell backup-db restore-db

install:
	$(PYTHON) -m pip install -e .

run-mock:
	$(PYTHON) -m spvx.cli ingest --mode mock

# AIS Stream ingestion (runs continuously)
ingest-ais:
	$(PYTHON) ingest_aisstream.py

# Aggregate AIS raw data into dwell statistics
aggregate-dwell:
	$(PYTHON) aggregate_dwell.py

backup-db:
	bin/backup_duckdb.sh

restore-db:
	bin/restore_duckdb.sh

compute-index:
	$(PYTHON) -m spvx.cli compute-index

train:
	$(PYTHON) -m spvx.cli train

score:
	$(PYTHON) -m spvx.cli score

serve:
	$(PYTHON) -m spvx.cli serve

lint:
	$(PYTHON) -m ruff check src tests
	$(PYTHON) -m black --check src tests
	$(PYTHON) -m isort --check-only src tests

format:
	$(PYTHON) -m black src tests
	$(PYTHON) -m isort src tests
	$(PYTHON) -m ruff check --fix src tests

test:
	$(PYTHON) -m pytest tests

test-cov:
	$(PYTHON) -m pytest tests --cov=src --cov-report=term-missing --cov-report=html

test-integration:
	$(PYTHON) -m pytest tests -m integration

type-check:
	$(PYTHON) -m mypy src --ignore-missing-imports

security:
	$(PYTHON) -m bandit -r src -f json || true
	$(PYTHON) -m safety check --json || true

ci-check: lint type-check test security
	@echo "✓ All CI checks passed"

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .coverage htmlcov .mypy_cache .ruff_cache
