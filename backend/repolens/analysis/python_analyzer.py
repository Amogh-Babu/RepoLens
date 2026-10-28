"""Python `LanguageAnalyzer` built on the standard library `ast` module."""

import ast

from repolens.analysis.models import (
    ImportForm,
    ParsedFile,
    ParsedImport,
    ParsedSymbol,
    ParseError,
)
from repolens.graph.models import SymbolKind


PYTHON_LANGUAGE = "python"
PYTHON_FILE_EXTENSIONS = (".py", ".pyi")


class PythonAnalyzer:
    """Extract imports and top-level symbols from Python source text.

    Source is only parsed with `ast.parse`; it is never imported, executed, or
    evaluated. A file that does not parse is reported with `parsed=False` and a
    `ParseError` so the rest of the repository still analyzes.
    """

    language: str = PYTHON_LANGUAGE
    file_extensions: tuple[str, ...] = PYTHON_FILE_EXTENSIONS

    def supports(self, path: str) -> bool:
        """Return whether `path` has a Python source extension."""
        return path.lower().endswith(self.file_extensions)

    def analyze(self, path: str, source: str) -> ParsedFile:
        """Return the imports and top-level symbols declared in `source`."""
        line_count = len(source.splitlines())
        try:
            tree = ast.parse(source, filename=path)
        except (SyntaxError, ValueError) as error:
            return ParsedFile(
                path=path,
                language=self.language,
                parsed=False,
                line_count=line_count,
                error=_to_parse_error(error),
            )

        return ParsedFile(
            path=path,
            language=self.language,
            parsed=True,
            line_count=line_count,
            imports=_extract_imports(tree),
            symbols=_extract_top_level_symbols(tree),
        )


def _to_parse_error(error: Exception) -> ParseError:
    """Describe a parse failure without leaking the source text."""
    if isinstance(error, SyntaxError):
        return ParseError(
            message=error.msg or "invalid syntax",
            line=error.lineno,
            column=error.offset,
        )
    return ParseError(message=str(error) or "could not parse source")


def _extract_imports(tree: ast.Module) -> tuple[ParsedImport, ...]:
    """Collect every import in the tree, including imports inside functions.

    Statements that reference the same module are merged into one record so a
    module is reported once per file, with the names it contributes and the
    line of its first import.
    """
    merged: dict[tuple[ImportForm, int, str | None], ParsedImport] = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                _merge_import(
                    merged,
                    ParsedImport(
                        module=alias.name,
                        form="import",
                        level=0,
                        line=node.lineno,
                    ),
                )
        elif isinstance(node, ast.ImportFrom):
            _merge_import(
                merged,
                ParsedImport(
                    module=node.module,
                    form="from",
                    level=node.level,
                    symbols=tuple(alias.name for alias in node.names),
                    line=node.lineno,
                ),
            )

    return tuple(
        sorted(merged.values(), key=lambda imported: (imported.line, imported.raw_name))
    )


def _merge_import(
    merged: dict[tuple[ImportForm, int, str | None], ParsedImport],
    imported: ParsedImport,
) -> None:
    """Add `imported` to `merged`, combining it with the same module reference."""
    key = (imported.form, imported.level, imported.module)
    existing = merged.get(key)
    if existing is None:
        merged[key] = imported
        return

    extra = tuple(name for name in imported.symbols if name not in existing.symbols)
    merged[key] = ParsedImport(
        module=existing.module,
        form=existing.form,
        level=existing.level,
        symbols=existing.symbols + extra,
        line=min(existing.line, imported.line),
    )


def _extract_top_level_symbols(tree: ast.Module) -> tuple[ParsedSymbol, ...]:
    """Collect the functions, classes, and variables declared at module level.

    Methods and nested definitions belong to their enclosing symbol and are not
    reported separately.
    """
    symbols: list[ParsedSymbol] = []
    seen: set[tuple[str, SymbolKind]] = set()

    def add(name: str, kind: SymbolKind, line: int) -> None:
        if (name, kind) in seen:
            return
        seen.add((name, kind))
        symbols.append(ParsedSymbol(name=name, kind=kind, line=line))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(node.name, "function", node.lineno)
        elif isinstance(node, ast.ClassDef):
            add(node.name, "class", node.lineno)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for name in _assigned_names(target):
                    add(name, "variable", node.lineno)
        elif isinstance(node, ast.AnnAssign):
            for name in _assigned_names(node.target):
                add(name, "variable", node.lineno)

    return tuple(symbols)


def _assigned_names(target: ast.expr) -> tuple[str, ...]:
    """Return the plain names bound by an assignment target.

    Attribute and subscript targets such as `config.debug = True` do not
    declare a module-level symbol, so they contribute no names.
    """
    if isinstance(target, ast.Name):
        return (target.id,)
    if isinstance(target, (ast.Tuple, ast.List)):
        names: list[str] = []
        for element in target.elts:
            names.extend(_assigned_names(element))
        return tuple(names)
    if isinstance(target, ast.Starred):
        return _assigned_names(target.value)
    return ()
