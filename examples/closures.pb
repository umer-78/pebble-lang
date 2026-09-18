// Functions are values, and they remember where they were written.

fn counter() {
  let n = 0;
  return fn() {
    n = n + 1;
    return n;
  };
}

let a = counter();
let b = counter();
print([a(), a(), a(), b()]);      // two independent counters

fn adder(x) { return fn(y) { return x + y; }; }
let add10 = adder(10);
print(add10(5));

// Each iteration of a `for` gets its own binding, so these do not all
// capture the same variable.
let fns = [];
for (let i = 0; i < 3; i = i + 1) {
  push(fns, fn() { return i * i; });
}
print([fns[0](), fns[1](), fns[2]()]);

// A plain `while` has one binding, shared. This is the difference.
let shared = [];
let j = 0;
while (j < 3) {
  push(shared, fn() { return j; });
  j = j + 1;
}
print([shared[0](), shared[1](), shared[2]()]);
