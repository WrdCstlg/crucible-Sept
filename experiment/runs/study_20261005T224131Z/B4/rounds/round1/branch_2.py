import bisect
import itertools

PRIORITY_LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}

VALID_EVENTS_3 = {'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'}
VALID_EVENTS_4 = {'OPEN', 'PRIORITY'}
VALID_PRIORITIES = {'P1', 'P2', 'P3', 'P4'}


def _raw_business_minutes_before(m: int) -> int:
    """Return the number of business minutes in [0, m) ignoring holidays."""
    if m <= 540:
        return 0
    w = m // 10080
    rem = m % 10080
    day = rem // 1440
    mod = rem % 1440

    total = w * 2400
    if day < 5:
        total += day * 480
        if mod > 540:
            total += min(mod, 1020) - 540
    else:
        total += 5 * 480
    return total


def _raw_business_minutes(start: int, end: int) -> int:
    if start >= end:
        return 0
    return _raw_business_minutes_before(end) - _raw_business_minutes_before(start)


def compute_sla(stream):
    """
    Compute SLA metrics for tickets in stream.
    Uses an event sweep that rebuilds each ticket's running intervals,
    then counts business minutes per interval.
    """
    holiday_days = set()
    ticket_events = []
    max_ticket_minute = None

    for line_idx, line in enumerate(stream):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        n_parts = len(parts)
        if n_parts not in (3, 4):
            continue

        f1, f2, f3 = parts[0], parts[1], parts[2]

        # Field 1: ASCII digits 0-9
        if not (f1.isascii() and f1.isdigit()):
            continue
        minute = int(f1)

        # Field 2: non-empty ticket ID
        if not f2:
            continue

        # Event validation
        if f3 in VALID_EVENTS_4:
            if n_parts != 4:
                continue
            f4 = parts[3]
            if f4 not in VALID_PRIORITIES:
                continue
            if f2 == '*':
                continue
            ticket_events.append((minute, line_idx, f2, f3, f4))
            if max_ticket_minute is None or minute > max_ticket_minute:
                max_ticket_minute = minute
        elif f3 in VALID_EVENTS_3:
            if n_parts != 3:
                continue
            if f3 == 'HOLIDAY':
                if f2 != '*':
                    continue
                holiday_days.add(minute // 1440)
            else:
                if f2 == '*':
                    continue
                ticket_events.append((minute, line_idx, f2, f3, None))
                if max_ticket_minute is None or minute > max_ticket_minute:
                    max_ticket_minute = minute
        else:
            continue

    if not ticket_events:
        return []

    now = max_ticket_minute

    # Calendar: filter holidays to weekdays only (weekdays 0-4 have business hours)
    weekday_holidays_set = {d for d in holiday_days if (d % 7) < 5}
    weekday_holidays_list = sorted(weekday_holidays_set)

    def count_business_minutes(start: int, end: int) -> int:
        if start >= end:
            return 0
        raw = _raw_business_minutes(start, end)
        if not weekday_holidays_set or raw == 0:
            return raw

        d_start = start // 1440
        d_end = end // 1440

        if d_start == d_end:
            if d_start in weekday_holidays_set:
                return 0
            return raw

        holiday_mins = 0
        if d_start in weekday_holidays_set:
            holiday_mins += _raw_business_minutes(start, (d_start + 1) * 1440)
        if d_end in weekday_holidays_set:
            holiday_mins += _raw_business_minutes(d_end * 1440, end)

        idx_lo = bisect.bisect_right(weekday_holidays_list, d_start)
        idx_hi = bisect.bisect_left(weekday_holidays_list, d_end)
        if idx_hi > idx_lo:
            holiday_mins += (idx_hi - idx_lo) * 480

        return max(0, raw - holiday_mins)

    def find_minute_for_business_minutes(start: int, end: int, needed: int) -> int:
        low = start + 1
        high = end
        while low < high:
            mid = (low + high) // 2
            if count_business_minutes(start, mid) >= needed:
                high = mid
            else:
                low = mid + 1
        return low

    # Group ticket events by ticket_id
    tickets_map = {}
    for minute, line_idx, ticket_id, event_type, priority_arg in ticket_events:
        if ticket_id not in tickets_map:
            tickets_map[ticket_id] = []
        tickets_map[ticket_id].append((minute, line_idx, event_type, priority_arg))

    results = []

    # Process tickets in code-point order
    for ticket_id in sorted(tickets_map.keys()):
        events = tickets_map[ticket_id]
        events.sort(key=lambda x: (x[0], x[1]))

        # Group events by minute
        grouped_events = []
        for minute, grp in itertools.groupby(events, key=lambda x: x[0]):
            grouped_events.append((minute, [(x[2], x[3]) for x in grp]))

        # Ensure timeline extends to now
        if grouped_events[-1][0] < now:
            grouped_events.append((now, []))

        status = 'not_opened'
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        prev_minute = None

        # Event sweep rebuilding running intervals and accumulating business minutes
        for curr_minute, events_at_curr in grouped_events:
            if prev_minute is not None:
                if status == 'running':
                    bm = count_business_minutes(prev_minute, curr_minute)
                    if not breached:
                        limit = PRIORITY_LIMITS[priority]
                        needed = (limit + 1) - used_minutes
                        if needed <= bm:
                            t = find_minute_for_business_minutes(prev_minute, curr_minute, needed)
                            if t < curr_minute:
                                breached = True
                                breached_at = t
                    used_minutes += bm

            # Apply all events at curr_minute in stream order
            for event_type, p_arg in events_at_curr:
                if event_type == 'OPEN':
                    if status in ('not_opened', 'closed'):
                        status = 'running'
                        priority = p_arg
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif event_type == 'PRIORITY':
                    if status in ('running', 'paused'):
                        priority = p_arg
                elif event_type == 'PAUSE':
                    if status == 'running':
                        status = 'paused'
                elif event_type == 'RESUME':
                    if status == 'paused':
                        status = 'running'
                elif event_type == 'CLOSE':
                    if status in ('running', 'paused'):
                        status = 'closed'
                elif event_type == 'REOPEN':
                    if status == 'closed':
                        status = 'running'

            # Breach check after all events at curr_minute have taken effect
            if had_valid_open and not breached and curr_minute <= now:
                if used_minutes > PRIORITY_LIMITS[priority]:
                    breached = True
                    breached_at = curr_minute

            prev_minute = curr_minute

        if had_valid_open:
            results.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": status,
            })

    return results