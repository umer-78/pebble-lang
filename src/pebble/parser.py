"""Tokens to a syntax tree, by Pratt parsing.

The textbook recursive-descent grammar gives every precedence level its own
function — `equality` calls `comparison` calls `term` calls `factor` calls
`unary` calls `call` calls `primary`. With the ten binary operators here that
is seven near-identical functions whose only difference is which operators they
match and which function they delegate to, and adding an operator means editing
the chain in two places.

Pratt parsing replaces the chain with a table and one loop. Each token kind gets
a binding power; the loop keeps consuming operators while the next one binds
tighter than the level it was called at. Right-associativity is expressed by
recursing at a *lower* power than the operator's own, which is the whole of the
trick and the reason `2 ^ 3 ^ 2` would group correctly without a second code
path.
"""

from __future__ import annotations

from .errors import ParseError
from .syntax import (
    Assign,
    Binary,
    Block,
    BreakStatement,
    Call,
    ContinueStatement,
    ExpressionStatement,
    Function,
    If,
    Index,
    IndexSet,
    Let,
    ListLiteral,
    Literal,
    Logical,
    MapLiteral,
    Node,
    Program,
    ReturnStatement,
    Unary,
    Variable,
    While,
)
from .tokens import Kind, Token

# Binding powers. Higher binds tighter. The gap of 10 between levels leaves
# room to insert an operator later without renumbering the table.
BINDING = {
    Kind.OR: 10,
    Kind.AND: 20,
    Kind.EQUAL_EQUAL: 30, Kind.BANG_EQUAL: 30,
    Kind.LESS: 40, Kind.LESS_EQUAL: 40, Kind.GREATER: 40, Kind.GREATER_EQUAL: 40,
    Kind.PLUS: 50, Kind.MINUS: 50,
    Kind.STAR: 60, Kind.SLASH: 60, Kind.PERCENT: 60,
}

UNARY_BINDING = 70          # binds tighter than any binary operator
CALL_BINDING = 80           # and calls and indexing tighter still

LOGICAL = {Kind.AND, Kind.OR}


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.position = 0

    # -- helpers ----------------------------------------------------------

    @property
    def current(self) -> Token:
        return self.tokens[self.position]

    def check(self, *kinds: Kind) -> bool:
        return self.current.kind in kinds

    def advance(self) -> Token:
        token = self.current
        if token.kind is not Kind.EOF:
            self.position += 1
        return token

    def match(self, *kinds: Kind) -> Token | None:
        if self.check(*kinds):
            return self.advance()
        return None

    def expect(self, kind: Kind, what: str) -> Token:
        if self.check(kind):
            return self.advance()
        found = "end of file" if self.current.kind is Kind.EOF else repr(self.current.lexeme)
        raise ParseError(f"expected {what}, found {found}",
                         self.current.line, self.current.column)

    # -- entry ------------------------------------------------------------

    def parse(self) -> Program:
        program = Program(token=self.current)
        while not self.check(Kind.EOF):
            program.statements.append(self.declaration())
        return program

    # -- statements -------------------------------------------------------

    def declaration(self) -> Node:
        if self.check(Kind.FN) and self.tokens[self.position + 1].kind is Kind.IDENTIFIER:
            return self.function_declaration()
        if self.match(Kind.LET):
            return self.let_statement()
        return self.statement()

    def function_declaration(self) -> Node:
        token = self.advance()                      # fn
        name = self.expect(Kind.IDENTIFIER, "a function name")
        function = self.function_rest(name.lexeme, token)
        return Let(name.lexeme, function, token)

    def function_rest(self, name: str | None, token: Token) -> Function:
        self.expect(Kind.LEFT_PAREN, "'(' after the function name")
        parameters: list[Token] = []
        if not self.check(Kind.RIGHT_PAREN):
            while True:
                parameters.append(self.expect(Kind.IDENTIFIER, "a parameter name"))
                if not self.match(Kind.COMMA):
                    break
        self.expect(Kind.RIGHT_PAREN, "')' after the parameters")
        self.expect(Kind.LEFT_BRACE, "'{' before the function body")
        return Function(name, parameters, self.block_body(), token)

    def let_statement(self) -> Node:
        name = self.expect(Kind.IDENTIFIER, "a variable name")
        initialiser = self.expression() if self.match(Kind.EQUAL) else None
        self.expect(Kind.SEMICOLON, "';' after the declaration")
        return Let(name.lexeme, initialiser, name)

    def statement(self) -> Node:
        if self.match(Kind.IF):
            return self.if_statement()
        if self.match(Kind.WHILE):
            return self.while_statement()
        if self.match(Kind.FOR):
            return self.for_statement()
        if self.check(Kind.RETURN):
            return self.return_statement()
        if self.check(Kind.BREAK):
            token = self.advance()
            self.expect(Kind.SEMICOLON, "';' after 'break'")
            return BreakStatement(token)
        if self.check(Kind.CONTINUE):
            token = self.advance()
            self.expect(Kind.SEMICOLON, "';' after 'continue'")
            return ContinueStatement(token)
        if self.check(Kind.LEFT_BRACE):
            token = self.advance()
            return Block(self.block_body(), token)

        expression = self.expression()
        self.expect(Kind.SEMICOLON, "';' after the expression")
        return ExpressionStatement(expression)

    def block_body(self) -> list[Node]:
        statements = []
        while not self.check(Kind.RIGHT_BRACE, Kind.EOF):
            statements.append(self.declaration())
        self.expect(Kind.RIGHT_BRACE, "'}' to close the block")
        return statements

    def if_statement(self) -> Node:
        token = self.tokens[self.position - 1]
        self.expect(Kind.LEFT_PAREN, "'(' after 'if'")
        condition = self.expression()
        self.expect(Kind.RIGHT_PAREN, "')' after the condition")
        then_branch = self.statement()
        else_branch = self.statement() if self.match(Kind.ELSE) else None
        return If(condition, then_branch, else_branch, token)

    def while_statement(self) -> Node:
        token = self.tokens[self.position - 1]
        self.expect(Kind.LEFT_PAREN, "'(' after 'while'")
        condition = self.expression()
        self.expect(Kind.RIGHT_PAREN, "')' after the condition")
        return While(condition, self.statement(), token)

    def for_statement(self) -> Node:
        """Desugared into a while loop, with one deliberate exception.

        The increment is *not* appended to the body. If it were, `continue`
        would jump past it and the loop would never advance — a hang, not an
        error. It is carried on the While node instead and run by the
        interpreter after every iteration however that iteration ended.
        """
        token = self.tokens[self.position - 1]
        self.expect(Kind.LEFT_PAREN, "'(' after 'for'")

        loop_variable = None
        if self.match(Kind.SEMICOLON):
            initialiser = None
        elif self.match(Kind.LET):
            initialiser = self.let_statement()
            loop_variable = initialiser.name
        else:
            expression = self.expression()
            self.expect(Kind.SEMICOLON, "';' after the loop initialiser")
            initialiser = ExpressionStatement(expression)

        condition = Literal(True, token) if self.check(Kind.SEMICOLON) else self.expression()
        self.expect(Kind.SEMICOLON, "';' after the loop condition")

        increment = None if self.check(Kind.RIGHT_PAREN) else self.expression()
        self.expect(Kind.RIGHT_PAREN, "')' after the for clauses")

        loop = While(condition, self.statement(), token,
                     increment=ExpressionStatement(increment) if increment else None,
                     loop_variable=loop_variable)
        return Block([initialiser, loop], token) if initialiser else loop

    def return_statement(self) -> Node:
        token = self.advance()
        value = None if self.check(Kind.SEMICOLON) else self.expression()
        self.expect(Kind.SEMICOLON, "';' after the return value")
        return ReturnStatement(value, token)

    # -- expressions ------------------------------------------------------

    def expression(self) -> Node:
        return self.assignment()

    def assignment(self) -> Node:
        """Assignment is right-associative and its target must be assignable.

        The target is parsed as an ordinary expression and then inspected,
        because `a[i + 1] = v` cannot be recognised as a target until the whole
        left side has been read.
        """
        target = self.binding(0)

        equals = self.match(Kind.EQUAL)
        if equals is None:
            return target

        value = self.assignment()
        if isinstance(target, Variable):
            return Assign(target.name, value, target.token)
        if isinstance(target, Index):
            return IndexSet(target.target, target.index, value, equals)
        raise ParseError("cannot assign to this expression", equals.line, equals.column)

    def binding(self, minimum: int) -> Node:
        """The Pratt loop: parse a prefix, then absorb operators that bind tighter."""
        left = self.prefix()

        while True:
            kind = self.current.kind

            if kind in (Kind.LEFT_PAREN, Kind.LEFT_BRACKET) and minimum < CALL_BINDING:
                left = self.postfix(left)
                continue

            power = BINDING.get(kind)
            if power is None or power <= minimum:
                return left

            operator = self.advance()
            right = self.binding(power)     # left-associative: recurse above our own power
            node = Logical if kind in LOGICAL else Binary
            left = node(left, operator, right)

    def prefix(self) -> Node:
        if self.check(Kind.BANG, Kind.MINUS):
            operator = self.advance()
            return Unary(operator, self.binding(UNARY_BINDING))
        return self.primary()

    def postfix(self, callee: Node) -> Node:
        if self.match(Kind.LEFT_PAREN):
            token = self.tokens[self.position - 1]
            arguments = []
            if not self.check(Kind.RIGHT_PAREN):
                while True:
                    arguments.append(self.expression())
                    if not self.match(Kind.COMMA):
                        break
            self.expect(Kind.RIGHT_PAREN, "')' after the arguments")
            return Call(callee, arguments, token)

        token = self.expect(Kind.LEFT_BRACKET, "'['")
        index = self.expression()
        self.expect(Kind.RIGHT_BRACKET, "']' after the index")
        return Index(callee, index, token)

    def primary(self) -> Node:
        token = self.current

        if self.match(Kind.FALSE):
            return Literal(False, token)
        if self.match(Kind.TRUE):
            return Literal(True, token)
        if self.match(Kind.NIL):
            return Literal(None, token)
        if self.match(Kind.NUMBER, Kind.STRING):
            return Literal(token.literal, token)
        if self.match(Kind.IDENTIFIER):
            return Variable(token.lexeme, token)
        if self.match(Kind.FN):
            return self.function_rest(None, token)

        if self.match(Kind.LEFT_PAREN):
            inner = self.expression()
            self.expect(Kind.RIGHT_PAREN, "')' after the expression")
            return inner

        if self.match(Kind.LEFT_BRACKET):
            items = []
            if not self.check(Kind.RIGHT_BRACKET):
                while True:
                    items.append(self.expression())
                    if not self.match(Kind.COMMA):
                        break
            self.expect(Kind.RIGHT_BRACKET, "']' after the list")
            return ListLiteral(items, token)

        if self.match(Kind.LEFT_BRACE):
            pairs = []
            if not self.check(Kind.RIGHT_BRACE):
                while True:
                    key = self.expression()
                    self.expect(Kind.COLON, "':' between the key and value")
                    pairs.append((key, self.expression()))
                    if not self.match(Kind.COMMA):
                        break
            self.expect(Kind.RIGHT_BRACE, "'}' after the map")
            return MapLiteral(pairs, token)

        found = "end of file" if token.kind is Kind.EOF else repr(token.lexeme)
        raise ParseError(f"expected an expression, found {found}", token.line, token.column)


def parse(tokens: list[Token]) -> Program:
    return Parser(tokens).parse()
