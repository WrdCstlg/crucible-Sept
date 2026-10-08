import re
import sys
from bisect import bisect_left, bisect_right
from collections import OrderedDict, deque
from heapq import heappush, heappop

_NAME = re.compile(r'[A-Za-z0-9_]+')
_NUM = re.compile(r'[0-9]+')


def _to_int(s):
    t = s.lstrip('0')
    if not t:
        return 0
    try:
        return int(t)
    except ValueError:
        setter = getattr(sys, 'set_int_max_str_digits', None)
        if setter is None:
            raise
        old = sys.get_int_max_str_digits()
        setter(0)
        try:
            return int(t)
        finally:
            setter(old)


def _name_ok(s):
    return _NAME.fullmatch(s) is not None


def _num(s):
    if _NUM.fullmatch(s) is None:
        return 0
    return _to_int(s)


def _parse(line):
    if not isinstance(line, str):
        return None
    f = [x.strip() for x in line.strip().split(',')]
    n = len(f)
    cmd = f[0]
    if cmd == 'LIMIT':
        if n != 6 and n != 7:
            return None
        owner, oid, side = f[1], f[2], f[3]
        if not _name_ok(owner) or not _name_ok(oid) or side not in ('B', 'S'):
            return None
        price = _num(f[4])
        qty = _num(f[5])
        if price < 1 or qty < 1:
            return None
        flag = None
        disp = 0
        if n == 7:
            fl = f[6]
            if fl == 'IOC' or fl == 'FOK' or fl == 'POST':
                flag = fl
            elif fl.startswith('ICE='):
                disp = _num(fl[4:])
                if disp < 1 or disp >= qty:
                    return None
                flag = 'ICE'
            else:
                return None
        return ('LIMIT', owner, oid, side, price, qty, flag, disp)
    if cmd == 'MARKET':
        if n != 5:
            return None
        owner, oid, side = f[1], f[2], f[3]
        if not _name_ok(owner) or not _name_ok(oid) or side not in ('B', 'S'):
            return None
        qty = _num(f[4])
        if qty < 1:
            return None
        return ('MARKET', owner, oid, side, qty)
    if cmd == 'STOP':
        if n != 6:
            return None
        owner, oid, side = f[1], f[2], f[3]
        if not _name_ok(owner) or not _name_ok(oid) or side not in ('B', 'S'):
            return None
        trig = _num(f[4])
        qty = _num(f[5])
        if trig < 1 or qty < 1:
            return None
        return ('STOP', owner, oid, side, trig, qty)
    if cmd == 'CANCEL':
        if n != 2 or not _name_ok(f[1]):
            return None
        return ('CANCEL', f[1])
    if cmd == 'AMEND':
        if n != 4 or not _name_ok(f[1]):
            return None
        price = _num(f[2])
        qty = _num(f[3])
        if price < 1 or qty < 1:
            return None
        return ('AMEND', f[1], price, qty)
    return None


class _Order:
    __slots__ = ('owner', 'oid', 'side', 'price', 'vis', 'hid', 'disp', 'flag', 'pidx', 'obit')

    def __init__(self, owner, oid, side, price, vis, hid, disp, flag):
        self.owner = owner
        self.oid = oid
        self.side = side
        self.price = price
        self.vis = vis
        self.hid = hid
        self.disp = disp
        self.flag = flag
        self.pidx = 0
        self.obit = None


def run_book(commands):
    parsed = [_parse(c) for c in commands]

    price_set = set()
    fok_owners = set()
    trig_set = set()
    for p in parsed:
        if p is None:
            continue
        c = p[0]
        if c == 'LIMIT':
            price_set.add(p[4])
            if p[6] == 'FOK':
                fok_owners.add(p[1])
        elif c == 'AMEND':
            price_set.add(p[2])
        elif c == 'STOP':
            trig_set.add(p[4])

    track = bool(fok_owners)
    plist = sorted(price_set)
    M = len(plist)
    pos = {v: i for i, v in enumerate(plist)} if track else {}
    bid_tree = [0] * (M + 1) if track else None
    ask_tree = [0] * (M + 1) if track else None
    owner_bits = {}
    if track:
        for ow in fok_owners:
            owner_bits[(ow, 'B')] = {}
            owner_bits[(ow, 'S')] = {}

    tvals = sorted(trig_set)
    tpos = {v: i for i, v in enumerate(tvals)}
    T = len(tvals)
    size = 1
    while size < max(T, 1):
        size *= 2
    INF = len(commands) + 10
    buy_seg = [INF] * (2 * size)
    sell_seg = [INF] * (2 * size)
    buy_q = {}
    sell_q = {}
    stop_by_line = {}
    stop_by_id = {}

    orders = {}
    consumed = set()
    bids = {}
    asks = {}
    bid_heap = []
    ask_heap = []
    trades = []
    rejects = []
    stp = []
    last = None

    def bit_change(o, d):
        i = o.pidx + 1
        tree = bid_tree if o.side == 'B' else ask_tree
        while i <= M:
            tree[i] += d
            i += i & -i
        ob = o.obit
        if ob is not None:
            i = o.pidx + 1
            while i <= M:
                ob[i] = ob.get(i, 0) + d
                i += i & -i

    def pre_list(tree, k):
        s = 0
        while k > 0:
            s += tree[k]
            k -= k & -k
        return s

    def pre_dict(tree, k):
        s = 0
        while k > 0:
            s += tree.get(k, 0)
            k -= k & -k
        return s

    def fok_total(owner, side, price):
        k = pos[price]
        if side == 'B':
            ob = owner_bits[(owner, 'S')]
            return pre_list(ask_tree, k + 1) - pre_dict(ob, k + 1)
        ob = owner_bits[(owner, 'B')]
        return ((pre_list(bid_tree, M) - pre_list(bid_tree, k))
                - (pre_dict(ob, M) - pre_dict(ob, k)))

    def best_ask():
        h = ask_heap
        while h:
            p = h[0]
            if p in asks:
                return p
            heappop(h)
        return None

    def best_bid():
        h = bid_heap
        while h:
            p = -h[0]
            if p in bids:
                return p
            heappop(h)
        return None

    def crosses(side, price):
        if side == 'B':
            a = best_ask()
            return a is not None and a <= price
        b = best_bid()
        return b is not None and b >= price

    def match(owner, oid, side, limit, qty):
        nonlocal last
        if side == 'B':
            levels = asks
            heap = ask_heap
            neg = False
        else:
            levels = bids
            heap = bid_heap
            neg = True
        while qty > 0:
            p = None
            while heap:
                top = heap[0]
                pp = -top if neg else top
                if pp in levels:
                    p = pp
                    break
                heappop(heap)
            if p is None:
                break
            if limit is not None:
                if neg:
                    if p < limit:
                        break
                elif p > limit:
                    break
            level = levels[p]
            while qty > 0 and level:
                o = next(iter(level.values()))
                if o.owner == owner:
                    del level[o.oid]
                    del orders[o.oid]
                    stp.append(o.oid)
                    if track:
                        bit_change(o, -(o.vis + o.hid))
                    continue
                v = o.vis
                t = qty if qty < v else v
                qty -= t
                v -= t
                o.vis = v
                if neg:
                    trades.append({"seq": len(trades) + 1, "price": p, "qty": t,
                                   "buy": o.oid, "sell": oid, "aggressor": side})
                else:
                    trades.append({"seq": len(trades) + 1, "price": p, "qty": t,
                                   "buy": oid, "sell": o.oid, "aggressor": side})
                last = p
                if track:
                    bit_change(o, -t)
                if v == 0:
                    h = o.hid
                    if h > 0:
                        d = o.disp
                        r = d if d < h else h
                        o.hid = h - r
                        o.vis = r
                        level.move_to_end(o.oid)
                    else:
                        del level[o.oid]
                        del orders[o.oid]
            if not level:
                del levels[p]
        return qty

    def rest(owner, oid, side, price, r, flag, disp):
        if flag == 'ICE':
            vis = disp if disp < r else r
            hid = r - vis
        else:
            vis = r
            hid = 0
        o = _Order(owner, oid, side, price, vis, hid, disp, flag)
        if side == 'B':
            levels = bids
            heap = bid_heap
            key = -price
        else:
            levels = asks
            heap = ask_heap
            key = price
        level = levels.get(price)
        if level is None:
            level = OrderedDict()
            levels[price] = level
            heappush(heap, key)
        level[oid] = o
        orders[oid] = o
        if track:
            o.pidx = pos[price]
            o.obit = owner_bits.get((owner, side))
            bit_change(o, r)

    def remove_order(o):
        levels = bids if o.side == 'B' else asks
        level = levels[o.price]
        del level[o.oid]
        if not level:
            del levels[o.price]
        del orders[o.oid]
        if track:
            bit_change(o, -(o.vis + o.hid))

    def refresh(side, tidx):
        if side == 'B':
            q = buy_q[tidx]
            seg = buy_seg
        else:
            q = sell_q[tidx]
            seg = sell_seg
        while q and q[0] not in stop_by_line:
            q.popleft()
        val = q[0] if q else INF
        i = tidx + size
        if seg[i] == val:
            return
        seg[i] = val
        i >>= 1
        while i:
            a = seg[2 * i]
            b = seg[2 * i + 1]
            seg[i] = a if a < b else b
            i >>= 1

    def seg_query(seg, l, r):
        res = INF
        l += size
        r += size
        while l < r:
            if l & 1:
                if seg[l] < res:
                    res = seg[l]
                l += 1
            if r & 1:
                r -= 1
                if seg[r] < res:
                    res = seg[r]
            l >>= 1
            r >>= 1
        return res

    def run_stops():
        while stop_by_line and last is not None:
            L = last
            kb = bisect_right(tvals, L)
            b = seg_query(buy_seg, 0, kb) if kb > 0 else INF
            ks = bisect_left(tvals, L)
            s = seg_query(sell_seg, ks, T) if ks < T else INF
            line = b if b < s else s
            if line >= INF:
                return
            owner, oid, side, trig, qty, tidx = stop_by_line.pop(line)
            del stop_by_id[oid]
            refresh(side, tidx)
            rem = match(owner, oid, side, None, qty)
            if rem == qty:
                rejects.append({"line": line, "reason": "no_liquidity"})

    for i, p in enumerate(parsed):
        if p is None:
            rejects.append({"line": i, "reason": "malformed"})
            continue
        c = p[0]
        tc0 = len(trades)
        new_stop = False
        if c == 'LIMIT':
            _, owner, oid, side, price, qty, flag, disp = p
            if oid in consumed:
                rejects.append({"line": i, "reason": "duplicate_id"})
                continue
            consumed.add(oid)
            if flag == 'POST':
                if crosses(side, price):
                    rejects.append({"line": i, "reason": "post_would_cross"})
                else:
                    rest(owner, oid, side, price, qty, 'POST', 0)
            elif flag == 'FOK':
                if fok_total(owner, side, price) < qty:
                    rejects.append({"line": i, "reason": "fok_unfilled"})
                else:
                    match(owner, oid, side, price, qty)
            elif flag == 'IOC':
                match(owner, oid, side, price, qty)
            else:
                r = match(owner, oid, side, price, qty)
                if r > 0:
                    rest(owner, oid, side, price, r, flag, disp)
        elif c == 'MARKET':
            _, owner, oid, side, qty = p
            if oid in consumed:
                rejects.append({"line": i, "reason": "duplicate_id"})
                continue
            consumed.add(oid)
            r = match(owner, oid, side, None, qty)
            if r == qty:
                rejects.append({"line": i, "reason": "no_liquidity"})
        elif c == 'STOP':
            _, owner, oid, side, trig, qty = p
            if oid in consumed:
                rejects.append({"line": i, "reason": "duplicate_id"})
                continue
            consumed.add(oid)
            tidx = tpos[trig]
            stop_by_line[i] = (owner, oid, side, trig, qty, tidx)
            stop_by_id[oid] = i
            qd = buy_q if side == 'B' else sell_q
            q = qd.get(tidx)
            if q is None:
                q = deque()
                qd[tidx] = q
            q.append(i)
            refresh(side, tidx)
            new_stop = True
        elif c == 'CANCEL':
            oid = p[1]
            o = orders.get(oid)
            if o is not None:
                remove_order(o)
            elif oid in stop_by_id:
                line = stop_by_id.pop(oid)
                st = stop_by_line.pop(line)
                refresh(st[2], st[5])
            else:
                rejects.append({"line": i, "reason": "unknown_id"})
        elif c == 'AMEND':
            _, oid, price, qty = p
            o = orders.get(oid)
            if o is None:
                rejects.append({"line": i, "reason": "unknown_id"})
            else:
                total = o.vis + o.hid
                if price == o.price and qty == total:
                    pass
                elif price == o.price and qty < total:
                    d = total - qty
                    if o.hid >= d:
                        o.hid -= d
                    else:
                        d2 = d - o.hid
                        o.hid = 0
                        o.vis -= d2
                    if track:
                        bit_change(o, -d)
                else:
                    if o.flag == 'POST' and crosses(o.side, price):
                        rejects.append({"line": i, "reason": "post_would_cross"})
                    else:
                        remove_order(o)
                        r = match(o.owner, oid, o.side, price, qty)
                        if r > 0:
                            rest(o.owner, oid, o.side, price, r, o.flag, o.disp)
        if stop_by_line and (new_stop or len(trades) != tc0):
            run_stops()

    out_bids = []
    for pr in sorted(bids, reverse=True):
        out_bids.append([pr, [[o.oid, o.vis, o.hid] for o in bids[pr].values()]])
    out_asks = []
    for pr in sorted(asks):
        out_asks.append([pr, [[o.oid, o.vis, o.hid] for o in asks[pr].values()]])
    out_stops = []
    for line in sorted(stop_by_line):
        st = stop_by_line[line]
        out_stops.append([st[1], st[2], st[3], st[4]])

    return {
        "trades": trades,
        "rejects": rejects,
        "stp_cancelled": stp,
        "bids": out_bids,
        "asks": out_asks,
        "stops": out_stops,
        "last_price": last,
    }