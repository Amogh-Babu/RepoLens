import logging
from dataclasses import asdict

from fastapi import APIRouter, FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from fastapi.routing import APIRoute

from repolens.search import (
    AnalysisUnavailableError,
    PaginationValidationError,
    QueryValidationError,
    SearchService,
)
from repolens.search.models import MatchKind


_LOGGER = logging.getLogger(__name__)


class _SearchRoute(APIRoute):
    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def route_handler(request: Request):
            try:
                return await original_handler(request)
            except RequestValidationError:
                return _error_response(
                    422,
                    "INVALID_REQUEST",
                    "The search request contains invalid parameters.",
                    "Use a non-negative offset and a limit between 1 and 100.",
                )

        return route_handler


class MatchEvidenceResponse(BaseModel):
    kind: MatchKind
    value: str
    matched_terms: list[str]


class RankedFileResponse(BaseModel):
    path: str
    score: float
    reason: str
    matches: list[MatchEvidenceResponse]


class SearchPageResponse(BaseModel):
    results: list[RankedFileResponse]
    total: int
    offset: int
    limit: int
    has_more: bool


def create_search_router(search_service: SearchService) -> APIRouter:
    """Create the GET search route using an injected search service."""
    router = APIRouter(route_class=_SearchRoute)

    @router.get(
        "/analyses/{analysis_id}/search",
        response_model=SearchPageResponse,
        summary="Search an analyzed repository",
    )
    def search_analysis(
        analysis_id: str,
        q: str,
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=20, ge=1, le=100),
    ) -> JSONResponse | dict[str, object]:
        try:
            page = search_service.search(analysis_id, q, offset=offset, limit=limit)
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

        return asdict(page)

    return router


def install_search_api(app: FastAPI, search_service: SearchService) -> None:
    """Mount search routes without changing other routes' validation behavior."""
    app.include_router(create_search_router(search_service))


def _error_response(
    status_code: int, code: str, message: str, hint: str
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "hint": hint},
    )