from bisect import bisect_left
from collections import defaultdict


LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}


def _parse_line(line):
    line = line.strip()
    if not line:
        return None
    parts = line.split(',')
    if len(parts) not in (3, 4):
        return None
    parts = [p.strip() for p in parts]

    m_str = parts[0]
    if not m_str or not m_str.isascii() or not m_str.isdigit():
        return None
    minute = int(m_str)

    ticket_id = parts[1]
    if not ticket_id:
        return None

    event = parts[2]
    if event not in ('OPEN', 'PRIORITY', 'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'):
        return None

    if event in ('OPEN', 'PRIORITY'):
        if len(parts) != 4:
            return None
        p_arg = parts[3]
        if p_arg not in ('P1', 'P2', 'P3', 'P4'):
            return None
    else:
        if len(parts) != 3:
            return None
        p_arg = None

    if event == 'HOLIDAY':
        if ticket_id != '*':
            return None
    else:
        if ticket_id == '*':
            return None

    return minute, ticket_id, event, p_arg


def _apply_event(state, priority, used, breached, breached_at, had_valid_open, event_type, event_arg):
    if event_type == 'OPEN':
        if state in ('NOT_OPENED', 'CLOSED'):
            return 'RUNNING', event_arg, 0, False, None, True
        else:
            return state, priority, used, breached, breached_at, had_valid_open
    elif event_type == 'PRIORITY':
        if state in ('RUNNING', 'PAUSED'):
            return state, event_arg, used, breached, breached_at, had_valid_open
        else:
            return state, priority, used, breached, breached_at, had_valid_open
    elif event_type == 'PAUSE':
        if state == 'RUNNING':
            return 'PAUSED', priority, used, breached, breached_at, had_valid_open
        else:
            return state, priority, used, breached, breached_at, had_valid_open
    elif event_type == 'RESUME':
        if state == 'PAUSED':
            return 'RUNNING', priority, used, breached, breached_at, had_valid_open
        else:
            return state, priority, used, breached, breached_at, had_valid_open
    elif event_type == 'CLOSE':
        if state in ('RUNNING', 'PAUSED'):
            return 'CLOSED', priority, used, breached, breached_at, had_valid_open
        else:
            return state, priority, used, breached, breached_at, had_valid_open
    elif event_type == 'REOPEN':
        if state == 'CLOSED':
            return 'RUNNING', priority, used, breached, breached_at, had_valid_open
        else:
            return state, priority, used, breached, breached_at, had_valid_open
    return state, priority, used, breached, breached_at, had_valid_open


def compute_sla(stream):
    ticket_events = []
    holiday_days = set()

    for idx, line in enumerate(stream):
        parsed = _parse_line(line)
        if parsed is None:
            continue
        minute, ticket_id, event, p_arg = parsed
        if event == 'HOLIDAY':
            holiday_days.add(minute // 1440)
        else:
            ticket_events.append((minute, idx, ticket_id, event, p_arg))

    if not ticket_events:
        return []

    now = max(e[0] for e in ticket_events)

    sorted_holidays = sorted(d for d in holiday_days if d % 7 < 5)
    holiday_set = set(sorted_holidays)

    def biz_minutes_from_zero(m):
        d = m // 1440
        mod = m % 1440
        weekday = d % 7
        raw = (d // 7) * 2400 + min(weekday, 5) * 480
        if weekday < 5:
            raw += max(0, min(mod, 1020) - 540)

        idx = bisect_left(sorted_holidays, d)
        raw -= idx * 480
        if d in holiday_set and weekday < 5:
            raw -= max(0, min(mod, 1020) - 540)
        return raw

    tickets_map = defaultdict(list)
    for minute, idx, ticket_id, event, p_arg in ticket_events:
        tickets_map[ticket_id].append((minute, idx, event, p_arg))

    results = []

    for ticket_id, events in tickets_map.items():
        events.sort(key=lambda x: x[0])

        grouped_events = []
        for m, idx, ev, arg in events:
            if grouped_events and grouped_events[-1][0] == m:
                grouped_events[-1][1].append((ev, arg))
            else:
                grouped_events.append((m, [(ev, arg)]))

        state = 'NOT_OPENED'
        priority = None
        used = 0
        breached = False
        breached_at = None
        had_valid_open = False
        current_minute = 0

        for m, ev_list in grouped_events:
            if had_valid_open and state == 'RUNNING' and m > current_minute:
                biz = biz_minutes_from_zero(m) - biz_minutes_from_zero(current_minute)
                L = LIMITS[priority]
                if not breached:
                    if used + biz <= L:
                        used += biz
                    else:
                        target = biz_minutes_from_zero(current_minute) + (L + 1 - used)
                        lo = current_minute
                        hi = m
                        while lo < hi:
                            mid = (lo + hi) // 2
                            if biz_minutes_from_zero(mid) >= target:
                                hi = mid
                            else:
                                lo = mid + 1
                        t_breach = lo
                        if t_breach < m:
                            breached = True
                            breached_at = t_breach
                        used += biz
                else:
                    used += biz

            for ev, arg in ev_list:
                state, priority, used, breached, breached_at, had_valid_open = _apply_event(
                    state, priority, used, breached, breached_at, had_valid_open, ev, arg
                )

            current_minute = m

            if had_valid_open and not breached:
                if used > LIMITS[priority]:
                    breached = True
                    breached_at = m

        if had_valid_open and state == 'RUNNING' and now > current_minute:
            biz = biz_minutes_from_zero(now) - biz_minutes_from_zero(current_minute)
            L = LIMITS[priority]
            if not breached:
                if used + biz <= L:
                    used += biz
                else:
                    target = biz_minutes_from_zero(current_minute) + (L + 1 - used)
                    lo = current_minute
                    hi = now
                    while lo < hi:
                        mid = (lo + hi) // 2
                        if biz_minutes_from_zero(mid) >= target:
                            hi = mid
                        else:
                            lo = mid + 1
                    breached = True
                    breached_at = lo
                    used += biz
            else:
                used += biz

        if had_valid_open:
            results.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used,
                "breached": breached,
                "breached_at": breached_at,
                "status": state.lower(),
            })

    results.sort(key=lambda d: d["ticket_id"])
    return results