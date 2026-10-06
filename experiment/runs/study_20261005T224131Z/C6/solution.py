from bisect import bisect_left, bisect_right
from operator import itemgetter

_LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
_EVENTS = frozenset(["OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"])

_NOT_OPENED, _RUNNING, _PAUSED, _CLOSED = 0, 1, 2, 3
_STATUS = {_RUNNING: "running", _PAUSED: "paused", _CLOSED: "closed"}


def _parse_int(s):
    s = s.lstrip("0") or "0"
    try:
        return int(s)
    except ValueError:
        v = 0
        for i in range(0, len(s), 1000):
            chunk = s[i:i + 1000]
            v = v * (10 ** len(chunk)) + int(chunk)
        return v


def _is_ascii_digits(s):
    if not s:
        return False
    try:
        if not s.isascii():
            return False
    except AttributeError:  # very old Python fallback
        return all("0" <= c <= "9" for c in s)
    return s.isdigit()


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
        parts = [p.strip() for p in parts]
        ms, tid, ev = parts[0], parts[1], parts[2]
        if not _is_ascii_digits(ms):
            continue
        if not tid:
            continue
        if ev not in _EVENTS:
            continue
        prio = None
        if ev == "OPEN" or ev == "PRIORITY":
            if n != 4:
                continue
            prio = parts[3]
            if prio not in _LIMITS:
                continue
        else:
            if n != 3:
                continue
        if ev == "HOLIDAY":
            if tid != "*":
                continue
            holiday_days.add(_parse_int(ms) // 1440)
            continue
        if tid == "*":
            continue
        m = _parse_int(ms)
        if now is None or m > now:
            now = m
        lst = tickets.get(tid)
        if lst is None:
            lst = []
            tickets[tid] = lst
        lst.append((m, ev, prio))

    if now is None:
        return []

    # Holiday calendar restricted to weekdays.
    hol_set = set()
    hw_list = []
    for d in holiday_days:
        wk, wd = divmod(d, 7)
        if wd < 5:
            hol_set.add(d)
            hw_list.append(wk * 5 + wd)
    hw = sorted(hw_list)
    keys = [hw[i] - i for i in range(len(hw))]

    def F(t):
        # number of business minutes in [0, t)
        d, rem = divmod(t, 1440)
        wk, wd = divmod(d, 7)
        if wd < 5:
            WB = wk * 5 + wd
            res = (WB - bisect_left(hw, WB)) * 480
            if d not in hol_set:
                r = rem - 540
                if r > 0:
                    res += r if r < 480 else 480
        else:
            WB = wk * 5 + 5
            res = (WB - bisect_left(hw, WB)) * 480
        return res

    def nth(j):
        # the business minute with 0-based index j
        nday, off = divmod(j, 480)
        W = nday + bisect_right(keys, nday)
        wk, wd = divmod(W, 5)
        return (wk * 7 + wd) * 1440 + 540 + off

    F_now = F(now)
    results = []

    for tid in sorted(tickets):
        evs = tickets[tid]
        evs.sort(key=itemgetter(0))
        state = _NOT_OPENED
        prio = None
        used = 0
        breach = None
        opened = False
        last_t = None
        F_last = None
        i = 0
        L = len(evs)
        while i < L:
            t = evs[i][0]
            Ft = None
            # Advance from last_t to t.
            if state == _RUNNING:
                Ft = F(t)
                gain = Ft - F_last
                if breach is None and gain > 0:
                    need = _LIMITS[prio] - used + 1
                    if gain >= need:
                        tb = nth(F_last + need - 1) + 1
                        if tb < t:
                            breach = tb
                used += gain
            # Apply all events at minute t.
            while i < L and evs[i][0] == t:
                _, ev, p = evs[i]
                i += 1
                if ev == "OPEN":
                    if state == _NOT_OPENED or state == _CLOSED:
                        state = _RUNNING
                        prio = p
                        used = 0
                        breach = None
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
            # Check breach at minute t.
            if state != _NOT_OPENED and breach is None and used > _LIMITS[prio]:
                breach = t
            last_t = t
            if state == _RUNNING:
                F_last = Ft if Ft is not None else F(t)
            else:
                F_last = None

        # Final segment up to now (inclusive for breach).
        if state == _RUNNING and now > last_t:
            gain = F_now - F_last
            if breach is None and gain > 0:
                need = _LIMITS[prio] - used + 1
                if gain >= need:
                    breach = nth(F_last + need - 1) + 1
            used += gain

        if not opened:
            continue
        results.append({
            "ticket_id": tid,
            "priority": prio,
            "used_minutes": used,
            "breached": breach is not None,
            "breached_at": breach,
            "status": _STATUS[state],
        })

    return results