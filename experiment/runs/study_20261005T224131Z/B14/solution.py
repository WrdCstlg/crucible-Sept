from bisect import bisect_left
from collections import defaultdict

LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}

VALID_EVENTS_4 = {'OPEN', 'PRIORITY'}
VALID_EVENTS_3 = {'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'}
VALID_PRIORITIES = {'P1', 'P2', 'P3', 'P4'}
STATUS_MAP = {
    'RUNNING': 'running',
    'PAUSED': 'paused',
    'CLOSED': 'closed',
}


def compute_sla(stream):
    holidays = set()
    events_by_ticket = defaultdict(list)
    has_ticket_events = False
    max_minute = -1

    for line in stream:
        trimmed = line.strip()
        if not trimmed:
            continue

        raw_fields = trimmed.split(',')
        n_fields = len(raw_fields)
        if n_fields not in (3, 4):
            continue

        f0 = raw_fields[0].strip()
        f1 = raw_fields[1].strip()
        f2 = raw_fields[2].strip()

        if not f0 or not f0.isascii() or not f0.isdigit():
            continue
        minute = int(f0)

        if not f1:
            continue
        ticket_id = f1
        event = f2

        if event in VALID_EVENTS_4:
            if n_fields != 4:
                continue
            f3 = raw_fields[3].strip()
            if f3 not in VALID_PRIORITIES:
                continue
            if ticket_id == '*':
                continue
            events_by_ticket[ticket_id].append((minute, event, f3))
            has_ticket_events = True
            if minute > max_minute:
                max_minute = minute

        elif event in VALID_EVENTS_3:
            if n_fields != 3:
                continue
            if event == 'HOLIDAY':
                if ticket_id != '*':
                    continue
                holidays.add(minute // 1440)
            else:
                if ticket_id == '*':
                    continue
                events_by_ticket[ticket_id].append((minute, event, None))
                has_ticket_events = True
                if minute > max_minute:
                    max_minute = minute
        else:
            continue

    if not has_ticket_events:
        return []

    now = max_minute

    holiday_days = sorted([d for d in holidays if d % 7 < 5])
    n_holidays = len(holiday_days)

    def business_minutes(m):
        d = m // 1440
        mod = m % 1440
        weeks = d // 7
        rem = d % 7

        b = weeks * 2400 + (rem if rem < 5 else 5) * 480
        if rem < 5:
            if mod > 540:
                b_day = (1020 if mod > 1020 else mod) - 540
            else:
                b_day = 0
        else:
            b_day = 0
        b += b_day

        idx = bisect_left(holiday_days, d)
        b -= idx * 480
        if idx < n_holidays and holiday_days[idx] == d:
            b -= b_day
        return b

    results = []

    for ticket_id in sorted(events_by_ticket.keys()):
        ticket_events = events_by_ticket[ticket_id]
        ticket_events.sort(key=lambda x: x[0])

        grouped_events = []
        curr_m = None
        curr_batch = []
        for ev in ticket_events:
            m = ev[0]
            if m != curr_m:
                if curr_batch:
                    grouped_events.append((curr_m, curr_batch))
                curr_m = m
                curr_batch = [ev]
            else:
                curr_batch.append(ev)
        if curr_batch:
            grouped_events.append((curr_m, curr_batch))

        state = 'NOT_OPENED'
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        has_valid_open = False
        last_m = None

        for m, batch in grouped_events:
            if last_m is not None:
                if state == 'RUNNING':
                    delta = business_minutes(m) - business_minutes(last_m)
                    if not breached:
                        lim = LIMITS[priority]
                        target = business_minutes(last_m) + (lim - used_minutes + 1)
                        if m - 1 >= last_m and business_minutes(m - 1) >= target:
                            low = last_m
                            high = m - 1
                            while low < high:
                                mid = (low + high) // 2
                                if business_minutes(mid) >= target:
                                    high = mid
                                else:
                                    low = mid + 1
                            breached = True
                            breached_at = low
                    used_minutes += delta

            for ev in batch:
                _, ev_type, ev_prio = ev
                if ev_type == 'OPEN':
                    if state == 'NOT_OPENED' or state == 'CLOSED':
                        state = 'RUNNING'
                        priority = ev_prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        has_valid_open = True
                elif ev_type == 'PRIORITY':
                    if state == 'RUNNING' or state == 'PAUSED':
                        priority = ev_prio
                elif ev_type == 'PAUSE':
                    if state == 'RUNNING':
                        state = 'PAUSED'
                elif ev_type == 'RESUME':
                    if state == 'PAUSED':
                        state = 'RUNNING'
                elif ev_type == 'CLOSE':
                    if state == 'RUNNING' or state == 'PAUSED':
                        state = 'CLOSED'
                elif ev_type == 'REOPEN':
                    if state == 'CLOSED':
                        state = 'RUNNING'

            if has_valid_open and not breached and priority is not None:
                if used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = m

            last_m = m

        if last_m is not None and last_m < now:
            if state == 'RUNNING':
                delta = business_minutes(now) - business_minutes(last_m)
                if not breached:
                    lim = LIMITS[priority]
                    target = business_minutes(last_m) + (lim - used_minutes + 1)
                    if business_minutes(now) >= target:
                        low = last_m
                        high = now
                        while low < high:
                            mid = (low + high) // 2
                            if business_minutes(mid) >= target:
                                high = mid
                            else:
                                low = mid + 1
                        breached = True
                        breached_at = low
                used_minutes += delta

        if has_valid_open:
            results.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": STATUS_MAP[state],
            })

    return results