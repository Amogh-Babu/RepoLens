"""Resource limits for one RepoLens server process, read from the environment.

Semantic indexing runs a local ONNX model (BGE-small through FastEmbed) on
the CPU. Its memory grows with the inference batch size times the square of
the longest chunk in the batch, and by default ONNX Runtime starts one thread
per core it can see, which in a container is every host core, not the
container's CPU quota. These limits keep one process inside a small machine
(4 cores, 4 GB): see `docs/system-requirements.md` for the measurements
behind the defaults.

- `REPOLENS_EMBEDDINGS_ENABLED`: `false` turns semantic indexing off; search
  is then keyword-only and says so.
- `REPOLENS_EMBEDDING_THREADS`: ONNX Runtime threads for the model.
- `REPOLENS_EMBEDDING_BATCH_SIZE`: chunks per inference call.
- `REPOLENS_MAX_EMBEDDING_CHUNKS`: the most chunks one analysis may embed;
  a larger repository keeps its map and keyword search but gets no semantic
  index, and search says why.
- `REPOLENS_MAX_CONCURRENT_ANALYSES`: analyses that run at once; more wait
  in a queue.
"""

from collections.abc import Mapping
from dataclasses import dataclass
import os

from repolens.search.embedding import (
    DEFAULT_BATCH_SIZE,
    DEFAULT_MAX_EMBED_THREADS,
    FastEmbedEmbedder,
    effective_cpu_count,
)


class ResourceConfigError(ValueError):
    """Raised when a `REPOLENS_*` resource variable is not a valid value."""


@dataclass(frozen=True)
class ResourceLimits:
    embeddings_enabled: bool = True
    embedding_threads: int = 2
    embedding_batch_size: int = DEFAULT_BATCH_SIZE
    max_embedding_chunks: int = 10_000
    max_concurrent_analyses: int = 1

    def __post_init__(self) -> None:
        for name in (
            "embedding_threads",
            "embedding_batch_size",
            "max_embedding_chunks",
            "max_concurrent_analyses",
        ):
            if getattr(self, name) < 1:
                raise ResourceConfigError(f"{name} must be at least 1.")

    @classmethod
    def from_environment(
        cls, environ: Mapping[str, str] = os.environ
    ) -> "ResourceLimits":
        """Read the limits, using the defaults for unset or empty variables."""
        defaults = cls()
        return cls(
            embeddings_enabled=_boolean(
                environ, "REPOLENS_EMBEDDINGS_ENABLED", defaults.embeddings_enabled
            ),
            embedding_threads=_positive_alias(
                environ, "REPOLENS_EMBEDDING_THREADS", "REPOLENS_EMBED_THREADS",
                min(DEFAULT_MAX_EMBED_THREADS, effective_cpu_count()),
            ),
            embedding_batch_size=_positive_alias(
                environ, "REPOLENS_EMBEDDING_BATCH_SIZE", "REPOLENS_EMBED_BATCH_SIZE",
                defaults.embedding_batch_size,
            ),
            max_embedding_chunks=_positive(
                environ, "REPOLENS_MAX_EMBEDDING_CHUNKS", defaults.max_embedding_chunks
            ),
            max_concurrent_analyses=_positive(
                environ,
                "REPOLENS_MAX_CONCURRENT_ANALYSES",
                defaults.max_concurrent_analyses,
            ),
        )


def create_embedder(
    limits: ResourceLimits, environ: Mapping[str, str] = os.environ
) -> FastEmbedEmbedder | None:
    """The process's one embedding model, or None with embeddings disabled.

    The model itself loads on first use (`REPOLENS_EMBEDDING_CACHE` names
    where its files are kept).
    """
    if not limits.embeddings_enabled:
        return None
    return FastEmbedEmbedder(
        cache_dir=environ.get("REPOLENS_EMBEDDING_CACHE", "").strip() or None,
        threads=limits.embedding_threads,
        batch_size=limits.embedding_batch_size,
    )


_TRUE = frozenset({"1", "true", "yes", "on"})
_FALSE = frozenset({"0", "false", "no", "off"})


def _positive_alias(
    environ: Mapping[str, str], name: str, alias: str, default: int
) -> int:
    selected = name if environ.get(name, "").strip() else alias
    return _positive(environ, selected, default)


def _boolean(environ: Mapping[str, str], name: str, default: bool) -> bool:
    value = environ.get(name, "").strip().casefold()
    if not value:
        return default
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    raise ResourceConfigError(f"{name} must be true or false, not {value!r}.")


def _positive(environ: Mapping[str, str], name: str, default: int) -> int:
    value = environ.get(name, "").strip()
    if not value:
        return default
    try:
        number = int(value)
    except ValueError:
        raise ResourceConfigError(
            f"{name} must be a whole number, not {value!r}."
        ) from None
    if number < 1:
        raise ResourceConfigError(f"{name} must be at least 1, not {number}.")
    return number
