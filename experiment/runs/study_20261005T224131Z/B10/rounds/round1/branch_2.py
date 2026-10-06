import bisect
from collections import defaultdict

LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400
}

STATUS_MAP = {
    'RUNNING': 'running',
    'PAUSED': 'paused',
    'CLOSED': 'closed'
}


def _count_weekdays_up_to(day):
    """Return the number of weekdays (Monday-Friday) in [0, day]."""
    if day < 0:
        return 0
    weeks = day // 7
    rem = day % 7
    return weeks * 5 + min(rem + 1, 5)


def _business_minutes_between(start, end, holiday_set, weekday_holidays):
    """Count business minutes in the half-open interval [start, end)."""
    if start >= end:
        return 0

    d_start = start // 1440
    m_start = start % 1440
    d_end = end // 1440
    m_end = end % 1440

    if d_start == d_end:
        if d_start in holiday_set or (d_start % 7) >= 5:
            return 0
        return max(0, min(m_end, 1020) - max(m_start, 540))

    total = 0

    # Start day
    if d_start not in holiday_set and (d_start % 7) < 5:
        total += max(0, 1020 - max(m_start, 540))

    # End day
    if d_end not in holiday_set and (d_end % 7) < 5:
        total += max(0, min(m_end, 1020) - 540)

    # Full days in [d_start + 1, d_end - 1]
    d1 = d_start + 1
    d2 = d_end - 1
    if d1 <= d2:
        std_days = _count_weekdays_up_to(d2) - _count_weekdays_up_to(d1 - 1)
        idx1 = bisect.bisect_left(weekday_holidays, d1)
        idx2 = bisect.bisect_right(weekday_holidays, d2)
        hols = max(0, idx2 - idx1)
        actual_days = std_days - hols
        total += actual_days * 480

    return total


def _find_breach_minute(start, end, needed, holiday_set, weekday_holidays):
    """
    Find the smallest minute t in [start + 1, end] such that
    business_minutes_between(start, t) == needed.
    """
    low = start + 1
    high = end
    ans = end
    while low <= high:
        mid = (low + high) // 2
        if _business_minutes_between(start, mid, holiday_set, weekday_holidays) >= needed:
            ans = mid
            high = mid - 1
        else:
            low = mid + 1
    return ans


def compute_sla(stream):
    """
    Compute SLA statistics for tickets from a stream of CSV records.
    """
    holiday_set = set()
    ticket_events_by_id = defaultdict(list)
    has_ticket_events = False
    now = -1

    # Parse stream records
    stream_idx = 0
    for raw_line in stream:
        line = raw_line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) not in (3, 4):
            continue

        f0 = parts[0]
        if not f0 or not f0.isascii() or not f0.isdigit():
            continue
        minute = int(f0)

        tid = parts[1]
        if not tid:
            continue

        evt = parts[2]
        if evt == 'HOLIDAY':
            if len(parts) != 3 or tid != '*':
                continue
            holiday_set.add(minute // 1440)
            continue

        if tid == '*':
            continue

        if evt in ('OPEN', 'PRIORITY'):
            if len(parts) != 4 or parts[3] not in ('P1', 'P2', 'P3', 'P4'):
                continue
            prio = parts[3]
        elif evt in ('PAUSE', 'RESUME', 'CLOSE', 'REOPEN'):
            if len(parts) != 3:
                continue
            prio = None
        else:
            continue

        has_ticket_events = True
        if minute > now:
            now = minute
        ticket_events_by_id[tid].append((minute, stream_idx, evt, prio))
        stream_idx += 1

    if not has_ticket_events:
        return []

    weekday_holidays = sorted(d for d in holiday_set if d % 7 < 5)

    results = []

    # Process tickets in code-point order
    for tid in sorted(ticket_events_by_id.keys()):
        raw_events = ticket_events_by_id[tid]
        raw_events.sort(key=lambda x: (x[0], x[1]))

        # Group events by minute
        events_by_minute = defaultdict(list)
        distinct_minutes = []
        for m, _, evt, prio in raw_events:
            if m not in events_by_minute:
                distinct_minutes.append(m)
            events_by_minute[m].append((evt, prio))

        state = 'NOT_OPENED'
        priority = None
        had_valid_open = False
        used_minutes = 0
        breached = False
        breached_at = None
        last_m = None

        # Sweep through event minutes
        for curr_m in distinct_minutes:
            if state == 'RUNNING':
                start = last_m
                end = curr_m
                biz = _business_minutes_between(start, end, holiday_set, weekday_holidays)
                if not breached:
                    limit = LIMITS[priority]
                    needed = (limit + 1) - used_minutes
                    if needed <= 0:
                        breached = True
                        breached_at = start
                    elif biz >= needed:
                        t = _find_breach_minute(start, end, needed, holiday_set, weekday_holidays)
                        if t < end:
                            breached = True
                            breached_at = t
                used_minutes += biz

            # Apply all events at curr_m in order
            for evt, p_arg in events_by_minute[curr_m]:
                if evt == 'OPEN':
                    if state == 'NOT_OPENED':
                        state = 'RUNNING'
                        priority = p_arg
                        had_valid_open = True
                        used_minutes = 0
                        breached = False
                        breached_at = None
                    elif state == 'CLOSED':
                        state = 'RUNNING'
                        priority = p_arg
                        used_minutes = 0
                        breached = False
                        breached_at = None
                elif evt == 'PRIORITY':
                    if state in ('RUNNING', 'PAUSED'):
                        priority = p_arg
                elif evt == 'PAUSE':
                    if state == 'RUNNING':
                        state = 'PAUSED'
                elif evt == 'RESUME':
                    if state == 'PAUSED':
                        state = 'RUNNING'
                elif evt == 'CLOSE':
                    if state in ('RUNNING', 'PAUSED'):
                        state = 'CLOSED'
                elif evt == 'REOPEN':
                    if state == 'CLOSED':
                        state = 'RUNNING'

            # Check breach at curr_m after all events at curr_m
            if had_valid_open and not breached and priority is not None:
                limit = LIMITS[priority]
                if used_minutes > limit:
                    breached = True
                    breached_at = curr_m

            last_m = curr_m

        if not had_valid_open:
            continue

        # Advance from last_m to now
        if last_m < now:
            if state == 'RUNNING':
                start = last_m
                end = now
                biz = _business_minutes_between(start, end, holiday_set, weekday_holidays)
                if not breached:
                    limit = LIMITS[priority]
                    needed = (limit + 1) - used_minutes
                    if needed <= 0:
                        breached = True
                        breached_at = start
                    elif biz >= needed:
                        t = _find_breach_minute(start, end, needed, holiday_set, weekday_holidays)
                        if t < end:
                            breached = True
                            breached_at = t
                used_minutes += biz

            if not breached and priority is not None:
                limit = LIMITS[priority]
                if used_minutes > limit:
                    breached = True
                    breached_at = now

        results.append({
            "ticket_id": tid,
            "priority": priority,
            "used_minutes": used_minutes,
            "breached": breached,
            "breached_at": breached_at,
            "status": STATUS_MAP[state]
        })

    return results