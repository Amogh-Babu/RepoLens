"""HTTP routes for AI file summaries.

- `GET /ai/status`: whether summaries are on, the provider notice, and usage.
- `GET /analyses/{id}/ai-summaries/{path}`: the cached summary, if any. Never
  calls the model.
- `POST /analyses/{id}/ai-summaries/{path}`: return the cached summary or
  generate one; `?regenerate=true` replaces a cached one (rate-limited).

Errors use the API's `{code, message, hint}` shape. Routes are plain `def`s,
so FastAPI runs them on its worker threads and a model call never blocks the
event loop.
"""

import logging
from typing import Any, Literal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from repolens.ai.errors import SummaryError
from repolens.ai.models import (
    Coverage,
    KeySymbolKind,
    Relationship,
    SideEffectKind,
)
from repolens.ai.service import CodeSummaryService
from repolens.graph.endpoints import AnalysisIdPath
from repolens.graph.store import GraphStoreError


_LOGGER = logging.getLogger(__name__)

_NO_STORE = {"Cache-Control": "no-store"}


class AiUsageResponse(BaseModel):
    day: str
    modelCalls: int
    inputTokens: int
    outputTokens: int
    cacheHits: int
    cacheMisses: int
    cacheHitRate: float | None
    validationFailures: int
    providerFailures: int
    averageLatencyMs: int | None
    estimatedCostUsd: float | None


class AiStatusResponse(BaseModel):
    enabled: bool
    provider: str | None
    model: str | None
    notice: str | None
    dailyCallLimit: int | None
    usage: AiUsageResponse | None


class KeySymbolResponse(BaseModel):
    name: str
    kind: KeySymbolKind
    description: str
    line: int
    url: str


class SummaryDependencyResponse(BaseModel):
    path: str
    relationship: Relationship
    description: str


class SideEffectResponse(BaseModel):
    kind: SideEffectKind
    description: str
    startLine: int
    endLine: int
    url: str


class EvidenceResponse(BaseModel):
    startLine: int
    endLine: int
    description: str
    url: str


class CodeSummaryResponse(BaseModel):
    summary: str
    purpose: str
    responsibilities: list[str]
    keySymbols: list[KeySymbolResponse]
    dependencies: list[SummaryDependencyResponse]
    sideEffects: list[SideEffectResponse]
    uncertainties: list[str]
    evidence: list[EvidenceResponse]
    coverage: Coverage


class SummaryMetadataResponse(BaseModel):
    model: str
    promptVersion: str
    schemaVersion: str
    sourceHash: str
    generatedAt: str
    cached: bool
    cacheStatus: Literal["hit", "miss", "regenerated"]
    coverage: Coverage
    inspectedLines: list[list[int]]
    lineCount: int
    sourceUrl: str


class FileSummaryResponse(BaseModel):
    analysisId: str
    path: str
    sha: str
    status: Literal["notGenerated", "completed"]
    summary: CodeSummaryResponse | None
    metadata: SummaryMetadataResponse | None


def _error(exc: SummaryError | GraphStoreError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict(), headers=_NO_STORE)


def _unexpected(analysis_id: str) -> JSONResponse:
    _LOGGER.exception("AI summary request failed for analysis %s", analysis_id)
    return JSONResponse(
        status_code=500,
        content={
            "code": "AI_SUMMARY_FAILED",
            "message": "The AI summary could not be produced.",
            "hint": "The rest of the analysis is unaffected. Try again later.",
        },
        headers=_NO_STORE,
    )


def create_ai_router(service: CodeSummaryService) -> APIRouter:
    """Create the AI status and file-summary routes."""
    router = APIRouter()

    @router.get(
        "/ai/status",
        response_model=AiStatusResponse,
        summary="Report whether AI file summaries are enabled, and today's usage",
    )
    def ai_status() -> Any:
        return JSONResponse(content=service.status(), headers=_NO_STORE)

    @router.get(
        "/analyses/{analysis_id}/ai-summaries/{file_path:path}",
        response_model=FileSummaryResponse,
        summary="Get the cached AI summary of a file, without generating one",
    )
    def read_summary(analysis_id: AnalysisIdPath, file_path: str) -> Any:
        try:
            payload = service.get_summary(analysis_id, file_path)
        except (SummaryError, GraphStoreError) as exc:
            return _error(exc)
        except Exception:
            return _unexpected(analysis_id)
        return JSONResponse(content=payload, headers=_NO_STORE)

    @router.post(
        "/analyses/{analysis_id}/ai-summaries/{file_path:path}",
        response_model=FileSummaryResponse,
        summary="Return the cached AI summary of a file, or generate and verify one",
    )
    def create_summary(
        analysis_id: AnalysisIdPath,
        file_path: str,
        regenerate: bool = Query(default=False),
    ) -> Any:
        try:
            payload = service.generate_summary(
                analysis_id, file_path, regenerate=regenerate
            )
        except (SummaryError, GraphStoreError) as exc:
            return _error(exc)
        except Exception:
            return _unexpected(analysis_id)
        return JSONResponse(content=payload, headers=_NO_STORE)

    return router
