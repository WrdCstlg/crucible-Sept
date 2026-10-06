from bisect import bisect_left
from operator import itemgetter

_LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
_TICKET_EVENTS = frozenset(("OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN"))
_DIGITS = "0123456789"
_STATUS = {1: "running", 2: "paused", 3: "closed"}
_key0 = itemgetter(0)


def _parse_int(s):
    s = s.lstrip("0")
    if not s:
        return 0
    if len(s) <= 4000:
        return int(s)
    v = 0
    for k in range(0, len(s), 4000):
        chunk = s[k:k + 4000]
        v = v * (10 ** len(chunk)) + int(chunk)
    return v


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
        f1 = parts[0].strip()
        if not f1 or f1.strip(_DIGITS):
            continue
        tid = parts[1].strip()
        if not tid:
            continue
        ev = parts[2].strip()
        if ev == "HOLIDAY":
            if n != 3 or tid != "*":
                continue
            holidays.add(_parse_int(f1) // 1440)
            continue
        if ev not in _TICKET_EVENTS:
            continue
        if tid == "*":
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
        m = _parse_int(f1)
        lst = tickets.get(tid)
        if lst is None:
            lst = []
            tickets[tid] = lst
        lst.append((m, ev, p))
        if now is None or m > now:
            now = m

    if now is None:
        return []

    # Calendar structures
    wh = sorted(d for d in holidays if d % 7 < 5)
    cnt = [(d // 7) * 5 + (d % 7) - i for i, d in enumerate(wh)]
    hol_set = holidays

    def B(t):
        # number of business minutes x with 0 <= x < t
        D, r = divmod(t, 1440)
        w = D % 7
        res = ((D // 7) * 5 + (w if w < 5 else 5) - bisect_left(wh, D)) * 480
        if w < 5 and r > 540 and D not in hol_set:
            res += (r - 540) if r < 1020 else 480
        return res

    def inv(T):
        # smallest y with B(y) >= T, for T >= 1
        q, r = divmod(T - 1, 480)
        h = bisect_left(cnt, q + 1)
        j = q + h
        day = (j // 5) * 7 + j % 5
        return day * 1440 + 540 + r + 1

    result = []
    limits = _LIMITS
    for tid in sorted(tickets):
        evs = tickets[tid]
        evs.sort(key=_key0)
        state = 0  # 0 NOT_OPENED, 1 RUNNING, 2 PAUSED, 3 CLOSED
        prio = None
        used = 0
        bat = None
        bcur = 0
        cur = None
        i = 0
        n = len(evs)
        while i < n:
            t = evs[i][0]
            bt = None
            if state == 1:
                bt = B(t)
                delta = bt - bcur
                if delta:
                    if bat is None:
                        L = limits[prio]
                        if used + delta > L:
                            y = inv(bcur + L - used + 1)
                            if y < t:
                                bat = y
                    used += delta
            while i < n and evs[i][0] == t:
                _, ev, p = evs[i]
                i += 1
                if ev == "OPEN":
                    if state == 0 or state == 3:
                        state = 1
                        prio = p
                        used = 0
                        bat = None
                elif ev == "PRIORITY":
                    if state == 1 or state == 2:
                        prio = p
                elif ev == "PAUSE":
                    if state == 1:
                        state = 2
                elif ev == "RESUME":
                    if state == 2:
                        state = 1
                elif ev == "CLOSE":
                    if state == 1 or state == 2:
                        state = 3
                else:  # REOPEN
                    if state == 3:
                        state = 1
            if state and bat is None and used > limits[prio]:
                bat = t
            if state == 1:
                bcur = bt if bt is not None else B(t)
            cur = t

        if state == 0:
            continue

        if state == 1 and cur < now:
            bt = B(now)
            delta = bt - bcur
            if delta:
                if bat is None:
                    L = limits[prio]
                    if used + delta > L:
                        bat = inv(bcur + L - used + 1)
                used += delta

        result.append({
            "ticket_id": tid,
            "priority": prio,
            "used_minutes": used,
            "breached": bat is not None,
            "breached_at": bat,
            "status": _STATUS[state],
        })

    return result