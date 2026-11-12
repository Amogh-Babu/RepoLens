"""Local text embedding providers and searchable file-chunk construction."""

from collections.abc import Iterable, Sequence
import hashlib
import math
import re
import threading
from typing import Protocol

from repolens.search.models import SearchDocument


Embedding = tuple[float, ...]
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")
_CAMEL_BOUNDARY = re.compile(r"([a-z0-9])([A-Z])")
MODEL_NAME = "BAAI/bge-small-en-v1.5"
_MAX_CHUNK_WORDS = 160
_MAX_CHUNKS_PER_FILE = 64


class Embedder(Protocol):
    """Turn passages and queries into comparable dense vectors."""

    @property
    def model_id(self) -> str: ...

    def embed(self, texts: Sequence[str]) -> list[Embedding]: ...


class FastEmbedEmbedder:
    """CPU-only local embeddings from FastEmbed's ONNX BGE-small model."""

    def __init__(self, cache_dir: str | None = None) -> None:
        self._cache_dir = cache_dir
        self._model = None
        self._lock = threading.Lock()

    @property
    def model_id(self) -> str:
        return MODEL_NAME

    def embed(self, texts: Sequence[str]) -> list[Embedding]:
        if self._model is None:
            with self._lock:
                if self._model is None:
                    from fastembed import TextEmbedding

                    self._model = TextEmbedding(
                        model_name=MODEL_NAME,
                        cache_dir=self._cache_dir,
                    )
        passages = [
            text if text.startswith("query: ") else f"passage: {text}"
            for text in texts
        ]
        return [
            tuple(float(value) for value in vector)
            for vector in self._model.embed(passages)
        ]


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


def document_text(document: SearchDocument) -> str:
    """Create the one-file passage used for semantic indexing."""
    segments = [
        _expand_words(document.path),
        *(_expand_words(symbol) for symbol in document.symbols),
        *(_expand_words(member) for member in document.members),
        *(_expand_words(reference) for reference in document.references),
        *document.docstrings,
        *document.comments,
    ]
    return "\n".join(segment.strip() for segment in segments if segment.strip())


def document_chunks(document: SearchDocument) -> list[str]:
    """Split long file passages into bounded, independently searchable chunks."""
    body = document_text(document)
    words = body.split()
    if len(words) <= _MAX_CHUNK_WORDS:
        return [body] if body else []

    segments = [
        _expand_words(symbol)
        for symbol in (*document.symbols, *document.members, *document.references)
    ]
    segments.extend(document.docstrings)
    segments.extend(document.comments)
    prefix = _expand_words(document.path)
    chunk_words = max(1, _MAX_CHUNK_WORDS - len(prefix.split()))
    chunks = []
    for segment in segments:
        segment_words = segment.split()
        chunks.extend(
            " ".join(segment_words[start : start + chunk_words])
            for start in range(0, len(segment_words), chunk_words)
        )
    if len(chunks) > _MAX_CHUNKS_PER_FILE:
        stride = math.ceil(len(chunks) / _MAX_CHUNKS_PER_FILE)
        chunks = chunks[::stride][:_MAX_CHUNKS_PER_FILE]
    return [f"{prefix}\n{chunk}" for chunk in chunks]


def cosine_similarity(left: Embedding, right: Embedding) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
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