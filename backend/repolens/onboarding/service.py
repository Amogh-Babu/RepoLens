"""Build a deterministic starting guide from a stored dependency graph."""

from collections import Counter, defaultdict
from pathlib import PurePosixPath
from typing import Any

from repolens.file_categories import file_category
from repolens.graph.models import DependencyGraph
from repolens.graph.ports import GraphStore
from repolens.search.models import SearchDocument


_ENTRY_NAMES = frozenset(
    {"__main__.py", "main.py", "manage.py", "app.py", "asgi.py", "wsgi.py", "cli.py"}
)
_APP_FACTORY_SYMBOLS = frozenset(
    {
        "create_app",
        "make_app",
        "build_app",
        "init_app",
        "get_application",
        "get_wsgi_application",
        "get_asgi_application",
    }
)
_APP_INSTANCE_SYMBOLS = frozenset({"app", "application", "server", "api", "cli"})
_MAIN_FUNCTION_SYMBOLS = frozenset({"main", "cli", "main_cli", "entrypoint"})
_FRAMEWORK_MODULES = frozenset(
    {
        "fastapi",
        "flask",
        "typer",
        "click",
        "argparse",
        "starlette",
        "uvicorn",
        "gunicorn",
        "django",
        "sanic",
        "quart",
        "litestar",
        "aiohttp",
        "tornado",
        "falcon",
        "bottle",
    }
)
class OverviewService:
    """Create a repo-specific onboarding guide without retaining source files."""

    def __init__(self, store: GraphStore) -> None:
        self._store = store

    def get_overview(self, analysis_id: str) -> dict[str, Any]:
        graph = self._store.get_graph(analysis_id)
        documents = self._store.get_search_documents(analysis_id)
        return build_overview(graph, documents)


def build_overview(
    graph: DependencyGraph,
    documents: tuple[SearchDocument, ...] | list[SearchDocument],
) -> dict[str, Any]:
    """Summarize entry points, central files, packages and a dependency-first tour."""
    documents_by_path = {document.path: document for document in documents}
    categories = {file.path: file_category(file.path) for file in graph.files}
    dependents: dict[str, set[str]] = defaultdict(set)
    dependencies: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        dependencies[edge.source].add(edge.target)
        dependents[edge.target].add(edge.source)

    entry_candidates: list[tuple[str, str]] = []
    for file in graph.files:
        if not file.parsed or categories[file.path] in ("test", "docs", "migration", "config"):
            continue
        reason = _entry_point_reason(file.path, documents_by_path.get(file.path))
        if reason is not None:
            entry_candidates.append((file.path, reason))

    entry_candidates.sort(key=lambda item: (item[0].casefold(), item[0]))
    entry_paths = [path for path, _ in entry_candidates]
    entry_points = [
        {
            "path": path,
            "reason": reason,
            "summary": _summary(path, documents_by_path, dependents),
        }
        for path, reason in entry_candidates[:12]
    ]

    core_paths = _page_rank(graph, categories)[:8]
    core_files = [
        {
            "path": path,
            "score": round(score, 6),
            "reason": f"Imported by {len(dependents[path])} analyzed files.",
            "summary": _summary(path, documents_by_path, dependents),
        }
        for path, score in core_paths
    ]

    source_modules = {
        file.module for file in graph.files if categories[file.path] == "source"
    }
    modules = {
        module.id: module
        for module in graph.modules
        if module.id in source_modules
    }
    file_modules = {file.path: file.module for file in graph.files}
    module_edges: Counter[tuple[str, str]] = Counter()
    for edge in graph.edges:
        source = file_modules.get(edge.source)
        target = file_modules.get(edge.target)
        if source in modules and target in modules and source != target:
            module_edges[(source, target)] += 1

    outgoing: dict[str, set[str]] = defaultdict(set)
    for source, target in module_edges:
        outgoing[source].add(target)
    module_layers, cyclic_modules = _module_layers(set(modules), outgoing)
    package_records = [
        {
            "id": module_id,
            "name": modules[module_id].name,
            "fileCount": len(modules[module_id].file_paths),
            "layer": module_layers.get(module_id, 0),
            "cyclic": module_id in cyclic_modules,
        }
        for module_id in sorted(modules, key=str.casefold)
    ]
    max_layer = max(module_layers.values(), default=0)
    layers = [
        {
            "depth": depth,
            "name": "Foundations" if depth == 0 else f"Layer {depth + 1}",
            "packages": [
                module_id
                for module_id in sorted(modules, key=str.casefold)
                if module_layers.get(module_id, 0) == depth
            ],
        }
        for depth in range(max_layer + 1)
    ] if modules else []
    areas = _feature_areas(graph, dependencies, dependents, categories)
    tour = _reading_tour(
        graph,
        entry_paths,
        core_paths,
        dependencies,
        documents_by_path,
        dependents,
        categories,
    )

    return {
        "entryPoints": entry_points,
        "coreFiles": core_files,
        "architecture": {
            "packages": package_records,
            "edges": [
                {"source": source, "target": target, "count": count}
                for (source, target), count in sorted(module_edges.items())
            ],
            "layers": layers,
            "hasCycles": bool(cyclic_modules),
        },
        "areas": areas,
        "tour": tour,
        "categories": [
            {"path": path, "category": categories[path]}
            for path in sorted(categories, key=str.casefold)
        ],
    }


def _entry_point_reason(
    path: str,
    document: SearchDocument | None,
) -> str | None:
    """Return why `path` is an entry point from its code markers, symbols, or name."""
    name = PurePosixPath(path).name.casefold()
    markers = set(document.entry_markers) if document is not None else set()
    symbols = {sym.casefold() for sym in document.symbols} if document is not None else set()
    framework_refs = (
        {
            ref.lstrip(".").split(".", 1)[0].casefold()
            for ref in document.references
            if ref.lstrip(".")
        }
        & _FRAMEWORK_MODULES
        if document is not None
        else set()
    )

    if "main_guard" in markers:
        return "Contains an if __name__ == '__main__' execution block."
    if "app_instance" in markers or (
        symbols & _APP_INSTANCE_SYMBOLS and framework_refs
    ):
        return "Instantiates the application or command-line runner."
    if "app_factory" in markers or (symbols & _APP_FACTORY_SYMBOLS):
        return "Defines an application factory function."
    if "cli_decorator" in markers or (
        ( "main_function" in markers or (symbols & _MAIN_FUNCTION_SYMBOLS) )
        and (name in _ENTRY_NAMES or bool(framework_refs))
    ):
        return "Defines a command-line entry point."
    if "route_decorator" in markers:
        return "Registers top-level application routes."
    if "main_function" in markers or (symbols & _MAIN_FUNCTION_SYMBOLS):
        return "Defines a command-line entry point."
    if name in _ENTRY_NAMES:
        return "Conventional application or command entry-point filename."
    return None


def _page_rank(
    graph: DependencyGraph,
    categories: dict[str, str],
) -> list[tuple[str, float]]:
    eligible = [
        file.path
        for file in graph.files
        if categories[file.path] == "source" and file.parsed
    ]
    if not eligible:
        eligible = [file.path for file in graph.files if file.parsed]
    if not eligible:
        return []

    nodes = set(eligible)
    outgoing: dict[str, set[str]] = defaultdict(set)
    incoming: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        if edge.source in nodes and edge.target in nodes:
            outgoing[edge.source].add(edge.target)
            incoming[edge.target].add(edge.source)

    count = len(eligible)
    scores = {path: 1 / count for path in eligible}
    damping = 0.85
    for _ in range(40):
        sink_score = sum(scores[path] for path in eligible if not outgoing[path])
        next_scores = {
            path: (1 - damping) / count + damping * sink_score / count
            for path in eligible
        }
        for path in eligible:
            for importer in incoming[path]:
                next_scores[path] += damping * scores[importer] / len(outgoing[importer])
        scores = next_scores

    return sorted(scores.items(), key=lambda item: (-item[1], item[0].casefold()))


def _module_layers(
    modules: set[str], outgoing: dict[str, set[str]]
) -> tuple[dict[str, int], set[str]]:
    remaining = set(modules)
    layers: dict[str, int] = {}
    cyclic: set[str] = set()
    while remaining:
        ready = {
            module
            for module in remaining
            if not (outgoing[module] & remaining)
        }
        if not ready:
            ready = remaining.copy()
            cyclic.update(ready)
        for module in ready:
            dependencies = outgoing[module] & layers.keys()
            layers[module] = max((layers[item] + 1 for item in dependencies), default=0)
        remaining.difference_update(ready)
    return layers, cyclic


def _feature_areas(
    graph: DependencyGraph,
    dependencies: dict[str, set[str]],
    dependents: dict[str, set[str]],
    categories: dict[str, str],
) -> list[dict[str, Any]]:
    nodes = {
        file.path
        for file in graph.files
        if categories[file.path] == "source"
    }
    labels = {path: path for path in nodes}
    for _ in range(8):
        updated = dict(labels)
        changed = False
        for path in sorted(nodes, key=str.casefold):
            neighbors = (dependencies[path] | dependents[path]) & nodes
            if not neighbors:
                continue
            counts = Counter(labels[neighbor] for neighbor in neighbors)
            label = min(counts, key=lambda value: (-counts[value], value.casefold()))
            if label != labels[path]:
                updated[path] = label
                changed = True
        labels = updated
        if not changed:
            break

    groups: dict[str, list[str]] = defaultdict(list)
    for path, label in labels.items():
        groups[label].append(path)
    areas = []
    for paths in groups.values():
        paths.sort(key=str.casefold)
        name = _area_name(paths)
        areas.append(
            {
                "id": paths[0],
                "name": name,
                "files": paths,
                "summary": f"{len(paths)} files connected by internal imports.",
            }
        )
    return sorted(areas, key=lambda area: (area["name"].casefold(), area["id"]))


def _area_name(paths: list[str]) -> str:
    directories = [PurePosixPath(path).parent.as_posix() for path in paths]
    parts = [PurePosixPath(path).parts for path in directories]
    common: list[str] = []
    for tokens in zip(*parts):
        if len(set(tokens)) != 1:
            break
        common.append(tokens[0])
    return "/".join(common) if common else PurePosixPath(paths[0]).stem


def _reading_tour(
    graph: DependencyGraph,
    entry_paths: list[str],
    core_paths: list[tuple[str, float]],
    dependencies: dict[str, set[str]],
    documents: dict[str, SearchDocument],
    dependents: dict[str, set[str]],
    categories: dict[str, str],
) -> list[dict[str, str]]:
    ordered: list[str] = []
    visited: set[str] = set()

    def visit(path: str) -> None:
        if path in visited:
            return
        visited.add(path)
        for dependency in sorted(dependencies[path], key=str.casefold):
            visit(dependency)
        ordered.append(path)

    for path in entry_paths:
        visit(path)
    for path, _ in core_paths:
        if len(ordered) >= 12:
            break
        visit(path)

    target_count = min(12, max(8, len(graph.files)))
    for file in sorted(graph.files, key=lambda item: item.path.casefold()):
        if len(ordered) >= target_count:
            break
        if categories.get(file.path) == "test":
            continue
        visit(file.path)

    entry_set = set(entry_paths)
    return [
        {
            "path": path,
            "reason": (
                "Start here: this is a conventional application entry point."
                if path in entry_set
                else f"Read before its callers: {len(dependents[path])} files import it."
                if dependents[path]
                else "A central source file that anchors the repository structure."
            ),
            "summary": _summary(path, documents, dependents),
        }
        for path in ordered[:12]
    ]


def first_docstring_line(document: SearchDocument) -> str:
    """Return the first line of a file's first non-empty docstring, or ''."""
    docstring = next((line.strip() for line in document.docstrings if line.strip()), "")
    return docstring.splitlines()[0][:180] if docstring else ""


def _summary(
    path: str,
    documents: dict[str, SearchDocument],
    dependents: dict[str, set[str]],
) -> str:
    document = documents.get(path)
    if document is not None:
        docstring = first_docstring_line(document)
        if docstring:
            return docstring
        symbol_count = len(document.symbols) + len(document.members)
    else:
        symbol_count = 0
    used_by = len(dependents[path])
    noun = "symbol" if symbol_count == 1 else "symbols"
    return f"Defines {symbol_count} {noun}; used by {used_by} files."