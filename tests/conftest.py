import io
from pathlib import Path

import pytest

from pebble import Interpreter, parse, resolve, tokenize

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def execute(source: str, *, resolved: bool = True, max_depth: int = 200):
    """Run a program and return (printed lines, interpreter)."""
    output = io.StringIO()
    interpreter = Interpreter(output=output, max_depth=max_depth, resolved=resolved)
    program = parse(tokenize(source))
    if resolved:
        resolve(program, set(interpreter.globals.values))
    interpreter.run(program)
    return output.getvalue().splitlines(), interpreter


@pytest.fixture()
def run():
    """Run a program and return the printed lines."""
    def _run(source: str, **kwargs):
        return execute(source, **kwargs)[0]
    return _run


@pytest.fixture()
def value():
    """Run `print(<expression>)` and return the single printed line."""
    def _value(expression: str, **kwargs):
        lines = execute(f"print({expression});", **kwargs)[0]
        assert len(lines) == 1
        return lines[0]
    return _value


@pytest.fixture(scope="session")
def examples():
    return EXAMPLES
