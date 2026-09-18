"""Turning source into tokens, and refusing source that is not."""

from __future__ import annotations

import pytest

from pebble import LexError, tokenize
from pebble.tokens import Kind


def kinds(source: str) -> list[Kind]:
    return [token.kind for token in tokenize(source)]


def test_an_empty_program_is_one_token():
    assert kinds("") == [Kind.EOF]


def test_whitespace_is_not_a_token():
    assert kinds("   \t\r\n  ") == [Kind.EOF]


def test_operators():
    assert kinds("+ - * / %") == [
        Kind.PLUS, Kind.MINUS, Kind.STAR, Kind.SLASH, Kind.PERCENT, Kind.EOF]


@pytest.mark.parametrize(("source", "kind"), [
    ("!", Kind.BANG), ("!=", Kind.BANG_EQUAL),
    ("=", Kind.EQUAL), ("==", Kind.EQUAL_EQUAL),
    ("<", Kind.LESS), ("<=", Kind.LESS_EQUAL),
    (">", Kind.GREATER), (">=", Kind.GREATER_EQUAL),
])
def test_two_character_operators_beat_one(source, kind):
    assert kinds(source)[0] is kind


def test_a_longer_operator_is_preferred():
    """`a<=b` is three tokens, not four: the scanner must not stop at '<'."""
    assert kinds("a<=b") == [Kind.IDENTIFIER, Kind.LESS_EQUAL, Kind.IDENTIFIER, Kind.EOF]


def test_keywords_are_not_identifiers():
    assert kinds("let") == [Kind.LET, Kind.EOF]
    assert kinds("letter") == [Kind.IDENTIFIER, Kind.EOF]


def test_identifiers_may_hold_digits_and_underscores():
    assert kinds("_a1 b_2") == [Kind.IDENTIFIER, Kind.IDENTIFIER, Kind.EOF]


def test_numbers_are_floats():
    assert [t.literal for t in tokenize("1 2.5 100")][:3] == [1.0, 2.5, 100.0]


def test_a_trailing_dot_is_not_part_of_the_number():
    """`1.` is a number then a dot, so `1.method` could work later without a relex."""
    assert kinds("1.") == [Kind.NUMBER, Kind.DOT, Kind.EOF]
    assert tokenize("1.")[0].literal == 1.0


def test_strings_carry_their_contents_without_the_quotes():
    assert tokenize('"hello"')[0].literal == "hello"


@pytest.mark.parametrize(("source", "expected"), [
    (r'"a\nb"', "a\nb"), (r'"a\tb"', "a\tb"), (r'"a\"b"', 'a"b'), (r'"a\\b"', "a\\b"),
])
def test_escapes(source, expected):
    assert tokenize(source)[0].literal == expected


def test_an_unknown_escape_is_an_error():
    with pytest.raises(LexError, match="unknown escape"):
        tokenize(r'"a\qb"')


def test_an_unterminated_string_is_an_error():
    with pytest.raises(LexError, match="unterminated string"):
        tokenize('"never closed')


def test_a_line_comment_runs_to_the_newline():
    assert kinds("1 // 2 3\n4") == [Kind.NUMBER, Kind.NUMBER, Kind.EOF]


def test_block_comments_nest():
    """`/* a /* b */ c */` must not end at the first `*/`."""
    assert kinds("1 /* a /* b */ c */ 2") == [Kind.NUMBER, Kind.NUMBER, Kind.EOF]


def test_an_unterminated_block_comment_is_an_error():
    with pytest.raises(LexError, match="unterminated block comment"):
        tokenize("/* forever")


def test_an_unexpected_character_is_an_error():
    with pytest.raises(LexError, match="unexpected character"):
        tokenize("a # b")


# -- positions ---------------------------------------------------------------

def test_lines_are_counted():
    assert [t.line for t in tokenize("a\nb\nc")][:3] == [1, 2, 3]


def test_columns_restart_on_each_line():
    assert [t.column for t in tokenize("ab\ncd")][:2] == [1, 1]


def test_columns_count_from_one():
    tokens = tokenize("let x")
    assert (tokens[0].column, tokens[1].column) == (1, 5)


def test_a_multi_line_string_advances_the_line_count():
    tokens = tokenize('"one\ntwo"\nafter')
    assert tokens[1].line == 3


def test_a_block_comment_advances_the_line_count():
    tokens = tokenize("/* one\ntwo */ after")
    assert tokens[0].line == 2


def test_the_error_position_points_at_the_offending_character():
    with pytest.raises(LexError) as error:
        tokenize("let a = 1;\nlet b = #;")
    assert error.value.line == 2
    assert error.value.column == 9


def test_eof_carries_a_position_too():
    assert tokenize("a\nb")[-1].line == 2
