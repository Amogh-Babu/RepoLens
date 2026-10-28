"""Command line entry point for the mini repository."""

import argparse
import os.path

from app.config import DEFAULT_TIMEOUT, Settings
from app.services.billing import InvoiceCalculator

VERSION = "1.0.0"
DEBUG: bool = False


def build_parser() -> argparse.ArgumentParser:
    """Build the command line parser for a billing run."""
    parser = argparse.ArgumentParser(prog="mini")
    parser.add_argument("--config", default=os.path.join(".", "mini.toml"))
    return parser


async def run(settings: Settings) -> float:
    """Report the invoice total for the given settings."""
    from app.services import billing  # Imported lazily to keep startup fast.

    calculator = billing.InvoiceCalculator(settings.tax_rate)
    return calculator.total(DEFAULT_TIMEOUT)


def main() -> float:
    """Parse arguments and run a billing report."""
    build_parser().parse_args()
    return 0.0
