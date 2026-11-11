"""Resolve imports to repository files and label them internal or external.

Classification is the pipeline stage between parsing and storing: analyzers
report imports exactly as written and mark them all `unresolved`, this module
decides which of them point at another file in the repository, and only the
resolved kind and target are persisted. It works on the storable records
`repolens.analysis.adapter` produces, because resolving one import needs the
whole file list.

- `internal`: the reference names a module file in the repository. A `from`
  import whose names are submodules (`from app.services import billing`)
  becomes one record per submodule, so each gets its own dependency edge.
- `external`: an absolute import whose top-level package the repository does
  not contain, such as `os` or `flask`.
- `unresolved`: a relative import, or an import of a package the repository
  does contain, that points at no file. An ambiguous reference is left
  unresolved rather than guessed: a wrong edge misleads the dependency map,
  while a missing one only leaves it quiet.

Nothing here reads the repository or imports any analyzed module: resolution is
pure path arithmetic over the analyzed file paths, following Python's module
layout rules (dotted names, `__init__.py` packages, `.pyi` stubs). Another
language maps onto `ImportRecord` the same way but has its own layout rules,
so it would bring its own resolver.
"""

import dataclasses
from collections.abc import Iterable

from repolens.graph.models import AnalyzedFile, ImportRecord


# How a dotted module name can appear on disk. Packages come first because
# Python's import system prefers a package directory to a same-named module,
# and a module wins over its own type stub.
MODULE_SUFFIXES = ("/__init__.py", "/__init__.pyi", ".py", ".pyi")

# File names that make the directory holding them a package rather than a
# plain directory, so it cannot also be a source root.
PACKAGE_MARKER_NAMES = frozenset({"__init__.py", "__init__.pyi"})

_STAR_IMPORT = "*"


class ImportClassifier:
    """Classify a repository's imports against the files it actually contains.

    Build one classifier per analysis and reuse it for every file: the source
    roots and the file index are derived once from `file_paths`, which are the
    POSIX repository-relative paths of the analyzed files.
    """

    def __init__(self, file_paths: Iterable[str]) -> None:
        self._files = frozenset(file_paths)
        self._directories = _directories_of(self._files)
        self._source_roots = _infer_source_roots(self._files, self._directories)
        self._deepest_first = tuple(
            sorted(self._source_roots, key=lambda root: (-_depth(root), root))
        )
        self._roots_by_directory: dict[str, tuple[str, ...]] = {}

    @property
    def source_roots(self) -> tuple[str, ...]:
        """Return the directories absolute imports are resolved against.

        The repository root is always one. Any other directory that is not
        itself inside a package is one too, so a `src/` or `backend/` layout
        resolves `app.config` to `src/app/config.py` rather than reporting an
        external `app` package.
        """
        return self._source_roots

    def classify(
        self, source_path: str, imported: ImportRecord
    ) -> tuple[ImportRecord, ...]:
        """Resolve one import into the records that describe what it reaches.

        `source_path` is the repository path of the file the import was
        written in; a relative import resolves against that file's package.
        One statement can reach several files — `from pkg import a, b` names
        two submodules — so this returns one record per resolved target, and
        exactly one `external` or `unresolved` record when it reaches none.
        """
        if imported.level > 0:
            base = _package_base(source_path, imported.level)
            if base is None:
                return (_unresolved(imported),)
            return self._records_in(base, source_path, imported) or (
                _unresolved(imported),
            )

        module = imported.raw_name
        directory = source_path.rpartition("/")[0]
        for root in self._roots_for(source_path):
            records = self._records_in(root, source_path, imported)
            if records:
                return records
            if _contains(root, directory) and self._owns(root, module):
                break

        package = self._external_package(source_path, module)
        if package is None:
            return (_unresolved(imported),)
        return (
            ImportRecord(
                raw_name=imported.raw_name,
                kind="external",
                target_package=package,
                level=imported.level,
                symbols=imported.symbols,
            ),
        )

    def classify_file(self, file: AnalyzedFile) -> AnalyzedFile:
        """Return `file` with every one of its imports classified.

        Repeated references to one target are merged, so a file that reaches
        `app/services/billing.py` both as `from app.services import billing`
        and as `from app.services.billing import InvoiceCalculator` keeps one
        record for it. A file that did not parse reports no imports, so it
        passes through unchanged instead of failing the stage.
        """
        if not file.imports:
            return file

        classified: list[ImportRecord] = []
        seen_targets: set[str] = set()
        for imported in file.imports:
            for record in self.classify(file.path, imported):
                if record.target_path is not None:
                    if record.target_path in seen_targets:
                        continue
                    seen_targets.add(record.target_path)
                classified.append(record)

        return dataclasses.replace(file, imports=tuple(classified))

    def classify_files(
        self, files: Iterable[AnalyzedFile]
    ) -> tuple[AnalyzedFile, ...]:
        """Return every file with its imports classified, in the given order."""
        return tuple(self.classify_file(file) for file in files)

    def _records_in(
        self, root: str, source_path: str, imported: ImportRecord
    ) -> tuple[ImportRecord, ...]:
        """Resolve one import below `root` into internal records, if any.

        The dotted module is resolved first, because only a package can hold
        submodules: `from app.config import DEFAULT_TIMEOUT` resolves to the
        `app/config.py` module and its trailing name stays an attribute, even
        where a directory holds an `app/config/DEFAULT_TIMEOUT.py`.

        When the module is a package, or names a directory with no module file
        of its own (a namespace package, which includes the empty module of
        `from . import config`), each imported name is tried as a submodule,
        so `from . import config` reaches the sibling `config.py` and
        `from app.services import billing` reaches `app/services/billing.py`
        rather than only the package that re-exports it. The module itself is
        reported as well unless every imported name turned out to be a
        submodule. `'*'` is never resolved as a submodule: a star import is
        resolved from its module alone.

        A file never depends on itself, so a target that lands back on
        `source_path` is dropped.
        """
        module = imported.raw_name[imported.level :]
        base_target = self._resolve_module(root, module)

        names = tuple(name for name in imported.symbols if name != _STAR_IMPORT)
        submodules: list[tuple[str, str]] = []
        if base_target is None or _is_package_file(base_target):
            for name in names:
                target = self._resolve_module(root, _join_module(module, name))
                if target is not None and target != source_path:
                    submodules.append(
                        (_join_raw_name(imported.raw_name, name), target)
                    )

        if base_target is None and imported.level == 0 and not names:
            base_target = self._closest_parent_package(root, module)

        resolved: list[tuple[str, str]] = []
        keeps_base = not names or len(submodules) < len(names)
        if keeps_base and base_target is not None and base_target != source_path:
            resolved.append((imported.raw_name, base_target))
        resolved.extend(submodules)

        return tuple(
            ImportRecord(
                raw_name=raw_name,
                kind="internal",
                target_path=target,
                level=imported.level,
                symbols=imported.symbols,
            )
            for raw_name, target in resolved
        )

    def _resolve_module(self, root: str, module: str) -> str | None:
        """Return the file a dotted module name maps to below `root`."""
        base = "/".join(part for part in (root, module.replace(".", "/")) if part)
        if not base:
            return None
        for suffix in MODULE_SUFFIXES:
            candidate = base + suffix
            if candidate in self._files:
                return candidate
        return None

    def _closest_parent_package(self, root: str, module: str) -> str | None:
        """Return the file of the nearest parent package of `module`.

        `import pkg.generated.models` runs `pkg/__init__.py` even when the
        named module is not in the analysis, which is what happens when the
        ingestion filter excluded it. The nearest package that *is* in the
        analysis is the most precise true target for that dependency.
        """
        parts = module.split(".")
        for end in range(len(parts) - 1, 0, -1):
            target = self._resolve_module(root, ".".join(parts[:end]))
            if target is not None:
                return target
        return None

    def _external_package(self, source_path: str, module: str) -> str | None:
        """Return the distribution an unresolved absolute import comes from.

        Only the top-level name is reported, so `os.path` is `os`. A reference
        whose top-level name *is* a repository package is reported as no
        package at all: the import points inside the repository, the named
        module is simply missing, which is `unresolved` rather than a
        third-party dependency.
        """
        if not module:
            return None
        for root in self._roots_for(source_path):
            if self._owns(root, module):
                return None
        return module.split(".")[0]

    def _owns(self, root: str, module: str) -> bool:
        """Return whether `root` holds the top-level package `module` names.

        A namespace package counts, so a bare `service_b/app/` directory owns
        `app` for the files inside it even with no `__init__.py`.
        """
        top_level = module.split(".")[0]
        if not top_level:
            return False
        if self._resolve_module(root, top_level) is not None:
            return True
        return "/".join(part for part in (root, top_level) if part) in self._directories

    def _roots_for(self, source_path: str) -> tuple[str, ...]:
        """Return the source roots to try for a file, nearest root first.

        The roots containing the importing file come first, deepest first,
        the way the nearest package directory on `sys.path` wins at runtime,
        and the roots outside its tree follow, the way an installed
        distribution is still importable from a `tests/` directory.

        Search stops at the first containing root that owns the top-level
        package being imported, so two copies of one package in a monorepo
        stay apart: a file in `service_b/` resolves `app.config` in its own
        tree, and a module only `service_a/` has is missing rather than a
        cross-checkout dependency Python would never take.
        """
        directory = source_path.rpartition("/")[0]
        cached = self._roots_by_directory.get(directory)
        if cached is None:
            cached = tuple(
                root for root in self._deepest_first if _contains(root, directory)
            ) + tuple(
                root
                for root in reversed(self._deepest_first)
                if not _contains(root, directory)
            )
            self._roots_by_directory[directory] = cached
        return cached


def classify_imports(files: Iterable[AnalyzedFile]) -> tuple[AnalyzedFile, ...]:
    """Classify every import in a converted analysis against those files.

    This is the classifying stage in one call: the analyzed files are the only
    files an import can resolve to, because they are the only ones the store
    can point an internal import at.
    """
    analyzed = tuple(files)
    return ImportClassifier(file.path for file in analyzed).classify_files(analyzed)


def _unresolved(imported: ImportRecord) -> ImportRecord:
    """Return the import marked as pointing at no known file."""
    return ImportRecord(
        raw_name=imported.raw_name,
        kind="unresolved",
        level=imported.level,
        symbols=imported.symbols,
    )


def _directories_of(file_paths: frozenset[str]) -> frozenset[str]:
    """Return every directory the analyzed files live in, parents included."""
    directories: set[str] = set()
    for path in file_paths:
        parts = path.split("/")[:-1]
        for end in range(1, len(parts) + 1):
            directories.add("/".join(parts[:end]))
    return frozenset(directories)


def _infer_source_roots(
    file_paths: frozenset[str], directories: frozenset[str]
) -> tuple[str, ...]:
    """Return the repository root plus every directory outside a package."""
    packages = {
        directory
        for directory in directories
        if any(
            f"{directory}/{marker}" in file_paths for marker in PACKAGE_MARKER_NAMES
        )
    }
    roots = {""} | {
        directory
        for directory in directories
        if not any(
            ancestor in packages for ancestor in _self_and_ancestors(directory)
        )
    }
    return tuple(sorted(roots, key=lambda root: (_depth(root), root)))


def _package_base(source_path: str, level: int) -> str | None:
    """Return the directory a relative import of `level` dots resolves against.

    Level 1 is the importing file's own package and each further level is one
    package up, so `from .. import config` in `app/services/billing.py`
    resolves against `app`. A level that reaches past the repository root
    returns None; a relative import is never an external package.
    """
    parts = source_path.split("/")[:-1]
    ups = level - 1
    if ups > len(parts):
        return None
    return "/".join(parts[: len(parts) - ups])


def _self_and_ancestors(directory: str) -> tuple[str, ...]:
    """Return `directory` and each of its parent directories below the root."""
    parts = directory.split("/")
    return tuple("/".join(parts[:end]) for end in range(1, len(parts) + 1))


def _contains(root: str, directory: str) -> bool:
    """Return whether `root` is `directory` or one of its parents."""
    return root == "" or directory == root or directory.startswith(f"{root}/")


def _depth(directory: str) -> int:
    """Return how many path components a directory has, 0 for the root."""
    return 0 if not directory else directory.count("/") + 1


def _is_package_file(path: str) -> bool:
    """Return whether a resolved path is a package rather than a plain module."""
    return path.rpartition("/")[2] in PACKAGE_MARKER_NAMES


def _join_module(module: str, name: str) -> str:
    """Return the dotted name of `name` seen as a submodule of `module`."""
    return f"{module}.{name}" if module else name


def _join_raw_name(raw_name: str, name: str) -> str:
    """Render `from <raw_name> import <name>` as one dotted reference."""
    if not raw_name or raw_name.endswith("."):
        return f"{raw_name}{name}"
    return f"{raw_name}.{name}"
