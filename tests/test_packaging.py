"""Scaffold checks for the finance_poc distribution and profile templates."""

from __future__ import annotations

import importlib
from pathlib import Path

import finance_poc

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = (
    "pyproject.toml",
    "README.md",
    "Makefile",
    ".gitignore",
    ".pre-commit-config.yaml",
    ".env.example",
    "config/dev.env.example",
    "config/test.env.example",
    "config/prod.env.example",
    "backend/src/finance_poc/py.typed",
    "frontend/components/__init__.py",
)

SUBMODULES = (
    "finance_poc.api",
    "finance_poc.api.v1",
    "finance_poc.core",
    "finance_poc.models",
    "finance_poc.connectors",
    "finance_poc.services",
    "finance_poc.storage",
    "finance_poc.utils",
)


def _env_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        keys.add(stripped.split("=", 1)[0].strip())
    return keys


def test_package_version() -> None:
    assert finance_poc.__version__ == "0.1.0"


def test_py_typed_marker() -> None:
    package_dir = Path(finance_poc.__file__).resolve().parent
    assert (package_dir / "py.typed").is_file()


def test_scaffold_files_exist() -> None:
    missing = [relative for relative in REQUIRED_PATHS if not (ROOT / relative).is_file()]
    assert missing == []


def test_submodules_import() -> None:
    for name in SUBMODULES:
        importlib.import_module(name)


def test_profile_examples_share_keys() -> None:
    dev = _env_keys(ROOT / "config" / "dev.env.example")
    test = _env_keys(ROOT / "config" / "test.env.example")
    prod = _env_keys(ROOT / "config" / "prod.env.example")
    local = _env_keys(ROOT / ".env.example")
    assert dev == test == prod == local
    assert "FINNHUB_API_KEY" in dev
    assert "TWELVEDATA_API_KEY" in dev
    assert "GROK_API_KEY" in dev
    assert "GROK_MODEL" in dev
    assert "SEC_COMPANY_NAME" in dev
    assert "SEC_CONTACT_EMAIL" in dev


def _env_value(path: Path, key: str) -> str:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            return stripped.split("=", 1)[1]
    raise AssertionError(f"{key} missing from {path.name}")


def test_dev_database_is_local_postgres() -> None:
    url = _env_value(ROOT / "config" / "dev.env.example", "DATABASE_URL")
    assert url == "postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/finance_poc"


def test_test_database_is_sqlite_memory() -> None:
    url = _env_value(ROOT / "config" / "test.env.example", "DATABASE_URL")
    assert url == "sqlite+aiosqlite:///:memory:"
