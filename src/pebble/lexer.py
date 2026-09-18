"""Source text to tokens, tracking line and column throughout.

Positions are carried on every token rather than reconstructed later. An error
message that can only say "somewhere in your program" is the single most
common failing of a hand-written interpreter, and the cost of avoiding it is
two integers per token.
"""

from __future__ import annotations

from .errors import LexError
from .tokens import KEYWORDS, Kind, Token

SINGLE = {
    "(": Kind.LEFT_PAREN, ")": Kind.RIGHT_PAREN,
    "{": Kind.LEFT_BRACE, "}": Kind.RIGHT_BRACE,
    "[": Kind.LEFT_BRACKET, "]": Kind.RIGHT_BRACKET,
    ",": Kind.COMMA, ".": Kind.DOT, ";": Kind.SEMICOLON, ":": Kind.COLON,
    "+": Kind.PLUS, "-": Kind.MINUS, "*": Kind.STAR, "%": Kind.PERCENT,
}

PAIRS = {
    "!": (Kind.BANG, Kind.BANG_EQUAL),
    "=": (Kind.EQUAL, Kind.EQUAL_EQUAL),
    "<": (Kind.LESS, Kind.LESS_EQUAL),
    ">": (Kind.GREATER, Kind.GREATER_EQUAL),
}

ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "0": "\0"}


class Lexer:
    def __init__(self, source: str):
        self.source = source
        self.tokens: list[Token] = []
        self.start = 0
        self.current = 0
        self.line = 1
        self.line_start = 0

    # -- helpers ----------------------------------------------------------

    @property
    def at_end(self) -> bool:
        return self.current >= len(self.source)

    @property
    def column(self) -> int:
        return self.start - self.line_start + 1

    def advance(self) -> str:
        char = self.source[self.current]
        self.current += 1
        return char

    def peek(self, ahead: int = 0) -> str:
        index = self.current + ahead
        return self.source[index] if index < len(self.source) else "\0"

    def match(self, expected: str) -> bool:
        if self.at_end or self.source[self.current] != expected:
            return False
        self.current += 1
        return True

    def add(self, kind: Kind, literal: object = None) -> None:
        self.tokens.append(Token(kind, self.source[self.start:self.current],
                                 literal, self.line, self.column))

    def newline(self) -> None:
        self.line += 1
        self.line_start = self.current

    # -- the scan ---------------------------------------------------------

    def scan(self) -> list[Token]:
        while not self.at_end:
            self.start = self.current
            self.scan_token()
        self.start = self.current
        self.add(Kind.EOF)
        return self.tokens

    def scan_token(self) -> None:
        char = self.advance()

        if char in " \r\t":
            return
        if char == "\n":
            self.newline()
            return

        if char == "/":
            if self.match("/"):
                while self.peek() != "\n" and not self.at_end:
                    self.advance()
                return
            if self.match("*"):
                self.block_comment()
                return
            self.add(Kind.SLASH)
            return

        if char in SINGLE:
            self.add(SINGLE[char])
            return

        if char in PAIRS:
            alone, paired = PAIRS[char]
            self.add(paired if self.match("=") else alone)
            return

        if char == '"':
            self.string()
            return

        if char.isdigit():
            self.number()
            return

        if char.isalpha() or char == "_":
            self.identifier()
            return

        raise LexError(f"unexpected character {char!r}", self.line, self.column)

    def block_comment(self) -> None:
        """Nested block comments, because /* /* */ */ ending early is a trap."""
        depth = 1
        while depth > 0:
            if self.at_end:
                raise LexError("unterminated block comment", self.line, self.column)
            if self.peek() == "/" and self.peek(1) == "*":
                self.advance()
                self.advance()
                depth += 1
            elif self.peek() == "*" and self.peek(1) == "/":
                self.advance()
                self.advance()
                depth -= 1
            else:
                if self.peek() == "\n":
                    self.advance()
                    self.newline()
                else:
                    self.advance()

    def string(self) -> None:
        pieces: list[str] = []
        while self.peek() != '"':
            if self.at_end:
                raise LexError("unterminated string", self.line, self.column)
            char = self.advance()
            if char == "\n":
                self.newline()
                pieces.append(char)
            elif char == "\\":
                if self.at_end:
                    raise LexError("unterminated escape", self.line, self.column)
                code = self.advance()
                if code not in ESCAPES:
                    raise LexError(f"unknown escape '\\{code}'", self.line, self.column)
                pieces.append(ESCAPES[code])
            else:
                pieces.append(char)
        self.advance()  # closing quote
        self.add(Kind.STRING, "".join(pieces))

    def number(self) -> None:
        while self.peek().isdigit():
            self.advance()
        if self.peek() == "." and self.peek(1).isdigit():
            self.advance()
            while self.peek().isdigit():
                self.advance()
        self.add(Kind.NUMBER, float(self.source[self.start:self.current]))

    def identifier(self) -> None:
        while self.peek().isalnum() or self.peek() == "_":
            self.advance()
        text = self.source[self.start:self.current]
        self.add(KEYWORDS.get(text, Kind.IDENTIFIER))


def tokenize(source: str) -> list[Token]:
    return Lexer(source).scan()
