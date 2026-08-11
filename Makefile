PYTHON ?= python

.PHONY: install format lint test build audit demo run benchmark robustness artifacts check

install:
	$(PYTHON) -m pip install -e ".[dev]"

format:
	$(PYTHON) -m ruff format .

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m mypy -p fraud_engine

test:
	$(PYTHON) -m pytest --cov=fraud_engine --cov-report=term-missing --cov-fail-under=80

build:
	$(PYTHON) -m build

audit:
	$(PYTHON) -m pip_audit

demo:
	$(PYTHON) -m fraud_engine.demo

run:
	$(PYTHON) -m uvicorn fraud_engine.api:app --host 0.0.0.0 --port 8000

benchmark:
	$(PYTHON) -m fraud_engine.benchmark

robustness:
	$(PYTHON) -m fraud_engine.robustness

artifacts:
	$(PYTHON) -m fraud_engine.artifacts

compare:
	$(PYTHON) -m fraud_engine.compare benchmarks/results/reference/summary.json benchmarks/results/optimized/summary.json

check: lint test build
