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
from repolens.graph.store import SqliteGraphStore
from repolens.ingestion import (
    GitHubRefResolver,
    GitHubSource,
    IngestionError,
    NoPythonFilesError,
    RepoSource,
)


_LOGGER = logging.getLogger(__name__)

DEFAULT_MAX_CONCURRENT_ANALYSES = 2

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
    ) -> None:
        """Initialize the runner.

        Args:
          resolver: Resolves refs to commit SHAs; defaults to the GitHub API.
          source: Downloads snapshots; defaults to `GitHubSource`.
          analysis_service: Parses snapshots; defaults to Python only.
          executor: Runs analyses in the background; defaults to a small
            thread pool. Tests pass one that runs work inline.
          work_root: Parent directory for temporary snapshots; defaults to
            the system temporary directory.
        """
        self._resolver = resolver if resolver is not None else GitHubRefResolver()
        self._source = source if source is not None else GitHubSource()
        self._analysis_service = (
            analysis_service if analysis_service is not None else AnalysisService()
        )
        self._executor = (
            executor
            if executor is not None
            else ThreadPoolExecutor(
                max_workers=DEFAULT_MAX_CONCURRENT_ANALYSES,
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

        cached = store.find_cached_analysis(repo_url, sha)
        if cached is not None:
            return {
                "analysisId": str(cached["id"]),
                "sha": str(cached["sha"]),
                "status": str(cached["status"]),
            }

        analysis_id = f"analysis-{uuid.uuid4().hex[:12]}"
        store.save(
            AnalysisRecord(
                analysis_id=analysis_id,
                repo=repo_url,
                ref=clean_ref,
                sha=sha,
                status="queued",
                stage="downloading",
            )
        )
        self._executor.submit(self.run, store, analysis_id, repo_url, clean_ref, sha)
        return {"analysisId": analysis_id, "sha": sha, "status": "queued"}

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
            shutil.rmtree(work_dir, ignore_errors=True)

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

        if not store.update_stage(analysis_id, "classifying"):
            return
        files = classify_imports(to_analyzed_files(analysis))

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
            )
        )
