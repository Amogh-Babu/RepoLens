"""Command-line entry point for the bookshop."""

import sys

from bookshop.app import create_app


def main() -> int:
    app = create_app()
    return app.run(sys.argv[1:])


if __name__ == "__main__":
    sys.exit(main())
