from bisect import bisect_left
from collections import defaultdict


LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}


def _parse_line(line):
    s = line.strip()
    if not s:
        return None
    raw_fields = s.split(',')
    n = len(raw_fields)
    if n not in (3, 4):
        return None
    fields = [f.strip() for f in raw_fields]

    m_str = fields[0]
    if not (m_str.isascii() and m_str.isdigit()):
        return None
    minute = int(m_str)

    ticket_id = fields[1]
    if not ticket_id:
        return None

    event = fields[2]
    if event not in ('OPEN', 'PRIORITY', 'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'):
        return None

    if event in ('OPEN', 'PRIORITY'):
        if n != 4:
            return None
        priority = fields[3]
        if priority not in ('P1', 'P2', 'P3', 'P4'):
            return None
    else:
        if n != 3:
            return None
        priority = None

    if event == 'HOLIDAY':
        if ticket_id != '*':
            return None
    else:
        if ticket_id == '*':
            return None

    return minute, ticket_id, event, priority


def _build_calendar_calculator(holiday_days):
    def business_minutes_up_to(m):
        if m <= 0:
            return 0
        w = m // 10080
        rem = m % 10080
        d = rem // 1440
        mod = rem % 1440
        base = w * 2400 + (d if d < 5 else 5) * 480
        if d < 5:
            if mod >= 1020:
                base += 480
            elif mod > 540:
                base += mod - 540

        cur_d = m // 1440
        idx = bisect_left(holiday_days, cur_d)
        holiday_sub = idx * 480
        if idx < len(holiday_days) and holiday_days[idx] == cur_d:
            if mod >= 1020:
                holiday_sub += 480
            elif mod > 540:
                holiday_sub += mod - 540

        return base - holiday_sub

    return business_minutes_up_to


def compute_sla(stream):
    ticket_events = []
    holiday_set = set()

    for line_idx, line in enumerate(stream):
        parsed = _parse_line(line)
        if parsed is None:
            continue
        minute, ticket_id, event, priority = parsed
        if event == 'HOLIDAY':
            holiday_set.add(minute // 1440)
        else:
            ticket_events.append((minute, line_idx, ticket_id, event, priority))

    if not ticket_events:
        return []

    now = max(ev[0] for ev in ticket_events)

    # Filter holidays to weekdays only (weekdays 0..4) and sort
    holiday_days = sorted(d for d in holiday_set if (d % 7) < 5)
    b_mins_up_to = _build_calendar_calculator(holiday_days)

    by_ticket = defaultdict(list)
    for minute, line_idx, ticket_id, event, priority in ticket_events:
        by_ticket[ticket_id].append((minute, line_idx, event, priority))

    results = []

    for ticket_id in sorted(by_ticket.keys()):
        raw_events = by_ticket[ticket_id]
        raw_events.sort(key=lambda x: (x[0], x[1]))

        # Group events at the same minute
        events_by_minute = []
        for minute, line_idx, event, priority in raw_events:
            if not events_by_minute or events_by_minute[-1][0] != minute:
                events_by_minute.append((minute, []))
            events_by_minute[-1][1].append((event, priority))

        # --- Phase 1: Event sweep that rebuilds running intervals ---
        state = 'not_opened'
        priority = None
        has_valid_open = False

        items = []
        m_prev = 0
        state_prev = 'not_opened'
        priority_prev = None

        for m, ev_list in events_by_minute:
            if m > m_prev and state_prev == 'running':
                items.append((m, 0, 'RUN', m_prev, priority_prev))

            session_reset = False
            for event, p in ev_list:
                if event == 'OPEN':
                    if state == 'not_opened' or state == 'closed':
                        state = 'running'
                        priority = p
                        session_reset = True
                        has_valid_open = True
                elif event == 'PRIORITY':
                    if state in ('running', 'paused'):
                        priority = p
                elif event == 'PAUSE':
                    if state == 'running':
                        state = 'paused'
                elif event == 'RESUME':
                    if state == 'paused':
                        state = 'running'
                elif event == 'CLOSE':
                    if state in ('running', 'paused'):
                        state = 'closed'
                elif event == 'REOPEN':
                    if state == 'closed':
                        state = 'running'

            if session_reset:
                items.clear()

            if has_valid_open:
                items.append((m, 1, 'CHECK', priority))

            m_prev = m
            state_prev = state
            priority_prev = priority

        if not has_valid_open:
            continue

        if state_prev == 'running' and m_prev < now:
            items.append((now, 0, 'RUN', m_prev, priority_prev))
            items.append((now, 1, 'CHECK', priority_prev))

        # --- Phase 2: Count business minutes per interval and evaluate breaches ---
        used_minutes = 0
        breached = False
        breached_at = None

        for item in items:
            kind = item[2]
            if kind == 'RUN':
                end_m, _, _, start_m, p = item
                b_mins = b_mins_up_to(end_m) - b_mins_up_to(start_m)
                limit = LIMITS[p]
                if not breached:
                    needed = limit + 1 - used_minutes
                    if b_mins >= needed:
                        low = start_m + 1
                        high = end_m
                        ans = high
                        while low <= high:
                            mid = (low + high) // 2
                            if (b_mins_up_to(mid) - b_mins_up_to(start_m)) >= needed:
                                ans = mid
                                high = mid - 1
                            else:
                                low = mid + 1
                        if ans < end_m:
                            breached = True
                            breached_at = ans
                used_minutes += b_mins
            elif kind == 'CHECK':
                chk_m, _, _, p = item
                limit = LIMITS[p]
                if not breached and used_minutes > limit:
                    breached = True
                    breached_at = chk_m

        results.append({
            "ticket_id": ticket_id,
            "priority": priority_prev,
            "used_minutes": used_minutes,
            "breached": breached,
            "breached_at": breached_at,
            "status": state_prev,
        })

    return results