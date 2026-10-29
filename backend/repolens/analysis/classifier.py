"""Resolve imports to repository files and label them internal or external.

Classification is the pipeline stage between parsing and storing: analyzers
report imports exactly as written, this module decides which of them point at
another file in the repository, and only the resolved kind and target are
persisted. It works on the storable records `repolens.analysis.adapter`
produces, because resolving one import needs the whole file list.

Nothing here reads the repository or imports any analyzed module: resolution is
pure path arithmetic over the analyzed file paths, following Python's module
layout rules (dotted names, `__init__.py` packages, `.pyi` stubs). Another
language maps onto `ImportRecord` the same way but has its own layout rules,
so it would bring its own resolver.
"""

from collections.abc import Iterable

from repolens.graph.models import AnalyzedFile, ImportRecord


# How a dotted module name can appear on disk. Packages come first because
# Python's import system prefers a package directory to a same-named module.
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

    An import is `internal` when it resolves to one of those files, `external`
    when it names a package the repository does not contain (the standard
    library or a third-party distribution), and `unresolved` when it points
    inside the repository but no file matches, which also covers star imports
    with no resolvable module and relative imports that reach past the root.
    """

    def __init__(self, file_paths: Iterable[str]) -> None:
        self._files = frozenset(file_paths)
        self._source_roots = _infer_source_roots(self._files)
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

    def classify(self, source_path: str, imported: ImportRecord) -> ImportRecord:
        """Return `imported` with its kind, target path, and package filled in.

        `source_path` is the repository path of the file the import was written
        in; a relative import resolves against that file's package.
        """
        module = imported.raw_name[imported.level :]

        if imported.level > 0:
            return _resolved(imported, self._resolve_relative(source_path, imported))

        for root in self._roots_for(source_path):
            target = self._resolve_reference(root, module, imported, source_path)
            if target is not None:
                return _resolved(imported, target)

        package = self._external_package(source_path, module)
        return _resolved(imported, None, package=package)

    def classify_file(self, file: AnalyzedFile) -> AnalyzedFile:
        """Return `file` with every one of its imports classified.

        A file that did not parse reports no imports, so it passes through
        unchanged instead of failing the stage.
        """
        if not file.imports:
            return file
        return AnalyzedFile(
            path=file.path,
            module=file.module,
            parsed=file.parsed,
            line_count=file.line_count,
            symbols=file.symbols,
            imports=tuple(
                self.classify(file.path, imported) for imported in file.imports
            ),
            comments=file.comments,
        )

    def classify_files(
        self, files: Iterable[AnalyzedFile]
    ) -> tuple[AnalyzedFile, ...]:
        """Return every file with its imports classified, in the given order."""
        return tuple(self.classify_file(file) for file in files)

    def _resolve_relative(
        self, source_path: str, imported: ImportRecord
    ) -> str | None:
        """Resolve a relative import against the importing file's package.

        Level 1 is the importing file's own package and each further level is
        one package up, so `from .. import config` in
        `app/services/billing.py` resolves against `app`. A level that reaches
        past the repository root resolves to nothing; a relative import is
        never an external package.
        """
        base = _package_base(source_path, imported.level)
        if base is None:
            return None
        module = imported.raw_name[imported.level :]
        return self._resolve_reference(base, module, imported, source_path)

    def _resolve_reference(
        self,
        root: str,
        module: str,
        imported: ImportRecord,
        source_path: str,
    ) -> str | None:
        """Resolve one import reference below `root`, or return None.

        A `from` import that takes a single name prefers that name as a
        submodule, so `from . import config` reaches the sibling
        `config.py` and `from app.services import billing` reaches
        `app/services/billing.py` rather than the package that re-exports it.
        Otherwise the dotted module itself is the target, which is what makes
        the trailing name in `from app.config import DEFAULT_TIMEOUT` an
        attribute instead of a module. `'*'` is never resolved as a submodule:
        a star import is resolved from its module alone.

        A file never depends on itself, so a reference that lands back on
        `source_path` resolves to nothing.
        """
        names = tuple(name for name in imported.symbols if name != _STAR_IMPORT)
        if len(names) == 1:
            submodule = self._resolve_module(root, _join_module(module, names[0]))
            if submodule is not None and submodule != source_path:
                return submodule

        target = self._resolve_module(root, module)
        return None if target == source_path else target

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

    def _external_package(self, source_path: str, module: str) -> str | None:
        """Return the distribution an unresolved absolute import comes from.

        Only the top-level name is reported, so `os.path` is `os`. A reference
        whose top-level name *is* a repository package is reported as no
        package at all: the import points inside the repository, the named
        module is simply missing, which is `unresolved` rather than a
        third-party dependency.
        """
        top_level = module.split(".")[0]
        if not top_level:
            return None
        for root in self._roots_for(source_path):
            if self._resolve_module(root, top_level) is not None:
                return None
        return top_level

    def _roots_for(self, source_path: str) -> tuple[str, ...]:
        """Return the source roots to try for a file, nearest root first.

        The roots containing the importing file come first, deepest first,
        the way the nearest package directory on `sys.path` wins at runtime.
        That keeps two copies of one package in a monorepo apart: a file in
        `service_b/` resolves `app.config` to its own tree.
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


def _resolved(
    imported: ImportRecord, target: str | None, package: str | None = None
) -> ImportRecord:
    """Return `imported` labeled for the target path or package it resolved to."""
    if target is not None:
        kind = "internal"
    elif package is not None:
        kind = "external"
    else:
        kind = "unresolved"
    return ImportRecord(
        raw_name=imported.raw_name,
        kind=kind,
        target_path=target,
        target_package=package,
        level=imported.level,
        symbols=imported.symbols,
    )


def _infer_source_roots(file_paths: frozenset[str]) -> tuple[str, ...]:
    """Return the repository root plus every directory outside a package."""
    directories: set[str] = set()
    for path in file_paths:
        parts = path.split("/")[:-1]
        for end in range(1, len(parts) + 1):
            directories.add("/".join(parts[:end]))

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
    """Return the directory a relative import of `level` dots resolves against."""
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


def _join_module(module: str, name: str) -> str:
    """Return the dotted name of `name` seen as a submodule of `module`."""
    return f"{module}.{name}" if module else name
