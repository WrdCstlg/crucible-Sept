import bisect
from collections import defaultdict

PRIORITY_LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}

VALID_EVENTS_4 = {'OPEN', 'PRIORITY'}
VALID_EVENTS_3 = {'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'}
VALID_PRIORITIES = {'P1', 'P2', 'P3', 'P4'}


def _parse_line(raw_line):
    s = raw_line.strip()
    if not s:
        return None
    parts = [p.strip() for p in s.split(',')]
    n = len(parts)
    if n not in (3, 4):
        return None

    f1, f2, f3 = parts[0], parts[1], parts[2]

    if not (f1.isascii() and f1.isdigit()):
        return None
    minute = int(f1)

    if not f2:
        return None

    if f3 in VALID_EVENTS_4:
        if n != 4:
            return None
        f4 = parts[3]
        if f4 not in VALID_PRIORITIES:
            return None
        priority = f4
    elif f3 in VALID_EVENTS_3:
        if n != 3:
            return None
        priority = None
    else:
        return None

    if f3 == 'HOLIDAY':
        if f2 != '*':
            return None
    else:
        if f2 == '*':
            return None

    return minute, f2, f3, priority


def _build_calendar(holidays_set):
    eff_holidays_set = {d for d in holidays_set if d % 7 < 5}
    h_list = sorted(eff_holidays_set)

    def count_business_minutes(m):
        """Returns the number of business minutes in [0, m)."""
        if m <= 0:
            return 0
        d = m // 1440
        mod = m % 1440

        weeks = d // 7
        rem = d % 7
        b_days = weeks * 5 + (rem if rem < 5 else 5)
        b_days -= bisect.bisect_left(h_list, d)

        total = b_days * 480
        if d % 7 < 5 and d not in eff_holidays_set:
            if mod > 540:
                total += min(mod, 1020) - 540

        return total

    return count_business_minutes


def _find_breach_minute(count_bus_mins, t_start, t_end, target):
    """
    Finds the smallest minute t in [t_start, t_end] such that
    count_bus_mins(t) >= target.
    """
    lo = t_start
    hi = t_end
    while lo < hi:
        mid = (lo + hi) // 2
        if count_bus_mins(mid) >= target:
            hi = mid
        else:
            lo = mid + 1
    return lo


def compute_sla(stream):
    ticket_events_by_id = defaultdict(list)
    holidays_set = set()
    has_ticket_events = False
    max_minute = -1

    for line_idx, raw_line in enumerate(stream):
        parsed = _parse_line(raw_line)
        if parsed is None:
            continue
        minute, ticket_id, event_type, priority = parsed
        if event_type == 'HOLIDAY':
            holidays_set.add(minute // 1440)
        else:
            has_ticket_events = True
            if minute > max_minute:
                max_minute = minute
            ticket_events_by_id[ticket_id].append((minute, line_idx, event_type, priority))

    if not has_ticket_events:
        return []

    now = max_minute
    count_bus_mins = _build_calendar(holidays_set)

    status_map = {
        'RUNNING': 'running',
        'PAUSED': 'paused',
        'CLOSED': 'closed',
    }

    results = []

    for ticket_id in sorted(ticket_events_by_id.keys()):
        raw_events = ticket_events_by_id[ticket_id]
        raw_events.sort(key=lambda x: (x[0], x[1]))

        # Group events by minute
        grouped_events = []
        for evt in raw_events:
            m = evt[0]
            if grouped_events and grouped_events[-1][0] == m:
                grouped_events[-1][1].append(evt)
            else:
                grouped_events.append((m, [evt]))

        state = 'NOT_OPENED'
        priority = None
        used = 0
        breached = False
        breached_at = None
        ever_opened = False
        last_minute = None

        for m, evts in grouped_events:
            if state != 'NOT_OPENED' and last_minute < m:
                if state == 'RUNNING':
                    bus_mins = count_bus_mins(m) - count_bus_mins(last_minute)
                    if not breached:
                        limit = PRIORITY_LIMITS[priority]
                        needed = limit + 1 - used
                        if bus_mins >= needed:
                            target = count_bus_mins(last_minute) + needed
                            t = _find_breach_minute(count_bus_mins, last_minute, m, target)
                            if t < m:
                                breached = True
                                breached_at = t
                    used += bus_mins
                last_minute = m
            elif last_minute is None:
                last_minute = m

            # Apply all events at minute m in order
            for _, _, event_type, evt_prio in evts:
                if event_type == 'OPEN':
                    if state in ('NOT_OPENED', 'CLOSED'):
                        state = 'RUNNING'
                        priority = evt_prio
                        used = 0
                        breached = False
                        breached_at = None
                        ever_opened = True
                elif event_type == 'PRIORITY':
                    if state in ('RUNNING', 'PAUSED'):
                        priority = evt_prio
                elif event_type == 'PAUSE':
                    if state == 'RUNNING':
                        state = 'PAUSED'
                elif event_type == 'RESUME':
                    if state == 'PAUSED':
                        state = 'RUNNING'
                elif event_type == 'CLOSE':
                    if state in ('RUNNING', 'PAUSED'):
                        state = 'CLOSED'
                elif event_type == 'REOPEN':
                    if state == 'CLOSED':
                        state = 'RUNNING'

            # Check breach at minute m after all events at minute m have taken effect
            if ever_opened and state != 'NOT_OPENED' and not breached:
                current_limit = PRIORITY_LIMITS[priority]
                if used > current_limit:
                    breached = True
                    breached_at = m

        # Sweep from the last event minute up to "now"
        if ever_opened and last_minute < now:
            if state == 'RUNNING':
                bus_mins = count_bus_mins(now) - count_bus_mins(last_minute)
                if not breached:
                    limit = PRIORITY_LIMITS[priority]
                    needed = limit + 1 - used
                    if bus_mins >= needed:
                        target = count_bus_mins(last_minute) + needed
                        t = _find_breach_minute(count_bus_mins, last_minute, now, target)
                        if t <= now:
                            breached = True
                            breached_at = t
                used += bus_mins
            last_minute = now

        if ever_opened:
            results.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used,
                "breached": breached,
                "breached_at": breached_at,
                "status": status_map[state],
            })

    return results