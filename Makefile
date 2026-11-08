.PHONY: install lint format typecheck test check run-backend run-frontend

PYTHON ?= python

install:
	$(PYTHON) -m pip install -e ".[backend,frontend,dev]"

lint:
	$(PYTHON) -m ruff check .
	$(PYTHON) -m black --check .

format:
	$(PYTHON) -m ruff check --fix .
	$(PYTHON) -m black .

typecheck:
	$(PYTHON) -m mypy

test:
	$(PYTHON) -m pytest

check: lint typecheck test

run-backend:
	$(PYTHON) -m uvicorn finance_poc.main:app --reload --host 127.0.0.1 --port 8000

run-frontend:
	$(PYTHON) -m streamlit run frontend/app.py --server.port 8501 --server.address 127.0.0.1
