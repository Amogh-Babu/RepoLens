"""Classify each import as internal, external, or unresolved.

The analyzer reports imports as written and marks them all `unresolved`,
because only the whole file list tells whether `app.config` names a file in
the repository. This module builds that list and resolves each import against
it:

- `internal`: the import names a module file in the repository. A `from`
  import whose names are submodules (`from app.services import billing`)
  becomes one record per submodule so each gets its own dependency edge.
- `external`: an absolute import whose top-level package is not in the
  repository, such as `os` or `flask`.
- `unresolved`: a relative import, or an import of a package the repository
  contains, that points at no file.

Only `.py` and `.pyi` files count as modules. Both the repository root and a
top-level `src/` directory are treated as import roots.
"""

from collections.abc import Iterable, Sequence
from dataclasses import replace

from repolens.graph.models import AnalyzedFile, ImportRecord


_MODULE_SUFFIXES = (".py", ".pyi")
_SOURCE_ROOTS = ("", "src/")


def classify_imports(files: Sequence[AnalyzedFile]) -> tuple[AnalyzedFile, ...]:
    """Return `files` with every import classified against the file list."""
    index = _build_module_index(file.path for file in files)
    local_packages = frozenset(name.split(".", 1)[0] for name in index)
    return tuple(
        replace(
            file,
            imports=_classify_file_imports(file, index, local_packages),
        )
        for file in files
    )


def _build_module_index(paths: Iterable[str]) -> dict[str, str]:
    """Map every dotted module name in the repository to its file path.

    A `.py` file wins over a `.pyi` stub for the same module.
    """
    index: dict[str, str] = {}
    ordered = sorted(paths, key=lambda path: (path.endswith(".pyi"), path))
    for path in ordered:
        for module in _module_names(path):
            index.setdefault(module, path)
    return index


def _module_names(path: str) -> list[str]:
    """Return the dotted names a file can be imported as, one per source root."""
    if not path.endswith(_MODULE_SUFFIXES):
        return []
    stem = path.rsplit(".", 1)[0]
    names: list[str] = []
    for root in _SOURCE_ROOTS:
        if not stem.startswith(root):
            continue
        parts = stem[len(root) :].split("/")
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts and all(parts):
            names.append(".".join(parts))
    return names


def _classify_file_imports(
    file: AnalyzedFile,
    index: dict[str, str],
    local_packages: frozenset[str],
) -> tuple[ImportRecord, ...]:
    """Classify the imports of one file, merging repeated targets."""
    classified: list[ImportRecord] = []
    seen_targets: set[str] = set()
    for record in file.imports:
        for result in _classify_import(file.path, record, index, local_packages):
            if result.target_path is not None:
                if result.target_path in seen_targets:
                    continue
                seen_targets.add(result.target_path)
            classified.append(result)
    return tuple(classified)


def _classify_import(
    importer: str,
    record: ImportRecord,
    index: dict[str, str],
    local_packages: frozenset[str],
) -> list[ImportRecord]:
    """Resolve one import to internal targets, or classify why it has none."""
    base = _absolute_base(importer, record)
    if base is None:
        return [_unresolved(record)]

    targets: list[tuple[str, str]] = []
    names = [name for name in record.symbols if name != "*"]
    submodules_found = 0
    for name in names:
        target = index.get(f"{base}.{name}" if base else name)
        if target is not None:
            submodules_found += 1
            targets.append((_join_raw_name(record.raw_name, name), target))

    if base and (not names or submodules_found < len(names)):
        target = index.get(base)
        if target is None and record.level == 0 and not names:
            target = _longest_prefix_target(base, index)
        if target is not None:
            targets.insert(0, (record.raw_name, target))

    targets = [(raw, target) for raw, target in targets if target != importer]
    if targets:
        return [
            ImportRecord(
                raw_name=raw,
                kind="internal",
                target_path=target,
                level=record.level,
                symbols=record.symbols,
            )
            for raw, target in targets
        ]

    top_level = base.split(".", 1)[0]
    if record.level > 0 or top_level in local_packages:
        return [_unresolved(record)]
    return [
        replace(record, kind="external", target_path=None, target_package=top_level)
    ]


def _absolute_base(importer: str, record: ImportRecord) -> str | None:
    """Return the absolute dotted module an import refers to.

    A relative import is resolved from the importing file's directory. Returns
    None when the relative import climbs above the repository root.
    """
    module = record.raw_name.lstrip(".")
    if record.level == 0:
        return module
    package = importer.split("/")[:-1]
    climb = record.level - 1
    if climb > len(package):
        return None
    parts = package[: len(package) - climb]
    if module:
        parts.extend(module.split("."))
    return ".".join(parts)


def _longest_prefix_target(module: str, index: dict[str, str]) -> str | None:
    """Return the file of the longest parent package of `module` in the index."""
    parts = module.split(".")
    for end in range(len(parts) - 1, 0, -1):
        target = index.get(".".join(parts[:end]))
        if target is not None:
            return target
    return None


def _join_raw_name(raw_name: str, name: str) -> str:
    """Render `from <raw_name> import <name>` as one dotted reference."""
    if not raw_name or raw_name.endswith("."):
        return f"{raw_name}{name}"
    return f"{raw_name}.{name}"


def _unresolved(record: ImportRecord) -> ImportRecord:
    """Return the import marked as pointing at no known file."""
    return replace(record, kind="unresolved", target_path=None, target_package=None)
