# Installation

Proxium runs as one Docker image or from source.

## Supported versions

| | Supported | Docker image | Compose example |
|---|---|---|---|
| PostgreSQL | 17, 18 | 17 | 17 |
| Redis | 8 | 8, from its Debian base | 8 |

Every supported version runs the full test suite in CI. Your own database or Redis, e.g. a managed one, works on
any of them. PostgreSQL 13 to 16 should work too, nothing newer is used, but they aren't tested.

The image keeps PostgreSQL data in its volume, and a new major version can't read an older one's data. So the
bundled PostgreSQL changes only in a release that comes with an upgrade guide.

### Upgrading Redis

Nothing is lost whichever way Redis is upgraded. It keeps only what's true right now: the connections open at the
moment and the migration lock. Every proxy knows its own connections and writes them to Redis again on its own, so
there's no data to move. The bundled Redis and the compose example don't even save it to disk.

With the Docker image the bundled Redis comes with the image: it's upgraded with Proxium, nothing to do.

With the compose example or your own Redis, pick one of two ways.

**Restart in place**, the simple one. E.g. `docker compose -f docker/compose.yaml pull redis`, then
`docker compose -f docker/compose.yaml up -d redis`, or the upgrade of a managed Redis.

- Proxies keep running. For up to `PROXY_REDIS_OUTAGE_TIMEOUT` seconds of Redis being away, 30 by default, clients
  notice nothing. If it takes longer, new connections under connection limits are refused until Redis is back,
  others go on.
- Redis comes back empty. Within a third of `PROXY_CONNECTION_LEASE`, 10 seconds by default, every proxy writes its
  open connections there again. Until then a connection limit may let up to its value more in.

**Switch to a new Redis**, no outage at all.

1. Start the new Redis of a [supported version](#supported-versions).
2. Restart the instances one by one with `REDIS_URL` of the new one, see
   [Restart without downtime](proxy.md#restart-without-downtime). An old process finishes its connections counted
   in the old Redis, the new one counts in the new Redis.
3. Once no old process is left, stop the old Redis. What it still holds are connections of processes that are gone.

While old and new processes overlap they don't see each other's connections: a connection limit may let up to its
value more in, for up to `PROXY_GRACEFUL_TIMEOUT`.

Either way, don't upgrade Proxium at the same time: instances starting on different Redis don't share the migration
lock of `proxium-manage migrate`. More on how the proxy handles Redis failures in
[Connection limits](configuration.md#connection-limits).

## Docker

One image runs everything: the proxy, the API, the admin UI, PostgreSQL and Redis. State lives in one volume.

The image is `ikoldakov/proxium` on Docker Hub and `ghcr.io/koldakov/proxium` on GitHub, for amd64 and arm64.
`latest` is the last release, a version like `0.1.0` pins it, `edge` is the current `main`, not released yet.

`edge` is for trying what's coming, not for production. It's built from every commit to `main`, and a commit may
change what an installation needs before the release that documents how to upgrade. E.g. when Redis became required,
an `edge` installation with its own database and no `REDIS_URL` started each container with a Redis of its own,
which they don't share, and a source install without `REDIS_URL` stopped starting. Run a version tag in production.
Before pulling a new `edge`, read `[Unreleased]` in the
[changelog](https://github.com/koldakov/proxium/blob/main/CHANGELOG.md).

### Quickstart

```bash
docker run -d --name proxium -p 80:80 -p 8080:8080 -v proxium:/var/lib/proxium \
  -e SUPERUSER_CREATE=true -e SUPERUSER_EMAIL=admin@example.com -e SUPERUSER_PASSWORD=... \
  ikoldakov/proxium
```

`SUPERUSER_CREATE=true` creates the first admin on start, the email and the password are required then. Later
starts skip it: changing `SUPERUSER_PASSWORD` doesn't change the stored password.

Without it no admin is created, create one later in the running container:

```bash
docker exec -it proxium proxium-manage createsuperuser
```

The admin UI is at http://localhost, the proxy at `localhost:8080`. Superuser variables: `SUPERUSER_CREATE`,
`SUPERUSER_EMAIL`, `SUPERUSER_PASSWORD`, `SUPERUSER_NAME`, `SUPERUSER_SURNAME`, see [Configuration](configuration.md)
for these and the rest.

### Domain and HTTPS for the admin UI

| Want | Add |
|---|---|
| Let's Encrypt | `-p 443:443 -e ADMIN_HOST=admin.example.com -e ADMIN_TLS=auto` |
| Own ACME server, no internet | the same plus `-e ADMIN_ACME_CA=https://ca.corp.lan/acme/directory` |
| Own certificate | `-p 443:443 -e ADMIN_HOST=admin.example.com -e ADMIN_TLS=files -v /etc/ssl/proxium:/certs:ro` |
| Self-signed, no internet | `-p 443:443 -e ADMIN_HOST=admin.corp.lan -e ADMIN_TLS=internal` |

`ADMIN_HOST` must point to this server: add a DNS A or AAAA record for it at your DNS provider. `auto` also needs
port 80 or 443 reachable by the ACME server: from the internet for Let's Encrypt, from your network for
`ADMIN_ACME_CA`. Behind your own load balancer or Kubernetes ingress that terminates TLS,
keep `ADMIN_TLS=off` and route the host to the container's port 80.

`files` reads `cert.pem` and `key.pem`, readable by UID 10001. `internal` signs with Caddy's own CA: trust
`/var/lib/proxium/caddy/pki/authorities/local/root.crt` from the volume on client machines.

The proxy's own TLS doesn't depend on this: its certificates are managed in the admin UI, see [TLS](proxy.md#tls).

### Ports and IPs

`PROXY_LISTEN` is what the proxy listens on inside the container, `-p` publishes it. Container ports must match.
`EXPOSE` in the image lists only the defaults, any port works with `-p`:

```bash
docker run -d --name proxium -p 80:80 -p 8090-8092:8090-8092 -e PROXY_LISTEN=0.0.0.0:8090-8092 \
  -v proxium:/var/lib/proxium ikoldakov/proxium
```

Several IPs require the host network: in a bridge network the container doesn't see the host's IPs. `-p` isn't used
then, `PROXY_LISTEN` takes the host's addresses as is:

```bash
docker run -d --name proxium --network host -e PROXY_LISTEN=10.0.0.0/29:10000-10999 \
  -v proxium:/var/lib/proxium ikoldakov/proxium
```

| | `-p` | `--network host` |
|---|---|---|
| Ports and port ranges | yes | yes |
| Several listening IPs | no, the proxy sees one | yes, Linux only |
| [Outgoing IPs](proxy.md#outgoing-ips) | no, one host IP | yes, Linux only |

Linux only: Docker Desktop on macOS and Windows runs containers in a VM, they don't see the computer's IPs even
with `--network host`. Run proxium without Docker there, see [From source](#from-source).

### Own database, Redis and secrets

| Want | Add |
|---|---|
| Own PostgreSQL | `-e DATABASE_URL=postgres://user:password@db.example.com:5432/proxium` |
| Own Redis | `-e REDIS_URL=redis://redis.example.com:6379/0 -e REDIS_PASSWORD=...` |
| Own keys | `-e ENCRYPTION_KEY=... -e API_SECRET_KEY=...`, else generated once and kept in the volume |

Every variable from [Configuration](configuration.md) works with `-e`, Docker-only ones are under [Docker](configuration.md#docker).
Give `docker stop` time for open connections: `--stop-timeout 40`. Leave a few seconds over
`PROXY_GRACEFUL_TIMEOUT`: closing connections release their places in Redis, up to the two Redis timeouts.

### Separate containers

`docker/compose.yaml` runs the same image as two containers, the API with the admin UI and the proxy, next to
PostgreSQL and Redis.
They share the secrets, settings come from the environment as with `docker run`:

```bash
SUPERUSER_CREATE=true SUPERUSER_EMAIL=admin@example.com SUPERUSER_PASSWORD=... \
  docker compose -f docker/compose.yaml up -d --build
```

`ENCRYPTION_KEY` and `API_SECRET_KEY`, if not set, are generated on the first start and kept in the `secrets`
volume. Set them, and the volume stores no secrets. Keys generated by an earlier start stay there unused: delete
them from the volume once you set your own. To move to your own keys later, pass the generated ones from the volume,
or rotate `ENCRYPTION_KEY` with `ENCRYPTION_OLD_KEYS`, see [TLS](proxy.md#tls): with a new key stored certificates can't be
read. A new `API_SECRET_KEY` only logs everyone out.

To customize ports, the database, TLS and the rest, take
[docker/compose.yaml](https://github.com/koldakov/proxium/blob/main/docker/compose.yaml) as a starting point and
edit your copy.

### Commands

```bash
docker exec -it proxium proxium-manage createsuperuser
docker exec -it proxium proxium-manage changepassword admin@example.com
```

## From source

Requirements: Python 3.14+, [uv](https://docs.astral.sh/uv/), PostgreSQL and Redis of the
[supported versions](#supported-versions).

```bash
git clone https://github.com/koldakov/proxium.git
cd proxium
uv sync
cp .env.template .env           # fill it in, see Configuration
uv run --env-file .env proxium-manage migrate
uv run --env-file .env proxium-manage createsuperuser
```

Run the proxy:

```bash
uv run --env-file .env proxium
```

or

```bash
uv run --env-file .env python -m proxium
```

The API is a FastAPI app served by [Hypercorn](https://hypercorn.readthedocs.io/). Extra arguments go to Hypercorn:

```bash
uv run --env-file .env proxium-api --bind 127.0.0.1:8000
```
