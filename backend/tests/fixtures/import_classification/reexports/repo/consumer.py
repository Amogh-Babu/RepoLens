"""An application that only wants the names library.core re-exports."""

from library.core import Engine, Registry, run_engine


def build() -> Engine:
    """Build the engine from the package's public surface."""
    return run_engine(Registry())
