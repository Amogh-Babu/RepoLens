"""Invoice calculation and billing operations."""

# Calculate invoice totals and format billing summaries.


def calculate_invoice(subtotal: float, tax: float) -> float:
    """Return the total amount due for an invoice."""
    return subtotal + tax