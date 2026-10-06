from bisect import bisect_left, bisect_right
from operator import itemgetter

_LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
_EVENTS4 = frozenset(("OPEN", "PRIORITY"))
_EVENTS3 = frozenset(("PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"))
_DIGITS = frozenset("0123456789")

_NOT_OPENED, _RUNNING, _PAUSED, _CLOSED = 0, 1, 2, 3
_STATUS = {_RUNNING: "running", _PAUSED: "paused", _CLOSED: "closed"}

_first = itemgetter(0)


def _to_int(s):
    try:
        return int(s)
    except ValueError:
        # Guard against interpreter limits on very long digit strings.
        s2 = s.lstrip("0") or "0"
        n = 0
        for i in range(0, len(s2), 1000):
            chunk = s2[i:i + 1000]
            n = n * (10 ** len(chunk)) + int(chunk)
        return n


def _parse(line):
    if not isinstance(line, str):
        return None
    s = line.strip()
    if not s:
        return None
    parts = s.split(",")
    n = len(parts)
    if n != 3 and n != 4:
        return None
    f1 = parts[0].strip()
    if not f1 or not _DIGITS.issuperset(f1):
        return None
    tid = parts[1].strip()
    if not tid:
        return None
    ev = parts[2].strip()
    if ev in _EVENTS4:
        if n != 4:
            return None
        p = parts[3].strip()
        if p not in _LIMITS:
            return None
    elif ev in _EVENTS3:
        if n != 3:
            return None
        p = None
    else:
        return None
    if ev == "HOLIDAY":
        if tid != "*":
            return None
    elif tid == "*":
        return None
    return (_to_int(f1), tid, ev, p)


def compute_sla(stream):
    holiday_days = set()
    tickets = {}
    now = None

    for line in stream:
        rec = _parse(line)
        if rec is None:
            continue
        m, tid, ev, p = rec
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

    # Only weekday holidays matter for business-minute counting.
    hw_days = sorted(d for d in holiday_days if d % 7 < 5)
    hw_set = set(hw_days)
    # g[i] = number of non-holiday weekdays (by weekday index) before the i-th holiday
    g = [(d // 7) * 5 + (d % 7) - i for i, d in enumerate(hw_days)]

    def bus_before(t):
        """Number of business minutes x with 0 <= x < t."""
        d, mod = divmod(t, 1440)
        q, r = divmod(d, 7)
        w = q * 5 + (r if r < 5 else 5)
        h = bisect_left(hw_days, d)
        res = (w - h) * 480
        if r < 5 and mod > 540 and d not in hw_set:
            res += (mod if mod < 1020 else 1020) - 540
        return res

    def kth(c):
        """Minute of the c-th (1-based) business minute overall."""
        idx = c - 1
        j, mod = divmod(idx, 480)
        w = j + bisect_right(g, j)
        q, r = divmod(w, 5)
        d = q * 7 + r
        return d * 1440 + 540 + mod

    results = []
    for tid in sorted(tickets):
        evs = tickets[tid]
        evs.sort(key=_first)
        state = _NOT_OPENED
        prio = None
        used = 0
        last = None
        last_B = 0
        breached_at = None
        i = 0
        n = len(evs)
        while i < n:
            m = evs[i][0]
            Bm = None
            if state == _RUNNING:
                Bm = bus_before(m)
                delta = Bm - last_B
                if delta:
                    if breached_at is None:
                        lim = _LIMITS[prio]
                        if used + delta > lim:
                            t = kth(last_B + lim + 1 - used) + 1
                            if t < m:
                                breached_at = t
                    used += delta
            # Apply all events at minute m
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
            if state != _NOT_OPENED and breached_at is None and used > _LIMITS[prio]:
                breached_at = m
            last = m
            if state == _RUNNING:
                last_B = Bm if Bm is not None else bus_before(m)

        if state == _NOT_OPENED:
            continue

        # Tail: from last event to now
        if state == _RUNNING and last is not None and now > last:
            Bn = bus_before(now)
            delta = Bn - last_B
            if delta:
                if breached_at is None:
                    lim = _LIMITS[prio]
                    if used + delta > lim:
                        breached_at = kth(last_B + lim + 1 - used) + 1
                used += delta

        results.append({
            "ticket_id": tid,
            "priority": prio,
            "used_minutes": used,
            "breached": breached_at is not None,
            "breached_at": breached_at,
            "status": _STATUS[state],
        })

    return results