import bisect
from operator import itemgetter

_LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
_EVENTS = frozenset(("OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"))

_NOT_OPENED = 0
_RUNNING = 1
_PAUSED = 2
_CLOSED = 3
_STATUS_NAMES = {_RUNNING: "running", _PAUSED: "paused", _CLOSED: "closed"}


def _to_int(s):
    s = s.lstrip("0")
    if not s:
        return 0
    if len(s) <= 4000:
        return int(s)
    v = 0
    for k in range(0, len(s), 1000):
        chunk = s[k:k + 1000]
        v = v * (10 ** len(chunk)) + int(chunk)
    return v


def compute_sla(stream):
    holidays = set()
    tickets = {}
    now = None

    for line in stream:
        if not isinstance(line, str):
            continue
        s = line.strip()
        if not s:
            continue
        parts = s.split(",")
        n = len(parts)
        if n != 3 and n != 4:
            continue
        f1 = parts[0].strip()
        if not f1 or not f1.isascii() or not f1.isdigit():
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
            holidays.add(_to_int(f1) // 1440)
            continue
        if tid == "*":
            continue
        m = _to_int(f1)
        if now is None or m > now:
            now = m
        lst = tickets.get(tid)
        if lst is None:
            lst = []
            tickets[tid] = lst
        lst.append((m, ev, p))

    if now is None:
        return []

    # Weekday holidays only matter for business minutes.
    HD = sorted(d for d in holidays if d % 7 < 5)
    HDset = set(HD)
    # A[i] = (weekday index of holiday i) - i ; nondecreasing
    A = [((h // 7) * 5 + (h % 7)) - i for i, h in enumerate(HD)]

    bisect_left = bisect.bisect_left
    bisect_right = bisect.bisect_right

    def B(t):
        """Number of business minutes x with 0 <= x < t."""
        d, rem = divmod(t, 1440)
        w, dd = divmod(d, 7)
        wd = w * 5 + (dd if dd < 5 else 5)
        h = bisect_left(HD, d)
        res = 480 * (wd - h)
        if dd < 5 and d not in HDset:
            r = rem - 540
            if r > 0:
                res += r if r < 480 else 480
        return res

    def first_t(target):
        """Smallest t with B(t) >= target (target >= 1)."""
        nidx = target - 1
        w, r = divmod(nidx, 480)
        j = bisect_right(A, w)
        q = w + j
        D = (q // 5) * 7 + (q % 5)
        return D * 1440 + 540 + r + 1

    results = []
    key0 = itemgetter(0)

    for tid, evs in tickets.items():
        evs.sort(key=key0)  # stable
        state = _NOT_OPENED
        prio = None
        used = 0
        breached = False
        bat = None
        cur = None
        opened = False
        i = 0
        nev = len(evs)
        while i < nev:
            m = evs[i][0]
            if state == _RUNNING:
                bcur = B(cur)
                bm = B(m)
                if not breached:
                    L = _LIMITS[prio]
                    if used + bm - bcur > L:
                        t = first_t(bcur + L + 1 - used)
                        if t < m:
                            breached = True
                            bat = t
                used += bm - bcur
            cur = m
            while i < nev and evs[i][0] == m:
                _, ev, p = evs[i]
                i += 1
                if ev == "OPEN":
                    if state == _NOT_OPENED or state == _CLOSED:
                        state = _RUNNING
                        prio = p
                        used = 0
                        breached = False
                        bat = None
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
            if state != _NOT_OPENED and not breached and used > _LIMITS[prio]:
                breached = True
                bat = m

        if not opened:
            continue

        if state == _RUNNING and now > cur:
            bcur = B(cur)
            bnow = B(now)
            if not breached:
                L = _LIMITS[prio]
                if used + bnow - bcur > L:
                    t = first_t(bcur + L + 1 - used)
                    if t <= now:
                        breached = True
                        bat = t
            used += bnow - bcur

        results.append({
            "ticket_id": tid,
            "priority": prio,
            "used_minutes": int(used),
            "breached": bool(breached),
            "breached_at": bat if breached else None,
            "status": _STATUS_NAMES[state],
        })

    results.sort(key=lambda r: r["ticket_id"])
    return results