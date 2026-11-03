"""Settings shared by every part of the bookshop."""

import os

DEBUG = os.environ.get("BOOKSHOP_DEBUG") == "1"
SECRET_KEY = os.environ.get("BOOKSHOP_SECRET", "dev-secret")
PAGE_SIZE: int = 20
