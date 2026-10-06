from bisect import bisect_left
from collections import defaultdict

PRIORITY_LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}

VALID_EVENTS_3 = {"PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}
VALID_EVENTS_4 = {"OPEN", "PRIORITY"}
VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}


def compute_sla(stream):
    raw_holidays = set()
    ticket_events = defaultdict(list)
    max_minute = -1
    has_ticket_events = False

    # 1. Parse lines and collect holiday days and ticket events
    for line in stream:
        trimmed = line.strip()
        if not trimmed:
            continue
        parts = trimmed.split(",")
        n_fields = len(parts)
        if n_fields not in (3, 4):
            continue

        f0 = parts[0].strip()
        if not f0 or not all("0" <= c <= "9" for c in f0):
            continue
        minute = int(f0)

        ticket_id = parts[1].strip()
        if not ticket_id:
            continue

        event = parts[2].strip()

        if event == "HOLIDAY":
            if n_fields != 3 or ticket_id != "*":
                continue
            raw_holidays.add(minute // 1440)
            continue

        if ticket_id == "*":
            continue

        if event in VALID_EVENTS_4:
            if n_fields != 4:
                continue
            prio = parts[3].strip()
            if prio not in VALID_PRIORITIES:
                continue
            ticket_events[ticket_id].append((minute, event, prio))
            has_ticket_events = True
            if minute > max_minute:
                max_minute = minute
        elif event in VALID_EVENTS_3:
            if n_fields != 3:
                continue
            ticket_events[ticket_id].append((minute, event, None))
            has_ticket_events = True
            if minute > max_minute:
                max_minute = minute

    if not has_ticket_events:
        return []

    now = max_minute

    # 2. Setup business calendar and holiday lookup
    weekday_holidays = {d for d in raw_holidays if d % 7 < 5}
    sorted_holidays = sorted(weekday_holidays)
    holiday_set = weekday_holidays

    def business_minutes_before(t: int) -> int:
        week, rem = divmod(t, 10080)
        day_in_week, min_in_day = divmod(rem, 1440)
        full_wd = 5 if day_in_week >= 5 else day_in_week
        cur_day_mins = max(0, min(min_in_day, 1020) - 540) if day_in_week < 5 else 0
        base = week * 2400 + full_wd * 480 + cur_day_mins

        day = week * 7 + day_in_week
        idx = bisect_left(sorted_holidays, day)
        holidays_mins = idx * 480
        if day in holiday_set:
            holidays_mins += cur_day_mins

        return base - holidays_mins

    def find_breach_minute(m_start: int, m_end: int, target_b: int) -> int:
        low = m_start
        high = m_end
        while low < high:
            mid = (low + high) // 2
            if business_minutes_before(mid) >= target_b:
                high = mid
            else:
                low = mid + 1
        return low

    results = []

    # 3. Sweep events per ticket, rebuild running intervals, and count business minutes
    for tid in sorted(ticket_events.keys()):
        events = ticket_events[tid]
        events.sort(key=lambda x: x[0])

        # Group consecutive events occurring at the exact same minute
        grouped = []
        for m, ev, p in events:
            if grouped and grouped[-1][0] == m:
                grouped[-1][1].append((ev, p))
            else:
                grouped.append((m, [(ev, p)]))

        state = "NOT_OPENED"
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        last_run_start = None
        had_valid_open = False

        for m, event_list in grouped:
            # Rebuild running interval [last_run_start, m) and count business minutes
            if state == "RUNNING" and last_run_start is not None and m > last_run_start:
                m_biz = business_minutes_before(m) - business_minutes_before(last_run_start)
                if not breached:
                    limit = PRIORITY_LIMITS[priority]
                    needed = limit + 1 - used_minutes
                    if m_biz >= needed:
                        target = business_minutes_before(last_run_start) + needed
                        t_breach = find_breach_minute(last_run_start, m, target)
                        if t_breach < m:
                            breached = True
                            breached_at = t_breach
                used_minutes += m_biz
                last_run_start = m

            # Apply state transitions for events at minute m
            for ev, p in event_list:
                if ev == "OPEN":
                    if state in ("NOT_OPENED", "CLOSED"):
                        state = "RUNNING"
                        priority = p
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                        last_run_start = m
                elif ev == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = p
                elif ev == "PAUSE":
                    if state == "RUNNING":
                        state = "PAUSED"
                        last_run_start = None
                elif ev == "RESUME":
                    if state == "PAUSED":
                        state = "RUNNING"
                        last_run_start = m
                elif ev == "CLOSE":
                    if state in ("RUNNING", "PAUSED"):
                        state = "CLOSED"
                        last_run_start = None
                elif ev == "REOPEN":
                    if state == "CLOSED":
                        state = "RUNNING"
                        last_run_start = m

            # Check breach condition at minute m after all events at m take effect
            if had_valid_open and not breached and m <= now:
                limit = PRIORITY_LIMITS[priority]
                if used_minutes > limit:
                    breached = True
                    breached_at = m

        # Account for running interval extending to "now"
        if state == "RUNNING" and last_run_start is not None and now > last_run_start:
            m_biz = business_minutes_before(now) - business_minutes_before(last_run_start)
            if not breached:
                limit = PRIORITY_LIMITS[priority]
                needed = limit + 1 - used_minutes
                if m_biz >= needed:
                    target = business_minutes_before(last_run_start) + needed
                    t_breach = find_breach_minute(last_run_start, now, target)
                    breached = True
                    breached_at = t_breach
            used_minutes += m_biz

        if not had_valid_open:
            continue

        results.append({
            "ticket_id": tid,
            "priority": priority,
            "used_minutes": used_minutes,
            "breached": breached,
            "breached_at": breached_at,
            "status": state.lower(),
        })

    return results