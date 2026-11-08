# Finance data POC

Modular financial data platform. A FastAPI service collects prices, quotes, news, filings, and company data from several providers and exposes one normalized API. A Streamlit UI reads that API over HTTP.

Phase 1 builds the data platform. Grok is the configured LLM (`grok-4.7` on the xAI API). Sentiment, retrieval over filings, and the research agent attach later beside the market-data service.

## Providers

| Capability | Order |
| --- | --- |
| Prices | yfinance, then Twelve Data |
| Quotes | Finnhub, then yfinance |
| News | Finnhub |
| Company profile | yfinance, then Finnhub |
| Filings and financial statements | SEC EDGAR submissions and company facts |

## Layout

Application code lives in `backend/src/finance_poc`. The Streamlit app lives in `frontend/` and does not import the backend package. Tests live in `tests/`. Profile templates live in `config/`.

## Setup

From `finance-ai-poc`, with Python 3.11 or newer:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
copy .env.example .env
python -m pip install -e ".[backend,frontend,dev]"
```

`make install` runs that same install once `python` points at the virtualenv. Copy `config/test.env.example` or `config/prod.env.example` instead when you want those profiles. Real keys stay in the untracked `.env`.

## Profiles

`APP_ENV` is `dev`, `test`, or `prod`. The matching example file lists every setting. Process environment variables override the file. An empty `SETTINGS_ENV_FILE` loads no file. Prod startup rejects a missing database URL, Finnhub key, Twelve Data key, Grok key, or SEC contact identity. API keys are `SecretStr` values and are never written to logs.

Dev and prod use PostgreSQL at `127.0.0.1:5432`, database `finance_poc`, user `postgres`. Create that database before the storage layer connects. The test profile uses in-memory SQLite so pytest does not need the server. Put the Grok key in `.env` as `GROK_API_KEY` (`XAI_API_KEY` is accepted as an alias). The default model is `grok-4.7` and the base URL is `https://api.x.ai/v1`.

`dev` uses readable debug logs and open API docs. `test` logs warnings. `prod` writes JSON logs to the console and a rotating file, and turns the interactive docs off. Every log line carries `request_id`, `provider`, and `ticker` when that context is set.

## Commands

The `Makefile` defines the same actions. On a machine without GNU make, run the Python commands with the virtualenv active.

| Make | Python | Purpose |
| --- | --- | --- |
| `make lint` | `python -m ruff check .` then `python -m black --check .` | Lint and format check |
| `make format` | `python -m ruff check --fix .` then `python -m black .` | Apply fixes |
| `make typecheck` | `python -m mypy` | Strict mypy |
| `make test` | `python -m pytest` | Pytest with coverage |
| `make check` | the three checks above | Lint, types, and tests |
| `make run-backend` | `python -m uvicorn finance_poc.main:app --reload --host 127.0.0.1 --port 8000` | API, after the app factory lands |
| `make run-frontend` | `python -m streamlit run frontend/app.py --server.port 8501 --server.address 127.0.0.1` | UI, after the Streamlit app lands |

Install the git hooks with `pre-commit install` after the dev extra is installed.

## Status

Step 2 of 12 is in place: settings profiles, logging, and the exception hierarchy. Connectors, storage, the API, and the UI are not implemented yet. The Grok client is not called yet.
