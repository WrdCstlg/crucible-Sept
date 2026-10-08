"""Reference for Problem 16 (data-schema validator). Stdlib only.

Step 1 walks the schema with an explicit stack, checks keyword shapes, resolves $ref by exact pointer-string match and
finds cyclic $refs with an iterative Tarjan SCC (a $ref L -> T is cyclic iff L and T share a component). Step 2
validates with an explicit stack of generators, so instance depth is limited only by memory, not by recursion.
"""
import re
from fractions import Fraction

TYPE_NAMES = frozenset(["null", "boolean", "object", "array", "number", "integer", "string"])
MAP_KW = ("properties", "patternProperties", "$defs")
LIST_KW = ("prefixItems", "allOf", "anyOf", "oneOf")
ONE_KW = ("additionalProperties", "items", "not", "if", "then", "else")
COUNT_KW = ("minItems", "maxItems", "minLength", "maxLength")
BOUND_KW = ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum")
KNOWN = frozenset(MAP_KW + LIST_KW + ONE_KW + COUNT_KW + BOUND_KW +
                  ("type", "enum", "const", "required", "multipleOf", "uniqueItems", "pattern", "$ref"))
IN_PLACE = frozenset(["allOf", "anyOf", "oneOf", "not", "if", "then", "else"])


def token(key):
    return key.replace("~", "~0").replace("/", "~1")


def is_schema(v):
    return type(v) is dict or type(v) is bool


def is_number(v):
    return type(v) is int or type(v) is float


def compiled(pattern, cache):
    """The compiled pattern, or None if it is not a str or does not compile."""
    if type(pattern) is not str:
        return None
    if pattern not in cache:
        try:
            cache[pattern] = re.compile(pattern)
        except Exception:  # noqa: BLE001  (re.error, OverflowError, RecursionError, ...)
            cache[pattern] = None
    return cache[pattern]


def well_formed(kw, v, cache):
    if kw == "type":
        if type(v) is str:
            return v in TYPE_NAMES
        return (type(v) is list and len(v) > 0 and all(type(t) is str and t in TYPE_NAMES for t in v)
                and len(set(v)) == len(v))
    if kw == "enum":
        return type(v) is list
    if kw == "const":
        return True
    if kw in ("properties", "$defs"):
        return type(v) is dict and all(is_schema(s) for s in v.values())
    if kw == "patternProperties":
        return (type(v) is dict and all(is_schema(s) for s in v.values())
                and all(compiled(p, cache) is not None for p in v))
    if kw in ONE_KW:
        return is_schema(v)
    if kw in LIST_KW:
        return type(v) is list and len(v) > 0 and all(is_schema(s) for s in v)
    if kw == "required":
        return type(v) is list and all(type(s) is str for s in v)
    if kw in COUNT_KW:
        return type(v) is int and v >= 0
    if kw in BOUND_KW:
        return is_number(v)
    if kw == "multipleOf":
        return is_number(v) and v > 0
    if kw == "uniqueItems":
        return type(v) is bool
    if kw == "pattern":
        return compiled(v, cache) is not None
    return type(v) is str          # $ref: resolution is checked once every location is known


def components(nodes, links):
    """Iterative Tarjan: node -> representative of its strongly connected component."""
    index, low, comp = {}, {}, {}
    stack, on = [], set()
    counter = 0
    for start in nodes:
        if start in index:
            continue
        index[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on.add(start)
        work = [(start, iter(links.get(start, ())))]
        while work:
            v, it = work[-1]
            descended = False
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on.add(w)
                    work.append((w, iter(links.get(w, ()))))
                    descended = True
                    break
                if w in on and index[w] < low[v]:
                    low[v] = index[w]
            if descended:
                continue
            work.pop()
            if work:
                u = work[-1][0]
                if low[v] < low[u]:
                    low[u] = low[v]
            if low[v] == index[v]:
                while True:
                    w = stack.pop()
                    on.discard(w)
                    comp[w] = v
                    if w == v:
                        break
    return comp


def check_schema(root, cache):
    locs, links, refs, problems = {}, {}, [], []
    stack = [("", root)]
    while stack:
        loc, s = stack.pop()
        locs[loc] = s
        if type(s) is not dict:
            continue
        out = links[loc] = []
        for kw, v in s.items():
            if kw not in KNOWN:
                continue
            at = loc + "/" + kw
            if not well_formed(kw, v, cache):
                problems.append((at, kw))
                continue
            if kw in MAP_KW:
                children = [(at + "/" + token(k), sub) for k, sub in v.items()]
            elif kw in LIST_KW:
                children = [(at + "/" + str(i), sub) for i, sub in enumerate(v)]
            elif kw in ONE_KW:
                children = [(at, v)]
            else:
                children = []
                if kw == "$ref":
                    refs.append((loc, v))
            if kw in IN_PLACE:
                out.extend(c for c, _ in children)
            stack.extend(children)
    targets = {}
    for loc, ref in refs:
        if ref[:1] == "#" and ref[1:] in locs:
            targets[loc] = ref[1:]
            links[loc].append(ref[1:])
        else:
            problems.append((loc + "/$ref", "$ref"))
    comp = components(locs, links)
    for loc, target in targets.items():
        if comp[loc] == comp[target]:
            problems.append((loc + "/$ref", "$ref"))
    return locs, targets, problems


def type_matches(x, name):
    t = type(x)
    if name == "null":
        return x is None
    if name == "boolean":
        return t is bool
    if name == "object":
        return t is dict
    if name == "array":
        return t is list
    if name == "string":
        return t is str
    if name == "number":
        return t is int or t is float
    return t is int or (t is float and x.is_integer())          # integer


def jkey(v):
    """Hashable key with JSON equality: 1 == 1.0, True != 1, objects by key set, arrays by order."""
    t = type(v)
    if t is bool:
        return (1, v)
    if t is int or t is float:
        return (2, v)
    if t is str:
        return (3, v)
    if v is None:
        return (0,)
    if t is list:
        return (4, tuple(jkey(e) for e in v))
    return (5, frozenset((k, jkey(e)) for k, e in v.items()))


def exact(v):
    return Fraction(v) if type(v) is int else Fraction(repr(v))


def render(path):
    parts = []
    while path is not None:
        path, tok = path
        parts.append(tok)
    return "".join("/" + p for p in reversed(parts))


class Validator:
    def __init__(self, locs, targets, cache):
        self.locs, self.targets, self.cache = locs, targets, cache
        self.keys = {}

    def key_set(self, loc, values):
        ks = self.keys.get(loc)
        if ks is None:
            ks = self.keys[loc] = {jkey(e) for e in values}
        return ks

    def run(self, loc, x, path, sink):
        # In-place links pass the same path object down, so an in-place cycle would revisit an active
        # (location, path object) pair. Step 1 excludes such cycles; the guard turns a broken check into an error
        # instead of an endless loop.
        key = (loc, id(path))
        active = {key}
        stack = [(self.apply(loc, x, path, sink), key)]
        while stack:
            gen, key = stack[-1]
            req = next(gen, None)
            if req is None:
                stack.pop()
                active.discard(key)
                continue
            key = (req[0], id(req[2]))
            if key in active:
                raise RuntimeError("in-place cycle reached during validation")
            active.add(key)
            stack.append((self.apply(*req), key))

    def apply(self, loc, x, path, sink):
        s = self.locs[loc]
        if s is True:
            return
        if s is False:
            sink.append((path, "false", loc))
            return
        if "type" in s:
            names = s["type"]
            if type(names) is str:
                names = (names,)
            if not any(type_matches(x, n) for n in names):
                sink.append((path, "type", loc + "/type"))
                return
        t = type(x)
        if "enum" in s and jkey(x) not in self.key_set(loc + "/enum", s["enum"]):
            sink.append((path, "enum", loc + "/enum"))
        if "const" in s and jkey(x) not in self.key_set(loc + "/const", [s["const"]]):
            sink.append((path, "const", loc + "/const"))

        if t is int or t is float:
            if "minimum" in s and x < s["minimum"]:
                sink.append((path, "minimum", loc + "/minimum"))
            if "maximum" in s and x > s["maximum"]:
                sink.append((path, "maximum", loc + "/maximum"))
            if "exclusiveMinimum" in s and x <= s["exclusiveMinimum"]:
                sink.append((path, "exclusiveMinimum", loc + "/exclusiveMinimum"))
            if "exclusiveMaximum" in s and x >= s["exclusiveMaximum"]:
                sink.append((path, "exclusiveMaximum", loc + "/exclusiveMaximum"))
            if "multipleOf" in s and (exact(x) / exact(s["multipleOf"])).denominator != 1:
                sink.append((path, "multipleOf", loc + "/multipleOf"))

        elif t is str:
            if "minLength" in s and len(x) < s["minLength"]:
                sink.append((path, "minLength", loc + "/minLength"))
            if "maxLength" in s and len(x) > s["maxLength"]:
                sink.append((path, "maxLength", loc + "/maxLength"))
            if "pattern" in s and self.cache[s["pattern"]].search(x) is None:
                sink.append((path, "pattern", loc + "/pattern"))

        elif t is list:
            if "minItems" in s and len(x) < s["minItems"]:
                sink.append((path, "minItems", loc + "/minItems"))
            if "maxItems" in s and len(x) > s["maxItems"]:
                sink.append((path, "maxItems", loc + "/maxItems"))
            if s.get("uniqueItems") is True and len({jkey(e) for e in x}) < len(x):
                sink.append((path, "uniqueItems", loc + "/uniqueItems"))
            n = 0
            if "prefixItems" in s:
                n = len(s["prefixItems"])
                for i in range(min(n, len(x))):
                    yield (loc + "/prefixItems/" + str(i), x[i], (path, str(i)), sink)
            if "items" in s:
                for i in range(n, len(x)):
                    yield (loc + "/items", x[i], (path, str(i)), sink)

        elif t is dict:
            if "required" in s and any(name not in x for name in s["required"]):
                sink.append((path, "required", loc + "/required"))
            props = s.get("properties", {})
            pats = s.get("patternProperties", {})
            additional = "additionalProperties" in s
            for k, v in x.items():
                tok = token(k)
                matched = False
                if k in props:
                    matched = True
                    yield (loc + "/properties/" + tok, v, (path, tok), sink)
                for p in pats:
                    if self.cache[p].search(k) is not None:
                        matched = True
                        yield (loc + "/patternProperties/" + token(p), v, (path, tok), sink)
                if additional and not matched:
                    yield (loc + "/additionalProperties", v, (path, tok), sink)

        if "allOf" in s:
            for i in range(len(s["allOf"])):
                yield (loc + "/allOf/" + str(i), x, path, sink)
        if "anyOf" in s:
            ok = False
            for i in range(len(s["anyOf"])):
                sub = []
                yield (loc + "/anyOf/" + str(i), x, path, sub)
                if not sub:
                    ok = True
                    break
            if not ok:
                sink.append((path, "anyOf", loc + "/anyOf"))
        if "oneOf" in s:
            accepted = 0
            for i in range(len(s["oneOf"])):
                sub = []
                yield (loc + "/oneOf/" + str(i), x, path, sub)
                if not sub:
                    accepted += 1
            if accepted != 1:
                sink.append((path, "oneOf", loc + "/oneOf"))
        if "not" in s:
            sub = []
            yield (loc + "/not", x, path, sub)
            if not sub:
                sink.append((path, "not", loc + "/not"))
        if "if" in s:
            sub = []
            yield (loc + "/if", x, path, sub)
            branch = "then" if not sub else "else"
            if branch in s:
                yield (loc + "/" + branch, x, path, sink)
        if loc in self.targets:
            yield (self.targets[loc], x, path, sink)


def validate(schema, instance):
    cache = {}
    locs, targets, problems = check_schema(schema, cache)
    if problems:
        return [{"path": None, "keyword": kw, "schema_path": at} for at, kw in sorted(problems)]
    sink = []
    Validator(locs, targets, cache).run("", instance, None, sink)
    found = {(render(path), at, kw) for path, kw, at in sink}
    return [{"path": p, "keyword": kw, "schema_path": at} for p, at, kw in sorted(found)]
