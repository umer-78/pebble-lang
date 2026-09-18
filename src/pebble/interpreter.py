"""The tree-walking evaluator."""

from __future__ import annotations

import sys

from .environment import Environment
from .errors import DepthError, Return, RuntimeError_
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
from .tokens import Kind
from .values import Callable_, PebbleFunction, hashable, stringify, truthy, type_name

# One guest call costs this many host frames: _Call, call_function, run_block,
# execute, and the nodes between them. Measured, not guessed —
# test_one_guest_call_costs_seven_host_frames pins it, so an extra layer added
# to the evaluator updates this number instead of silently overrunning the host
# stack before max_depth is reached.
HOST_FRAMES_PER_CALL = 7
HOST_HEADROOM = 200
HOST_LIMIT_CEILING = 60_000


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


class Interpreter:
    """Walks the tree and evaluates it.

    `max_depth` exists because a tree-walking interpreter recurses on the host
    stack: guest recursion 10,000 deep is host recursion far deeper than that,
    and Python's own limit turns it into a RecursionError traceback out of the
    interpreter's internals. Counting call frames turns that into a program
    error with a line number, which is what a user of the language needs.
    """

    def __init__(self, *, output=None, max_depth: int = 200, resolved: bool = True):
        self.globals = Environment()
        self.environment = self.globals
        self.output = output if output is not None else sys.stdout
        self.max_depth = max_depth
        self.depth = 0
        self.resolved = resolved
        self.calls = 0

        if max_depth < 1:
            raise ValueError("max_depth must be at least 1")
        self.host_limit = max_depth * HOST_FRAMES_PER_CALL + HOST_HEADROOM
        if self.host_limit > HOST_LIMIT_CEILING:
            raise ValueError(
                f"max_depth {max_depth} would need a host recursion limit of "
                f"{self.host_limit:,}, past the {HOST_LIMIT_CEILING:,} this "
                "interpreter is willing to ask for")

        from .builtins import install
        install(self)

    # -- entry ------------------------------------------------------------

    def run(self, program: Program) -> object:
        """Run a program, with enough host stack to reach `max_depth` first.

        The depth limit is only a promise if the host stack outlasts it. Seven
        host frames per guest call against Python's default limit of 1,000
        leaves room for about 140 guest frames — so a default `max_depth` of
        200 would have been unreachable, and runaway recursion would have
        surfaced as a host RecursionError traceback out of the evaluator's
        internals rather than as an error in the program that caused it. The
        limit is raised for the duration of the run and put back afterwards,
        because it is a process-wide setting and this is a library.
        """
        previous = sys.getrecursionlimit()
        if self.host_limit > previous:
            sys.setrecursionlimit(self.host_limit)
        try:
            result = None
            for statement in program.statements:
                result = self.execute(statement)
            return result
        finally:
            sys.setrecursionlimit(previous)

    def execute(self, node: Node | None) -> object:
        if node is None:
            return None
        return getattr(self, f"_{type(node).__name__}")(node)

    evaluate = execute

    def emit(self, text: str) -> None:
        print(text, file=self.output)

    # -- variables --------------------------------------------------------

    def lookup(self, node) -> object:
        """Resolved variables jump; unresolved ones walk.

        `self.resolved` is what makes the closure-scoping demonstration
        possible: turning it off reproduces the late-binding behaviour the
        resolver exists to prevent, so the difference can be asserted by a test
        rather than described in a comment.
        """
        if self.resolved:
            if node.depth is not None:
                return self.environment.get_at(node.depth, node.name)
            # Not a local, so a global — and global means the outermost scope,
            # not "whatever the chain happens to hold by now". Walking the chain
            # here is exactly the late binding the resolver exists to remove.
            return self.globals.get(node.name, node.token.line, node.token.column)
        return self.environment.get(node.name, node.token.line, node.token.column)

    def _Variable(self, node: Variable) -> object:
        return self.lookup(node)

    def _Assign(self, node: Assign) -> object:
        value = self.evaluate(node.value)
        if self.resolved and node.depth is not None:
            self.environment.assign_at(node.depth, node.name, value)
        elif self.resolved:
            self.globals.assign(node.name, value, node.token.line, node.token.column)
        else:
            self.environment.assign(node.name, value, node.token.line, node.token.column)
        return value

    def _Let(self, node: Let) -> object:
        value = self.evaluate(node.initialiser) if node.initialiser else None
        if isinstance(value, PebbleFunction) and value.name == "anonymous":
            value.name = node.name
        self.environment.define(node.name, value)
        return None

    # -- statements -------------------------------------------------------

    def _ExpressionStatement(self, node: ExpressionStatement) -> object:
        return self.evaluate(node.expression)

    def _Block(self, node: Block) -> object:
        return self.run_block(node.statements, Environment(self.environment))

    def run_block(self, statements: list[Node], environment: Environment) -> object:
        previous = self.environment
        self.environment = environment
        try:
            for statement in statements:
                self.execute(statement)
        finally:
            self.environment = previous
        return None

    def _If(self, node: If) -> object:
        if truthy(self.evaluate(node.condition)):
            return self.execute(node.then_branch)
        return self.execute(node.else_branch)

    def _While(self, node: While) -> object:
        """One binding per iteration when the loop declared its own variable.

        `for (let i = 0; i < 3; i = i + 1)` where the body makes a closure is
        the oldest bug in this shape: with a single binding shared by every
        iteration, all three closures see the final value and return 2, 2, 2.
        JavaScript's `var` does that; its `let` does not, and neither does this.

        The ordering is what makes it work, and it is easy to get wrong. Giving
        each iteration a fresh copy is not enough on its own: run the increment
        in the same scope the body just captured and every closure sees a value
        one too high. So the fresh scope is made *before* the increment, which
        then runs in the scope the next iteration will use. The body's captured
        scope is never touched again.
        """
        if node.loop_variable is None:
            while truthy(self.evaluate(node.condition)):
                try:
                    self.execute(node.body)
                except _Break:
                    break
                except _Continue:
                    pass
                self.execute(node.increment)
            return None

        name = node.loop_variable
        outer = self.environment
        # The iteration scope *replaces* the loop's own scope rather than
        # nesting inside it. Nesting adds a link the resolver never counted, so
        # every variable from an enclosing scope would be found one link short.
        parent = outer.parent
        iteration = Environment(parent)
        iteration.define(name, outer.values[name])

        while True:
            if not truthy(self.in_scope(iteration, node.condition)):
                return None
            try:
                self.in_scope(iteration, node.body)
            except _Break:
                return None
            except _Continue:
                pass

            following = Environment(parent)
            following.define(name, iteration.values[name])
            self.in_scope(following, node.increment)
            iteration = following

    def in_scope(self, environment: Environment, node: Node | None) -> object:
        """Run one node in a given scope and put the previous one back."""
        previous = self.environment
        self.environment = environment
        try:
            return self.execute(node)
        finally:
            self.environment = previous

    def _BreakStatement(self, node: BreakStatement) -> object:
        raise _Break

    def _ContinueStatement(self, node: ContinueStatement) -> object:
        raise _Continue

    def _ReturnStatement(self, node: ReturnStatement) -> object:
        raise Return(self.evaluate(node.value) if node.value else None)

    # -- expressions ------------------------------------------------------

    def _Literal(self, node: Literal) -> object:
        return node.value

    def _ListLiteral(self, node: ListLiteral) -> object:
        return [self.evaluate(item) for item in node.items]

    def _MapLiteral(self, node: MapLiteral) -> object:
        out: dict[object, object] = {}
        for key, value in node.pairs:
            evaluated = hashable(self.evaluate(key), node.token.line, node.token.column)
            out[evaluated] = self.evaluate(value)
        return out

    def _Unary(self, node: Unary) -> object:
        right = self.evaluate(node.right)
        if node.operator.kind is Kind.BANG:
            return not truthy(right)
        if not isinstance(right, float):
            raise RuntimeError_(f"cannot negate a {type_name(right)}",
                                node.operator.line, node.operator.column)
        return -right

    def _Logical(self, node: Logical) -> object:
        """Short-circuiting, and returning the operand rather than a boolean.

        `a or b` gives `a` when `a` is truthy, so `name or "anonymous"` works as
        a default. Evaluating the right side regardless would make
        `x != nil and x[0]` a crash instead of a guard.
        """
        left = self.evaluate(node.left)
        if node.operator.kind is Kind.OR:
            return left if truthy(left) else self.evaluate(node.right)
        return self.evaluate(node.right) if truthy(left) else left

    def _Binary(self, node: Binary) -> object:
        left = self.evaluate(node.left)
        right = self.evaluate(node.right)
        kind = node.operator.kind
        line, column = node.operator.line, node.operator.column

        if kind is Kind.EQUAL_EQUAL:
            return self.equal(left, right)
        if kind is Kind.BANG_EQUAL:
            return not self.equal(left, right)

        if kind is Kind.PLUS:
            if isinstance(left, float) and isinstance(right, float):
                return left + right
            if isinstance(left, str) and isinstance(right, str):
                return left + right
            if isinstance(left, list) and isinstance(right, list):
                return left + right
            raise RuntimeError_(
                f"cannot add a {type_name(left)} to a {type_name(right)}", line, column)

        if kind in (Kind.LESS, Kind.LESS_EQUAL, Kind.GREATER, Kind.GREATER_EQUAL):
            if isinstance(left, str) and isinstance(right, str):
                pass
            elif not (isinstance(left, float) and isinstance(right, float)):
                raise RuntimeError_(
                    f"cannot compare a {type_name(left)} with a {type_name(right)}",
                    line, column)
            return {
                Kind.LESS: left < right, Kind.LESS_EQUAL: left <= right,
                Kind.GREATER: left > right, Kind.GREATER_EQUAL: left >= right,
            }[kind]

        if not (isinstance(left, float) and isinstance(right, float)):
            raise RuntimeError_(
                f"cannot apply '{node.operator.lexeme}' to a {type_name(left)} "
                f"and a {type_name(right)}", line, column)

        if kind is Kind.MINUS:
            return left - right
        if kind is Kind.STAR:
            return left * right
        if right == 0 and kind in (Kind.SLASH, Kind.PERCENT):
            # Returning inf would let a mistake propagate silently through an
            # arithmetic chain and surface far from its cause.
            raise RuntimeError_("division by zero", line, column)
        if kind is Kind.SLASH:
            return left / right
        return left % right

    @staticmethod
    def equal(left: object, right: object) -> bool:
        """`==` does not convert.

        In Python `1.0 == True`, which would make `1 == true` true in this
        language by accident. Comparing types first is a one-line fix for a
        class of confusion that has followed == around for decades.
        """
        if isinstance(left, bool) != isinstance(right, bool):
            return False
        if isinstance(left, float) != isinstance(right, float):
            return False
        return left == right

    def _Index(self, node: Index) -> object:
        target = self.evaluate(node.target)
        index = self.evaluate(node.index)
        line, column = node.token.line, node.token.column

        if isinstance(target, list):
            position = self.list_position(index, len(target), line, column)
            return target[position]
        if isinstance(target, str):
            position = self.list_position(index, len(target), line, column)
            return target[position]
        if isinstance(target, dict):
            key = hashable(index, line, column)
            if key not in target:
                raise RuntimeError_(f"no key {stringify(key)} in the map", line, column)
            return target[key]
        raise RuntimeError_(f"cannot index a {type_name(target)}", line, column)

    def _IndexSet(self, node: IndexSet) -> object:
        target = self.evaluate(node.target)
        index = self.evaluate(node.index)
        value = self.evaluate(node.value)
        line, column = node.token.line, node.token.column

        if isinstance(target, list):
            target[self.list_position(index, len(target), line, column)] = value
            return value
        if isinstance(target, dict):
            target[hashable(index, line, column)] = value
            return value
        raise RuntimeError_(f"cannot assign into a {type_name(target)}", line, column)

    @staticmethod
    def list_position(index: object, length: int, line: int, column: int) -> int:
        if not isinstance(index, float) or not index.is_integer():
            raise RuntimeError_(f"an index must be a whole number, got {stringify(index)}",
                                line, column)
        position = int(index)
        if position < 0:
            position += length
        if not 0 <= position < length:
            raise RuntimeError_(
                f"index {stringify(index)} is outside a collection of length {length}",
                line, column)
        return position

    # -- calls ------------------------------------------------------------

    def _Function(self, node: Function) -> object:
        return PebbleFunction(node, self.environment)

    def _Call(self, node: Call) -> object:
        callee = self.evaluate(node.callee)
        arguments = [self.evaluate(argument) for argument in node.arguments]
        line, column = node.token.line, node.token.column

        if not isinstance(callee, Callable_):
            raise RuntimeError_(f"cannot call a {type_name(callee)}", line, column)
        if callee.arity >= 0 and len(arguments) != callee.arity:
            raise RuntimeError_(
                f"{callee.name} takes {callee.arity} argument(s), got {len(arguments)}",
                line, column)

        self.calls += 1
        return callee.call(self, arguments, node.token)

    def call_function(self, function: PebbleFunction, arguments: list[object], token) -> object:
        if self.depth >= self.max_depth:
            raise DepthError(
                f"call depth exceeded {self.max_depth} — infinite recursion?",
                token.line, token.column)

        environment = Environment(function.closure)
        for parameter, argument in zip(function.declaration.parameters, arguments, strict=True):
            environment.define(parameter.lexeme, argument)

        self.depth += 1
        try:
            self.run_block(function.declaration.body, environment)
        except Return as returned:
            return returned.value
        except RecursionError as error:
            # The belt to the depth counter's braces. If the evaluator ever
            # grows a frame and HOST_FRAMES_PER_CALL goes stale, this still
            # reports a program error rather than a host traceback.
            raise DepthError(
                "the host stack ran out before the call-depth limit was reached",
                token.line, token.column) from error
        finally:
            self.depth -= 1
        return None
