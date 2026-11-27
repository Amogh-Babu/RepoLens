"""Path-based categories shared by onboarding and search."""

from pathlib import PurePosixPath


_TEST_DIRS = frozenset({"test", "tests"})
_TOOL_DIRS = frozenset({"script", "scripts", "tool", "tools"})
_DOC_DIRS = frozenset({"doc", "docs", "documentation"})
_EXAMPLE_DIRS = frozenset({"example", "examples", "demo", "demos"})
_MIGRATION_DIRS = frozenset({"migration", "migrations"})
_CONFIG_NAMES = frozenset(
    {
        "pyproject.toml", "setup.cfg", "setup.py", "tox.ini", "noxfile.py",
        "requirements.txt", "dockerfile", "makefile",
    }
)
_CONFIG_SUFFIXES = frozenset(
    {".ini", ".cfg", ".toml", ".yaml", ".yml", ".json", ".lock", ".env"}
)


def file_category(path: str) -> str:
    parts = tuple(part.casefold() for part in PurePosixPath(path).parts)
    name = parts[-1] if parts else ""
    if _TEST_DIRS.intersection(parts[:-1]) or name.startswith("test_") or name.endswith(
        "_test.py"
    ) or name == "conftest.py":
        return "test"
    if _DOC_DIRS.intersection(parts[:-1]) or name in {
        "readme.md", "changelog.md", "contributing.md",
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
