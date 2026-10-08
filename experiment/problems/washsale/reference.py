"""Reference for Problem 12 (tax lots with wash sales). Stdlib only; exact integer arithmetic.

One pass over the valid trades in processing order (date, input index). Every valid BUY's lot exists from the start,
so a loss sale can place replacement pieces on purchases that come later. Per identical group, the lots are kept in
(date, index) order with a monotone window-start pointer and a union-find "next lot with fresh shares" skip list, so
each loss row finds its candidates without rescanning used-up lots.
"""
from collections import deque
from datetime import date

WINDOW = 30
DIGITS = frozenset("0123456789")
FIELDS = ("date", "side", "symbol", "qty", "amount")


def day_number(s):
    """'YYYY-MM-DD' (ASCII digits, a real date, year 1900-2099) -> proleptic Gregorian ordinal, else None."""
    if type(s) is not str or len(s) != 10 or s[4] != "-" or s[7] != "-":
        return None
    ys, ms, ds = s[0:4], s[5:7], s[8:10]
    if not (set(ys) <= DIGITS and set(ms) <= DIGITS and set(ds) <= DIGITS):
        return None
    y, m, d = int(ys), int(ms), int(ds)
    if y < 1900 or y > 2099:
        return None
    try:
        return date(y, m, d).toordinal()
    except ValueError:
        return None


def parse_trade(t):
    if type(t) is not dict or any(k not in t for k in FIELDS):
        return None
    day = day_number(t["date"])
    side, sym, qty, amount = t["side"], t["symbol"], t["qty"], t["amount"]
    if day is None or type(side) is not str or side not in ("BUY", "SELL"):
        return None
    if type(sym) is not str or sym == "":
        return None
    if type(qty) is not int or qty < 1 or type(amount) is not int or amount < 0:
        return None
    return day, side, sym, qty, amount


def split(total, qty, k):
    """Share of `total` (spread over `qty` shares) that goes with `k` of them; the rest stays behind."""
    return total * k // qty


def term(start, sale):
    if sale - start > 366:
        return "LONG"
    s = date.fromordinal(start)
    if s.month == 2 and s.day == 29:
        anniversary = date(s.year + 1, 3, 1)
    else:
        anniversary = date(s.year + 1, s.month, s.day)
    return "LONG" if sale > anniversary.toordinal() else "SHORT"


class Lot:
    __slots__ = ("idx", "day", "sym", "fq", "fb", "repl", "pos")

    def __init__(self, idx, day, sym, qty, amount):
        self.idx, self.day, self.sym = idx, day, sym
        self.fq, self.fb = qty, amount          # fresh piece
        self.repl = deque()                     # replacement pieces: (qty, basis, carried_days)
        self.pos = -1


class Window:
    """The lots of one identical group in (date, index) order."""

    def __init__(self, lots):
        self.lots = lots
        for pos, lot in enumerate(lots):
            lot.pos = pos
        self.nxt = list(range(len(lots) + 1))   # nxt chain -> first lot at or after pos with fresh shares
        self.lo = 0

    def find(self, i):
        nxt = self.nxt
        r = i
        while nxt[r] != r:
            r = nxt[r]
        while nxt[i] != r:
            nxt[i], i = r, nxt[i]
        return r

    def exhaust(self, pos):
        self.nxt[pos] = pos + 1

    def replace(self, day, n, loss, held_days, drawn):
        lots = self.lots
        while self.lo < len(lots) and lots[self.lo].day < day - WINDOW:
            self.lo += 1
        chunks, need = [], n
        i = self.find(self.lo)
        while need and i < len(lots) and lots[i].day <= day + WINDOW:
            lot = lots[i]
            if lot.idx not in drawn:
                c = min(need, lot.fq)
                chunks.append((lot, c))
                need -= c
            i = self.find(i + 1)
        r = n - need
        if r == 0:
            return 0
        disallowed = loss * r // n
        left_d, left_r = disallowed, r
        for lot, c in chunks:
            d = split(left_d, left_r, c)
            left_d -= d
            left_r -= c
            b = split(lot.fb, lot.fq, c)
            lot.fq -= c
            lot.fb -= b
            lot.repl.append((c, b + d, held_days))
            if lot.fq == 0:
                self.exhaust(lot.pos)
        return disallowed


def compute_gains(trades, identical):
    # Identical groups: union of the listed groups (transitive).
    parent = {}

    def root(s):
        while parent[s] != s:
            parent[s] = parent[parent[s]]
            s = parent[s]
        return s

    for grp in identical:
        for s in grp:
            parent.setdefault(s, s)
        for s in grp[1:]:
            a, b = root(grp[0]), root(s)
            if a != b:
                parent[b] = a

    def group(sym):
        return root(sym) if sym in parent else sym

    # 1. Validation and processing order.
    rejected, valid = [], []
    for idx, t in enumerate(trades):
        p = parse_trade(t)
        if p is None:
            rejected.append(idx)
        else:
            valid.append((p[0], idx) + p[1:])
    valid.sort(key=lambda v: (v[0], v[1]))

    # 2. Every valid BUY's lot exists from the start.
    lots, by_group = {}, {}
    for day, idx, side, sym, qty, amount in valid:
        if side == "BUY":
            lot = Lot(idx, day, sym, qty, amount)
            lots[idx] = lot
            by_group.setdefault(group(sym), []).append(lot)
    windows = {g: Window(lst) for g, lst in by_group.items()}

    # 3-5. Process.
    held, fifo, rows = {}, {}, []
    for day, idx, side, sym, qty, amount in valid:
        if side == "BUY":
            fifo.setdefault(sym, deque()).append(lots[idx])
            held[sym] = held.get(sym, 0) + qty
            continue
        if held.get(sym, 0) < qty:
            rejected.append(idx)
            continue
        held[sym] -= qty
        win = windows[group(sym)]
        queue = fifo[sym]
        pieces, drawn, need = [], set(), qty
        while need:
            lot = queue[0]
            drawn.add(lot.idx)
            while need and lot.repl:
                pq, pb, pc = lot.repl[0]
                if pq <= need:
                    lot.repl.popleft()
                    pieces.append((lot, pq, pb, pc))
                    need -= pq
                else:
                    b = split(pb, pq, need)
                    lot.repl[0] = (pq - need, pb - b, pc)
                    pieces.append((lot, need, b, pc))
                    need = 0
            if need and lot.fq:
                k = min(need, lot.fq)
                b = split(lot.fb, lot.fq, k)
                lot.fq -= k
                lot.fb -= b
                pieces.append((lot, k, b, 0))
                need -= k
                if lot.fq == 0:
                    win.exhaust(lot.pos)
            if not lot.repl and lot.fq == 0:
                queue.popleft()
        left_amount, left_qty = amount, qty
        for lot, k, basis, carried in pieces:
            proceeds = split(left_amount, left_qty, k)
            left_amount -= proceeds
            left_qty -= k
            start = lot.day - carried
            disallowed = 0
            if basis > proceeds:
                disallowed = win.replace(day, k, basis - proceeds, day - start, drawn)
            rows.append({"sale": idx, "lot": lot.idx, "qty": k, "proceeds": proceeds, "basis": basis,
                         "gain": proceeds - basis, "disallowed": disallowed, "term": term(start, day)})

    rows.sort(key=lambda r: r["sale"])
    open_lots = []
    for day, idx, side, sym, qty, amount in valid:
        if side == "BUY":
            lot = lots[idx]
            for pq, pb, pc in lot.repl:
                open_lots.append({"lot": idx, "qty": pq, "basis": pb, "carried_days": pc})
            if lot.fq:
                open_lots.append({"lot": idx, "qty": lot.fq, "basis": lot.fb, "carried_days": 0})
    totals = {"short_term": 0, "long_term": 0, "disallowed": 0}
    for r in rows:
        totals["short_term" if r["term"] == "SHORT" else "long_term"] += r["gain"] + r["disallowed"]
        totals["disallowed"] += r["disallowed"]
    return {"realized": rows, "open_lots": open_lots, "rejected": sorted(rejected), "totals": totals}
