"""FastAPI application matching the RepoLens frontend API contract."""

import hashlib
import logging
import re
from typing import Any, Literal, Protocol
from urllib.parse import urlparse
import uuid

from fastapi import APIRouter, FastAPI, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel

from repolens.graph.endpoints import (
    DependencyGraphResponse,
    FileDetailResponse,
    create_graph_router,
)
from repolens.graph.models import (
    AnalysisRecord,
    AnalysisStage,
    AnalysisStatus,
)
from repolens.graph.store import (
    GraphStoreError,
    SqliteGraphStore,
    normalize_repo_url,
)
from repolens.search import (
    AnalysisUnavailableError,
    PaginationValidationError,
    QueryValidationError,
    SearchService,
)


_LOGGER = logging.getLogger(__name__)

_GITHUB_PATH_RE = re.compile(r"^/([^/\s]+)/([^/\s]+)/?$")
_FULL_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)

FrontendMatchKind = Literal["filename", "symbol", "import", "comment"]


class ApiErrorBodyResponse(BaseModel):
    code: str
    message: str
    hint: str | None = None


class StartAnalysisRequestModel(BaseModel):
    url: str
    ref: str | None = None


class StartAnalysisResponseModel(BaseModel):
    analysisId: str
    sha: str
    status: AnalysisStatus


class AnalysisSummaryResponse(BaseModel):
    filesAnalyzed: int
    filesExcluded: int
    filesUnparsed: int


class AnalysisResponse(BaseModel):
    analysisId: str
    repoUrl: str
    ref: str | None
    sha: str
    status: AnalysisStatus
    stage: AnalysisStage | None
    summary: AnalysisSummaryResponse | None
    fromCache: bool
    createdAt: str
    expiresAt: str
    error: ApiErrorBodyResponse | None


class SearchMatchResponse(BaseModel):
    kind: FrontendMatchKind
    text: str
    line: int | None
    value: str
    matched_terms: list[str]


class RankedFileContractResponse(BaseModel):
    position: int
    path: str
    score: float
    reason: str
    matches: list[SearchMatchResponse]


class SearchContractResponse(BaseModel):
    query: str
    total: int
    offset: int
    limit: int
    has_more: bool
    results: list[RankedFileContractResponse]


class AnalysisRunner(Protocol):
    """Protocol for starting or resolving a repository analysis."""

    def start(
        self,
        store: SqliteGraphStore,
        repo_url: str,
        ref: str | None,
    ) -> dict[str, Any]:
        """Start or reuse an analysis and return {analysisId, sha, status}."""
        ...


class DefaultAnalysisRunner:
    """Default runner that reuses cached analyses or registers a queued analysis."""

    def start(
        self,
        store: SqliteGraphStore,
        repo_url: str,
        ref: str | None,
    ) -> dict[str, Any]:
        clean_ref = ref.strip() if ref and ref.strip() else None
        if clean_ref and _FULL_SHA_RE.match(clean_ref):
            sha = clean_ref.lower()
        else:
            digest = hashlib.sha1(
                f"{repo_url}@{clean_ref or 'HEAD'}".encode("utf-8")
            ).hexdigest()
            sha = digest

        cached = store.find_cached_analysis(repo_url, sha)
        if cached is not None:
            return {
                "analysisId": str(cached["id"]),
                "sha": str(cached["sha"]),
                "status": str(cached["status"]),
            }

        analysis_id = f"analysis-{uuid.uuid4().hex[:12]}"
        record = AnalysisRecord(
            analysis_id=analysis_id,
            repo=repo_url,
            ref=clean_ref,
            sha=sha,
            status="queued",
            stage="resolving",
            from_cache=False,
        )
        store.save(record)
        return {
            "analysisId": analysis_id,
            "sha": sha,
            "status": "queued",
        }


def validate_github_repo_url(raw_url: str) -> str:
    """Validate and normalize a public GitHub repository URL."""
    trimmed = raw_url.strip()
    if not trimmed:
        raise GraphStoreError(
            code="INVALID_URL",
            message="Enter a GitHub repository URL.",
            hint="Use the format https://github.com/<owner>/<repo>.",
            status_code=400,
        )

    parsed = urlparse(trimmed)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise GraphStoreError(
            code="INVALID_URL",
            message="This is not a valid repository URL.",
            hint="Use the format https://github.com/<owner>/<repo>.",
            status_code=400,
        )

    host = parsed.netloc.lower()
    if host not in ("github.com", "www.github.com"):
        raise GraphStoreError(
            code="UNSUPPORTED_HOST",
            message="Only GitHub repositories are supported.",
            hint="Use a public GitHub repository URL: https://github.com/<owner>/<repo>.",
            status_code=400,
        )

    path = parsed.path.rstrip("/")
    if path.endswith(".git"):
        path = path[:-4]

    match = _GITHUB_PATH_RE.match(path)
    if match is None:
        raise GraphStoreError(
            code="INVALID_URL",
            message="This is not a GitHub repository URL.",
            hint="Use the format https://github.com/<owner>/<repo>.",
            status_code=400,
        )

    owner, repo = match.group(1), match.group(2)
    return normalize_repo_url(f"https://github.com/{owner}/{repo}")


class _ContractRoute(APIRoute):
    """Route class that converts FastAPI request validation errors into {code, message, hint}."""

    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def route_handler(request: Request):
            try:
                return await original_handler(request)
            except RequestValidationError:
                if request.url.path.endswith("/search"):
                    return _error_response(
                        422,
                        "INVALID_REQUEST",
                        "The search request contains invalid parameters.",
                        "Use a non-negative offset and a limit between 1 and 100.",
                    )
                return _error_response(
                    400,
                    "INVALID_URL",
                    "The request body is invalid.",
                    "Provide a JSON object with a valid GitHub repository URL.",
                )

        return route_handler


def create_analysis_router(
    store: SqliteGraphStore,
    runner: AnalysisRunner | None = None,
) -> APIRouter:
    """Create routes for starting, polling, cancelling, and searching analyses."""
    active_runner = runner or DefaultAnalysisRunner()
    search_service = SearchService(store)
    router = APIRouter(route_class=_ContractRoute)

    @router.post(
        "/analyses",
        response_model=StartAnalysisResponseModel,
        summary="Start a new repository analysis or reuse a cached one",
    )
    def start_analysis(payload: StartAnalysisRequestModel) -> Any:
        try:
            repo_url = validate_github_repo_url(payload.url)
            return active_runner.start(store, repo_url, payload.ref)
        except GraphStoreError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.to_dict(),
            )

    @router.get(
        "/analyses/{analysis_id}",
        response_model=AnalysisResponse,
        summary="Get the status, stage, and summary of an analysis",
    )
    def get_analysis(analysis_id: str) -> Any:
        try:
            return store.get_analysis(analysis_id)
        except GraphStoreError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.to_dict(),
            )

    @router.delete(
        "/analyses/{analysis_id}",
        status_code=204,
        summary="Cancel a queued or running analysis",
    )
    def cancel_analysis(analysis_id: str) -> Response:
        try:
            store.cancel_analysis(analysis_id)
            return Response(status_code=204)
        except GraphStoreError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.to_dict(),
            )

    @router.get(
        "/analyses/{analysis_id}/search",
        response_model=SearchContractResponse,
        summary="Search an analyzed repository and return a ranked reading list",
    )
    def search_analysis(
        analysis_id: str,
        q: str,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> Any:
        try:
            page = search_service.search(
                analysis_id, q, offset=offset, limit=limit
            )
        except QueryValidationError as error:
            return _error_response(
                422,
                "INVALID_QUERY",
                str(error),
                "Enter a keyword or phrase of at most 200 characters.",
            )
        except PaginationValidationError as error:
            return _error_response(
                422,
                "INVALID_PAGINATION",
                str(error),
                "Use a non-negative offset and a limit between 1 and 100.",
            )
        except GraphStoreError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.to_dict(),
            )
        except AnalysisUnavailableError:
            return _error_response(
                404,
                "ANALYSIS_UNAVAILABLE",
                "This analysis is missing or has expired.",
                "Re-analyze the repository before searching it.",
            )
        except Exception:
            _LOGGER.exception("Search failed for analysis %s", analysis_id)
            return _error_response(
                500,
                "SEARCH_FAILED",
                "The search could not be completed.",
                "Retry the search. If the problem continues, re-analyze the repository.",
            )

        results: list[dict[str, Any]] = []
        for idx, ranked in enumerate(page.results):
            line_lookup = store.get_file_match_lines(analysis_id, ranked.path)
            matches: list[dict[str, Any]] = []
            for m in ranked.matches:
                frontend_kind: FrontendMatchKind = (
                    "import" if m.kind == "reference" else m.kind
                )
                line = line_lookup.get((m.kind, m.value))
                matches.append(
                    {
                        "kind": frontend_kind,
                        "text": m.value,
                        "line": line,
                        "value": m.value,
                        "matched_terms": list(m.matched_terms),
                    }
                )
            results.append(
                {
                    "position": page.offset + idx + 1,
                    "path": ranked.path,
                    "score": ranked.score,
                    "reason": ranked.reason,
                    "matches": matches,
                }
            )

        return {
            "query": q.strip(),
            "total": page.total,
            "offset": page.offset,
            "limit": page.limit,
            "has_more": page.has_more,
            "results": results,
        }

    return router


def create_app(
    store: SqliteGraphStore | None = None,
    runner: AnalysisRunner | None = None,
) -> FastAPI:
    """Create the RepoLens FastAPI application matching the frontend contract."""
    graph_store = store if store is not None else SqliteGraphStore()

    application = FastAPI(
        title="RepoLens API",
        version="0.1.0",
        description="Architectural discovery and feature search API for Python repositories.",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    application.state.store = graph_store
    application.include_router(create_analysis_router(graph_store, runner=runner))
    application.include_router(create_graph_router(graph_store))

    return application


def _error_response(
    status_code: int,
    code: str,
    message: str,
    hint: str | None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "hint": hint},
    )


app = create_app()
