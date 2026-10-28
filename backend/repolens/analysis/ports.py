"""Protocol definition for pluggable per-language source analyzers."""

from typing import Protocol, runtime_checkable

from repolens.analysis.models import ParsedFile


@runtime_checkable
class LanguageAnalyzer(Protocol):
    """Extract imports and top-level symbols from one language's source files.

    Implementations parse source text only. They never import, execute, or
    evaluate the code they analyze, and they report an unparsable file instead
    of raising, so a second language can be added without changing the rest of
    the pipeline.
    """

    language: str
    file_extensions: tuple[str, ...]

    def supports(self, path: str) -> bool:
        """Return whether this analyzer can analyze the file at `path`."""
        ...

    def analyze(self, path: str, source: str) -> ParsedFile:
        """Return the imports and top-level symbols of `source`."""
        ...
