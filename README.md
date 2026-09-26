# pebble: small programming language

[![CI](https://github.com/umer-78/pebble-lang/actions/workflows/ci.yml/badge.svg)](https://github.com/umer-78/pebble-lang/actions/workflows/ci.yml)

**Live demo:** https://umer-78.github.io/pebble-lang/

A small programming language, implemented from scratch in Python with no
dependencies: a hand-written lexer, a Pratt parser, a static scope resolver and
a tree-walking interpreter. Closures, first-class functions, lists, maps, a REPL
and error messages that name the line and column.

```
$ pebble run examples/closures.pb
[1, 2, 3, 1]
15
[0, 1, 4]
[3, 3, 3]
```

- **217 tests**, Python 3.10–3.12, standard library only
- Four stages you can look at separately: `pebble tokens`, `pebble ast`,
  `pebble run --no-resolve`, `pebble run`
- The two hard parts of scoping — closure capture and per-iteration bindings —
  are demonstrated by tests that fail against the obvious implementation

## Quick start

```bash
git clone https://github.com/umer-78/pebble-lang.git
cd pebble-lang
pip install -e ".[dev]"
pytest -q                          # 217 tests

pebble run examples/sort.pb
pebble run examples/wordcount.pb
pebble repl
pebble tokens -c 'let n = fib(2);'
pebble ast    -c 'let a = 1 + 2 * 3;'
pebble bench
```

## The language

```javascript
fn counter() {
  let n = 0;
  return fn() { n = n + 1; return n; };   // closes over n
}

let next = counter();
print([next(), next()]);                  // [1, 2]

let counts = {};
let words = split("the quick the", " ");
for (let i = 0; i < len(words); i = i + 1) {
  let word = words[i];
  if (has(counts, word)) { counts[word] = counts[word] + 1; }
  else { counts[word] = 1; }
}
print(counts["the"]);                     // 2
```

Numbers are floats, printed without the `.0` when whole. `nil` and `false` are
the only false values — not `0`, not `""`, not `[]`. `==` does not convert, so
`1 == true` is false. `and` and `or` short-circuit and return an operand rather
than a boolean, so `name or "anonymous"` is a default. Sixteen built-in
functions, all of them ordinary values you can pass around.

## A closure captures a scope, not a snapshot

This is the whole reason the resolver exists:

```javascript
let a = "global";
{
  fn show() { print(a); }
  show();                 // "global"
  let a = "block";
  show();                 // "global" — and this is the hard part
}
```

`show` was written before the block's own `a` existed, so both calls must print
`global`. An interpreter that looks a variable up by walking the environment
chain at call time gets the second one wrong: by then the block *does* contain
an `a`, and the closure finds it. The variable's meaning changed after the code
that used it was written.

The resolver walks the tree once before anything runs and records, for each
variable, how many scopes out its declaration is — a number that cannot change
later. Both behaviours are runnable, so the difference is a measurement rather
than an argument:

```
$ pebble run -c 'let a = "global"; { fn f() { print(a); } f(); let a = "block"; f(); }'
global
global

$ pebble run --no-resolve -c ...   # the same program, without the resolver
global
block
```

The same pass rejects programs that cannot work regardless of input — `let a =
a;`, `return` outside a function, `break` outside a loop, a name declared twice
in one scope — before a statement executes.

## Every loop iteration gets its own binding

The oldest bug in this shape, and the reason JavaScript needed `let`:

```javascript
let fns = [];
for (let i = 0; i < 3; i = i + 1) { push(fns, fn() { return i; }); }
print([fns[0](), fns[1](), fns[2]()]);      // [0, 1, 2]
```

With one binding shared by every iteration, all three closures see the value the
loop ended on and this prints `[2, 2, 2]`. A `while` loop has no variable of its
own, so nothing can be copied, and that is exactly what it does — the contrast
is in `examples/closures.pb`:

| loop | result |
| --- | --- |
| `for (let i = 0; …)` | `[0, 1, 2]` |
| `while` with an outer `let i` | `[3, 3, 3]` |

Giving each iteration a fresh copy is not sufficient on its own, and getting it
wrong is quiet. Run the increment in the same scope the body just captured and
every closure reads one too high — `[1, 2, 3]`, which looks close enough to
correct to survive a casual test. So the next iteration's scope is created
*before* the increment runs, and the scope the body captured is never touched
again. Two further details both cost a test to find:

- The per-iteration scope **replaces** the loop's own scope rather than nesting
  inside it. Nesting adds a link the resolver never counted, and every variable
  from an enclosing scope is then found one scope short.
- A `for` loop's increment is **not** appended to its body. If it were,
  `continue` would jump over it and the loop would never advance — a hang, not
  an error. It is carried on the loop node and run however the iteration ended.

## The depth limit has to outlast the host stack

A tree-walking interpreter recurses on the host's stack, so runaway recursion in
a Pebble program is runaway recursion in Python. Counting guest call frames and
raising a clean error is the obvious fix, and it was wrong in a way the first
test suite could not see: the test picked `max_depth=50` and passed, while the
default of 200 crashed with a Python traceback out of the evaluator's internals.

One guest call costs exactly **7** host frames. Python's default recursion limit
is **1,000**. So about 140 guest frames fit, and a limit of 200 was unreachable:

```
$ pebble run -c 'fn f() { return f(); } f();'
<command line>:line 1, column 18: call depth exceeded 200 — infinite recursion?
```

The interpreter now raises the host limit to cover `max_depth` for the duration
of a run and puts it back afterwards, refuses at construction a `max_depth` that
would need an unreasonable host limit, and catches `RecursionError` as a net in
case the evaluator ever grows a frame. `test_one_guest_call_costs_seven_host_frames`
measures the constant so it cannot drift, and
`test_runaway_recursion_is_caught_at_the_default_depth` checks the default
rather than a convenient one.

## Pratt parsing instead of a function per precedence level

The textbook recursive-descent grammar gives every precedence level its own
function: `equality` calls `comparison` calls `term` calls `factor` calls
`unary` calls `call` calls `primary`. With thirteen binary operators that is
seven near-identical functions whose only difference is which tokens they match
and which function they delegate to, and adding an operator means editing the
chain in two places.

Pratt parsing replaces the chain with a table and one loop:

```python
BINDING = {
    Kind.OR: 10,
    Kind.AND: 20,
    Kind.EQUAL_EQUAL: 30, Kind.BANG_EQUAL: 30,
    Kind.LESS: 40, Kind.LESS_EQUAL: 40, Kind.GREATER: 40, Kind.GREATER_EQUAL: 40,
    Kind.PLUS: 50, Kind.MINUS: 50,
    Kind.STAR: 60, Kind.SLASH: 60, Kind.PERCENT: 60,
}
```

Left-associativity falls out of recursing at a power *above* the operator's own;
right-associativity would be recursing at one below. A new operator is one line.
Thirteen parametrised tests assert the resulting shapes directly —
`1 + 2 * 3` → `(1 + (2 * 3))`, `8 / 4 / 2` → `((8 / 4) / 2)` — and one test
asserts that every binary token in the lexer has a table entry, because an
operator without one does not fail: it silently ends the expression.

```
$ pebble ast -c 'let a = 1 + 2 * 3;'
Let
  name: 'a'
  initialiser:
    Binary
      left:
        Literal
          value: 1.0
      operator: PLUS('+')
      right:
        Binary
          left:
            Literal
              value: 2.0
          operator: STAR('*')
          right:
            Literal
              value: 3.0
```

## Errors name a position

Every token carries a line and a column, and every error carries the token it
came from. The cost is two integers per token; the alternative is the single
most common failing of a hand-written interpreter.

```
$ pebble run bad.pb
bad.pb:line 3, column 19: undefined variable 'xs'

$ pebble run missing-semicolon.pb
pebble: line 3, column 1: expected ';' after the return value, found '}'

$ pebble run -c 'let a = 1; { let a = a; }'
pebble: line 1, column 22: 'a' is read inside its own initialiser
```

An undefined variable is an error, not `nil`. A typo in a name should not
quietly evaluate to nothing.

## Speed, measured against the language it is written in

A tree walker allocates an environment per call and dispatches on node type for
every operation. It is not fast, and quoting only its own numbers would hide by
how much:

```
$ pebble bench
fib(25), 242,786 calls
  pebble     2.868s         84,662 calls/s
  python     0.014s     16,889,459 calls/s
  ratio      199.5x slower than the host language
```

Roughly two hundred times slower than Python, which is itself not a fast
language. That is one run — the ratio moves by ten percent or so between runs,
and `pebble bench` prints whatever it measures rather than a number recorded
here. The fix is not a faster tree walker: it is compiling to bytecode and
running a loop over an instruction array instead of walking nodes, which is a
different project.

## Layout

```
src/pebble/
  lexer.py         source to tokens, with line and column on every one
  parser.py        tokens to a tree, by Pratt parsing
  resolver.py      static scope resolution, and the errors caught before running
  interpreter.py   the tree-walking evaluator
  environment.py   scopes, with the resolved and by-name lookup paths
  values.py        runtime values, truthiness, printing
  builtins.py      sixteen functions, all ordinary values
  cli.py           run, repl, tokens, ast, bench, builtins
examples/          four programs, whose output is asserted by the test suite
tests/             217 tests
```

The examples are not decoration: `tests/test_examples.py` runs each one and
compares its output line by line, and a further test fails if an example is
added without its expected output.

## Tests

```
$ pytest -q
217 passed
```

Grouped by stage — lexer, parser, resolver, interpreter, CLI, examples. The ones
that earn their place are the ones that fail against the obvious implementation:
the closure that must not see a later declaration, the loop whose closures must
not all agree, the increment that `continue` must not skip, and the depth limit
that must be reached before the host stack is.

## Licence

MIT.
