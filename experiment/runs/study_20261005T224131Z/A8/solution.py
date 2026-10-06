from bisect import bisect_left
from collections import defaultdict


def compute_sla(stream):
    holiday_days = set()
    ticket_events = defaultdict(list)
    now = None

    for line in stream:
        s = line.strip()
        if not s:
            continue
        parts = [p.strip() for p in s.split(',')]
        n = len(parts)
        if n not in (3, 4):
            continue

        m_str = parts[0]
        if not m_str or not m_str.isascii() or not m_str.isdigit():
            continue
        minute = int(m_str)

        ticket_id = parts[1]
        if not ticket_id:
            continue

        event = parts[2]
        if event == 'HOLIDAY':
            if n != 3 or ticket_id != '*':
                continue
            holiday_days.add(minute // 1440)
            continue

        if ticket_id == '*':
            continue

        if event in ('OPEN', 'PRIORITY'):
            if n != 4:
                continue
            prio = parts[3]
            if prio not in ('P1', 'P2', 'P3', 'P4'):
                continue
            ticket_events[ticket_id].append((minute, event, prio))
        elif event in ('PAUSE', 'RESUME', 'CLOSE', 'REOPEN'):
            if n != 3:
                continue
            ticket_events[ticket_id].append((minute, event, None))
        else:
            continue

        if now is None or minute > now:
            now = minute

    if now is None:
        return []

    # Calendar helpers
    hw_list = sorted(d for d in holiday_days if d % 7 < 5)
    hw_set = set(hw_list)

    def business_minutes_before(m: int) -> int:
        if m <= 0:
            return 0
        d = m // 1440
        rem = m % 1440

        weeks = d // 7
        extra_days = d % 7
        weekdays_count = weeks * 5 + min(extra_days, 5)
        total_bm = weekdays_count * 480

        weekday_of_d = d % 7
        if weekday_of_d < 5 and d not in hw_set:
            if rem > 540:
                total_bm += min(rem, 1020) - 540

        idx = bisect_left(hw_list, d)
        total_bm -= idx * 480
        return total_bm

    def business_minutes_between(m1: int, m2: int) -> int:
        if m2 <= m1:
            return 0
        return business_minutes_before(m2) - business_minutes_before(m1)

    def find_breach_minute(low: int, high: int, target: int) -> int:
        ans = high
        while low <= high:
            mid = (low + high) // 2
            if business_minutes_before(mid) >= target:
                ans = mid
                high = mid - 1
            else:
                low = mid + 1
        return ans

    LIMITS = {
        'P1': 240,
        'P2': 480,
        'P3': 1440,
        'P4': 2400,
    }

    results = []

    for ticket_id, raw_events in ticket_events.items():
        # Stable sort by minute
        raw_events.sort(key=lambda x: x[0])

        # Group by minute
        grouped_events = []
        cur_min = None
        cur_list = []
        for m, ev_type, ev_prio in raw_events:
            if m != cur_min:
                if cur_list:
                    grouped_events.append((cur_min, cur_list))
                cur_min = m
                cur_list = [(ev_type, ev_prio)]
            else:
                cur_list.append((ev_type, ev_prio))
        if cur_list:
            grouped_events.append((cur_min, cur_list))

        status = 'NOT_OPENED'
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        prev_minute = None

        for m_curr, evs in grouped_events:
            if prev_minute is not None:
                if status == 'RUNNING':
                    limit = LIMITS[priority]
                    if not breached:
                        bm_before_curr = business_minutes_between(prev_minute, m_curr - 1)
                        if used_minutes + bm_before_curr >= limit + 1:
                            target = business_minutes_before(prev_minute) + limit + 1 - used_minutes
                            breached_at = find_breach_minute(prev_minute + 1, m_curr - 1, target)
                            breached = True
                    used_minutes += business_minutes_between(prev_minute, m_curr)

            # Apply events at minute m_curr in order
            for ev_type, ev_prio in evs:
                if ev_type == 'OPEN':
                    if status in ('NOT_OPENED', 'CLOSED'):
                        status = 'RUNNING'
                        priority = ev_prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif ev_type == 'PRIORITY':
                    if status in ('RUNNING', 'PAUSED'):
                        priority = ev_prio
                elif ev_type == 'PAUSE':
                    if status == 'RUNNING':
                        status = 'PAUSED'
                elif ev_type == 'RESUME':
                    if status == 'PAUSED':
                        status = 'RUNNING'
                elif ev_type == 'CLOSE':
                    if status in ('RUNNING', 'PAUSED'):
                        status = 'CLOSED'
                elif ev_type == 'REOPEN':
                    if status == 'CLOSED':
                        status = 'RUNNING'

            # Post-event check at minute m_curr
            if had_valid_open and not breached and priority is not None:
                limit = LIMITS[priority]
                if used_minutes > limit:
                    breached = True
                    breached_at = m_curr

            prev_minute = m_curr

        # Advance from last event to 'now'
        if prev_minute is not None and prev_minute < now:
            if status == 'RUNNING':
                limit = LIMITS[priority]
                if not breached:
                    bm_to_now = business_minutes_between(prev_minute, now)
                    if used_minutes + bm_to_now >= limit + 1:
                        target = business_minutes_before(prev_minute) + limit + 1 - used_minutes
                        breached_at = find_breach_minute(prev_minute + 1, now, target)
                        breached = True
                used_minutes += business_minutes_between(prev_minute, now)

        if had_valid_open:
            results.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": status.lower(),
            })

    results.sort(key=lambda x: x["ticket_id"])
    return results