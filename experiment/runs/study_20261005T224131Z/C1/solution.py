from bisect import bisect_left, bisect_right
from operator import itemgetter

_LIMITS = {'P1': 240, 'P2': 480, 'P3': 1440, 'P4': 2400}
_PRIOS = frozenset(('P1', 'P2', 'P3', 'P4'))

_EV_OPEN, _EV_PRIORITY, _EV_PAUSE, _EV_RESUME, _EV_CLOSE, _EV_REOPEN = range(6)
_SIMPLE_EVENTS = {
    'PAUSE': _EV_PAUSE,
    'RESUME': _EV_RESUME,
    'CLOSE': _EV_CLOSE,
    'REOPEN': _EV_REOPEN,
}

_NOT_OPENED, _RUNNING, _PAUSED, _CLOSED = range(4)
_STATUS_NAMES = {_RUNNING: 'running', _PAUSED: 'paused', _CLOSED: 'closed'}


def _parse_int(s):
    s2 = s.lstrip('0')
    if not s2:
        return 0
    try:
        return int(s2)
    except ValueError:
        # Extremely long digit strings (int/str conversion limit); convert in chunks.
        v = 0
        for i in range(0, len(s2), 1000):
            chunk = s2[i:i + 1000]
            v = v * (10 ** len(chunk)) + int(chunk)
        return v


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
        parts = s.split(',')
        nparts = len(parts)
        if nparts != 3 and nparts != 4:
            continue
        ms = parts[0].strip()
        if not ms or not ms.isascii() or not ms.isdigit():
            continue
        tid = parts[1].strip()
        if not tid:
            continue
        ev = parts[2].strip()
        if ev == 'OPEN' or ev == 'PRIORITY':
            if nparts != 4 or tid == '*':
                continue
            p = parts[3].strip()
            if p not in _PRIOS:
                continue
            code = _EV_OPEN if ev == 'OPEN' else _EV_PRIORITY
        elif ev in _SIMPLE_EVENTS:
            if nparts != 3 or tid == '*':
                continue
            p = None
            code = _SIMPLE_EVENTS[ev]
        elif ev == 'HOLIDAY':
            if nparts != 3 or tid != '*':
                continue
            holiday_days.add(_parse_int(ms) // 1440)
            continue
        else:
            continue
        m = _parse_int(ms)
        if now is None or m > now:
            now = m
        lst = tickets.get(tid)
        if lst is None:
            lst = []
            tickets[tid] = lst
        lst.append((m, code, p))

    if now is None:
        return []

    # Holidays as business-day indices (only weekdays matter).
    h = sorted({(d // 7) * 5 + (d % 7) for d in holiday_days if d % 7 < 5})
    nh = len(h)
    g = [h[i] - i for i in range(nh)]

    def B(t):
        """Number of business minutes x with 0 <= x < t."""
        d, r = divmod(t, 1440)
        w, wd = divmod(d, 7)
        if wd < 5:
            bd = w * 5 + wd
            c = bisect_left(h, bd)
            total = (bd - c) * 480
            if not (c < nh and h[c] == bd):
                if r > 540:
                    extra = r - 540
                    if extra > 480:
                        extra = 480
                    total += extra
            return total
        bd = w * 5 + 5
        c = bisect_left(h, bd)
        return (bd - c) * 480

    def inv(k):
        """Minute of the k-th (0-based) business minute."""
        q, off = divmod(k, 480)
        c = bisect_right(g, q)
        D = q + c
        w, wd = divmod(D, 5)
        return (w * 7 + wd) * 1440 + 540 + off

    results = []
    key0 = itemgetter(0)

    for tid in sorted(tickets):
        evs = tickets[tid]
        evs.sort(key=key0)  # stable: same-minute events keep stream order
        state = _NOT_OPENED
        prio = None
        used = 0
        bat = None
        opened = False
        bprev = 0
        i = 0
        n = len(evs)
        while i < n:
            m = evs[i][0]
            bm = None
            if state == _RUNNING:
                bm = B(m)
                if bat is None:
                    need = _LIMITS[prio] - used + 1
                    if need < 1:
                        need = 1
                    x = inv(bprev + need - 1)
                    if x + 1 < m:
                        bat = x + 1
                used += bm - bprev
            j = i
            while j < n and evs[j][0] == m:
                _, code, p = evs[j]
                if code == _EV_OPEN:
                    if state == _NOT_OPENED or state == _CLOSED:
                        state = _RUNNING
                        prio = p
                        used = 0
                        bat = None
                        opened = True
                elif code == _EV_PRIORITY:
                    if state == _RUNNING or state == _PAUSED:
                        prio = p
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
                j += 1
            i = j
            if state != _NOT_OPENED and bat is None and used > _LIMITS[prio]:
                bat = m
            if state == _RUNNING:
                bprev = bm if bm is not None else B(m)
            prev = m

        if not opened:
            continue

        if state == _RUNNING and prev < now:
            bnow = B(now)
            if bat is None:
                need = _LIMITS[prio] - used + 1
                if need < 1:
                    need = 1
                x = inv(bprev + need - 1)
                if x + 1 <= now:
                    bat = x + 1
            used += bnow - bprev

        results.append({
            "ticket_id": tid,
            "priority": prio,
            "used_minutes": used,
            "breached": bat is not None,
            "breached_at": bat,
            "status": _STATUS_NAMES[state],
        })

    return results