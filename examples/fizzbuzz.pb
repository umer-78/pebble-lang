// The smallest program that exercises loops, branches and string building.
// There is no ternary operator on purpose: one conditional form is enough for a
// language this size, and `if` as a statement keeps the grammar honest.

fn fizzbuzz(n) {
  let out = [];
  for (let i = 1; i <= n; i = i + 1) {
    let word = "";
    if (i % 3 == 0) word = word + "Fizz";
    if (i % 5 == 0) word = word + "Buzz";
    if (word == "") {
      push(out, i);
    } else {
      push(out, word);
    }
  }
  return out;
}

print(join(fizzbuzz(15), " "));
