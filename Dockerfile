# syntax=docker/dockerfile:1

# All in one image: the proxy, the API, the admin UI on Caddy and a bundled PostgreSQL, run by s6-overlay.
# Usage: README, Containerization. Start scripts: docker/rootfs.

ARG S6_OVERLAY_VERSION=3.2.1.0
ARG POSTGRES_VERSION=17


# The build platform: the output is static files, the same for any architecture, built once without emulation.
FROM --platform=$BUILDPLATFORM node:24-alpine AS admin

WORKDIR /app

COPY fsrc/package.json fsrc/package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci

COPY fsrc ./

# Empty: Caddy serves the API on the same origin, requests go to /api/... as is.
ENV VITE_API_URL=""

RUN npm run build


FROM python:3.14-slim AS app

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# Dependencies first: they change less often than the code, so this layer stays cached.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-dev --no-install-project

COPY pyproject.toml uv.lock README.md LICENSE.md ./
COPY src ./src

# Not editable: the venv holds the package itself, src isn't copied to the final image.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable


# The build platform: it only unpacks archives, TARGETARCH picks the one for the image.
FROM --platform=$BUILDPLATFORM python:3.14-slim AS s6

ARG S6_OVERLAY_VERSION
ARG TARGETARCH

RUN apt-get update \
    && apt-get install --yes --no-install-recommends xz-utils \
    && rm -rf /var/lib/apt/lists/*

ADD https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-noarch.tar.xz \
    https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-x86_64.tar.xz \
    https://github.com/just-containers/s6-overlay/releases/download/v${S6_OVERLAY_VERSION}/s6-overlay-aarch64.tar.xz \
    /tmp/

RUN case "$TARGETARCH" in \
        amd64) arch=x86_64 ;; \
        arm64) arch=aarch64 ;; \
        *) echo "Unsupported architecture: $TARGETARCH" >&2; exit 1 ;; \
    esac \
    && mkdir /s6 \
    && tar -C /s6 -Jxpf /tmp/s6-overlay-noarch.tar.xz \
    && tar -C /s6 -Jxpf "/tmp/s6-overlay-$arch.tar.xz"


FROM python:3.14-slim

ARG POSTGRES_VERSION
# No prompts from apt; ARG, not ENV: only for the build.
ARG DEBIAN_FRONTEND=noninteractive

# The package would create its own cluster: the bundled one is made on the first start, in the volume.
RUN mkdir -p /etc/postgresql-common \
    && echo "create_main_cluster = false" > /etc/postgresql-common/createcluster.conf \
    && apt-get update \
    && apt-get install --yes --no-install-recommends \
        "postgresql-$POSTGRES_VERSION" \
        # Time zones for the schedule condition of policies.
        tzdata \
        libcap2-bin \
    && rm -rf /var/lib/apt/lists/*

# Not root, yet on ports 80 and 443.
COPY --from=caddy:2 /usr/bin/caddy /usr/bin/caddy
RUN setcap cap_net_bind_service=+ep /usr/bin/caddy

# A fixed UID: files mounted into the container, e.g. the admin certificate, must be readable by it.
# Not --system: system accounts are meant to be below 1000.
RUN groupadd --gid 10001 proxium \
    && useradd --uid 10001 --gid proxium --no-create-home proxium

COPY --from=s6 /s6/ /
COPY --from=app /app/.venv /app/.venv
COPY --from=admin /app/dist /srv/admin
COPY docker/rootfs/ /

# /usr/local/bin first: its proxium-manage wraps the one in the venv for `docker exec`.
ENV PATH="/usr/local/bin:/app/.venv/bin:/usr/lib/postgresql/$POSTGRES_VERSION/bin:/command:$PATH" \
    PYTHONUNBUFFERED=1 \
    PGDATA=/var/lib/proxium/postgres \
    PROXY_LISTEN=0.0.0.0:8080 \
    # A failed start step, e.g. migrations, stops the container instead of running half of it.
    S6_BEHAVIOUR_IF_STAGE2_FAILS=2 \
    # Start steps wait as long as they need: migrations wait for the database themselves.
    S6_CMD_WAIT_FOR_SERVICES_MAXTIME=0 \
    # Open proxy connections get PROXY_GRACEFUL_TIMEOUT (30s by default) to finish on stop.
    S6_SERVICES_GRACETIME=35000

VOLUME /var/lib/proxium

EXPOSE 80 443 8080

ENTRYPOINT ["/init"]
