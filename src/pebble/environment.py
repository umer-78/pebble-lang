"""Scopes at run time.

Two lookup paths, deliberately. Resolved variables know exactly how many links
out their binding lives and walk that many; globals are looked up by name in the
outermost scope. Anything the resolver could not place is a global, and a global
that does not exist is a runtime error rather than a silent nil — a typo in a
name should not quietly evaluate to nothing.
"""

from __future__ import annotations

from .errors import RuntimeError_


class Environment:
    __slots__ = ("values", "parent")

    def __init__(self, parent: Environment | None = None):
        self.values: dict[str, object] = {}
        self.parent = parent

    def define(self, name: str, value: object) -> None:
        self.values[name] = value

    def ancestor(self, distance: int) -> Environment:
        environment = self
        for _ in range(distance):
            assert environment.parent is not None, "resolver promised a deeper scope"
            environment = environment.parent
        return environment

    def get_at(self, distance: int, name: str) -> object:
        return self.ancestor(distance).values[name]

    def assign_at(self, distance: int, name: str, value: object) -> None:
        self.ancestor(distance).values[name] = value

    # -- the by-name path, for globals -------------------------------------

    def get(self, name: str, line: int = 0, column: int = 0) -> object:
        environment: Environment | None = self
        while environment is not None:
            if name in environment.values:
                return environment.values[name]
            environment = environment.parent
        raise RuntimeError_(f"undefined variable '{name}'", line, column)

    def assign(self, name: str, value: object, line: int = 0, column: int = 0) -> None:
        environment: Environment | None = self
        while environment is not None:
            if name in environment.values:
                environment.values[name] = value
                return
            environment = environment.parent
        raise RuntimeError_(f"undefined variable '{name}'", line, column)
