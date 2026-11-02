"""Checkout tests for the reference repository (never run by RepoLens)."""

from bookshop.auth.tokens import issue_token
from bookshop.catalog.models import Book, User
from bookshop.orders.checkout import cart_total, place_order


def test_place_order_empties_the_cart():
    user = User(id="ada", password_hash="pw", cart=[Book("1", "Dune", "Herbert", 999)])
    assert place_order(user, issue_token("ada")) == 999
    assert cart_total(user) == 0
