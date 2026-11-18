"""HTTP payload serializers and FastAPI route wiring for graph endpoints."""

import hashlib
import json
from typing import Annotated, Any

from fastapi import APIRouter, Path, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from repolens.graph.models import DependencyGraph, FileDetail, ImportKind, SymbolKind
from repolens.graph.ports import GraphStore
from repolens.graph.store import GraphStoreError


# Analysis ids are generated as `analysis-<12 hex digits>`; anything that is
# not a short slug cannot name an analysis, so it is rejected before the store
# is queried.
ANALYSIS_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
ANALYSIS_ID_MAX_LENGTH = 64

AnalysisIdPath = Annotated[
    str,
    Path(
        pattern=ANALYSIS_ID_PATTERN,
        max_length=ANALYSIS_ID_MAX_LENGTH,
        description="Analysis id returned by POST /analyses.",
        examples=["analysis-3f9c2a1b7d4e"],
    ),
]


class ModuleGroupResponse(BaseModel):
    id: str
    name: str
    filePaths: list[str]


class FileNodeResponse(BaseModel):
    path: str
    module: str
    parsed: bool
    lineCount: int


class ImportEdgeResponse(BaseModel):
    source: str
    target: str


class DependencyGraphResponse(BaseModel):
    modules: list[ModuleGroupResponse]
    files: list[FileNodeResponse]
    edges: list[ImportEdgeResponse]


class SymbolInfoResponse(BaseModel):
    name: str
    kind: SymbolKind
    line: int
    sourceUrl: str


class ImportInfoResponse(BaseModel):
    rawName: str
    kind: ImportKind
    targetPath: str | None
    targetPackage: str | None


class FileDetailResponse(BaseModel):
    path: str
    module: str
    parsed: bool
    lineCount: int
    symbols: list[SymbolInfoResponse]
    imports: list[ImportInfoResponse]
    importedBy: list[str]
    sourceUrl: str


def serialize_graph(graph: DependencyGraph) -> dict[str, Any]:
    """Serialize a DependencyGraph for GET /analyses/{id}/graph."""
    return {
        "modules": [
            {
                "id": group.id,
                "name": group.name,
                "filePaths": list(group.file_paths),
            }
            for group in graph.modules
        ],
        "files": [
            {
                "path": node.path,
                "module": node.module,
                "parsed": node.parsed,
                "lineCount": node.line_count,
            }
            for node in graph.files
        ],
        "edges": [
            {
                "source": edge.source,
                "target": edge.target,
            }
            for edge in graph.edges
        ],
    }


def serialize_file_detail(detail: FileDetail) -> dict[str, Any]:
    """Serialize a FileDetail for GET /analyses/{id}/files/{path}."""
    return {
        "path": detail.path,
        "module": detail.module,
        "parsed": detail.parsed,
        "lineCount": detail.line_count,
        "symbols": [
            {
                "name": sym.name,
                "kind": sym.kind,
                "line": sym.line,
                "sourceUrl": sym.source_url,
            }
            for sym in detail.symbols
        ],
        "imports": [
            {
                "rawName": imp.raw_name,
                "kind": imp.kind,
                "targetPath": imp.target_path,
                "targetPackage": imp.target_package,
            }
            for imp in detail.imports
        ],
        "importedBy": list(detail.imported_by),
        "sourceUrl": detail.source_url,
    }


def get_graph_response(store: GraphStore, analysis_id: str) -> dict[str, Any]:
    """Fetch and serialize the dependency graph for an analysis."""
    return serialize_graph(store.get_graph(analysis_id))


def get_file_detail_response(
    store: GraphStore,
    analysis_id: str,
    file_path: str,
) -> dict[str, Any]:
    """Fetch and serialize the file detail view for a single file."""
    return serialize_file_detail(store.get_file(analysis_id, file_path))


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    """Return whether an If-None-Match header matches `etag`."""
    if not if_none_match:
        return False
    stripped_etag = etag[2:] if etag.startswith("W/") else etag
    for candidate in if_none_match.split(","):
        token = candidate.strip()
        if token == "*":
            return True
        if token.startswith("W/"):
            token = token[2:].strip()
        if token == stripped_etag:
            return True
    return False


def cached_json_response(
    request: Request,
    payload: dict[str, Any],
    etag_scope: str,
    cache_control: str = "private, immutable",
) -> Response:
    """Return a JSONResponse with ETag and Cache-Control, or 304 Not Modified.

    `cache_control` defaults to immutable, for payloads fixed by the analysis.
    A payload that can change during an analysis's lifetime passes
    `"private, no-cache"`, so the browser revalidates it with the ETag.
    """
    body_bytes = json.dumps(
        payload, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(body_bytes).hexdigest()[:16]
    etag = f'"{etag_scope}-{digest}"'
    headers = {
        "ETag": etag,
        "Cache-Control": cache_control,
    }
    if _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=payload, headers=headers)


def create_graph_router(store: GraphStore) -> APIRouter:
    """Create a FastAPI APIRouter for the graph and file-detail endpoints."""
    router = APIRouter()

    @router.get(
        "/analyses/{analysis_id}/graph",
        response_model=DependencyGraphResponse,
        summary="Get the dependency graph for an analyzed repository",
    )
    def read_graph(analysis_id: AnalysisIdPath, request: Request) -> Any:
        try:
            payload = get_graph_response(store, analysis_id)
        except GraphStoreError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.to_dict(),
            )
        return cached_json_response(request, payload, f"{analysis_id}-graph")

    @router.get(
        "/analyses/{analysis_id}/files/{file_path:path}",
        response_model=FileDetailResponse,
        summary="Get details for a single file in an analyzed repository",
    )
    def read_file_detail(
        analysis_id: AnalysisIdPath,
        file_path: str,
        request: Request,
    ) -> Any:
        try:
            payload = get_file_detail_response(store, analysis_id, file_path)
        except GraphStoreError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.to_dict(),
            )
        return cached_json_response(request, payload, f"{analysis_id}-file")

    return router
