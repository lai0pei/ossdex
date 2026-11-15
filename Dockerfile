# Image for `ossdex-server` (web UI, API, MCP). The SQLite database is mounted from the host.
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages packages
RUN uv sync --frozen --package ossdex-server --no-dev
COPY --from=web /web/dist web/dist
ENV PATH="/app/.venv/bin:$PATH" OSSDEX_HOME=/app
