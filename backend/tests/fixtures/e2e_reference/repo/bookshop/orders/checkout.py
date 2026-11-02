"""Turning a cart into an order."""

from bookshop.auth.tokens import verify_token
from bookshop.catalog.models import User

from .receipts import send_receipt


def cart_total(user: User) -> int:
    return sum(book.price_cents for book in user.cart)


def place_order(user: User, token: str) -> int:
    if verify_token(token) != user.id:
        raise PermissionError("The token does not match this user.")
    total = cart_total(user)
    send_receipt(user, total)
    user.cart.clear()
    return total
