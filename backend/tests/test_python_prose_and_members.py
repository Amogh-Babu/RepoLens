"""Docstrings, comments, and class members from the Python analyzer (#77).

These widen what search can find without changing `symbols`, which stay the
module-level declarations shown in the file detail panel.
"""

import textwrap

from repolens.analysis import PythonAnalyzer
from repolens.analysis.adapter import to_analyzed_file


def _analyze(source: str):
    return PythonAnalyzer().analyze("pkg/module.py", textwrap.dedent(source).lstrip("\n"))


def _members(source: str) -> list[tuple[str, str, str, int]]:
    return [(m.owner, m.name, m.kind, m.line) for m in _analyze(source).members]


def _prose(source: str) -> list[tuple[int, str, str]]:
    return [(c.line, c.kind, c.text) for c in _analyze(source).comments]


def test_methods_and_class_attributes_are_members_of_their_class() -> None:
    source = """
        from dataclasses import dataclass

        @dataclass
        class User:
            id: str
            cart: list = None
            LIMIT = 3

            def check_password(self, password):
                return True

            async def refresh(self):
                pass
        """

    assert _members(source) == [
        ("User", "id", "attribute", 5),
        ("User", "cart", "attribute", 6),
        ("User", "LIMIT", "attribute", 7),
        ("User", "check_password", "method", 9),
        ("User", "refresh", "method", 12),
    ]


def test_attributes_assigned_through_the_receiver_are_members() -> None:
    source = """
        class Cart:
            def __init__(this, owner):
                this.owner = owner
                this.items: list = []
                other.flag = True

            def add(self, item):
                self.count += 1
                self.owner = item
        """

    assert _members(source) == [
        ("Cart", "__init__", "method", 2),
        ("Cart", "add", "method", 7),
        ("Cart", "owner", "attribute", 3),
        ("Cart", "items", "attribute", 4),
        ("Cart", "count", "attribute", 8),
    ]


def test_members_do_not_change_the_module_level_symbols() -> None:
    parsed = _analyze(
        """
        class Cart:
            def total(self):
                def helper():
                    pass
                return 0
        """
    )

    assert [(s.name, s.kind) for s in parsed.symbols] == [("Cart", "class")]
    assert [m.name for m in parsed.members] == ["total"]


def test_static_methods_without_parameters_have_no_receiver() -> None:
    source = """
        class Tools:
            @staticmethod
            def build():
                x = 1
        """

    assert _members(source) == [("Tools", "build", "method", 3)]


def test_docstrings_of_the_module_classes_functions_and_methods() -> None:
    source = '''
        """Turning a cart into an order."""

        def cart_total(user):
            """Sum the prices in the cart."""

            def nested():
                """Not part of the file's story."""

        class Order:
            """A placed order.

            Orders are immutable.
            """

            def cancel(self):
                """Cancel the order."""
        '''

    assert _prose(source) == [
        (1, "docstring", "Turning a cart into an order."),
        (4, "docstring", "Sum the prices in the cart."),
        (10, "docstring", "A placed order.\n\nOrders are immutable."),
        (16, "docstring", "Cancel the order."),
    ]


def test_consecutive_comment_lines_form_one_block() -> None:
    source = """
        # Compute the cart total
        # including tax.

        # A separate thought.
        TAX = 1  # flat rate
        RATE = 2
        """

    assert _prose(source) == [
        (1, "comment", "Compute the cart total including tax."),
        (4, "comment", "A separate thought."),
        (5, "comment", "flat rate"),
    ]


def test_tool_directives_and_file_headers_are_not_prose() -> None:
    source = """
        #!/usr/bin/env python
        # -*- coding: utf-8 -*-
        # vim: set ft=python:
        import os  # noqa: F401
        x = []  # type: list[int]
        y = 1  # pragma: no cover
        #
        # Real explanation.
        """

    assert _prose(source) == [(8, "comment", "Real explanation.")]


def test_a_comment_after_code_does_not_join_the_next_block() -> None:
    source = """
        x = 1  # trailing
        # leading
        y = 2
        """

    assert _prose(source) == [(1, "comment", "trailing"), (2, "comment", "leading")]


def test_very_long_prose_is_clipped() -> None:
    long_text = "word " * 1000
    parsed = _analyze(f'"""{long_text}"""\n')

    (docstring,) = parsed.comments
    assert len(docstring.text) <= 2000
    assert docstring.text.endswith("…")


def test_an_unparsable_file_reports_no_prose_or_members() -> None:
    parsed = _analyze(
        """
        # a comment
        def broken(:
        """
    )

    assert not parsed.parsed
    assert parsed.comments == ()
    assert parsed.members == ()


def test_the_adapter_carries_prose_and_members_into_storable_records() -> None:
    stored = to_analyzed_file(
        _analyze(
            '''
            """Checkout."""
            class Cart:
                def total(self):  # sum it
                    pass
            '''
        )
    )

    assert [(c.line, c.kind, c.text) for c in stored.comments] == [
        (1, "docstring", "Checkout."),
        (3, "comment", "sum it"),
    ]
    assert [(m.qualified_name, m.kind, m.line) for m in stored.members] == [
        ("Cart.total", "method", 3)
    ]
