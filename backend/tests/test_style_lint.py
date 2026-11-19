"""Tests for the AST-based style linter in backend/tools/style_lint.py."""

import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT / "tools"))

import style_lint  # noqa: E402


def lint_source(tmp_path, source, name="sample.py"):
    """Writes source to a temp file, lints it, and returns violations."""
    path = tmp_path / name
    path.write_text(source, encoding="utf-8")
    return style_lint.lint_file(str(path))


def messages(violations):
    """Returns the message text from each violation."""
    return [v.message for v in violations]


# Function naming

def test_function_name_not_snake_case_is_flagged(tmp_path):
    violations = lint_source(tmp_path, '''
def BadName():
    """Does something."""
''')
    assert any("should be snake_case" in m for m in messages(violations))


def test_snake_case_function_is_allowed(tmp_path):
    violations = lint_source(tmp_path, '''
def good_name():
    """Does something."""
''')
    assert not any("snake_case" in m for m in messages(violations))


def test_dunder_method_is_not_flagged_for_naming(tmp_path):
    violations = lint_source(tmp_path, '''
class Thing:
    """A thing."""

    def __init__(self):
        """Creates a thing."""
''')
    assert not any("snake_case" in m for m in messages(violations))


def test_async_function_is_checked(tmp_path):
    violations = lint_source(tmp_path, '''
async def BadAsync():
    """Does something."""
''')
    assert any("should be snake_case" in m for m in messages(violations))


# Function docstrings

def test_public_function_without_docstring_is_flagged(tmp_path):
    violations = lint_source(tmp_path, '''
def public_func():
    return 1
''')
    assert any("missing docstring" in m for m in messages(violations))


def test_private_function_without_docstring_is_allowed(tmp_path):
    violations = lint_source(tmp_path, '''
def _private_func():
    return 1
''')
    assert not any("missing docstring" in m for m in messages(violations))


# Class naming and docstrings

def test_class_not_capwords_is_flagged(tmp_path):
    violations = lint_source(tmp_path, '''
class bad_class:
    """A class."""
''')
    assert any("should be CapWords" in m for m in messages(violations))


def test_capwords_class_is_allowed(tmp_path):
    violations = lint_source(tmp_path, '''
class GoodClass:
    """A class."""
''')
    assert not any("CapWords" in m for m in messages(violations))


def test_class_without_docstring_is_flagged(tmp_path):
    violations = lint_source(tmp_path, '''
class GoodClass:
    pass
''')
    assert any("missing docstring" in m for m in messages(violations))


# Imports

def test_multiple_imports_on_one_line_are_flagged(tmp_path):
    violations = lint_source(tmp_path, "import os, sys\n")
    assert any("one import per line" in m for m in messages(violations))


def test_single_import_per_line_is_allowed(tmp_path):
    violations = lint_source(tmp_path, "import os\nimport sys\n")
    assert not any("one import per line" in m for m in messages(violations))


def test_wildcard_import_is_flagged(tmp_path):
    violations = lint_source(tmp_path, "from os.path import *\n")
    assert any("wildcard" in m for m in messages(violations))


def test_named_from_import_is_allowed(tmp_path):
    violations = lint_source(tmp_path, "from os import path\n")
    assert not any("wildcard" in m for m in messages(violations))


# Line length

def test_line_over_80_chars_is_flagged(tmp_path):
    long_line = "x = '" + "a" * 80 + "'\n"
    violations = lint_source(tmp_path, long_line)
    assert any("max 80" in m for m in messages(violations))


def test_line_exactly_80_chars_is_allowed(tmp_path):
    line = "x = '" + "a" * 74 + "'\n"
    assert len(line.rstrip("\n")) == 80
    violations = lint_source(tmp_path, line)
    assert not any("max 80" in m for m in messages(violations))


# Violation reporting

def test_violation_reports_correct_line_number(tmp_path):
    violations = lint_source(tmp_path, '''
import os

def BadName():
    """Does something."""
''')
    naming = [v for v in violations if "snake_case" in v.message]
    assert len(naming) == 1
    assert naming[0].line == 4


def test_clean_file_has_no_violations(tmp_path):
    violations = lint_source(tmp_path, '''
"""Module docstring."""

import os


class GoodClass:
    """A well-formed class."""

    def good_method(self):
        """Does something."""
        return os.getcwd()
''')
    assert violations == []


# Command-line behavior

def test_main_exits_nonzero_on_violations(tmp_path, monkeypatch, capsys):
    bad = tmp_path / "bad.py"
    bad.write_text("def BadName():\n    pass\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["style_lint.py", str(bad)])
    with pytest.raises(SystemExit) as exc:
        runpy_main()
    assert exc.value.code == 1
    assert "snake_case" in capsys.readouterr().out


def test_main_exits_zero_on_clean_file(tmp_path, monkeypatch):
    good = tmp_path / "good.py"
    good.write_text('"""Module."""\n', encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["style_lint.py", str(good)])
    with pytest.raises(SystemExit) as exc:
        runpy_main()
    assert exc.value.code == 0

def test_visitor_hook_methods_are_not_flagged_for_naming(tmp_path):
    violations = lint_source(tmp_path, '''
import ast


class Walker(ast.NodeVisitor):
    """Visits nodes."""

    def visit_FunctionDef(self, node):
        """Visits a function."""
        self.generic_visit(node)
''')
    assert not any("snake_case" in m for m in messages(violations))

def test_syntax_error_is_reported_not_raised(tmp_path):
    """Reports broken syntax as a violation instead of crashing."""
    violations = lint_source(tmp_path, "def broken(x:\n")
    assert any("syntax error" in m for m in messages(violations))

# None comparisons

def test_equality_with_none_is_flagged(tmp_path):
    violations = lint_source(tmp_path, "x = 1\nif x == None:\n    pass\n")
    assert any("'is' or 'is not'" in m for m in messages(violations))


def test_inequality_with_none_is_flagged(tmp_path):
    violations = lint_source(tmp_path, "x = 1\nif None != x:\n    pass\n")
    assert any("'is' or 'is not'" in m for m in messages(violations))


def test_identity_check_with_none_is_allowed(tmp_path):
    violations = lint_source(tmp_path, "x = 1\nif x is None:\n    pass\n")
    assert not any("'is' or 'is not'" in m for m in messages(violations))


# Bare except

def test_bare_except_is_flagged(tmp_path):
    violations = lint_source(tmp_path, (
        "try:\n"
        "    pass\n"
        "except:\n"
        "    pass\n"))
    assert any("bare 'except:'" in m for m in messages(violations))


def test_typed_except_is_allowed(tmp_path):
    violations = lint_source(tmp_path, (
        "try:\n"
        "    pass\n"
        "except ValueError:\n"
        "    pass\n"))
    assert not any("bare 'except:'" in m for m in messages(violations))


# Mutable default arguments

def test_list_default_argument_is_flagged(tmp_path):
    violations = lint_source(tmp_path, '''
def collect(items=[]):
    """Collects items."""
    return items
''')
    assert any("mutable default" in m for m in messages(violations))


def test_dict_keyword_default_is_flagged(tmp_path):
    violations = lint_source(tmp_path, '''
def configure(*, options={}):
    """Configures options."""
    return options
''')
    assert any("mutable default" in m for m in messages(violations))


def test_none_default_argument_is_allowed(tmp_path):
    violations = lint_source(tmp_path, '''
def collect(items=None):
    """Collects items."""
    return items or []
''')
    assert not any("mutable default" in m for m in messages(violations))


# Unused imports

def test_unused_import_is_flagged(tmp_path):
    violations = lint_source(tmp_path, "import os\n")
    assert any("'os' imported but unused" in m
               for m in messages(violations))


def test_used_import_is_allowed(tmp_path):
    violations = lint_source(tmp_path, "import os\nprint(os.sep)\n")
    assert not any("imported but unused" in m
                   for m in messages(violations))


def test_unused_from_import_is_flagged(tmp_path):
    violations = lint_source(tmp_path, "from os import path\n")
    assert any("'path' imported but unused" in m
               for m in messages(violations))


def test_aliased_import_uses_alias_name(tmp_path):
    violations = lint_source(tmp_path, (
        "import numpy as np\n"
        "print(np.zeros(3))\n"))
    assert not any("imported but unused" in m
                   for m in messages(violations))


def test_dotted_import_counts_as_top_level_name(tmp_path):
    violations = lint_source(tmp_path, (
        "import os.path\n"
        "print(os.sep)\n"))
    assert not any("imported but unused" in m
                   for m in messages(violations))

def runpy_main():
    """Runs the linter's __main__ block as if invoked from the command line."""
    import runpy
    runpy.run_path(
        str(BACKEND_ROOT / "tools" / "style_lint.py"), run_name="__main__")