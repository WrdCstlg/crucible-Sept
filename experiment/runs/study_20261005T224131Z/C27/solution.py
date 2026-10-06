import re
from bisect import bisect_left, bisect_right

_LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
_EVENTS = frozenset(("OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"))
_DIGITS_RE = re.compile(r"[0-9]+")

_NOT_OPENED, _RUNNING, _PAUSED, _CLOSED = 0, 1, 2, 3
_STATUS = {_RUNNING: "running", _PAUSED: "paused", _CLOSED: "closed"}


def _parse_int(s):
    s = s.lstrip("0") or "0"
    try:
        return int(s)
    except ValueError:
        # Extremely long digit strings (int max str digits limit); parse in chunks.
        v = 0
        for k in range(0, len(s), 1000):
            chunk = s[k:k + 1000]
            v = v * (10 ** len(chunk)) + int(chunk)
        return v


def _parse_line(line):
    if not isinstance(line, str):
        return None
    s = line.strip()
    if not s:
        return None
    parts = s.split(",")
    if len(parts) != 3 and len(parts) != 4:
        return None
    parts = [p.strip() for p in parts]
    f_min, tid, ev = parts[0], parts[1], parts[2]
    if not _DIGITS_RE.fullmatch(f_min):
        return None
    if not tid:
        return None
    if ev not in _EVENTS:
        return None
    if ev == "OPEN" or ev == "PRIORITY":
        if len(parts) != 4:
            return None
        pr = parts[3]
        if pr not in _LIMITS:
            return None
    else:
        if len(parts) != 3:
            return None
        pr = None
    if ev == "HOLIDAY":
        if tid != "*":
            return None
    elif tid == "*":
        return None
    return (_parse_int(f_min), tid, ev, pr)


class _Calendar(object):
    def __init__(self, holiday_days):
        H = sorted(d for d in set(holiday_days) if d % 7 < 5)
        self.H = H
        self.K = [(d // 7) * 2400 + (d % 7) * 480 - 480 * i for i, d in enumerate(H)]

    def count(self, t):
        """Number of business minutes in [0, t)."""
        days, rem = divmod(t, 1440)
        weeks, dw = divmod(days, 7)
        part = rem - 540
        if part < 0:
            part = 0
        elif part > 480:
            part = 480
        if dw < 5:
            c = weeks * 2400 + dw * 480 + part
        else:
            c = weeks * 2400 + 2400
        H = self.H
        if H:
            idx = bisect_left(H, days)
            c -= idx * 480
            if idx < len(H) and H[idx] == days:
                c -= part
        return c

    def nth(self, c):
        """Minute of the business minute with 0-based global index c."""
        h = bisect_right(self.K, c)
        wi = c + 480 * h
        weeks, r = divmod(wi, 2400)
        dw, mod = divmod(r, 480)
        return (weeks * 7 + dw) * 1440 + 540 + mod


def _process(evs, cal, now):
    state = _NOT_OPENED
    prio = None
    used = 0
    b_last = 0
    breached_at = None
    n = len(evs)
    i = 0
    while i < n:
        m = evs[i][0]
        b_m = cal.count(m)
        if state == _RUNNING:
            gained = b_m - b_last
            if breached_at is None:
                lim = _LIMITS[prio]
                if used + gained > lim:
                    t = cal.nth(b_last + lim - used) + 1
                    if t < m:
                        breached_at = t
            used += gained
        b_last = b_m
        j = i
        while j < n and evs[j][0] == m:
            ev = evs[j][1]
            pr = evs[j][2]
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
            j += 1
        if state != _NOT_OPENED and breached_at is None and used > _LIMITS[prio]:
            breached_at = m
        i = j

    if state == _NOT_OPENED:
        return None

    if state == _RUNNING:
        b_now = cal.count(now)
        gained = b_now - b_last
        if breached_at is None:
            lim = _LIMITS[prio]
            if used + gained > lim:
                t = cal.nth(b_last + lim - used) + 1
                if t <= now:
                    breached_at = t
        used += gained

    return {
        "priority": prio,
        "used_minutes": used,
        "breached": breached_at is not None,
        "breached_at": breached_at,
        "status": _STATUS[state],
    }


def compute_sla(stream):
    holidays = set()
    tickets = {}
    now = None
    for line in stream:
        rec = _parse_line(line)
        if rec is None:
            continue
        m, tid, ev, pr = rec
        if ev == "HOLIDAY":
            holidays.add(m // 1440)
            continue
        if now is None or m > now:
            now = m
        lst = tickets.get(tid)
        if lst is None:
            lst = []
            tickets[tid] = lst
        lst.append((m, ev, pr))

    if now is None:
        return []

    cal = _Calendar(holidays)
    result = []
    for tid in sorted(tickets):
        evs = tickets[tid]
        evs.sort(key=lambda e: e[0])  # stable
        r = _process(evs, cal, now)
        if r is None:
            continue
        result.append({
            "ticket_id": tid,
            "priority": r["priority"],
            "used_minutes": r["used_minutes"],
            "breached": r["breached"],
            "breached_at": r["breached_at"],
            "status": r["status"],
        })
    return result