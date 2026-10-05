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
| `ENCRYPTION_KEY` | Fernet key that encrypts private keys of TLS certificates in the database, see [TLS](#tls) |
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
| `PROXY_SETTINGS_POLL_INTERVAL` | Seconds between lookups of the [settings](#settings) from the admin UI, default `5` |

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

### TLS

Clients may encrypt the connection to the proxy, on the same ports: a connection starting with a TLS handshake is
decrypted, and HTTP or SOCKS5 is detected inside. Credentials then don't travel in the clear. TLS is on while a
certificate is active: add one under TLS certificates in the admin UI, the first one is activated right away.
Without one, TLS clients get a handshake failure, plain HTTP and SOCKS5 keep working.

```bash
curl -x https://username:password@proxy.example.com:8080 https://example.com
```

The certificate must be for the host name clients connect to. One certificate is active at a time and serves all
ports, for several names use one with all of them in it. Activating another one, on adding it or later on its
page, turns the active one off: new connections get it within the cache TTL ([settings](#settings)), open ones keep
theirs, no restart needed. The proxy looks the certificate up once per cache TTL, not on every connection: TLS
clients can't load the database before they authenticate. The admin UI names the one turned off, and if another admin has activated one meanwhile, it refuses and shows the new state
instead of turning off a certificate you haven't seen. The active one can't be deleted, deactivate it first.

A self-signed certificate works too, the admin UI generates one for given names. Clients trust it only if told
to: download the certificate from its page for curl's `--proxy-cacert`, or skip the check with `--proxy-insecure`.

```bash
curl -x https://username:password@proxy.example.com:8080 --proxy-cacert proxium-1.pem https://example.com
```

Private keys are stored encrypted with `ENCRYPTION_KEY`, the API never returns them. Generate the key once and give
the same one to the proxy, the API and the management commands:

```bash
python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
```

Losing or changing it makes the stored keys unreadable: TLS clients are refused with "can't be decrypted" in the
log until the certificate is uploaded again.

The proxy needs a writable temporary directory: Python's `ssl` loads a key only from a file, not from memory
([python/cpython#60691](https://github.com/python/cpython/issues/60691)), so the decrypted key goes to a file
readable by the proxy's user alone and is removed right after loading. In a container with a read-only root, point
`TMPDIR` to a tmpfs, e.g. an `emptyDir` with `medium: Memory` in Kubernetes: the key then never reaches a disk.
Without it, TLS clients are refused with "Can't write the certificate to a temporary file" in the log.

A renewed certificate, e.g. from Let's Encrypt, goes in with `importcert`, see
[Management commands](#management-commands). certbot can run it after every renewal, with the same environment as
the proxy:

```bash
certbot renew --deploy-hook 'cd /opt/proxium && uv run --env-file .env proxium-manage importcert --no-input \
  --cert "$RENEWED_LINEAGE/fullchain.pem" --key "$RENEWED_LINEAGE/privkey.pem"'
```

SOCKS5 inside TLS works too, but few clients support it, curl doesn't. HTTP/2 to the proxy isn't supported, clients
fall back to HTTP/1.1.

Don't terminate TLS in front of the proxy, e.g. with nginx `stream`: the proxy would see nginx's connection
instead of the client's, so trusted networks would check nginx's IP, and the `listener` outgoing mode would take
the address nginx connects to.

### Trusted networks

Clients from trusted networks use the proxy without credentials, over HTTP and SOCKS5 alike. There are none by
default, so everyone needs an account. Add them in the admin UI or with the API (`/api/trusted-networks`), e.g.
`192.168.0.0/16` for a local network or `10.0.0.5` for a single address. Add only networks you control: anyone in
them gets in.

```bash
curl -x http://127.0.0.1:8080 https://example.com         # from a trusted network
curl -x socks5h://127.0.0.1:8080 https://example.com
```

New connections follow changes within the cache TTL ([settings](#settings)). Clients connected right now keep
their open connections until they close: removing a network doesn't cut them off at once.

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
account's page or the network's form, and changes apply to new connections within the cache TTL.

A pool takes IPs of one family, IPv4 or IPv6: an IPv4 IP can't reach IPv6-only sites and back, so a mixed pool
would fail at random. The admin offers only the IPs a pool can take. A pool in use keeps at least one IP, switch
the mode first to empty it. An IP in a pool can't be deleted, and an IP's address can change only within its
family. A pool holds up to `API_OUTGOING_POOL_MAX_SIZE` IPs.

The proxy binds the outgoing socket to the IP before connecting, so the IP must be on the server's interfaces,
e.g. `ip addr add 203.0.113.11/32 dev eth0`, and routed to it. Nothing checks that on saving, the API may run on
another host: a connection from an IP that isn't there fails with "not on this host or loopback" in the log, and
so does one from loopback, e.g. `listener` on `127.0.0.1`. Nothing falls back to another IP. Behind cloud NAT,
use the private IPs the public ones map to. IPs of different providers need policy routing (`ip rule`) in the OS.

### Settings

The Settings page of the admin UI holds what the proxy does with connections. The proxy looks the settings up
every `PROXY_SETTINGS_POLL_INTERVAL` seconds and applies them without a restart: new connections get them, open
ones keep the old.

- Allowed networks: the proxy reaches only the public internet, loopback, private networks and cloud metadata
  (`169.254.169.254`) are blocked. List the private networks clients may reach anyway, e.g. `10.0.0.0/8`. Every
  client gets them, accounts and trusted networks alike.
- Timeouts, seconds: handshake, for a client to authenticate and send its request, `10` by default; idle, after
  which a silent tunnel is closed, `300`; connect, to resolve and reach a target, `10`.
- Cache TTL, seconds, `10` by default: how long the proxy reuses checks of accounts and trusted networks, refusals
  too, and the TLS certificate, instead of looking them up and hashing secrets on every connection. Changes to
  them reach new connections within it: a revoked or expired account keeps connecting, a removed trusted network
  stays trusted, a new one isn't yet. Lowering it drops what's cached, so it applies at once. If the database is
  down, clients without a cached check are refused.

Check an account with a site that shows the caller's IP:

```bash
curl -x http://USERNAME:PASSWORD@127.0.0.1:8080 https://ifconfig.me
```

`Ctrl+C` (SIGINT) or SIGTERM stops accepting and waits up to `PROXY_GRACEFUL_TIMEOUT` for open connections.
A second signal stops immediately.

### Users and permissions

Admin UI users are managed under Access. A superuser may do everything, the first one comes from
`createsuperuser`, see [Management commands](#management-commands). Other users get permissions per section and
action, e.g. view, add and change trusted networks, revoke basic accounts or activate certificates, through groups
and on their own: a user has the permissions of all their groups plus their own. Traffic is a permission of its
own, so a user can see accounts and networks without their traffic.

- Groups, e.g. Operators or Read only, are named sets of permissions. A change to a group applies to all its
  users.
- A user gives only what they have: permissions, and groups whose permissions they all have. Taking away is
  always allowed. Only superusers make superusers or change them.
- Nobody deactivates themselves or takes their own superuser status away.
- An inactive user can't log in. A change of permissions or activity applies to the user's next request, the
  admin UI shows it within a minute or at the first refused action.
- Everyone changes their own name, surname and password under Profile in the user menu, no permission needed.
  The email is the login: only a user with `users.change` changes it.

The admin UI hides what the user may not do: sections, buttons, the outgoing pool without access to outgoing IPs.

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

Set a new password for any user, e.g. a forgotten one, it prompts for it twice:

```bash
uv run --env-file .env proxium-manage changepassword admin@example.com
```

Add a TLS certificate from PEM files and activate it, see [TLS](#tls). It asks before turning the active one off,
`--no-input` doesn't. The same certificate imported again is only activated. The key must have no password:

```bash
uv run --env-file .env proxium-manage importcert --cert fullchain.pem --key privkey.pem
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

## License

[MIT](LICENSE.md)
