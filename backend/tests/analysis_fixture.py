"""Shared access to the analysis mini repository fixture.

The fixture's Python files are read and parsed by the analyzer; they are never
imported or executed.
"""

from pathlib import Path

from repolens.analysis import AnalysisService, RepositoryAnalysis


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "analysis_mini_repo"


def analyze_fixture() -> RepositoryAnalysis:
    """Analyze the mini repository fixture with the default analyzers."""
    return AnalysisService().analyze_repository(FIXTURE_ROOT)
