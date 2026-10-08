from datetime import date as _date
from bisect import bisect_left
from collections import deque

_DIGITS = frozenset("0123456789")


def _parse_date(s):
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return None
    for k in (0, 1, 2, 3, 5, 6, 8, 9):
        if s[k] not in _DIGITS:
            return None
    y = int(s[0:4])
    m = int(s[5:7])
    d = int(s[8:10])
    if y < 1900 or y > 2099:
        return None
    try:
        return _date(y, m, d).toordinal()
    except ValueError:
        return None


def compute_gains(trades, identical):
    n_tr = len(trades)
    rejected = []

    # ---------- identical groups ----------
    par = {}

    def gfind(x):
        root = x
        while par[root] != root:
            root = par[root]
        while par[x] != root:
            nx = par[x]
            par[x] = root
            x = nx
        return root

    for lst in identical:
        prev = None
        for s in lst:
            if s not in par:
                par[s] = s
            if prev is not None:
                a = gfind(prev)
                b = gfind(s)
                if a != b:
                    par[a] = b
            prev = s

    # ---------- validation ----------
    date_cache = {}
    valid = []
    lot_date = [0] * n_tr
    fresh_q = [0] * n_tr
    fresh_b = [0] * n_tr
    lot_qty = [0] * n_tr

    for i, tr in enumerate(trades):
        try:
            ds = tr["date"]
            side = tr["side"]
            sym = tr["symbol"]
            qty = tr["qty"]
            amt = tr["amount"]
        except Exception:
            rejected.append(i)
            continue
        if not isinstance(ds, str):
            rejected.append(i)
            continue
        if ds in date_cache:
            o = date_cache[ds]
        else:
            o = _parse_date(ds)
            date_cache[ds] = o
        if o is None:
            rejected.append(i)
            continue
        if not isinstance(side, str) or (side != "BUY" and side != "SELL"):
            rejected.append(i)
            continue
        if not isinstance(sym, str) or len(sym) == 0:
            rejected.append(i)
            continue
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
            rejected.append(i)
            continue
        if not isinstance(amt, int) or isinstance(amt, bool) or amt < 0:
            rejected.append(i)
            continue
        is_buy = (side == "BUY")
        valid.append((o, i, is_buy, sym, qty, amt))
        if is_buy:
            lot_date[i] = o
            fresh_q[i] = qty
            fresh_b[i] = amt
            lot_qty[i] = qty

    valid.sort(key=lambda r: (r[0], r[1]))

    # ---------- group layout ----------
    gkey_cache = {}
    group_lots = {}
    for rec in valid:
        if rec[2]:
            sym = rec[3]
            gk = gkey_cache.get(sym)
            if gk is None:
                gk = gfind(sym) if sym in par else sym
                gkey_cache[sym] = gk
            lst = group_lots.get(gk)
            if lst is None:
                lst = []
                group_lots[gk] = lst
            lst.append(rec[1])

    gdate = []
    glot = []
    gbounds = {}
    gp = [0] * n_tr
    BIG = 1 << 60
    for gk, lots in group_lots.items():
        gs = len(glot)
        for lot in lots:
            gp[lot] = len(glot)
            glot.append(lot)
            gdate.append(lot_date[lot])
        ge = len(glot)
        glot.append(-1)
        gdate.append(BIG)
        gbounds[gk] = (gs, ge)
    uf = list(range(len(glot)))

    def find(x):
        r = x
        while uf[r] != r:
            r = uf[r]
        while x != r:
            nx = uf[x]
            uf[x] = r
            x = nx
        return r

    ann_cache = {}

    def term_of(t, hd):
        if hd > 366:
            return "LONG"
        hs = t - hd
        ann = ann_cache.get(hs)
        if ann is None:
            dd = _date.fromordinal(hs)
            if dd.month == 2 and dd.day == 29:
                ann = _date(dd.year + 1, 3, 1).toordinal()
            else:
                ann = _date(dd.year + 1, dd.month, dd.day).toordinal()
            ann_cache[hs] = ann
        return "LONG" if t > ann else "SHORT"

    # ---------- processing ----------
    rep = [None] * n_tr
    rep_head = [0] * n_tr
    held_cnt = {}
    held_dq = {}
    sales = []
    buy_order = []

    for (t, idx, is_buy, sym, qty, amt) in valid:
        if is_buy:
            dq = held_dq.get(sym)
            if dq is None:
                dq = deque()
                held_dq[sym] = dq
                held_cnt[sym] = 0
            dq.append(idx)
            held_cnt[sym] += qty
            buy_order.append(idx)
            continue

        hc = held_cnt.get(sym, 0)
        if qty > hc:
            rejected.append(idx)
            continue
        held_cnt[sym] = hc - qty
        dq = held_dq[sym]

        R = amt
        Q = qty
        need = qty
        rows = []
        loss = []
        drawn = []

        while need:
            lot = dq[0]
            drawn.append(lot)
            base = t - lot_date[lot]
            took = 0
            reps = rep[lot]
            if reps is not None:
                h = rep_head[lot]
                lr = len(reps)
                while need and h < lr:
                    pq, pb, pc = reps[h]
                    if pq <= need:
                        nn = pq
                        b = pb
                        h += 1
                    else:
                        nn = need
                        b = pb * nn // pq
                        reps[h] = (pq - nn, pb - b, pc)
                    need -= nn
                    took += nn
                    p = R * nn // Q
                    R -= p
                    Q -= nn
                    hd = base + pc
                    g = p - b
                    row = {"sale": idx, "lot": lot, "qty": nn, "proceeds": p,
                           "basis": b, "gain": g, "disallowed": 0,
                           "term": term_of(t, hd)}
                    rows.append(row)
                    if g < 0:
                        loss.append((row, nn, -g, hd))
                if h >= lr:
                    rep[lot] = None
                    rep_head[lot] = 0
                else:
                    rep_head[lot] = h
            if need:
                fq = fresh_q[lot]
                if fq:
                    fb = fresh_b[lot]
                    if fq <= need:
                        nn = fq
                        b = fb
                        fresh_q[lot] = 0
                        fresh_b[lot] = 0
                        x = gp[lot]
                        uf[x] = x + 1
                    else:
                        nn = need
                        b = fb * nn // fq
                        fresh_q[lot] = fq - nn
                        fresh_b[lot] = fb - b
                    need -= nn
                    took += nn
                    p = R * nn // Q
                    R -= p
                    Q -= nn
                    hd = base
                    g = p - b
                    row = {"sale": idx, "lot": lot, "qty": nn, "proceeds": p,
                           "basis": b, "gain": g, "disallowed": 0,
                           "term": term_of(t, hd)}
                    rows.append(row)
                    if g < 0:
                        loss.append((row, nn, -g, hd))
            rem = lot_qty[lot] - took
            lot_qty[lot] = rem
            if rem == 0:
                dq.popleft()

        if loss:
            drawn_set = set(drawn)
            gs, ge = gbounds[gkey_cache[sym]]
            lo = bisect_left(gdate, t - 30, gs, ge)
            hi_date = t + 30
            for (rd, nn, L, hd) in loss:
                pos = find(lo)
                needed = nn
                chunks = []
                while needed and pos < ge and gdate[pos] <= hi_date:
                    lot = glot[pos]
                    if lot in drawn_set:
                        pos = find(pos + 1)
                        continue
                    fq = fresh_q[lot]
                    if fq <= needed:
                        chunks.append((lot, fq))
                        needed -= fq
                        pos = find(pos + 1)
                    else:
                        chunks.append((lot, needed))
                        needed = 0
                r = nn - needed
                if r == 0:
                    continue
                D = L * r // nn
                rd["disallowed"] = D
                R2 = D
                Q2 = r
                for lot, c in chunks:
                    d = R2 * c // Q2
                    R2 -= d
                    Q2 -= c
                    fq = fresh_q[lot]
                    fb = fresh_b[lot]
                    tb = fb * c // fq
                    fresh_q[lot] = fq - c
                    fresh_b[lot] = fb - tb
                    if fq == c:
                        x = gp[lot]
                        uf[x] = x + 1
                    reps = rep[lot]
                    if reps is None:
                        rep[lot] = [(c, tb + d, hd)]
                        rep_head[lot] = 0
                    else:
                        reps.append((c, tb + d, hd))

        sales.append((idx, rows))

    # ---------- output ----------
    sales.sort(key=lambda x: x[0])
    realized = []
    st = 0
    lt = 0
    dis = 0
    for _, rows in sales:
        for row in rows:
            realized.append(row)
            v = row["gain"] + row["disallowed"]
            if row["term"] == "SHORT":
                st += v
            else:
                lt += v
            dis += row["disallowed"]

    open_lots = []
    for lot in buy_order:
        reps = rep[lot]
        if reps is not None:
            for h in range(rep_head[lot], len(reps)):
                pq, pb, pc = reps[h]
                if pq > 0:
                    open_lots.append({"lot": lot, "qty": pq, "basis": pb,
                                      "carried_days": pc})
        if fresh_q[lot]:
            open_lots.append({"lot": lot, "qty": fresh_q[lot],
                              "basis": fresh_b[lot], "carried_days": 0})

    rejected.sort()
    return {"realized": realized,
            "open_lots": open_lots,
            "rejected": rejected,
            "totals": {"short_term": st, "long_term": lt, "disallowed": dis}}