"""Runtime values and how they print."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from .errors import RuntimeError_


@dataclass
class Callable_:
    """A function the interpreter can call: user-defined or built in."""

    name: str
    arity: int

    def call(self, interpreter, arguments, token):  # pragma: no cover - interface
        raise NotImplementedError


class Builtin(Callable_):
    def __init__(self, name: str, arity: int, function: Callable):
        super().__init__(name, arity)
        self.function = function

    def call(self, interpreter, arguments, token):
        return self.function(*arguments)

    def __repr__(self) -> str:
        return f"<builtin {self.name}>"


class PebbleFunction(Callable_):
    """A user function, closed over the environment it was written in."""

    def __init__(self, declaration, closure, name: str | None = None):
        super().__init__(name or declaration.name or "anonymous", len(declaration.parameters))
        self.declaration = declaration
        self.closure = closure

    def call(self, interpreter, arguments, token):
        return interpreter.call_function(self, arguments, token)

    def __repr__(self) -> str:
        return f"<fn {self.name}/{self.arity}>"


def stringify(value: object) -> str:
    """How a value looks when printed.

    Numbers are floats internally, because a language with one number type is
    simpler to specify and harder to get subtly wrong. They are printed without
    the trailing '.0' when they are whole, so `2 + 2` reads as 4 rather than
    4.0 — the representation is the implementation's business, not the
    program's.
    """
    if value is None:
        return "nil"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, float):
        if value != value:
            return "nan"
        if value in (float("inf"), float("-inf")):
            return "inf" if value > 0 else "-inf"
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "[" + ", ".join(stringify(item) for item in value) + "]"
    if isinstance(value, dict):
        return "{" + ", ".join(f"{stringify(k)}: {stringify(v)}" for k, v in value.items()) + "}"
    return repr(value)


def type_name(value: object) -> str:
    if value is None:
        return "nil"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "map"
    if isinstance(value, Callable_):
        return "function"
    return "unknown"


def truthy(value: object) -> bool:
    """Only nil and false are false.

    Not 0, not the empty string, not the empty list. Every language that makes
    those falsey ends up with `if (x)` meaning different things depending on
    whether x is a count or a handle, and with bugs where a legitimate zero is
    mistaken for absence. Keeping the rule to two values makes `if (list)`
    obviously wrong rather than subtly right, which is the point.
    """
    return value is not None and value is not False


def hashable(value: object, line: int = 0, column: int = 0) -> object:
    if isinstance(value, (str, float, bool)) or value is None:
        return value
    raise RuntimeError_(f"a {type_name(value)} cannot be a map key", line, column)
