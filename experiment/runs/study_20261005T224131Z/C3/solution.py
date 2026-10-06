from bisect import bisect_left, bisect_right
from operator import itemgetter

_LIMITS = {'P1': 240, 'P2': 480, 'P3': 1440, 'P4': 2400}

_EV_OPEN = 0
_EV_PRIORITY = 1
_EV_PAUSE = 2
_EV_RESUME = 3
_EV_CLOSE = 4
_EV_REOPEN = 5
_EV_HOLIDAY = 6

_EVENT_CODES = {
    'OPEN': _EV_OPEN,
    'PRIORITY': _EV_PRIORITY,
    'PAUSE': _EV_PAUSE,
    'RESUME': _EV_RESUME,
    'CLOSE': _EV_CLOSE,
    'REOPEN': _EV_REOPEN,
    'HOLIDAY': _EV_HOLIDAY,
}

_NOT_OPENED = 0
_RUNNING = 1
_PAUSED = 2
_CLOSED = 3

_STATUS_NAMES = {_RUNNING: 'running', _PAUSED: 'paused', _CLOSED: 'closed'}


def _parse_int(s):
    """Parse an ASCII digit string as a base-10 integer, robust to huge inputs."""
    s = s.lstrip('0')
    if not s:
        return 0
    if len(s) <= 4000:
        return int(s)
    val = 0
    for i in range(0, len(s), 1000):
        chunk = s[i:i + 1000]
        val = val * (10 ** len(chunk)) + int(chunk)
    return val


def compute_sla(stream):
    tickets = {}
    holidays = set()
    now = None

    for line in stream:
        if not isinstance(line, str):
            continue
        s = line.strip()
        if not s:
            continue
        parts = s.split(',')
        nparts = len(parts)
        if nparts != 3 and nparts != 4:
            continue
        f1 = parts[0].strip()
        if not (f1.isdigit() and f1.isascii()):
            continue
        tid = parts[1].strip()
        if not tid:
            continue
        code = _EVENT_CODES.get(parts[2].strip())
        if code is None:
            continue
        if code == _EV_OPEN or code == _EV_PRIORITY:
            if nparts != 4:
                continue
            p = parts[3].strip()
            if p not in _LIMITS:
                continue
        else:
            if nparts != 3:
                continue
            p = None
        if code == _EV_HOLIDAY:
            if tid != '*':
                continue
            holidays.add(_parse_int(f1) // 1440)
            continue
        if tid == '*':
            continue
        m = _parse_int(f1)
        if now is None or m > now:
            now = m
        lst = tickets.get(tid)
        if lst is None:
            lst = []
            tickets[tid] = lst
        lst.append((m, code, p))

    if now is None:
        return []

    # Only weekday holidays matter for business-minute counting.
    H = sorted(d for d in holidays if d % 7 < 5)
    Hset = set(H)
    # A[i] = number of non-holiday weekdays before holiday i (non-decreasing).
    A = [((h // 7) * 5 + h % 7) - i for i, h in enumerate(H)]

    def B(t):
        """Number of business minutes in [0, t)."""
        d, rem = divmod(t, 1440)
        w, r = divmod(d, 7)
        wd = w * 5 + (r if r < 5 else 5)
        hcount = bisect_left(H, d)
        total = (wd - hcount) * 480
        if r < 5 and d not in Hset and rem > 540:
            total += (rem if rem < 1020 else 1020) - 540
        return total

    def xinv(j):
        """Minute of the j-th (1-indexed) business minute."""
        k, off = divmod(j - 1, 480)
        c = bisect_right(A, k)
        q = k + c
        day = (q // 5) * 7 + q % 5
        return day * 1440 + 540 + off

    LIM = _LIMITS
    result = []
    key0 = itemgetter(0)

    for tid, evs in tickets.items():
        evs.sort(key=key0)
        state = _NOT_OPENED
        prio = None
        U = 0
        Bcur = 0
        br = None
        opened = False
        i = 0
        n = len(evs)
        while i < n:
            m = evs[i][0]
            bm = None
            if state == _RUNNING:
                bm = B(m)
                if br is None:
                    j = Bcur + LIM[prio] - U + 1
                    if bm >= j:
                        t = xinv(j) + 1
                        if t < m:
                            br = t
                U += bm - Bcur
            while i < n:
                e = evs[i]
                if e[0] != m:
                    break
                code = e[1]
                if code == _EV_OPEN:
                    if state == _NOT_OPENED or state == _CLOSED:
                        state = _RUNNING
                        prio = e[2]
                        U = 0
                        br = None
                        opened = True
                elif code == _EV_PRIORITY:
                    if state == _RUNNING or state == _PAUSED:
                        prio = e[2]
                elif code == _EV_PAUSE:
                    if state == _RUNNING:
                        state = _PAUSED
                elif code == _EV_RESUME:
                    if state == _PAUSED:
                        state = _RUNNING
                elif code == _EV_CLOSE:
                    if state == _RUNNING or state == _PAUSED:
                        state = _CLOSED
                else:  # REOPEN
                    if state == _CLOSED:
                        state = _RUNNING
                i += 1
            if state != _NOT_OPENED and br is None and U > LIM[prio]:
                br = m
            if state == _RUNNING:
                Bcur = bm if bm is not None else B(m)

        if not opened:
            continue

        if state == _RUNNING:
            bn = B(now)
            if br is None:
                j = Bcur + LIM[prio] - U + 1
                if bn >= j:
                    br = xinv(j) + 1
            U += bn - Bcur

        result.append({
            "ticket_id": tid,
            "priority": prio,
            "used_minutes": U,
            "breached": br is not None,
            "breached_at": br,
            "status": _STATUS_NAMES[state],
        })

    result.sort(key=lambda d: d["ticket_id"])
    return result