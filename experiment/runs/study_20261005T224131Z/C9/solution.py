from bisect import bisect_left, bisect_right
from operator import itemgetter

_LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
_EVENTS = frozenset(("OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"))
_PRIOS = frozenset(_LIMITS)

_NOT_OPENED, _RUNNING, _PAUSED, _CLOSED = 0, 1, 2, 3
_STATUS = {_RUNNING: "running", _PAUSED: "paused", _CLOSED: "closed"}


def _parse_int(s):
    s = s.lstrip("0")
    if not s:
        return 0
    if len(s) <= 4000:
        return int(s)
    result = 0
    for i in range(0, len(s), 1000):
        chunk = s[i:i + 1000]
        result = result * (10 ** len(chunk)) + int(chunk)
    return result


def _parse(line):
    if not isinstance(line, str):
        return None
    parts = line.strip().split(",")
    n = len(parts)
    if n != 3 and n != 4:
        return None
    f_min = parts[0].strip()
    if not f_min or not f_min.isascii() or not f_min.isdigit():
        return None
    tid = parts[1].strip()
    if not tid:
        return None
    ev = parts[2].strip()
    if ev not in _EVENTS:
        return None
    if ev == "OPEN" or ev == "PRIORITY":
        if n != 4:
            return None
        p = parts[3].strip()
        if p not in _PRIOS:
            return None
    else:
        if n != 3:
            return None
        p = None
    if ev == "HOLIDAY":
        if tid != "*":
            return None
    elif tid == "*":
        return None
    return (_parse_int(f_min), tid, ev, p)


def _weekdays_before(d):
    q, r = divmod(d, 7)
    return q * 5 + (r if r < 5 else 5)


def compute_sla(stream):
    holidays = set()
    events = []
    for line in stream:
        rec = _parse(line)
        if rec is None:
            continue
        if rec[2] == "HOLIDAY":
            holidays.add(rec[0] // 1440)
        else:
            events.append(rec)

    if not events:
        return []

    events.sort(key=itemgetter(0))  # stable
    now = max(e[0] for e in events)

    H = sorted(d for d in holidays if d % 7 < 5)
    Hset = set(H)
    G = [_weekdays_before(d) - i for i, d in enumerate(H)]

    def B(t):
        # number of business minutes x with 0 <= x < t
        d, rem = divmod(t, 1440)
        q, r = divmod(d, 7)
        full = q * 5 + (r if r < 5 else 5) - bisect_left(H, d)
        cnt = full * 480
        if r < 5 and d not in Hset:
            x = rem - 540
            if x > 0:
                cnt += x if x < 480 else 480
        return cnt

    def kth(k):
        # minute of the k-th (1-indexed) business minute
        j, o = divmod(k - 1, 480)
        n = j + bisect_right(G, j)
        q, r = divmod(n, 5)
        return (q * 7 + r) * 1440 + 540 + o

    limits = _LIMITS

    def advance(tk, m, bound):
        # tk: [state, prio, used(last), last, B(last) or None, breached_at]
        state = tk[0]
        if state != _NOT_OPENED:
            last = tk[3]
            used = tk[2]
            if tk[5] is None:
                L = limits[tk[1]]
                if used > L:
                    tk[5] = last
                elif state == _RUNNING:
                    bl = tk[4]
                    if bl is None:
                        bl = B(last)
                        tk[4] = bl
                    t = kth(bl + L - used + 1) + 1
                    if t < bound:
                        tk[5] = t
            if state == _RUNNING:
                bl = tk[4]
                if bl is None:
                    bl = B(last)
                bm = B(m) if m != last else bl
                tk[2] = used + bm - bl
                tk[4] = bm
            else:
                if m != last:
                    tk[4] = None
        else:
            if m != tk[3]:
                tk[4] = None
        tk[3] = m

    tickets = {}
    for m, tid, ev, p in events:
        tk = tickets.get(tid)
        if tk is None:
            tk = [_NOT_OPENED, None, 0, m, None, None]
            tickets[tid] = tk
        elif tk[3] != m:
            advance(tk, m, m)

        st = tk[0]
        if ev == "OPEN":
            if st == _NOT_OPENED or st == _CLOSED:
                tk[0] = _RUNNING
                tk[1] = p
                tk[2] = 0
                tk[5] = None
        elif ev == "PRIORITY":
            if st == _RUNNING or st == _PAUSED:
                tk[1] = p
        elif ev == "PAUSE":
            if st == _RUNNING:
                tk[0] = _PAUSED
        elif ev == "RESUME":
            if st == _PAUSED:
                tk[0] = _RUNNING
        elif ev == "CLOSE":
            if st == _RUNNING or st == _PAUSED:
                tk[0] = _CLOSED
        elif ev == "REOPEN":
            if st == _CLOSED:
                tk[0] = _RUNNING

    out = []
    for tid in sorted(tickets):
        tk = tickets[tid]
        if tk[0] == _NOT_OPENED:
            continue
        advance(tk, now, now + 1)
        out.append({
            "ticket_id": tid,
            "priority": tk[1],
            "used_minutes": int(tk[2]),
            "breached": tk[5] is not None,
            "breached_at": tk[5],
            "status": _STATUS[tk[0]],
        })
    return out