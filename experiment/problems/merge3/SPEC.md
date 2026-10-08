# Problem 18: Three-way text merge

Implement `def merge(base, ours, theirs)` in Python, using only the standard library.

`base` is the common ancestor of a text; `ours` and `theirs` are two edited versions of it. All three are `str` (any
characters, possibly empty). Merge the two sets of edits line by line and return

```python
{"text": merged_text, "conflicts": number_of_conflict_blocks, "clean": conflicts == 0}
```

The rules below fix exactly one output for every input. Where they differ from git, GNU diff3 or any other tool,
these rules win.

## 1. Lines

1. A text is split into lines at `"\n"` only, and every line keeps its `"\n"`. The last line may lack one:
   `"a\nb"` is the two lines `"a\n"`, `"b"`; `"a\nb\n"` is `"a\n"`, `"b\n"`; `"\n"` is one line `"\n"`;
   `""` has no lines at all.
2. No other character ends a line. `"\r"` (alone or before `"\n"`), form feed, `"\x85"`, `"\u2028"` and every
   other character are ordinary text inside a line.
3. Two lines are equal only if they are identical strings, including the `"\n"` and any `"\r"`. So a last line
   `"b"` (no newline) differs from `"b\n"`, and `"a\r\n"` differs from `"a\n"`.
4. Joining a text's lines in order gives back the text exactly.

## 2. The diff

The diff of base against another version (ours or theirs) decides which base lines are kept and which line of the
other version each kept line is matched with. Let A be the lines of base (N lines) and B the lines of the other
version (M lines), both 0-indexed.

Picture the grid of points (x, y) with 0 ≤ x ≤ N and 0 ≤ y ≤ M. From (x, y) a path may move:
- **right** to (x+1, y): delete A[x];
- **down** to (x, y+1): insert B[y];
- **diagonally** to (x+1, y+1), only when A[x] == B[y]: keep A[x], matched with B[y].

A point's diagonal number is k = x − y. The diff is the path from (0, 0) to (N, M) built by this procedure (Myers'
greedy algorithm). V maps a diagonal number to an x value.

1. Before step 0, set V[1] = 0.
2. Do step d for d = 0, 1, 2, … . Step d handles k = −d, −d+2, …, d−2, d. Every V value it reads is a value from
   step d−1 (or the V[1] = 0 above when d = 0). For each k, do sub-steps 1–4:
   1. Choose how to enter diagonal k:
      - if k = −d: **down** from diagonal k+1; start x = V[k+1];
      - else if k = d: **right** from diagonal k−1; start x = V[k−1] + 1;
      - otherwise let x_down = V[k+1] and x_right = V[k−1] + 1. If x_down ≥ x_right go **down** with start
        x = x_down; otherwise go **right** with start x = x_right. On a tie, the down move (insertion) wins.
   2. Let y = x − k. While x < N and y < M and A[x] == B[y]: add 1 to both x and y.
   3. Set V[k] = x for step d. The path to this point is: the path to the step d−1 point of the diagonal chosen in
      sub-step 1, then that one down or right move, then the diagonal moves of sub-step 2. At step 0 there is no
      earlier path: the path starts at (0, 0) and is just the diagonal moves of sub-step 2.
   4. If (x, y) = (N, M), stop. The path to this point is the diff.

Some points reached along the way lie outside the grid (x > N or y > M). Keep them as they are; sub-step 2 simply
makes no diagonal moves from them. The procedure always stops by step N + M, and its path has the fewest possible
inserted plus deleted lines.

A[x] is **matched** with B[y] when the diff contains the diagonal move from (x, y) to (x+1, y+1). Every other base
line is deleted and every other line of B is inserted. Matches keep their order: if A[x] ↔ B[y] and A[x'] ↔ B[y']
with x < x', then y < y'.

Among the many shortest paths this procedure picks one particular path, and your matches must be exactly its
matches, however you compute them.

## 3. Merging

Diff base against ours and, separately, base against theirs (base is always A).

1. A base line is **stable** if it is matched in both diffs. Call the stable base lines s_1 < s_2 < … < s_r. Their
   partners o_1 < … < o_r in ours and t_1 < … < t_r in theirs also increase.
2. The stable lines cut all three texts into **chunks**. Chunk j (j = 1 … r+1) is made of three parts:
   - the base lines strictly between s_{j−1} and s_j;
   - the ours lines strictly between o_{j−1} and o_j;
   - the theirs lines strictly between t_{j−1} and t_j.

   Here s_0 = o_0 = t_0 = −1, s_{r+1} = number of base lines, o_{r+1} = number of ours lines and
   t_{r+1} = number of theirs lines. A part may be empty, and a chunk whose three parts are all empty is skipped.
3. Write, in order: chunk 1, stable line s_1, chunk 2, s_2, …, s_r, chunk r+1. A stable line is written once (it
   is the same string in all three texts).
4. Resolve a chunk by comparing its parts as lists of lines (b = base part, o = ours part, t = theirs part), testing
   in this order:
   1. if o == b: write t (only theirs changed it);
   2. else if t == b: write o (only ours changed it);
   3. else if o == t: write o once (both made the same change);
   4. else it is a **conflict**: write a conflict block (section 4).

These consequences follow from the rules above:
- Two edits with no stable line between them fall into one chunk, so they conflict even when they change different
  lines. For example, ours edits line 2 and theirs edits line 3, or ours inserts a line just before a line that
  theirs edits or deletes.
- Insertions by both sides at the same place are written once if identical; otherwise they conflict, and the base
  part of the block is empty.
- A line that is identical in all three texts still separates chunks only if both diffs matched it.

## 4. Conflict blocks

A conflict block is written as:

1. the marker line `<<<<<<< ours`
2. the ours part
3. the marker line `||||||| base`
4. the base part
5. the marker line `=======`
6. the theirs part
7. the marker line `>>>>>>> theirs`

Each marker line is exactly the text shown followed by `"\n"`: seven `<`, `|`, `=` or `>` characters, then (except
for `=======`) one space and the label. The `||||||| base` marker is written even when the base part is empty.
Every part is written in full: lines that ours and theirs have in common are **not** moved out of the block. Inside
a block, a part whose last line has no `"\n"` (it was the last line of its text) gets one `"\n"` appended after that
line, so each marker starts a new line. Input lines that look like markers are ordinary text.

## 5. Output

- `text`: everything written by section 3, joined in order, with nothing added or removed outside conflict blocks.
  So the merged text ends with `"\n"` exactly when the last thing written ends with one. It ends without a newline
  when the last thing written is a line without one (a stable line or a line of a resolved chunk). It always ends
  with `"\n"` when it ends with a conflict block. If nothing is written, `text` is `""`.
- `conflicts`: the number of conflict blocks written (not a count of marker-like lines in `text`).
- `clean`: `True` if `conflicts` is 0, else `False`.

## Size

Each input has at most 60 000 lines and 3 000 000 characters. In the large inputs, each of ours and theirs differs
from base by at most 300 inserted plus deleted lines (D, the step at which the procedure stops). The whole call must
finish within a few seconds in CPython, with about 1 GB of memory. Following the procedure takes about O((N+M)·D)
time. Anything that fills an N×M table (in time or memory) is far too slow, and recursing once per line exceeds
Python's default recursion limit.

## Examples

Example 1 (edits separated by a stable line merge cleanly; an insertion by one side):

```python
merge("def f():\n    return 1\n\ndef g():\n    return 2\n",
      "def f():\n    return 10\n\ndef g():\n    return 2\n",
      "def f():\n    return 1\n\ndef g():\n    log()\n    return 2\n")
# -> {"text": "def f():\n    return 10\n\ndef g():\n    log()\n    return 2\n", "conflicts": 0, "clean": True}
```

Example 2 (a conflict block, and the same change made on both sides written once):

```python
merge("a\nb\nc\nd\ne\n", "a\nB\nc\nD\ne\n", "a\nX\nc\nD\ne\n")
# -> {"text": "a\n<<<<<<< ours\nB\n||||||| base\nb\n=======\nX\n>>>>>>> theirs\nc\nD\ne\n",
#     "conflicts": 1, "clean": False}
```

Example 3 (adding the final newline changes the last line; parts end with a newline inside the block):

```python
merge("x = 1\ny = 2", "x = 1\ny = 3", "x = 1\ny = 2\n")
# -> {"text": "x = 1\n<<<<<<< ours\ny = 3\n||||||| base\ny = 2\n=======\ny = 2\n>>>>>>> theirs\n",
#     "conflicts": 1, "clean": False}
```

Example 4 (the diff decides what is stable: base→ours keeps `b`, i.e. delete `a`, keep `b`, insert `a`, because
the tie at step 2 goes down):

```python
merge("a\nb\n", "b\na\n", "a\nb\nc\n")
# -> {"text": "b\n<<<<<<< ours\na\n||||||| base\n=======\nc\n>>>>>>> theirs\n", "conflicts": 1, "clean": False}
```
