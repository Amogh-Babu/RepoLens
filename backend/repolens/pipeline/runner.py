"""Run a full repository analysis: resolve, download, parse, classify, store.

`PipelineAnalysisRunner` is the `AnalysisRunner` the API server uses. Starting
an analysis resolves the ref to a commit SHA right away, so the response can
name the SHA and a cached analysis of the same commit can be reused. The rest
of the pipeline runs on a background thread and records each stage in the
graph store, which is what `GET /analyses/{id}` reports while the frontend
polls.

Repository content is downloaded and parsed only; it is never imported,
executed, or evaluated.
"""

from concurrent.futures import Executor, ThreadPoolExecutor
import logging
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any
import uuid

from repolens.analysis import (
    AnalysisService,
    classify_imports,
    to_analysis_counts,
    to_analyzed_files,
)
from repolens.graph.models import AnalysisErrorRecord, AnalysisRecord
from repolens.graph.store import IndexingCancelled, SqliteGraphStore
from repolens.ingestion import (
    GitHubRefResolver,
    GitHubSource,
    IngestionError,
    NoPythonFilesError,
    RepoSource,
)


_LOGGER = logging.getLogger(__name__)

# One at a time: semantic indexing already uses the machine's cores, and two
# at once took about four times as long as one after the other (#118).
DEFAULT_MAX_CONCURRENT_ANALYSES = 1

_UNEXPECTED_FAILURE = AnalysisErrorRecord(
    code="ANALYSIS_FAILED",
    message="RepoLens could not analyze this repository.",
    hint="Try again. If it keeps failing, report the repository URL.",
)


class PipelineAnalysisRunner:
    """Analyze public GitHub repositories on background threads."""

    def __init__(
        self,
        resolver: GitHubRefResolver | None = None,
        source: RepoSource | None = None,
        analysis_service: AnalysisService | None = None,
        executor: Executor | None = None,
        work_root: Path | None = None,
        max_concurrent_analyses: int = DEFAULT_MAX_CONCURRENT_ANALYSES,
    ) -> None:
        """Initialize the runner.

        Args:
          resolver: Resolves refs to commit SHAs; defaults to the GitHub API.
          source: Downloads snapshots; defaults to `GitHubSource`.
          analysis_service: Parses snapshots; defaults to Python only.
          executor: Runs analyses in the background; defaults to a pool of
            `max_concurrent_analyses` threads, so later analyses wait in a
            queue. Tests pass one that runs work inline.
          work_root: Parent directory for temporary snapshots; defaults to
            the system temporary directory.
          max_concurrent_analyses: Analyses that run at once when no
            `executor` is given.
        """
        if max_concurrent_analyses < 1:
            raise ValueError("max_concurrent_analyses must be at least 1.")
        self._resolver = resolver if resolver is not None else GitHubRefResolver()
        self._source = source if source is not None else GitHubSource()
        self._analysis_service = (
            analysis_service if analysis_service is not None else AnalysisService()
        )
        self._executor = (
            executor
            if executor is not None
            else ThreadPoolExecutor(
                max_workers=max_concurrent_analyses,
                thread_name_prefix="repolens-analysis",
            )
        )
        self._work_root = work_root

    def start(
        self,
        store: SqliteGraphStore,
        repo_url: str,
        ref: str | None,
    ) -> dict[str, Any]:
        """Resolve the commit, then reuse a cached analysis or queue a new one.

        Raises:
          IngestionError: The repository or ref could not be resolved.
        """
        clean_ref = ref.strip() if ref and ref.strip() else None
        sha = self._resolver.resolve(repo_url, clean_ref)

        row, created = store.start_or_reuse_analysis(
            repo_url,
            clean_ref,
            sha,
            initial_stage="downloading",
        )
        analysis_id = str(row["id"])
        if created:
            self._executor.submit(
                self.run, store, analysis_id, repo_url, clean_ref, sha
            )
        return {
            "analysisId": analysis_id,
            "sha": str(row["sha"]),
            "status": str(row["status"]),
        }

    def run(
        self,
        store: SqliteGraphStore,
        analysis_id: str,
        repo_url: str,
        ref: str | None,
        sha: str,
    ) -> None:
        """Run every stage after resolving and record the outcome.

        Never raises: a failure is stored on the analysis so the frontend can
        show it. Stops quietly once the analysis has been cancelled.
        """
        work_dir = Path(
            tempfile.mkdtemp(prefix="repolens-snapshot-", dir=self._work_root)
        )
        try:
            self._run_stages(store, analysis_id, repo_url, ref, sha, work_dir)
        except IngestionError as error:
            store.fail_analysis(
                analysis_id,
                AnalysisErrorRecord(
                    code=error.code, message=error.message, hint=error.hint
                ),
            )
        except Exception:
            _LOGGER.exception("Analysis %s of %s failed", analysis_id, repo_url)
            store.fail_analysis(analysis_id, _UNEXPECTED_FAILURE)
        finally:
            # Normally already gone (see `_run_stages`); this covers failures
            # and cancellations before parsing finished.
            _remove_snapshot(work_dir)

    def _run_stages(
        self,
        store: SqliteGraphStore,
        analysis_id: str,
        repo_url: str,
        ref: str | None,
        sha: str,
        work_dir: Path,
    ) -> None:
        """Download, filter, parse, classify, and store one analysis."""
        if not store.update_stage(analysis_id, "downloading"):
            return
        snapshot = self._source.fetch_snapshot(repo_url, sha, work_dir / "snapshot")

        if not store.update_stage(analysis_id, "filtering"):
            return
        if not any(self._analysis_service.supports(path) for path in snapshot.files):
            raise NoPythonFilesError()

        if not store.update_stage(analysis_id, "parsing"):
            return
        analysis = self._analysis_service.analyze_repository(snapshot.root)
        # Everything later stages need is in memory now. Removing the source
        # before the analysis is marked completed means a completed analysis
        # never has a snapshot left on disk (#73), and source is never kept
        # longer than parsing needs it.
        _remove_snapshot(work_dir)

        if not store.update_stage(analysis_id, "classifying"):
            return
        files = classify_imports(to_analyzed_files(analysis))

        if not store.update_stage(analysis_id, "indexing"):
            return
        # Falls back to no vectors (keyword search only) if the model fails
        # or the repository is over the chunk budget; the status says which.
        # Stops between batches if the analysis is cancelled meanwhile.
        try:
            semantic = store.build_semantic_index(
                files, should_continue=lambda: store.is_active(analysis_id)
            )
        except IndexingCancelled:
            return

        if not store.update_stage(analysis_id, "storing"):
            return
        store.complete_analysis(
            AnalysisRecord(
                analysis_id=analysis_id,
                repo=repo_url,
                ref=ref,
                sha=sha,
                status="completed",
                counts=to_analysis_counts(analysis),
                files=files,
                embeddings=semantic.records,
                semantic_status=semantic.status,
                semantic_chunks=semantic.chunk_count,
            )
        )


def _remove_snapshot(work_dir: Path) -> None:
    """Delete a snapshot directory, logging (not raising) if any of it stays."""
    if not work_dir.exists():
        return
    if sys.version_info >= (3, 12):
        shutil.rmtree(work_dir, onexc=_log_cleanup_error)
    else:  # `onexc` is new in 3.12; `onerror` is deprecated from then on.
        shutil.rmtree(
            work_dir,
            onerror=lambda function, path, info: _log_cleanup_error(function, path, info[1]),
        )


def _log_cleanup_error(function: Any, path: str, error: BaseException) -> None:
    _LOGGER.warning(
        "Could not remove %s during snapshot cleanup: %s", path, error, exc_info=error
    )
