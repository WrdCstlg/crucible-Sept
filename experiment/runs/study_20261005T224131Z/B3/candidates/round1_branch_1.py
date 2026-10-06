from bisect import bisect_left
from collections import defaultdict

LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}

STATUS_MAP = {
    1: "running",
    2: "paused",
    3: "closed",
}


def _build_calendar(weekday_holidays_sorted):
    """
    Returns (b_day, b) functions:
      b_day(d): business minutes in [0, d * 1440)
      b(t):     business minutes in [0, t)
    """

    def b_day(d: int) -> int:
        weeks = d // 7
        dow = d % 7
        std_minutes = weeks * 2400 + (dow if dow < 5 else 5) * 480
        h_count = bisect_left(weekday_holidays_sorted, d)
        return std_minutes - h_count * 480

    def b(t: int) -> int:
        d = t // 1440
        mod = t % 1440
        base = b_day(d)
        dow = d % 7
        if dow < 5:
            idx = bisect_left(weekday_holidays_sorted, d)
            if idx >= len(weekday_holidays_sorted) or weekday_holidays_sorted[idx] != d:
                if mod > 540:
                    base += min(mod - 540, 480)
        return base

    return b_day, b


def _find_breach_minute(target: int, t_start: int, t_end: int, b_day) -> int:
    """
    Finds the smallest minute t such that b(t) >= target,
    given that b(t_start) < target <= b(t_end).
    """
    low = t_start // 1440
    high = (t_end + 1439) // 1440
    while low < high:
        mid = (low + high) // 2
        if b_day(mid + 1) >= target:
            high = mid
        else:
            low = mid + 1
    d = low
    rem = target - b_day(d)
    return d * 1440 + 540 + rem


def compute_sla(stream):
    raw_holidays = set()
    events_by_ticket = defaultdict(list)
    max_ticket_m = -1
    has_ticket_events = False

    valid_events = {"OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}
    priorities = {"P1", "P2", "P3", "P4"}

    for orig_idx, raw_line in enumerate(stream):
        line = raw_line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) not in (3, 4):
            continue

        m_str, ticket_id, event = parts[0], parts[1], parts[2]
        if not m_str.isascii() or not m_str.isdigit():
            continue
        if not ticket_id or event not in valid_events:
            continue

        m = int(m_str)

        if event in ("OPEN", "PRIORITY"):
            if len(parts) != 4 or parts[3] not in priorities or ticket_id == "*":
                continue
            opt_p = parts[3]
        elif event == "HOLIDAY":
            if len(parts) != 3 or ticket_id != "*":
                continue
            raw_holidays.add(m // 1440)
            continue
        else:
            if len(parts) != 3 or ticket_id == "*":
                continue
            opt_p = None

        has_ticket_events = True
        if m > max_ticket_m:
            max_ticket_m = m
        events_by_ticket[ticket_id].append((m, orig_idx, event, opt_p))

    if not has_ticket_events:
        return []

    now = max_ticket_m

    # Only weekday holidays affect business hours
    weekday_holidays = sorted(d for d in raw_holidays if (d % 7) < 5)
    b_day, b = _build_calendar(weekday_holidays)

    results = []

    for ticket_id, ticket_events in events_by_ticket.items():
        ticket_events.sort(key=lambda e: (e[0], e[1]))

        state = 0  # 0: NOT_OPENED, 1: RUNNING, 2: PAUSED, 3: CLOSED
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        has_valid_open = False
        current_time = 0

        idx = 0
        n_events = len(ticket_events)
        while idx < n_events:
            m = ticket_events[idx][0]
            events_at_m = []
            while idx < n_events and ticket_events[idx][0] == m:
                events_at_m.append(ticket_events[idx])
                idx += 1

            # Advance state machine from current_time to m
            if current_time < m:
                if state == 1:
                    elapsed = b(m) - b(current_time)
                    if not breached:
                        limit = LIMITS[priority]
                        if used_minutes + elapsed > limit:
                            target = b(current_time) + (limit - used_minutes + 1)
                            t_breach = _find_breach_minute(target, current_time, m, b_day)
                            if t_breach < m:
                                breached = True
                                breached_at = t_breach
                    used_minutes += elapsed
                current_time = m

            # Apply all events at minute m
            for _, _, ev, p in events_at_m:
                if ev == "OPEN":
                    if state == 0 or state == 3:
                        state = 1
                        priority = p
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        has_valid_open = True
                elif ev == "PRIORITY":
                    if state == 1 or state == 2:
                        priority = p
                elif ev == "PAUSE":
                    if state == 1:
                        state = 2
                elif ev == "RESUME":
                    if state == 2:
                        state = 1
                elif ev == "CLOSE":
                    if state == 1 or state == 2:
                        state = 3
                elif ev == "REOPEN":
                    if state == 3:
                        state = 1

            # Check breach at minute m after all events at m take effect
            if not breached and priority is not None and m <= now:
                if used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = m

        # Advance ticket from last event time to "now"
        if current_time < now:
            if state == 1:
                elapsed = b(now) - b(current_time)
                if not breached:
                    limit = LIMITS[priority]
                    if used_minutes + elapsed > limit:
                        target = b(current_time) + (limit - used_minutes + 1)
                        t_breach = _find_breach_minute(target, current_time, now, b_day)
                        if t_breach <= now:
                            breached = True
                            breached_at = t_breach
                used_minutes += elapsed
            current_time = now

        if has_valid_open:
            results.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": STATUS_MAP[state],
            })

    results.sort(key=lambda x: x["ticket_id"])
    return results