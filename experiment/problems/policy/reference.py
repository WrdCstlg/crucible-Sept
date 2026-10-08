"""Reference for Problem 11 (access-policy evaluator). Stdlib only, deterministic, never mutates its inputs.

Design notes:
  * glob matching splits a pattern at its stars; the first segment is anchored at the start, the last at the end, and
    the middle ones are found leftmost-first (each segment is a fixed-length regex with no quantifiers), so a pattern
    with dozens of stars never backtracks;
  * identity sets are computed once per principal with an iterative BFS (chains are deeper than the recursion limit);
  * which identity statements a principal's patterns reach is cached per principal, and every wildcard principal
    pattern is matched once against all principal ids.
"""
import re
from collections import deque
from fractions import Fraction

STATEMENT_KEYS = frozenset(["sid", "effect", "principals", "actions", "not_actions", "resources", "not_resources",
                            "conditions", "set"])
BASES = ("StringEquals", "StringNotEquals", "StringLike", "StringNotLike", "NumericEquals", "NumericNotEquals",
         "NumericLessThan", "NumericLessThanEquals", "NumericGreaterThan", "NumericGreaterThanEquals", "Bool", "Null")
NEGATED = ("StringNotEquals", "StringNotLike", "NumericNotEquals")
NUMBER = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")
ASCII_FOLD = str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz")
STAR, ONE, LIT, PRINCIPAL, TAG = "star", "one", "lit", "principal", "tag"


def fold(s):
    """Case folding for actions: ASCII letters only."""
    return s.translate(ASCII_FOLD)


def parse_number(s):
    if NUMBER.fullmatch(s) is None:
        return None
    return Fraction(s)


def plain_tokens(pattern):
    """Tokens of a pattern without references: * and ? are wildcards, every other character is literal."""
    return tuple((STAR, "") if c == "*" else (ONE, "") if c == "?" else (LIT, c) for c in pattern)


def parse_resource(pattern):
    """Resource pattern -> list of tokens, where (PRINCIPAL, "") and (TAG, key) are still to be substituted.
    None if the pattern is invalid."""
    items, i, n = [], 0, len(pattern)
    while i < n:
        c = pattern[i]
        if c == "$" and i + 1 < n and pattern[i + 1] == "{":
            j = pattern.find("}", i + 2)
            if j < 0:
                return None
            inner = pattern[i + 2:j]
            if inner == "principal":
                items.append((PRINCIPAL, ""))
            elif inner.startswith("tag:") and len(inner) > 4:
                items.append((TAG, inner[4:]))
            elif inner in ("*", "?", "$"):
                items.append((LIT, inner))
            else:
                return None
            i = j + 1
        else:
            items.append((STAR, "") if c == "*" else (ONE, "") if c == "?" else (LIT, c))
            i += 1
    return items


class Glob:
    """Whole-string matcher for a token sequence."""
    __slots__ = ("segs",)

    def __init__(self, tokens):
        segs = [[]]
        for kind, ch in tokens:
            if kind == STAR:
                segs.append([])
            else:
                segs[-1].append(re.escape(ch) if kind == LIT else ".")
        self.segs = [(re.compile("".join(s), re.S), len(s)) for s in segs]

    def match(self, s):
        segs = self.segs
        n = len(s)
        if len(segs) == 1:
            rx, size = segs[0]
            return n == size and rx.match(s) is not None
        (first, a), (last, b) = segs[0], segs[-1]
        if a + b > n or first.match(s) is None or last.match(s, n - b) is None:
            return False
        pos, end = a, n - b
        for rx, size in segs[1:-1]:
            if size:
                m = rx.search(s, pos, end)
                if m is None:
                    return False
                pos = m.end()
        return True


def parse_operator(op):
    prefix = ""
    for p in ("ForAnyValue:", "ForAllValues:"):
        if op.startswith(p):
            prefix, op = p, op[len(p):]
            break
    if_exists = op.endswith("IfExists")
    if if_exists:
        op = op[:-len("IfExists")]
    if op not in BASES:
        return None
    if op == "Null" and (prefix or if_exists):
        return None
    return prefix, op, if_exists


def is_str_list(x):
    return type(x) is list and len(x) > 0 and all(type(v) is str for v in x)


def compile_statement(st, glob):
    """Well-formed statement -> dict of compiled parts; malformed -> None."""
    if type(st) is not dict or not set(st) <= STATEMENT_KEYS:
        return None
    sid, effect, bset = st.get("sid"), st.get("effect"), st.get("set")
    if type(sid) is not str or sid == "":
        return None
    if type(effect) is not str or effect not in ("Allow", "Deny"):
        return None
    if bset is not None and (type(bset) is not str or bset == ""):
        return None
    if bset is None:
        if not is_str_list(st.get("principals")):
            return None
    elif "principals" in st:
        return None
    if ("actions" in st) == ("not_actions" in st):
        return None
    if ("resources" in st) == ("not_resources" in st):
        return None
    not_actions, not_resources = "not_actions" in st, "not_resources" in st
    acts = st["not_actions"] if not_actions else st["actions"]
    ress = st["not_resources"] if not_resources else st["resources"]
    if not is_str_list(acts) or not is_str_list(ress):
        return None
    templates = [parse_resource(p) for p in ress]
    if any(t is None for t in templates):
        return None
    conds = []
    if "conditions" in st:
        body = st["conditions"]
        if type(body) is not dict:
            return None
        for op, keys in body.items():
            parsed = parse_operator(op) if type(op) is str else None
            if parsed is None or type(keys) is not dict:
                return None
            prefix, base, if_exists = parsed
            for key, val in keys.items():
                values = [val] if type(val) is str else val
                if type(key) is not str or not is_str_list(values):
                    return None
                if base.startswith("Numeric"):
                    values = [parse_number(v) for v in values]
                    if any(v is None for v in values):
                        return None
                elif base in ("Bool", "Null"):
                    if any(v not in ("true", "false") for v in values):
                        return None
                elif base in ("StringLike", "StringNotLike"):
                    values = [glob(plain_tokens(v)) for v in values]
                conds.append((prefix, base, if_exists, key, values))
    fixed = {}
    for i, t in enumerate(templates):
        if all(kind not in (PRINCIPAL, TAG) for kind, _ in t):
            fixed[i] = glob(tuple(t))
    return {"sid": sid, "deny": effect == "Deny", "set": bset,
            "principals": st.get("principals"),
            "not_actions": not_actions, "actions": [glob(plain_tokens(fold(p))) for p in acts],
            "not_resources": not_resources, "templates": templates, "fixed": fixed,
            "conditions": conds}


def passes(base, values, r):
    """Does one request string r pass base against the policy values?"""
    if base == "StringEquals":
        return r in values
    if base == "StringNotEquals":
        return r not in values
    if base == "StringLike":
        return any(g.match(r) for g in values)
    if base == "StringNotLike":
        return not any(g.match(r) for g in values)
    if base == "Bool":
        return r in values
    x = parse_number(r)
    if x is None:
        return False
    if base == "NumericEquals":
        return any(x == v for v in values)
    if base == "NumericNotEquals":
        return all(x != v for v in values)
    if base == "NumericLessThan":
        return any(x < v for v in values)
    if base == "NumericLessThanEquals":
        return any(x <= v for v in values)
    if base == "NumericGreaterThan":
        return any(x > v for v in values)
    return any(x >= v for v in values)


def condition_holds(cond, ctx):
    prefix, base, if_exists, key, values = cond
    if base == "Null":
        present = key in ctx
        return any((v == "true") != present for v in values)
    if key not in ctx:
        if if_exists:
            return True
        if prefix == "ForAllValues:":
            return True
        if prefix == "ForAnyValue:":
            return False
        return base in NEGATED
    raw = ctx[key]
    vals = [raw] if type(raw) is str else raw
    if prefix == "ForAllValues:":
        return all(passes(base, values, r) for r in vals)
    return any(passes(base, values, r) for r in vals)


def result(decision, reason, sids):
    return {"decision": decision, "reason": reason, "statements": sorted(set(sids))}


def authorize(principals, policies, requests):
    globs = {}

    def glob(tokens):
        g = globs.get(tokens)
        if g is None:
            g = globs[tokens] = Glob(tokens)
        return g

    identity_stmts, boundary_stmts = [], {}
    for raw in policies:
        st = compile_statement(raw, glob)
        if st is None:
            continue
        st["n"] = len(identity_stmts) + sum(len(v) for v in boundary_stmts.values())
        if st["set"] is None:
            identity_stmts.append(st)
        else:
            boundary_stmts.setdefault(st["set"], []).append(st)

    dist_cache = {}

    def identity(pid):
        """Member id -> distance, by breadth-first search over valid edges."""
        dist = dist_cache.get(pid)
        if dist is None:
            dist = {pid: 0}
            queue = deque([pid])
            while queue:
                x = queue.popleft()
                for y in principals[x]["inherits"]:
                    if y in dist or y not in principals:
                        continue
                    if principals[y]["kind"] != "role":
                        continue
                    dist[y] = dist[x] + 1
                    queue.append(y)
            dist_cache[pid] = dist
        return dist

    tag_cache = {}

    def tag(pid, key):
        if (pid, key) not in tag_cache:
            best = None
            for member, d in identity(pid).items():
                if key in principals[member]["tags"]:
                    cand = (d, member)
                    if best is None or cand < best:
                        best = cand
            tag_cache[(pid, key)] = None if best is None else principals[best[1]]["tags"][key]
        return tag_cache[(pid, key)]

    wildcard_hits = {}

    def pattern_reaches(pattern, members):
        if "*" not in pattern and "?" not in pattern:
            return pattern in members
        ids = wildcard_hits.get(pattern)
        if ids is None:
            g = glob(plain_tokens(pattern))
            ids = wildcard_hits[pattern] = {p for p in principals if g.match(p)}
        return not ids.isdisjoint(members)

    info_cache = {}

    def principal_info(pid):
        info = info_cache.get(pid)
        if info is None:
            members = identity(pid)
            stmts = [st for st in identity_stmts if any(pattern_reaches(p, members) for p in st["principals"])]
            bsets = sorted({principals[m]["boundary"] for m in members if principals[m]["boundary"] is not None})
            info = info_cache[pid] = (stmts, bsets)
        return info

    res_cache = {}

    def resource_globs(st, pid):
        """One Glob per resource pattern, or None where a referenced tag is missing."""
        key = (st["n"], pid)
        out = res_cache.get(key)
        if out is None:
            out = []
            for i, t in enumerate(st["templates"]):
                if i in st["fixed"]:
                    out.append(st["fixed"][i])
                    continue
                toks = []
                for kind, val in t:
                    if kind == PRINCIPAL:
                        toks.extend((LIT, ch) for ch in pid)
                    elif kind == TAG:
                        value = tag(pid, val)
                        if value is None:
                            toks = None
                            break
                        toks.extend((LIT, ch) for ch in value)
                    else:
                        toks.append((kind, val))
                out.append(None if toks is None else glob(tuple(toks)))
            res_cache[key] = out
        return out

    def matches(st, pid, action, resource, ctx):
        hit = any(g.match(action) for g in st["actions"])
        if hit == st["not_actions"]:
            return False
        hit = any(g is not None and g.match(resource) for g in resource_globs(st, pid))
        if hit == st["not_resources"]:
            return False
        return all(condition_holds(c, ctx) for c in st["conditions"])

    out = []
    for req in requests:
        pid = req["principal"]
        if pid not in principals:
            out.append(result("DENY", "unknown_principal", []))
            continue
        stmts, bsets = principal_info(pid)
        action, resource, ctx = fold(req["action"]), req["resource"], req["context"]
        allow, deny = [], []
        for st in stmts:
            if matches(st, pid, action, resource, ctx):
                (deny if st["deny"] else allow).append(st["sid"])
        if deny:
            out.append(result("DENY", "explicit_deny", deny))
            continue
        b_allow, b_deny, outside = [], [], False
        for b in bsets:
            allowed_here = denied_here = False
            for st in boundary_stmts.get(b, []):
                if matches(st, pid, action, resource, ctx):
                    if st["deny"]:
                        b_deny.append(st["sid"])
                        denied_here = True
                    else:
                        b_allow.append(st["sid"])
                        allowed_here = True
            if denied_here or not allowed_here:
                outside = True
        if outside:
            out.append(result("DENY", "outside_boundary", b_deny))
        elif allow:
            out.append(result("ALLOW", "allowed", allow + b_allow))
        else:
            out.append(result("DENY", "implicit_deny", []))
    return out
