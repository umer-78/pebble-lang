"""Static scope resolution — the pass that makes closures mean what they say."""

from __future__ import annotations

import pytest

from pebble import ResolveError, parse, resolve, tokenize
from pebble.syntax import Variable


def check(source: str):
    program = parse(tokenize(source))
    return resolve(program, {"print", "len"})


def depths(source: str) -> list[int | None]:
    """Every variable use's resolved distance, in source order."""
    found: list[int | None] = []

    def walk(node):
        if isinstance(node, Variable):
            found.append(node.depth)
        if hasattr(node, "__dataclass_fields__"):
            for name in node.__dataclass_fields__:
                value = getattr(node, name)
                if isinstance(value, list):
                    for item in value:
                        walk(item)
                else:
                    walk(value)

    for statement in check(source).statements:
        walk(statement)
    return found


# -- the headline ------------------------------------------------------------

SHADOW = """
let a = "global";
{
  fn show() { print(a); }
  show();
  let a = "block";
  show();
}
"""


def test_a_closure_sees_the_scope_it_was_written_in(run):
    """Both calls print "global": `show` closed over the block before the
    block's own `a` existed, and a later declaration cannot reach backwards."""
    assert run(SHADOW) == ["global", "global"]


def test_without_resolution_the_second_call_is_wrong(run):
    """The bug the resolver removes, kept runnable so the difference is a
    measurement rather than a claim. Looking a variable up by walking the
    environment chain at call time finds the block's `a`, which did not exist
    when the closure was made."""
    assert run(SHADOW, resolved=False) == ["global", "block"]


def test_the_resolver_records_no_depth_for_a_global():
    """`None` means global, and the interpreter reads globals from the outermost
    scope rather than walking the chain — walking is what caused the bug above."""
    assert depths("let a = 1; print(a);") == [None, None]


def test_the_resolver_counts_scopes_out():
    assert depths("{ let a = 1; { let b = a; } }") == [1]


def test_a_parameter_resolves_to_the_function_scope():
    assert depths("fn f(x) { return x; }") == [0]


def test_a_capture_resolves_past_the_inner_function():
    assert depths("fn outer(x) { fn inner() { return x; } return inner; }") == [1, 0]


# -- programs rejected before they run ---------------------------------------

def test_a_variable_cannot_be_read_in_its_own_initialiser():
    """`let a = a;` reads a name that is declared but not yet defined. At run
    time it would quietly produce nil; here it is a compile error."""
    with pytest.raises(ResolveError, match="own initialiser"):
        check("{ let a = 1; { let a = a; } }")


def test_a_name_cannot_be_declared_twice_in_one_scope():
    with pytest.raises(ResolveError, match="already declared"):
        check("{ let a = 1; let a = 2; }")


def test_shadowing_in_a_nested_scope_is_fine():
    check("{ let a = 1; { let a = 2; } }")


def test_the_same_name_in_sibling_scopes_is_fine():
    check("{ let a = 1; } { let a = 2; }")


def test_a_top_level_redeclaration_is_allowed():
    """The global scope is the REPL's scope, where redefining a name is the
    normal way to work."""
    check("let a = 1; let a = 2;")


def test_return_outside_a_function_is_rejected():
    with pytest.raises(ResolveError, match="'return' outside a function"):
        check("return 1;")


def test_break_outside_a_loop_is_rejected():
    with pytest.raises(ResolveError, match="'break' outside a loop"):
        check("break;")


def test_continue_outside_a_loop_is_rejected():
    with pytest.raises(ResolveError, match="'continue' outside a loop"):
        check("continue;")


def test_break_inside_a_function_inside_a_loop_is_rejected():
    """A function is a control-flow boundary: `break` in it cannot mean the
    enclosing loop, because the function may be called anywhere."""
    with pytest.raises(ResolveError, match="outside a loop"):
        check("while (true) { fn f() { break; } }")


def test_break_is_allowed_in_a_nested_loop():
    check("while (true) { while (true) { break; } break; }")


def test_return_is_allowed_in_a_nested_function():
    check("fn outer() { fn inner() { return 1; } return inner; }")


def test_an_error_carries_its_position():
    with pytest.raises(ResolveError) as error:
        check("let x = 1;\nbreak;")
    assert error.value.line == 2


def test_resolution_is_idempotent():
    """Resolving twice must not shift any depth — a pass that is not
    idempotent breaks the REPL, which resolves each new statement against the
    same tree of definitions."""
    source = "{ let a = 1; { let b = a; } }"
    assert depths(source) == depths(source)


def test_a_forward_reference_to_a_later_global_is_allowed(run):
    """Mutual recursion at the top level needs this: `even` names `odd` before
    `odd` exists, and only the call has to succeed, not the definition."""
    assert run("""
        fn even(n) { if (n == 0) return true; return odd(n - 1); }
        fn odd(n) { if (n == 0) return false; return even(n - 1); }
        print(even(10));
        print(odd(10));
    """) == ["true", "false"]
