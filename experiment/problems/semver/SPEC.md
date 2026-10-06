# Problem 7: Dependency resolver with semantic-version ranges

Implement `def resolve(registry, root)` in Python, using only the standard library.

- `registry` is a dict: package name → dict: version string → dict of dependencies (package name → range string).
- `root` is a dict: package name → range string (the project's own requirements).

All names, versions and ranges are `str`.

## Versions

A version string is **valid** if it is `MAJOR.MINOR.PATCH`, optionally followed by `-PRERELEASE`, optionally followed
by `+BUILD` (in that order), where:

- MAJOR, MINOR and PATCH are non-negative integers written in ASCII digits with **no leading zeros** (`0` is fine,
  `01` is not);
- PRERELEASE and BUILD are non-empty, dot-separated lists of non-empty identifiers made of ASCII letters, digits and
  `-`. A prerelease identifier made only of digits must not have a leading zero; build identifiers may.

Registry versions that are not valid are ignored entirely: they can never be selected.

**Precedence** (ordering) of valid versions:

1. Compare MAJOR, MINOR, PATCH numerically, in that order.
2. If those are equal, a version **without** a prerelease is greater than one **with** a prerelease.
3. Two prereleases are compared identifier by identifier from the left: two numeric identifiers compare numerically;
   two other identifiers compare by ASCII code point; a numeric identifier is lower than a non-numeric one. If all
   compared identifiers are equal, the version with more identifiers is greater.
4. BUILD is ignored for precedence.

## Ranges

In ranges, **whitespace** means the ASCII space character (U+0020) only; any other character (a tab, for example)
is part of a token. A range is one or more **comparator sets** separated by `||`. A version satisfies the range if
it satisfies **any** set. Each set is split into **tokens** at runs of spaces (leading and trailing spaces are
ignored); a set with no tokens means `*`.

A set is either a **hyphen range**, exactly three tokens of which the middle one is `-` (`A - B`, where A and B are
partial versions with no operator), or otherwise one or more **items**, one per token. Each item or hyphen range
becomes zero or more comparators of the form `OP VERSION`, with OP one of `>=`, `>`, `<`, `<=`, `=`; the version
must satisfy every comparator of the set. A set with no comparators is satisfied by every version without a
prerelease (see **Prereleases** below).

**Partial versions.** Inside a range a version may be partial: `M`, `M.m` or `M.m.p`, where any trailing components
may instead be a wildcard `x`, `X` or `*`, and a wildcard may only be followed by wildcards (`1.x.3` is invalid).
`*`, `x` and `X` alone are a partial version with no components. Components follow the same no-leading-zero rule.
Only a complete `M.m.p` may carry `-PRERELEASE`; no range version may carry `+BUILD`. Let **k** be the number of
present (non-wildcard) components. For k ≥ 1:

- **low** = the partial version with missing components filled with `0` (and its prerelease, if any);
- **next** = the partial version with its last present component increased by 1 and every later component `0`
  (for example `1.2` → `1.3.0` and `1` → `2.0.0`). The table never uses next for k = 3.

**Items.** An item is an optional operator immediately followed (no space) by a partial version. In the table,
"any version" means the item adds no comparator, and "no version" means the whole set is satisfied by nothing:

| Item | k = 0 | k = 1 or 2 | k = 3 |
|---|---|---|---|
| `P` or `=P` | any version | `>=low <next` | `=P` |
| `>=P` | any version | `>=low` | `>=P` |
| `>P` | no version | `>=next` | `>P` |
| `<P` | no version | `<low` | `<P` |
| `<=P` | any version | `<next` | `<=P` |
| `~P` | any version | `>=low <next` | `>=P <M.(m+1).0` |
| `^P` | any version | `>=low <U` | `>=P <U` |

For `^`, **U** is found by increasing the left-most **non-zero** present component by 1 and setting every later
component to 0; if every present component is 0, increase the **last present** one instead. Examples: `^1.2.3` →
`<2.0.0`; `^0.2.3` → `<0.3.0`; `^0.0.3` → `<0.0.4`; `^0.0` → `<0.1.0`; `^0` → `<1.0.0`.

**Hyphen ranges.** `A - B` means `>=low(A)` (no lower bound if A has k = 0; a complete A keeps its prerelease) and,
for B: `<=B` if k = 3 (keeping its prerelease), `<next(B)` if k is 1 or 2, no upper bound if k = 0.

Anything else (an unknown operator such as `==` or `~>`, a space between an operator and its version, a `v` prefix, a
stray `-` token, an operator on a hyphen-range endpoint, an invalid version) makes the **whole range invalid**: it is
satisfied by no version, even if another `||` set would have matched.

**Prereleases.** A version **with** a prerelease satisfies a comparator set only if it satisfies every comparator in
the set **and** at least one comparator in that set has a version with a prerelease and the same MAJOR.MINOR.PATCH
as the candidate. (So `>=1.2.3-beta.1` admits `1.2.3-beta.7` but not `1.2.4-alpha`, and `^1.0.0` admits no
prerelease at all.) A version without a prerelease only needs to satisfy every comparator.

## Resolution

The **requirements** on a package P are its range in `root` (if any) plus, for every selected package, the range
that the selected version's dependencies give for P (if any). A package is **unresolved** if it has at least one
requirement and is not selected. Resolve by this exact depth-first search:

1. If no package is unresolved, the current selection is the answer.
2. Otherwise let P be the unresolved package whose name is smallest in code-point order. Its **candidates** are its
   valid registry versions that satisfy **all** current requirements on P, ordered by precedence, highest first
   (versions of equal precedence: the one whose whole string is greater in code-point order first). A package
   missing from the registry has no candidates.
3. Try the candidates in order. Trying version v means: select P = v (its dependencies now add requirements), then
   check that **every** selected package, P included, still satisfies all of its requirements. If the check passes,
   continue the search from step 1; if that search succeeds, so does this one.
4. If the check fails or the deeper search fails, undo the selection of P and try its next candidate. If no candidate
   is left, this search fails, and the search that selected the previous package moves on to that package's next
   candidate.

A package may depend on itself; the check in step 3 covers that like any other requirement.

## Output

Return `{"ok": True, "packages": {name: version, ...}}` with every selected package and its version string exactly as
written in the registry, or `{"ok": False, "packages": {}}` if the search fails. An empty `root` gives
`{"ok": True, "packages": {}}`.

## Examples

Example 1 (highest satisfying version; `^0.2.1` stops before `0.3.0`):

```python
registry = {"a": {"0.2.1": {}, "0.2.9": {}, "0.3.0": {}}}
root = {"a": "^0.2.1"}
# -> {"ok": True, "packages": {"a": "0.2.9"}}
```

Example 2 (prereleases need an opt-in on the same MAJOR.MINOR.PATCH):

```python
registry = {"a": {"1.0.0": {}, "1.1.0-beta.2": {}, "1.1.0-beta.10": {}}}
resolve(registry, {"a": ">=1.0.0"})          # -> {"ok": True, "packages": {"a": "1.0.0"}}
resolve(registry, {"a": ">=1.1.0-beta.1"})   # -> {"ok": True, "packages": {"a": "1.1.0-beta.10"}}
```

Example 3 (backtracking: `app 2.0.0` needs `lib ^2` but `util 1.0.0` needs `lib <2`, so `app` falls back to 1.0.0):

```python
registry = {
    "app":  {"2.0.0": {"lib": "^2.0.0"}, "1.0.0": {"lib": "^1.0.0"}},
    "lib":  {"1.4.0": {}, "2.1.0": {}},
    "util": {"1.0.0": {"lib": "<2"}},
}
root = {"app": "*", "util": "1.x"}
# -> {"ok": True, "packages": {"app": "1.0.0", "lib": "1.4.0", "util": "1.0.0"}}
```

Example 4 (invalid ranges match nothing):

```python
registry = {"a": {"1.0.0": {}}}
resolve(registry, {"a": ">= 1.0.0"})   # -> {"ok": False, "packages": {}}
```
