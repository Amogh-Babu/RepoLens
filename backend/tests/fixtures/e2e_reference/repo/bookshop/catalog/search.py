"""Finding books by title."""

import requests

from bookshop.catalog.models import Book
from bookshop.config import PAGE_SIZE

CATALOG_URL = "https://example.com/catalog.json"


def search_books(query: str) -> list[Book]:
    books = [Book(**row) for row in requests.get(CATALOG_URL, timeout=5).json()]
    needle = query.casefold()
    matches = [book for book in books if needle in book.title.casefold()]
    return matches[:PAGE_SIZE]
