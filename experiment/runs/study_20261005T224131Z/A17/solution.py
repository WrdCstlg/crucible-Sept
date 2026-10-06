from bisect import bisect_left
from collections import defaultdict


LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}

VALID_EVENTS = {
    "OPEN",
    "PRIORITY",
    "PAUSE",
    "RESUME",
    "CLOSE",
    "REOPEN",
    "HOLIDAY",
}

VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}


def compute_sla(stream):
    holiday_days = set()
    ticket_events = defaultdict(list)
    has_any_ticket_event = False
    now = -1
    orig_idx = 0

    for line in stream:
        s = line.strip()
        if not s:
            continue
        parts = s.split(",")
        num_parts = len(parts)
        if num_parts not in (3, 4):
            continue

        f0 = parts[0].strip()
        f1 = parts[1].strip()
        f2 = parts[2].strip()

        if not f0 or not f0.isascii() or not f0.isdigit():
            continue
        minute = int(f0)

        if not f1:
            continue
        ticket_id = f1

        event = f2
        if event not in VALID_EVENTS:
            continue

        if event in ("OPEN", "PRIORITY"):
            if num_parts != 4:
                continue
            p = parts[3].strip()
            if p not in VALID_PRIORITIES:
                continue
            priority_param = p
        else:
            if num_parts != 3:
                continue
            priority_param = None

        if event == "HOLIDAY":
            if ticket_id != "*":
                continue
            holiday_days.add(minute // 1440)
        else:
            if ticket_id == "*":
                continue
            has_any_ticket_event = True
            if minute > now:
                now = minute
            ticket_events[ticket_id].append((minute, orig_idx, event, priority_param))
            orig_idx += 1

    if not has_any_ticket_event:
        return []

    # Weekday holidays only (0=Mon ... 4=Fri)
    sorted_holidays = sorted(d for d in holiday_days if d % 7 < 5)
    num_holidays = len(sorted_holidays)

    def business_minutes(m):
        if m <= 0:
            return 0
        d_m, min_in_day = divmod(m, 1440)
        weeks, day = divmod(d_m, 7)
        if day < 5:
            raw = weeks * 2400 + day * 480
            if min_in_day > 540:
                raw += 480 if min_in_day >= 1020 else min_in_day - 540
        else:
            raw = weeks * 2400 + 2400

        idx = bisect_left(sorted_holidays, d_m)
        deduction = idx * 480
        if idx < num_holidays and sorted_holidays[idx] == d_m:
            if min_in_day > 540:
                deduction += 480 if min_in_day >= 1020 else min_in_day - 540
        return raw - deduction

    results = []

    for ticket_id in sorted(ticket_events.keys()):
        events = ticket_events[ticket_id]
        events.sort(key=lambda x: (x[0], x[1]))

        # Group events by minute
        grouped = []
        for ev in events:
            if not grouped or grouped[-1][0] != ev[0]:
                grouped.append((ev[0], [ev]))
            else:
                grouped[-1][1].append(ev)

        # Extend timeline to "now" if needed
        if grouped[-1][0] < now:
            grouped.append((now, []))

        state = "NOT_OPENED"
        priority = None
        used_time = 0
        breached = False
        breached_at = None
        has_valid_open = False

        m_prev = None
        b_prev = 0

        for m_curr, ev_list in grouped:
            b_curr = business_minutes(m_curr)

            if m_prev is not None:
                if state == "RUNNING":
                    used_in_interval = b_curr - b_prev
                    if not breached:
                        limit = LIMITS[priority]
                        needed = limit + 1 - used_time
                        target = b_prev + needed
                        if b_curr >= target:
                            # Binary search for first minute in [m_prev + 1, m_curr] reaching target
                            low = m_prev + 1
                            high = m_curr
                            t_breach = m_curr
                            while low <= high:
                                mid = (low + high) // 2
                                if business_minutes(mid) >= target:
                                    t_breach = mid
                                    high = mid - 1
                                else:
                                    low = mid + 1
                            if t_breach < m_curr:
                                breached = True
                                breached_at = t_breach
                    used_time += used_in_interval

            # Apply all events at m_curr in stream order
            for ev in ev_list:
                _, _, event_type, p_param = ev
                if event_type == "OPEN":
                    if state in ("NOT_OPENED", "CLOSED"):
                        state = "RUNNING"
                        priority = p_param
                        used_time = 0
                        breached = False
                        breached_at = None
                        has_valid_open = True
                elif event_type == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = p_param
                elif event_type == "PAUSE":
                    if state == "RUNNING":
                        state = "PAUSED"
                elif event_type == "RESUME":
                    if state == "PAUSED":
                        state = "RUNNING"
                elif event_type == "CLOSE":
                    if state in ("RUNNING", "PAUSED"):
                        state = "CLOSED"
                elif event_type == "REOPEN":
                    if state == "CLOSED":
                        state = "RUNNING"

            # Check breach at m_curr after all events applied
            if has_valid_open and not breached:
                limit = LIMITS[priority]
                if used_time > limit:
                    breached = True
                    breached_at = m_curr

            m_prev = m_curr
            b_prev = b_curr

        if has_valid_open:
            results.append(
                {
                    "ticket_id": ticket_id,
                    "priority": priority,
                    "used_minutes": used_time,
                    "breached": breached,
                    "breached_at": breached_at,
                    "status": state.lower(),
                }
            )

    return results