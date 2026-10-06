FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    XDG_STATE_HOME=/state

WORKDIR /app

# Install dependencies first so this layer is cached across source changes
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev

# Conduit ID cache; mount a volume here so it survives container restarts
VOLUME /state

# Mount config.toml at /app/config.toml and pass secrets via env vars
CMD ["uv", "run", "--no-sync", "ayalite"]
