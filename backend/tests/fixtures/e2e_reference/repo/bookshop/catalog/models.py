"""Books and users stored by the bookshop."""

from dataclasses import dataclass, field


@dataclass
class Book:
    isbn: str
    title: str
    author: str
    price_cents: int


@dataclass
class User:
    id: str
    password_hash: str
    cart: list[Book] = field(default_factory=list)

    def check_password(self, password: str) -> bool:
        return password == self.password_hash
