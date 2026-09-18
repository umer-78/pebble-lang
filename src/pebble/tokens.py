"""Token kinds and the token record."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class Kind(Enum):
    # single characters
    LEFT_PAREN = auto(); RIGHT_PAREN = auto()
    LEFT_BRACE = auto(); RIGHT_BRACE = auto()
    LEFT_BRACKET = auto(); RIGHT_BRACKET = auto()
    COMMA = auto(); DOT = auto(); SEMICOLON = auto(); COLON = auto()
    PLUS = auto(); MINUS = auto(); STAR = auto(); SLASH = auto(); PERCENT = auto()

    # one or two characters
    BANG = auto(); BANG_EQUAL = auto()
    EQUAL = auto(); EQUAL_EQUAL = auto()
    GREATER = auto(); GREATER_EQUAL = auto()
    LESS = auto(); LESS_EQUAL = auto()

    # literals
    IDENTIFIER = auto(); STRING = auto(); NUMBER = auto()

    # keywords
    AND = auto(); ELSE = auto(); FALSE = auto(); FN = auto(); FOR = auto()
    IF = auto(); LET = auto(); NIL = auto(); OR = auto(); RETURN = auto()
    TRUE = auto(); WHILE = auto(); BREAK = auto(); CONTINUE = auto()

    EOF = auto()


KEYWORDS = {
    "and": Kind.AND, "else": Kind.ELSE, "false": Kind.FALSE, "fn": Kind.FN,
    "for": Kind.FOR, "if": Kind.IF, "let": Kind.LET, "nil": Kind.NIL,
    "or": Kind.OR, "return": Kind.RETURN, "true": Kind.TRUE, "while": Kind.WHILE,
    "break": Kind.BREAK, "continue": Kind.CONTINUE,
}


@dataclass(frozen=True)
class Token:
    kind: Kind
    lexeme: str
    literal: object = None
    line: int = 0
    column: int = 0

    def __repr__(self) -> str:
        if self.literal is not None:
            return f"{self.kind.name}({self.lexeme!r}={self.literal!r})"
        return f"{self.kind.name}({self.lexeme!r})"
