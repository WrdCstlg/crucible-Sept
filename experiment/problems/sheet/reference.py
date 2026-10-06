"""Reference for Problem 8 (spreadsheet formula evaluator). Stdlib only."""
import math
from decimal import ROUND_HALF_UP, Context, Decimal

LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
DIGITS = "0123456789"


class Err:
    __slots__ = ("code",)

    def __init__(self, code):
        self.code = code


class _Empty:
    pass


EMPTY = _Empty()
DIV0, VALUE, REF, NAME, NUM, CYCLE, PARSE = (Err(c) for c in ("#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#NUM!",
                                                            "#CYCLE!", "#PARSE!"))
ARITY = {"SUM": (1, None), "MIN": (1, None), "MAX": (1, None), "AVERAGE": (1, None), "COUNT": (1, None),
         "AND": (1, None), "OR": (1, None), "CONCAT": (1, None), "NOT": (1, 1), "IF": (2, 3), "IFERROR": (2, 2),
         "LEN": (1, 1), "ROUND": (2, 2)}
AGGREGATES = {"SUM", "MIN", "MAX", "AVERAGE", "COUNT", "AND", "OR", "CONCAT"}


class ParseError(Exception):
    pass


def is_number_literal(s):
    body = s[1:] if s.startswith("-") else s
    if "." in body:
        whole, _, frac = body.partition(".")
    else:
        whole, frac = body, None
    if whole == "" or any(ch not in DIGITS for ch in whole):
        return False
    if frac is not None and (frac == "" or any(ch not in DIGITS for ch in frac)):
        return False
    return True


def ref_key(word):
    """Valid single-letter reference -> 'A1' style key, else None."""
    if len(word) < 2 or word[0] not in LETTERS or any(ch not in DIGITS for ch in word[1:]):
        return None
    row = word[1:]
    if row[0] == "0" or int(row) > 999:
        return None
    return word[0].upper() + row


# ── Tokenizer ───────────────────────────────────────────────────────────────
def tokenize(text):
    toks, i, n = [], 0, len(text)
    while i < n:
        ch = text[i]
        if ch == " ":
            i += 1
        elif ch in DIGITS:
            j = i
            while j < n and text[j] in DIGITS:
                j += 1
            if j < n and text[j] == ".":
                k = j + 1
                while k < n and text[k] in DIGITS:
                    k += 1
                if k == j + 1:
                    raise ParseError("bad number")
                j = k
            toks.append(("num", float(text[i:j])))
            i = j
        elif ch == '"':
            j, buf = i + 1, []
            while True:
                if j >= n:
                    raise ParseError("unterminated string")
                if text[j] == '"':
                    if j + 1 < n and text[j + 1] == '"':
                        buf.append('"')
                        j += 2
                        continue
                    break
                buf.append(text[j])
                j += 1
            toks.append(("str", "".join(buf)))
            i = j + 1
        elif ch in LETTERS:
            j = i
            while j < n and text[j] in LETTERS:
                j += 1
            k = j
            while k < n and text[k] in DIGITS:
                k += 1
            word, has_digits, i = text[i:k], k > j, k
            m = i
            while m < n and text[m] == " ":
                m += 1
            if m < n and text[m] == "(":
                toks.append(("func", word.upper()))
            elif i < n and text[i] == ":":
                if not has_digits:
                    raise ParseError("':' after a name")
                j2 = i + 1
                while j2 < n and text[j2] in LETTERS:
                    j2 += 1
                k2 = j2
                while k2 < n and text[k2] in DIGITS:
                    k2 += 1
                if j2 == i + 1 or k2 == j2:
                    raise ParseError("bad range")
                a, b = ref_key(word), ref_key(text[i + 1:k2])
                toks.append(("range", (a, b)) if a and b else ("badref", None))
                i = k2
            elif word.upper() in ("TRUE", "FALSE"):
                toks.append(("bool", word.upper() == "TRUE"))
            elif has_digits:
                key = ref_key(word)
                toks.append(("ref", key) if key else ("badref", None))
            else:
                toks.append(("name", word))
        elif text.startswith(("<>", "<=", ">="), i):
            toks.append(("op", text[i:i + 2]))
            i += 2
        elif ch in "=<>&+-*/^":
            toks.append(("op", ch))
            i += 1
        elif ch in "(),":
            toks.append((ch, None))
            i += 1
        else:
            raise ParseError(f"unexpected {ch!r}")
    return toks


# ── Parser (AST nodes are tuples) ───────────────────────────────────────────
class Parser:
    def __init__(self, toks):
        self.toks, self.i = toks, 0

    def peek(self):
        return self.toks[self.i] if self.i < len(self.toks) else (None, None)

    def take(self):
        t = self.peek()
        self.i += 1
        return t

    def binary(self, ops, sub):
        node = sub()
        while self.peek()[0] == "op" and self.peek()[1] in ops:
            op = self.take()[1]
            node = ("bin", op, node, sub())
        return node

    def expr(self):
        return self.binary(("=", "<>", "<=", ">=", "<", ">"), self.concat)

    def concat(self):
        return self.binary(("&",), self.additive)

    def additive(self):
        return self.binary(("+", "-"), self.term)

    def term(self):
        return self.binary(("*", "/"), self.power)

    def power(self):
        return self.binary(("^",), self.unary)

    def unary(self):
        t = self.peek()
        if t[0] == "op" and t[1] in ("-", "+"):
            self.take()
            return ("neg" if t[1] == "-" else "pos", self.unary())
        return self.primary()

    def primary(self):
        kind, val = self.take()
        if kind in ("num", "str", "bool", "ref", "range", "badref", "name"):
            return (kind, val)
        if kind == "func":
            if self.take()[0] != "(":
                raise ParseError("expected (")
            args = []
            if self.peek()[0] == ")":
                self.take()
            else:
                while True:
                    args.append(self.expr())
                    t = self.take()
                    if t[0] == ")":
                        break
                    if t[0] != ",":
                        raise ParseError("expected , or )")
            if val in ARITY:
                lo, hi = ARITY[val]
                if len(args) < lo or (hi is not None and len(args) > hi):
                    raise ParseError("arity")
                return ("call", val, args)
            return ("unknown", val, args)
        if kind == "(":
            node = self.expr()
            if self.take()[0] != ")":
                raise ParseError("expected )")
            return ("paren", node)
        raise ParseError("unexpected token")


def parse_formula(text):
    toks = tokenize(text)
    p = Parser(toks)
    node = p.expr()
    if p.i != len(toks):
        raise ParseError("leftover")
    return node


def range_keys(a, b):
    c1, r1, c2, r2 = a[0], int(a[1:]), b[0], int(b[1:])
    cl, ch = sorted((c1, c2))
    rl, rh = sorted((r1, r2))
    return [chr(c) + str(r) for r in range(rl, rh + 1) for c in range(ord(cl), ord(ch) + 1)]


def collect_refs(node, out):
    kind = node[0]
    if kind == "ref":
        out.add(node[1])
    elif kind == "range":
        out.update(range_keys(*node[1]))
    elif kind in ("neg", "pos", "paren"):
        collect_refs(node[1], out)
    elif kind == "bin":
        collect_refs(node[2], out)
        collect_refs(node[3], out)
    elif kind in ("call", "unknown"):
        for a in node[2]:
            collect_refs(a, out)


# ── Values ──────────────────────────────────────────────────────────────────
def fmt(x):
    r = round(x, 9)
    if r == int(r):
        return str(int(r))
    return repr(r)


def to_number(v):
    t = type(v)
    if t is Err:
        return v
    if t is float:
        return v
    if t is str:
        return float(v) if is_number_literal(v) else VALUE
    if t is bool:
        return 1.0 if v else 0.0
    return 0.0


def to_text(v):
    t = type(v)
    if t is Err or t is str:
        return v
    if t is float:
        return fmt(v)
    if t is bool:
        return "TRUE" if v else "FALSE"
    return ""


def ascii_lower(s):
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in s)


def to_bool(v):
    t = type(v)
    if t is Err or t is bool:
        return v
    if t is float:
        return v != 0
    if t is str:
        low = ascii_lower(v)
        if low == "true":
            return True
        if low == "false":
            return False
        return VALUE
    return False


def finite(x):
    return x if math.isfinite(x) else NUM


def arith(op, a, b):
    x = to_number(a)
    if type(x) is Err:
        return x
    y = to_number(b)
    if type(y) is Err:
        return y
    try:
        if op == "+":
            return finite(x + y)
        if op == "-":
            return finite(x - y)
        if op == "*":
            return finite(x * y)
        if op == "/":
            return DIV0 if y == 0 else finite(x / y)
        if x == 0 and y == 0:
            return NUM
        if x == 0 and y < 0:
            return DIV0
        if x < 0 and not float(y).is_integer():
            return NUM
        return finite(float(x ** y))
    except OverflowError:
        return NUM


RANK = {float: 0, str: 1, bool: 2}
DEFAULT = {float: 0.0, str: "", bool: False}


def compare(a, b):
    if a is EMPTY and b is EMPTY:
        return 0
    if a is EMPTY:
        a = DEFAULT[type(b)]
    if b is EMPTY:
        b = DEFAULT[type(a)]
    ra, rb = RANK[type(a)], RANK[type(b)]
    if ra != rb:
        return -1 if ra < rb else 1
    if ra == 0:
        a, b = round(a, 9), round(b, 9)
    elif ra == 1:
        a, b = ascii_lower(a), ascii_lower(b)
    return (a > b) - (a < b)


def round_half_away(x, n):
    ctx = Context(prec=400)
    d = Decimal(repr(x))
    q = d.quantize(Decimal(1).scaleb(-n), rounding=ROUND_HALF_UP, context=ctx)
    return float(q)


# ── Evaluation ──────────────────────────────────────────────────────────────
class Sheet:
    def __init__(self, values):
        self.values = values  # key -> value for already evaluated / literal cells

    def cell(self, key):
        return self.values.get(key, EMPTY)

    def ev(self, node):
        kind = node[0]
        if kind == "num" or kind == "str" or kind == "bool":
            return node[1]
        if kind == "ref":
            return self.cell(node[1])
        if kind == "range":
            return VALUE
        if kind == "badref":
            return REF
        if kind == "name" or kind == "unknown":
            return NAME
        if kind == "neg":
            v = to_number(self.ev(node[1]))
            return v if type(v) is Err else -v
        if kind == "pos" or kind == "paren":
            return self.ev(node[1])
        if kind == "bin":
            op = node[1]
            a = self.ev(node[2])
            b = self.ev(node[3])
            if type(a) is Err:
                return a
            if type(b) is Err:
                return b
            if op in ("+", "-", "*", "/", "^"):
                return arith(op, a, b)
            if op == "&":
                return to_text(a) + to_text(b)
            c = compare(a, b)
            return {"=": c == 0, "<>": c != 0, "<": c < 0, "<=": c <= 0, ">": c > 0, ">=": c >= 0}[op]
        return self.call(node[1], node[2])

    def arg_values(self, arg):
        """(is_range, values) for an aggregate argument."""
        if arg[0] == "ref":
            return True, [self.cell(arg[1])]
        if arg[0] == "range":
            return True, [self.cell(k) for k in range_keys(*arg[1])]
        return False, [self.ev(arg)]

    def call(self, name, args):
        if name in ("SUM", "MIN", "MAX", "AVERAGE"):
            nums = []
            for arg in args:
                is_range, vals = self.arg_values(arg)
                for v in vals:
                    if type(v) is Err:
                        return v
                    if is_range:
                        if type(v) is float:
                            nums.append(v)
                    else:
                        x = to_number(v)
                        if type(x) is Err:
                            return x
                        nums.append(x)
            if name == "SUM" or name == "AVERAGE":
                total = 0.0
                for x in nums:
                    total += x
                if name == "SUM":
                    return finite(total)
                return DIV0 if not nums else finite(total / len(nums))
            if not nums:
                return 0.0
            return min(nums) if name == "MIN" else max(nums)
        if name == "COUNT":
            count = 0
            for arg in args:
                is_range, vals = self.arg_values(arg)
                for v in vals:
                    t = type(v)
                    if is_range:
                        count += t is float
                    else:
                        count += t is float or t is bool or (t is str and is_number_literal(v))
            return float(count)
        if name in ("AND", "OR"):
            used = []
            for arg in args:
                is_range, vals = self.arg_values(arg)
                for v in vals:
                    if type(v) is Err:
                        return v
                    if is_range:
                        if type(v) is bool:
                            used.append(v)
                        elif type(v) is float:
                            used.append(v != 0)
                    else:
                        b = to_bool(v)
                        if type(b) is Err:
                            return b
                        used.append(b)
            if not used:
                return VALUE
            return all(used) if name == "AND" else any(used)
        if name == "CONCAT":
            parts = []
            for arg in args:
                _, vals = self.arg_values(arg)
                for v in vals:
                    s = to_text(v)
                    if type(s) is Err:
                        return s
                    parts.append(s)
            return "".join(parts)
        if name == "IF":
            cond = to_bool(self.plain(args[0]))
            if type(cond) is Err:
                return cond
            if cond:
                return self.plain(args[1])
            return self.plain(args[2]) if len(args) == 3 else False
        if name == "IFERROR":
            v = self.plain(args[0])
            return self.plain(args[1]) if type(v) is Err else v
        if name == "NOT":
            b = to_bool(self.plain(args[0]))
            return b if type(b) is Err else (not b)
        if name == "LEN":
            s = to_text(self.plain(args[0]))
            return s if type(s) is Err else float(len(s))
        # ROUND
        x = to_number(self.plain(args[0]))
        if type(x) is Err:
            return x
        n = to_number(self.plain(args[1]))
        if type(n) is Err:
            return n
        n = max(-15, min(15, int(n)))
        return finite(round_half_away(x, n))

    def plain(self, arg):
        return self.ev(arg)


def literal(raw):
    if is_number_literal(raw):
        return float(raw)
    if raw in ("TRUE", "FALSE"):
        return raw == "TRUE"
    if raw == "":
        return EMPTY
    return raw


def cycle_nodes(keys, edges):
    """Iterative Tarjan: every node on a directed cycle (non-trivial SCC or self-loop)."""
    index, low, on_stack, stack, out = {}, {}, set(), [], set()
    counter = 0
    for start in keys:
        if start in index:
            continue
        work = [(start, iter(edges.get(start, ())))]
        index[start] = low[start] = counter
        counter += 1
        stack.append(start)
        on_stack.add(start)
        while work:
            node, it = work[-1]
            advanced = False
            for nxt in it:
                if nxt not in index:
                    index[nxt] = low[nxt] = counter
                    counter += 1
                    stack.append(nxt)
                    on_stack.add(nxt)
                    work.append((nxt, iter(edges.get(nxt, ()))))
                    advanced = True
                    break
                if nxt in on_stack:
                    low[node] = min(low[node], index[nxt])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                low[parent] = min(low[parent], low[node])
            if low[node] == index[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack.discard(w)
                    comp.append(w)
                    if w == node:
                        break
                if len(comp) > 1 or node in edges.get(node, ()):
                    out.update(comp)
    return out


def evaluate(cells):
    values, asts, refs_of, edges = {}, {}, {}, {}
    for key, raw in cells.items():
        if raw.startswith("="):
            try:
                asts[key] = parse_formula(raw[1:])
            except ParseError:
                values[key] = PARSE
                continue
            refs = set()
            collect_refs(asts[key], refs)
            refs_of[key] = refs
        else:
            values[key] = literal(raw)
    for key, refs in refs_of.items():
        edges[key] = [r for r in sorted(refs) if r in asts]
    keys = sorted(asts)
    for key in cycle_nodes(keys, edges):
        values[key] = CYCLE
        del asts[key]
    sheet = Sheet(values)
    # evaluate in dependency order (iterative post-order over the acyclic remainder)
    done = set()
    for start in sorted(asts):
        if start in done:
            continue
        work = [(start, iter(edges[start]))]
        done.add(start)
        while work:
            node, it = work[-1]
            pushed = False
            for nxt in it:
                if nxt in asts and nxt not in done:
                    done.add(nxt)
                    work.append((nxt, iter(edges[nxt])))
                    pushed = True
                    break
            if not pushed:
                work.pop()
                values[node] = sheet.ev(asts[node])
    out = {}
    for key, raw in cells.items():
        v = values[key]
        t = type(v)
        if t is Err:
            out[key] = {"error": v.code}
        elif t is float:
            r = round(v, 9)
            out[key] = int(r) if r == int(r) else r
        elif v is EMPTY:
            out[key] = 0 if raw.startswith("=") else None
        else:
            out[key] = v
    return out
