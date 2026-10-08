"""Second oracle for experiment/problems/semver/SPEC.md, written from the spec alone (reference.py was not read).

Built differently on purpose: versions and partial versions are read by a hand scanner (no regular expressions),
range items are expanded through the spec's item table literally, and the depth-first search runs on an explicit
stack and recomputes every requirement from scratch after each selection. Slow by design. Used only to check
reference.py by differential testing on non-stress cases. Never shown to any model under study.
"""
from functools import cmp_to_key

DIGITS = set("0123456789")
ID_CHARS = DIGITS | set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-")
WILDCARDS = {"x", "X", "*"}
OPERATORS = (">=", "<=", ">", "<", "=", "~", "^")      # two-character operators first


def all_digits(s):
    return s != "" and all(c in DIGITS for c in s)


def plain_number(s):                                    # ASCII digits, no leading zero ("0" is fine)
    return all_digits(s) and (s == "0" or s[0] != "0")


def identifiers(text, prerelease):
    """Dot-separated non-empty identifiers, or None. Numeric prerelease identifiers may not have a leading zero."""
    parts = text.split(".")
    for p in parts:
        if p == "" or any(c not in ID_CHARS for c in p):
            return None
        if prerelease and all_digits(p) and not plain_number(p):
            return None
    return tuple(parts)


_versions = {}


def version(s):
    """A registry version string -> (MAJOR, MINOR, PATCH, prerelease identifiers), or None if it is not valid."""
    if s not in _versions:
        _versions[s] = _version(s)
    return _versions[s]


def _version(s):
    rest, plus, build = s.partition("+")
    if plus and identifiers(build, prerelease=False) is None:
        return None
    core, dash, pre = rest.partition("-")
    nums = core.split(".")
    if len(nums) != 3 or not all(plain_number(n) for n in nums):
        return None
    ids = ()
    if dash:
        ids = identifiers(pre, prerelease=True)
        if ids is None:
            return None
    return int(nums[0]), int(nums[1]), int(nums[2]), ids


def compare_identifiers(a, b):
    for x, y in zip(a, b):
        if all_digits(x) and all_digits(y):
            c = (int(x) > int(y)) - (int(x) < int(y))
        elif all_digits(x):
            c = -1
        elif all_digits(y):
            c = 1
        else:
            c = (x > y) - (x < y)
        if c:
            return c
    return (len(a) > len(b)) - (len(a) < len(b))


def precedence(v, w):
    """-1, 0 or 1. BUILD was dropped when parsing, so it is ignored here."""
    for i in range(3):
        if v[i] != w[i]:
            return -1 if v[i] < w[i] else 1
    if not v[3] and not w[3]:
        return 0
    if not v[3]:
        return 1
    if not w[3]:
        return -1
    return compare_identifiers(v[3], w[3])


def partial(s):
    """A range version -> (present components, prerelease identifiers), or None if it is not a valid partial."""
    if s in WILDCARDS:
        return [], ()
    if "+" in s:
        return None
    core, dash, pre = s.partition("-")
    parts = core.split(".")
    if not 1 <= len(parts) <= 3:
        return None
    present, wild = [], False
    for p in parts:
        if p in WILDCARDS:
            wild = True
        elif plain_number(p) and not wild:
            present.append(int(p))
        else:
            return None
    ids = ()
    if dash:
        if len(present) != 3 or wild:
            return None
        ids = identifiers(pre, prerelease=True)
        if ids is None:
            return None
    return present, ids


def low(present, ids):
    return tuple(present + [0] * (3 - len(present))) + (ids,)


def next_up(present):
    return tuple(present[:-1] + [present[-1] + 1] + [0] * (3 - len(present))) + ((),)


def caret_upper(present):
    nonzero = [i for i, c in enumerate(present) if c != 0]
    i = nonzero[0] if nonzero else len(present) - 1
    return tuple(present[:i] + [present[i] + 1] + [0] * (2 - i)) + ((),)


NOTHING = "no version"


def item(token):
    """One range item -> list of (OP, version) comparators, NOTHING, or None if the item is invalid."""
    op = next((o for o in OPERATORS if token.startswith(o)), "")
    p = partial(token[len(op):])
    if p is None:
        return None
    present, ids = p
    k = len(present)
    if k == 0:
        return NOTHING if op in (">", "<") else []
    if k < 3:
        lo, nx = low(present, ids), next_up(present)
        table = {"": [(">=", lo), ("<", nx)], "=": [(">=", lo), ("<", nx)], ">=": [(">=", lo)], ">": [(">=", nx)],
                 "<": [("<", lo)], "<=": [("<", nx)], "~": [(">=", lo), ("<", nx)],
                 "^": [(">=", lo), ("<", caret_upper(present))]}
    else:
        v = tuple(present) + (ids,)
        table = {"": [("=", v)], "=": [("=", v)], ">=": [(">=", v)], ">": [(">", v)], "<": [("<", v)],
                 "<=": [("<=", v)], "~": [(">=", v), ("<", (present[0], present[1] + 1, 0, ()))],
                 "^": [(">=", v), ("<", caret_upper(present))]}
    return table[op]


_ranges = {}


def comparator_sets(r):
    """A range string -> list of comparator sets (NOTHING for a set no version satisfies), or None if invalid."""
    if r not in _ranges:
        _ranges[r] = _comparator_sets(r)
    return _ranges[r]


def _comparator_sets(r):
    sets = []
    for text in r.split("||"):
        tokens = [t for t in text.split(" ") if t]
        if len(tokens) == 3 and tokens[1] == "-":
            a, b = partial(tokens[0]), partial(tokens[2])
            if a is None or b is None:
                return None
            comps = []
            if a[0]:
                comps.append((">=", low(*a)))
            if len(b[0]) == 3:
                comps.append(("<=", tuple(b[0]) + (b[1],)))
            elif b[0]:
                comps.append(("<", next_up(b[0])))
            sets.append(comps)
            continue
        comps, empty = [], False
        for t in tokens:
            got = item(t)
            if got is None:
                return None
            if got == NOTHING:
                empty = True
            else:
                comps.extend(got)
        sets.append(NOTHING if empty else comps)
    return sets


def holds(op, v, c):
    x = precedence(v, c)
    return {"=": x == 0, ">=": x >= 0, ">": x > 0, "<": x < 0, "<=": x <= 0}[op]


def satisfies(r, v):
    sets = comparator_sets(r)
    if sets is None:
        return False
    for comps in sets:
        if comps == NOTHING or not all(holds(op, v, c) for op, c in comps):
            continue
        if not v[3] or any(c[3] and c[:3] == v[:3] for _, c in comps):
            return True
    return False


def resolve(registry, root):
    def requirements(selection, name):
        reqs = [root[name]] if name in root else []
        for q, ver in selection.items():
            deps = registry[q][ver]
            if name in deps:
                reqs.append(deps[name])
        return reqs

    def candidates(selection, name):
        reqs = requirements(selection, name)
        valid = [s for s in registry.get(name, {}) if version(s) is not None]
        ok = [s for s in valid if all(satisfies(r, version(s)) for r in reqs)]
        return sorted(ok, key=cmp_to_key(lambda a, b: precedence(version(b), version(a)) or (a < b) - (a > b)))

    def next_package(selection):
        names = set(root)
        for q, ver in selection.items():
            names.update(registry[q][ver])
        unresolved = sorted(n for n in names if n not in selection)
        return unresolved[0] if unresolved else None

    def consistent(selection):
        return all(satisfies(r, version(ver)) for q, ver in selection.items() for r in requirements(selection, q))

    selection = {}
    p = next_package(selection)
    if p is None:
        return {"ok": True, "packages": {}}
    stack = [[p, candidates(selection, p), 0]]     # package, its candidates, index of the next one to try
    while stack:
        frame = stack[-1]
        p, cands, i = frame
        selection.pop(p, None)
        if i == len(cands):
            stack.pop()
            continue
        frame[2] = i + 1
        selection[p] = cands[i]
        if not consistent(selection):
            continue
        q = next_package(selection)
        if q is None:
            return {"ok": True, "packages": dict(selection)}
        stack.append([q, candidates(selection, q), 0])
    return {"ok": False, "packages": {}}
