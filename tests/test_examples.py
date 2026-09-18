"""The example programs are part of the test suite, not decoration.

Each one's expected output is written out here, so an example that stops
working fails CI instead of quietly misleading whoever reads it next.
"""

from __future__ import annotations

import pytest

from .conftest import execute

EXPECTED = {
    "fizzbuzz.pb": [
        "1 2 Fizz 4 Buzz Fizz 7 8 Fizz Buzz 11 Fizz 13 14 FizzBuzz",
    ],
    "closures.pb": [
        "[1, 2, 3, 1]",
        "15",
        "[0, 1, 4]",
        "[3, 3, 3]",
    ],
    "sort.pb": [
        "[1, 2, 3, 3, 4, 5, 6, 7, 8, 9]",
        "7",
        "-1",
        "[9, 3, 7, 1, 8, 3, 5, 2, 6, 4]",
    ],
    "wordcount.pb": [
        "the: 3",
        "fox: 2",
        "brown: 1",
    ],
}


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_example_output(examples, name):
    lines, _ = execute((examples / name).read_text(encoding="utf-8"))
    assert lines == EXPECTED[name]


def test_every_example_is_covered(examples):
    """A new example must come with its expected output."""
    on_disk = {path.name for path in examples.glob("*.pb")}
    assert on_disk == set(EXPECTED)
