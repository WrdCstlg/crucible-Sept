"""Second oracle for experiment/problems/sheet/SPEC.md, written from the spec alone (reference.py was not read).

Built differently on purpose: a hand-written lexer feeds a Pratt (binding-power) parser instead of one function per
grammar level; cells on a cycle are found with Kosaraju's two-pass strongly-connected-components algorithm; the
remaining formulas are evaluated once each in a topological order from Kahn's algorithm, so no value is ever
computed by recursing through references; ROUND works on the integer digits of repr(x) instead of decimal.Decimal.
Used only to check reference.py by differential testing. Never shown to any model under study.
"""
import math
import re
from collections import deque

NUMBER_LITERAL = re.compile(r"-?[0-9]+(?:\.[0-9]+)?")
LETTERS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
DIGITS = set("0123456789")
COLUMNS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIV0, VALUE, REF, NAME, NUM, CYCLE, PARSE = "#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!", "#CYCLE!", "#PARSE!"

AGGREGATES = {"SUM", "MIN", "MAX", "AVERAGE", "COUNT", "AND", "OR", "CONCAT"}
ARITY = {**{f: (1, None) for f in AGGREGATES}, "NOT": (1, 1), "IF": (2, 3), "IFERROR": (2, 2), "LEN": (1, 1),
         "ROUND": (2, 2)}
BINDING = {"=": 10, "<>": 10, "<=": 10, ">=": 10, "<": 10, ">": 10, "&": 20, "+": 30, "-": 30, "*": 40, "/": 40,
           "^": 50}


class Err:
    __slots__ = ("code",)

    def __init__(self, code):
        self.code = code


class _Empty:
    __slots__ = ()


EMPTY = _Empty()


class GrammarError(Exception):
    pass


# ── Values and coercions ────────────────────────────────────────────────────
def ascii_lower(s):
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in s)


def fmt(x):
    r = round(x, 9)
    return str(int(r)) if r.is_integer() else repr(r)


def finite(x):
    return x if math.isfinite(x) else Err(NUM)


def to_number(v):
    t = type(v)
    if t is Err or t is float:
        return v
    if t is bool:
        return 1.0 if v else 0.0
    if v is EMPTY:
        return 0.0
    return float(v) if NUMBER_LITERAL.fullmatch(v) else Err(VALUE)


def to_text(v):
    t = type(v)
    if t is Err or t is str:
        return v
    if t is float:
        return fmt(v)
    if t is bool:
        return "TRUE" if v else "FALSE"
    return ""


def to_bool(v):
    t = type(v)
    if t is Err or t is bool:
        return v
    if t is float:
        return v != 0
    if v is EMPTY:
        return False
    low = ascii_lower(v)
    return True if low == "true" else False if low == "false" else Err(VALUE)


def literal(raw):
    if NUMBER_LITERAL.fullmatch(raw):
        return float(raw)
    if raw in ("TRUE", "FALSE"):
        return raw == "TRUE"
    return EMPTY if raw == "" else raw


# ── Lexer ───────────────────────────────────────────────────────────────────
def cell_name(word):
    """A reference token -> canonical cell name, or None if it is not a valid REF."""
    letters = word.rstrip("0123456789")
    row = word[len(letters):]
    return letters.upper() + row if len(letters) == 1 and row[0] != "0" and len(row) <= 3 else None


def word_end(src, i):
    while i < len(src) and src[i] in LETTERS:
        i += 1
    while i < len(src) and src[i] in DIGITS:
        i += 1
    return i


def before_paren(src, i):
    while i < len(src) and src[i] == " ":
        i += 1
    return i < len(src) and src[i] == "("


def lex(src):
    toks, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c == " ":
            i += 1
        elif c in DIGITS:
            j = i
            while j < n and src[j] in DIGITS:
                j += 1
            if j + 1 < n and src[j] == "." and src[j + 1] in DIGITS:
                j += 1
                while j < n and src[j] in DIGITS:
                    j += 1
            toks.append(("val", float(src[i:j])))
            i = j
        elif c == '"':
            j, buf = i + 1, []
            while True:
                if j >= n:
                    raise GrammarError("unterminated string")
                if src[j] == '"':
                    if j + 1 < n and src[j + 1] == '"':
                        buf.append('"')
                        j += 2
                        continue
                    break
                buf.append(src[j])
                j += 1
            toks.append(("val", "".join(buf)))
            i = j + 1
        elif c in LETTERS:
            j = word_end(src, i)
            word = src[i:j]
            if before_paren(src, j):
                toks.append(("func", word.upper()))
            elif word.upper() in ("TRUE", "FALSE"):
                toks.append(("val", word.upper() == "TRUE"))
            elif word[-1] in DIGITS:
                if j < n and src[j] == ":":
                    k = word_end(src, j + 1) if j + 1 < n and src[j + 1] in LETTERS else j + 1
                    right = src[j + 1:k]
                    if not right or right[-1] not in DIGITS or before_paren(src, k):
                        raise GrammarError("':' not between two reference tokens")
                    toks.append(("range", cell_name(word), cell_name(right)))
                    j = k
                else:
                    toks.append(("ref", cell_name(word)))
            else:
                toks.append(("val", Err(NAME)))
            i = j
        elif src[i:i + 2] in ("<>", "<=", ">="):
            toks.append(("op", src[i:i + 2]))
            i += 2
        elif c in "+-*/^&=<>(),":
            toks.append(("op", c))
            i += 1
        else:
            raise GrammarError(f"unexpected character {c!r}")
    return toks


# ── Pratt parser ────────────────────────────────────────────────────────────
class Parser:
    def __init__(self, toks):
        self.toks, self.i = toks, 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else ("end", None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expect(self, text):
        if self.take() != ("op", text):
            raise GrammarError(f"expected {text!r}")

    def expression(self, rbp=0):
        left = self.prefix()
        while True:
            tok = self.peek()
            if tok[0] != "op" or tok[1] not in BINDING or BINDING[tok[1]] <= rbp:
                return left
            self.take()
            left = ("bin", tok[1], left, self.expression(BINDING[tok[1]]))

    def prefix(self):
        signs = []
        while self.peek() in (("op", "-"), ("op", "+")):
            signs.append(self.take()[1])
        node = self.primary()
        for s in reversed(signs):
            node = ("neg" if s == "-" else "pos", node)
        return node

    def primary(self):
        tok = self.take()
        if tok[0] in ("val", "ref", "range"):
            return tok
        if tok == ("op", "("):
            inner = self.expression()
            self.expect(")")
            return ("paren", inner)
        if tok[0] == "func":
            self.expect("(")
            args = []
            if self.peek() == ("op", ")"):
                self.take()
            else:
                while True:
                    args.append(self.expression())
                    sep = self.take()
                    if sep == ("op", ")"):
                        break
                    if sep != ("op", ","):
                        raise GrammarError("expected ',' or ')'")
            if tok[1] in ARITY:
                lo, hi = ARITY[tok[1]]
                if len(args) < lo or (hi is not None and len(args) > hi):
                    raise GrammarError(f"{tok[1]} takes {lo}..{hi} arguments")
            return ("call", tok[1], args)
        raise GrammarError(f"unexpected {tok!r}")


def parse(formula):
    p = Parser(lex(formula))
    tree = p.expression()
    if p.peek()[0] != "end":
        raise GrammarError("leftover text")
    return tree


def range_cells(a, b):
    c1, c2 = sorted((COLUMNS.index(a[0]), COLUMNS.index(b[0])))
    r1, r2 = sorted((int(a[1:]), int(b[1:])))
    return [COLUMNS[c] + str(r) for r in range(r1, r2 + 1) for c in range(c1, c2 + 1)]


def referenced(tree):
    out, todo = set(), [tree]
    while todo:
        node = todo.pop()
        kind = node[0]
        if kind == "ref" and node[1] is not None:
            out.add(node[1])
        elif kind == "range" and node[1] is not None and node[2] is not None:
            out.update(range_cells(node[1], node[2]))
        elif kind == "bin":
            todo += [node[2], node[3]]
        elif kind in ("neg", "pos", "paren"):
            todo.append(node[1])
        elif kind == "call":
            todo += node[2]
    return out


# ── Evaluation ──────────────────────────────────────────────────────────────
def compare(a, b):
    if a is EMPTY and b is EMPTY:
        return 0
    blank = {float: 0.0, str: "", bool: False}
    if a is EMPTY:
        a = blank[type(b)]
    if b is EMPTY:
        b = blank[type(a)]
    rank = {float: 0, str: 1, bool: 2}
    if type(a) is not type(b):
        return -1 if rank[type(a)] < rank[type(b)] else 1
    if type(a) is float:
        a, b = round(a, 9), round(b, 9)
    elif type(a) is str:
        a, b = ascii_lower(a), ascii_lower(b)
    return (a > b) - (a < b)


def round_half_away(x, n):
    m = re.fullmatch(r"(-?)([0-9]+)(?:\.([0-9]+))?(?:e([+-][0-9]+))?", repr(x))
    if m is None:
        return Err(NUM)
    sign, whole, frac, exp = m.group(1), m.group(2), m.group(3) or "", int(m.group(4) or 0)
    digits, exp = int(whole + frac), exp - len(frac)          # |x| = digits * 10**exp exactly
    if exp >= -n:
        return x
    unit = 10 ** (-n - exp)
    q, r = divmod(digits, unit)
    if 2 * r >= unit:
        q += 1
    return finite(float(f"{sign}{q}e{-n}"))


class Sheet:
    def __init__(self, values):
        self.values = values

    def cell(self, name):
        return self.values.get(name, EMPTY)

    def cells_of(self, arg):
        """Arg values of a RANGE/REF argument to an aggregate, row-major."""
        if arg[0] == "ref":
            return [Err(REF)] if arg[1] is None else [self.cell(arg[1])]
        if arg[1] is None or arg[2] is None:
            return [Err(REF)]
        return [self.cell(c) for c in range_cells(arg[1], arg[2])]

    def ev(self, node):
        kind = node[0]
        if kind == "val":
            return node[1]
        if kind == "ref":
            return Err(REF) if node[1] is None else self.cell(node[1])
        if kind == "range":
            return Err(REF) if node[1] is None or node[2] is None else Err(VALUE)
        if kind == "paren":
            return self.ev(node[1])
        if kind in ("neg", "pos"):
            signs = []
            while node[0] in ("neg", "pos"):
                signs.append(node[0])
                node = node[1]
            v = self.ev(node)
            for s in reversed(signs):
                if s == "neg":
                    v = to_number(v)
                    if type(v) is not Err:
                        v = finite(-v)
            return v
        if kind == "bin":
            return self.binary(node[1], self.ev(node[2]), self.ev(node[3]))
        return self.call(node[1], node[2])

    def binary(self, op, a, b):
        if type(a) is Err:
            return a
        if type(b) is Err:
            return b
        if op == "&":
            return to_text(a) + to_text(b)
        if op in ("=", "<>", "<", ">", "<=", ">="):
            c = compare(a, b)
            return {"=": c == 0, "<>": c != 0, "<": c < 0, ">": c > 0, "<=": c <= 0, ">=": c >= 0}[op]
        x = to_number(a)
        if type(x) is Err:
            return x
        y = to_number(b)
        if type(y) is Err:
            return y
        if op == "+":
            return finite(x + y)
        if op == "-":
            return finite(x - y)
        if op == "*":
            return finite(x * y)
        if op == "/":
            return Err(DIV0) if y == 0 else finite(x / y)
        if x == 0 and y == 0:
            return Err(NUM)
        if x == 0 and y < 0:
            return Err(DIV0)
        if x < 0 and not y.is_integer():
            return Err(NUM)
        try:
            return finite(x ** y)
        except OverflowError:
            return Err(NUM)

    def call(self, name, args):
        if name not in ARITY:
            return Err(NAME)
        if name in AGGREGATES:
            return self.aggregate(name, args)
        if name == "IFERROR":
            first = self.ev(args[0])
            return self.ev(args[1]) if type(first) is Err else first
        if name == "IF":
            cond = to_bool(self.ev(args[0]))
            if type(cond) is Err:
                return cond
            if cond:
                return self.ev(args[1])
            return self.ev(args[2]) if len(args) == 3 else False
        if name == "NOT":
            v = to_bool(self.ev(args[0]))
            return v if type(v) is Err else not v
        if name == "LEN":
            t = to_text(self.ev(args[0]))
            return t if type(t) is Err else float(len(t))
        x = to_number(self.ev(args[0]))                         # ROUND
        if type(x) is Err:
            return x
        n = to_number(self.ev(args[1]))
        if type(n) is Err:
            return n
        return round_half_away(x, max(-15, min(15, int(n))))

    def aggregate(self, name, args):
        direct = [a[0] not in ("ref", "range") for a in args]
        if name == "COUNT":
            count = 0
            for arg, d in zip(args, direct):
                if d:
                    v = self.ev(arg)
                    count += type(v) in (float, bool) or (type(v) is str and bool(NUMBER_LITERAL.fullmatch(v)))
                else:
                    count += sum(type(v) is float for v in self.cells_of(arg))
            return float(count)
        if name == "CONCAT":
            parts = []
            for arg, d in zip(args, direct):
                for v in ([self.ev(arg)] if d else self.cells_of(arg)):
                    t = to_text(v)
                    if type(t) is Err:
                        return t
                    parts.append(t)
            return "".join(parts)
        if name in ("AND", "OR"):
            used = []
            for arg, d in zip(args, direct):
                if d:
                    v = to_bool(self.ev(arg))
                    if type(v) is Err:
                        return v
                    used.append(v)
                    continue
                for v in self.cells_of(arg):
                    if type(v) is Err:
                        return v
                    if type(v) is bool:
                        used.append(v)
                    elif type(v) is float:
                        used.append(v != 0)
            if not used:
                return Err(VALUE)
            return all(used) if name == "AND" else any(used)
        nums = []                                               # SUM, MIN, MAX, AVERAGE
        for arg, d in zip(args, direct):
            if d:
                v = to_number(self.ev(arg))
                if type(v) is Err:
                    return v
                nums.append(v)
                continue
            for v in self.cells_of(arg):
                if type(v) is Err:
                    return v
                if type(v) is float:
                    nums.append(v)
        if name in ("MIN", "MAX"):
            return (min(nums) if name == "MIN" else max(nums)) if nums else 0.0
        total = 0.0
        for x in nums:
            total += x
        if name == "SUM":
            return finite(total)
        return finite(total / len(nums)) if nums else Err(DIV0)


# ── Cycles, order, output ───────────────────────────────────────────────────
def cyclic_cells(adj):
    """Kosaraju: cells in a strongly connected component of size > 1, or with an edge to themselves."""
    order, seen = [], set()
    for start in adj:
        if start in seen:
            continue
        seen.add(start)
        stack = [(start, iter(adj[start]))]
        while stack:
            v, it = stack[-1]
            for w in it:
                if w not in seen:
                    seen.add(w)
                    stack.append((w, iter(adj[w])))
                    break
            else:
                stack.pop()
                order.append(v)
    radj = {v: [] for v in adj}
    for v, ws in adj.items():
        for w in ws:
            radj[w].append(v)
    on_cycle, owner = set(), {}
    for start in reversed(order):
        if start in owner:
            continue
        owner[start], members, stack = start, [start], [start]
        while stack:
            v = stack.pop()
            for w in radj[v]:
                if w not in owner:
                    owner[w] = start
                    members.append(w)
                    stack.append(w)
        if len(members) > 1 or start in adj[start]:
            on_cycle.update(members)
    return on_cycle


def output(raw, v):
    if type(v) is Err:
        return {"error": v.code}
    if v is EMPTY:
        return 0 if raw.startswith("=") else None
    if type(v) in (bool, str):
        return v
    r = round(v, 9)
    return int(r) if r.is_integer() else r


def evaluate(cells):
    values, trees = {}, {}
    for key, raw in cells.items():
        if raw.startswith("="):
            try:
                trees[key] = parse(raw[1:])
            except GrammarError:
                values[key] = Err(PARSE)
        else:
            values[key] = literal(raw)
    adj = {c: {t for t in referenced(tree) if t in trees} for c, tree in trees.items()}
    on_cycle = cyclic_cells(adj)
    for c in on_cycle:
        values[c] = Err(CYCLE)
    pending = {c: {t for t in adj[c] if t not in on_cycle} for c in trees if c not in on_cycle}
    users = {c: [] for c in pending}
    for c, deps in pending.items():
        for t in deps:
            users[t].append(c)
    waiting = {c: len(deps) for c, deps in pending.items()}
    ready = deque(c for c, k in waiting.items() if k == 0)
    sheet, done = Sheet(values), 0
    while ready:
        c = ready.popleft()
        values[c] = sheet.ev(trees[c])
        done += 1
        for u in users[c]:
            waiting[u] -= 1
            if waiting[u] == 0:
                ready.append(u)
    assert done == len(pending), "non-cycle cells must form a DAG"
    return {key: output(raw, values[key]) for key, raw in cells.items()}
