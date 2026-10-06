import re
from bisect import bisect_left, bisect_right

_DIGITS_RE = re.compile(r'[0-9]+')
_EVENTS = frozenset(("OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"))
_LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}

_NOT_OPENED, _RUNNING, _PAUSED, _CLOSED = 0, 1, 2, 3
_STATUS_NAME = {_RUNNING: "running", _PAUSED: "paused", _CLOSED: "closed"}


def _to_int(s):
    s = s.lstrip('0')
    if not s:
        return 0
    try:
        return int(s)
    except ValueError:
        # Extremely long digit strings (int max str digits limit); parse in chunks.
        v = 0
        for k in range(0, len(s), 1000):
            c = s[k:k + 1000]
            v = v * (10 ** len(c)) + int(c)
        return v


def compute_sla(stream):
    events = []      # (minute, ticket_id, event, priority)
    hol_days = set()  # weekday holiday day numbers

    for line in stream:
        if not isinstance(line, str):
            continue
        parts = line.strip().split(',')
        n = len(parts)
        if n != 3 and n != 4:
            continue
        f1 = parts[0].strip()
        if not _DIGITS_RE.fullmatch(f1):
            continue
        tid = parts[1].strip()
        if not tid:
            continue
        ev = parts[2].strip()
        if ev not in _EVENTS:
            continue
        if ev == "OPEN" or ev == "PRIORITY":
            if n != 4:
                continue
            p = parts[3].strip()
            if p not in _LIMITS:
                continue
        else:
            if n != 3:
                continue
            p = None
        if ev == "HOLIDAY":
            if tid != "*":
                continue
            d = _to_int(f1) // 1440
            if d % 7 < 5:
                hol_days.add(d)
            continue
        if tid == "*":
            continue
        events.append((_to_int(f1), tid, ev, p))

    if not events:
        return []

    now = max(e[0] for e in events)
    events.sort(key=lambda e: e[0])  # stable

    per = {}
    for e in events:
        lst = per.get(e[1])
        if lst is None:
            lst = []
            per[e[1]] = lst
        lst.append(e)

    # Calendar helpers
    hol_w = sorted((d // 7) * 5 + (d % 7) for d in hol_days)
    adj = [w - i for i, w in enumerate(hol_w)]

    def B(t):
        """Number of business minutes x with 0 <= x < t."""
        d, r = divmod(t, 1440)
        wk, wd = divmod(d, 7)
        if wd < 5:
            W = wk * 5 + wd
            nh = bisect_left(hol_w, W)
            total = (W - nh) * 480
            if r > 540 and d not in hol_days:
                total += (r - 540) if r < 1020 else 480
        else:
            W = wk * 5 + 5
            nh = bisect_left(hol_w, W)
            total = (W - nh) * 480
        return total

    def first_t(K):
        """Smallest t with B(t) >= K (K >= 1)."""
        k0 = K - 1
        j, off = divmod(k0, 480)
        w = j + bisect_right(adj, j)
        wk, wd = divmod(w, 5)
        return (wk * 7 + wd) * 1440 + 540 + off + 1

    out = []
    for tid, evs in per.items():
        state = _NOT_OPENED
        prio = None
        used = 0
        b_last = 0
        breached = None
        opened = False
        i = 0
        n = len(evs)
        while i < n:
            m = evs[i][0]
            if state == _RUNNING:
                bm = B(m)
                used_m = used + bm - b_last
                if breached is None:
                    L = _LIMITS[prio]
                    if used_m > L:
                        t = first_t(L + 1 - used + b_last)
                        if t < m:
                            breached = t
                used = used_m
            else:
                bm = None

            while i < n and evs[i][0] == m:
                ev = evs[i][2]
                p = evs[i][3]
                i += 1
                if ev == "OPEN":
                    if state == _NOT_OPENED or state == _CLOSED:
                        state = _RUNNING
                        prio = p
                        used = 0
                        breached = None
                        opened = True
                elif ev == "PRIORITY":
                    if state == _RUNNING or state == _PAUSED:
                        prio = p
                elif ev == "PAUSE":
                    if state == _RUNNING:
                        state = _PAUSED
                elif ev == "RESUME":
                    if state == _PAUSED:
                        state = _RUNNING
                elif ev == "CLOSE":
                    if state == _RUNNING or state == _PAUSED:
                        state = _CLOSED
                elif ev == "REOPEN":
                    if state == _CLOSED:
                        state = _RUNNING

            if state != _NOT_OPENED and breached is None and used > _LIMITS[prio]:
                breached = m

            if state == _RUNNING:
                b_last = bm if bm is not None else B(m)

        if not opened:
            continue

        if state == _RUNNING:
            bn = B(now)
            used_n = used + bn - b_last
            if breached is None:
                L = _LIMITS[prio]
                if used_n > L:
                    breached = first_t(L + 1 - used + b_last)
            used = used_n

        out.append({
            "ticket_id": tid,
            "priority": prio,
            "used_minutes": used,
            "breached": breached is not None,
            "breached_at": breached,
            "status": _STATUS_NAME[state],
        })

    out.sort(key=lambda r: r["ticket_id"])
    return out