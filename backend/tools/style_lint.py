"""Minimal AST-based style linter for RepoLens (Google Python Style Guide)."""

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

MAX_LINE_LENGTH = 80
SNAKE_CASE = re.compile(r"^_?[a-z][a-z0-9_]*$")
CAP_WORDS = re.compile(r"^_?[A-Z][a-zA-Z0-9]*$")
UPPER_CASE = re.compile(r"^_?[A-Z][A-Z0-9_]*$")
# ast.NodeVisitor requires methods named visit_<NodeType>.
VISITOR_HOOK = re.compile(r"^visit_[A-Za-z]+$")
MUTABLE_DEFAULTS = (ast.List, ast.Dict, ast.Set)


@dataclass
class Violation:
    """A single style problem found in a source file."""

    path: str
    line: int
    message: str


def _is_valid_function_name(name):
    """Returns True if a function name follows the naming rules."""
    return bool(SNAKE_CASE.match(name)
                or name.startswith("__")
                or VISITOR_HOOK.match(name))


def _is_none(node):
    """Returns True if an AST node is the literal None."""
    return isinstance(node, ast.Constant) and node.value is None


class StyleChecker(ast.NodeVisitor):
    """Walks an AST and records Google-style violations."""

    def __init__(self, path, source):
        """Stores the file path and its source lines."""
        self.path = path
        self.lines = source.splitlines()
        self.violations = []
        self.imported_names = {}  # name -> import node
        self.used_names = set()

    def report(self, node, message):
        """Records a violation tied to an AST node."""
        self.violations.append(
            Violation(self.path, getattr(node, "lineno", 0), message))

    def visit_FunctionDef(self, node):
        """Checks function naming, docstrings, and default arguments."""
        if not _is_valid_function_name(node.name):
            self.report(node, f"function '{node.name}' should be snake_case")
        if (ast.get_docstring(node) is None
                and not node.name.startswith("_")
                and not node.name.startswith("test_")):
            self.report(
                node, f"public function '{node.name}' missing docstring")
        for default in node.args.defaults + node.args.kw_defaults:
            if isinstance(default, MUTABLE_DEFAULTS):
                self.report(
                    default,
                    f"mutable default argument in '{node.name}'")
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_ClassDef(self, node):
        """Checks class naming and docstrings."""
        if not CAP_WORDS.match(node.name):
            self.report(node, f"class '{node.name}' should be CapWords")
        if ast.get_docstring(node) is None:
            self.report(node, f"class '{node.name}' missing docstring")
        self.generic_visit(node)

    def visit_Compare(self, node):
        """Flags comparisons to None made with == or !=."""
        for op, comparator in zip(node.ops, node.comparators):
            if isinstance(op, (ast.Eq, ast.NotEq)) and (
                    _is_none(node.left) or _is_none(comparator)):
                self.report(
                    node, "compare to None with 'is' or 'is not'")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node):
        """Flags bare except clauses."""
        if node.type is None:
            self.report(node, "bare 'except:' is not allowed")
        self.generic_visit(node)

    def visit_Import(self, node):
        """Checks for multiple imports on one line and records names."""
        if len(node.names) > 1:
            self.report(node, "use one import per line")
        for alias in node.names:
            name = alias.asname or alias.name.split(".")[0]
            self.imported_names[name] = node
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        """Checks for wildcard imports and records imported names."""
        if any(alias.name == "*" for alias in node.names):
            self.report(node, "wildcard imports are not allowed")
        for alias in node.names:
            if alias.name != "*":
                self.imported_names[alias.asname or alias.name] = node
        self.generic_visit(node)

    def visit_Name(self, node):
        """Records every name that is read."""
        self.used_names.add(node.id)
        self.generic_visit(node)

    def check_unused_imports(self):
        """Flags imported names that are never referenced."""
        for name, node in self.imported_names.items():
            if name not in self.used_names:
                self.report(node, f"'{name}' imported but unused")

    def check_line_lengths(self):
        """Flags physical lines longer than the column limit."""
        for i, line in enumerate(self.lines, start=1):
            if len(line) > MAX_LINE_LENGTH:
                self.violations.append(Violation(
                    self.path, i,
                    f"line is {len(line)} chars (max {MAX_LINE_LENGTH})"))

    def run(self, tree):
        """Runs all checks on a parsed module and returns the violations."""
        self.visit(tree)
        self.check_unused_imports()
        self.check_line_lengths()
        return self.violations


def lint_file(path):
    """Parses a file and returns its style violations."""
    with open(path, encoding="utf-8") as f:
        source = f.read()
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError as err:
        return [Violation(path, err.lineno or 0,
                          f"syntax error: {err.msg}")]
    return StyleChecker(path, source).run(tree)


if __name__ == "__main__":
    paths = [p for p in sys.argv[1:] if "fixtures" not in Path(p).parts]
    problems = [v for p in paths for v in lint_file(p)]
    for v in sorted(problems, key=lambda v: (v.path, v.line)):
        print(f"{v.path}:{v.line}: {v.message}")
    sys.exit(1 if problems else 0)