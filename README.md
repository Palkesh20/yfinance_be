# Finance data POC

Modular financial data platform. A FastAPI service collects prices, quotes, news, filings, and company data from several providers and exposes one normalized API. A Streamlit UI reads that API over HTTP.

Grok (`grok-4.7` on the xAI API) explains why a stock rose or fell. A primary researcher uses company headlines and filings, a secondary researcher uses the benchmark, sector, and financial facts, and an analyst writes the note. The home page filters that note to the last day, week, month, or year.

## Providers

| Capability | Order |
| --- | --- |
| Prices | yfinance, then Twelve Data |
| Quotes | Finnhub, then yfinance |
| News | Finnhub and yfinance, combined |
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
| `make run-backend` | `python -m uvicorn finance_poc.main:app --reload --host 127.0.0.1 --port 8000` | API |
| `make run-frontend` | `python -m streamlit run frontend/app.py --server.port 8501 --server.address 127.0.0.1` | UI |

Install the git hooks with `pre-commit install` after the dev extra is installed.

## Run

Start Postgres on `127.0.0.1:5432` with database `finance_poc`, or use Docker Compose, which starts Postgres for you. Put provider keys in `.env`.

```powershell
python -m uvicorn finance_poc.main:app --host 127.0.0.1 --port 8000
python -m streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501
python scripts/smoke_test.py
```

`SMOKE_BASE_URL` points the smoke script at an already running API. Without it, the script checks `/health` in-process with SQLite.

Docker Compose runs Postgres, the API, and Streamlit:

```powershell
docker compose up --build
```

The API is at `http://127.0.0.1:8000` and the UI at `http://127.0.0.1:8501`. Inside Compose, the UI calls `http://backend:8000`.

## API

| Method | Path | Data |
| --- | --- | --- |
| GET | `/health` | Database and provider configuration |
| GET | `/api/v1/prices/{ticker}` | Price bars |
| GET | `/api/v1/quotes/{ticker}` | Latest quote |
| GET | `/api/v1/news` | Headlines and sentiment |
| GET | `/api/v1/filings/{ticker}` | SEC filings |
| GET | `/api/v1/companies/{ticker}` | Company profile |
| GET | `/api/v1/companies/{ticker}/financials` | Annual statement facts |
| POST | `/api/v1/research` | Grok answer using fetched headlines |
| POST | `/api/v1/analysis` | Why the price moved over `1d`, `1w`, `1m`, or `1y` |

Responses use `data`, `source`, `cached`, and `as_of`. Errors use `error.code`, `error.message`, and `error.request_id`.

## Status

The data platform and the three-role move note are in place. There is no vector store. The note is an explanation of the fetched evidence, not a trade recommendation.
