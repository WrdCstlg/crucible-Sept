from bisect import bisect_left, bisect_right, insort
from datetime import date as _date

_DIGITS = frozenset("0123456789")
_STAFF_KEYS = ("id", "skills", "max_minutes_week", "unavailable", "senior")
_SHIFT_KEYS = ("id", "start", "end", "skill", "need", "needs_senior")


def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def _date_ord(s):
    if not isinstance(s, str) or len(s) != 10:
        return None
    if s[4] != "-" or s[7] != "-":
        return None
    for p in (0, 1, 2, 3, 5, 6, 8, 9):
        if s[p] not in _DIGITS:
            return None
    y = int(s[0:4])
    m = int(s[5:7])
    d = int(s[8:10])
    if y < 1:
        return None
    try:
        return _date(y, m, d).toordinal()
    except ValueError:
        return None


def _ts_min(s):
    if not isinstance(s, str) or len(s) != 16:
        return None
    if s[10] != " " or s[13] != ":":
        return None
    for p in (11, 12, 14, 15):
        if s[p] not in _DIGITS:
            return None
    o = _date_ord(s[:10])
    if o is None:
        return None
    h = int(s[11:13])
    mi = int(s[14:16])
    if h > 23 or mi > 59:
        return None
    return o * 1440 + h * 60 + mi


def _check_staff(rec):
    if not isinstance(rec, dict):
        return None
    for k in _STAFF_KEYS:
        if k not in rec:
            return None
    sid = rec["id"]
    if not isinstance(sid, str) or len(sid) == 0:
        return None
    skills = rec["skills"]
    if not isinstance(skills, list):
        return None
    for x in skills:
        if not isinstance(x, str):
            return None
    mm = rec["max_minutes_week"]
    if not _is_int(mm) or mm < 0:
        return None
    un = rec["unavailable"]
    if not isinstance(un, list):
        return None
    uo = set()
    for x in un:
        o = _date_ord(x)
        if o is None:
            return None
        uo.add(o)
    sen = rec["senior"]
    if not isinstance(sen, bool):
        return None
    return (sid, frozenset(skills), int(mm), frozenset(uo), bool(sen))


def _check_shift(rec):
    if not isinstance(rec, dict):
        return None
    for k in _SHIFT_KEYS:
        if k not in rec:
            return None
    sid = rec["id"]
    if not isinstance(sid, str) or len(sid) == 0:
        return None
    st = _ts_min(rec["start"])
    en = _ts_min(rec["end"])
    if st is None or en is None or en <= st or en - st > 1440:
        return None
    skill = rec["skill"]
    if not isinstance(skill, str):
        return None
    need = rec["need"]
    if not _is_int(need) or need < 1:
        return None
    ns = rec["needs_senior"]
    if not isinstance(ns, bool):
        return None
    return (sid, st, en, skill, int(need), bool(ns))


def make_roster(staff, shifts, rules):
    # ---------------- validation ----------------
    ign_staff = []
    cand = []
    for idx, rec in enumerate(staff):
        c = _check_staff(rec)
        if c is None:
            ign_staff.append(idx)
        else:
            cand.append((idx, c))
    cnt = {}
    for _, c in cand:
        cnt[c[0]] = cnt.get(c[0], 0) + 1
    vstaff = []
    for idx, c in cand:
        if cnt[c[0]] > 1:
            ign_staff.append(idx)
        else:
            vstaff.append(c)
    ign_staff.sort()

    ign_shifts = []
    cand = []
    for idx, rec in enumerate(shifts):
        c = _check_shift(rec)
        if c is None:
            ign_shifts.append(idx)
        else:
            cand.append((idx, c))
    cnt = {}
    for _, c in cand:
        cnt[c[0]] = cnt.get(c[0], 0) + 1
    vshifts = []
    for idx, c in cand:
        if cnt[c[0]] > 1:
            ign_shifts.append(idx)
        else:
            vshifts.append(c)
    ign_shifts.sort()

    # ---------------- staff data ----------------
    vstaff.sort(key=lambda c: c[0])
    N = len(vstaff)
    ids = [c[0] for c in vstaff]
    rank_of = {sid: r for r, sid in enumerate(ids)}
    maxm = [c[2] for c in vstaff]
    unav = [c[3] if c[3] else None for c in vstaff]
    senior = [c[4] for c in vstaff]
    skills_of = [tuple(c[1]) for c in vstaff]

    skill_ranks = {}
    for r in range(N):
        for k in skills_of[r]:
            lst = skill_ranks.get(k)
            if lst is None:
                skill_ranks[k] = [r]
            else:
                lst.append(r)
    skill_minmax = {}
    maxsr = {}
    for k, holders in skill_ranks.items():
        skill_minmax[k] = min(maxm[r] for r in holders)
        ms = -1
        for r in holders:
            if senior[r]:
                ms = r
        maxsr[k] = ms

    forb = [None] * N
    for pair in rules["forbidden_pairs"]:
        a, b = pair[0], pair[1]
        if a == b:
            continue
        ra = rank_of.get(a)
        rb = rank_of.get(b)
        if ra is None or rb is None or ra == rb:
            continue
        if forb[ra] is None:
            forb[ra] = set()
        if forb[rb] is None:
            forb[rb] = set()
        forb[ra].add(rb)
        forb[rb].add(ra)

    rest = rules["min_rest_minutes"]
    maxc = rules["max_consecutive_days"]

    # ---------------- shift data ----------------
    nsh = len(vshifts)
    sh_id = [c[0] for c in vshifts]
    sh_start = [c[1] for c in vshifts]
    sh_end = [c[2] for c in vshifts]
    sh_skill = [c[3] for c in vshifts]
    sh_need = [c[4] for c in vshifts]
    sh_sen = [c[5] for c in vshifts]
    sh_len = [sh_end[i] - sh_start[i] for i in range(nsh)]
    sh_d1 = [sh_start[i] // 1440 for i in range(nsh)]
    sh_d2 = [(sh_end[i] - 1) // 1440 for i in range(nsh)]
    sh_week = [(sh_d1[i] - 1) // 7 for i in range(nsh)]

    def result(ok, seats):
        mins = [0] * N
        assignments = {}
        if ok:
            for si in range(nsh):
                people = seats[si]
                L = sh_len[si]
                for r in people:
                    mins[r] += L
                assignments[sh_id[si]] = [ids[r] for r in people]
        return {
            "ok": ok,
            "assignments": assignments,
            "minutes": {ids[r]: mins[r] for r in range(N)},
            "ignored": {"staff": ign_staff, "shifts": ign_shifts},
        }

    if nsh == 0:
        return result(True, [])

    # ---------------- static infeasibility check (pruning only) ----------------
    st_noua = {}
    st_ua = {}
    st_sen_noua = {}
    st_sen_ua = {}
    for k, holders in skill_ranks.items():
        a = []
        b = []
        sm = -1
        sb = []
        for r in holders:
            if unav[r] is None:
                a.append(maxm[r])
                if senior[r] and maxm[r] > sm:
                    sm = maxm[r]
            else:
                b.append(r)
                if senior[r]:
                    sb.append(r)
        a.sort()
        st_noua[k] = a
        st_ua[k] = b
        st_sen_noua[k] = sm
        st_sen_ua[k] = sb

    for si in range(nsh):
        k = sh_skill[si]
        need = sh_need[si]
        L = sh_len[si]
        d1 = sh_d1[si]
        d2 = sh_d2[si]
        holders = skill_ranks.get(k)
        if holders is None or len(holders) < need:
            return result(False, None)
        if d1 != d2 and maxc < 2:
            return result(False, None)
        a = st_noua[k]
        c = len(a) - bisect_left(a, L)
        if c < need:
            for r in st_ua[k]:
                if maxm[r] >= L:
                    ua = unav[r]
                    if d1 not in ua and d2 not in ua:
                        c += 1
                        if c >= need:
                            break
            if c < need:
                return result(False, None)
        if sh_sen[si]:
            if st_sen_noua[k] < L:
                fnd = False
                for r in st_sen_ua[k]:
                    if maxm[r] >= L:
                        ua = unav[r]
                        if d1 not in ua and d2 not in ua:
                            fnd = True
                            break
                if not fnd:
                    return result(False, None)

    # ---------------- slots ----------------
    order = sorted(range(nsh), key=lambda i: (sh_start[i], sh_end[i], sh_id[i]))
    slot_si = []
    slot_seat = []
    for si in order:
        for kk in range(sh_need[si]):
            slot_si.append(si)
            slot_seat.append(kk)
    nslots = len(slot_si)

    minlen = {}
    for si in range(nsh):
        w = sh_week[si]
        d = minlen.get(w)
        if d is None:
            d = {}
            minlen[w] = d
        k = sh_skill[si]
        cur = d.get(k)
        if cur is None or sh_len[si] < cur:
            d[k] = sh_len[si]

    # ---------------- search state ----------------
    NEG = -(1 << 62)
    last_end = [NEG] * N
    last_date = [-10] * N
    last_run = [0] * N
    seats = [[] for _ in range(nsh)]
    scnt = [0] * nsh
    lastkey = [-1] * nslots
    sv_r = [0] * nslots
    sv_le = [0] * nslots
    sv_ld = [0] * nslots
    sv_lr = [0] * nslots
    sv_w = [0] * nslots
    weekW = {}
    cache = {}

    def build(w):
        if len(cache) >= 8:
            cache.clear()
        wd = weekW.get(w)
        ws = {}
        for k, ml in minlen[w].items():
            holders = skill_ranks.get(k)
            if not holders:
                ws[k] = []
                continue
            if not wd:
                if ml <= skill_minmax[k]:
                    ws[k] = holders[:]
                else:
                    ws[k] = [r for r in holders if maxm[r] >= ml]
            else:
                lst = []
                for r in holders:
                    W = wd.get(r, 0)
                    if maxm[r] - W >= ml:
                        lst.append(W * N + r)
                lst.sort()
                ws[k] = lst
        cache[w] = ws
        return ws

    def update(w, r, fromW, toW):
        ws = cache.get(w)
        if ws is None:
            return
        mlw = minlen[w]
        mx = maxm[r]
        for k in skills_of[r]:
            lst = ws.get(k)
            if lst is None:
                continue
            ml = mlw[k]
            if mx - fromW >= ml:
                fk = fromW * N + r
                p = bisect_left(lst, fk)
                del lst[p]
            if mx - toW >= ml:
                insort(lst, toW * N + r)

    # ---------------- depth-first search ----------------
    i = 0
    ok = False
    while True:
        if i == nslots:
            ok = True
            break
        si = slot_si[i]
        k = slot_seat[i]
        w = sh_week[si]
        ws = cache.get(w)
        if ws is None:
            ws = build(w)
        skill = sh_skill[si]
        lst = ws[skill]
        seats_si = seats[si]
        lb = seats_si[-1] if k else -1
        s_start = sh_start[si]
        s_len = sh_len[si]
        d1 = sh_d1[si]
        d2 = sh_d2[si]
        span = d2 - d1
        need = sh_need[si]
        is_last = (k == need - 1)
        rem = need - 1 - k
        sen_needed = sh_sen[si] and scnt[si] == 0
        msr = maxsr.get(skill, -1)
        holders = skill_ranks[skill]
        nh = len(holders)
        nl = len(lst)
        j = bisect_right(lst, lastkey[i])
        found = False
        key = -1
        W = 0
        r = -1
        run = 0
        while j < nl:
            key = lst[j]
            W, r = divmod(key, N)
            if r <= lb:
                j = bisect_right(lst, key - r + lb, j + 1)
                continue
            j += 1
            if W + s_len > maxm[r]:
                continue
            if sen_needed and not senior[r] and (is_last or msr < r):
                continue
            if last_end[r] + rest > s_start:
                continue
            ua = unav[r]
            if ua is not None and (d1 in ua or d2 in ua):
                continue
            ld = last_date[r]
            if ld == d1:
                run = last_run[r] + span
            elif ld == d1 - 1:
                run = last_run[r] + 1 + span
            else:
                run = 1 + span
            if run > maxc:
                continue
            if k:
                fb = forb[r]
                if fb is not None and not fb.isdisjoint(seats_si):
                    continue
            if rem > 0 and nh - bisect_right(holders, r) < rem:
                continue
            found = True
            break

        if not found:
            lastkey[i] = -1
            i -= 1
            if i < 0:
                break
            # undo slot i
            r2 = sv_r[i]
            si2 = slot_si[i]
            seats[si2].pop()
            if senior[r2]:
                scnt[si2] -= 1
            last_end[r2] = sv_le[i]
            last_date[r2] = sv_ld[i]
            last_run[r2] = sv_lr[i]
            oldW = sv_w[i]
            newW = oldW + sh_len[si2]
            w2 = sh_week[si2]
            wd = weekW[w2]
            if oldW:
                wd[r2] = oldW
            else:
                del wd[r2]
            update(w2, r2, newW, oldW)
            continue

        # place candidate r in slot i
        lastkey[i] = key
        seats_si.append(r)
        if senior[r]:
            scnt[si] += 1
        sv_r[i] = r
        sv_le[i] = last_end[r]
        sv_ld[i] = last_date[r]
        sv_lr[i] = last_run[r]
        sv_w[i] = W
        last_end[r] = sh_end[si]
        last_date[r] = d2
        last_run[r] = run
        wd = weekW.get(w)
        if wd is None:
            wd = {}
            weekW[w] = wd
        newW = W + s_len
        wd[r] = newW
        update(w, r, W, newW)
        i += 1

    if ok:
        return result(True, seats)
    return result(False, None)