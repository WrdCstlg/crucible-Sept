from bisect import bisect_left
from collections import defaultdict
from itertools import groupby

LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}

VALID_EVENTS = {'OPEN', 'PRIORITY', 'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'}
VALID_PRIORITIES = {'P1', 'P2', 'P3', 'P4'}


def compute_sla(stream):
    holidays_set = set()
    ticket_events = defaultdict(list)
    now = None

    for line in stream:
        trimmed = line.strip()
        raw_fields = trimmed.split(',')
        if len(raw_fields) not in (3, 4):
            continue

        fields = [f.strip() for f in raw_fields]
        f0 = fields[0]
        if not f0 or not f0.isascii() or not f0.isdigit():
            continue
        minute = int(f0)

        ticket_id = fields[1]
        if not ticket_id:
            continue

        event = fields[2]
        if event not in VALID_EVENTS:
            continue

        if event in ('OPEN', 'PRIORITY'):
            if len(fields) != 4:
                continue
            priority = fields[3]
            if priority not in VALID_PRIORITIES:
                continue
        else:
            if len(fields) != 3:
                continue
            priority = None

        if event == 'HOLIDAY':
            if ticket_id != '*':
                continue
            holidays_set.add(minute // 1440)
        else:
            if ticket_id == '*':
                continue
            if now is None or minute > now:
                now = minute
            ticket_events[ticket_id].append((minute, event, priority))

    if now is None:
        return []

    sorted_holidays = sorted(d for d in holidays_set if d % 7 < 5)

    def business_minutes_between(m1, m2):
        if m1 >= m2:
            return 0
        d1 = m1 // 1440
        d2 = m2 // 1440

        if d1 == d2:
            if d1 % 7 >= 5 or d1 in holidays_set:
                return 0
            s = m1 % 1440
            e = m2 % 1440
            start = 540 if s < 540 else s
            end = 1020 if e > 1020 else e
            return end - start if end > start else 0

        ans = 0
        # Remainder of day d1
        if d1 % 7 < 5 and d1 not in holidays_set:
            s = m1 % 1440
            start = 540 if s < 540 else s
            if start < 1020:
                ans += 1020 - start

        # Whole days in [d1 + 1, d2)
        da = d1 + 1
        db = d2
        if da < db:
            wa = (da // 7) * 5 + (da % 7 if da % 7 < 5 else 5)
            wb = (db // 7) * 5 + (db % 7 if db % 7 < 5 else 5)
            h = bisect_left(sorted_holidays, db) - bisect_left(sorted_holidays, da)
            ans += ((wb - wa) - h) * 480

        # Start of day d2
        if d2 % 7 < 5 and d2 not in holidays_set:
            e = m2 % 1440
            end = 1020 if e > 1020 else e
            if end > 540:
                ans += end - 540

        return ans

    def find_breach_minute(m_start, m_end, k):
        low = m_start + 1
        high = m_end
        while low < high:
            mid = (low + high) // 2
            if business_minutes_between(m_start, mid) >= k:
                high = mid
            else:
                low = mid + 1
        return low

    results = []

    for ticket_id, events in ticket_events.items():
        events.sort(key=lambda x: x[0])

        state = 'NOT_OPENED'
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        last_m = None

        grouped = [(m, list(grp)) for m, grp in groupby(events, key=lambda x: x[0])]

        for curr_m, grp_events in grouped:
            if last_m is not None and curr_m > last_m:
                if state == 'RUNNING':
                    elapsed = business_minutes_between(last_m, curr_m)
                    if not breached:
                        limit = LIMITS[priority]
                        k = (limit + 1) - used_minutes
                        if k <= elapsed:
                            t_breach = find_breach_minute(last_m, curr_m, k)
                            if t_breach < curr_m:
                                breached = True
                                breached_at = t_breach
                    used_minutes += elapsed

            last_m = curr_m

            # Apply all events at curr_m
            for _, ev_type, ev_arg in grp_events:
                if ev_type == 'OPEN':
                    if state in ('NOT_OPENED', 'CLOSED'):
                        state = 'RUNNING'
                        priority = ev_arg
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif ev_type == 'PRIORITY':
                    if state in ('RUNNING', 'PAUSED'):
                        priority = ev_arg
                elif ev_type == 'PAUSE':
                    if state == 'RUNNING':
                        state = 'PAUSED'
                elif ev_type == 'RESUME':
                    if state == 'PAUSED':
                        state = 'RUNNING'
                elif ev_type == 'CLOSE':
                    if state in ('RUNNING', 'PAUSED'):
                        state = 'CLOSED'
                elif ev_type == 'REOPEN':
                    if state == 'CLOSED':
                        state = 'RUNNING'

            # Breach check at curr_m
            if had_valid_open and not breached:
                limit = LIMITS[priority]
                if used_minutes > limit:
                    breached = True
                    breached_at = curr_m

        if not had_valid_open:
            continue

        # Advance to "now"
        if last_m is not None and last_m < now:
            if state == 'RUNNING':
                elapsed = business_minutes_between(last_m, now)
                if not breached:
                    limit = LIMITS[priority]
                    k = (limit + 1) - used_minutes
                    if k <= elapsed:
                        t_breach = find_breach_minute(last_m, now, k)
                        breached = True
                        breached_at = t_breach
                used_minutes += elapsed

        results.append({
            'ticket_id': ticket_id,
            'priority': priority,
            'used_minutes': used_minutes,
            'breached': breached,
            'breached_at': breached_at,
            'status': state.lower(),
        })

    results.sort(key=lambda d: d['ticket_id'])
    return results