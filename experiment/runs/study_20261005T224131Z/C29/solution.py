from bisect import bisect_left, bisect_right
from operator import itemgetter

_EVENTS = frozenset(('OPEN', 'PRIORITY', 'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'))
_LIMITS = {'P1': 240, 'P2': 480, 'P3': 1440, 'P4': 2400}

_NOT, _RUN, _PAU, _CLO = 0, 1, 2, 3
_STATUS = {_RUN: 'running', _PAU: 'paused', _CLO: 'closed'}


def _to_int(s):
    s = s.lstrip('0')
    if not s:
        return 0
    try:
        return int(s)
    except ValueError:
        v = 0
        for i in range(0, len(s), 1000):
            chunk = s[i:i + 1000]
            v = v * (10 ** len(chunk)) + int(chunk)
        return v


def compute_sla(stream):
    tickets = {}
    holidays = set()
    now = None

    for raw in stream:
        if not isinstance(raw, str):
            continue
        parts = raw.strip().split(',')
        n = len(parts)
        if n != 3 and n != 4:
            continue
        f1 = parts[0].strip()
        if not f1 or not (f1.isascii() and f1.isdigit()):
            continue
        tid = parts[1].strip()
        if not tid:
            continue
        ev = parts[2].strip()
        if ev not in _EVENTS:
            continue
        if ev == 'OPEN' or ev == 'PRIORITY':
            if n != 4:
                continue
            p = parts[3].strip()
            if p not in _LIMITS:
                continue
        else:
            if n != 3:
                continue
            p = None
        if ev == 'HOLIDAY':
            if tid != '*':
                continue
        elif tid == '*':
            continue
        m = _to_int(f1)
        if ev == 'HOLIDAY':
            holidays.add(m // 1440)
            continue
        if now is None or m > now:
            now = m
        lst = tickets.get(tid)
        if lst is None:
            lst = []
            tickets[tid] = lst
        lst.append((m, ev, p))

    if now is None:
        return []

    # Holiday structures: weekday-index of each weekday holiday.
    hw = sorted({(d // 7) * 5 + (d % 7) for d in holidays if d % 7 < 5})
    fmiss = [h - i for i, h in enumerate(hw)]
    hol_set = holidays

    def B(t):
        """Number of business minutes in [0, t)."""
        d, rem = divmod(t, 1440)
        w, dd = divmod(d, 7)
        wd = w * 5 + (dd if dd < 5 else 5)
        full = wd - bisect_left(hw, wd)
        res = full * 480
        if dd < 5 and d not in hol_set:
            pp = rem - 540
            if pp > 0:
                res += pp if pp < 480 else 480
        return res

    def first_reach(T):
        """Smallest y with B(y) >= T (T >= 1)."""
        q, r = divmod(T - 1, 480)
        c = bisect_right(fmiss, q)
        k = q + c
        w, dd = divmod(k, 5)
        D = w * 7 + dd
        return D * 1440 + 540 + r + 1

    results = []
    key0 = itemgetter(0)
    for tid in sorted(tickets):
        evs = tickets[tid]
        evs.sort(key=key0)
        state = _NOT
        prio = None
        used = 0
        breached_at = None
        opened = False
        cur_t = None
        b_cur = 0
        i = 0
        L = len(evs)
        while i < L:
            t = evs[i][0]
            b_t = None
            if cur_t is not None and state == _RUN:
                b_t = B(t)
                if breached_at is None:
                    T = b_cur + _LIMITS[prio] + 1 - used
                    if b_t >= T:
                        y = first_reach(T)
                        if y < t:
                            breached_at = y
                used += b_t - b_cur
            while i < L and evs[i][0] == t:
                _, ev, p = evs[i]
                i += 1
                if ev == 'OPEN':
                    if state == _NOT or state == _CLO:
                        state = _RUN
                        prio = p
                        used = 0
                        breached_at = None
                        opened = True
                elif ev == 'PRIORITY':
                    if state == _RUN or state == _PAU:
                        prio = p
                elif ev == 'PAUSE':
                    if state == _RUN:
                        state = _PAU
                elif ev == 'RESUME':
                    if state == _PAU:
                        state = _RUN
                elif ev == 'CLOSE':
                    if state == _RUN or state == _PAU:
                        state = _CLO
                elif ev == 'REOPEN':
                    if state == _CLO:
                        state = _RUN
            if state != _NOT and breached_at is None and used > _LIMITS[prio]:
                breached_at = t
            if state == _RUN:
                b_cur = b_t if b_t is not None else B(t)
            cur_t = t

        if not opened:
            continue

        if state == _RUN and cur_t < now:
            b_now = B(now)
            if breached_at is None:
                T = b_cur + _LIMITS[prio] + 1 - used
                if b_now >= T:
                    breached_at = first_reach(T)
            used += b_now - b_cur

        results.append({
            "ticket_id": tid,
            "priority": prio,
            "used_minutes": used,
            "breached": breached_at is not None,
            "breached_at": breached_at,
            "status": _STATUS[state],
        })

    return results