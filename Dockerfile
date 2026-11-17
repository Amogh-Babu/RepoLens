# syntax=docker/dockerfile:1
#
# RepoLens in one image: the React frontend is built in a Node stage, and the
# FastAPI backend serves both it and the API (under /api) on port 8000.
#
#   docker compose up                      # build and run (see compose.yaml)
#   docker build -t repolens .             # just build the runtime image
#   docker build --target test .           # run the whole backend suite
#
# Every base image and tool is pinned to an exact version, and Python
# dependencies come from backend/uv.lock, so the image is the same on every
# machine. Nothing needs to be installed on the host except Docker.

# --- Frontend: build the static bundle ---------------------------------------
FROM node:22.23.3-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# --- Backend base: the pinned interpreter plus uv ----------------------------
FROM python:3.12.15-slim-bookworm AS backend-base
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    REPOLENS_EMBEDDING_CACHE=/opt/fastembed \
    PATH="/opt/venv/bin:${PATH}"
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --locked --no-dev \
    && python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5', cache_dir='/opt/fastembed')"

# --- Test: the backend suite, including the end-to-end reference run --------
# The search-precision benchmark lists files with `git ls-files`, and the
# image has no git checkout; CI runs it outside the image instead.
FROM backend-base AS test
RUN uv sync --locked
COPY backend/ ./
RUN python -m pytest -q --ignore=tests/test_search_precision.py

# --- Runtime (default target) ------------------------------------------------
FROM backend-base AS runtime
COPY backend/repolens ./repolens
COPY --from=frontend /app/frontend/dist /app/frontend/dist
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin repolens \
    && mkdir -p /data \
    && chown repolens /data
USER repolens
ENV REPOLENS_DB_PATH=/data/repolens.db \
    REPOLENS_FRONTEND_DIR=/app/frontend/dist \
    REPOLENS_EMBEDDING_CACHE=/opt/fastembed
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]
CMD ["uvicorn", "repolens.api.server:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
