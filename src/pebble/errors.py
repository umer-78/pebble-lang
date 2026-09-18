"""Every way a program can fail, with the position that caused it."""

from __future__ import annotations


class PebbleError(Exception):
    """Base class. Carries a line and column so the CLI can point at the source."""

    def __init__(self, message: str, line: int = 0, column: int = 0):
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column

    def __str__(self) -> str:
        where = f"line {self.line}" if self.line else "somewhere"
        if self.column:
            where += f", column {self.column}"
        return f"{where}: {self.message}"


class LexError(PebbleError):
    """The source could not be turned into tokens."""


class ParseError(PebbleError):
    """The tokens do not form a program."""


class ResolveError(PebbleError):
    """The program parses but its names do not work out.

    Caught before anything runs, which is the point of having a resolver at
    all: `let a = a;` is not a runtime problem, it is a nonsense program.
    """


class RuntimeError_(PebbleError):
    """Something went wrong while running. Named with a trailing underscore to
    avoid shadowing the builtin, which a language implementation still needs."""


class DepthError(RuntimeError_):
    """Recursion went deeper than the interpreter is willing to follow.

    A tree-walking interpreter recurses on the host stack, so unbounded
    recursion in the guest language crashes the host with a stack overflow.
    Raising this instead turns an interpreter crash into a program error.
    """


class Return(Exception):  # noqa: N818
    """Not an error — the control-flow signal a `return` statement raises.

    Unwinding the host stack is how a tree-walking interpreter returns from a
    call, so this deliberately inherits from Exception rather than PebbleError.
    """

    def __init__(self, value):
        super().__init__(value)
        self.value = value
