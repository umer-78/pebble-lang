"""Evaluating programs: arithmetic, truth, collections, closures and failure."""

from __future__ import annotations

import pytest

from pebble import DepthError, RuntimeError_

# -- arithmetic --------------------------------------------------------------

@pytest.mark.parametrize(("source", "expected"), [
    ("1 + 1", "2"), ("7 - 9", "-2"), ("3 * 4", "12"), ("7 / 2", "3.5"),
    ("7 % 3", "1"), ("-7 % 3", "2"), ("2 + 3 * 4", "14"), ("(2 + 3) * 4", "20"),
    ("-(-5)", "5"),
])
def test_arithmetic(value, source, expected):
    assert value(source) == expected


def test_whole_numbers_print_without_a_decimal_point(value):
    """One number type internally; the '.0' is the implementation's business."""
    assert value("2 + 2") == "4"
    assert value("5 / 2") == "2.5"
    assert value("10 / 4") == "2.5"


def test_division_by_zero_is_an_error(run):
    """Returning inf would let the mistake travel to somewhere unrelated."""
    with pytest.raises(RuntimeError_, match="division by zero"):
        run("print(1 / 0);")


def test_modulo_by_zero_is_an_error(run):
    with pytest.raises(RuntimeError_, match="division by zero"):
        run("print(1 % 0);")


def test_arithmetic_on_a_string_is_an_error(run):
    with pytest.raises(RuntimeError_, match="cannot apply"):
        run('print("a" - 1);')


def test_adding_a_number_to_a_string_is_an_error(run):
    """No implicit conversion. `"total: " + 3` is a mistake often enough that
    silently producing "total: 3" costs more than it saves — `str` is one call."""
    with pytest.raises(RuntimeError_, match="cannot add"):
        run('print("total: " + 3);')


def test_strings_and_lists_concatenate(value):
    assert value('"ab" + "cd"') == "abcd"
    assert value("[1] + [2, 3]") == "[1, 2, 3]"


# -- truth and equality ------------------------------------------------------

@pytest.mark.parametrize(("source", "expected"), [
    ("!true", "false"), ("!false", "true"), ("!nil", "true"),
    ("!0", "false"), ('!""', "false"), ("![]", "false"),
])
def test_only_nil_and_false_are_false(value, source, expected):
    """Zero is not false, nor is the empty string or list. A language where
    `if (count)` means something different from `if (handle)` invites the bug
    where a legitimate zero reads as absence."""
    assert value(source) == expected


@pytest.mark.parametrize(("source", "expected"), [
    ("1 == 1", "true"), ("1 == 2", "false"), ("1 != 2", "true"),
    ('"a" == "a"', "true"), ("nil == nil", "true"), ("true == true", "true"),
    ("1 == true", "false"), ("0 == false", "false"), ("nil == false", "false"),
    ('"1" == 1', "false"), ("[1, 2] == [1, 2]", "true"),
])
def test_equality_does_not_convert(value, source, expected):
    """In the host language `1.0 == True`, which would make `1 == true` true
    here by accident. Types are compared before values."""
    assert value(source) == expected


def test_comparison_of_different_types_is_an_error(run):
    with pytest.raises(RuntimeError_, match="cannot compare"):
        run('print(1 < "a");')


def test_strings_compare_lexicographically(value):
    assert value('"apple" < "banana"') == "true"


# -- logical operators -------------------------------------------------------

def test_and_and_or_return_an_operand_not_a_boolean(value):
    """So `name or "anonymous"` works as a default."""
    assert value('nil or "fallback"') == "fallback"
    assert value('"given" or "fallback"') == "given"
    assert value('nil and "never"') == "nil"
    assert value('"a" and "b"') == "b"


def test_or_short_circuits(run):
    assert run('fn boom() { print("ran"); return true; } print(true or boom());') == ["true"]


def test_and_short_circuits(run):
    assert run('fn boom() { print("ran"); return true; } print(false and boom());') == ["false"]


def test_short_circuiting_makes_a_guard_possible(run):
    assert run("let xs = nil; print(xs != nil and xs[0]);") == ["false"]


# -- variables and scope -----------------------------------------------------

def test_a_declaration_without_an_initialiser_is_nil(run):
    assert run("let a; print(a);") == ["nil"]


def test_an_undefined_variable_is_an_error_not_nil(run):
    with pytest.raises(RuntimeError_, match="undefined variable 'nope'"):
        run("print(nope);")


def test_assignment_returns_the_assigned_value(run):
    assert run("let a = 1; print(a = 2); print(a);") == ["2", "2"]


def test_a_block_scopes_its_declarations(run):
    assert run('let a = "outer"; { let a = "inner"; print(a); } print(a);') == [
        "inner", "outer"]


def test_assignment_reaches_the_enclosing_scope(run):
    assert run('let a = "outer"; { a = "changed"; } print(a);') == ["changed"]


# -- control flow ------------------------------------------------------------

def test_if_and_else(run):
    assert run('if (1 < 2) print("yes"); else print("no");') == ["yes"]
    assert run('if (1 > 2) print("yes"); else print("no");') == ["no"]


def test_while_counts(run):
    assert run("let i = 0; while (i < 3) { i = i + 1; } print(i);") == ["3"]


def test_break_leaves_the_loop(run):
    assert run("""
        let total = 0;
        for (let i = 0; i < 10; i = i + 1) { if (i == 3) break; total = total + i; }
        print(total);
    """) == ["3"]


def test_continue_skips_the_rest_of_the_body_but_not_the_increment(run):
    """The reason a `for` loop's increment is not appended to its body: with it
    appended, `continue` would jump over it and this loop would never finish."""
    assert run("""
        let total = 0;
        for (let i = 0; i < 5; i = i + 1) { if (i % 2 == 0) continue; total = total + i; }
        print(total);
    """) == ["4"]


def test_continue_in_a_while_loop_does_not_hang(run):
    assert run("""
        let i = 0;
        let seen = 0;
        while (i < 5) { i = i + 1; if (i == 2) continue; seen = seen + 1; }
        print(seen);
    """) == ["4"]


def test_break_only_leaves_the_inner_loop(run):
    assert run("""
        let count = 0;
        for (let i = 0; i < 3; i = i + 1) {
          for (let j = 0; j < 3; j = j + 1) { if (j == 1) break; count = count + 1; }
        }
        print(count);
    """) == ["3"]


# -- closures ----------------------------------------------------------------

def test_a_closure_keeps_its_own_state(run):
    assert run("""
        fn counter() { let n = 0; return fn() { n = n + 1; return n; }; }
        let a = counter();
        let b = counter();
        print([a(), a(), b()]);
    """) == ["[1, 2, 1]"]


def test_each_for_iteration_gets_its_own_binding(run):
    """The oldest bug in this shape. With one binding shared by every
    iteration these print 3, 3, 3 — the value the loop ended on."""
    assert run("""
        let fns = [];
        for (let i = 0; i < 3; i = i + 1) { push(fns, fn() { return i; }); }
        print([fns[0](), fns[1](), fns[2]()]);
    """) == ["[0, 1, 2]"]


def test_a_while_loop_shares_one_binding(run):
    """The contrast that makes the previous test mean something. A `while` loop
    has no variable of its own, so there is nothing to give a fresh copy of."""
    assert run("""
        let fns = [];
        let i = 0;
        while (i < 3) { push(fns, fn() { return i; }); i = i + 1; }
        print([fns[0](), fns[1](), fns[2]()]);
    """) == ["[3, 3, 3]"]


def test_the_loop_still_terminates_with_per_iteration_bindings(run):
    """Copying the variable per iteration must not lose the increment."""
    assert run("let last = 0; for (let i = 0; i < 100; i = i + 1) { last = i; } print(last);") == ["99"]


def test_an_enclosing_variable_is_visible_inside_a_for_body(run):
    """The per-iteration scope replaces the loop's scope rather than nesting
    inside it; nesting would add a link the resolver never counted and every
    outer variable would be looked up one scope short."""
    assert run("""
        { let outside = "seen";
          for (let i = 0; i < 2; i = i + 1) { print(outside); } }
    """) == ["seen", "seen"]


def test_functions_are_values(run):
    assert run("""
        fn twice(f, x) { return f(f(x)); }
        print(twice(fn(n) { return n * 3; }, 2));
    """) == ["18"]


def test_a_builtin_is_a_value_too(run):
    assert run("let show = print; show(42);") == ["42"]


def test_recursion(run):
    assert run("fn fact(n) { if (n <= 1) return 1; return n * fact(n - 1); } print(fact(10));") == [
        "3628800"]


def test_a_function_without_a_return_gives_nil(run):
    assert run("fn f() { let a = 1; } print(f());") == ["nil"]


def test_a_bare_return_gives_nil(run):
    assert run("fn f() { return; } print(f());") == ["nil"]


# -- collections -------------------------------------------------------------

def test_lists(value):
    assert value("[1, 2, 3][1]") == "2"
    assert value("[]") == "[]"


def test_negative_indices_count_from_the_end(value):
    assert value("[1, 2, 3][-1]") == "3"


def test_an_index_out_of_range_is_an_error(run):
    with pytest.raises(RuntimeError_, match="outside a collection"):
        run("print([1, 2][5]);")


def test_a_fractional_index_is_an_error(run):
    with pytest.raises(RuntimeError_, match="whole number"):
        run("print([1, 2][0.5]);")


def test_list_assignment(run):
    assert run("let xs = [1, 2, 3]; xs[0] = 9; print(xs);") == ["[9, 2, 3]"]


def test_strings_index_like_lists(value):
    assert value('"abc"[1]') == "b"


def test_maps(run):
    assert run('let m = {"a": 1}; m["b"] = 2; print(m["b"]); print(len(m));') == ["2", "2"]


def test_a_missing_key_is_an_error(run):
    with pytest.raises(RuntimeError_, match="no key"):
        run('let m = {"a": 1}; print(m["b"]);')


def test_a_list_cannot_be_a_map_key(run):
    with pytest.raises(RuntimeError_, match="cannot be a map key"):
        run("let m = {}; m[[1]] = 2;")


def test_lists_are_references(run):
    """Assigning a list does not copy it — worth a test because the alternative
    is a language where `push` sometimes has no visible effect."""
    assert run("let a = [1]; let b = a; push(b, 2); print(a);") == ["[1, 2]"]


# -- builtins ----------------------------------------------------------------

@pytest.mark.parametrize(("source", "expected"), [
    ('len("abc")', "3"), ("len([1, 2])", "2"), ('str(3)', "3"), ('num("2.5")', "2.5"),
    ("type(1)", "number"), ('type("a")', "string"), ("type([])", "list"),
    ("type(nil)", "nil"), ("type(true)", "bool"), ("type(print)", "function"),
    ("sqrt(9)", "3"), ("floor(2.7)", "2"), ("abs(-3)", "3"),
    ('join(["a", "b"], "-")', "a-b"), ('len(split("a b c", " "))', "3"),
    ('slice("abcdef", 1, 3)', "bc"),
])
def test_builtins(value, source, expected):
    assert value(source) == expected


def test_type_of_a_user_function_is_function(value):
    assert value("type(fn() { return 1; })") == "function"


def test_num_rejects_nonsense(run):
    with pytest.raises(RuntimeError_, match="not a number"):
        run('print(num("banana"));')


def test_sqrt_of_a_negative_number_is_an_error(run):
    with pytest.raises(RuntimeError_, match="negative"):
        run("print(sqrt(-1));")


def test_pop_from_an_empty_list_is_an_error(run):
    with pytest.raises(RuntimeError_, match="empty list"):
        run("print(pop([]));")


# -- calling -----------------------------------------------------------------

def test_the_wrong_number_of_arguments_is_an_error(run):
    with pytest.raises(RuntimeError_, match="takes 1 argument"):
        run("fn f(a) { return a; } f(1, 2);")


def test_calling_a_non_function_is_an_error(run):
    with pytest.raises(RuntimeError_, match="cannot call a number"):
        run("let a = 1; a();")


def test_runaway_recursion_is_a_program_error_not_a_crash(run):
    """A tree walker recurses on the host stack, so unbounded guest recursion
    would otherwise surface as a host RecursionError out of the interpreter's
    internals rather than as an error in the program that caused it."""
    with pytest.raises(DepthError, match="call depth exceeded"):
        run("fn f() { return f(); } f();", max_depth=50)


def test_the_depth_limit_does_not_stop_legitimate_recursion(run):
    assert run("fn down(n) { if (n == 0) return 0; return down(n - 1); } print(down(40));",
               max_depth=50) == ["0"]


def test_depth_is_released_after_a_call_returns(run):
    """Counting frames without decrementing would make a long sequence of
    shallow calls fail as though it were deep recursion."""
    assert run("""
        fn one() { return 1; }
        let total = 0;
        for (let i = 0; i < 200; i = i + 1) { total = total + one(); }
        print(total);
    """, max_depth=5) == ["200"]


# -- errors carry positions --------------------------------------------------

def test_a_runtime_error_carries_its_line(run):
    with pytest.raises(RuntimeError_) as error:
        run("let a = 1;\nlet b = 2;\nprint(a / 0);")
    assert error.value.line == 3


# -- the host stack ----------------------------------------------------------

def test_runaway_recursion_is_caught_at_the_default_depth(run):
    """Not just at whatever small limit a test chooses.

    The first version of this suite only checked a `max_depth` of 50 and
    passed, while the default of 200 crashed: seven host frames per guest call
    against Python's default limit of 1,000 leaves room for about 140 guest
    frames, so the interpreter's own counter was never reached.
    """
    with pytest.raises(DepthError, match="call depth exceeded 200"):
        run("fn f() { return f(); } f();")


def test_one_guest_call_costs_seven_host_frames():
    """The constant the host-stack calculation is built on, measured here so it
    cannot drift. If the evaluator grows a layer, this fails and the constant is
    updated rather than quietly overrunning the stack."""
    import inspect
    import io

    from pebble import Interpreter, parse, resolve, tokenize
    from pebble.interpreter import HOST_FRAMES_PER_CALL
    from pebble.values import Builtin

    seen: list[int] = []
    interpreter = Interpreter(output=io.StringIO())
    interpreter.globals.define("probe", Builtin("probe", 0, lambda: seen.append(len(inspect.stack(0)))))

    program = parse(tokenize("fn down(n) { if (n == 0) return probe(); return down(n - 1); }"
                             " down(0); down(1); down(2);"))
    resolve(program, set(interpreter.globals.values))
    interpreter.run(program)

    assert seen[1] - seen[0] == seen[2] - seen[1] == HOST_FRAMES_PER_CALL


def test_a_max_depth_the_host_cannot_support_is_refused():
    """Better to refuse at construction than to raise the host limit so far
    that the C stack segfaults, which no `except` can catch."""
    from pebble import Interpreter

    with pytest.raises(ValueError, match="host recursion limit"):
        Interpreter(max_depth=100_000)


def test_the_host_recursion_limit_is_put_back_after_a_run(run):
    """It is a process-wide setting, and this is a library."""
    import sys

    before = sys.getrecursionlimit()
    run("fn down(n) { if (n == 0) return 0; return down(n - 1); } print(down(100));",
        max_depth=150)
    assert sys.getrecursionlimit() == before


def test_the_limit_is_put_back_even_when_the_program_fails(run):
    import sys

    before = sys.getrecursionlimit()
    with pytest.raises(DepthError):
        run("fn f() { return f(); } f();", max_depth=150)
    assert sys.getrecursionlimit() == before
