"""Local text embedding providers and searchable file-chunk construction."""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import math
import os
from pathlib import Path
import re
import threading
from typing import Callable, Protocol

import numpy as np
import numpy.typing as npt

from repolens.search.models import SearchDocument


# One float32 vector. Embedders may return any sequence of floats; the store
# and search convert them with `as_unit_vector`.
Embedding = npt.NDArray[np.float32] | Sequence[float]
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
MODEL_NAME = "BAAI/bge-small-en-v1.5"
# Callers mark a search query by starting it with this; anything else is a
# passage from the repository.
QUERY_MARKER = "query: "
# BGE's own instruction for short retrieval queries. BGE embeds passages as
# they are, with no prefix.
_BGE_QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "
# A file whose whole passage fits in this many words is one chunk.
_MAX_CHUNK_WORDS = 200
# Longer files are split into chunks of names packed up to this many words,
# so a chunk stays about a few related names and still matches sharply.
_PACKED_CHUNK_WORDS = 32
_MAX_CHUNKS_PER_FILE = 16

# Texts per model call. ONNX Runtime's activations grow with batch size times
# the square of the longest text in the batch; 16 keeps a batch's peak in the
# low hundreds of megabytes, where fastembed's default of 256 can need
# gigabytes.
DEFAULT_EMBED_BATCH_SIZE = 16
DEFAULT_BATCH_SIZE = DEFAULT_EMBED_BATCH_SIZE
DEFAULT_MAX_EMBED_THREADS = 2


def _read_resource_file(path: str) -> str | None:
    try:
        return Path(path).read_text(encoding="utf-8")
    except OSError:
        return None


def effective_cpu_count(
    *,
    read_text: Callable[[str], str | None] = _read_resource_file,
    affinity_count: int | None = None,
    host_count: int | None = None,
) -> int:
    """Return CPUs available to this process, including container quotas."""
    if host_count is None:
        host_count = os.cpu_count()
    if affinity_count is None:
        try:
            affinity_count = len(os.sched_getaffinity(0))
        except (AttributeError, OSError):
            affinity_count = None

    limits = [value for value in (host_count, affinity_count) if value and value > 0]
    quota: int | None = None
    cpu_max = read_text("/sys/fs/cgroup/cpu.max")
    if cpu_max:
        fields = cpu_max.split()
        if len(fields) >= 2 and fields[0] != "max":
            try:
                quota = math.ceil(int(fields[0]) / int(fields[1]))
            except (ValueError, ZeroDivisionError):
                pass
    if quota is None:
        quota_text = read_text("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
        period_text = read_text("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
        if quota_text and period_text:
            try:
                quota_value = int(quota_text)
                if quota_value > 0:
                    quota = math.ceil(quota_value / int(period_text))
            except (ValueError, ZeroDivisionError):
                pass
    if quota is not None and quota > 0:
        limits.append(quota)
    return max(1, min(limits, default=1))


class Embedder(Protocol):
    """Turn passages and queries into comparable dense vectors."""

    @property
    def model_id(self) -> str: ...

    def embed(self, texts: Sequence[str]) -> list[Embedding]: ...


class FastEmbedEmbedder:
    """CPU-only local embeddings from FastEmbed's ONNX BGE-small model.

    One model is shared by every analysis and search in the process, and it
    runs one call at a time. Batches and CPU threads are bounded by default.
    """

    def __init__(
        self,
        cache_dir: str | None = None,
        *,
        batch_size: int | None = None,
        threads: int | None = None,
    ) -> None:
        if threads is not None and threads < 1:
            raise ValueError("threads must be at least 1.")
        if batch_size is not None and batch_size < 1:
            raise ValueError("batch_size must be at least 1.")
        self._cache_dir = cache_dir
        self._batch_size = max(1, batch_size or DEFAULT_EMBED_BATCH_SIZE)
        self._threads = max(1, threads) if threads else min(
            DEFAULT_MAX_EMBED_THREADS, effective_cpu_count()
        )
        self._model = None
        self._lock = threading.Lock()
        self._inference_lock = threading.Lock()

    @property
    def model_id(self) -> str:
        # Names the input format too: vectors stored under an earlier format
        # (with "passage: " prefixes) are not compared with these.
        return f"{MODEL_NAME}+bge-query-instruction"

    @property
    def batch_size(self) -> int:
        return self._batch_size

    @property
    def threads(self) -> int | None:
        """Inference threads, bounded by container CPU capacity by default."""
        return self._threads

    def embed(self, texts: Sequence[str]) -> list[Embedding]:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = TextEmbedding(
                        model_name=MODEL_NAME,
                        cache_dir=self._cache_dir,
                        threads=self._threads,
                    )
        inputs = [
            _BGE_QUERY_INSTRUCTION + text.removeprefix(QUERY_MARKER)
            if text.startswith(QUERY_MARKER)
            else text
            for text in texts
        ]
        # The model pads every text in a batch to the batch's longest one.
        # Chunks range from a two-word name to a full paragraph, so in input
        # order nearly every batch is padded to paragraph length. Embedding
        # them shortest first keeps similar lengths together, then the
        # vectors are put back in input order.
        order = sorted(range(len(inputs)), key=lambda index: len(inputs[index]))
        vectors: list[Embedding] = [()] * len(inputs)
        with self._inference_lock:
            for index, vector in zip(
                order,
                self._model.embed(
                    [inputs[index] for index in order], batch_size=self._batch_size
                ),
                strict=True,
            ):
                vectors[index] = np.asarray(vector, dtype=np.float32)
        return vectors


class HashEmbedder:
    """Stable feature-hash embeddings for tests, CI and offline development."""

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions < 8:
            raise ValueError("Embedding dimensions must be at least 8.")
        self._dimensions = dimensions

    @property
    def model_id(self) -> str:
        return f"hash-v1-{self._dimensions}"

    def embed(self, texts: Sequence[str]) -> list[Embedding]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> Embedding:
        vector = [0.0] * self._dimensions
        for token in _TOKEN_PATTERN.findall(text.casefold()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self._dimensions
            vector[index] += 1.0 if digest[4] & 1 else -1.0
        return _normalize(vector)


@dataclass(frozen=True)
class ChunkVectors:
    """Every stored chunk vector of one analysis, as one float32 matrix.

    Row `i` of `matrix` is the unit-length vector of chunk `texts[i]`, which
    belongs to `paths[path_ids[i]]`. One matrix instead of a tuple of Python
    floats per chunk is about 8x smaller and lets a query be scored against
    every chunk in one matrix product.
    """

    paths: tuple[str, ...]
    path_ids: npt.NDArray[np.int32]
    texts: tuple[str, ...]
    matrix: npt.NDArray[np.float32]

    @classmethod
    def empty(cls) -> "ChunkVectors":
        return cls((), np.zeros(0, dtype=np.int32), (), np.zeros((0, 0), np.float32))

    @classmethod
    def from_pairs(
        cls, pairs_by_path: Mapping[str, Sequence[tuple[str, Embedding]]]
    ) -> "ChunkVectors":
        """Build from `{path: [(chunk text, vector), ...]}`.

        Rows whose length differs from the first vector are dropped, as the
        old pairwise comparison scored them zero.
        """
        paths: list[str] = []
        path_ids: list[int] = []
        texts: list[str] = []
        rows: list[npt.NDArray[np.float32]] = []
        dimensions: int | None = None
        for path, pairs in pairs_by_path.items():
            path_index = len(paths)
            paths.append(path)
            for text, vector in pairs:
                row = as_unit_vector(vector)
                if dimensions is None:
                    dimensions = row.shape[0]
                if row.shape[0] != dimensions or dimensions == 0:
                    continue
                path_ids.append(path_index)
                texts.append(text)
                rows.append(row)
        if not rows:
            return cls.empty()
        return cls(
            paths=tuple(paths),
            path_ids=np.asarray(path_ids, dtype=np.int32),
            texts=tuple(texts),
            matrix=np.vstack(rows),
        )

    @property
    def dimensions(self) -> int:
        return int(self.matrix.shape[1]) if self.matrix.ndim == 2 else 0

    def __len__(self) -> int:
        return len(self.texts)

    def best_by_path(self, query: Embedding) -> dict[str, tuple[float, str]]:
        """Return each path's best cosine similarity to `query` and its chunk.

        Only positive similarities are returned, matching how search uses
        them. Ties go to the earlier chunk.
        """
        query_vector = as_unit_vector(query)
        if not len(self) or query_vector.shape[0] != self.dimensions:
            return {}
        scores = self.matrix @ query_vector
        # Best chunk first within each path; earlier chunks win ties.
        order = np.lexsort((np.arange(len(scores)), -scores, self.path_ids))
        sorted_ids = self.path_ids[order]
        first = np.flatnonzero(np.r_[True, sorted_ids[1:] != sorted_ids[:-1]])
        best: dict[str, tuple[float, str]] = {}
        for row in order[first]:
            score = float(scores[row])
            if score > 0:
                best[self.paths[int(self.path_ids[row])]] = (score, self.texts[row])
        return best


def as_unit_vector(vector: Embedding) -> npt.NDArray[np.float32]:
    """Return `vector` as a float32 array scaled to unit length.

    A zero vector stays zero, so it scores zero against everything.
    """
    array = np.asarray(vector, dtype=np.float32).reshape(-1)
    norm = float(np.linalg.norm(array))
    if norm == 0 or not math.isfinite(norm):
        return np.zeros_like(array)
    return array / np.float32(norm)


def document_text(document: SearchDocument) -> str:
    """Create the one-file passage used for semantic indexing."""
    segments = [
        _expand_words(document.path),
        *(_expand_words(symbol) for symbol in document.symbols),
        *(_expand_words(member) for member in document.members),
        *(_expand_words(reference) for reference in document.references),
    ]
    return "\n".join(segment.strip() for segment in segments if segment.strip())


def document_chunks(document: SearchDocument) -> list[str]:
    """Split long file passages into bounded, independently searchable chunks.

    A short file is one chunk. A longer one is split into chunks of a few
    names each, packed in source order (symbols, then members, then imports)
    up to `_PACKED_CHUNK_WORDS` words with the path in front. Packing several
    short names per chunk, rather than one chunk per name, keeps the chunk
    count, and so indexing time and memory, bounded on large files (#118).
    """
    body = document_text(document)
    words = body.split()
    if len(words) <= _MAX_CHUNK_WORDS:
        return [body] if body else []

    prefix = _expand_words(document.path)
    budget = max(1, _PACKED_CHUNK_WORDS - len(prefix.split()))
    chunks: list[str] = []
    current: list[str] = []
    for name in (*document.symbols, *document.members, *document.references):
        name_words = _expand_words(name).split()
        if not name_words:
            continue
        if current and len(current) + len(name_words) > budget:
            chunks.append(" ".join(current))
            current = []
        # A single name longer than the budget is cut into budget-sized parts.
        while len(name_words) > budget:
            chunks.append(" ".join(name_words[:budget]))
            name_words = name_words[budget:]
        current.extend(name_words)
    if current:
        chunks.append(" ".join(current))
    if len(chunks) > _MAX_CHUNKS_PER_FILE:
        stride = math.ceil(len(chunks) / _MAX_CHUNKS_PER_FILE)
        chunks = chunks[::stride][:_MAX_CHUNKS_PER_FILE]
    return [f"{prefix}\n{chunk}" for chunk in chunks]


def cosine_similarity(left: Embedding, right: Embedding) -> float:
    """Return the cosine similarity of two vectors, or 0 when undefined."""
    if len(left) != len(right) or not len(left):
        return 0.0
    left_norm = math.sqrt(sum(float(value) * float(value) for value in left))
    right_norm = math.sqrt(sum(float(value) * float(value) for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(float(a) * float(b) for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )


def _expand_words(value: str) -> str:
    separated = _CAMEL_BOUNDARY.sub(r"\1 \2", value.replace("_", " "))
    return " ".join(_TOKEN_PATTERN.findall(separated))


def _normalize(values: Iterable[float]) -> Embedding:
    vector = tuple(values)
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return tuple(value / magnitude for value in vector)
