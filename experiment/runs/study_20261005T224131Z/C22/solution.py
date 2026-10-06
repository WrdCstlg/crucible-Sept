from bisect import bisect_left, bisect_right

_LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
_PRIOS = frozenset(("P1", "P2", "P3", "P4"))

_NOT_OPENED = 0
_RUNNING = 1
_PAUSED = 2
_CLOSED = 3

_EV_OPEN = 0
_EV_PRIORITY = 1
_EV_PAUSE = 2
_EV_RESUME = 3
_EV_CLOSE = 4
_EV_REOPEN = 5

_SIMPLE_EVENTS = {
    "PAUSE": _EV_PAUSE,
    "RESUME": _EV_RESUME,
    "CLOSE": _EV_CLOSE,
    "REOPEN": _EV_REOPEN,
}

_STATUS_NAMES = {_RUNNING: "running", _PAUSED: "paused", _CLOSED: "closed"}


def _to_int(s):
    s = s.lstrip("0")
    if not s:
        return 0
    if len(s) <= 4000:
        return int(s)
    v = 0
    for i in range(0, len(s), 4000):
        c = s[i:i + 4000]
        v = v * (10 ** len(c)) + int(c)
    return v


def compute_sla(stream):
    holiday_wd = set()   # weekday indices (Mon-Fri enumeration) that are holidays
    tickets = {}
    now = None

    for line in stream:
        if not isinstance(line, str):
            continue
        parts = line.strip().split(",")
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
        if ev == "HOLIDAY":
            if n != 3 or tid != "*":
                continue
            m = _to_int(ms)
            day = m // 1440
            wk, dow = divmod(day, 7)
            if dow < 5:
                holiday_wd.add(wk * 5 + dow)
            continue
        if ev == "OPEN" or ev == "PRIORITY":
            if n != 4:
                continue
            p = parts[3].strip()
            if p not in _PRIOS:
                continue
            code = _EV_OPEN if ev == "OPEN" else _EV_PRIORITY
        else:
            code = _SIMPLE_EVENTS.get(ev)
            if code is None or n != 3:
                continue
            p = None
        if tid == "*":
            continue
        m = _to_int(ms)
        if now is None or m > now:
            now = m
        lst = tickets.get(tid)
        if lst is None:
            lst = []
            tickets[tid] = lst
        lst.append((m, code, p))

    if now is None:
        return []

    hw = sorted(holiday_wd)
    hset = holiday_wd
    arr = [h - i for i, h in enumerate(hw)]

    def B(t):
        # number of business minutes x with 0 <= x < t
        day, rem = divmod(t, 1440)
        wk, dow = divmod(day, 7)
        if dow < 5:
            wdb = wk * 5 + dow
            hc = bisect_left(hw, wdb) if hw else 0
            total = (wdb - hc) * 480
            if rem > 540 and wdb not in hset:
                x = rem - 540
                total += x if x < 480 else 480
            return total
        wdb = wk * 5 + 5
        hc = bisect_left(hw, wdb) if hw else 0
        return (wdb - hc) * 480

    def inv(target):
        # smallest t with B(t) >= target (target >= 1)
        q, r = divmod(target - 1, 480)
        j = bisect_right(arr, q) if arr else 0
        w = q + j
        wk, d = divmod(w, 5)
        return (wk * 7 + d) * 1440 + 540 + r + 1

    results = []
    for tid in sorted(tickets):
        evs = tickets[tid]
        evs.sort(key=lambda e: e[0])
        state = _NOT_OPENED
        prio = None
        limit = 0
        used = 0
        bat = None
        b_last = 0
        i = 0
        n = len(evs)
        while i < n:
            T = evs[i][0]
            bT = None
            if state == _RUNNING:
                bT = B(T)
                gained = bT - b_last
                if bat is None:
                    k = limit - used + 1
                    if gained >= k:
                        tb = inv(b_last + k)
                        if tb < T:
                            bat = tb
                used += gained
            while i < n and evs[i][0] == T:
                _, code, p = evs[i]
                i += 1
                if code == _EV_OPEN:
                    if state == _NOT_OPENED or state == _CLOSED:
                        state = _RUNNING
                        prio = p
                        limit = _LIMITS[p]
                        used = 0
                        bat = None
                elif code == _EV_PRIORITY:
                    if state == _RUNNING or state == _PAUSED:
                        prio = p
                        limit = _LIMITS[p]
                elif code == _EV_PAUSE:
                    if state == _RUNNING:
                        state = _PAUSED
                elif code == _EV_RESUME:
                    if state == _PAUSED:
                        state = _RUNNING
                elif code == _EV_CLOSE:
                    if state == _RUNNING or state == _PAUSED:
                        state = _CLOSED
                elif code == _EV_REOPEN:
                    if state == _CLOSED:
                        state = _RUNNING
            if state != _NOT_OPENED and bat is None and used > limit:
                bat = T
            if state == _RUNNING:
                b_last = bT if bT is not None else B(T)

        if state == _NOT_OPENED:
            continue

        if state == _RUNNING:
            bN = B(now)
            gained = bN - b_last
            if bat is None:
                k = limit - used + 1
                if gained >= k:
                    bat = inv(b_last + k)
            used += gained

        results.append({
            "ticket_id": tid,
            "priority": prio,
            "used_minutes": used,
            "breached": bat is not None,
            "breached_at": bat,
            "status": _STATUS_NAMES[state],
        })

    return results