"""Reference for Problem 7 (dependency resolver with semantic-version ranges). Stdlib only."""
import functools

ASCII_DIGITS = "0123456789"
IDENT_CHARS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-")
WILDCARDS = ("x", "X", "*")
OPERATORS = (">=", "<=", ">", "<", "=", "~", "^")  # two-character operators first


class Invalid(Exception):
    pass


def is_number(s):
    """Non-negative integer in ASCII digits with no leading zeros."""
    return s != "" and all(ch in ASCII_DIGITS for ch in s) and (s == "0" or s[0] != "0")


def is_numeric_ident(s):
    return s != "" and all(ch in ASCII_DIGITS for ch in s)


def parse_idents(text, prerelease):
    if text == "":
        return None
    idents = text.split(".")
    for ident in idents:
        if ident == "" or any(ch not in IDENT_CHARS for ch in ident):
            return None
        if prerelease and is_numeric_ident(ident) and not is_number(ident):
            return None
    return idents


def parse_version(text):
    """Return (major, minor, patch, prerelease_ids_tuple) or None if invalid. BUILD is validated and dropped."""
    core, build = text, None
    if "+" in core:
        core, build = core.split("+", 1)
        if parse_idents(build, False) is None:
            return None
    pre = None
    if "-" in core:
        core, pre_text = core.split("-", 1)
        pre = parse_idents(pre_text, True)
        if pre is None:
            return None
    parts = core.split(".")
    if len(parts) != 3 or not all(is_number(p) for p in parts):
        return None
    return (int(parts[0]), int(parts[1]), int(parts[2]), tuple(pre) if pre else ())


def compare_ident(a, b):
    na, nb = is_numeric_ident(a), is_numeric_ident(b)
    if na and nb:
        x, y = int(a), int(b)
    elif na:
        return -1
    elif nb:
        return 1
    else:
        x, y = a, b
    return (x > y) - (x < y)


def compare(v, w):
    for i in range(3):
        if v[i] != w[i]:
            return -1 if v[i] < w[i] else 1
    pv, pw = v[3], w[3]
    if not pv and not pw:
        return 0
    if not pv:
        return 1
    if not pw:
        return -1
    for a, b in zip(pv, pw):
        c = compare_ident(a, b)
        if c:
            return c
    return (len(pv) > len(pw)) - (len(pv) < len(pw))


# ── Ranges ───────────────────────────────────────────────────────────────────
def parse_partial(text):
    """Return (components list of ints, prerelease tuple). Raises Invalid."""
    pre = ()
    if "+" in text:
        raise Invalid("build metadata in a range")
    if "-" in text:
        text, pre_text = text.split("-", 1)
        ids = parse_idents(pre_text, True)
        if ids is None:
            raise Invalid("bad prerelease")
        pre = tuple(ids)
    if text in WILDCARDS:
        comps = []
        raw = [text]
    else:
        raw = text.split(".")
        if len(raw) > 3:
            raise Invalid("too many components")
        comps = []
        seen_wild = False
        for r in raw:
            if r in WILDCARDS:
                seen_wild = True
            elif seen_wild:
                raise Invalid("component after wildcard")
            elif is_number(r):
                comps.append(int(r))
            else:
                raise Invalid("bad component")
    if pre and len(comps) != 3:
        raise Invalid("prerelease on a partial version")
    return comps, pre


def low(comps, pre):
    c = comps + [0] * (3 - len(comps))
    return (c[0], c[1], c[2], pre)


def bump(comps, index):
    c = comps[:index] + [comps[index] + 1] + [0] * (2 - index)
    return (c[0], c[1], c[2], ())


def nxt(comps):
    return bump(comps, len(comps) - 1)


def caret_upper(comps):
    for i, value in enumerate(comps):
        if value != 0:
            return bump(comps, i)
    return bump(comps, len(comps) - 1)


NOTHING = "nothing"


def item_comparators(token):
    op = ""
    for candidate in OPERATORS:
        if token.startswith(candidate):
            op = candidate
            break
    comps, pre = parse_partial(token[len(op):])
    k = len(comps)
    if k == 0:
        return NOTHING if op in (">", "<") else []
    if k == 3:
        v = low(comps, pre)
        if op in ("", "="):
            return [("=", v)]
        if op in (">=", ">", "<", "<="):
            return [(op, v)]
        if op == "~":
            return [(">=", v), ("<", bump(comps, 1))]
        return [(">=", v), ("<", caret_upper(comps))]
    if op in ("", "=", "~"):
        return [(">=", low(comps, pre)), ("<", nxt(comps))]
    if op == ">=":
        return [(">=", low(comps, pre))]
    if op == ">":
        return [(">=", nxt(comps))]
    if op == "<":
        return [("<", low(comps, pre))]
    if op == "<=":
        return [("<", nxt(comps))]
    return [(">=", low(comps, pre)), ("<", caret_upper(comps))]


def set_comparators(text):
    tokens = [t for t in text.split(" ") if t != ""]
    if len(tokens) == 3 and tokens[1] == "-":
        out = []
        a_comps, a_pre = parse_partial(tokens[0])
        b_comps, b_pre = parse_partial(tokens[2])
        if a_comps:
            out.append((">=", low(a_comps, a_pre)))
        if len(b_comps) == 3:
            out.append(("<=", low(b_comps, b_pre)))
        elif b_comps:
            out.append(("<", nxt(b_comps)))
        return out
    out = []
    unsatisfiable = False
    for token in tokens:
        cs = item_comparators(token)
        if cs == NOTHING:
            unsatisfiable = True
        else:
            out.extend(cs)
    return NOTHING if unsatisfiable else out


def parse_range(text):
    """Return a list of comparator sets (each a list, or NOTHING), or None if the range is invalid."""
    try:
        return [set_comparators(part) for part in text.split("||")]
    except Invalid:
        return None


def test_comparator(v, op, w):
    c = compare(v, w)
    return {"=": c == 0, ">=": c >= 0, ">": c > 0, "<": c < 0, "<=": c <= 0}[op]


def satisfies(v, parsed):
    if parsed is None:
        return False
    for cs in parsed:
        if cs == NOTHING:
            continue
        if not all(test_comparator(v, op, w) for op, w in cs):
            continue
        if v[3] and not any(w[3] and w[:3] == v[:3] for _, w in cs):
            continue
        return True
    return False


# ── Resolution ───────────────────────────────────────────────────────────────
def resolve(registry, root):
    range_cache = {}

    def rng(text):
        if text not in range_cache:
            range_cache[text] = parse_range(text)
        return range_cache[text]

    versions = {}
    for name, table in registry.items():
        valid = []
        for vs, deps in table.items():
            pv = parse_version(vs)
            if pv is not None:
                valid.append((pv, vs, deps))
        # highest precedence first; equal precedence: greater whole string first
        def order(a, b):
            c = compare(a[0], b[0])
            if c:
                return -c
            return (a[1] < b[1]) - (a[1] > b[1])
        versions[name] = sorted(valid, key=functools.cmp_to_key(order))

    selected = {}  # name -> (parsed, version string, deps)

    def requirements(name):
        reqs = []
        if name in root:
            reqs.append(root[name])
        for sel_name in sorted(selected):
            deps = selected[sel_name][2]
            if name in deps:
                reqs.append(deps[name])
        return reqs

    def unresolved():
        names = set(root)
        for _, _, deps in selected.values():
            names.update(deps)
        pending = sorted(n for n in names if n not in selected)
        return pending[0] if pending else None

    def consistent():
        for name, (pv, _, _) in selected.items():
            for r in requirements(name):
                if not satisfies(pv, rng(r)):
                    return False
        return True

    def search():
        p = unresolved()
        if p is None:
            return True
        reqs = requirements(p)
        candidates = [c for c in versions.get(p, []) if all(satisfies(c[0], rng(r)) for r in reqs)]
        for pv, vs, deps in candidates:
            selected[p] = (pv, vs, deps)
            if consistent() and search():
                return True
            del selected[p]
        return False

    if search():
        return {"ok": True, "packages": {name: sel[1] for name, sel in selected.items()}}
    return {"ok": False, "packages": {}}
