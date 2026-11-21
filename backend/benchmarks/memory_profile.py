"""Measure peak memory and stage times of one real repository analysis.

This answers issue #118: how much memory does analyzing a repository take,
and where does the time go? It runs the production pipeline
(`PipelineAnalysisRunner` with the GitHub resolver and source, and an
`SqliteGraphStore` with the FastEmbed model) inline on this thread, then runs
a few searches against the finished analysis, the way the frontend does right
after an analysis completes.

Run it from `backend/`:

    python -m benchmarks.memory_profile https://github.com/numpy/numpy
    python -m benchmarks.memory_profile https://github.com/vmware/pyvmomi

Peak memory is the process's peak resident set size (`ru_maxrss` on Linux and
macOS, `PeakWorkingSetSize` on Windows), which is what the kernel's OOM killer
and the issue report measure. It includes the model and Python itself.
"""

import argparse
from concurrent.futures import Executor, Future
import json
import logging
import os
import sys
import threading
import time
from typing import Any, Callable

from repolens.graph import SqliteGraphStore
from repolens.pipeline import PipelineAnalysisRunner
from repolens.search import SearchService
from repolens.search.embedding import FastEmbedEmbedder


_MIB = 1024 * 1024
_DEFAULT_QUERIES = (
    "parse configuration file",
    "authentication",
    "where are arrays allocated",
    "tests for the command line interface",
    "error handling",
)


class _InlineExecutor(Executor):
    """Run submitted work immediately on the calling thread."""

    def submit(
        self, fn: Callable[..., Any], /, *args: Any, **kwargs: Any
    ) -> Future:
        """Run `fn` now and return a future holding its outcome."""
        future: Future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except BaseException as error:  # pylint: disable=broad-except
            future.set_exception(error)
        return future


def current_rss_bytes() -> int:
    """Return this process's current resident set size in bytes."""
    if sys.platform == "win32":
        return _windows_memory_counters()[1]
    try:
        with open("/proc/self/statm", encoding="ascii") as statm:
            resident_pages = int(statm.read().split()[1])
        return resident_pages * os.sysconf("SC_PAGE_SIZE")
    except OSError:
        return peak_rss_bytes()


def peak_rss_bytes() -> int:
    """Return this process's peak resident set size in bytes."""
    if sys.platform == "win32":
        return _windows_memory_counters()[0]
    import resource  # pylint: disable=import-outside-toplevel

    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports kilobytes, macOS bytes.
    return peak if sys.platform == "darwin" else peak * 1024


def _windows_memory_counters() -> tuple[int, int]:
    """Return (peak, current) working set bytes on Windows."""
    import ctypes  # pylint: disable=import-outside-toplevel
    from ctypes import wintypes  # pylint: disable=import-outside-toplevel

    class _Counters(ctypes.Structure):
        """PROCESS_MEMORY_COUNTERS from psapi.h."""

        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = _Counters()
    counters.cb = ctypes.sizeof(_Counters)
    get_current_process = ctypes.windll.kernel32.GetCurrentProcess
    get_current_process.restype = wintypes.HANDLE
    get_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory_info.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_Counters),
        wintypes.DWORD,
    ]
    get_memory_info.restype = wintypes.BOOL
    if not get_memory_info(get_current_process(), ctypes.byref(counters), counters.cb):
        raise OSError(ctypes.get_last_error(), "GetProcessMemoryInfo failed")
    return int(counters.PeakWorkingSetSize), int(counters.WorkingSetSize)


class _RssSampler:
    """Track the highest current RSS seen during each stage."""

    def __init__(
        self, interval_seconds: float = 0.2, abort_above_bytes: int | None = None
    ) -> None:
        self._interval = interval_seconds
        self._abort_above = abort_above_bytes
        self._stage = "starting"
        self._stage_peaks: dict[str, int] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        """Start sampling in the background."""
        self._thread.start()

    def stop(self) -> None:
        """Stop sampling and wait for the sampler thread."""
        self._stop.set()
        self._thread.join()

    def enter(self, stage: str) -> None:
        """Attribute samples from now on to `stage`."""
        with self._lock:
            self._record()
            self._stage = stage
            self._record()

    def stage_peaks(self) -> dict[str, int]:
        """Return the highest RSS seen in each stage, in bytes."""
        with self._lock:
            return dict(self._stage_peaks)

    def _record(self) -> None:
        rss = current_rss_bytes()
        self._stage_peaks[self._stage] = max(self._stage_peaks.get(self._stage, 0), rss)
        if self._abort_above is not None and rss > self._abort_above:
            # Stop before the machine starts swapping; the numbers so far are
            # the result.
            print(
                json.dumps(
                    {
                        "status": "aborted",
                        "reason": f"RSS passed {self._abort_above // _MIB} MiB",
                        "stage": self._stage,
                        "stagePeakRssMiB": {
                            stage: round(value / _MIB)
                            for stage, value in self._stage_peaks.items()
                        },
                    },
                    indent=2,
                ),
                flush=True,
            )
            os._exit(2)  # pylint: disable=protected-access

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            with self._lock:
                self._record()


class _ProfiledStore(SqliteGraphStore):
    """A graph store that reports each stage change to an `_RssSampler`."""

    def __init__(self, sampler: _RssSampler, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._sampler = sampler
        self.stage_started: dict[str, float] = {}

    def update_stage(self, analysis_id: str, stage: Any) -> bool:
        """Record the stage change, then update the analysis as usual."""
        self._sampler.enter(str(stage))
        self.stage_started[str(stage)] = time.perf_counter()
        return super().update_stage(analysis_id, stage)


def profile(
    repo_url: str,
    ref: str | None,
    queries: tuple[str, ...],
    db_path: str,
    abort_above_mib: int | None = None,
) -> dict[str, Any]:
    """Analyze `repo_url`, run `queries`, and return the measurements."""
    sampler = _RssSampler(
        abort_above_bytes=abort_above_mib * _MIB if abort_above_mib else None
    )
    sampler.start()
    started = time.perf_counter()
    store = _ProfiledStore(sampler, db_path, embedder=FastEmbedEmbedder())
    runner = PipelineAnalysisRunner(executor=_InlineExecutor())
    response = runner.start(store, repo_url, ref)
    analysis_id = response["analysisId"]
    analysis = store.get_analysis(analysis_id)
    stage_times = _stage_durations(store.stage_started, time.perf_counter())
    analysis_seconds = time.perf_counter() - started

    search_seconds: list[float] = []
    if analysis["status"] == "completed":
        sampler.enter("searching")
        service = SearchService(store)
        for query in queries:
            search_started = time.perf_counter()
            service.search(analysis_id, query)
            search_seconds.append(round(time.perf_counter() - search_started, 3))
    sampler.enter("done")
    sampler.stop()

    return {
        "repo": repo_url,
        "ref": ref,
        "status": analysis["status"],
        "error": analysis["error"],
        "summary": analysis["summary"],
        "analysisSeconds": round(analysis_seconds, 1),
        "stageSeconds": stage_times,
        "searchSeconds": search_seconds,
        "peakRssMiB": round(peak_rss_bytes() / _MIB),
        "stagePeakRssMiB": {
            stage: round(value / _MIB) for stage, value in sampler.stage_peaks().items()
        },
    }


def _stage_durations(started: dict[str, float], finished: float) -> dict[str, float]:
    ordered = sorted(started.items(), key=lambda item: item[1])
    durations = {}
    for index, (stage, start) in enumerate(ordered):
        end = ordered[index + 1][1] if index + 1 < len(ordered) else finished
        durations[stage] = round(end - start, 1)
    return durations


def main(argv: list[str] | None = None) -> int:
    """Run the profile from the command line and print the result as JSON."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo_url")
    parser.add_argument("--ref", default=None)
    parser.add_argument(
        "--db",
        default=":memory:",
        help="SQLite path for the graph store (the Docker image uses a file).",
    )
    parser.add_argument("--searches", type=int, default=len(_DEFAULT_QUERIES))
    parser.add_argument(
        "--abort-above-mib",
        type=int,
        default=None,
        help="Stop the run if resident memory passes this many MiB.",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    queries = tuple(
        _DEFAULT_QUERIES[index % len(_DEFAULT_QUERIES)]
        for index in range(args.searches)
    )
    result = profile(args.repo_url, args.ref, queries, args.db, args.abort_above_mib)
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
