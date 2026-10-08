"""Reference for Problem 14 (bank reconciliation). Stdlib only; integer cents; never mutates its inputs.

Selection in every pass is defined by keys, so the efficient indexes below (by token, by amount, by date) give the
same answer as the literal "repeatedly take the smallest key" / "try every 2- and 3-subset" reading of the spec.
"""
import re
from bisect import bisect_left, bisect_right
from datetime import date

DIGITS = "0123456789"
WORD_RUN = re.compile(r"[A-Za-z0-9._-]+")
DIGIT_RUN = re.compile(r"[0-9]+")
JOINERS = str.maketrans("", "", "-_.")
LEDGER_FIELDS = ("id", "date", "amount", "ref", "party")
BANK_FIELDS = ("id", "date", "amount", "text")


def day_number(s):
    """Proleptic Gregorian day number of a strict YYYY-MM-DD string, or None."""
    if type(s) is not str or len(s) != 10 or s[4] != "-" or s[7] != "-":
        return None
    y, m, d = s[0:4], s[5:7], s[8:10]
    if not all(c in DIGITS for c in y + m + d):
        return None
    try:
        return date(int(y), int(m), int(d)).toordinal()
    except ValueError:
        return None


def _no_leading_zeros(match):
    return match.group().lstrip("0") or "0"


def tokens(s):
    out = []
    for run in WORD_RUN.findall(s):
        t = run.translate(JOINERS).upper()
        if t:
            out.append(DIGIT_RUN.sub(_no_leading_zeros, t))
    return out


def ref_key(ref):
    toks = tokens(ref)
    return toks[0] if len(toks) == 1 else None


def validate(records, fields):
    """Return (valid records as (index, record, day), sorted invalid indices)."""
    passed, bad = [], []
    for i, r in enumerate(records):
        if type(r) is not dict or any(k not in r for k in fields):
            bad.append(i)
            continue
        if type(r["id"]) is not str or r["id"] == "":
            bad.append(i)
            continue
        day = day_number(r["date"])
        if day is None:
            bad.append(i)
            continue
        if type(r["amount"]) is not int or r["amount"] == 0:
            bad.append(i)
            continue
        if any(type(r[k]) is not str for k in fields[3:]):
            bad.append(i)
            continue
        passed.append((i, r, day))
    count = {}
    for i, r, day in passed:
        count[r["id"]] = count.get(r["id"], 0) + 1
    good = []
    for i, r, day in passed:
        if count[r["id"]] > 1:
            bad.append(i)
        else:
            good.append((i, r, day))
    return good, sorted(bad)


def best_group(members, target):
    """members: list of (delta, id, amount, handle). Best 2- or 3-subset summing to target, or None.
    Order: fewest members, then smallest delta sum, then smallest sorted id list."""
    by_amount = {}
    for pos, m in enumerate(members):
        by_amount.setdefault(m[2], []).append(pos)
    best = None
    for i, a in enumerate(members):
        for j in by_amount.get(target - a[2], ()):
            if j > i:
                b = members[j]
                cand = (a[0] + b[0], sorted((a[1], b[1])), (a, b))
                if best is None or cand[:2] < best[:2]:
                    best = cand
    if best is not None:
        return best[2]
    n = len(members)
    for i in range(n):
        a = members[i]
        for j in range(i + 1, n):
            b = members[j]
            for k in by_amount.get(target - a[2] - b[2], ()):
                if k > j:
                    c = members[k]
                    cand = (a[0] + b[0] + c[0], sorted((a[1], b[1], c[1])), (a, b, c))
                    if best is None or cand[:2] < best[:2]:
                        best = cand
    return None if best is None else best[2]


def reconcile(ledger, bank, params):
    W, F = params["days"], params["fee_cents"]
    good_l, bad_l = validate(ledger, LEDGER_FIELDS)
    good_b, bad_b = validate(bank, BANK_FIELDS)

    # Ledger entry: [id, day, amount, key, party]; bank line: [id, day, amount, token set].
    L = [(r["id"], day, r["amount"], ref_key(r["ref"]), r["party"]) for i, r, day in good_l]
    B = [(r["id"], day, r["amount"], set(tokens(r["text"]))) for i, r, day in good_b]
    l_used = [False] * len(L)
    b_used = [False] * len(B)
    matches = []

    def record(kind, lis, bis):
        for li in lis:
            l_used[li] = True
        for bi in bis:
            b_used[bi] = True
        matches.append({"type": kind, "ledger": sorted(L[li][0] for li in lis),
                        "bank": sorted(B[bi][0] for bi in bis),
                        "difference": sum(B[bi][2] for bi in bis) - sum(L[li][2] for li in lis)})

    def take_pairs(kind, cands):
        cands.sort()
        for c in cands:
            li, bi = c[-2], c[-1]
            if not l_used[li] and not b_used[bi]:
                record(kind, [li], [bi])

    # Pass 1: reference.
    carriers = {}
    for bi, b in enumerate(B):
        for t in b[3]:
            carriers.setdefault(t, []).append(bi)
    cands = []
    for li, e in enumerate(L):
        if e[3] is None:
            continue
        for bi in carriers.get(e[3], ()):
            b = B[bi]
            if b[2] == e[2]:
                dd = abs(b[1] - e[1])
                if dd <= W:
                    cands.append((dd, e[1], e[0], b[0], li, bi))
    take_pairs("ref", cands)

    # Pass 2: exact amount.
    by_amount = {}
    for bi in sorted((bi for bi in range(len(B)) if not b_used[bi]), key=lambda bi: B[bi][1]):
        by_amount.setdefault(B[bi][2], []).append(bi)
    amount_days = {a: [B[bi][1] for bi in lst] for a, lst in by_amount.items()}
    cands = []
    for li, e in enumerate(L):
        if l_used[li] or e[2] not in by_amount:
            continue
        lst, days = by_amount[e[2]], amount_days[e[2]]
        for bi in lst[bisect_left(days, e[1] - W):bisect_right(days, e[1] + W)]:
            b = B[bi]
            cands.append((abs(b[1] - e[1]), e[1], e[0], b[0], li, bi))
    take_pairs("amount", cands)

    # Pass 3: one bank line = 2-3 ledger entries of one party.
    open_l = sorted((li for li in range(len(L)) if not l_used[li] and L[li][4] != ""), key=lambda li: L[li][1])
    open_l_days = [L[li][1] for li in open_l]
    for bi in sorted((bi for bi in range(len(B)) if not b_used[bi]), key=lambda bi: (B[bi][1], B[bi][0])):
        b = B[bi]
        parties = {}
        for li in open_l[bisect_left(open_l_days, b[1] - W):bisect_right(open_l_days, b[1] + W)]:
            if not l_used[li]:
                e = L[li]
                parties.setdefault(e[4], []).append((abs(e[1] - b[1]), e[0], e[2], li))
        best = None
        for members in parties.values():
            if len(members) >= 2:
                g = best_group(members, b[2])
                if g is not None:
                    cand = (len(g), sum(m[0] for m in g), sorted(m[1] for m in g), g)
                    if best is None or cand[:3] < best[:3]:
                        best = cand
        if best is not None:
            record("multi_ledger", [m[3] for m in best[3]], [bi])

    # Pass 4: 2-3 bank lines carrying one ledger entry's key = that entry.
    carriers = {}
    for bi in sorted((bi for bi in range(len(B)) if not b_used[bi]), key=lambda bi: B[bi][1]):
        for t in B[bi][3]:
            carriers.setdefault(t, []).append(bi)
    carrier_days = {t: [B[bi][1] for bi in lst] for t, lst in carriers.items()}
    for li in sorted((li for li in range(len(L)) if not l_used[li]), key=lambda li: (L[li][1], L[li][0])):
        e = L[li]
        if e[3] is None or e[3] not in carriers:
            continue
        lst, days = carriers[e[3]], carrier_days[e[3]]
        members = [(abs(B[bi][1] - e[1]), B[bi][0], B[bi][2], bi)
                   for bi in lst[bisect_left(days, e[1] - W):bisect_right(days, e[1] + W)] if not b_used[bi]]
        if len(members) >= 2:
            g = best_group(members, e[2])
            if g is not None:
                record("multi_bank", [li], [m[3] for m in g])

    # Pass 5: bank amount = ledger amount - fee, 1 <= fee <= F, same sign.
    open_b = sorted((B[bi][2], bi) for bi in range(len(B)) if not b_used[bi])
    open_b_amounts = [a for a, bi in open_b]
    cands = []
    if F >= 1:
        for li, e in enumerate(L):
            if l_used[li]:
                continue
            lo, hi = e[2] - F, e[2] - 1
            if e[2] > 0:
                lo = max(lo, 1)
            for amount, bi in open_b[bisect_left(open_b_amounts, lo):bisect_right(open_b_amounts, hi)]:
                b = B[bi]
                dd = abs(b[1] - e[1])
                if dd <= W:
                    cands.append((dd, e[2] - amount, e[1], e[0], b[0], li, bi))
    take_pairs("fee", cands)

    return {"matches": matches,
            "unmatched_ledger": [L[li][0] for li in range(len(L)) if not l_used[li]],
            "unmatched_bank": [B[bi][0] for bi in range(len(B)) if not b_used[bi]],
            "invalid": {"ledger": bad_l, "bank": bad_b}}
