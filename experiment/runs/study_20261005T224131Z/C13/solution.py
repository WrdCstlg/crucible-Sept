from bisect import bisect_left, bisect_right

_LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
_PRIOS = frozenset(_LIMITS)
_EVENTS = frozenset(
    ("OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY")
)

_NOT_OPENED = 0
_RUNNING = 1
_PAUSED = 2
_CLOSED = 3

_STATUS = {_RUNNING: "running", _PAUSED: "paused", _CLOSED: "closed"}


def _is_ascii_digits(s):
    return bool(s) and s.isascii() and s.isdigit()


def _parse_int(s):
    try:
        return int(s)
    except ValueError:
        # Fallback for extremely long digit strings (int max str digits limit).
        n = 0
        for i in range(0, len(s), 1000):
            chunk = s[i:i + 1000]
            n = n * (10 ** len(chunk)) + int(chunk)
        return n


def _parse_line(raw):
    """Return (minute, tid, event, prio) or None if malformed."""
    if not isinstance(raw, str):
        return None
    parts = raw.strip().split(",")
    nf = len(parts)
    if nf != 3 and nf != 4:
        return None
    parts = [p.strip() for p in parts]
    ms, tid, ev = parts[0], parts[1], parts[2]
    if not _is_ascii_digits(ms):
        return None
    if not tid:
        return None
    if ev not in _EVENTS:
        return None
    prio = None
    if ev == "OPEN" or ev == "PRIORITY":
        if nf != 4:
            return None
        prio = parts[3]
        if prio not in _PRIOS:
            return None
    else:
        if nf != 3:
            return None
    if ev == "HOLIDAY":
        if tid != "*":
            return None
    else:
        if tid == "*":
            return None
    return (_parse_int(ms), tid, ev, prio)


def compute_sla(stream):
    tickets = {}
    hol_days = set()
    now = None

    for raw in stream:
        rec = _parse_line(raw)
        if rec is None:
            continue
        m, tid, ev, prio = rec
        if ev == "HOLIDAY":
            d = m // 1440
            if d % 7 < 5:
                hol_days.add(d)
            continue
        lst = tickets.get(tid)
        if lst is None:
            lst = []
            tickets[tid] = lst
        lst.append((m, ev, prio))
        if now is None or m > now:
            now = m

    if now is None:
        return []

    # Weekday indices of holidays (only weekday holidays matter).
    hidx = sorted(5 * (d // 7) + (d % 7) for d in hol_days)
    adj = [hidx[j] - j for j in range(len(hidx))]

    def B(t):
        """Number of business minutes x with 0 <= x < t."""
        d, mod = divmod(t, 1440)
        wd = d % 7
        w = 5 * (d // 7) + (wd if wd < 5 else 5)
        h = bisect_left(hidx, w)
        total = 480 * (w - h)
        if wd < 5 and d not in hol_days:
            p = mod - 540
            if p > 0:
                total += p if p < 480 else 480
        return total

    def inv(n):
        """Smallest t with B(t) >= n, for n >= 1."""
        j = n - 1
        k, off = divmod(j, 480)
        g = k + bisect_right(adj, k)
        day = 7 * (g // 5) + g % 5
        return day * 1440 + 540 + off + 1

    results = []
    for tid, evs in tickets.items():
        evs.sort(key=lambda e: e[0])
        state = _NOT_OPENED
        prio = None
        U = 0
        Bc = 0
        c = None
        br = None
        opened = False
        i = 0
        n = len(evs)
        while i < n:
            m = evs[i][0]
            Bm = None
            if state == _RUNNING:
                if br is None:
                    t = inv(Bc + _LIMITS[prio] - U + 1)
                    if t < m:
                        br = t
                Bm = B(m)
                U += Bm - Bc
            # Apply all events at minute m in order.
            while i < n and evs[i][0] == m:
                _, ev, p = evs[i]
                i += 1
                if ev == "OPEN":
                    if state == _NOT_OPENED or state == _CLOSED:
                        state = _RUNNING
                        prio = p
                        U = 0
                        br = None
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
            if state != _NOT_OPENED and br is None and U > _LIMITS[prio]:
                br = m
            if state == _RUNNING:
                Bc = Bm if Bm is not None else B(m)
            c = m

        if not opened:
            continue

        if c < now and state == _RUNNING:
            if br is None:
                t = inv(Bc + _LIMITS[prio] - U + 1)
                if t <= now:
                    br = t
            U += B(now) - Bc

        results.append({
            "ticket_id": tid,
            "priority": prio,
            "used_minutes": U,
            "breached": br is not None,
            "breached_at": br,
            "status": _STATUS[state],
        })

    results.sort(key=lambda r: r["ticket_id"])
    return results