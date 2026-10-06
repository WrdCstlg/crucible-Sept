from bisect import bisect_left
from collections import defaultdict


def compute_sla(stream):
    LIMITS = {
        'P1': 240,
        'P2': 480,
        'P3': 1440,
        'P4': 2400,
    }

    holidays = set()
    ticket_events_by_id = defaultdict(list)
    has_ticket_events = False
    now = -1

    for line_idx, line in enumerate(stream):
        trimmed = line.strip()
        if not trimmed:
            continue
        parts = [p.strip() for p in trimmed.split(',')]
        if len(parts) not in (3, 4):
            continue

        minute_str, ticket_id, event = parts[0], parts[1], parts[2]
        if not (minute_str.isascii() and minute_str.isdigit()):
            continue
        minute = int(minute_str)
        if not ticket_id:
            continue

        if event == 'HOLIDAY':
            if len(parts) != 3 or ticket_id != '*':
                continue
            holidays.add(minute // 1440)
        elif event in ('OPEN', 'PRIORITY'):
            if len(parts) != 4 or ticket_id == '*':
                continue
            prio = parts[3]
            if prio not in LIMITS:
                continue
            ticket_events_by_id[ticket_id].append((minute, line_idx, event, prio))
            has_ticket_events = True
            if minute > now:
                now = minute
        elif event in ('PAUSE', 'RESUME', 'CLOSE', 'REOPEN'):
            if len(parts) != 3 or ticket_id == '*':
                continue
            ticket_events_by_id[ticket_id].append((minute, line_idx, event, None))
            has_ticket_events = True
            if minute > now:
                now = minute
        else:
            continue

    if not has_ticket_events:
        return []

    sorted_holidays = sorted(d for d in holidays if d % 7 < 5)

    def business_minutes_to(t):
        if t <= 0:
            return 0
        d = t // 1440
        mod = t % 1440
        weeks = d // 7
        rem_days = d % 7
        full_weekdays = weeks * 5 + min(rem_days, 5)
        raw = full_weekdays * 480
        part = 0
        if rem_days < 5:
            part = max(0, min(mod, 1020) - 540)
            raw += part

        idx = bisect_left(sorted_holidays, d)
        holiday_mins = idx * 480
        if idx < len(sorted_holidays) and sorted_holidays[idx] == d:
            holiday_mins += part
        return raw - holiday_mins

    results = []
    status_map = {
        'RUNNING': 'running',
        'PAUSED': 'paused',
        'CLOSED': 'closed',
    }

    for ticket_id, events in ticket_events_by_id.items():
        events.sort(key=lambda x: (x[0], x[1]))

        # Group events by minute to process all events at minute m together
        minute_groups = []
        current_m = None
        current_group = []
        for m, _, ev, prio in events:
            if m != current_m:
                if current_group:
                    minute_groups.append((current_m, current_group))
                current_m = m
                current_group = [(ev, prio)]
            else:
                current_group.append((ev, prio))
        if current_group:
            minute_groups.append((current_m, current_group))

        state = 'NOT_OPENED'
        priority = None
        used_time = 0
        breached = False
        breached_at = None
        has_valid_open = False
        prev_m = None

        for m, group in minute_groups:
            if prev_m is not None and prev_m < m:
                if state == 'RUNNING':
                    bm = business_minutes_to(m) - business_minutes_to(prev_m)
                    if not breached:
                        needed = LIMITS[priority] + 1 - used_time
                        if bm >= needed:
                            target = business_minutes_to(prev_m) + needed
                            low = prev_m + 1
                            high = m
                            while low < high:
                                mid = (low + high) // 2
                                if business_minutes_to(mid) >= target:
                                    high = mid
                                else:
                                    low = mid + 1
                            if low < m:
                                breached = True
                                breached_at = low
                    used_time += bm

            for ev, prio in group:
                if ev == 'OPEN':
                    if state in ('NOT_OPENED', 'CLOSED'):
                        state = 'RUNNING'
                        priority = prio
                        used_time = 0
                        breached = False
                        breached_at = None
                        has_valid_open = True
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

            if not breached and has_valid_open and priority is not None:
                if used_time > LIMITS[priority]:
                    breached = True
                    breached_at = m

            prev_m = m

        if prev_m is not None and prev_m < now:
            if state == 'RUNNING':
                bm = business_minutes_to(now) - business_minutes_to(prev_m)
                if not breached:
                    needed = LIMITS[priority] + 1 - used_time
                    if bm >= needed:
                        target = business_minutes_to(prev_m) + needed
                        low = prev_m + 1
                        high = now
                        while low < high:
                            mid = (low + high) // 2
                            if business_minutes_to(mid) >= target:
                                high = mid
                            else:
                                low = mid + 1
                        if low < now:
                            breached = True
                            breached_at = low
                used_time += bm

            if not breached and has_valid_open and priority is not None:
                if used_time > LIMITS[priority]:
                    breached = True
                    breached_at = now

        if has_valid_open:
            results.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used_time,
                "breached": breached,
                "breached_at": breached_at,
                "status": status_map[state],
            })

    results.sort(key=lambda x: x["ticket_id"])
    return results