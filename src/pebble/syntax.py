"""The syntax tree.

Plain dataclasses rather than a visitor hierarchy with an `accept` method on
every node. The visitor pattern exists to give statically typed languages
double dispatch; Python has `functools.singledispatch` and dictionaries, and
paying for the ceremony anyway makes the tree harder to read for no benefit.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .tokens import Token


class Node:
    """Base for every tree node. `token` is the position to blame in an error."""

    token: Token


# -- expressions -------------------------------------------------------------

@dataclass
class Literal(Node):
    value: object
    token: Token


@dataclass
class ListLiteral(Node):
    items: list[Node]
    token: Token


@dataclass
class MapLiteral(Node):
    pairs: list[tuple[Node, Node]]
    token: Token


@dataclass
class Variable(Node):
    name: str
    token: Token
    depth: int | None = None       # filled in by the resolver


@dataclass
class Assign(Node):
    name: str
    value: Node
    token: Token
    depth: int | None = None


@dataclass
class IndexSet(Node):
    target: Node
    index: Node
    value: Node
    token: Token


@dataclass
class Unary(Node):
    operator: Token
    right: Node

    @property
    def token(self) -> Token:
        return self.operator


@dataclass
class Binary(Node):
    left: Node
    operator: Token
    right: Node

    @property
    def token(self) -> Token:
        return self.operator


@dataclass
class Logical(Node):
    left: Node
    operator: Token
    right: Node

    @property
    def token(self) -> Token:
        return self.operator


@dataclass
class Call(Node):
    callee: Node
    arguments: list[Node]
    token: Token


@dataclass
class Index(Node):
    target: Node
    index: Node
    token: Token


@dataclass
class Function(Node):
    """A function expression. `fn name(...) {...}` is sugar for `let name = fn(...)`."""

    name: str | None
    parameters: list[Token]
    body: list[Node]
    token: Token


# -- statements --------------------------------------------------------------

@dataclass
class Let(Node):
    name: str
    initialiser: Node | None
    token: Token


@dataclass
class ExpressionStatement(Node):
    expression: Node

    @property
    def token(self) -> Token:
        return self.expression.token


@dataclass
class Block(Node):
    statements: list[Node]
    token: Token


@dataclass
class If(Node):
    condition: Node
    then_branch: Node
    else_branch: Node | None
    token: Token


@dataclass
class While(Node):
    condition: Node
    body: Node
    token: Token
    increment: Node | None = None   # a `for` loop's step, run even after `continue`
    loop_variable: str | None = None  # a `for (let i …)` variable, rebound each iteration


@dataclass
class ReturnStatement(Node):
    value: Node | None
    token: Token


@dataclass
class BreakStatement(Node):
    token: Token


@dataclass
class ContinueStatement(Node):
    token: Token


@dataclass
class Program(Node):
    statements: list[Node] = field(default_factory=list)
    token: Token = None  # type: ignore[assignment]
