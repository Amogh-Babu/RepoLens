"""The library package forwards the core registry and every plugin name."""

from library.core import Registry
from library.plugins import *

__all__ = ["Registry"]
