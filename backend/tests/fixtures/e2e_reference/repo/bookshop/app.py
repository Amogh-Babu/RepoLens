"""Builds the bookshop application from its parts."""

from . import config
from .auth import login_required
from .catalog.search import search_books
from .orders import checkout


class App:
    """A minimal application object."""

    def __init__(self, debug: bool) -> None:
        self.debug = debug
        self.routes = {"search": search_books, "order": login_required(checkout)}

    def run(self, args: list[str]) -> int:
        return 0 if args or not self.debug else 1


def create_app() -> App:
    return App(debug=config.DEBUG)
