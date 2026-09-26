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
| `PROXY_LISTEN` | Addresses to listen on, default `127.0.0.1:8080`, see below |
| `PROXY_GRACEFUL_TIMEOUT` | Seconds open connections get to finish on shutdown, default `30` |
| `PROXY_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`, default `INFO` |

`PROXY_LISTEN` is a comma-separated list of `host:port` pairs. A host is an IP address, a network or a host name,
IPv6 goes in brackets. A port may be an inclusive range. Every host listens on every port of its pair:

```bash
PROXY_LISTEN=127.0.0.1:8080                          # one socket
PROXY_LISTEN=localhost:8080                          # every address localhost resolves to
PROXY_LISTEN=0.0.0.0:8080,[::]:8080                  # all IPv4 and IPv6 interfaces
PROXY_LISTEN=10.0.0.0/29:10000-10999                 # 6 host addresses x 1000 ports
```

Host names are resolved once, on start.

## Usage

```bash
uv run --env-file .env proxium
```

or

```bash
uv run --env-file .env python -m proxium
```

`Ctrl+C` (SIGINT) or SIGTERM stops accepting and waits up to `PROXY_GRACEFUL_TIMEOUT` for open connections.
A second signal stops immediately.

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
