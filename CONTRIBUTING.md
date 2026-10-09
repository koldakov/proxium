# Contributing

Thanks for helping with Proxium. Please follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Issues

- Bugs and feature requests: open an [issue](https://github.com/koldakov/proxium/issues/new/choose) using a template.
- Vulnerabilities: never in public issues, see [SECURITY.md](SECURITY.md).

For a larger change, open an issue first to agree on the approach.

## Setup

Requirements: Python 3.14+, [uv](https://docs.astral.sh/uv/), Node 24 for the admin UI.

```bash
git clone git@github.com:koldakov/proxium.git
cd proxium
uv sync
npm install --prefix fsrc
uv run pre-commit install
```

The admin UI hooks use tools from `fsrc/node_modules`, so `npm install` is needed even for backend changes.

Copy `.env.template` to `.env` and fill it in. Every new environment variable goes to `.env.template` with a
description.

## Checks

Hooks run on commit: ruff, mypy, prettier, eslint, tsc. Run them all manually:

```bash
uv run pre-commit run --all-files
```

Tests:

```bash
uv run pytest
```

CI runs both on every push.

## Code

- Model changes need a migration, see [Database migrations](#database-migrations).
- Tests cover critical logic and mirror the `src` structure.
- User-facing changes update the README and [docs](docs).

## Database migrations

Migrations are managed with [Alembic](https://alembic.sqlalchemy.org/) and live in `src/proxium/db/migrations`.
Models must be imported in `src/proxium/db/models.py` so autogenerate can see them.

```bash
# Apply migrations
uv run --env-file .env proxium-manage migrate

# Create a new migration from model changes
uv run --env-file .env alembic revision --autogenerate -m "description"
```

## Commits and pull requests

- Commit subject up to 72 characters, in the imperative: `Add proxy pool limits`. Details go to the body.
- One pull request — one change. Fill in the template.
- Keep the branch up to date with `main`, CI must pass.

By contributing you agree your work is licensed under the [MIT License](LICENSE.md).
