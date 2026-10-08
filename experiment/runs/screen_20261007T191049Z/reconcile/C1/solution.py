import re
import heapq
from bisect import bisect_left, bisect_right
from datetime import date as _date

_WORD_RE = re.compile(r'[A-Za-z0-9._-]+')
_DIG_RE = re.compile(r'[0-9]+')
_DIGITS = frozenset('0123456789')


def _strip_zeros(mo):
    s = mo.group().lstrip('0')
    return s if s else '0'


def _tokens(s):
    out = []
    for run in _WORD_RE.findall(s):
        t = run.replace('-', '').replace('_', '').replace('.', '')
        if not t:
            continue
        t = t.upper()
        if '0' in t:
            t = _DIG_RE.sub(_strip_zeros, t)
        out.append(t)
    return out


def _parse_date(s):
    if not isinstance(s, str) or len(s) != 10:
        return None
    if s[4] != '-' or s[7] != '-':
        return None
    for k in (0, 1, 2, 3, 5, 6, 8, 9):
        if s[k] not in _DIGITS:
            return None
    y = int(s[0:4])
    mo = int(s[5:7])
    d = int(s[8:10])
    if y < 1:
        return None
    try:
        return _date(y, mo, d).toordinal()
    except ValueError:
        return None


def _validate(records, extra):
    parsed = []
    for r in records:
        rec = None
        if isinstance(r, dict) and 'id' in r and 'date' in r and 'amount' in r:
            ok = True
            for k in extra:
                if k not in r:
                    ok = False
                    break
            if ok:
                rid = r['id']
                if isinstance(rid, str) and rid != '':
                    o = _parse_date(r['date'])
                    if o is not None:
                        a = r['amount']
                        if isinstance(a, int) and not isinstance(a, bool) and a != 0:
                            vals = tuple(r[k] for k in extra)
                            if all(isinstance(v, str) for v in vals):
                                rec = (rid, o, a, vals)
        parsed.append(rec)
    counts = {}
    for rec in parsed:
        if rec is not None:
            counts[rec[0]] = counts.get(rec[0], 0) + 1
    for p in range(len(parsed)):
        rec = parsed[p]
        if rec is not None and counts[rec[0]] > 1:
            parsed[p] = None
    return parsed


def reconcile(ledger, bank, params):
    W = int(params["days"])
    F = int(params["fee_cents"])

    Lp = _validate(ledger, ("ref", "party"))
    Bp = _validate(bank, ("text",))
    inv_l = [p for p, r in enumerate(Lp) if r is None]
    inv_b = [p for p, r in enumerate(Bp) if r is None]

    e_id, e_ord, e_amt, e_party, e_key = [], [], [], [], []
    for r in Lp:
        if r is None:
            continue
        rid, o, a, (ref, party) = r
        e_id.append(rid)
        e_ord.append(o)
        e_amt.append(a)
        e_party.append(party)
        toks = _tokens(ref)
        e_key.append(toks[0] if len(toks) == 1 else None)
    n = len(e_id)

    keyset = set(k for k in e_key if k is not None)

    b_id, b_ord, b_amt = [], [], []
    tok_lists = {}
    for r in Bp:
        if r is None:
            continue
        rid, o, a, (text,) = r
        j = len(b_id)
        b_id.append(rid)
        b_ord.append(o)
        b_amt.append(a)
        if keyset:
            for tk in set(_tokens(text)):
                if tk in keyset:
                    lst = tok_lists.get(tk)
                    if lst is None:
                        tok_lists[tk] = [j]
                    else:
                        lst.append(j)
    m = len(b_id)

    tok_index = {}
    for tk, lst in tok_lists.items():
        lst.sort(key=b_ord.__getitem__)
        tok_index[tk] = ([b_ord[j] for j in lst], lst)

    me = [False] * n
    mb = [False] * m
    matches = []

    e_order = sorted(range(n), key=lambda i: (e_ord[i], e_id[i]))

    # ---------------- Pass 1: ref ----------------
    cands = []
    for i in range(n):
        key = e_key[i]
        if key is None:
            continue
        ent = tok_index.get(key)
        if ent is None:
            continue
        dates, lst = ent
        t = e_ord[i]
        a = e_amt[i]
        lo = bisect_left(dates, t - W)
        hi = bisect_right(dates, t + W)
        for q in range(lo, hi):
            j = lst[q]
            if b_amt[j] == a:
                dd = dates[q] - t
                if dd < 0:
                    dd = -dd
                cands.append((dd, t, e_id[i], b_id[j], i, j))
    cands.sort()
    for c in cands:
        i = c[4]
        j = c[5]
        if not me[i] and not mb[j]:
            me[i] = True
            mb[j] = True
            matches.append(("ref", (i,), (j,)))

    # ---------------- Pass 2: amount ----------------
    buckets = {}
    for j in range(m):
        if mb[j]:
            continue
        k2 = (b_amt[j], b_ord[j])
        bk = buckets.get(k2)
        if bk is None:
            buckets[k2] = [0, [j]]
        else:
            bk[1].append(j)
    amt_dates = {}
    for (a, o), bk in buckets.items():
        if len(bk[1]) > 1:
            bk[1].sort(key=b_id.__getitem__)
        lst = amt_dates.get(a)
        if lst is None:
            amt_dates[a] = [o]
        else:
            lst.append(o)
    for v in amt_dates.values():
        v.sort()
    levels = [[] for _ in range(W + 1)]
    for i in e_order:
        if me[i]:
            continue
        ds = amt_dates.get(e_amt[i])
        if ds is None:
            continue
        t = e_ord[i]
        lo = bisect_left(ds, t - W)
        hi = bisect_right(ds, t + W)
        for q in range(lo, hi):
            off = ds[q] - t
            if off < 0:
                off = -off
            lv = levels[off]
            if not lv or lv[-1] != i:
                lv.append(i)
    for d in range(W + 1):
        for i in levels[d]:
            if me[i]:
                continue
            a = e_amt[i]
            t = e_ord[i]
            best = -1
            for dt in ((t - d, t + d) if d else (t,)):
                bk = buckets.get((a, dt))
                if bk is None:
                    continue
                lst = bk[1]
                p = bk[0]
                L = len(lst)
                while p < L and mb[lst[p]]:
                    p += 1
                bk[0] = p
                if p < L:
                    j = lst[p]
                    if best < 0 or b_id[j] < b_id[best]:
                        best = j
            if best >= 0:
                me[i] = True
                mb[best] = True
                matches.append(("amount", (i,), (best,)))

    # ---------------- Pass 3: multi_ledger ----------------
    l3 = [j for j in range(m) if not mb[j]]
    if l3 and n:
        l3.sort(key=lambda j: (b_ord[j], b_id[j]))
        all_d = sorted(set(b_ord[j] for j in l3))
        nd = len(all_d)
        amt_ld = {}
        for j in l3:
            lst = amt_ld.get(b_amt[j])
            if lst is None:
                amt_ld[b_amt[j]] = [b_ord[j]]
            else:
                lst.append(b_ord[j])
        for v in amt_ld.values():
            v.sort()
        parties = {}
        for i in range(n):
            if me[i]:
                continue
            pt = e_party[i]
            if not pt:
                continue
            t = e_ord[i]
            q = bisect_left(all_d, t - W)
            if q < nd and all_d[q] <= t + W:
                lst = parties.get(pt)
                if lst is None:
                    parties[pt] = [i]
                else:
                    lst.append(i)
        pair_g = {}
        trip_g = {}
        W2 = 2 * W
        for mem in parties.values():
            k = len(mem)
            if k < 2:
                continue
            mem.sort(key=lambda i: (e_ord[i], e_id[i]))
            ords = [e_ord[i] for i in mem]
            amts = [e_amt[i] for i in mem]
            ids = [e_id[i] for i in mem]
            for p in range(k - 1):
                dp = ords[p]
                ap = amts[p]
                end = bisect_right(ords, dp + W2, p + 1)
                if end - p < 2:
                    continue
                hiW = dp + W
                for q in range(p + 1, end):
                    dq = ords[q]
                    s2 = ap + amts[q]
                    lst = amt_ld.get(s2)
                    if lst is not None:
                        x = bisect_left(lst, dq - W)
                        if x < len(lst) and lst[x] <= hiW:
                            ip, iq = ids[p], ids[q]
                            idt = (ip, iq) if ip < iq else (iq, ip)
                            sub = pair_g.get(s2)
                            if sub is None:
                                sub = pair_g[s2] = {}
                            dk = (dp, dq)
                            g = sub.get(dk)
                            item = (idt, (mem[p], mem[q]))
                            if g is None:
                                sub[dk] = [item]
                            else:
                                g.append(item)
                    for r in range(q + 1, end):
                        s3 = s2 + amts[r]
                        lst = amt_ld.get(s3)
                        if lst is not None:
                            dr = ords[r]
                            x = bisect_left(lst, dr - W)
                            if x < len(lst) and lst[x] <= hiW:
                                idt = tuple(sorted((ids[p], ids[q], ids[r])))
                                sub = trip_g.get(s3)
                                if sub is None:
                                    sub = trip_g[s3] = {}
                                dk = (dp, dq, dr)
                                g = sub.get(dk)
                                item = (idt, (mem[p], mem[q], mem[r]))
                                if g is None:
                                    sub[dk] = [item]
                                else:
                                    g.append(item)

        def build(gd):
            res = {}
            for s, sub in gd.items():
                arr = []
                for dk, gl in sub.items():
                    if len(gl) > 1:
                        gl.sort()
                    arr.append([dk[0], dk[-1], dk, gl, 0])
                arr.sort(key=lambda x: x[0])
                res[s] = [0, arr]
            return res

        pair_idx = build(pair_g)
        trip_idx = build(trip_g)
        if pair_idx or trip_idx:
            for j in l3:
                A = b_amt[j]
                t = b_ord[j]
                lo_d = t - W
                hi_d = t + W
                chosen = None
                for gidx in (pair_idx, trip_idx):
                    ent = gidx.get(A)
                    if ent is None:
                        continue
                    arr = ent[1]
                    st = ent[0]
                    na = len(arr)
                    while st < na and arr[st][0] < lo_d:
                        st += 1
                    ent[0] = st
                    best_key = None
                    best_mem = None
                    x = st
                    while x < na:
                        sb = arr[x]
                        x += 1
                        if sb[0] > hi_d:
                            break
                        if sb[1] > hi_d:
                            continue
                        gl = sb[3]
                        p = sb[4]
                        ng = len(gl)
                        while p < ng:
                            for e in gl[p][1]:
                                if me[e]:
                                    break
                            else:
                                break
                            p += 1
                        sb[4] = p
                        if p >= ng:
                            continue
                        cost = 0
                        for dd in sb[2]:
                            cost += (dd - t) if dd >= t else (t - dd)
                        key = (cost, gl[p][0])
                        if best_key is None or key < best_key:
                            best_key = key
                            best_mem = gl[p][1]
                    if best_mem is not None:
                        chosen = best_mem
                        break
                if chosen is not None:
                    mb[j] = True
                    for e in chosen:
                        me[e] = True
                    matches.append(("multi_ledger", chosen, (j,)))

    # ---------------- Pass 4: multi_bank ----------------
    for i in e_order:
        if me[i]:
            continue
        key = e_key[i]
        if key is None:
            continue
        ent = tok_index.get(key)
        if ent is None:
            continue
        dates, lst = ent
        t = e_ord[i]
        lo = bisect_left(dates, t - W)
        hi = bisect_right(dates, t + W)
        if hi - lo < 2:
            continue
        C = [lst[q] for q in range(lo, hi) if not mb[lst[q]]]
        k = len(C)
        if k < 2:
            continue
        target = e_amt[i]
        ca = [b_amt[j] for j in C]
        cd = [abs(b_ord[j] - t) for j in C]
        cid = [b_id[j] for j in C]
        best_key = None
        best = None
        for x in range(k - 1):
            need = target - ca[x]
            for y in range(x + 1, k):
                if ca[y] == need:
                    ix, iy = cid[x], cid[y]
                    ids = (ix, iy) if ix < iy else (iy, ix)
                    kk = (cd[x] + cd[y], ids)
                    if best_key is None or kk < best_key:
                        best_key = kk
                        best = (C[x], C[y])
        if best is None and k >= 3:
            pos = {}
            for z in range(k):
                pl = pos.get(ca[z])
                if pl is None:
                    pos[ca[z]] = [z]
                else:
                    pl.append(z)
            for x in range(k - 2):
                for y in range(x + 1, k - 1):
                    zs = pos.get(target - ca[x] - ca[y])
                    if zs is None:
                        continue
                    for z in zs:
                        if z > y:
                            ids = tuple(sorted((cid[x], cid[y], cid[z])))
                            kk = (cd[x] + cd[y] + cd[z], ids)
                            if best_key is None or kk < best_key:
                                best_key = kk
                                best = (C[x], C[y], C[z])
        if best is not None:
            me[i] = True
            for j in best:
                mb[j] = True
            matches.append(("multi_bank", (i,), best))

    # ---------------- Pass 5: fee ----------------
    if F > 0 and n and m:
        per_date = {}
        for j in range(m):
            if mb[j]:
                continue
            dd = per_date.get(b_ord[j])
            if dd is None:
                dd = per_date[b_ord[j]] = {}
            lst = dd.get(b_amt[j])
            if lst is None:
                dd[b_amt[j]] = [j]
            else:
                lst.append(j)
        dstruct = {}
        amtset = set()
        for o, dd in per_date.items():
            amts = sorted(dd)
            amtset.update(amts)
            bks = []
            for a in amts:
                l = dd[a]
                if len(l) > 1:
                    l.sort(key=b_id.__getitem__)
                bks.append(l)
            dstruct[o] = (amts, bks, [0] * len(amts), list(range(len(amts))))
        all_amts = sorted(amtset)

        def query(o, lo, hi):
            st = dstruct.get(o)
            if st is None:
                return None
            amts, bks, ptrs, par = st
            jx = bisect_right(amts, hi) - 1
            while jx >= 0:
                r = jx
                while r >= 0 and par[r] != r:
                    r = par[r]
                while jx != r:
                    nx = par[jx]
                    par[jx] = r
                    jx = nx
                if r < 0 or amts[r] < lo:
                    return None
                lst = bks[r]
                p = ptrs[r]
                L = len(lst)
                while p < L and mb[lst[p]]:
                    p += 1
                ptrs[r] = p
                if p < L:
                    return amts[r], lst[p]
                par[r] = r - 1
                jx = r - 1
            return None

        def bounds(a):
            if a > 0:
                lo = a - F
                if lo < 1:
                    lo = 1
            else:
                lo = a - F
            return lo, a - 1

        def compute(i, d0):
            a = e_amt[i]
            lo, hi = bounds(a)
            if lo > hi:
                return None
            t = e_ord[i]
            for d in range(d0, W + 1):
                best = None
                for dt in ((t - d, t + d) if d else (t,)):
                    r = query(dt, lo, hi)
                    if r is not None:
                        cand = (a - r[0], b_id[r[1]], r[1])
                        if best is None or cand < best:
                            best = cand
                if best is not None:
                    return (d, best[0], t, e_id[i], best[1], i, best[2])
            return None

        heap = []
        for i in range(n):
            if me[i]:
                continue
            lo, hi = bounds(e_amt[i])
            if lo > hi:
                continue
            kq = bisect_right(all_amts, hi)
            if kq == 0 or all_amts[kq - 1] < lo:
                continue
            r = compute(i, 0)
            if r is not None:
                heap.append(r)
        heapq.heapify(heap)
        while heap:
            item = heapq.heappop(heap)
            i = item[5]
            j = item[6]
            if me[i]:
                continue
            if mb[j]:
                r = compute(i, item[0])
                if r is not None:
                    heapq.heappush(heap, r)
                continue
            me[i] = True
            mb[j] = True
            matches.append(("fee", (i,), (j,)))

    # ---------------- Output ----------------
    out_matches = []
    for typ, es, bs in matches:
        out_matches.append({
            "type": typ,
            "ledger": sorted(e_id[i] for i in es),
            "bank": sorted(b_id[j] for j in bs),
            "difference": sum(b_amt[j] for j in bs) - sum(e_amt[i] for i in es),
        })
    return {
        "matches": out_matches,
        "unmatched_ledger": [e_id[i] for i in range(n) if not me[i]],
        "unmatched_bank": [b_id[j] for j in range(m) if not mb[j]],
        "invalid": {"ledger": inv_l, "bank": inv_b},
    }