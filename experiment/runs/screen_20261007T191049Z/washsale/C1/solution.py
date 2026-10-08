import datetime
from bisect import bisect_left
from collections import deque

_DIGITS = "0123456789"


def compute_gains(trades, identical):
    # ---------- identical groups (union-find) ----------
    uf = {}

    def ufind(x):
        root = x
        while uf[root] != root:
            root = uf[root]
        while uf[x] != root:
            nx = uf[x]
            uf[x] = root
            x = nx
        return root

    if identical:
        for lst in identical:
            if isinstance(lst, str):
                continue
            try:
                items = list(lst)
            except TypeError:
                continue
            prev = None
            for s in items:
                if not isinstance(s, str):
                    continue
                if s not in uf:
                    uf[s] = s
                if prev is not None:
                    a = ufind(prev)
                    b = ufind(s)
                    if a != b:
                        uf[a] = b
                prev = s

    gcache = {}

    def gkey(s):
        g = gcache.get(s)
        if g is None:
            g = ufind(s) if s in uf else s
            gcache[s] = g
        return g

    # ---------- validation ----------
    date_cache = {}

    def parse_date(s):
        if not isinstance(s, str) or len(s) != 10:
            return None
        if s in date_cache:
            return date_cache[s]
        res = None
        if s[4] == '-' and s[7] == '-':
            ys, ms, dd = s[0:4], s[5:7], s[8:10]
            ok = True
            for c in ys + ms + dd:
                if c not in _DIGITS:
                    ok = False
                    break
            if ok:
                y, m, d = int(ys), int(ms), int(dd)
                if 1900 <= y <= 2099:
                    try:
                        res = datetime.date(y, m, d).toordinal()
                    except ValueError:
                        res = None
        date_cache[s] = res
        return res

    def is_int(v):
        return isinstance(v, int) and not isinstance(v, bool)

    n_tr = len(trades)
    rejected = []
    valid = []
    for idx in range(n_tr):
        t = trades[idx]
        try:
            ds = t["date"]
            side = t["side"]
            sym = t["symbol"]
            qty = t["qty"]
            amt = t["amount"]
        except Exception:
            rejected.append(idx)
            continue
        o = parse_date(ds)
        if o is None:
            rejected.append(idx)
            continue
        if not isinstance(side, str) or (side != "BUY" and side != "SELL"):
            rejected.append(idx)
            continue
        if not isinstance(sym, str) or len(sym) == 0:
            rejected.append(idx)
            continue
        if not is_int(qty) or qty < 1:
            rejected.append(idx)
            continue
        if not is_int(amt) or amt < 0:
            rejected.append(idx)
            continue
        valid.append((o, idx, side == "BUY", sym, int(qty), int(amt)))
    valid.sort(key=lambda r: (r[0], r[1]))

    # ---------- lots ----------
    lacq = [0] * n_tr
    fq = [0] * n_tr
    fb = [0] * n_tr
    reps = [None] * n_tr
    rhead = [0] * n_tr
    lpos = [0] * n_tr
    buy_order = []
    group_lists = {}
    for (o, idx, isbuy, sym, qty, amt) in valid:
        if isbuy:
            lacq[idx] = o
            fq[idx] = qty
            fb[idx] = amt
            reps[idx] = []
            buy_order.append(idx)
            g = gkey(sym)
            lst = group_lists.get(g)
            if lst is None:
                lst = []
                group_lists[g] = lst
            lst.append(idx)

    pos_acq = []
    pos_lot = []
    gspan = {}
    for g, lst in group_lists.items():
        s = len(pos_lot)
        for lot in lst:
            lpos[lot] = len(pos_lot)
            pos_lot.append(lot)
            pos_acq.append(lacq[lot])
        gspan[g] = (s, len(pos_lot))
    nxt = list(range(len(pos_lot) + 1))

    def find(i):
        root = i
        while nxt[root] != root:
            root = nxt[root]
        while nxt[i] != root:
            nx_ = nxt[i]
            nxt[i] = root
            i = nx_
        return root

    ann_cache = {}

    def ann_ord(start):
        a = ann_cache.get(start)
        if a is None:
            d = datetime.date.fromordinal(start)
            if d.month == 2 and d.day == 29:
                a = datetime.date(d.year + 1, 3, 1).toordinal()
            else:
                a = datetime.date(d.year + 1, d.month, d.day).toordinal()
            ann_cache[start] = a
        return a

    # ---------- processing ----------
    held = {}
    queues = {}
    sym_span = {}
    sale_rows = {}
    tot_short = 0
    tot_long = 0
    tot_dis = 0

    for (o, idx, isbuy, sym, qty, amt) in valid:
        if isbuy:
            held[sym] = held.get(sym, 0) + qty
            q = queues.get(sym)
            if q is None:
                q = deque()
                queues[sym] = q
            q.append(idx)
            continue
        h = held.get(sym, 0)
        if qty > h:
            rejected.append(idx)
            continue
        held[sym] = h - qty
        q = queues[sym]
        rem = qty
        rows = []
        last = -1
        while rem:
            lot = q[0]
            rl = reps[lot]
            hd = rhead[lot]
            acq = lacq[lot]
            nrl = len(rl)
            while rem and hd < nrl:
                pc = rl[hd]
                pq = pc[0]
                if pq <= rem:
                    rows.append((lot, pq, pc[1], acq - pc[2]))
                    rem -= pq
                    hd += 1
                else:
                    pb = pc[1]
                    tb = pb * rem // pq
                    rows.append((lot, rem, tb, acq - pc[2]))
                    pc[0] = pq - rem
                    pc[1] = pb - tb
                    rem = 0
            rhead[lot] = hd
            if rem:
                pq = fq[lot]
                if pq:
                    if pq <= rem:
                        rows.append((lot, pq, fb[lot], acq))
                        rem -= pq
                        fq[lot] = 0
                        fb[lot] = 0
                        p_ = lpos[lot]
                        nxt[p_] = p_ + 1
                    else:
                        pb = fb[lot]
                        tb = pb * rem // pq
                        rows.append((lot, rem, tb, acq))
                        fq[lot] = pq - rem
                        fb[lot] = pb - tb
                        rem = 0
            last = lot
            if rhead[lot] >= len(rl) and fq[lot] == 0:
                q.popleft()
                reps[lot] = []
                rhead[lot] = 0

        span = sym_span.get(sym)
        if span is None:
            span = gspan[gkey(sym)]
            sym_span[sym] = span
        gs, ge = span

        R = amt
        Q = qty
        out = []
        for (lot, n, b, start) in rows:
            p = R * n // Q
            R -= p
            Q -= n
            gain = p - b
            hdays = o - start
            D = 0
            if gain < 0:
                L = -gain
                need = n
                lo = bisect_left(pos_acq, o - 30, gs, ge)
                hi_date = o + 30
                pos = find(lo)
                chunks = []
                while need and pos < ge and pos_acq[pos] <= hi_date:
                    lot2 = pos_lot[pos]
                    if lot2 == last:
                        pos = find(pos + 1)
                        continue
                    f = fq[lot2]
                    if f <= need:
                        chunks.append((lot2, f))
                        need -= f
                        pos = find(pos + 1)
                    else:
                        chunks.append((lot2, need))
                        need = 0
                r = n - need
                if r:
                    D = L * r // n
                    R2 = D
                    Q2 = r
                    for lot2, c in chunks:
                        d = R2 * c // Q2
                        R2 -= d
                        Q2 -= c
                        f = fq[lot2]
                        B = fb[lot2]
                        sb = B * c // f
                        fq[lot2] = f - c
                        fb[lot2] = B - sb
                        reps[lot2].append([c, sb + d, hdays])
                        if f == c:
                            p_ = lpos[lot2]
                            nxt[p_] = p_ + 1
            if hdays > 366:
                term = "LONG"
            elif hdays < 365:
                term = "SHORT"
            else:
                term = "LONG" if o > ann_ord(start) else "SHORT"
            if term == "SHORT":
                tot_short += gain + D
            else:
                tot_long += gain + D
            tot_dis += D
            out.append({"sale": idx, "lot": lot, "qty": n, "proceeds": p,
                        "basis": b, "gain": gain, "disallowed": D, "term": term})
        sale_rows[idx] = out

    realized = []
    for i in sorted(sale_rows):
        realized.extend(sale_rows[i])

    open_lots = []
    for lot in buy_order:
        rl = reps[lot]
        for k in range(rhead[lot], len(rl)):
            pc = rl[k]
            if pc[0] > 0:
                open_lots.append({"lot": lot, "qty": pc[0], "basis": pc[1],
                                  "carried_days": pc[2]})
        if fq[lot] > 0:
            open_lots.append({"lot": lot, "qty": fq[lot], "basis": fb[lot],
                              "carried_days": 0})

    rejected.sort()
    return {"realized": realized,
            "open_lots": open_lots,
            "rejected": rejected,
            "totals": {"short_term": tot_short, "long_term": tot_long,
                       "disallowed": tot_dis}}