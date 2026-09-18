"""Pebble: a small language with a lexer, a Pratt parser and a tree-walking interpreter."""

from .errors import DepthError, LexError, ParseError, PebbleError, ResolveError, RuntimeError_
from .interpreter import Interpreter
from .lexer import Lexer, tokenize
from .parser import Parser, parse
from .resolver import Resolver, resolve
from .values import Builtin, PebbleFunction, stringify, truthy, type_name

__all__ = [
    "Builtin", "DepthError", "Interpreter", "LexError", "Lexer", "ParseError",
    "Parser", "PebbleError", "PebbleFunction", "ResolveError", "Resolver",
    "RuntimeError_", "parse", "resolve", "run", "stringify", "tokenize",
    "truthy", "type_name",
]
__version__ = "1.0.0"


def run(source: str, *, output=None, max_depth: int = 200, resolved: bool = True):
    """Lex, parse, resolve and execute a program. Returns the interpreter."""
    interpreter = Interpreter(output=output, max_depth=max_depth, resolved=resolved)
    program = parse(tokenize(source))
    if resolved:
        resolve(program, set(interpreter.globals.values))
    interpreter.run(program)
    return interpreter
