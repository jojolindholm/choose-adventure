# Runtime image for saga-server (game engine + per-player SQLite + LLM client).
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Install project + deps (no dev group) in one sync; source is copied first so
# the project itself is installed here too.
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

EXPOSE 8787

# --no-sync: the venv is already up to date; `uv run` would otherwise re-sync
# and pull the dev group into the image at container start.
ENV CYA_DATA_DIR=/data
CMD ["uv", "run", "--no-sync", "saga-server"]
