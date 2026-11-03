"""Store-wide configuration, two packages above the order modules."""

import os
from pathlib import Path

DEFAULT_CURRENCY = "USD"
DATA_DIR = Path(os.environ.get("STORE_DATA_DIR", "/var/lib/store"))
