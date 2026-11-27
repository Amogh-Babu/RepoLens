"""Tests for the limits that keep analysis memory bounded (#118).

Indexing is the memory peak of an analysis, so these check that it embeds in
small batches with a bounded model configuration, stops when the analysis is
cancelled, stores compact float32 vectors, and that search scores them as one
matrix with the same results as pairwise cosine similarity.
"""

from pathlib import Path
import random
import sys
import types

import numpy as np
import pytest

from repolens.graph import AnalysisRecord, SqliteGraphStore
from repolens.graph.models import AnalyzedFile, SymbolRecord
from repolens.pipeline import PipelineAnalysisRunner
from repolens.search.embedding import (
    ChunkVectors,
    FastEmbedEmbedder,
    HashEmbedder,
    cosine_similarity,
)

from test_pipeline_runner import REPO_URL, SHA, FakeResolver, FakeSource, ManualExecutor


class RecordingEmbedder:
    """HashEmbedder that records each call and can run a hook before it."""

    def __init__(self, before_call=None) -> None:
        self._inner = HashEmbedder()
        self.calls: list[list[str]] = []
        self._before_call = before_call

    @property
    def model_id(self) -> str:
        return self._inner.model_id

    def embed(self, texts):
        if self._before_call is not None:
            self._before_call(len(self.calls))
        self.calls.append(list(texts))
        return self._inner.embed(texts)


def _files(count: int, symbols_per_file: int = 1) -> tuple[AnalyzedFile, ...]:
    return tuple(
        AnalyzedFile(
            path=f"pkg/module_{index}.py",
            parsed=True,
            symbols=tuple(
                SymbolRecord(name=f"function_{index}_{symbol}", kind="function", line=1)
                for symbol in range(symbols_per_file)
            ),
        )
        for index in range(count)
    )


def test_fastembed_model_is_loaded_with_bounded_threads_and_batches(
    monkeypatch,
) -> None:
    created: dict = {}

    class FakeTextEmbedding:
        def __init__(self, **kwargs) -> None:
            created.update(kwargs)

        def embed(self, texts, batch_size=256):
            created["batch_size"] = batch_size
            return [np.ones(4, dtype=np.float32) for _ in texts]

    monkeypatch.setitem(
        sys.modules, "fastembed", types.SimpleNamespace(TextEmbedding=FakeTextEmbedding)
    )
    embedder = FastEmbedEmbedder(batch_size=8, threads=2)

    vectors = embedder.embed(["a", "bb"])

    assert created["threads"] == 2
    assert created["batch_size"] == 8
    assert all(vector.dtype == np.float32 for vector in vectors)


def test_fastembed_defaults_are_small() -> None:
    embedder = FastEmbedEmbedder()

    assert embedder.batch_size == 16
    assert embedder.threads in (1, 2)


def test_indexing_embeds_in_groups_and_packs_float32(monkeypatch) -> None:
    monkeypatch.setattr("repolens.graph.store.EMBEDDING_GROUP_SIZE", 3)
    embedder = RecordingEmbedder()
    store = SqliteGraphStore(embedder=embedder)

    records = store.build_embeddings(_files(7))

    assert [len(call) for call in embedder.calls] == [3, 3, 1]
    assert len(records) == 7
    for record in records:
        vector = np.frombuffer(record.vector, dtype="<f4")
        assert vector.shape == (384,)
        assert np.linalg.norm(vector) == pytest.approx(1.0, abs=1e-5)


def test_indexing_stops_between_groups_when_told_to(monkeypatch) -> None:
    monkeypatch.setattr("repolens.graph.store.EMBEDDING_GROUP_SIZE", 2)
    embedder = RecordingEmbedder()
    store = SqliteGraphStore(embedder=embedder)
    answers = iter([True, False])

    records = store.build_embeddings(_files(6), should_continue=lambda: next(answers))

    assert records == ()
    assert len(embedder.calls) == 1


def test_cancelling_during_indexing_stops_the_model(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("repolens.graph.store.EMBEDDING_GROUP_SIZE", 1)
    store_holder: dict = {}

    def cancel_on_first_call(call_index: int) -> None:
        if call_index == 0:
            store = store_holder["store"]
            store.cancel_analysis(store_holder["analysis_id"])

    embedder = RecordingEmbedder(before_call=cancel_on_first_call)
    store = SqliteGraphStore(embedder=embedder)
    store_holder["store"] = store
    executor = ManualExecutor(run_immediately=False)
    runner = PipelineAnalysisRunner(
        resolver=FakeResolver(),
        source=FakeSource(),
        executor=executor,
        work_root=tmp_path,
    )
    started = runner.start(store, REPO_URL, None)
    store_holder["analysis_id"] = started["analysisId"]

    executor.run_pending()

    assert store.get_analysis(started["analysisId"])["status"] == "cancelled"
    # The first group ran; every later one was skipped.
    assert len(embedder.calls) == 1


def test_runner_runs_one_analysis_at_a_time_by_default() -> None:
    runner = PipelineAnalysisRunner(resolver=FakeResolver(), source=FakeSource())

    assert runner._executor._max_workers == 1  # pylint: disable=protected-access


def test_chunk_matrix_matches_pairwise_cosine() -> None:
    rng = random.Random(118)
    pairs = {
        f"file_{index}.py": [
            (f"chunk {index}.{chunk}", tuple(rng.uniform(-1, 1) for _ in range(16)))
            for chunk in range(rng.randint(1, 5))
        ]
        for index in range(30)
    }
    pairs["zero.py"] = [("nothing", (0.0,) * 16)]
    query = tuple(rng.uniform(-1, 1) for _ in range(16))

    best = ChunkVectors.from_pairs(pairs).best_by_path(query)

    expected = {}
    for path, chunks in pairs.items():
        score, text = max(
            ((cosine_similarity(query, vector), text) for text, vector in chunks),
            key=lambda item: item[0],
        )
        if score > 0:
            expected[path] = (score, text)
    assert best.keys() == expected.keys()
    for path, (score, text) in expected.items():
        assert best[path][1] == text
        assert best[path][0] == pytest.approx(score, abs=1e-5)


def test_chunk_matrix_ignores_a_query_of_another_size() -> None:
    vectors = ChunkVectors.from_pairs({"a.py": [("a", (1.0, 0.0))]})

    assert vectors.best_by_path((1.0, 0.0, 0.0)) == {}
    assert ChunkVectors.empty().best_by_path((1.0,)) == {}


def _completed(store: SqliteGraphStore, analysis_id: str, files) -> None:
    store.save(
        AnalysisRecord(
            analysis_id=analysis_id,
            repo=REPO_URL,
            ref=None,
            sha=SHA,
            status="completed",
            files=files,
        )
    )


def test_search_vectors_are_cached_and_refreshed_on_save() -> None:
    store = SqliteGraphStore(embedder=HashEmbedder())
    _completed(store, "analysis-a", _files(3))

    first = store.get_search_embeddings("analysis-a")
    again = store.get_search_embeddings("analysis-a")
    assert first is again
    assert len(first) == 3
    assert first.matrix.dtype == np.float32
    assert store.get_search_documents("analysis-a") == store.get_search_documents(
        "analysis-a"
    )

    _completed(store, "analysis-a", _files(5))

    assert len(store.get_search_embeddings("analysis-a")) == 5
    assert len(store.get_search_documents("analysis-a")) == 5


def test_search_cache_keeps_only_a_few_analyses() -> None:
    store = SqliteGraphStore(embedder=HashEmbedder())
    for name in ("a", "b", "c"):
        _completed(store, f"analysis-{name}", _files(2))
        store.get_search_embeddings(f"analysis-{name}")

    cached = list(store._search_cache)  # pylint: disable=protected-access
    assert cached == ["analysis-b", "analysis-c"]
