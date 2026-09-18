"""Precedence, associativity, and error messages that point somewhere."""

from __future__ import annotations

import pytest

from pebble import ParseError, parse, tokenize
from pebble.parser import BINDING
from pebble.syntax import (
    Assign,
    Binary,
    Block,
    Call,
    ExpressionStatement,
    Function,
    Index,
    IndexSet,
    Let,
    ListLiteral,
    Literal,
    Logical,
    MapLiteral,
    Unary,
    Variable,
    While,
)


def tree(source: str):
    return parse(tokenize(source)).statements


def expression(source: str):
    statement = tree(f"{source};")[0]
    assert isinstance(statement, ExpressionStatement)
    return statement.expression


def shape(node) -> str:
    """A parenthesised rendering, so precedence can be asserted as a string."""
    if isinstance(node, Literal):
        from pebble.values import stringify
        return stringify(node.value)
    if isinstance(node, Variable):
        return node.name
    if isinstance(node, (Binary, Logical)):
        return f"({shape(node.left)} {node.operator.lexeme} {shape(node.right)})"
    if isinstance(node, Unary):
        return f"({node.operator.lexeme}{shape(node.right)})"
    if isinstance(node, Assign):
        return f"({node.name} = {shape(node.value)})"
    if isinstance(node, Call):
        return f"{shape(node.callee)}({', '.join(shape(a) for a in node.arguments)})"
    if isinstance(node, Index):
        return f"{shape(node.target)}[{shape(node.index)}]"
    return type(node).__name__


# -- precedence --------------------------------------------------------------

@pytest.mark.parametrize(("source", "expected"), [
    ("1 + 2 * 3", "(1 + (2 * 3))"),
    ("1 * 2 + 3", "((1 * 2) + 3)"),
    ("1 + 2 - 3", "((1 + 2) - 3)"),
    ("1 - 2 - 3", "((1 - 2) - 3)"),
    ("1 / 2 / 3", "((1 / 2) / 3)"),
    ("-1 + 2", "((-1) + 2)"),
    ("-a * b", "((-a) * b)"),
    ("!a == b", "((!a) == b)"),
    ("1 < 2 == true", "((1 < 2) == true)"),
    ("a or b and c", "(a or (b and c))"),
    ("a and b or c", "((a and b) or c)"),
    ("1 + 2 < 3 + 4", "((1 + 2) < (3 + 4))"),
    ("a % b * c", "((a % b) * c)"),
])
def test_precedence_and_associativity(source, expected):
    assert shape(expression(source)) == expected


def test_parentheses_override_precedence():
    assert shape(expression("(1 + 2) * 3")) == "((1 + 2) * 3)"


def test_binary_operators_are_left_associative():
    """Right-associativity here would make 8 / 4 / 2 equal 4 instead of 1."""
    node = expression("8 / 4 / 2")
    assert isinstance(node.left, Binary)
    assert shape(node) == "((8 / 4) / 2)"


def test_assignment_is_right_associative():
    assert shape(expression("a = b = 1")) == "(a = (b = 1))"


def test_calls_bind_tighter_than_arithmetic():
    assert shape(expression("1 + f(2) * 3")) == "(1 + (f(2) * 3))"


def test_indexing_binds_tighter_than_unary():
    """`-xs[0]` negates the element, not the list."""
    assert shape(expression("-xs[0]")) == "(-xs[0])"
    assert shape(expression("!f(1)")) == "(!f(1))"


def test_calls_and_indexes_chain():
    assert shape(expression("f(1)[2](3)")) == "f(1)[2](3)"


def test_every_binary_operator_has_a_binding_power():
    """A new operator added to the lexer without a table entry parses as a
    statement boundary and silently truncates the expression."""
    from pebble.tokens import Kind
    binary = {Kind.PLUS, Kind.MINUS, Kind.STAR, Kind.SLASH, Kind.PERCENT,
              Kind.EQUAL_EQUAL, Kind.BANG_EQUAL, Kind.LESS, Kind.LESS_EQUAL,
              Kind.GREATER, Kind.GREATER_EQUAL, Kind.AND, Kind.OR}
    assert binary <= set(BINDING)


def test_binding_powers_are_ordered_as_documented():
    from pebble.tokens import Kind
    assert BINDING[Kind.OR] < BINDING[Kind.AND] < BINDING[Kind.EQUAL_EQUAL]
    assert BINDING[Kind.EQUAL_EQUAL] < BINDING[Kind.LESS] < BINDING[Kind.PLUS]
    assert BINDING[Kind.PLUS] < BINDING[Kind.STAR]


# -- statements --------------------------------------------------------------

def test_let_with_and_without_an_initialiser():
    statements = tree("let a = 1; let b;")
    assert isinstance(statements[0], Let) and statements[0].initialiser is not None
    assert isinstance(statements[1], Let) and statements[1].initialiser is None


def test_a_function_declaration_is_a_let():
    """`fn f() {}` is sugar, so a function name is an ordinary variable and can
    be reassigned, shadowed and passed around like any other value."""
    statement = tree("fn f(a, b) { return a; }")[0]
    assert isinstance(statement, Let)
    assert isinstance(statement.initialiser, Function)
    assert [p.lexeme for p in statement.initialiser.parameters] == ["a", "b"]


def test_an_anonymous_function_is_an_expression():
    assert isinstance(expression("fn(x) { return x; }"), Function)


def test_else_binds_to_the_nearest_if():
    outer = tree("if (a) if (b) x(); else y();")[0]
    assert outer.else_branch is None
    assert outer.then_branch.else_branch is not None


def test_a_for_loop_becomes_a_block_around_a_while():
    block = tree("for (let i = 0; i < 3; i = i + 1) f();")[0]
    assert isinstance(block, Block)
    assert isinstance(block.statements[0], Let)
    assert isinstance(block.statements[1], While)


def test_a_for_loops_increment_is_not_appended_to_the_body():
    """If it were, `continue` would skip it and the loop would hang."""
    loop = tree("for (let i = 0; i < 3; i = i + 1) { f(); }")[0].statements[1]
    assert loop.increment is not None
    assert len(loop.body.statements) == 1


def test_a_for_loop_records_its_variable():
    loop = tree("for (let i = 0; i < 3; i = i + 1) f();")[0].statements[1]
    assert loop.loop_variable == "i"


def test_a_for_loop_without_a_let_has_no_loop_variable():
    loop = tree("let i = 0; for (; i < 3; i = i + 1) f();")[1]
    assert loop.loop_variable is None


def test_an_empty_for_header_is_an_infinite_loop():
    loop = tree("for (;;) break;")[0]
    assert isinstance(loop, While)
    assert loop.condition.value is True


def test_collections():
    assert isinstance(expression("[1, 2, 3]"), ListLiteral)
    assert isinstance(tree("let m = {};")[0].initialiser, MapLiteral)
    assert len(tree('let m = {"a": 1, "b": 2};')[0].initialiser.pairs) == 2


def test_a_brace_at_the_start_of_a_statement_is_a_block_not_a_map():
    """The same ambiguity JavaScript has, resolved the same way — and it is
    reported rather than silently mis-parsed.

    `{` could open a block or a map literal. A statement may start with a
    block, so at statement position the block wins: `{}` is an empty block, and
    `{"a": 1};` is a block whose first statement is the expression `"a"`
    followed by a stray colon, which is a parse error with a position rather
    than a program that quietly does the wrong thing. Maps are written where
    maps belong — in expression position, as in `let m = {"a": 1};`.
    """
    assert isinstance(tree("{}")[0], Block)
    with pytest.raises(ParseError) as error:
        tree('{"a": 1};')
    assert error.value.column == 5


def test_a_trailing_comma_is_not_allowed():
    with pytest.raises(ParseError):
        expression("[1, 2,]")


def test_index_assignment_is_its_own_node():
    """`a[i] = v` cannot be recognised until the whole left side is parsed."""
    assert isinstance(expression("a[0] = 1"), IndexSet)


# -- errors ------------------------------------------------------------------

def test_a_missing_semicolon_is_reported_where_it_is_missing():
    with pytest.raises(ParseError) as error:
        tree("let a = 1\nlet b = 2;")
    assert "';'" in error.value.message
    assert error.value.line == 2


def test_an_unclosed_parenthesis_is_an_error():
    with pytest.raises(ParseError, match=r"\)"):
        expression("(1 + 2")


def test_an_unclosed_block_is_an_error():
    with pytest.raises(ParseError, match="}"):
        tree("{ let a = 1;")


def test_assigning_to_a_literal_is_an_error():
    with pytest.raises(ParseError, match="cannot assign"):
        expression("1 = 2")


def test_assigning_to_a_call_is_an_error():
    with pytest.raises(ParseError, match="cannot assign"):
        expression("f() = 2")


def test_an_empty_expression_is_an_error():
    with pytest.raises(ParseError, match="expected an expression"):
        tree("let a = ;")


def test_an_error_at_the_end_says_end_of_file():
    with pytest.raises(ParseError, match="end of file"):
        tree("let a = 1 +")


def test_a_missing_parameter_name_is_an_error():
    with pytest.raises(ParseError, match="parameter name"):
        tree("fn f(1) {}")
