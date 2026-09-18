// Maps, strings and sorting by value — the shape of most real scripts.

let text = "the quick brown fox jumps over the lazy dog the fox sleeps";

fn tally(words) {
  let counts = {};
  for (let i = 0; i < len(words); i = i + 1) {
    let word = words[i];
    if (has(counts, word)) {
      counts[word] = counts[word] + 1;
    } else {
      counts[word] = 1;
    }
  }
  return counts;
}

fn top(counts, n) {
  let names = keys(counts);
  // selection sort by count, descending
  for (let i = 0; i < len(names); i = i + 1) {
    let best = i;
    for (let j = i + 1; j < len(names); j = j + 1) {
      if (counts[names[j]] > counts[names[best]]) best = j;
    }
    let swap = names[i];
    names[i] = names[best];
    names[best] = swap;
  }
  return slice(names, 0, n);
}

let counts = tally(split(text, " "));
let names = top(counts, 3);
for (let i = 0; i < len(names); i = i + 1) {
  print(names[i] + ": " + str(counts[names[i]]));
}
