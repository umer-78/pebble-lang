"""The command line: every subcommand, and the exit codes that matter."""

from __future__ import annotations

import pytest

from pebble.cli import main


def run_cli(capsys, *argv) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_run_a_program_from_the_command_line(capsys):
    code, out, _ = run_cli(capsys, "run", "-c", 'print("hello");')
    assert (code, out.strip()) == (0, "hello")


def test_run_a_program_from_a_file(capsys, examples):
    code, out, _ = run_cli(capsys, "run", str(examples / "fizzbuzz.pb"))
    assert code == 0
    assert "FizzBuzz" in out


def test_a_missing_file_is_reported(capsys):
    code, _, err = run_cli(capsys, "run", "no-such-file.pb")
    assert code == 2
    assert "no such file" in err


def test_no_source_is_reported(capsys):
    code, _, err = run_cli(capsys, "run")
    assert code == 2
    assert "give a file" in err


def test_a_parse_error_exits_one_and_names_the_line(capsys):
    code, _, err = run_cli(capsys, "run", "-c", "let a = ;")
    assert code == 1
    assert "line 1" in err


def test_a_runtime_error_exits_one(capsys):
    code, _, err = run_cli(capsys, "run", "-c", "print(1 / 0);")
    assert code == 1
    assert "division by zero" in err


def test_a_runtime_error_names_its_origin(capsys):
    code, _, err = run_cli(capsys, "run", "-c", "print(nope);")
    assert code == 1
    assert "<command line>" in err


def test_tokens(capsys):
    code, out, _ = run_cli(capsys, "tokens", "-c", "let a = 1;")
    assert code == 0
    assert "LET" in out and "NUMBER" in out and "EOF" in out


def test_tokens_shows_positions(capsys):
    _, out, _ = run_cli(capsys, "tokens", "-c", "let a = 1;")
    assert out.splitlines()[0].startswith("   1:1")


def test_ast(capsys):
    code, out, _ = run_cli(capsys, "ast", "-c", "let a = 1 + 2;")
    assert code == 0
    assert "Let" in out and "Binary" in out


def test_ast_leaves_out_empty_fields(capsys):
    """A tree dump nobody can read is a tree dump nobody uses."""
    _, out, _ = run_cli(capsys, "ast", "-c", "let a = 1;")
    assert "depth" not in out


def test_builtins_lists_the_standard_library(capsys):
    code, out, _ = run_cli(capsys, "builtins")
    assert code == 0
    names = [line.split()[0] for line in out.splitlines()]
    assert {"print", "len", "push", "keys", "sqrt"} <= set(names)
    assert names == sorted(names)


def test_bench_reports_both_languages(capsys):
    code, out, _ = run_cli(capsys, "bench", "-n", "12")
    assert code == 0
    assert "pebble" in out and "python" in out and "slower" in out


def test_no_resolve_reproduces_late_binding(capsys):
    """The flag exists so the resolver's effect can be shown, not guessed at."""
    source = 'let a = "global"; { fn f() { print(a); } f(); let a = "block"; f(); }'
    _, resolved, _ = run_cli(capsys, "run", "-c", source)
    _, unresolved, _ = run_cli(capsys, "run", "-c", source, "--no-resolve")
    assert resolved.split() == ["global", "global"]
    assert unresolved.split() == ["global", "block"]


def test_max_depth_is_configurable(capsys):
    code, _, err = run_cli(capsys, "run", "-c", "fn f() { return f(); } f();",
                           "--max-depth", "20")
    assert code == 1
    assert "call depth exceeded 20" in err


def test_version(capsys):
    with pytest.raises(SystemExit) as exit_:
        run_cli(capsys, "--version")
    assert exit_.value.code == 0
