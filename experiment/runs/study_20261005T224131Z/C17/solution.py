from bisect import bisect_left, bisect_right

_LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
_EVENTS = frozenset(("OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"))

_NOT_OPENED = 0
_RUNNING = 1
_PAUSED = 2
_CLOSED = 3
_STATUS = {_RUNNING: "running", _PAUSED: "paused", _CLOSED: "closed"}

_DAY = 1440
_WEEK = 10080
_BIZ_START = 540
_BIZ_LEN = 480
_WEEK_BIZ = 2400


def _to_int(s):
    s = s.lstrip("0")
    if not s:
        return 0
    if len(s) <= 4000:
        return int(s)
    val = 0
    for i in range(0, len(s), 4000):
        chunk = s[i:i + 4000]
        val = val * (10 ** len(chunk)) + int(chunk)
    return val


def _parse(line):
    if not isinstance(line, str):
        return None
    s = line.strip()
    if not s:
        return None
    parts = s.split(",")
    if len(parts) != 3 and len(parts) != 4:
        return None
    parts = [p.strip() for p in parts]
    m, tid, ev = parts[0], parts[1], parts[2]
    if not m or not (m.isascii() and m.isdigit()):
        return None
    if not tid:
        return None
    if ev not in _EVENTS:
        return None
    if ev == "OPEN" or ev == "PRIORITY":
        if len(parts) != 4:
            return None
        p = parts[3]
        if p not in _LIMITS:
            return None
    else:
        if len(parts) != 3:
            return None
        p = None
    if ev == "HOLIDAY":
        if tid != "*":
            return None
    elif tid == "*":
        return None
    return (_to_int(m), tid, ev, p)


def _base(t):
    """Business minutes in [0, t) ignoring holidays."""
    w, r = divmod(t, _WEEK)
    dd, m = divmod(r, _DAY)
    if dd >= 5:
        return w * _WEEK_BIZ + _WEEK_BIZ
    x = m - _BIZ_START
    if x < 0:
        x = 0
    elif x > _BIZ_LEN:
        x = _BIZ_LEN
    return w * _WEEK_BIZ + dd * _BIZ_LEN + x


class _Ticket:
    __slots__ = ("state", "prio", "used", "last", "breached_at", "opened")

    def __init__(self, t):
        self.state = _NOT_OPENED
        self.prio = None
        self.used = 0
        self.last = t
        self.breached_at = None
        self.opened = False


def compute_sla(stream):
    events = []
    hol_days = set()
    for line in stream:
        rec = _parse(line)
        if rec is None:
            continue
        if rec[2] == "HOLIDAY":
            hol_days.add(rec[0] // _DAY)
        else:
            events.append(rec)

    if not events:
        return []

    now = max(e[0] for e in events)
    events.sort(key=lambda e: e[0])

    hol = sorted(d for d in hol_days if d % 7 < 5)
    holset = set(hol)
    A = [_base(h * _DAY) - _BIZ_LEN * j for j, h in enumerate(hol)]

    def B(t):
        d = t // _DAY
        c = bisect_left(hol, d)
        res = _base(t) - _BIZ_LEN * c
        if d in holset:
            x = t - d * _DAY - _BIZ_START
            if x < 0:
                x = 0
            elif x > _BIZ_LEN:
                x = _BIZ_LEN
            res -= x
        return res

    def first_reach(T):
        """Smallest t with B(t) >= T (T >= 1)."""
        c = bisect_right(A, T - 1)
        k = T - 1 + _BIZ_LEN * c
        w, r = divmod(k, _WEEK_BIZ)
        dd, m = divmod(r, _BIZ_LEN)
        x = w * _WEEK + dd * _DAY + _BIZ_START + m
        return x + 1

    def advance(tk, t):
        last = tk.last
        if t > last and tk.state == _RUNNING:
            b0 = B(last)
            b1 = B(t)
            delta = b1 - b0
            if delta > 0:
                if tk.breached_at is None and tk.prio is not None:
                    need = _LIMITS[tk.prio] - tk.used + 1
                    if need < 1:
                        need = 1
                    if delta >= need:
                        tb = first_reach(b0 + need)
                        if tb < t:
                            tk.breached_at = tb
                tk.used += delta
        tk.last = t

    def check(tk, t):
        if tk.prio is not None and tk.breached_at is None:
            if tk.used > _LIMITS[tk.prio]:
                tk.breached_at = t

    tickets = {}
    n = len(events)
    i = 0
    while i < n:
        t = events[i][0]
        touched = []
        j = i
        while j < n and events[j][0] == t:
            _, tid, ev, p = events[j]
            j += 1
            tk = tickets.get(tid)
            if tk is None:
                tk = _Ticket(t)
                tickets[tid] = tk
                touched.append(tk)
            elif tk.last != t:
                advance(tk, t)
                touched.append(tk)

            st = tk.state
            if ev == "OPEN":
                if st == _NOT_OPENED or st == _CLOSED:
                    tk.state = _RUNNING
                    tk.prio = p
                    tk.used = 0
                    tk.breached_at = None
                    tk.opened = True
            elif ev == "PRIORITY":
                if st == _RUNNING or st == _PAUSED:
                    tk.prio = p
            elif ev == "PAUSE":
                if st == _RUNNING:
                    tk.state = _PAUSED
            elif ev == "RESUME":
                if st == _PAUSED:
                    tk.state = _RUNNING
            elif ev == "CLOSE":
                if st == _RUNNING or st == _PAUSED:
                    tk.state = _CLOSED
            elif ev == "REOPEN":
                if st == _CLOSED:
                    tk.state = _RUNNING
        for tk in touched:
            check(tk, t)
        i = j

    result = []
    for tid in sorted(tickets):
        tk = tickets[tid]
        if not tk.opened:
            continue
        advance(tk, now)
        check(tk, now)
        result.append({
            "ticket_id": tid,
            "priority": tk.prio,
            "used_minutes": tk.used,
            "breached": tk.breached_at is not None,
            "breached_at": tk.breached_at,
            "status": _STATUS[tk.state],
        })
    return result