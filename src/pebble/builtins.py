"""The standard library: small, and everything in it is a plain function.

Nothing here is a special form. `print` is a value you can pass to another
function, which is the difference between a language with first-class functions
and one that merely has functions.
"""

from __future__ import annotations

import math
import time

from .errors import RuntimeError_
from .values import Builtin, Callable_, stringify, type_name


def install(interpreter) -> None:
    def define(name: str, arity: int, function) -> None:
        interpreter.globals.define(name, Builtin(name, arity, function))

    def _print(value):
        interpreter.emit(stringify(value))
        return None

    def _len(value):
        if isinstance(value, (str, list, dict)):
            return float(len(value))
        raise RuntimeError_(f"a {type_name(value)} has no length")

    def _push(target, value):
        if not isinstance(target, list):
            raise RuntimeError_(f"cannot push onto a {type_name(target)}")
        target.append(value)
        return target

    def _pop(target):
        if not isinstance(target, list):
            raise RuntimeError_(f"cannot pop from a {type_name(target)}")
        if not target:
            raise RuntimeError_("cannot pop from an empty list")
        return target.pop()

    def _num(value):
        if isinstance(value, float):
            return value
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError as error:
                raise RuntimeError_(f"{value!r} is not a number") from error
        raise RuntimeError_(f"cannot convert a {type_name(value)} to a number")

    def _keys(value):
        if not isinstance(value, dict):
            raise RuntimeError_(f"a {type_name(value)} has no keys")
        return list(value.keys())

    def _has(value, key):
        if not isinstance(value, dict):
            raise RuntimeError_(f"a {type_name(value)} has no keys")
        return key in value

    def _slice(value, start, end):
        if not isinstance(value, (str, list)):
            raise RuntimeError_(f"cannot slice a {type_name(value)}")
        if not isinstance(start, float) or not isinstance(end, float):
            raise RuntimeError_("slice bounds must be numbers")
        return value[int(start):int(end)]

    def _sqrt(value):
        if not isinstance(value, float):
            raise RuntimeError_(f"cannot take the square root of a {type_name(value)}")
        if value < 0:
            raise RuntimeError_("cannot take the square root of a negative number")
        return math.sqrt(value)

    def _floor(value):
        if not isinstance(value, float):
            raise RuntimeError_(f"cannot floor a {type_name(value)}")
        return float(math.floor(value))

    def _abs(value):
        if not isinstance(value, float):
            raise RuntimeError_(f"cannot take the absolute value of a {type_name(value)}")
        return abs(value)

    def _split(value, separator):
        if not isinstance(value, str) or not isinstance(separator, str):
            raise RuntimeError_("split takes two strings")
        return value.split(separator) if separator else list(value)

    def _join(values, separator):
        if not isinstance(values, list) or not isinstance(separator, str):
            raise RuntimeError_("join takes a list and a string")
        return separator.join(stringify(item) for item in values)

    define("print", 1, _print)
    define("str", 1, stringify)
    define("num", 1, _num)
    define("type", 1, type_name)
    define("len", 1, _len)
    define("push", 2, _push)
    define("pop", 1, _pop)
    define("keys", 1, _keys)
    define("has", 2, _has)
    define("slice", 3, _slice)
    define("sqrt", 1, _sqrt)
    define("floor", 1, _floor)
    define("abs", 1, _abs)
    define("split", 2, _split)
    define("join", 2, _join)
    define("clock", 0, lambda: time.perf_counter())


def builtin_names(interpreter) -> list[str]:
    return sorted(name for name, value in interpreter.globals.values.items()
                  if isinstance(value, Callable_))
