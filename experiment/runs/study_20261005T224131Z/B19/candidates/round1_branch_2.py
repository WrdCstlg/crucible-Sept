from bisect import bisect_left
from collections import defaultdict
from itertools import groupby

LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}

VALID_EVENTS_4 = {'OPEN', 'PRIORITY'}
VALID_EVENTS_3 = {'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'}
VALID_PRIORITIES = {'P1', 'P2', 'P3', 'P4'}
DAY_MINS = (0, 480, 960, 1440, 1920, 2400, 2400)


def compute_sla(stream):
    ticket_events = []
    holiday_days = set()

    # 1. Parse and validate stream records
    stream_idx = 0
    for line in stream:
        s = line.strip()
        if not s:
            stream_idx += 1
            continue

        parts = [p.strip() for p in s.split(',')]
        n = len(parts)
        if n not in (3, 4):
            stream_idx += 1
            continue

        m_str = parts[0]
        if not m_str or not m_str.isascii() or not m_str.isdigit():
            stream_idx += 1
            continue
        minute = int(m_str)

        ticket_id = parts[1]
        if not ticket_id:
            stream_idx += 1
            continue

        event = parts[2]

        if event in VALID_EVENTS_4:
            if n != 4:
                stream_idx += 1
                continue
            prio = parts[3]
            if prio not in VALID_PRIORITIES:
                stream_idx += 1
                continue
            if ticket_id == '*':
                stream_idx += 1
                continue
            ticket_events.append((minute, stream_idx, ticket_id, event, prio))

        elif event in VALID_EVENTS_3:
            if n != 3:
                stream_idx += 1
                continue
            if event == 'HOLIDAY':
                if ticket_id != '*':
                    stream_idx += 1
                    continue
                holiday_days.add(minute // 1440)
            else:
                if ticket_id == '*':
                    stream_idx += 1
                    continue
                ticket_events.append((minute, stream_idx, ticket_id, event, None))

        stream_idx += 1

    if not ticket_events:
        return []

    # "Now" is the largest minute among all well-formed ticket events
    now = max(ev[0] for ev in ticket_events)

    # Filter holidays to effective weekdays (Monday-Friday) and sort
    sorted_holidays = sorted(d for d in holiday_days if (d % 7) < 5)
    len_holidays = len(sorted_holidays)

    def business_minutes(t):
        if t <= 0:
            return 0
        d = t // 1440
        rem = t % 1440
        weeks = d // 7
        rem_days = d % 7
        raw = weeks * 2400 + DAY_MINS[rem_days]
        if rem_days < 5:
            raw += max(0, min(rem, 1020) - 540)

        if not sorted_holidays:
            return raw

        idx = bisect_left(sorted_holidays, d)
        holiday_mins = idx * 480
        if idx < len_holidays and sorted_holidays[idx] == d:
            holiday_mins += max(0, min(rem, 1020) - 540)

        return raw - holiday_mins

    def find_breach_minute(start_m, end_m, target_b):
        low = start_m
        high = end_m
        ans = end_m
        while low <= high:
            mid = (low + high) // 2
            if business_minutes(mid) >= target_b:
                ans = mid
                high = mid - 1
            else:
                low = mid + 1
        return ans

    # 2. Group events by ticket
    ticket_events_by_id = defaultdict(list)
    for ev in ticket_events:
        ticket_events_by_id[ev[2]].append(ev)

    results = []

    # 3. Sweep events per ticket, rebuilding running intervals and counting business minutes
    for ticket_id, evs in ticket_events_by_id.items():
        evs.sort(key=lambda x: (x[0], x[1]))

        # Group events occurring at the exact same minute
        minute_events = []
        for m, group in groupby(evs, key=lambda x: x[0]):
            minute_events.append((m, [(x[3], x[4]) for x in group]))

        # Extend timeline to "now" if ticket's last event was before "now"
        if minute_events[-1][0] < now:
            minute_events.append((now, []))

        had_valid_open = False
        status = 'NOT_OPENED'
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None

        prev_m = None

        for m, events in minute_events:
            if prev_m is not None and prev_m < m:
                # Interval [prev_m, m)
                if status == 'RUNNING':
                    b = business_minutes(m) - business_minutes(prev_m)
                    limit = LIMITS[priority]
                    if not breached and used_minutes + b > limit:
                        k = (limit + 1) - used_minutes
                        target_b = business_minutes(prev_m) + k
                        tau = find_breach_minute(prev_m, m, target_b)
                        if tau < m:
                            breached = True
                            breached_at = tau
                        # If tau == m, breach check is deferred until after events at m are applied
                    used_minutes += b

            # Apply all events at minute m in stream order
            for event_type, event_prio in events:
                if event_type == 'OPEN':
                    if status in ('NOT_OPENED', 'CLOSED'):
                        had_valid_open = True
                        status = 'RUNNING'
                        priority = event_prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                elif event_type == 'PRIORITY':
                    if status in ('RUNNING', 'PAUSED'):
                        priority = event_prio
                elif event_type == 'PAUSE':
                    if status == 'RUNNING':
                        status = 'PAUSED'
                elif event_type == 'RESUME':
                    if status == 'PAUSED':
                        status = 'RUNNING'
                elif event_type == 'CLOSE':
                    if status in ('RUNNING', 'PAUSED'):
                        status = 'CLOSED'
                elif event_type == 'REOPEN':
                    if status == 'CLOSED':
                        status = 'RUNNING'

            # Check breach at minute m after all events at minute m are applied
            if had_valid_open and status != 'NOT_OPENED':
                if not breached and used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = m

            prev_m = m

        if had_valid_open:
            results.append({
                'ticket_id': ticket_id,
                'priority': priority,
                'used_minutes': used_minutes,
                'breached': breached,
                'breached_at': breached_at,
                'status': status.lower(),
            })

    results.sort(key=lambda d: d['ticket_id'])
    return results