from bisect import bisect_left
from collections import defaultdict

LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}


def count_weekdays(d):
    """Number of weekdays (Monday-Friday) in [0, d)."""
    if d <= 0:
        return 0
    return (d // 7) * 5 + min(d % 7, 5)


def compute_sla(stream):
    """
    Computes SLA metrics for tickets using an event sweep approach:
    rebuilds each ticket's running intervals, then counts business minutes per interval.
    """
    holiday_days = set()
    ticket_events = defaultdict(list)
    has_ticket_events = False
    now = -1

    # 1. Parse stream
    for line_idx, raw_line in enumerate(stream):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(',')
        if len(parts) not in (3, 4):
            continue
        fields = [p.strip() for p in parts]
        m_str, ticket_id, event = fields[0], fields[1], fields[2]

        if not m_str or not m_str.isascii() or not m_str.isdigit():
            continue
        m = int(m_str)

        if not ticket_id:
            continue

        if len(fields) == 4:
            if event not in ('OPEN', 'PRIORITY'):
                continue
            priority = fields[3]
            if priority not in LIMITS:
                continue
            if ticket_id == '*':
                continue
            has_ticket_events = True
            if m > now:
                now = m
            ticket_events[ticket_id].append((m, line_idx, event, priority))
        else:
            if event not in ('PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'):
                continue
            if event == 'HOLIDAY':
                if ticket_id != '*':
                    continue
                day = m // 1440
                if day % 7 < 5:
                    holiday_days.add(day)
            else:
                if ticket_id == '*':
                    continue
                has_ticket_events = True
                if m > now:
                    now = m
                ticket_events[ticket_id].append((m, line_idx, event, None))

    if not has_ticket_events:
        return []

    sorted_holidays = sorted(holiday_days)

    def is_biz_day(d):
        return (d % 7 < 5) and (d not in holiday_days)

    def count_biz_days(d1, d2):
        if d1 >= d2:
            return 0
        total_weekdays = count_weekdays(d2) - count_weekdays(d1)
        i1 = bisect_left(sorted_holidays, d1)
        i2 = bisect_left(sorted_holidays, d2)
        return total_weekdays - (i2 - i1)

    def count_business_minutes(t1, t2):
        if t1 >= t2:
            return 0
        d1 = t1 // 1440
        d2 = t2 // 1440
        if d1 == d2:
            if is_biz_day(d1):
                m1 = t1 % 1440
                m2 = t2 % 1440
                return max(0, min(m2, 1020) - max(m1, 540))
            return 0

        total = 0
        if is_biz_day(d1):
            m1 = t1 % 1440
            total += max(0, 1020 - max(m1, 540))

        if d2 > d1 + 1:
            total += count_biz_days(d1 + 1, d2) * 480

        if is_biz_day(d2):
            m2 = t2 % 1440
            total += max(0, min(m2, 1020) - 540)

        return total

    def find_kth_business_minute(start_t, k):
        """Finds the minute b of the k-th business minute (k >= 1) after start_t."""
        d = start_t // 1440
        if is_biz_day(d):
            m_day = start_t % 1440
            if m_day < 1020:
                biz_start = max(540, m_day)
                avail = 1020 - biz_start
                if k <= avail:
                    return d * 1440 + biz_start + (k - 1)
                k -= avail

        full_days = (k - 1) // 480
        rem_k = (k - 1) % 480 + 1
        target_biz_day_index = full_days + 1

        d_start = d + 1
        low = d_start + target_biz_day_index
        high = d_start + (target_biz_day_index + len(holiday_days) + 5) * 7 // 5 + 14
        while count_biz_days(d_start, high) < target_biz_day_index:
            high += (high - d_start) + 14

        while low < high:
            mid = (low + high) // 2
            if count_biz_days(d_start, mid) >= target_biz_day_index:
                high = mid
            else:
                low = mid + 1
        target_day = low - 1
        return target_day * 1440 + 540 + (rem_k - 1)

    # 2. Event sweep per ticket: rebuild running intervals and count business minutes
    results = []

    for ticket_id in sorted(ticket_events.keys()):
        raw_events = ticket_events[ticket_id]
        # Sort events stably by minute, then stream order
        raw_events.sort(key=lambda x: (x[0], x[1]))

        # Group events by minute
        minute_groups = defaultdict(list)
        distinct_minutes = []
        for m, idx, ev, prio in raw_events:
            if not minute_groups[m]:
                distinct_minutes.append(m)
            minute_groups[m].append((ev, prio))

        state = 'NOT_OPENED'
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False

        prev_m = None

        for m in distinct_minutes:
            events_at_m = minute_groups[m]

            # Rebuild interval [prev_m, m)
            if prev_m is not None and prev_m < m:
                if state == 'RUNNING':
                    bm = count_business_minutes(prev_m, m)
                    if not breached and had_valid_open:
                        limit = LIMITS[priority]
                        if used_minutes + bm > limit:
                            k_needed = limit - used_minutes + 1
                            b = find_kth_business_minute(prev_m, k_needed)
                            # If breach strictly precedes minute m, it occurred during the interval
                            if b + 1 < m:
                                breached = True
                                breached_at = b + 1
                    used_minutes += bm

            # Apply all events at minute m in stream order
            for ev, prio in events_at_m:
                if ev == 'OPEN':
                    if state in ('NOT_OPENED', 'CLOSED'):
                        state = 'RUNNING'
                        priority = prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif ev == 'PRIORITY':
                    if state in ('RUNNING', 'PAUSED'):
                        priority = prio
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

            # After every event at minute m has been applied, check for breach at minute m
            if had_valid_open and not breached:
                if used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = m

            prev_m = m

        # Sweep final interval from last event minute up to now
        if prev_m is not None and prev_m < now:
            if state == 'RUNNING':
                bm = count_business_minutes(prev_m, now)
                if not breached and had_valid_open:
                    limit = LIMITS[priority]
                    if used_minutes + bm > limit:
                        k_needed = limit - used_minutes + 1
                        b = find_kth_business_minute(prev_m, k_needed)
                        breached = True
                        breached_at = b + 1
                used_minutes += bm

        if had_valid_open:
            results.append({
                'ticket_id': ticket_id,
                'priority': priority,
                'used_minutes': used_minutes,
                'breached': breached,
                'breached_at': breached_at,
                'status': state.lower(),
            })

    return results