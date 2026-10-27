"""HTTP payload serializers and FastAPI route wiring for graph endpoints."""

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from repolens.graph.models import DependencyGraph, FileDetail, ImportKind, SymbolKind
from repolens.graph.ports import GraphStore
from repolens.graph.store import GraphStoreError


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


def create_graph_router(store: GraphStore) -> APIRouter:
    """Create a FastAPI APIRouter for the graph and file-detail endpoints."""
    router = APIRouter()

    @router.get(
        "/analyses/{analysis_id}/graph",
        response_model=DependencyGraphResponse,
        summary="Get the dependency graph for an analyzed repository",
    )
    def read_graph(analysis_id: str) -> Any:
        try:
            return get_graph_response(store, analysis_id)
        except GraphStoreError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.to_dict(),
            )

    @router.get(
        "/analyses/{analysis_id}/files/{file_path:path}",
        response_model=FileDetailResponse,
        summary="Get details for a single file in an analyzed repository",
    )
    def read_file_detail(analysis_id: str, file_path: str) -> Any:
        try:
            return get_file_detail_response(store, analysis_id, file_path)
        except GraphStoreError as exc:
            return JSONResponse(
                status_code=exc.status_code,
                content=exc.to_dict(),
            )

    return router
