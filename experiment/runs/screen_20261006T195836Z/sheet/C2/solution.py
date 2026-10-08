import math
import re
import sys
from bisect import bisect_left, bisect_right
from decimal import Decimal, Context, ROUND_HALF_UP

_isfinite = math.isfinite


class _Err(object):
    __slots__ = ('code',)

    def __init__(self, code):
        self.code = code

    def __repr__(self):
        return self.code


class _EmptyType(object):
    __slots__ = ()

    def __repr__(self):
        return '<empty>'


EMPTY = _EmptyType()
DIV0 = _Err('#DIV/0!')
VALUE = _Err('#VALUE!')
REF = _Err('#REF!')
NAME = _Err('#NAME?')
NUM = _Err('#NUM!')
CYCLE = _Err('#CYCLE!')
PARSE = _Err('#PARSE!')

_NUMLIT = re.compile(r'-?[0-9]+(?:\.[0-9]+)?')
_LOWER = str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')
_TOKRE = re.compile(
    r' *(?:([0-9]+(?:\.[0-9]+)?)|([A-Za-z]+[0-9]*)|"((?:[^"]|"")*)"|(<>|<=|>=|[-+*/^&=<>(),:]))'
)
_CMP = frozenset(('=', '<>', '<=', '>=', '<', '>'))
_ARITY = {
    'SUM': (1, None), 'MIN': (1, None), 'MAX': (1, None), 'AVERAGE': (1, None),
    'COUNT': (1, None), 'AND': (1, None), 'OR': (1, None), 'CONCAT': (1, None),
    'NOT': (1, 1), 'LEN': (1, 1), 'IF': (2, 3), 'IFERROR': (2, 2), 'ROUND': (2, 2),
}
_RANK = {float: 0, str: 1, bool: 2}
_DCTX = Context(prec=2000, rounding=ROUND_HALF_UP, Emin=-999999, Emax=999999)


def _fmt(x):
    r = round(x, 9)
    if r.is_integer():
        return str(int(r))
    return repr(r)


def _to_num(v):
    t = type(v)
    if t is float:
        return v
    if t is bool:
        return 1.0 if v else 0.0
    if t is str:
        if _NUMLIT.fullmatch(v):
            return float(v)
        return VALUE
    if v is EMPTY:
        return 0.0
    return v


def _to_text(v):
    t = type(v)
    if t is str:
        return v
    if t is float:
        return _fmt(v)
    if t is bool:
        return 'TRUE' if v else 'FALSE'
    if v is EMPTY:
        return ''
    return v


def _to_bool(v):
    t = type(v)
    if t is bool:
        return v
    if t is float:
        return v != 0
    if t is str:
        s = v.translate(_LOWER)
        if s == 'true':
            return True
        if s == 'false':
            return False
        return VALUE
    if v is EMPTY:
        return False
    return v


def _compare(l, r):
    if l is EMPTY:
        if r is EMPTY:
            return 0
        tr = type(r)
        l = 0.0 if tr is float else ('' if tr is str else False)
    elif r is EMPTY:
        tl = type(l)
        r = 0.0 if tl is float else ('' if tl is str else False)
    tl = type(l)
    tr = type(r)
    if tl is not tr:
        return -1 if _RANK[tl] < _RANK[tr] else 1
    if tl is float:
        a = round(l, 9)
        b = round(r, 9)
    elif tl is str:
        a = l.translate(_LOWER)
        b = r.translate(_LOWER)
    else:
        a = l
        b = r
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def _round_num(x, n):
    if not _isfinite(x):
        return NUM
    if n > 15:
        k = 15
    elif n < -15:
        k = -15
    else:
        k = int(n)
    try:
        d = Decimal(repr(x))
        q = d.quantize(Decimal((0, (1,), -k)), rounding=ROUND_HALF_UP, context=_DCTX)
        res = float(q)
    except Exception:
        return NUM
    if not _isfinite(res):
        return NUM
    return res


def _literal(raw):
    if _NUMLIT.fullmatch(raw):
        return float(raw)
    if raw == 'TRUE':
        return True
    if raw == 'FALSE':
        return False
    if raw == '':
        return EMPTY
    return raw


class _ParseError(Exception):
    pass


def _tokenize(text):
    toks = []
    pos = 0
    n = len(text)
    match = _TOKRE.match
    while True:
        m = match(text, pos)
        if m is None:
            if text.count(' ', pos) != n - pos:
                raise _ParseError()
            break
        g = m.lastindex
        if g == 1:
            toks.append(('N', float(m.group(1)), 0, 0))
        elif g == 2:
            toks.append(('W', m.group(2), m.start(2), m.end(2)))
        elif g == 3:
            toks.append(('S', m.group(3).replace('""', '"'), 0, 0))
        else:
            op = m.group(4)
            toks.append((op, op, m.start(4), m.end(4)))
        pos = m.end()
    toks.append(('END', None, n, n))
    return toks


def _parse_ref(word):
    # word: letters followed by at least one digit
    if len(word) < 2:
        return None
    c = word[1]
    if not ('0' <= c <= '9'):
        return None
    digits = word[1:]
    if digits[0] == '0' or len(digits) > 3:
        return None
    row = int(digits)
    if row < 1 or row > 999:
        return None
    col = ord(word[0].upper()) - 65
    return col, row


def _is_reftok(word):
    c = word[-1]
    return '0' <= c <= '9'


class _Parser(object):
    __slots__ = ('toks', 'i', 'refs', 'ranges')

    def __init__(self, toks):
        self.toks = toks
        self.i = 0
        self.refs = []
        self.ranges = []

    def expr(self):
        left = self.concat()
        toks = self.toks
        while True:
            k = toks[self.i][0]
            if k in _CMP:
                self.i += 1
                right = self.concat()
                left = ('cmp', k, left, right)
            else:
                return left

    def concat(self):
        left = self.additive()
        toks = self.toks
        while toks[self.i][0] == '&':
            self.i += 1
            right = self.additive()
            left = ('cat', left, right)
        return left

    def additive(self):
        left = self.term()
        toks = self.toks
        while True:
            k = toks[self.i][0]
            if k == '+' or k == '-':
                self.i += 1
                right = self.term()
                left = ('arith', k, left, right)
            else:
                return left

    def term(self):
        left = self.power()
        toks = self.toks
        while True:
            k = toks[self.i][0]
            if k == '*' or k == '/':
                self.i += 1
                right = self.power()
                left = ('arith', k, left, right)
            else:
                return left

    def power(self):
        left = self.unary()
        toks = self.toks
        while toks[self.i][0] == '^':
            self.i += 1
            right = self.unary()
            left = ('pow', left, right)
        return left

    def unary(self):
        toks = self.toks
        ops = []
        while True:
            k = toks[self.i][0]
            if k == '+' or k == '-':
                ops.append(k)
                self.i += 1
            else:
                break
        node = self.primary()
        for op in reversed(ops):
            node = ('neg', node) if op == '-' else ('pos', node)
        return node

    def primary(self):
        toks = self.toks
        t = toks[self.i]
        k = t[0]
        if k == 'N' or k == 'S':
            self.i += 1
            return ('const', t[1])
        if k == '(':
            self.i += 1
            e = self.expr()
            if toks[self.i][0] != ')':
                raise _ParseError()
            self.i += 1
            if e[0] == 'ref' or e[0] == 'range':
                return ('group', e)
            return e
        if k == 'W':
            word = t[1]
            nxt = toks[self.i + 1]
            if nxt[0] == '(':
                self.i += 2
                name = word.upper()
                args = []
                if toks[self.i][0] == ')':
                    self.i += 1
                else:
                    args.append(self.expr())
                    while toks[self.i][0] == ',':
                        self.i += 1
                        args.append(self.expr())
                    if toks[self.i][0] != ')':
                        raise _ParseError()
                    self.i += 1
                ar = _ARITY.get(name)
                if ar is None:
                    return ('const', NAME)
                lo, hi = ar
                if len(args) < lo or (hi is not None and len(args) > hi):
                    raise _ParseError()
                return ('call', name, args)
            self.i += 1
            up = word.upper()
            if up == 'TRUE':
                return ('const', True)
            if up == 'FALSE':
                return ('const', False)
            if not _is_reftok(word):
                return ('const', NAME)
            # reference token; maybe a range
            if nxt[0] == ':' and nxt[2] == t[3]:
                w2 = toks[self.i + 1]
                if (w2[0] == 'W' and w2[2] == nxt[3] and _is_reftok(w2[1])
                        and toks[self.i + 2][0] != '('):
                    self.i += 2
                    a = _parse_ref(word)
                    b = _parse_ref(w2[1])
                    if a is None or b is None:
                        return ('const', REF)
                    c1, r1 = a
                    c2, r2 = b
                    if c1 > c2:
                        c1, c2 = c2, c1
                    if r1 > r2:
                        r1, r2 = r2, r1
                    self.ranges.append((c1, r1, c2, r2))
                    return ('range', c1, r1, c2, r2)
            a = _parse_ref(word)
            if a is None:
                return ('const', REF)
            idx = a[1] * 26 + a[0]
            self.refs.append(idx)
            return ('ref', idx)
        raise _ParseError()


def _parse_formula(text):
    toks = _tokenize(text)
    p = _Parser(toks)
    node = p.expr()
    if toks[p.i][0] != 'END':
        raise _ParseError()
    return node, p.refs, p.ranges


def _evaluate(cells):
    N = 26 * 1000
    vals = [EMPTY] * N
    asts = {}
    info = {}
    is_node = bytearray(N)
    keyidx = []
    for key, raw in cells.items():
        idx = int(key[1:]) * 26 + (ord(key[0]) - 65)
        isf = raw[:1] == '='
        keyidx.append((key, idx, isf))
        if isf:
            try:
                node, refs, ranges = _parse_formula(raw[1:])
            except _ParseError:
                vals[idx] = PARSE
                continue
            asts[idx] = node
            info[idx] = (refs, ranges)
            is_node[idx] = 1
        else:
            vals[idx] = _literal(raw)

    # ---- reference graph ----
    col_rows = [[] for _ in range(26)]
    for idx in asts:
        col_rows[idx % 26].append(idx // 26)
    for lst in col_rows:
        lst.sort()
    adj = {}
    selfloop = set()
    for idx, (refs, ranges) in info.items():
        out = [w for w in refs if is_node[w]]
        for (c1, r1, c2, r2) in ranges:
            for c in range(c1, c2 + 1):
                rows = col_rows[c]
                if not rows:
                    continue
                lo = bisect_left(rows, r1)
                hi = bisect_right(rows, r2)
                for r in rows[lo:hi]:
                    out.append(r * 26 + c)
        adj[idx] = out
        if idx in out:
            selfloop.add(idx)

    # ---- Tarjan SCC (iterative) ----
    index = [-1] * N
    low = [0] * N
    onstk = bytearray(N)
    stk = []
    order = []
    cyc = []
    counter = 0
    for s in asts:
        if index[s] != -1:
            continue
        index[s] = low[s] = counter
        counter += 1
        stk.append(s)
        onstk[s] = 1
        work = [(s, iter(adj[s]))]
        while work:
            v, it = work[-1]
            advanced = False
            for w in it:
                if index[w] == -1:
                    index[w] = low[w] = counter
                    counter += 1
                    stk.append(w)
                    onstk[w] = 1
                    work.append((w, iter(adj[w])))
                    advanced = True
                    break
                elif onstk[w]:
                    if index[w] < low[v]:
                        low[v] = index[w]
            if advanced:
                continue
            work.pop()
            if work:
                u = work[-1][0]
                if low[v] < low[u]:
                    low[u] = low[v]
            if low[v] == index[v]:
                w = stk.pop()
                onstk[w] = 0
                if w == v:
                    if v in selfloop:
                        cyc.append(v)
                    else:
                        order.append(v)
                else:
                    cyc.append(w)
                    while w != v:
                        w = stk.pop()
                        onstk[w] = 0
                        cyc.append(w)
    for v in cyc:
        vals[v] = CYCLE

    # ---- evaluator ----
    def rr_values(a):
        if a[0] == 'ref':
            return (vals[a[1]],)
        _, c1, r1, c2, r2 = a
        if c1 == c2:
            return vals[r1 * 26 + c1: r2 * 26 + c1 + 1: 26]
        if c1 == 0 and c2 == 25:
            return vals[r1 * 26: r2 * 26 + 26]
        out = []
        for r in range(r1, r2 + 1):
            b = r * 26
            out.extend(vals[b + c1: b + c2 + 1])
        return out

    def ev(n):
        return H[n[0]](n)

    def h_const(n):
        return n[1]

    def h_ref(n):
        return vals[n[1]]

    def h_range(n):
        return VALUE

    def h_group(n):
        return ev(n[1])

    def h_pos(n):
        return ev(n[1])

    def h_neg(n):
        v = _to_num(ev(n[1]))
        if type(v) is _Err:
            return v
        r = -v
        if not _isfinite(r):
            return NUM
        return r

    def h_arith(n):
        l = ev(n[2])
        if type(l) is _Err:
            return l
        r = ev(n[3])
        if type(r) is _Err:
            return r
        a = _to_num(l)
        if type(a) is _Err:
            return a
        b = _to_num(r)
        if type(b) is _Err:
            return b
        op = n[1]
        try:
            if op == '+':
                res = a + b
            elif op == '-':
                res = a - b
            elif op == '*':
                res = a * b
            else:
                if b == 0:
                    return DIV0
                res = a / b
        except (OverflowError, ZeroDivisionError):
            return NUM
        if not _isfinite(res):
            return NUM
        return res

    def h_pow(n):
        l = ev(n[1])
        if type(l) is _Err:
            return l
        r = ev(n[2])
        if type(r) is _Err:
            return r
        a = _to_num(l)
        if type(a) is _Err:
            return a
        b = _to_num(r)
        if type(b) is _Err:
            return b
        if a == 0:
            if b == 0:
                return NUM
            if b < 0:
                return DIV0
        elif a < 0 and not b.is_integer():
            return NUM
        try:
            res = a ** b
        except (OverflowError, ZeroDivisionError, ValueError):
            return NUM
        if type(res) is not float or not _isfinite(res):
            return NUM
        return res

    def h_cat(n):
        l = ev(n[1])
        if type(l) is _Err:
            return l
        r = ev(n[2])
        if type(r) is _Err:
            return r
        return _to_text(l) + _to_text(r)

    def h_cmp(n):
        l = ev(n[2])
        if type(l) is _Err:
            return l
        r = ev(n[3])
        if type(r) is _Err:
            return r
        c = _compare(l, r)
        op = n[1]
        if op == '=':
            return c == 0
        if op == '<>':
            return c != 0
        if op == '<':
            return c < 0
        if op == '>':
            return c > 0
        if op == '<=':
            return c <= 0
        return c >= 0

    def collect_nums(args):
        nums = []
        for a in args:
            t = a[0]
            if t == 'ref' or t == 'range':
                for v in rr_values(a):
                    tv = type(v)
                    if tv is float:
                        nums.append(v)
                    elif tv is _Err:
                        return v
            else:
                v = _to_num(ev(a))
                if type(v) is _Err:
                    return v
                nums.append(v)
        return nums

    def f_sum(args):
        nums = collect_nums(args)
        if type(nums) is _Err:
            return nums
        s = 0.0
        for x in nums:
            s += x
        if not _isfinite(s):
            return NUM
        return s

    def f_average(args):
        nums = collect_nums(args)
        if type(nums) is _Err:
            return nums
        if not nums:
            return DIV0
        s = 0.0
        for x in nums:
            s += x
        try:
            res = s / len(nums)
        except OverflowError:
            return NUM
        if not _isfinite(res):
            return NUM
        return res

    def f_min(args):
        nums = collect_nums(args)
        if type(nums) is _Err:
            return nums
        if not nums:
            return 0.0
        return min(nums)

    def f_max(args):
        nums = collect_nums(args)
        if type(nums) is _Err:
            return nums
        if not nums:
            return 0.0
        return max(nums)

    def f_count(args):
        c = 0
        for a in args:
            t = a[0]
            if t == 'ref' or t == 'range':
                for v in rr_values(a):
                    if type(v) is float:
                        c += 1
            else:
                v = ev(a)
                tv = type(v)
                if tv is float or tv is bool or (tv is str and _NUMLIT.fullmatch(v)):
                    c += 1
        return float(c)

    def collect_bools(args):
        out = []
        for a in args:
            t = a[0]
            if t == 'ref' or t == 'range':
                for v in rr_values(a):
                    tv = type(v)
                    if tv is bool:
                        out.append(v)
                    elif tv is float:
                        out.append(v != 0)
                    elif tv is _Err:
                        return v
            else:
                b = _to_bool(ev(a))
                if type(b) is _Err:
                    return b
                out.append(b)
        return out

    def f_and(args):
        bs = collect_bools(args)
        if type(bs) is _Err:
            return bs
        if not bs:
            return VALUE
        return all(bs)

    def f_or(args):
        bs = collect_bools(args)
        if type(bs) is _Err:
            return bs
        if not bs:
            return VALUE
        return any(bs)

    def f_not(args):
        b = _to_bool(ev(args[0]))
        if type(b) is _Err:
            return b
        return not b

    def f_if(args):
        c = _to_bool(ev(args[0]))
        if type(c) is _Err:
            return c
        if c:
            return ev(args[1])
        if len(args) == 3:
            return ev(args[2])
        return False

    def f_iferror(args):
        v = ev(args[0])
        if type(v) is _Err:
            return ev(args[1])
        return v

    def f_concat(args):
        parts = []
        for a in args:
            t = a[0]
            if t == 'ref' or t == 'range':
                for v in rr_values(a):
                    s = _to_text(v)
                    if type(s) is _Err:
                        return s
                    parts.append(s)
            else:
                s = _to_text(ev(a))
                if type(s) is _Err:
                    return s
                parts.append(s)
        return ''.join(parts)

    def f_len(args):
        s = _to_text(ev(args[0]))
        if type(s) is _Err:
            return s
        return float(len(s))

    def f_round(args):
        x = _to_num(ev(args[0]))
        if type(x) is _Err:
            return x
        n = _to_num(ev(args[1]))
        if type(n) is _Err:
            return n
        return _round_num(x, n)

    FUNCS = {
        'SUM': f_sum, 'MIN': f_min, 'MAX': f_max, 'AVERAGE': f_average,
        'COUNT': f_count, 'AND': f_and, 'OR': f_or, 'CONCAT': f_concat,
        'NOT': f_not, 'LEN': f_len, 'IF': f_if, 'IFERROR': f_iferror,
        'ROUND': f_round,
    }

    def h_call(n):
        return FUNCS[n[1]](n[2])

    H = {
        'const': h_const, 'ref': h_ref, 'range': h_range, 'group': h_group,
        'pos': h_pos, 'neg': h_neg, 'arith': h_arith, 'pow': h_pow,
        'cat': h_cat, 'cmp': h_cmp, 'call': h_call,
    }

    for v in order:
        try:
            vals[v] = ev(asts[v])
        except Exception:
            vals[v] = VALUE

    # ---- output ----
    out = {}
    for key, idx, isf in keyidx:
        v = vals[idx]
        tv = type(v)
        if tv is float:
            r = round(v, 9)
            out[key] = int(r) if r.is_integer() else r
        elif tv is str or tv is bool:
            out[key] = v
        elif tv is _Err:
            out[key] = {'error': v.code}
        else:
            out[key] = 0 if isf else None
    return out


def evaluate(cells):
    old_limit = sys.getrecursionlimit()
    changed = False
    if old_limit < 20000:
        try:
            sys.setrecursionlimit(20000)
            changed = True
        except Exception:
            pass
    try:
        return _evaluate(cells)
    finally:
        if changed:
            try:
                sys.setrecursionlimit(old_limit)
            except Exception:
                pass