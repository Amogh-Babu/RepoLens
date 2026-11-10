"""Python `LanguageAnalyzer` built on the standard library `ast` module."""

import ast
import io
import re
import tokenize
from collections.abc import Iterator

from repolens.analysis.models import (
    ImportForm,
    ParsedComment,
    ParsedFile,
    ParsedImport,
    ParsedMember,
    ParsedSymbol,
    ParseError,
)
from repolens.graph.models import MemberKind, SymbolKind


PYTHON_LANGUAGE = "python"
PYTHON_FILE_EXTENSIONS = (".py", ".pyi")

# Function and class bodies are separate scopes: the names they bind belong to
# the function or class, not to the module.
_SCOPE_BOUNDARIES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)

# Prose longer than this is cut: the record stays findable, and one huge
# docstring cannot crowd out the rest of the index.
_MAX_PROSE_LENGTH = 2000

# Machine directives rather than prose: they say nothing about what code does.
_DIRECTIVE_COMMENT = re.compile(
    r"^(?:!|-\*-|(?:type|noqa|pragma|fmt|pylint|mypy|isort|pyright|ruff)\b"
    r"|(?:vim?|coding)[:=])",
    re.IGNORECASE,
)

_DocumentedNode = ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef


class PythonAnalyzer:
    """Extract imports, symbols, members, and prose from Python source text.

    Source is only parsed with `ast.parse` and read with `tokenize`; it is
    never imported, executed, or evaluated. A file that does not parse is
    reported with `parsed=False` and a `ParseError` so the rest of the
    repository still analyzes.
    """

    language: str = PYTHON_LANGUAGE
    file_extensions: tuple[str, ...] = PYTHON_FILE_EXTENSIONS

    def supports(self, path: str) -> bool:
        """Return whether `path` has a Python source extension."""
        return path.lower().endswith(self.file_extensions)

    def analyze(self, path: str, source: str) -> ParsedFile:
        """Return what `source` declares, imports, and says about itself."""
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
            members=_extract_members(tree),
            comments=_in_line_order(_extract_docstrings(tree), _extract_comments(source)),
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

    Declarations guarded by module-level control flow are module-level too, so
    an `if TYPE_CHECKING:` class, a `try`/`except ImportError` fallback, and a
    platform- or version-gated definition are all reported. A name declared in
    more than one branch is reported once, at the line of its first branch.

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

    for node in _module_scope_statements(tree.body):
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


def _module_scope_statements(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """Yield every statement that binds names in the module namespace.

    Control-flow suites run in the scope that contains them, so `if`, `try`,
    `for`, `while`, `with`, and `match` statements are followed into their
    bodies and into their `else`, `except`, and `finally` branches. Traversal
    stops at function and class definitions: those are yielded, because they
    declare a name, but their bodies are not entered.

    Statements come out in source order, so a name declared in several branches
    keeps the line of the first one.
    """
    for statement in body:
        yield statement
        if isinstance(statement, _SCOPE_BOUNDARIES):
            continue
        yield from _module_scope_statements(_nested_statements(statement))


def _nested_statements(statement: ast.stmt) -> list[ast.stmt]:
    """Return the statements a control-flow statement runs in the same scope."""
    nested: list[ast.stmt] = []
    for child in ast.iter_child_nodes(statement):
        if isinstance(child, ast.stmt):
            nested.append(child)
        elif isinstance(child, (ast.ExceptHandler, ast.match_case)):
            nested.extend(child.body)
    return nested


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


def _extract_members(tree: ast.Module) -> tuple[ParsedMember, ...]:
    """Collect the methods and attributes of every module-level class.

    Attributes are the names a class body binds (dataclass fields, class
    constants) plus the `self.<name>` attributes its methods assign. Each
    member is reported once per class, at its first line. Nested classes, and
    functions defined inside methods, are not members.
    """
    members: list[ParsedMember] = []
    for node in _module_scope_statements(tree.body):
        if isinstance(node, ast.ClassDef):
            members.extend(_class_members(node))
    return tuple(members)


def _class_members(cls: ast.ClassDef) -> list[ParsedMember]:
    """Return one class's methods, then its attributes, in first-line order."""
    members: list[ParsedMember] = []
    seen: set[str] = set()

    def add(name: str, kind: MemberKind, line: int) -> None:
        if name in seen:
            return
        seen.add(name)
        members.append(ParsedMember(owner=cls.name, name=name, kind=kind, line=line))

    methods: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for statement in _module_scope_statements(cls.body):
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(statement.name, "method", statement.lineno)
            methods.append(statement)
        elif isinstance(statement, ast.Assign):
            for target in statement.targets:
                for name in _assigned_names(target):
                    add(name, "attribute", statement.lineno)
        elif isinstance(statement, ast.AnnAssign):
            for name in _assigned_names(statement.target):
                add(name, "attribute", statement.lineno)

    for method in methods:
        for line, name in _receiver_attributes(method):
            add(name, "attribute", line)
    return members


def _receiver_attributes(
    method: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[tuple[int, str]]:
    """Return `(line, name)` for each `self.<name> = ...` in a method, by line.

    The receiver is the method's first positional parameter, whatever it is
    called. A static method with no parameters has no receiver.
    """
    if not method.args.args:
        return []
    receiver = method.args.args[0].arg
    assignments: list[tuple[int, str]] = []
    for node in ast.walk(method):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            targets = [node.target]
        for target in targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == receiver
            ):
                assignments.append((node.lineno, target.attr))
    return sorted(assignments)


def _extract_docstrings(tree: ast.Module) -> list[ParsedComment]:
    """Collect the module docstring and those of classes, functions, methods.

    Docstrings are read from the syntax tree as string constants, so nothing
    is evaluated. Functions nested inside other functions are skipped: they
    document local helpers rather than the file.
    """
    docstrings: list[ParsedComment] = []

    def add(node: _DocumentedNode) -> None:
        text = ast.get_docstring(node, clean=True)
        if text and text.strip():
            docstrings.append(
                ParsedComment(
                    line=node.body[0].lineno,
                    text=_clip(text.strip()),
                    kind="docstring",
                )
            )

    add(tree)
    for node in _module_scope_statements(tree.body):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(node)
        elif isinstance(node, ast.ClassDef):
            add(node)
            for statement in _module_scope_statements(node.body):
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add(statement)
    return docstrings


def _extract_comments(source: str) -> list[ParsedComment]:
    """Collect `#` comments as prose blocks, read with `tokenize`.

    Consecutive full-line comments become one block at the line of the first,
    since they usually form one explanation. A comment trailing code is a
    block of its own. Shebangs, encoding cookies, and tool directives such as
    `# noqa` or `# type: ignore` are dropped.
    """
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(source).readline))
    except (tokenize.TokenError, SyntaxError):
        return []

    comments: list[ParsedComment] = []
    block: list[str] = []
    block_start = block_end = 0

    def flush() -> None:
        if block:
            comments.append(ParsedComment(line=block_start, text=_clip(" ".join(block))))
            block.clear()

    for token in tokens:
        if token.type != tokenize.COMMENT:
            continue
        text = token.string.lstrip("#").strip()
        if not text or _DIRECTIVE_COMMENT.match(text):
            continue
        line = token.start[0]
        standalone = token.line.lstrip().startswith("#")
        if standalone and block and line == block_end + 1:
            block.append(text)
            block_end = line
            continue
        flush()
        block.append(text)
        block_start = block_end = line
        if not standalone:
            flush()
    flush()
    return comments


def _in_line_order(*groups: list[ParsedComment]) -> tuple[ParsedComment, ...]:
    """Return every comment block and docstring sorted by line."""
    merged = [comment for group in groups for comment in group]
    return tuple(sorted(merged, key=lambda comment: (comment.line, comment.kind)))


def _clip(text: str) -> str:
    """Cut prose to at most `_MAX_PROSE_LENGTH` characters."""
    if len(text) <= _MAX_PROSE_LENGTH:
        return text
    return text[: _MAX_PROSE_LENGTH - 1].rstrip() + "\u2026"
