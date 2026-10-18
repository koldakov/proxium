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

For acceptance tests, also copy `.env.test.template` to `.env.test`, see [Tests](#tests).

## Checks

Hooks run on commit: ruff, mypy, prettier, eslint, tsc. Run them all manually:

```bash
uv run pre-commit run --all-files
```

CI runs the checks and the tests on every push.

## Tests

```bash
uv run pytest                            # everything, fails under 85% coverage
uv run pytest tests/unit --no-cov        # no database
uv run pytest tests/acceptance --no-cov  # needs PostgreSQL, Redis and .env.test
```

The coverage threshold is for both suites together: a subset alone doesn't reach it, so run one with `--no-cov`.
A known annoyance: without the flag, e.g. `uv run pytest tests/unit` fails on coverage though every test passes. If you
know a clean way to check the threshold only on a full run, a pull request is welcome.

### Unit tests

`tests/unit` mirrors `src/proxium`. They cover critical logic only (limits, rules, counting) and never reach the
database.

### Acceptance tests

Scenarios in plain English in `tests/acceptance/features`, run by [pytest-bdd](https://pytest-bdd.readthedocs.io/)
against a real proxy, PostgreSQL and Redis. Steps live in `tests/acceptance/steps`, shared by every feature; async ones are
wrapped in `@async_step`.

API scenarios send requests to the app in process, with JSON in docstrings. A step keeps an answer under a name, and
`${office.id}` refers to its field later, deeper by dots, e.g. `${plan.rules.0.id}`: as text in a path, as a JSON value
in a body.

Scenarios on outgoing IPs need a second loopback address, `127.0.0.2`: Linux has it, macOS doesn't, so they're skipped
there. To run them on macOS: `sudo ifconfig lo0 alias 127.0.0.2`.

Local setup, once:

1. Copy `.env.test.template` to `.env.test` and set `DATABASE_URL`, and `REDIS_URL` unless Redis is on
   `localhost:6379`. pytest reads only `.env.test`, never `.env`.
2. Let that user create databases:

   ```bash
   psql -U postgres -c 'ALTER ROLE <user> CREATEDB;'
   ```

The tests use the server from `DATABASE_URL`, but never its database: they create `test_<name>` next to it and drop
it after the run. Your data is never touched. In Redis they take and drop keys only under
`test_proxium:`, never an instance's. No Redis yet: `docker run -d -p 6379:6379 redis:8-alpine`.

PyCharm resolves steps from `.feature` files only in the Professional edition. In the free one, turn off
Settings → Editor → Inspections → Gherkin → Undefined step: a missing step fails the test anyway.

### CI

Unit tests run first, acceptance tests only once they pass, then their coverage is combined into one report in the
run summary. The build fails if it's under the threshold.

## Code

- Model changes need a migration, see [Database migrations](#database-migrations).
- Changes come with tests where they matter, see [Tests](#tests).
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
