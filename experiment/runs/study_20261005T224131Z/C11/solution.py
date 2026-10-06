from bisect import bisect_left
from operator import itemgetter

_LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
_EVENTS = {"OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}

_NOT_OPENED = 0
_RUNNING = 1
_PAUSED = 2
_CLOSED = 3

_STATUS = {_RUNNING: "running", _PAUSED: "paused", _CLOSED: "closed"}


def _parse_int(digits):
    s = digits.lstrip("0")
    if not s:
        return 0
    try:
        return int(s)
    except ValueError:
        # Extremely long digit strings (int max str digits limit); convert in chunks.
        val = 0
        step = 1000
        for i in range(0, len(s), step):
            chunk = s[i:i + step]
            val = val * (10 ** len(chunk)) + int(chunk)
        return val


def _weekday_business_before(t):
    """Number of weekday business minutes (ignoring holidays) in [0, t)."""
    q, r = divmod(t, 10080)
    d, rem = divmod(r, 1440)
    if d >= 5:
        return q * 2400 + 2400
    x = rem - 540
    if x < 0:
        x = 0
    elif x > 480:
        x = 480
    return q * 2400 + d * 480 + x


def _weekday_inverse(k):
    """Smallest t with weekday-business-count W(t) >= k (k >= 1)."""
    q, r = divmod(k - 1, 2400)
    day, mod = divmod(r, 480)
    x = q * 10080 + day * 1440 + 540 + mod
    return x + 1


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
        parts = [p.strip() for p in parts]
        ms, tid, ev = parts[0], parts[1], parts[2]
        if not ms or not (ms.isascii() and ms.isdigit()):
            continue
        if not tid:
            continue
        if ev not in _EVENTS:
            continue
        if ev == "OPEN" or ev == "PRIORITY":
            if n != 4:
                continue
            prio = parts[3]
            if prio not in _LIMITS:
                continue
        else:
            if n != 3:
                continue
            prio = None
        if ev == "HOLIDAY":
            if tid != "*":
                continue
            holidays.add(_parse_int(ms) // 1440)
            continue
        if tid == "*":
            continue
        m = _parse_int(ms)
        lst = tickets.get(tid)
        if lst is None:
            lst = []
            tickets[tid] = lst
        lst.append((m, ev, prio))
        if now is None or m > now:
            now = m

    if now is None:
        return []

    hol = sorted(d for d in holidays if d % 7 < 5)
    nh = len(hol)
    W = _weekday_business_before
    # N_i: number of (non-holiday) business minutes before the start of holiday day hol[i]
    N = [W(hol[i] * 1440) - 480 * i for i in range(nh)]

    def B(t):
        w = W(t)
        if nh:
            day = t // 1440
            i = bisect_left(hol, day)
            h = i * 480
            if i < nh and hol[i] == day:
                x = t % 1440 - 540
                if x < 0:
                    x = 0
                elif x > 480:
                    x = 480
                h += x
            w -= h
        return w

    def Binv(k):
        """Smallest t with B(t) >= k (k >= 1)."""
        j = bisect_left(N, k) if nh else 0
        return _weekday_inverse(k + 480 * j)

    results = []
    key0 = itemgetter(0)

    for tid, evs in tickets.items():
        evs.sort(key=key0)  # stable
        state = _NOT_OPENED
        prio = None
        used = 0
        breached_at = None
        prev = None
        bprev = 0
        i = 0
        n = len(evs)
        while i < n:
            m = evs[i][0]
            j = i
            while j < n and evs[j][0] == m:
                j += 1
            bm = B(m)
            if state == _RUNNING:
                used_m = used + bm - bprev
                if breached_at is None:
                    limit = _LIMITS[prio]
                    if used_m > limit:
                        t = Binv(bprev + limit + 1 - used)
                        if t < m:
                            breached_at = t
                used = used_m
            prev = m
            bprev = bm
            # Apply events at minute m
            for k in range(i, j):
                _, ev, p = evs[k]
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
            # Post-event breach check at minute m
            if breached_at is None and state != _NOT_OPENED:
                if used > _LIMITS[prio]:
                    breached_at = m
            i = j

        if state == _NOT_OPENED:
            continue

        if state == _RUNNING and prev is not None and prev < now:
            used_now = used + B(now) - bprev
            if breached_at is None:
                limit = _LIMITS[prio]
                if used_now > limit:
                    breached_at = Binv(bprev + limit + 1 - used)
            used = used_now

        results.append({
            "ticket_id": tid,
            "priority": prio,
            "used_minutes": used,
            "breached": breached_at is not None,
            "breached_at": breached_at,
            "status": _STATUS[state],
        })

    results.sort(key=lambda d: d["ticket_id"])
    return results