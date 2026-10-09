# Configuration

Settings are read from environment variables. Copy the template and fill it in:

```bash
cp .env.template .env
```

## Common

Read by the proxy, the API and the management commands.

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL URL, e.g. `postgres://user:password@host/db_name` |
| `ENCRYPTION_KEY` | Fernet key that encrypts private keys of TLS certificates in the database, see [TLS](proxy.md#tls) |
| `ENCRYPTION_OLD_KEYS` | Comma-separated previous keys, they still decrypt during [key rotation](proxy.md#tls) |
| `DATABASE_ECHO` | Log every SQL query, default `false`. Parameters are always hidden |
| `DATABASE_POOL_SIZE` | Connections each process keeps open, default `5` |
| `DATABASE_POOL_MAX_OVERFLOW` | Extra connections under load, default `10` |
| `DATABASE_POOL_TIMEOUT` | Seconds to wait for a free connection, default `30` |
| `DATABASE_POOL_RECYCLE` | Seconds after which a connection is replaced, default `-1` (never) |

## Proxy

| Variable | Description |
|---|---|
| `PROXY_LISTEN` | Addresses to listen on, default `127.0.0.1:8080`, see below |
| `PROXY_GRACEFUL_TIMEOUT` | Seconds open connections get to finish on shutdown, default `30` |
| `PROXY_LOG_LEVEL` | `DEBUG`, `INFO`, `WARNING`, `ERROR` or `CRITICAL`, default `INFO` |
| `PROXY_SETTINGS_POLL_INTERVAL` | Seconds between lookups of the [settings](proxy.md#settings) from the admin UI, default `5` |

`PROXY_LISTEN` is a comma-separated list of `host:port` pairs. A host is an IP address, a network or a host name,
IPv6 goes in brackets. A port may be an inclusive range. Every host listens on every port of its pair:

```bash
PROXY_LISTEN=127.0.0.1:8080                          # one socket
PROXY_LISTEN=localhost:8080                          # every address localhost resolves to
PROXY_LISTEN=0.0.0.0:8080,[::]:8080                  # all IPv4 and IPv6 interfaces
PROXY_LISTEN=10.0.0.0/29:10000-10999                 # 6 host addresses x 1000 ports
```

Host names are resolved once, on start.

## API

| Variable | Description |
|---|---|
| `API_SECRET_KEY` | Secret that signs API user tokens, at least 32 characters. Changing it logs everyone out |
| `API_CORS_ORIGINS` | Comma-separated browser origins allowed to call the API, e.g. the admin dev server. Empty blocks all |
| `API_OUTGOING_POOL_MAX_SIZE` | IPs in one outgoing IP pool at most, default `256` |
| `API_POLICIES_MAX_PER_OWNER` | Policies assigned to one account or trusted network at most, up to `100`, default `32` |

## Management commands

| Variable | Description |
|---|---|
| `SUPERUSER_EMAIL` | `createsuperuser --no-input`: email, if `--email` isn't passed |
| `SUPERUSER_PASSWORD` | `createsuperuser --no-input`: password, there is no flag for it |
| `SUPERUSER_NAME` | `createsuperuser --no-input`: name, if `--name` isn't passed, default blank |
| `SUPERUSER_SURNAME` | `createsuperuser --no-input`: surname, if `--surname` isn't passed, default blank |

Without `--no-input` these are ignored: `createsuperuser` always prompts.

## Docker

Read only by the [image](installation.md#docker). There `DATABASE_URL`, `ENCRYPTION_KEY` and `API_SECRET_KEY` are
optional: unset, the bundled PostgreSQL runs and the keys are generated once, all kept in the volume.

| Variable | Description |
|---|---|
| `PROXIUM_SERVICES` | Services to run, comma-separated: `proxy`, `api`, `admin`. Default all |
| `SUPERUSER_CREATE` | `true` creates the superuser from `SUPERUSER_*` on start, an existing one is skipped. Default `false` |
| `ADMIN_TLS` | How the admin UI is served: `off`, `auto`, `files` or `internal`, see [Installation](installation.md#domain-and-https-for-the-admin-ui). Default `off` |
| `ADMIN_HOST` | Admin host name, e.g. `admin.example.com`. Needed by `auto` and `files`, `internal` defaults to `localhost` |
| `ADMIN_ACME_CA` | Own ACME server for `auto` instead of Let's Encrypt |
| `ADMIN_HTTP_PORT` | Admin HTTP port, default `80` |
| `ADMIN_HTTPS_PORT` | Admin HTTPS port, default `443` |
| `API_BIND` | Where the API listens, default the socket `unix:/run/proxium/api.sock` |
| `ADMIN_API_UPSTREAM` | Where the admin UI finds the API, default the same socket. `host:port` when the API runs in another container |
