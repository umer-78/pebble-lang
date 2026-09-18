"""Static scope resolution, run once between parsing and execution.

Without this pass the interpreter looks a variable up by walking the
environment chain at the moment it is used. That sounds equivalent and is not.
A closure captures a *chain*, not a snapshot, so a variable declared into a
scope after the closure was made becomes visible to it:

    let a = "global";
    {
      fn show() { print(a); }
      show();            // "global"
      let a = "block";
      show();            // "block" — with late binding. Wrong.
    }

`show` closed over the block before `a` existed there, so both calls should
print "global". The resolver walks the tree before anything runs and records,
for every variable use, how many scopes out its declaration was — a number that
cannot change later. The interpreter then jumps straight to that scope.

`test_closure_sees_the_scope_it_was_written_in` asserts both behaviours: the
resolved answer, and the wrong one an unresolved run still produces.

The pass also rejects programs that are nonsense regardless of input — a
variable read inside its own initialiser, `return` outside a function, `break`
outside a loop, a name declared twice in one scope — before a single statement
executes.
"""

from __future__ import annotations

from .errors import ResolveError
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

DECLARED, DEFINED = False, True


class Resolver:
    def __init__(self, globals_: set[str] | None = None):
        self.scopes: list[dict[str, bool]] = []
        self.globals = globals_ or set()
        self.function_depth = 0
        self.loop_depth = 0

    # -- scopes -----------------------------------------------------------

    def push(self) -> None:
        self.scopes.append({})

    def pop(self) -> None:
        self.scopes.pop()

    def declare(self, name: str, node: Node) -> None:
        if not self.scopes:
            return
        scope = self.scopes[-1]
        if name in scope:
            raise ResolveError(f"'{name}' is already declared in this scope",
                               node.token.line, node.token.column)
        scope[name] = DECLARED

    def define(self, name: str) -> None:
        if self.scopes:
            self.scopes[-1][name] = DEFINED

    def resolve_local(self, node: Node, name: str) -> None:
        for distance, scope in enumerate(reversed(self.scopes)):
            if name in scope:
                node.depth = distance
                return
        node.depth = None      # global, looked up by name at run time

    # -- walking ----------------------------------------------------------

    def run(self, program: Program) -> Program:
        for statement in program.statements:
            self.resolve(statement)
        return program

    def resolve(self, node: Node | None) -> None:
        if node is None:
            return
        handler = getattr(self, f"_{type(node).__name__}", None)
        if handler is None:
            raise ResolveError(f"cannot resolve {type(node).__name__}")
        handler(node)

    # -- statements -------------------------------------------------------

    def _Let(self, node: Let) -> None:
        self.declare(node.name, node)
        self.resolve(node.initialiser)
        self.define(node.name)

    def _Block(self, node: Block) -> None:
        self.push()
        for statement in node.statements:
            self.resolve(statement)
        self.pop()

    def _ExpressionStatement(self, node: ExpressionStatement) -> None:
        self.resolve(node.expression)

    def _If(self, node: If) -> None:
        self.resolve(node.condition)
        self.resolve(node.then_branch)
        self.resolve(node.else_branch)

    def _While(self, node: While) -> None:
        self.resolve(node.condition)
        self.loop_depth += 1
        self.resolve(node.body)
        self.resolve(node.increment)
        self.loop_depth -= 1

    def _ReturnStatement(self, node: ReturnStatement) -> None:
        if self.function_depth == 0:
            raise ResolveError("'return' outside a function",
                               node.token.line, node.token.column)
        self.resolve(node.value)

    def _BreakStatement(self, node: BreakStatement) -> None:
        if self.loop_depth == 0:
            raise ResolveError("'break' outside a loop", node.token.line, node.token.column)

    def _ContinueStatement(self, node: ContinueStatement) -> None:
        if self.loop_depth == 0:
            raise ResolveError("'continue' outside a loop", node.token.line, node.token.column)

    # -- expressions ------------------------------------------------------

    def _Literal(self, node: Literal) -> None:
        pass

    def _Variable(self, node: Variable) -> None:
        if self.scopes and self.scopes[-1].get(node.name) is DECLARED:
            raise ResolveError(f"'{node.name}' is read inside its own initialiser",
                               node.token.line, node.token.column)
        if not self.scopes and node.name not in self.globals:
            pass  # globals are checked at run time, where a later definition may exist
        self.resolve_local(node, node.name)

    def _Assign(self, node: Assign) -> None:
        self.resolve(node.value)
        self.resolve_local(node, node.name)

    def _IndexSet(self, node: IndexSet) -> None:
        self.resolve(node.target)
        self.resolve(node.index)
        self.resolve(node.value)

    def _Unary(self, node: Unary) -> None:
        self.resolve(node.right)

    def _Binary(self, node: Binary) -> None:
        self.resolve(node.left)
        self.resolve(node.right)

    def _Logical(self, node: Logical) -> None:
        self.resolve(node.left)
        self.resolve(node.right)

    def _Call(self, node: Call) -> None:
        self.resolve(node.callee)
        for argument in node.arguments:
            self.resolve(argument)

    def _Index(self, node: Index) -> None:
        self.resolve(node.target)
        self.resolve(node.index)

    def _ListLiteral(self, node: ListLiteral) -> None:
        for item in node.items:
            self.resolve(item)

    def _MapLiteral(self, node: MapLiteral) -> None:
        for key, value in node.pairs:
            self.resolve(key)
            self.resolve(value)

    def _Function(self, node: Function) -> None:
        self.push()
        self.function_depth += 1
        loops, self.loop_depth = self.loop_depth, 0   # a loop does not cross a function boundary
        for parameter in node.parameters:
            self.declare(parameter.lexeme, node)
            self.define(parameter.lexeme)
        for statement in node.body:
            self.resolve(statement)
        self.loop_depth = loops
        self.function_depth -= 1
        self.pop()


def resolve(program: Program, globals_: set[str] | None = None) -> Program:
    return Resolver(globals_).run(program)
