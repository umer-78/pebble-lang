// Quicksort and binary search, to show lists, recursion and early return.

fn quicksort(xs) {
  if (len(xs) < 2) return xs;

  let pivot = xs[0];
  let less = [];
  let same = [];
  let more = [];

  for (let i = 0; i < len(xs); i = i + 1) {
    let x = xs[i];
    if (x < pivot) {
      push(less, x);
    } else if (x > pivot) {
      push(more, x);
    } else {
      push(same, x);
    }
  }

  return quicksort(less) + same + quicksort(more);
}

fn search(xs, target) {
  let low = 0;
  let high = len(xs) - 1;
  while (low <= high) {
    let mid = floor((low + high) / 2);
    if (xs[mid] == target) return mid;
    if (xs[mid] < target) {
      low = mid + 1;
    } else {
      high = mid - 1;
    }
  }
  return -1;
}

let data = [9, 3, 7, 1, 8, 3, 5, 2, 6, 4];
let sorted = quicksort(data);
print(sorted);
print(search(sorted, 7));
print(search(sorted, 42));
print(data);                 // quicksort did not touch the original
