# Proxium

A lightweight proxy server written in Python.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/)

## Installation

```bash
git clone <repository-url>
cd proxium
uv sync
```

## Configuration

Settings are read from environment variables. Copy the template and fill it in:

```bash
cp .env.template .env
```

| Variable       | Description                                   |
|----------------|-----------------------------------------------|
| `DATABASE_URL` | PostgreSQL URL, e.g. `postgres://user:password@host/db_name` |

## Usage

```bash
uv run proxium
```

or

```bash
uv run python -m proxium
```

## Development

Install the git hooks:

```bash
uv run pre-commit install
```

Run all checks manually:

```bash
uv run pre-commit run --all-files
```

The hooks run [ruff](https://docs.astral.sh/ruff/) (lint and format) and [mypy](https://mypy.readthedocs.io/).
Their configuration lives in `pyproject.toml`.

## Database migrations

Migrations are managed with [Alembic](https://alembic.sqlalchemy.org/) and live in `src/proxium/db/migrations`.
Models must be imported in `src/proxium/db/models.py` so autogenerate can see them.

```bash
# Apply migrations
uv run --env-file .env alembic upgrade head

# Create a new migration from model changes
uv run --env-file .env alembic revision --autogenerate -m "description"
```
