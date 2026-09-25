"""pebble: run a Pebble program, or poke at the stages that run it."""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
from dataclasses import fields, is_dataclass
from pathlib import Path

from . import __version__
from .builtins import builtin_names
from .errors import PebbleError
from .interpreter import Interpreter
from .lexer import tokenize
from .parser import parse
from .resolver import resolve
from .syntax import Node
from .values import stringify


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pebble", description=__doc__)
    parser.add_argument("--version", action="version", version=f"pebble {__version__}")
    sub = parser.add_subparsers(dest="cmd")

    def source(p: argparse.ArgumentParser) -> None:
        p.add_argument("file", type=Path, nargs="?")
        p.add_argument("-c", "--code", help="a program given on the command line")

    run_cmd = sub.add_parser("run", help="run a program")
    source(run_cmd)
    run_cmd.add_argument("--max-depth", type=int, default=200)
    run_cmd.add_argument("--no-resolve", action="store_true",
                         help="skip static resolution, reproducing late variable binding")

    source(sub.add_parser("tokens", help="show the token stream"))
    source(sub.add_parser("ast", help="show the syntax tree"))

    bench = sub.add_parser("bench", help="time the interpreter against the host")
    bench.add_argument("-n", "--number", type=int, default=25)

    sub.add_parser("repl", help="an interactive prompt")
    sub.add_parser("builtins", help="list the standard library")
    return parser


def read_source(args) -> tuple[str, str]:
    if args.code:
        return args.code, "<command line>"
    if args.file:
        if not args.file.exists():
            raise FileNotFoundError(f"no such file: {args.file}")
        return args.file.read_text(encoding="utf-8"), str(args.file)
    raise ValueError("give a file or -c 'code'")


def show_tree(node, indent: int = 0) -> list[str]:
    pad = "  " * indent
    if isinstance(node, list):
        return [line for item in node for line in show_tree(item, indent)]
    if not is_dataclass(node) or not isinstance(node, Node):
        return [f"{pad}{node!r}"]

    lines = [f"{pad}{type(node).__name__}"]
    for field in fields(node):
        if field.name == "token":
            continue
        value = getattr(node, field.name)
        if value is None or value == []:
            continue
        if isinstance(value, (list, Node)) and not isinstance(value, str):
            lines.append(f"{pad}  {field.name}:")
            lines.extend(show_tree(value, indent + 2))
        else:
            lines.append(f"{pad}  {field.name}: {value!r}")
    return lines


def repl() -> int:
    interpreter = Interpreter()
    print(f"pebble {__version__} — an expression prints its value; Ctrl-D to leave")
    buffer = ""
    while True:
        try:
            line = input("... " if buffer else ">>> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        buffer = f"{buffer}\n{line}" if buffer else line
        if not buffer.strip():
            buffer = ""
            continue
        if buffer.count("{") > buffer.count("}"):
            continue
        if not buffer.rstrip().endswith(("}", ";")):
            buffer += ";"

        try:
            program = parse(tokenize(buffer))
            resolve(program, set(interpreter.globals.values))
            value = interpreter.run(program)
            if value is not None:
                print(stringify(value))
        except PebbleError as error:
            print(f"pebble: {error}", file=sys.stderr)
        buffer = ""


FIB = """
fn fib(n) { if (n < 2) return n; return fib(n - 1) + fib(n - 2); }
print(fib(%d));
"""


def bench(number: int) -> int:
    """Time this interpreter honestly, against the language it is written in.

    A tree walker allocates an environment per call and dispatches on the node
    type for every operation. It is not going to be fast, and quoting only its
    own numbers would hide by how much.
    """
    def host_fib(n: int) -> int:
        return n if n < 2 else host_fib(n - 1) + host_fib(n - 2)

    interpreter = Interpreter(output=io.StringIO(), max_depth=number + 10)
    program = parse(tokenize(FIB % number))
    resolve(program, set(interpreter.globals.values))

    start = time.perf_counter()
    interpreter.run(program)
    pebble_time = time.perf_counter() - start

    start = time.perf_counter()
    host_fib(number)
    host_time = time.perf_counter() - start

    print(f"fib({number}), {interpreter.calls:,} calls")
    print(f"  pebble  {pebble_time:8.3f}s   {interpreter.calls / pebble_time:12,.0f} calls/s")
    print(f"  python  {host_time:8.3f}s   {interpreter.calls / host_time:12,.0f} calls/s")
    print(f"  ratio   {pebble_time / host_time:8.1f}x slower than the host language")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point. Wraps the real work so piping into `head` — which closes the
    pipe early — ends quietly instead of printing a BrokenPipeError."""
    try:
        return _run(argv)
    except BrokenPipeError:
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 0
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130
    except PebbleError as error:
        print(f"pebble: {error}", file=sys.stderr)
        return 1
    except (ValueError, FileNotFoundError) as error:
        print(f"pebble: {error}", file=sys.stderr)
        return 2


def _run(argv: list[str] | None) -> int:
    args = build_parser().parse_args(argv)
    command = args.cmd or "repl"

    if command == "repl":
        return repl()
    if command == "builtins":
        interpreter = Interpreter()
        for name in builtin_names(interpreter):
            function = interpreter.globals.values[name]
            print(f"{name:<8} {function.arity} argument(s)")
        return 0
    if command == "bench":
        return bench(args.number)

    source, origin = read_source(args)

    if command == "tokens":
        for token in tokenize(source):
            print(f"{token.line:>4}:{token.column:<4} {token!r}")
        return 0

    if command == "ast":
        print("\n".join(show_tree(parse(tokenize(source)).statements)))
        return 0

    interpreter = Interpreter(max_depth=args.max_depth, resolved=not args.no_resolve)
    try:
        # Lex, parse and resolve errors name the file too, not only runtime ones.
        program = parse(tokenize(source))
        if not args.no_resolve:
            resolve(program, set(interpreter.globals.values))
        interpreter.run(program)
    except PebbleError as error:
        print(f"{origin}:{error}", file=sys.stderr)
        return 1
    return 0
