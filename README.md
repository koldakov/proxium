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

### Common

Read by the proxy, the API and the management commands.

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL URL, e.g. `postgres://user:password@host/db_name` |
| `DATABASE_ECHO` | Log every SQL query, default `false`. Parameters are always hidden |
| `DATABASE_POOL_SIZE` | Connections each process keeps open, default `5` |
| `DATABASE_POOL_MAX_OVERFLOW` | Extra connections under load, default `10` |
| `DATABASE_POOL_TIMEOUT` | Seconds to wait for a free connection, default `30` |
| `DATABASE_POOL_RECYCLE` | Seconds after which a connection is replaced, default `-1` (never) |

### Proxy

| Variable | Description |
|---|---|
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

### API

| Variable | Description |
|---|---|
| `API_SECRET_KEY` | Secret that signs API user tokens, at least 32 characters. Changing it logs everyone out |
| `API_CORS_ORIGINS` | Comma-separated browser origins allowed to call the API, e.g. the admin dev server. Empty blocks all |
| `API_OUTGOING_POOL_MAX_SIZE` | IPs in one outgoing IP pool at most, default `256` |

### Management commands

| Variable | Description |
|---|---|
| `SUPERUSER_EMAIL` | `createsuperuser`: email, if `--email` isn't passed. Not prompted then |
| `SUPERUSER_PASSWORD` | `createsuperuser --no-input`: password, there is no flag for it |
| `SUPERUSER_NAME` | `createsuperuser`: name, if `--name` isn't passed, default blank |
| `SUPERUSER_SURNAME` | `createsuperuser`: surname, if `--surname` isn't passed, default blank |

## Usage

```bash
uv run --env-file .env proxium
```

or

```bash
uv run --env-file .env python -m proxium
```

Every port speaks HTTP and SOCKS5, the protocol is detected by the first byte of the connection.
Clients authenticate with proxy accounts from the database, inactive and expired ones are refused:

```bash
curl -x http://username:password@127.0.0.1:8080 https://example.com                  # basic account
curl -x http://127.0.0.1:8080 --proxy-header "Proxy-Authorization: Bearer <token>" https://example.com  # token account
curl -x socks5h://username:password@127.0.0.1:8080 https://example.com                # basic account over SOCKS5
```

HTTP supports CONNECT tunnels and plain HTTP forwarding. SOCKS5 supports only CONNECT, with IPv4, IPv6 and domain
targets, and only basic accounts: the protocol has username/password authentication but no tokens.
Use `socks5h://` so the proxy resolves domains, with `socks5://` curl resolves them itself.

### Trusted networks

Clients from trusted networks use the proxy without credentials, over HTTP and SOCKS5 alike. There are none by
default, so everyone needs an account. Add them in the admin UI or with the API (`/api/trusted-networks`), e.g.
`192.168.0.0/16` for a local network or `10.0.0.5` for a single address. Add only networks you control: anyone in
them gets in.

```bash
curl -x http://127.0.0.1:8080 https://example.com         # from a trusted network
curl -x socks5h://127.0.0.1:8080 https://example.com
```

Networks are checked on every new connection, so new connections follow changes right away. Clients connected
right now keep their open connections until they close: removing a network doesn't cut them off at once.

A client that sends credentials is checked as an account even from a trusted network. The trusted network
authenticator itself refuses any credentials, since it can't check them: registered for a credentials kind by
mistake, it doesn't let in any password.

Networks may nest, e.g. `10.0.0.0/8` for the office and `10.1.2.3` for a CI server inside it. The narrowest
active one names the client in logs, e.g. `network:10.1.2.3/32`, and turning off one keeps the other working.
The admin UI lists the networks containing the one being edited and the ones inside it, page by page, and
tells how many keep trusting the addresses of a network being deleted. `/0` trusts the whole internet: the admin UI
asks to confirm saving it and warns while one is active.

`/api/trusted-networks` filters: `contains=<network>` for networks that contain it, `within=<network>` for ones
inside it, `isActive=true|false`, `prefixLength=<n>`, e.g. `?isActive=true&prefixLength=0` for ones open to everyone.

### Outgoing IPs

On a server with several IPs, each account and trusted network picks the one sites see, its outgoing mode:

- `system`, the default: the OS picks, usually the main IP of the server.
- `listener`: the IP the client connected to. A client of `203.0.113.11:8080` goes out from `203.0.113.11`, so
  listen on every IP, e.g. `PROXY_LISTEN=203.0.113.8/29:8080`. It works on `0.0.0.0` too.
- `pool`: a random IP of the account's pool, picked anew for every connection. A pool of one IP is a dedicated IP.

First add the server's IPs under Outgoing IPs in the admin UI. Then pick the mode on the account or trusted
network form: for `pool`, the IPs of the pool go right under it, on creating too. Later the pool is edited on the
account's page or the network's form, and changes apply to new connections at once.

A pool takes IPs of one family, IPv4 or IPv6: an IPv4 IP can't reach IPv6-only sites and back, so a mixed pool
would fail at random. The admin offers only the IPs a pool can take. A pool in use keeps at least one IP, switch
the mode first to empty it. An IP in a pool can't be deleted, and an IP's address can change only within its
family. A pool holds up to `API_OUTGOING_POOL_MAX_SIZE` IPs.

The proxy binds the outgoing socket to the IP before connecting, so the IP must be on the server's interfaces,
e.g. `ip addr add 203.0.113.11/32 dev eth0`, and routed to it. Nothing checks that on saving, the API may run on
another host: a connection from an IP that isn't there fails with "not on this host or loopback" in the log, and
so does one from loopback, e.g. `listener` on `127.0.0.1`. Nothing falls back to another IP. Behind cloud NAT,
use the private IPs the public ones map to. IPs of different providers need policy routing (`ip rule`) in the OS.

Check an account with a site that shows the caller's IP:

```bash
curl -x http://USERNAME:PASSWORD@127.0.0.1:8080 https://ifconfig.me
```

`Ctrl+C` (SIGINT) or SIGTERM stops accepting and waits up to `PROXY_GRACEFUL_TIMEOUT` for open connections.
A second signal stops immediately.

### API

The API is a FastAPI app served by [Hypercorn](https://hypercorn.readthedocs.io/). Extra arguments go to Hypercorn:

```bash
uv run --env-file .env proxium-api --bind 127.0.0.1:8000
```

### Management commands

Django-style commands run with `proxium-manage <command>`, `--help` lists them.

Create the first superuser, it prompts for the email and password. Name and surname are blank unless passed
with `--name`, `--surname` or `SUPERUSER_NAME`, `SUPERUSER_SURNAME`, see [Configuration](#configuration):

```bash
uv run --env-file .env proxium-manage createsuperuser
uv run --env-file .env proxium-manage createsuperuser --email admin@example.com --name Ivan
```

Without prompts, e.g. in scripts, the password comes only from `SUPERUSER_PASSWORD`, the email from `--email` or
`SUPERUSER_EMAIL`:

```bash
SUPERUSER_PASSWORD=... uv run --env-file .env proxium-manage createsuperuser --no-input --email admin@example.com
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
