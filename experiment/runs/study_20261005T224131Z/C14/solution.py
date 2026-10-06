from bisect import bisect_left, bisect_right
from operator import itemgetter

_LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
_EVENTS = {"OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}

_NOT_OPENED = 0
_RUNNING = 1
_PAUSED = 2
_CLOSED = 3

_STATUS_NAMES = {_RUNNING: "running", _PAUSED: "paused", _CLOSED: "closed"}


def _parse_int(s):
    s2 = s.lstrip("0")
    if not s2:
        return 0
    if len(s2) <= 4000:
        return int(s2)
    val = 0
    for i in range(0, len(s2), 1000):
        chunk = s2[i:i + 1000]
        val = val * (10 ** len(chunk)) + int(chunk)
    return val


def compute_sla(stream):
    holiday_days = set()
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
        ms = parts[0].strip()
        if not ms or not ms.isascii() or not ms.isdigit():
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
        elif tid == "*":
            continue
        m = _parse_int(ms)
        if ev == "HOLIDAY":
            holiday_days.add(m // 1440)
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

    # Holiday weekdays mapped to business-day indices (week*5 + weekday).
    HB = sorted({(d // 7) * 5 + (d % 7) for d in holiday_days if d % 7 < 5})
    HBset = set(HB)
    C = [HB[j] - j for j in range(len(HB))]

    def B(t):
        """Number of business minutes in [0, t)."""
        d, mod = divmod(t, 1440)
        w, wd = divmod(d, 7)
        if wd < 5:
            bd = w * 5 + wd
            h = bisect_left(HB, bd)
            if mod <= 540 or bd in HBset:
                p = 0
            elif mod >= 1020:
                p = 480
            else:
                p = mod - 540
            return (bd - h) * 480 + p
        bd = w * 5 + 5
        h = bisect_left(HB, bd)
        return (bd - h) * 480

    def first_t_reaching(k):
        """Smallest t with B(t) >= k (k >= 1)."""
        k0 = k - 1
        q, off = divmod(k0, 480)
        i = bisect_right(C, q)
        D = q + i
        w, wd = divmod(D, 5)
        day = w * 7 + wd
        x = day * 1440 + 540 + off
        return x + 1

    limits = _LIMITS
    key0 = itemgetter(0)
    results = []

    for tid in sorted(tickets):
        evs = tickets[tid]
        evs.sort(key=key0)
        state = _NOT_OPENED
        prio = None
        used = 0
        last = None
        B_last = 0
        breached_at = None
        i = 0
        n = len(evs)
        while i < n:
            m = evs[i][0]
            Bm = None
            if state == _RUNNING:
                Bm = B(m)
                delta = Bm - B_last
                if delta:
                    if breached_at is None:
                        L = limits[prio]
                        if used + delta > L:
                            t = first_t_reaching(B_last + L + 1 - used)
                            if t < m:
                                breached_at = t
                    used += delta
            # apply all events at minute m in order
            while i < n and evs[i][0] == m:
                _, ev, p = evs[i]
                i += 1
                if ev == "OPEN":
                    if state == _NOT_OPENED or state == _CLOSED:
                        state = _RUNNING
                        prio = p
                        used = 0
                        breached_at = None
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
            if state != _NOT_OPENED and breached_at is None and used > limits[prio]:
                breached_at = m
            if state == _RUNNING:
                if Bm is None:
                    Bm = B(m)
                B_last = Bm
            last = m

        if state == _NOT_OPENED:
            continue

        # Tail: extend to "now"
        if state == _RUNNING and now > last:
            Bn = B(now)
            delta = Bn - B_last
            if delta:
                if breached_at is None:
                    L = limits[prio]
                    if used + delta > L:
                        t = first_t_reaching(B_last + L + 1 - used)
                        if t <= now:
                            breached_at = t
                used += delta

        results.append({
            "ticket_id": tid,
            "priority": prio,
            "used_minutes": int(used),
            "breached": breached_at is not None,
            "breached_at": breached_at,
            "status": _STATUS_NAMES[state],
        })

    return results