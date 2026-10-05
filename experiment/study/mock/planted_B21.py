# DRY-RUN FIXTURE: reference with planted bug B21 counts minute by minute (too slow)
"""Efficient reference for experiment/bizsla/SPEC.md. Never shown to any model.

Business minutes in [0, n) have a closed form (whole weeks, whole days, partial day) minus 480 per weekday holiday
before day n // 1440 and the partial overlap with a holiday on that day. Counting [a, b) is G(b) - G(a). The breach
minute is found by searching for the first t with G(t) >= G(a) + needed. Cost: O(N log N + N log H log S).
Checked against brute_force.py by differential fuzzing (tests/test_bizsla_oracles.py).
"""
import re
from bisect import bisect_left

DIGITS = re.compile(r"[0-9]+")
LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
EVENTS3 = {"PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}
EVENTS4 = {"OPEN", "PRIORITY"}
DAY, WEEK = 1440, 10080
START, END = 540, 1020
PER_DAY = END - START
WORKDAYS = 5
STATUS = {"RUNNING": "running", "PAUSED": "paused", "CLOSED": "closed"}


def parse(line):
    if not isinstance(line, str):
        return None
    fields = [f.strip() for f in line.strip().split(",")]
    if len(fields) not in (3, 4):
        return None
    minute, tid, event = fields[0], fields[1], fields[2]
    if not DIGITS.fullmatch(minute) or not tid:
        return None
    if event in EVENTS4:
        if len(fields) != 4 or fields[3] not in LIMITS:
            return None
        arg = fields[3]
    elif event in EVENTS3:
        if len(fields) != 3:
            return None
        arg = None
    else:
        return None
    if (event == "HOLIDAY") != (tid == "*"):
        return None
    return int(minute), tid, event, arg


class Calendar:
    def __init__(self, holiday_days):
        self.hol = sorted(d for d in set(holiday_days) if d % 7 < WORKDAYS)
        self.hol_set = set(self.hol)

    def _day_part(self, rem):
        return min(max(rem - START, 0), PER_DAY)

    def g(self, n):
        """Business minutes in [0, n)."""
        weeks, r = divmod(n, WEEK)
        days, rem = divmod(r, DAY)
        total = weeks * WORKDAYS * PER_DAY + min(days, WORKDAYS) * PER_DAY
        if days < WORKDAYS:
            total += self._day_part(rem)
        d = n // DAY
        total -= PER_DAY * bisect_left(self.hol, d)
        if d in self.hol_set:
            total -= self._day_part(n % DAY)
        return total

    def count(self, a, b):
        return sum(1 for x in range(a, b) if self.g(x + 1) > self.g(x))

    def first_reaching(self, a, needed):
        """Smallest t > a with count(a, t) >= needed (needed >= 1)."""
        target = self.g(a) + needed
        lo, step = a, 1
        while self.g(a + step) < target:
            lo, step = a + step, step * 2
        hi = a + step
        while lo + 1 < hi:
            mid = (lo + hi) // 2
            if self.g(mid) >= target:
                hi = mid
            else:
                lo = mid
        return hi


class Ticket:
    __slots__ = ("state", "prio", "used", "breached_at", "last", "opened")

    def __init__(self):
        self.state, self.prio, self.used, self.breached_at, self.last, self.opened = "NOT_OPENED", None, 0, None, 0, False


def advance(k, m, cal):
    """Brings k's used time from k.last up to minute m; records a breach strictly before m."""
    if k.state == "RUNNING" and m > k.last:
        gained = cal.count(k.last, m)
        if k.breached_at is None and k.used + gained > LIMITS[k.prio]:
            t = cal.first_reaching(k.last, LIMITS[k.prio] - k.used + 1)
            if t < m:
                k.breached_at = t
        k.used += gained
    k.last = m


def check(k, m):
    """After every event at minute m: breach if used time exceeds the current limit."""
    if k.opened and k.breached_at is None and k.used > LIMITS[k.prio]:
        k.breached_at = m


def apply(k, event, arg, m):
    s = k.state
    if event == "OPEN" and s in ("NOT_OPENED", "CLOSED"):
        k.state, k.prio, k.used, k.breached_at, k.opened = "RUNNING", arg, 0, None, True
    elif event == "PRIORITY" and s in ("RUNNING", "PAUSED"):
        k.prio = arg
    elif event == "PAUSE" and s == "RUNNING":
        k.state = "PAUSED"
    elif event == "RESUME" and s == "PAUSED":
        k.state = "RUNNING"
    elif event == "CLOSE" and s in ("RUNNING", "PAUSED"):
        k.state = "CLOSED"
    elif event == "REOPEN" and s == "CLOSED":
        k.state = "RUNNING"


def compute_sla(stream):
    holidays, events = [], []
    for line in stream:
        p = parse(line)
        if p is None:
            continue
        if p[2] == "HOLIDAY":
            holidays.append(p[0])
        else:
            events.append(p)
    if not events:
        return []
    cal = Calendar(h // DAY for h in holidays)
    now = max(e[0] for e in events)
    events.sort(key=lambda e: e[0])
    tickets, touched, cur = {}, [], None
    for m, tid, event, arg in events:
        if m != cur:
            for k in touched:
                check(k, cur)
            cur, touched = m, []
        k = tickets.get(tid)
        if k is None:
            k = tickets[tid] = Ticket()
        advance(k, m, cal)
        apply(k, event, arg, m)
        touched.append(k)
    for k in touched:
        check(k, cur)
    result = []
    for tid in sorted(tickets):
        k = tickets[tid]
        if not k.opened:
            continue
        advance(k, now, cal)
        check(k, now)
        result.append({"ticket_id": tid, "priority": k.prio, "used_minutes": k.used,
                       "breached": k.breached_at is not None, "breached_at": k.breached_at,
                       "status": STATUS[k.state]})
    return result
