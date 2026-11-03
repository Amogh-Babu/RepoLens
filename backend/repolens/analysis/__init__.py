"""RepoLens source analysis package.

Parses source files into imports and top-level symbols behind the
`LanguageAnalyzer` interface, so support for another language is a new
analyzer rather than a change to the pipeline.
"""

from repolens.analysis.adapter import (
    to_analysis_counts,
    to_analyzed_file,
    to_analyzed_files,
)
from repolens.analysis.classifier import (
    MODULE_SUFFIXES,
    PACKAGE_MARKER_NAMES,
    ImportClassifier,
    classify_imports,
)
from repolens.analysis.models import (
    ImportForm,
    ParsedFile,
    ParsedImport,
    ParsedSymbol,
    ParseError,
    RepositoryAnalysis,
)
from repolens.analysis.ports import LanguageAnalyzer
from repolens.analysis.python_analyzer import (
    PYTHON_FILE_EXTENSIONS,
    PYTHON_LANGUAGE,
    PythonAnalyzer,
)
from repolens.analysis.service import (
    SKIPPED_DIRECTORY_NAMES,
    AnalysisService,
    UnsupportedFileError,
)

__all__ = [
    "AnalysisService",
    "ImportClassifier",
    "ImportForm",
    "LanguageAnalyzer",
    "MODULE_SUFFIXES",
    "PACKAGE_MARKER_NAMES",
    "PYTHON_FILE_EXTENSIONS",
    "PYTHON_LANGUAGE",
    "ParseError",
    "ParsedFile",
    "ParsedImport",
    "ParsedSymbol",
    "PythonAnalyzer",
    "RepositoryAnalysis",
    "SKIPPED_DIRECTORY_NAMES",
    "UnsupportedFileError",
    "classify_imports",
    "to_analysis_counts",
    "to_analyzed_file",
    "to_analyzed_files",
]
