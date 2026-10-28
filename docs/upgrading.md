# Upgrading

Read the release's section in the [changelog](https://github.com/koldakov/proxium/blob/main/CHANGELOG.md) first:
it lists every change a client or an installation may notice. Releases that need more than pulling the new version
get a section here.

## Every upgrade

Database migrations come with the new version and must run before it serves:

- **Docker image**: every start of a container with the proxy or the API applies them before those start, nothing
  to do. Several containers starting at once migrate one at a time, see
  [Management commands](management.md).
- **From source**: run them after each `uv sync` of a new version, before restarting the proxy and the API:

  ```bash
  uv run --env-file .env proxium-manage migrate
  ```

  Run it every time, even when the changelog mentions no schema change: with nothing new it does nothing.

## From 0.2 to 0.3

0.3 shows every proxy instance in the admin UI: the new Overview start page and Proxy instances. Proxies report
themselves to the database, so the schema changes: migrations add the instances table and their permissions. They
run on start as on every upgrade and take a second.

### What to check first

- **Back up the database.** Going back to 0.2 isn't a plain restart this time: 0.2's `migrate` doesn't know the
  new migrations and stops, and the Docker image doesn't start the proxy and the API without it. See
  [Going back](#going-back).
- **Admins who aren't superusers.** The Overview and Proxy instances need the new `proxy_instances.view`, deregistering
  an instance `proxy_instances.deregister`. Existing groups don't get them: add them where needed. Until then such
  users land on the first page open to them, as before.
- **Docker bridge networking.** Proxies report the IPs of their interfaces, in bridge networking the container's.
  Outgoing IPs of the host show as "Not on the proxy" there: a proxy can't connect from them in bridge networking
  anyway, run it with `--network host`, see [Ports and IPs](installation.md#ports-and-ips).
- **Global policies.** At most `API_GLOBAL_POLICIES_MAX` of them, `32` by default. Having more keeps them working,
  only making one more global is refused.

### Docker image

```bash
docker pull ikoldakov/proxium:0.3.0
docker stop --time 40 proxium && docker rm proxium
docker run -d --name proxium ... ikoldakov/proxium:0.3.0
```

Use the same `-p`, `-v` and `-e` as before.

### Compose

Nothing new in the compose example: pin the image to `ikoldakov/proxium:0.3.0` or keep `latest`, then:

```bash
docker compose -f docker/compose.yaml pull
docker compose -f docker/compose.yaml up -d
```

### From source

```bash
git fetch --tags && git checkout v0.3.0
uv sync
uv run --env-file .env proxium-manage migrate
```

and restart the proxy and the API. New variables in `.env.template` have working defaults, none has to be set.

### Without downtime

The 0.3 proxy starts next to the 0.2 one as in [Restart without downtime](proxy.md#restart-without-downtime), and
they share every limit through Redis. A 0.2 proxy doesn't report itself: the Overview shows only the 0.3 ones.

### Going back

Restore the backup made before the upgrade and run 0.2.0: what was written since, e.g. traffic, is lost. With the
image's own database, the backup is a copy of the volume while the container is stopped:

```bash
docker stop --time 40 proxium
docker run --rm -v proxium:/data -v "$PWD":/backup debian tar czf /backup/proxium-0.2.tar.gz -C /data .
```

Back:

```bash
docker rm -f proxium
docker run --rm -v proxium:/data -v "$PWD":/backup debian sh -c "find /data -mindepth 1 -delete && tar xzf /backup/proxium-0.2.tar.gz -C /data"
docker run -d --name proxium ... ikoldakov/proxium:0.2.0
```

## From 0.1 to 0.2

0.2 shares every limit between proxy instances through Redis: connections, speed and traffic quotas. Several
instances on one database now work as one proxy. Redis is required for that, like PostgreSQL.

The database schema is the same as in 0.1.1: no migrations to wait for, and going back to 0.1.1 is just running it
again.

### What to check first

- **Redis.** The Docker image runs its own when `REDIS_URL` isn't set, nothing to do. With your own Redis it must be
  7.4 or newer, see [Supported versions](installation.md#supported-versions). Several containers on one database
  need one Redis for all of them: with the bundled one each container counts limits alone.
- **HTTP clients that check status codes.** The proxy's own refusals carry `Proxy-Status`, a 503 over limits that
  can't be checked replaces a 500, a missing outgoing IP answers 500 instead of 502. Forwarded responses say
  `Connection: close`, and requests with an unclear body end get 400. See the changelog for the full list.

### Docker image

```bash
docker pull ikoldakov/proxium:0.2.0
docker stop --time 40 proxium && docker rm proxium
docker run -d --name proxium ... ikoldakov/proxium:0.2.0
```

Use the same `-p`, `-v` and `-e` as before. The bundled Redis starts with the container and keeps nothing on disk.

With your own database add `-e REDIS_URL=...` and, if it's not in the URL, `-e REDIS_PASSWORD=...` before the
upgrade, see [Own database, Redis and secrets](installation.md#own-database-redis-and-secrets).

### Compose

The compose example of 0.2 adds a `redis` service and `REDIS_URL` with `REDIS_PASSWORD` for both containers. Take
them from [docker/compose.yaml](https://github.com/koldakov/proxium/blob/main/docker/compose.yaml) into your copy,
pin the image to `ikoldakov/proxium:0.2.0` or keep `latest`, then:

```bash
docker compose -f docker/compose.yaml pull
docker compose -f docker/compose.yaml up -d
```

Volumes keep their names: the database, the secrets and the admin's data stay.

### From source

Start Redis of a supported version, set `REDIS_URL` in `.env`, then:

```bash
git fetch --tags && git checkout v0.2.0
uv sync
uv run --env-file .env proxium-manage migrate
```

and restart the proxy and the API. Compare your `.env` with `.env.template`: new variables have working defaults,
none has to be set.

### Without downtime

From 0.1.1 the new proxy can start next to the old one, see
[Restart without downtime](proxy.md#restart-without-downtime). From 0.1.0 it's a plain restart: a 0.1.0 proxy
doesn't share its ports.

While both run, the 0.1.1 proxy counts its limits alone: a connection limit may let up to its value more in, a speed
limit give up to its rate more, a quota let through what the old proxy hasn't written to the database. It lasts
until the old proxy stops, up to `PROXY_GRACEFUL_TIMEOUT`.

### Going back

Run the 0.1.1 image or `git checkout v0.1.1` on the same database. Redis isn't used by it and may stay.
