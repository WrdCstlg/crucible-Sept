from bisect import bisect_left, bisect_right
from collections import defaultdict

LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}

STATUS_MAP = {
    'RUNNING': 'running',
    'PAUSED': 'paused',
    'CLOSED': 'closed',
}


def standard_business_minutes_prefix(m: int) -> int:
    if m <= 0:
        return 0
    d, mod = divmod(m, 1440)
    weeks, rem = divmod(d, 7)
    res = weeks * 2400 + min(rem, 5) * 480
    if rem < 5:
        res += max(0, min(mod, 1020) - 540)
    return res


def compute_sla(stream):
    ticket_events = []
    holidays = set()

    for line in stream:
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) not in (3, 4):
            continue

        m_str, tid, ev = parts[0], parts[1], parts[2]
        if not (m_str.isascii() and m_str.isdigit()):
            continue
        m = int(m_str)
        if not tid:
            continue

        if ev == 'HOLIDAY':
            if len(parts) != 3 or tid != '*':
                continue
            holidays.add(m // 1440)
        elif tid == '*':
            continue
        elif ev in ('OPEN', 'PRIORITY'):
            if len(parts) != 4:
                continue
            p = parts[3]
            if p not in LIMITS:
                continue
            ticket_events.append((m, len(ticket_events), tid, ev, p))
        elif ev in ('PAUSE', 'RESUME', 'CLOSE', 'REOPEN'):
            if len(parts) != 3:
                continue
            ticket_events.append((m, len(ticket_events), tid, ev, None))
        else:
            continue

    if not ticket_events:
        return []

    now = max(ev[0] for ev in ticket_events)

    # Sort ticket events: primary by minute, secondary by original stream arrival order
    ticket_events.sort(key=lambda x: (x[0], x[1]))

    business_holidays = sorted(d for d in holidays if d % 7 < 5)
    business_holidays_set = set(business_holidays)

    def count_business_minutes(m1: int, m2: int) -> int:
        if m1 >= m2:
            return 0
        std = standard_business_minutes_prefix(m2) - standard_business_minutes_prefix(m1)
        if std == 0 or not business_holidays:
            return std

        d1 = m1 // 1440
        d2 = m2 // 1440

        if d1 == d2:
            if d1 in business_holidays_set:
                std -= max(0, min(m2, d1 * 1440 + 1020) - max(m1, d1 * 1440 + 540))
            return std

        if d1 in business_holidays_set:
            std -= max(0, d1 * 1440 + 1020 - max(m1, d1 * 1440 + 540))
        if d2 in business_holidays_set:
            std -= max(0, min(m2, d2 * 1440 + 1020) - (d2 * 1440 + 540))

        left = bisect_right(business_holidays, d1)
        right = bisect_left(business_holidays, d2)
        if right > left:
            std -= (right - left) * 480

        return std

    def find_kth_business_minute(start: int, end: int, k: int) -> int:
        lo = start
        hi = end - 1
        ans = hi
        while lo <= hi:
            mid = (lo + hi) // 2
            if count_business_minutes(start, mid + 1) >= k:
                ans = mid
                hi = mid - 1
            else:
                lo = mid + 1
        return ans

    # Group ticket events by ticket_id preserving chronological order
    tickets_events = defaultdict(list)
    for m, _, tid, ev, p in ticket_events:
        tickets_events[tid].append((m, ev, p))

    results = []

    for tid, ev_list in tickets_events.items():
        # Collapse events at the same minute into groups
        events_by_m = []
        for m, ev, p in ev_list:
            if events_by_m and events_by_m[-1][0] == m:
                events_by_m[-1][1].append((ev, p))
            else:
                events_by_m.append((m, [(ev, p)]))

        # Ensure sweep continues up to 'now'
        if events_by_m[-1][0] < now:
            events_by_m.append((now, []))

        status = 'NOT_OPENED'
        priority = None
        used = 0
        breached = False
        breached_at = None
        has_valid_open = False

        n_pts = len(events_by_m)
        for i in range(n_pts):
            m_curr, evs = events_by_m[i]

            # Apply all events taking effect at the start of minute m_curr
            for ev, p in evs:
                if ev == 'OPEN':
                    if status == 'NOT_OPENED':
                        status = 'RUNNING'
                        priority = p
                        used = 0
                        breached = False
                        breached_at = None
                        has_valid_open = True
                    elif status == 'CLOSED':
                        status = 'RUNNING'
                        priority = p
                        used = 0
                        breached = False
                        breached_at = None
                        has_valid_open = True
                elif ev == 'PRIORITY':
                    if status in ('RUNNING', 'PAUSED'):
                        priority = p
                elif ev == 'PAUSE':
                    if status == 'RUNNING':
                        status = 'PAUSED'
                elif ev == 'RESUME':
                    if status == 'PAUSED':
                        status = 'RUNNING'
                elif ev == 'CLOSE':
                    if status in ('RUNNING', 'PAUSED'):
                        status = 'CLOSED'
                elif ev == 'REOPEN':
                    if status == 'CLOSED':
                        status = 'RUNNING'

            # Breach check at m_curr after all events at m_curr have been applied
            if has_valid_open and status != 'NOT_OPENED' and not breached:
                if used > LIMITS[priority]:
                    breached = True
                    breached_at = m_curr

            # Sweep through the interval [m_curr, m_next)
            if i + 1 < n_pts:
                m_next = events_by_m[i + 1][0]
                if status == 'RUNNING':
                    b = count_business_minutes(m_curr, m_next)
                    if not breached:
                        needed = LIMITS[priority] + 1 - used
                        if b >= needed:
                            x = find_kth_business_minute(m_curr, m_next, needed)
                            # If x + 1 < m_next, the breach occurred with no events at x + 1
                            if x + 1 < m_next:
                                breached = True
                                breached_at = x + 1
                            # If x + 1 == m_next, the breach is checked at m_next after events at m_next
                    used += b

        if has_valid_open:
            results.append({
                "ticket_id": tid,
                "priority": priority,
                "used_minutes": used,
                "breached": breached,
                "breached_at": breached_at,
                "status": STATUS_MAP[status],
            })

    results.sort(key=lambda d: d["ticket_id"])
    return results