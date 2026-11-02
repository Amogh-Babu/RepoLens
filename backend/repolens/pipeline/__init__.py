"""RepoLens analysis pipeline.

Ties ingestion, analysis, and the graph store together so the API can turn a
repository URL into a stored, searchable dependency graph.
"""

from repolens.pipeline.runner import (
    DEFAULT_MAX_CONCURRENT_ANALYSES,
    PipelineAnalysisRunner,
)

__all__ = [
    "DEFAULT_MAX_CONCURRENT_ANALYSES",
    "PipelineAnalysisRunner",
]
