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


def _parse_line(raw_line):
    s = raw_line.strip()
    if not s:
        return None
    parts = [p.strip() for p in s.split(',')]
    n = len(parts)
    if n not in (3, 4):
        return None

    m_str, ticket_id, event = parts[0], parts[1], parts[2]
    if not m_str.isdigit() or not m_str.isascii():
        return None
    minute = int(m_str)

    if not ticket_id:
        return None

    if event in ('OPEN', 'PRIORITY'):
        if n != 4:
            return None
        p = parts[3]
        if p not in LIMITS:
            return None
        if ticket_id == '*':
            return None
        return (minute, ticket_id, event, p)
    elif event == 'HOLIDAY':
        if n != 3:
            return None
        if ticket_id != '*':
            return None
        return (minute, '*', 'HOLIDAY', None)
    elif event in ('PAUSE', 'RESUME', 'CLOSE', 'REOPEN'):
        if n != 3:
            return None
        if ticket_id == '*':
            return None
        return (minute, ticket_id, event, None)
    else:
        return None


def compute_sla(stream):
    raw_ticket_events = []
    holidays = set()
    now = None

    for line in stream:
        rec = _parse_line(line)
        if rec is None:
            continue
        minute, ticket_id, event, param = rec
        if event == 'HOLIDAY':
            holidays.add(minute // 1440)
        else:
            raw_ticket_events.append((minute, ticket_id, event, param))
            if now is None or minute > now:
                now = minute

    if now is None:
        return []

    # Weekday holidays in ascending order
    effective_holidays = sorted([d for d in holidays if d % 7 < 5])
    num_holidays = len(effective_holidays)

    def biz_minutes(t):
        if t <= 0:
            return 0
        # Standard calendar calculation without holidays
        weeks = t // 10080
        rem_min = t % 10080
        rem_day = rem_min // 1440
        day_min = rem_min % 1440

        comp_b_days = min(rem_day, 5)
        std = weeks * 2400 + comp_b_days * 480
        if rem_day < 5 and day_min > 540:
            std += min(day_min - 540, 480)

        # Holiday deduction
        day = t // 1440
        idx = bisect_left(effective_holidays, day)
        ded = idx * 480
        if idx < num_holidays and effective_holidays[idx] == day:
            day_m = t % 1440
            if day_m > 540:
                ded += min(day_m - 540, 480)

        return std - ded

    def get_biz_day(n):
        # Finds the smallest calendar day D such that biz_days(D + 1) >= n + 1
        low = (n // 5) * 7 + (n % 5)
        if num_holidays == 0:
            return low
        target = n + 1
        high = low + num_holidays * 2 + 14
        while low < high:
            mid = (low + high) // 2
            d1 = mid + 1
            idx = bisect_left(effective_holidays, d1)
            bd = (d1 // 7) * 5 + min(d1 % 7, 5) - idx
            if bd >= target:
                high = mid
            else:
                low = mid + 1
        return low

    def find_minute(target_bm):
        # Smallest minute t such that biz_minutes(t) >= target_bm
        if target_bm <= 0:
            return 0
        full_days = target_bm // 480
        rem_bm = target_bm % 480
        if rem_bm == 0:
            d = get_biz_day(full_days - 1)
            return d * 1440 + 1020
        else:
            d = get_biz_day(full_days)
            return d * 1440 + 540 + rem_bm

    # Group ticket events by ticket_id preserving stream order
    events_by_ticket = defaultdict(list)
    for m, tid, ev, p in raw_ticket_events:
        events_by_ticket[tid].append((m, ev, p))

    results = []

    for tid, t_events in events_by_ticket.items():
        # Stable sort by minute
        t_events.sort(key=lambda x: x[0])

        # Group consecutive events having the same minute
        events_by_m = []
        for m, ev, p in t_events:
            if not events_by_m or events_by_m[-1][0] != m:
                events_by_m.append((m, [(ev, p)]))
            else:
                events_by_m[-1][1].append((ev, p))

        state = 'NOT_OPENED'
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        ever_opened = False
        m_prev = None

        for m, ev_list in events_by_m:
            if m_prev is not None and m > m_prev:
                if state == 'RUNNING':
                    bm = biz_minutes(m) - biz_minutes(m_prev)
                    if not breached:
                        needed = LIMITS[priority] + 1 - used_minutes
                        if bm >= needed:
                            t_br = find_minute(biz_minutes(m_prev) + needed)
                            if t_br < m:
                                breached = True
                                breached_at = t_br
                    used_minutes += bm

            for ev, p in ev_list:
                if ev == 'OPEN':
                    if state in ('NOT_OPENED', 'CLOSED'):
                        state = 'RUNNING'
                        priority = p
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        ever_opened = True
                elif ev == 'PRIORITY':
                    if state in ('RUNNING', 'PAUSED'):
                        priority = p
                elif ev == 'PAUSE':
                    if state == 'RUNNING':
                        state = 'PAUSED'
                elif ev == 'RESUME':
                    if state == 'PAUSED':
                        state = 'RUNNING'
                elif ev == 'CLOSE':
                    if state in ('RUNNING', 'PAUSED'):
                        state = 'CLOSED'
                elif ev == 'REOPEN':
                    if state == 'CLOSED':
                        state = 'RUNNING'

            if ever_opened and not breached and priority is not None:
                if used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = m

            m_prev = m

        if ever_opened:
            if m_prev is not None and now > m_prev:
                if state == 'RUNNING':
                    bm = biz_minutes(now) - biz_minutes(m_prev)
                    if not breached:
                        needed = LIMITS[priority] + 1 - used_minutes
                        if bm >= needed:
                            t_br = find_minute(biz_minutes(m_prev) + needed)
                            breached = True
                            breached_at = t_br
                    used_minutes += bm

            results.append({
                "ticket_id": tid,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": STATUS_MAP[state],
            })

    results.sort(key=lambda x: x["ticket_id"])
    return results