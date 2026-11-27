"""Resource limits on semantic indexing and analysis concurrency (#118).

The embedding model is faked: these tests check how much work is asked of it
and what happens around it, never real inference.
"""

from collections.abc import Sequence
from pathlib import Path
import struct
import threading

from fastapi.testclient import TestClient
import pytest

from repolens.api.app import create_app
from repolens.api.server import create_server_from_environment
from repolens.graph import SqliteGraphStore
from repolens.graph.models import AnalyzedFile, CommentRecord, SymbolRecord
from repolens.graph.store import IndexingCancelled, _search_document
from repolens.pipeline import PipelineAnalysisRunner
from repolens.pipeline.runner import DEFAULT_MAX_CONCURRENT_ANALYSES
from repolens.resources import ResourceConfigError, ResourceLimits, create_embedder
from repolens.search.embedding import FastEmbedEmbedder, HashEmbedder

from test_pipeline_runner import REPO_URL, FakeResolver, FakeSource, ManualExecutor


class RecordingEmbedder:
    """Hash vectors, remembering how many texts each call was given."""

    def __init__(self, batch_size: int = 4) -> None:
        self.batch_size = batch_size
        self.calls: list[int] = []
        self._hash = HashEmbedder(dimensions=16)

    @property
    def model_id(self) -> str:
        return "recording"

    def embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        self.calls.append(len(texts))
        return self._hash.embed(texts)


def _files(count: int) -> tuple[AnalyzedFile, ...]:
    """`count` small parsed files, one chunk each."""
    return tuple(
        AnalyzedFile(
            path=f"pkg/module_{index}.py",
            parsed=True,
            symbols=(SymbolRecord(name=f"handler_{index}", kind="function", line=1),),
        )
        for index in range(count)
    )


# --- configuration ----------------------------------------------------------


def test_defaults_fit_a_small_machine() -> None:
    limits = ResourceLimits.from_environment({})

    assert limits == ResourceLimits(
        embeddings_enabled=True,
        embedding_threads=2,
        embedding_batch_size=16,
        max_embedding_chunks=10_000,
        max_concurrent_analyses=1,
    )
    assert DEFAULT_MAX_CONCURRENT_ANALYSES == 1


def test_reads_every_limit_from_the_environment() -> None:
    limits = ResourceLimits.from_environment(
        {
            "REPOLENS_EMBEDDINGS_ENABLED": "false",
            "REPOLENS_EMBEDDING_THREADS": "4",
            "REPOLENS_EMBEDDING_BATCH_SIZE": " 8 ",
            "REPOLENS_MAX_EMBEDDING_CHUNKS": "500",
            "REPOLENS_MAX_CONCURRENT_ANALYSES": "2",
        }
    )

    assert limits == ResourceLimits(False, 4, 8, 500, 2)


def test_existing_setting_names_and_new_name_precedence() -> None:
    limits = ResourceLimits.from_environment(
        {
            "REPOLENS_EMBED_THREADS": "3",
            "REPOLENS_EMBED_BATCH_SIZE": "24",
            "REPOLENS_EMBEDDING_BATCH_SIZE": "8",
        }
    )
    assert limits.embedding_threads == 3
    assert limits.embedding_batch_size == 8


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("REPOLENS_EMBEDDINGS_ENABLED", "maybe"),
        ("REPOLENS_EMBEDDING_THREADS", "0"),
        ("REPOLENS_EMBEDDING_BATCH_SIZE", "lots"),
        ("REPOLENS_MAX_EMBEDDING_CHUNKS", "-1"),
        ("REPOLENS_MAX_CONCURRENT_ANALYSES", "1.5"),
    ],
)
def test_rejects_invalid_limits_at_startup(name: str, value: str) -> None:
    with pytest.raises(ResourceConfigError, match=name):
        ResourceLimits.from_environment({name: value})


def test_disabled_embeddings_create_no_model() -> None:
    assert create_embedder(ResourceLimits(embeddings_enabled=False)) is None


def test_embedder_gets_the_thread_and_batch_limits(monkeypatch) -> None:
    created: dict[str, object] = {}

    class FakeTextEmbedding:
        def __init__(self, **kwargs: object) -> None:
            created.update(kwargs)

        def embed(self, texts, batch_size):
            created["batch_size"] = batch_size
            return [(1.0, 0.0) for _ in texts]

    import fastembed

    monkeypatch.setattr(fastembed, "TextEmbedding", FakeTextEmbedding)
    embedder = create_embedder(
        ResourceLimits(embedding_threads=3, embedding_batch_size=16),
        {"REPOLENS_EMBEDDING_CACHE": "/models"},
    )
    assert isinstance(embedder, FastEmbedEmbedder)

    embedder.embed(["a", "b"])

    assert created["threads"] == 3
    assert created["cache_dir"] == "/models"
    assert created["batch_size"] == 16


def test_model_calls_run_one_at_a_time() -> None:
    running = 0
    most = 0
    lock = threading.Lock()

    class SlowModel:
        def embed(self, texts, batch_size):
            nonlocal running, most
            with lock:
                running += 1
                most = max(most, running)
            threading.Event().wait(0.05)
            with lock:
                running -= 1
            return [(1.0,) for _ in texts]

    embedder = FastEmbedEmbedder()
    embedder._model = SlowModel()
    threads = [threading.Thread(target=embedder.embed, args=(["x"],)) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert most == 1


def test_server_applies_the_limits_from_its_environment(tmp_path: Path) -> None:
    server = create_server_from_environment(
        {
            "REPOLENS_DB_PATH": str(tmp_path / "repolens.db"),
            "REPOLENS_EMBEDDINGS_ENABLED": "false",
            "REPOLENS_MAX_EMBEDDING_CHUNKS": "7",
        },
        runner=PipelineAnalysisRunner(
            resolver=FakeResolver(), source=FakeSource(), executor=ManualExecutor()
        ),
    )

    store = server.routes[0].app.state.store  # type: ignore[attr-defined]
    assert store.embedder is None
    assert store._max_embedding_chunks == 7


# --- bounded indexing -------------------------------------------------------


def test_embeds_in_batches_no_larger_than_the_batch_size() -> None:
    embedder = RecordingEmbedder(batch_size=4)
    store = SqliteGraphStore(embedder=embedder)

    index = store.build_semantic_index(_files(10))

    assert index.status == "complete"
    assert index.chunk_count == 10
    assert embedder.calls == [4, 4, 2]
    assert len(index.records) == 10


def test_vectors_are_packed_float32_in_chunk_order() -> None:
    embedder = RecordingEmbedder()
    store = SqliteGraphStore(embedder=embedder)
    files = _files(3)

    index = store.build_semantic_index(files)

    assert [record.path for record in index.records] == [file.path for file in files]
    for record in index.records:
        assert isinstance(record.vector, bytes)
        assert len(record.vector) == 16 * 4
        expected = HashEmbedder(dimensions=16).embed([record.text])[0]
        assert struct.unpack("<16f", record.vector) == pytest.approx(expected, abs=1e-6)


def test_search_document_keeps_every_field_main_indexed() -> None:
    """Indexing hands the chunker the same document main built, prose included."""
    file = AnalyzedFile(
        path="pkg/config.py",
        symbols=(SymbolRecord(name="load_config", kind="function", line=3),),
        comments=(
            CommentRecord(line=1, text="Reads settings from disk.", kind="comment"),
            CommentRecord(line=4, text="Parse the YAML file.", kind="docstring"),
        ),
    )

    document = _search_document(file)

    assert document.comments == ("Reads settings from disk.",)
    assert document.docstrings == ("Parse the YAML file.",)
    assert document.symbols == ("load_config",)


def test_over_budget_repository_is_not_embedded_and_says_so() -> None:
    embedder = RecordingEmbedder()
    store = SqliteGraphStore(embedder=embedder, max_embedding_chunks=5)

    index = store.build_semantic_index(_files(6))

    assert index.status == "over_budget"
    assert index.chunk_count == 6
    assert index.records == ()
    assert embedder.calls == []


def test_budget_counts_chunks_not_files() -> None:
    embedder = RecordingEmbedder()
    store = SqliteGraphStore(embedder=embedder, max_embedding_chunks=5)

    index = store.build_semantic_index(_files(5))

    assert index.status == "complete"


def test_without_an_embedder_indexing_is_disabled() -> None:
    assert SqliteGraphStore().build_semantic_index(_files(2)).status == "disabled"


def test_nothing_to_embed_is_empty() -> None:
    store = SqliteGraphStore(embedder=RecordingEmbedder())

    assert store.build_semantic_index(()).status == "empty"


def test_a_failing_model_falls_back_without_vectors() -> None:
    class FailingEmbedder(RecordingEmbedder):
        def embed(self, texts):
            super().embed(texts)
            if len(self.calls) == 2:
                raise RuntimeError("out of memory")
            return self._hash.embed(texts)

    store = SqliteGraphStore(embedder=FailingEmbedder(batch_size=2))

    index = store.build_semantic_index(_files(6))

    assert index.status == "failed"
    assert index.records == ()


def test_stops_between_batches_once_cancelled() -> None:
    embedder = RecordingEmbedder(batch_size=2)
    store = SqliteGraphStore(embedder=embedder)
    checks = iter([True, True, False])

    with pytest.raises(IndexingCancelled):
        store.build_semantic_index(_files(10), should_continue=lambda: next(checks))

    assert embedder.calls == [2, 2]


def test_indexing_does_not_hold_the_store_lock() -> None:
    """Requests are answered while the model works."""
    store_holder: list[SqliteGraphStore] = []
    answered: list[bool] = []

    class ProbingEmbedder(RecordingEmbedder):
        def embed(self, texts):
            def probe() -> None:
                acquired = store_holder[0]._lock.acquire(timeout=1)
                if acquired:
                    store_holder[0]._lock.release()
                answered.append(acquired)

            thread = threading.Thread(target=probe)
            thread.start()
            thread.join()
            return super().embed(texts)

    store = SqliteGraphStore(embedder=ProbingEmbedder())
    store_holder.append(store)

    store.build_semantic_index(_files(3))

    assert answered and all(answered)


# --- the pipeline and the API -----------------------------------------------


def _pipeline_client(store: SqliteGraphStore, tmp_path: Path, executor=None) -> TestClient:
    runner = PipelineAnalysisRunner(
        resolver=FakeResolver(),
        source=FakeSource(),
        executor=executor or ManualExecutor(),
        work_root=tmp_path,
    )
    return TestClient(create_app(store, runner=runner))


def test_completed_analysis_reports_its_semantic_index(tmp_path: Path) -> None:
    client = _pipeline_client(SqliteGraphStore(embedder=RecordingEmbedder()), tmp_path)

    analysis_id = client.post("/analyses", json={"url": REPO_URL}).json()["analysisId"]
    body = client.get(f"/analyses/{analysis_id}").json()
    search = client.get(f"/analyses/{analysis_id}/search", params={"q": "billing"})

    assert body["semanticSearch"]["status"] == "complete"
    assert body["semanticSearch"]["chunks"] > 0
    assert search.json()["semanticStatus"] == "complete"


def test_over_budget_analysis_keeps_keyword_search_and_says_why(tmp_path: Path) -> None:
    embedder = RecordingEmbedder()
    store = SqliteGraphStore(embedder=embedder, max_embedding_chunks=1)
    client = _pipeline_client(store, tmp_path)

    analysis_id = client.post("/analyses", json={"url": REPO_URL}).json()["analysisId"]
    body = client.get(f"/analyses/{analysis_id}").json()
    search = client.get(f"/analyses/{analysis_id}/search", params={"q": "billing"})

    assert body["status"] == "completed"
    assert body["semanticSearch"]["status"] == "over_budget"
    assert search.status_code == 200
    assert search.json()["semanticStatus"] == "over_budget"
    assert "app/services/billing.py" in {r["path"] for r in search.json()["results"]}
    # Neither indexing nor the query used the model.
    assert embedder.calls == []
    assert client.get(f"/analyses/{analysis_id}/graph").status_code == 200


def test_disabled_embeddings_report_keyword_only_search(tmp_path: Path) -> None:
    client = _pipeline_client(SqliteGraphStore(), tmp_path)

    analysis_id = client.post("/analyses", json={"url": REPO_URL}).json()["analysisId"]
    search = client.get(f"/analyses/{analysis_id}/search", params={"q": "billing"})

    assert client.get(f"/analyses/{analysis_id}").json()["semanticSearch"] == {
        "status": "disabled",
        "chunks": 0,
    }
    assert search.json()["semanticStatus"] == "disabled"
    assert search.json()["results"]


def test_cancelling_during_indexing_saves_nothing(tmp_path: Path) -> None:
    store_holder: list[SqliteGraphStore] = []
    cancel_after_first_batch: list[str] = []

    class CancellingEmbedder(RecordingEmbedder):
        def embed(self, texts):
            if not self.calls:
                store_holder[0].cancel_analysis(cancel_after_first_batch[0])
            return super().embed(texts)

    embedder = CancellingEmbedder(batch_size=1)
    store = SqliteGraphStore(embedder=embedder)
    store_holder.append(store)
    executor = ManualExecutor(run_immediately=False)
    client = _pipeline_client(store, tmp_path, executor=executor)

    analysis_id = client.post("/analyses", json={"url": REPO_URL}).json()["analysisId"]
    cancel_after_first_batch.append(analysis_id)
    executor.run_pending()

    assert embedder.calls == [1]
    assert client.get(f"/analyses/{analysis_id}").json()["status"] == "cancelled"
    rows = store._conn.execute("SELECT COUNT(*) FROM embeddings;").fetchone()[0]
    files = store._conn.execute("SELECT COUNT(*) FROM files;").fetchone()[0]
    assert (rows, files) == (0, 0)


def test_default_runner_runs_one_analysis_at_a_time() -> None:
    runner = PipelineAnalysisRunner(resolver=FakeResolver(), source=FakeSource())

    assert runner._executor._max_workers == 1  # type: ignore[attr-defined]


def test_runner_rejects_a_zero_concurrency_limit() -> None:
    with pytest.raises(ValueError):
        PipelineAnalysisRunner(max_concurrent_analyses=0)


# --- search scoring ---------------------------------------------------------


def test_streaming_scores_match_the_full_vector_scores() -> None:
    """`semantic_matches` ranks files the same as scoring every stored vector."""
    embedder = HashEmbedder(dimensions=64)
    store = SqliteGraphStore(embedder=embedder)
    from test_graph_store import _sample_analysis

    store.save(_sample_analysis())
    query = embedder.embed(["service handler main"])[0]

    streamed = store.semantic_matches("analysis-1", query)
    expected = store.get_search_embeddings("analysis-1").best_by_path(query)

    assert streamed.keys() == expected.keys()
    for path, (score, text) in expected.items():
        assert streamed[path][0] == pytest.approx(score, abs=1e-5)
        assert streamed[path][1] == text
