# Problem 17: Ignore-file matcher

Implement `def ignored(files, rules)` in Python, using only the standard library.

Given the files of a project and the ignore files in its directories, report which files are ignored. The rules
resemble `.gitignore`, but they are complete as written here. Where they differ from a tool you know (git, `fnmatch`,
shell globs), this text wins.

- `files`: list of str, each a path such as `"src/app/main.py"`. Duplicates may occur.
- `rules`: dict mapping a directory path to a list of str, the lines of the ignore file in that directory. The key
  `""` is the root directory and `"src/app"` is a subdirectory.

A **character** is one Unicode code point (one element of a Python str). All comparisons are exact and
case-sensitive.

## 1. Paths and directories

1. Split each path at every `/` into **segments**. The path is **invalid** if any segment is empty, `.` or `..`. So
   the empty path, a leading or trailing `/`, and `//` are all invalid. Every other character, including spaces, `\`,
   `*`, `[`, `!` and `#`, is an ordinary part of a name. Nothing is trimmed.
2. The **directories** are the paths made of the first k segments, 1 ≤ k < (number of segments), of each path that
   passed step 1. The root `""` is not one of them and is never ignored.
3. A path that passed step 1 but is also a directory (for example `"a"` when `"a/b"` is given) is invalid too. It is
   still a directory.
4. The remaining valid paths are the **files**. The **parent** of a path is its first n−1 segments (`""` for a
   one-segment path).

## 2. Reading an ignore-file line

Apply these steps in order to each line.

1. If the line's first character is `#`, the line is a comment. Skip it.
2. Remove trailing spaces. Reading left to right, a `\` and the character after it form an **escape pair**. Remove
   the run of space characters (U+0020) at the end of the line, except any space that is the second half of an escape
   pair. Leading spaces, tabs and all other characters stay.
3. If the line is now empty, skip it.
4. If it starts with `!`, the rule is **negated**. Remove that one `!`.
5. If it ends with `/`, the rule is **directory-only**. Remove that one `/`.
6. If it now contains a `/` anywhere, the rule is **anchored**. Then, if it starts with `/`, remove that one `/`.
7. If it is now empty, skip it. Otherwise split it at every `/` into **pattern segments**. An unanchored rule has
   exactly one.

Steps 1 and 3–7 treat `\` as an ordinary character: escapes matter only in step 2 and inside pattern segments
(section 3), and a `\` never protects a `/`. So `\#x` and `\!x` are ordinary rules for the names `#x` and `!x`, and
` #x` (leading space) is not a comment.

A **globstar** is a pattern segment of an anchored rule that consists only of `*` characters, at least two of them
(`**`, `***`). Anywhere else, a run of `*` is just a `*`. This includes `a**b` and the whole pattern `**` of an
unanchored rule.

## 3. Matching a name against a pattern segment

A pattern segment matches a name (one path segment) if the whole segment matches the whole name. Read the segment left
to right:

| In the segment | Matches |
|---|---|
| `\` then a character c | c itself, whatever it is |
| `?` | any one character |
| `*` | any run of characters, possibly empty |
| `[` ... `]` | one character from a set (below) |
| any other character | itself |

`*` and `?` match `.` like any other character, including at the start of a name.

**Bracket expressions.** After `[`, a `!` or a `^` makes the set **negated**. Members are then read left to right up
to the closing `]`. A `]` in the first member position (right after `[`, `[!` or `[^`) is a member, not the closer.
A member is a character, or `\` followed by a character (meaning that character). If a member is followed by `-` and
then by a character other than `]`, the three form a **range** from lo to hi (hi may also be escaped), and reading
continues after hi. A range contains every character whose code point is between those of lo and hi inclusive. A
range with lo > hi contains nothing. Any other `-` is a plain member. There are no named classes such as
`[:alpha:]`. The expression matches one character that is in the set, or, when negated, one character that is not.

A rule **matches nothing** (it can never match, and so never decides anything) if any of its pattern segments:
- is empty (as in `a//b`);
- ends with an unpaired `\`: reading left to right, a `\` that starts an escape is the segment's last character
  (`a\\` is fine: it is `a` and an escaped `\`); or
- has a `[` whose bracket expression is not closed before the end of the segment. Such a `[` is never a literal
  character. (An escaped `\[`, or a `[` inside a bracket expression, starts nothing.)

## 4. When a rule matches a path

The ignore file of directory B **applies to** a path P (a file or a directory) if B is `""` or P starts with B + `/`.
Let rel be P without that prefix, as a list of segments.

- A directory-only rule never matches a file.
- An unanchored rule matches if its pattern segment matches the **last segment** of P. This works at any depth below
  B.
- An anchored rule without a globstar matches if rel has exactly as many segments as the rule, and each pattern
  segment matches the segment of rel in the same position.
- An anchored rule with globstars matches if all of rel can be split, in order, so that each ordinary pattern segment
  matches exactly one segment and each globstar takes **zero or more** whole segments, with one exception: a globstar
  that is the rule's **last** pattern segment takes **one or more**.

Relative to B: `doc/*.txt` matches `doc/a.txt` but not `doc/x/a.txt` or `x/doc/a.txt`; `**/doc` matches `doc` and
`x/y/doc`; `a/**/b` matches `a/b` and `a/x/y/b`; `doc/**` matches everything inside `doc`, but not `doc` itself.

## 5. Deciding

**decision(P).** Look at the ignore files that apply to P, from the deepest B up to the root. In the first one that
has at least one matching rule, the **last** matching rule in it decides: P is ignored if that rule is not negated,
and not ignored if it is negated. If no rule in any of them matches, P is not ignored. So a deeper ignore file with a
matching rule always wins, whatever the shallower ones say.

**Directories**, parents first: a directory is **excluded** if its parent is excluded or decision(directory) says
ignored.

**Files**: a file is **ignored** if its parent is excluded or decision(file) says ignored.

**Once a directory is excluded, nothing under it can be re-included.** A negated rule that matches a path below an
excluded directory has no effect, however exact it is and in whichever ignore file it appears. An ignore file inside
an excluded directory changes nothing. An ignore file whose key is neither `""` nor a directory applies to nothing.

## Output

```python
{"ignored": [...],       # the ignored files
 "ignored_dirs": [...],  # excluded directories whose parent is not excluded (the root never is)
 "invalid": [...]}       # every invalid path, from steps 1 and 3
```

Each list is sorted by Python's `sorted` (code point order) and contains no duplicates.

## Size

Up to 120 000 paths with up to 8 000 000 characters in total. A path may have up to 3 000 segments. Up to 5 000
ignore files with up to 20 000 lines in total. A line or a name is at most 300 characters. The whole call must finish
within a few seconds. Expect directory chains thousands of levels deep, trees of tens of thousands of files under
more than a thousand ignore files, and rules like `*a*a*a*a*a*a*a*b` or `**/a/**/a/**/a/**/b` tested against long
names and deep paths.

## Examples

Example 1 (comments, negation, last matching line wins, a directory-only rule at any depth, an invalid path):

```python
ignored(["a.log", "src/b.log", "src/keep.log", "build/out.txt", "src/build", "docs/build/x.md", "a//b", "README"],
        {"": ["# logs", "*.log", "!keep.log", "build/", ""]})
# src/build is a file, so build/ does not match it.
# -> {"ignored": ["a.log", "build/out.txt", "docs/build/x.md", "src/b.log"],
#     "ignored_dirs": ["build", "docs/build"], "invalid": ["a//b"]}
```

Example 2 (anchoring is relative to the ignore file's directory; a deeper ignore file wins):

```python
ignored(["out/a.txt", "src/out/b.txt", "src/gen/c.txt", "src/lib/gen/d.txt", "src/e.txt"],
        {"": ["/out", "*.txt"], "src": ["!*.txt", "/gen/"]})
# -> {"ignored": ["out/a.txt", "src/gen/c.txt"], "ignored_dirs": ["out", "src/gen"], "invalid": []}
```

Example 3 (an excluded directory cannot be re-included):

```python
ignored(["logs/a.log", "logs/keep/b.log", "notes/c.txt"],
        {"": ["logs/", "!logs/keep/", "!logs/keep/b.log"], "logs/keep": ["!*"]})
# -> {"ignored": ["logs/a.log", "logs/keep/b.log"], "ignored_dirs": ["logs"], "invalid": []}
```

Example 4 (escapes, escaped and unescaped trailing spaces, `?`, a range, a path that is also a directory):

```python
ignored(["#notes", "a ", "a", "x1", "x/y", "x", "data/v2", "data/vX"],
        {"": ["\\#notes", "a\\ ", "data/v[0-9]", "?1   "]})
# The Python literal "a\\ " is the three characters a, backslash, space; "?1   " ends in three plain spaces.
# -> {"ignored": ["#notes", "a ", "data/v2", "x1"], "ignored_dirs": [], "invalid": ["x"]}
```
