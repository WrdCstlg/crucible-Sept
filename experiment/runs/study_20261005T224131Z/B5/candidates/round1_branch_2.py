from bisect import bisect_left
from collections import defaultdict


def compute_sla(stream):
    """
    Computes SLA metrics for tickets from a CSV stream of events.

    Architectural approach:
    Event sweep that rebuilds each ticket's running intervals, then counts
    business minutes per interval.
    """
    PRIORITY_LIMITS = {
        "P1": 240,
        "P2": 480,
        "P3": 1440,
        "P4": 2400,
    }

    holidays = set()
    ticket_events = []

    # Parse and validate stream
    for idx, line in enumerate(stream):
        raw = line.strip()
        if not raw:
            continue
        parts = raw.split(",")
        if len(parts) not in (3, 4):
            continue
        parts = [p.strip() for p in parts]
        m_str, ticket_id, event = parts[0], parts[1], parts[2]

        if not m_str or not m_str.isascii() or not m_str.isdigit():
            continue
        minute = int(m_str)
        if not ticket_id:
            continue

        if event == "HOLIDAY":
            if len(parts) != 3 or ticket_id != "*":
                continue
            holidays.add(minute // 1440)
            continue

        if ticket_id == "*":
            continue

        if event in ("OPEN", "PRIORITY"):
            if len(parts) != 4:
                continue
            prio = parts[3]
            if prio not in PRIORITY_LIMITS:
                continue
        else:
            if len(parts) != 3:
                continue
            if event not in ("PAUSE", "RESUME", "CLOSE", "REOPEN"):
                continue
            prio = None

        ticket_events.append((minute, idx, ticket_id, event, prio))

    if not ticket_events:
        return []

    now = max(ev[0] for ev in ticket_events)

    # Pre-process calendar: weekday holidays only (Mon-Fri: weekday < 5)
    sorted_holidays = sorted(h for h in holidays if h % 7 < 5)
    holiday_set = set(sorted_holidays)

    def biz_minutes(t):
        """Total business minutes in [0, t)."""
        if t <= 0:
            return 0
        d = t // 1440
        rem = t % 1440
        weeks = d // 7
        rem_days = d % 7
        biz_days = rem_days if rem_days < 5 else 5
        day_min = min(rem, 1020) - 540
        if day_min < 0:
            day_min = 0

        reg = weeks * 2400 + biz_days * 480 + (day_min if rem_days < 5 else 0)

        k = bisect_left(sorted_holidays, d)
        sub = k * 480
        if d in holiday_set and rem_days < 5:
            sub += day_min
        return reg - sub

    def find_first_minute_ge(m_start, m_end, target):
        """
        Finds the smallest minute t in [m_start, m_end] such that biz_minutes(t) >= target.
        Assumes biz_minutes(m_end) >= target and target > biz_minutes(m_start).
        """
        d_min = m_start // 1440
        d_max = m_end // 1440

        low_d = d_min
        high_d = d_max
        ans_d = high_d
        while low_d <= high_d:
            mid_d = (low_d + high_d) // 2
            if biz_minutes(mid_d * 1440 + 1020) >= target:
                ans_d = mid_d
                high_d = mid_d - 1
            else:
                low_d = mid_d + 1

        b_start = biz_minutes(ans_d * 1440 + 540)
        return ans_d * 1440 + 540 + (target - b_start)

    # Group events by ticket
    events_by_ticket = defaultdict(list)
    for minute, idx, ticket_id, event, prio in ticket_events:
        events_by_ticket[ticket_id].append((minute, idx, event, prio))

    results = []

    # Process each ticket independently
    for ticket_id in sorted(events_by_ticket.keys()):
        raw_events = events_by_ticket[ticket_id]
        raw_events.sort(key=lambda x: (x[0], x[1]))

        # Group events by minute
        grouped_by_minute = []
        for minute, _, event, prio in raw_events:
            if not grouped_by_minute or grouped_by_minute[-1][0] != minute:
                grouped_by_minute.append((minute, [(event, prio)]))
            else:
                grouped_by_minute[-1][1].append((event, prio))

        state = "NOT_OPENED"
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        last_m = 0

        # Event sweep across distinct event timestamps
        for m, ev_list in grouped_by_minute:
            # Advance time from last_m to m
            if had_valid_open and state == "RUNNING" and m > last_m:
                delta_biz = biz_minutes(m) - biz_minutes(last_m)
                if not breached:
                    limit = PRIORITY_LIMITS[priority]
                    if used_minutes + delta_biz > limit:
                        target = biz_minutes(last_m) + limit + 1 - used_minutes
                        t = find_first_minute_ge(last_m, m, target)
                        if t < m:
                            breached = True
                            breached_at = t
                used_minutes += delta_biz

            # Apply all events at minute m in stream order
            for ev, p in ev_list:
                if ev == "OPEN":
                    if state in ("NOT_OPENED", "CLOSED"):
                        state = "RUNNING"
                        priority = p
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif ev == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = p
                elif ev == "PAUSE":
                    if state == "RUNNING":
                        state = "PAUSED"
                elif ev == "RESUME":
                    if state == "PAUSED":
                        state = "RUNNING"
                elif ev == "CLOSE":
                    if state in ("RUNNING", "PAUSED"):
                        state = "CLOSED"
                elif ev == "REOPEN":
                    if state == "CLOSED":
                        state = "RUNNING"

            # Check breach at minute m after all events at m are applied
            if had_valid_open and not breached and state != "NOT_OPENED":
                limit = PRIORITY_LIMITS[priority]
                if used_minutes > limit:
                    breached = True
                    breached_at = m

            last_m = m

        if not had_valid_open:
            continue

        # Advance from last_m to now
        if state == "RUNNING" and now > last_m:
            delta_biz = biz_minutes(now) - biz_minutes(last_m)
            if not breached:
                limit = PRIORITY_LIMITS[priority]
                if used_minutes + delta_biz > limit:
                    target = biz_minutes(last_m) + limit + 1 - used_minutes
                    t = find_first_minute_ge(last_m, now, target)
                    if t <= now:
                        breached = True
                        breached_at = t
            used_minutes += delta_biz

        status = state.lower()
        results.append({
            "ticket_id": ticket_id,
            "priority": priority,
            "used_minutes": used_minutes,
            "breached": breached,
            "breached_at": breached_at,
            "status": status,
        })

    results.sort(key=lambda x: x["ticket_id"])
    return results