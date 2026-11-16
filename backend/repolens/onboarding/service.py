"""Build a deterministic starting guide from a stored dependency graph."""

from collections import Counter, defaultdict
from pathlib import PurePosixPath
from typing import Any

from repolens.graph.models import DependencyGraph
from repolens.graph.ports import GraphStore
from repolens.search.models import SearchDocument


_ENTRY_NAMES = frozenset(
    {"__main__.py", "main.py", "manage.py", "app.py", "asgi.py", "wsgi.py", "cli.py"}
)
_TEST_DIRS = frozenset({"test", "tests"})
_TOOL_DIRS = frozenset({"script", "scripts", "tool", "tools"})
_DOC_DIRS = frozenset({"doc", "docs", "documentation"})
_EXAMPLE_DIRS = frozenset({"example", "examples", "demo", "demos"})
_MIGRATION_DIRS = frozenset({"migration", "migrations"})
_CONFIG_NAMES = frozenset(
    {
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
        "tox.ini",
        "noxfile.py",
        "requirements.txt",
        "dockerfile",
        "makefile",
    }
)
_CONFIG_SUFFIXES = frozenset(
    {".ini", ".cfg", ".toml", ".yaml", ".yml", ".json", ".lock", ".env"}
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
    categories = {file.path: _category(file.path) for file in graph.files}
    dependents: dict[str, set[str]] = defaultdict(set)
    dependencies: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        dependencies[edge.source].add(edge.target)
        dependents[edge.target].add(edge.source)

    entry_paths = [
        file.path
        for file in graph.files
        if PurePosixPath(file.path).name.casefold() in _ENTRY_NAMES
    ]
    entry_paths.sort(key=lambda path: (path.casefold(), path))
    entry_points = [
        {
            "path": path,
            "reason": "Conventional application or command entry-point filename.",
            "summary": _summary(path, documents_by_path, dependents),
        }
        for path in entry_paths[:12]
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


def _category(path: str) -> str:
    parts = tuple(part.casefold() for part in PurePosixPath(path).parts)
    name = parts[-1] if parts else ""
    if _TEST_DIRS.intersection(parts[:-1]) or name.startswith("test_") or name.endswith(
        "_test.py"
    ) or name == "conftest.py":
        return "test"
    if _DOC_DIRS.intersection(parts[:-1]) or name in {
        "readme.md",
        "changelog.md",
        "contributing.md",
    }:
        return "docs"
    if _EXAMPLE_DIRS.intersection(parts[:-1]):
        return "example"
    if _TOOL_DIRS.intersection(parts[:-1]):
        return "tool"
    if _MIGRATION_DIRS.intersection(parts[:-1]):
        return "migration"
    suffix = PurePosixPath(path).suffix.casefold()
    if name in _CONFIG_NAMES or suffix in _CONFIG_SUFFIXES or name.startswith("."):
        return "config"
    return "source"


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


def _summary(
    path: str,
    documents: dict[str, SearchDocument],
    dependents: dict[str, set[str]],
) -> str:
    document = documents.get(path)
    if document is not None:
        docstring = next((line.strip() for line in document.docstrings if line.strip()), "")
        if docstring:
            return docstring.splitlines()[0][:180]
        symbol_count = len(document.symbols) + len(document.members)
    else:
        symbol_count = 0
    used_by = len(dependents[path])
    noun = "symbol" if symbol_count == 1 else "symbols"
    return f"Defines {symbol_count} {noun}; used by {used_by} files."