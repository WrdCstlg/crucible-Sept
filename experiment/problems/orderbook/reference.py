"""Trusted reference for Problem 6 (order book). Written from SPEC.md; never shown to any model.

Book: per side, a heap of prices plus, per price, a deque of (token, order). An order's current token marks its live
queue entry; refreshing an iceberg or re-queuing appends a new entry and leaves the old one stale (skipped lazily).
"""
import heapq
import re
from collections import deque

_ID = re.compile(r"[A-Za-z0-9_]+")
_NUM = re.compile(r"[0-9]+")


class _Order:
    __slots__ = ("owner", "id", "side", "price", "vis", "hid", "display", "flag", "token", "alive")


class _Stop:
    __slots__ = ("owner", "id", "side", "trigger", "qty", "line", "alive")


def _num(s):
    if not _NUM.fullmatch(s):
        return None
    v = int(s)
    return v if v >= 1 else None


def _parse(raw):
    if not isinstance(raw, str):
        return None
    f = [x.strip() for x in raw.strip().split(",")]
    cmd = f[0]
    if cmd == "LIMIT" and len(f) in (6, 7):
        owner, oid, side, price, qty = f[1], f[2], f[3], _num(f[4]), _num(f[5])
        flag, display = None, None
        if len(f) == 7:
            if f[6] in ("IOC", "FOK", "POST"):
                flag = f[6]
            elif f[6].startswith("ICE="):
                display = _num(f[6][4:])
                if display is None or qty is None or display >= qty:
                    return None
                flag = "ICE"
            else:
                return None
        if _ID.fullmatch(owner) and _ID.fullmatch(oid) and side in ("B", "S") and price and qty:
            return ("LIMIT", owner, oid, side, price, qty, flag, display)
        return None
    if cmd == "MARKET" and len(f) == 5:
        owner, oid, side, qty = f[1], f[2], f[3], _num(f[4])
        if _ID.fullmatch(owner) and _ID.fullmatch(oid) and side in ("B", "S") and qty:
            return ("MARKET", owner, oid, side, qty)
        return None
    if cmd == "STOP" and len(f) == 6:
        owner, oid, side, trig, qty = f[1], f[2], f[3], _num(f[4]), _num(f[5])
        if _ID.fullmatch(owner) and _ID.fullmatch(oid) and side in ("B", "S") and trig and qty:
            return ("STOP", owner, oid, side, trig, qty)
        return None
    if cmd == "CANCEL" and len(f) == 2:
        return ("CANCEL", f[1]) if _ID.fullmatch(f[1]) else None
    if cmd == "AMEND" and len(f) == 4:
        price, qty = _num(f[2]), _num(f[3])
        if _ID.fullmatch(f[1]) and price and qty:
            return ("AMEND", f[1], price, qty)
        return None
    return None


class _Engine:
    def __init__(self):
        self.levels = {"B": {}, "S": {}}      # side -> price -> deque[(token, order)]
        self.count = {"B": {}, "S": {}}       # side -> price -> live orders at that price
        self.heaps = {"B": [], "S": []}       # bids store -price
        self.orders = {}                      # id -> resting _Order
        self.stops = {}                       # id -> untriggered _Stop
        self.pend = {"B": [], "S": []}        # buy: (trigger, line, stop); sell: (-trigger, line, stop)
        self.ready = []                       # (line, stop): once qualified, re-checked when popped
        self.consumed = set()
        self.tok = 0
        self.trades, self.rejects, self.stp = [], [], []
        self.last = None

    # book primitives
    def _token(self):
        self.tok += 1
        return self.tok

    def _enqueue(self, o):
        lv = self.levels[o.side]
        q = lv.get(o.price)
        if q is None:
            q = lv[o.price] = deque()
        o.token = self._token()
        q.append((o.token, o))
        c = self.count[o.side]
        if c.get(o.price, 0) == 0:
            heapq.heappush(self.heaps[o.side], -o.price if o.side == "B" else o.price)
        c[o.price] = c.get(o.price, 0) + 1

    def _remove(self, o):
        o.alive = False
        self.count[o.side][o.price] -= 1
        del self.orders[o.id]

    def _best(self, side):
        h, c = self.heaps[side], self.count[side]
        while h:
            price = -h[0] if side == "B" else h[0]
            if c.get(price, 0) > 0:
                q = self.levels[side][price]
                while True:
                    tok, o = q[0]
                    if o.alive and o.token == tok:
                        return o
                    q.popleft()
            heapq.heappop(h)
            c.pop(price, None)
            self.levels[side].pop(price, None)
        return None

    @staticmethod
    def _tradable(side, limit, price):
        return limit is None or (price <= limit if side == "B" else price >= limit)

    def _rest(self, owner, oid, side, price, qty, flag, display):
        o = _Order()
        o.owner, o.id, o.side, o.price, o.flag, o.display, o.alive = owner, oid, side, price, flag, display, True
        if flag == "ICE":
            o.vis = min(display, qty)
            o.hid = qty - o.vis
        else:
            o.vis, o.hid = qty, 0
        self.orders[oid] = o
        self._enqueue(o)

    def _match(self, owner, oid, side, limit, qty):
        opp = "S" if side == "B" else "B"
        traded = 0
        while qty > 0:
            o = self._best(opp)
            if o is None or not self._tradable(side, limit, o.price):
                break
            if o.owner == owner:
                self._remove(o)
                self.stp.append(o.id)
                continue
            q = min(qty, o.vis)
            buy, sell = (oid, o.id) if side == "B" else (o.id, oid)
            self.trades.append({"seq": len(self.trades) + 1, "price": o.price, "qty": q, "buy": buy, "sell": sell,
                                "aggressor": side})
            self.last = o.price
            qty -= q
            traded += q
            o.vis -= q
            if o.vis == 0:
                if o.hid > 0:
                    r = min(o.display, o.hid)
                    o.vis, o.hid = r, o.hid - r
                    o.token = self._token()                 # back of the level
                    self.levels[opp][o.price].append((o.token, o))
                else:
                    self._remove(o)
        return qty, traded

    def _available(self, owner, side, limit, need):
        opp = "S" if side == "B" else "B"
        prices = sorted((p for p, n in self.count[opp].items() if n > 0), reverse=(opp == "B"))
        total = 0
        for p in prices:
            if not self._tradable(side, limit, p):
                break
            for tok, o in self.levels[opp][p]:
                if o.alive and o.token == tok and o.owner != owner:
                    total += o.vis + o.hid
                    if total >= need:
                        return total
        return total

    def _crosses(self, side, price):
        o = self._best("S" if side == "B" else "B")
        return o is not None and self._tradable(side, price, o.price)

    def _enter_limit(self, line, owner, oid, side, price, qty, flag, display):
        if flag == "FOK" and self._available(owner, side, price, qty) < qty:
            self.rejects.append({"line": line, "reason": "fok_unfilled"})
            return
        if flag == "POST":
            if self._crosses(side, price):
                self.rejects.append({"line": line, "reason": "post_would_cross"})
                return
            self._rest(owner, oid, side, price, qty, flag, display)
            return
        rem, _ = self._match(owner, oid, side, price, qty)
        if rem > 0 and flag not in ("IOC", "FOK"):
            self._rest(owner, oid, side, price, rem, flag, display)

    def _market(self, line, owner, oid, side, qty):
        _, traded = self._match(owner, oid, side, None, qty)
        if traded == 0:
            self.rejects.append({"line": line, "reason": "no_liquidity"})

    # stops
    def _qualifies(self, s):
        return self.last is not None and (self.last >= s.trigger if s.side == "B" else self.last <= s.trigger)

    def _run_stops(self):
        while self.last is not None:
            pb, ps = self.pend["B"], self.pend["S"]
            while pb and pb[0][0] <= self.last:
                _, line, s = heapq.heappop(pb)
                heapq.heappush(self.ready, (line, s))
            while ps and -ps[0][0] >= self.last:
                _, line, s = heapq.heappop(ps)
                heapq.heappush(self.ready, (line, s))
            chosen = None
            while self.ready:
                line, s = heapq.heappop(self.ready)
                if not s.alive:
                    continue
                if self._qualifies(s):
                    chosen = s
                    break
                heapq.heappush(self.pend[s.side], (s.trigger if s.side == "B" else -s.trigger, s.line, s))
            if chosen is None:
                return
            chosen.alive = False
            del self.stops[chosen.id]
            self._market(chosen.line, chosen.owner, chosen.id, chosen.side, chosen.qty)

    # commands
    def process(self, line, raw):
        p = _parse(raw)
        if p is None:
            self.rejects.append({"line": line, "reason": "malformed"})
            return
        kind = p[0]
        if kind in ("LIMIT", "MARKET", "STOP"):
            oid = p[2]
            if oid in self.consumed:
                self.rejects.append({"line": line, "reason": "duplicate_id"})
                return
            self.consumed.add(oid)
            if kind == "LIMIT":
                self._enter_limit(line, *p[1:])
            elif kind == "MARKET":
                self._market(line, *p[1:])
            else:
                s = _Stop()
                s.owner, s.id, s.side, s.trigger, s.qty, s.line, s.alive = p[1], p[2], p[3], p[4], p[5], line, True
                self.stops[s.id] = s
                heapq.heappush(self.pend[s.side], (s.trigger if s.side == "B" else -s.trigger, line, s))
        elif kind == "CANCEL":
            oid = p[1]
            if oid in self.orders:
                self._remove(self.orders[oid])
            elif oid in self.stops:
                self.stops.pop(oid).alive = False
            else:
                self.rejects.append({"line": line, "reason": "unknown_id"})
        else:
            _, oid, price, qty = p
            o = self.orders.get(oid)
            if o is None:
                self.rejects.append({"line": line, "reason": "unknown_id"})
                return
            rem = o.vis + o.hid
            if price == o.price and qty == rem:
                return
            if price == o.price and qty < rem:
                cut = rem - qty
                d = min(o.hid, cut)
                o.hid -= d
                o.vis -= cut - d
                return
            if o.flag == "POST" and self._crosses(o.side, price):
                self.rejects.append({"line": line, "reason": "post_would_cross"})
                return
            self._remove(o)
            self._enter_limit(line, o.owner, o.id, o.side, price, qty, o.flag, o.display)
        self._run_stops()

    def snapshot(self, side):
        out = []
        for price in sorted((p for p, n in self.count[side].items() if n > 0), reverse=(side == "B")):
            orders = [[o.id, o.vis, o.hid] for tok, o in self.levels[side][price] if o.alive and o.token == tok]
            out.append([price, orders])
        return out


def run_book(commands):
    e = _Engine()
    for i, raw in enumerate(commands):
        e.process(i, raw)
    stops = sorted(e.stops.values(), key=lambda s: s.line)
    return {"trades": e.trades, "rejects": e.rejects, "stp_cancelled": e.stp, "bids": e.snapshot("B"),
            "asks": e.snapshot("S"), "stops": [[s.id, s.side, s.trigger, s.qty] for s in stops],
            "last_price": e.last}
