from bisect import bisect_left, bisect_right

_LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
_EVENTS = frozenset(["OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"])

_NOT_OPENED = 0
_RUNNING = 1
_PAUSED = 2
_CLOSED = 3

_STATUS = {_RUNNING: "running", _PAUSED: "paused", _CLOSED: "closed"}


def _parse_int(s):
    s2 = s.lstrip("0")
    if not s2:
        return 0
    if len(s2) <= 4000:
        return int(s2)
    val = 0
    for i in range(0, len(s2), 4000):
        chunk = s2[i:i + 4000]
        val = val * (10 ** len(chunk)) + int(chunk)
    return val


def compute_sla(stream):
    holidays = set()
    tickets = {}
    now = None

    for line in stream:
        if not isinstance(line, str):
            continue
        parts = line.strip().split(",")
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
            if n != 4 or parts[3] not in _LIMITS:
                continue
            pr = parts[3]
        else:
            if n != 3:
                continue
            pr = None
        if ev == "HOLIDAY":
            if tid != "*":
                continue
            m = _parse_int(ms)
            holidays.add(m // 1440)
            continue
        if tid == "*":
            continue
        m = _parse_int(ms)
        lst = tickets.get(tid)
        if lst is None:
            lst = []
            tickets[tid] = lst
        lst.append((m, ev, pr))
        if now is None or m > now:
            now = m

    if now is None:
        return []

    # Calendar preprocessing: only weekday holidays matter.
    HD = sorted(d for d in holidays if d % 7 < 5)
    Hset = set(HD)
    G = [((d // 7) * 5 + d % 7) - i for i, d in enumerate(HD)]

    def B(t):
        """Number of business minutes in [0, t)."""
        D, r = divmod(t, 1440)
        wd = D % 7
        w = (D // 7) * 5 + (wd if wd < 5 else 5)
        full = w - bisect_left(HD, D)
        res = full * 480
        if wd < 5 and r > 540 and D not in Hset:
            extra = r - 540
            if extra > 480:
                extra = 480
            res += extra
        return res

    def nth_end(T):
        """Smallest t with B(t) >= T, for T >= 1."""
        q, rem = divmod(T - 1, 480)
        j = bisect_right(G, q)
        w = q + j
        d = (w // 5) * 7 + w % 5
        return d * 1440 + 540 + rem + 1

    results = []
    for tid in sorted(tickets):
        evs = tickets[tid]
        evs.sort(key=lambda e: e[0])
        state = _NOT_OPENED
        prio = None
        used = 0
        last_B = 0
        breached_at = None
        i = 0
        n = len(evs)
        while i < n:
            t = evs[i][0]
            Bt = B(t)
            if state == _RUNNING:
                if breached_at is None:
                    T = last_B + _LIMITS[prio] + 1 - used
                    ts = nth_end(T)
                    if ts < t:
                        breached_at = ts
                used += Bt - last_B
            while i < n and evs[i][0] == t:
                _, ev, pr = evs[i]
                i += 1
                if ev == "OPEN":
                    if state == _NOT_OPENED or state == _CLOSED:
                        state = _RUNNING
                        prio = pr
                        used = 0
                        breached_at = None
                elif ev == "PRIORITY":
                    if state == _RUNNING or state == _PAUSED:
                        prio = pr
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
                breached_at = t
            last_B = Bt

        if state == _NOT_OPENED:
            continue

        if state == _RUNNING:
            if breached_at is None:
                T = last_B + _LIMITS[prio] + 1 - used
                ts = nth_end(T)
                if ts <= now:
                    breached_at = ts
            used += B(now) - last_B

        results.append({
            "ticket_id": tid,
            "priority": prio,
            "used_minutes": used,
            "breached": breached_at is not None,
            "breached_at": breached_at,
            "status": _STATUS[state],
        })

    return results