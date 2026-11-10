"""Production entry point: the API under `/api` and the frontend at `/`.

This is what the Docker image runs:

    uvicorn repolens.api.server:app --app-dir backend

One process serves both halves from the same origin, so the browser needs no
CORS rules and the frontend's default API base URL (`/api`) just works. In
development, `repolens.api.app:app` is still the API on its own, behind the
Vite dev server's `/api` proxy.

Configuration comes from the environment:

- `REPOLENS_DB_PATH`: SQLite file for the graph store. Unset or empty keeps
  it in memory, so analyses vanish on restart. The image sets
  `/data/repolens.db` on a volume.
- `REPOLENS_FRONTEND_DIR`: the built frontend (`frontend/dist`). Unset or
  missing serves the API only.
- `REPOLENS_CORS_ORIGINS`: comma-separated origins allowed to call the API
  from elsewhere. Empty by default.
- `GITHUB_TOKEN`: optional, raises GitHub's API rate limit (see the
  ingestion docs).
"""

from collections.abc import Mapping
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from repolens.api.app import AnalysisRunner, create_app
from repolens.graph.store import SqliteGraphStore
from repolens.pipeline import PipelineAnalysisRunner


API_PREFIX = "/api"

# Vite fingerprints everything under assets/, so a file there never changes;
# index.html must be revalidated so a new deploy is picked up at once.
_IMMUTABLE = "public, max-age=31536000, immutable"
_REVALIDATE = "no-cache"


class _FingerprintedFiles(StaticFiles):
    """Serve build assets with a long-lived cache header."""

    async def get_response(self, path, scope):  # type: ignore[override]
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = _IMMUTABLE
        return response


def create_server(
    *,
    store: SqliteGraphStore,
    runner: AnalysisRunner | None = None,
    frontend_dir: Path | None = None,
    cors_origins: tuple[str, ...] = (),
) -> FastAPI:
    """Mount the API under `/api` and, if built, the frontend at `/`.

    Any path outside `/api` that is not a file in the build gets
    `index.html`, so the frontend's client-side routes (such as
    `/analysis/<id>`) load on a refresh or a shared link.
    """
    server = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    server.mount(
        API_PREFIX,
        create_app(store, runner, cors_origins=cors_origins),
        name="api",
    )

    index = frontend_dir / "index.html" if frontend_dir is not None else None
    if frontend_dir is None or index is None or not index.is_file():
        return server

    root = frontend_dir.resolve()
    assets = root / "assets"
    if assets.is_dir():
        server.mount("/assets", _FingerprintedFiles(directory=assets), name="assets")

    @server.get("/{path:path}", include_in_schema=False)
    def frontend(path: str) -> FileResponse:
        if path == API_PREFIX.strip("/") or path.startswith(API_PREFIX.strip("/") + "/"):
            raise HTTPException(status_code=404)
        candidate = (root / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": _REVALIDATE})

    return server


def create_server_from_environment(
    environ: Mapping[str, str] = os.environ,
    runner: AnalysisRunner | None = None,
) -> FastAPI:
    """Build the production server from `REPOLENS_*` environment variables."""
    db_path = environ.get("REPOLENS_DB_PATH", "").strip() or ":memory:"
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    frontend = environ.get("REPOLENS_FRONTEND_DIR", "").strip()
    origins = tuple(
        origin.strip()
        for origin in environ.get("REPOLENS_CORS_ORIGINS", "").split(",")
        if origin.strip()
    )
    return create_server(
        store=SqliteGraphStore(db_path),
        runner=runner if runner is not None else PipelineAnalysisRunner(),
        frontend_dir=Path(frontend) if frontend else None,
        cors_origins=origins,
    )


app = create_server_from_environment()
