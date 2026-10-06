from bisect import bisect_left
from collections import defaultdict

VALID_EVENTS = {"OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}
VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}
LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}


def raw_biz_minutes(m: int) -> int:
    """Number of business minutes in [0, m) ignoring holidays."""
    d = m // 1440
    minute_of_day = m % 1440
    weeks = d // 7
    rem_days = d % 7
    biz = weeks * 2400 + min(rem_days, 5) * 480
    if rem_days < 5 and minute_of_day > 540:
        biz += min(minute_of_day - 540, 480)
    return biz


def total_biz_minutes(m: int, sorted_holidays: list, holiday_set: set) -> int:
    """Total business minutes in [0, m) accounting for weekday holidays."""
    raw = raw_biz_minutes(m)
    d = m // 1440
    idx = bisect_left(sorted_holidays, d)
    holiday_mins = idx * 480
    if d in holiday_set:
        minute_of_day = m % 1440
        if minute_of_day > 540:
            holiday_mins += min(minute_of_day - 540, 480)
    return raw - holiday_mins


def find_first_minute(low: int, high: int, target: int, sorted_holidays: list, holiday_set: set) -> int:
    """Find the earliest minute t in [low, high] where total_biz_minutes(t) >= target."""
    while low < high:
        mid = (low + high) // 2
        if total_biz_minutes(mid, sorted_holidays, holiday_set) >= target:
            high = mid
        else:
            low = mid + 1
    return low


def compute_sla(stream):
    raw_holidays = set()
    ticket_events = defaultdict(list)
    now = None
    order_index = 0

    for raw_line in stream:
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) not in (3, 4):
            continue

        f1 = parts[0].strip()
        f2 = parts[1].strip()
        f3 = parts[2].strip()
        f4 = parts[3].strip() if len(parts) == 4 else None

        # Field 1: minute (ASCII digits 0-9 only)
        if not f1 or not f1.isascii() or not f1.isdigit():
            continue
        minute = int(f1)

        # Field 2: ticket ID (non-empty)
        if not f2:
            continue

        # Field 3: event
        if f3 not in VALID_EVENTS:
            continue

        # Event-specific field count and priority validation
        if f3 in ("OPEN", "PRIORITY"):
            if len(parts) != 4 or f4 not in VALID_PRIORITIES:
                continue
        else:
            if len(parts) != 3:
                continue

        # Ticket ID check for HOLIDAY vs non-HOLIDAY
        if f3 == "HOLIDAY":
            if f2 != "*":
                continue
            raw_holidays.add(minute // 1440)
        else:
            if f2 == "*":
                continue
            if now is None or minute > now:
                now = minute
            ticket_events[f2].append((minute, order_index, f3, f4))
            order_index += 1

    if now is None:
        return []

    # Only weekday holidays (Mon-Fri) affect business minutes
    business_holidays = {d for d in raw_holidays if (d % 7) < 5}
    sorted_holidays = sorted(business_holidays)

    results = []

    for ticket_id in ticket_events:
        events = ticket_events[ticket_id]
        events.sort(key=lambda x: x[0])  # Stable sort by minute

        minute_groups = []
        for minute, _, event, p_val in events:
            if minute_groups and minute_groups[-1][0] == minute:
                minute_groups[-1][1].append((event, p_val))
            else:
                minute_groups.append((minute, [(event, p_val)]))

        state = "NOT_OPENED"
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        current_minute = minute_groups[0][0]

        for m, events_at_m in minute_groups:
            # Advance time from current_minute to m
            if current_minute < m:
                if state == "RUNNING":
                    elapsed = (
                        total_biz_minutes(m, sorted_holidays, business_holidays)
                        - total_biz_minutes(current_minute, sorted_holidays, business_holidays)
                    )
                    if not breached and priority is not None:
                        limit = LIMITS[priority]
                        k = limit + 1 - used_minutes
                        if k <= elapsed:
                            target = (
                                total_biz_minutes(current_minute, sorted_holidays, business_holidays)
                                + k
                            )
                            t = find_first_minute(current_minute, m, target, sorted_holidays, business_holidays)
                            if t < m:
                                breached = True
                                breached_at = t
                    used_minutes += elapsed
                current_minute = m

            # Apply all events at minute m
            for event, p_val in events_at_m:
                if event == "OPEN":
                    if state in ("NOT_OPENED", "CLOSED"):
                        state = "RUNNING"
                        priority = p_val
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif event == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = p_val
                elif event == "PAUSE":
                    if state == "RUNNING":
                        state = "PAUSED"
                elif event == "RESUME":
                    if state == "PAUSED":
                        state = "RUNNING"
                elif event == "CLOSE":
                    if state in ("RUNNING", "PAUSED"):
                        state = "CLOSED"
                elif event == "REOPEN":
                    if state == "CLOSED":
                        state = "RUNNING"

            # Check breach at minute m after all events at minute m have been applied
            if had_valid_open and not breached and priority is not None:
                limit = LIMITS[priority]
                if used_minutes > limit:
                    breached = True
                    breached_at = m

        # Advance remaining time from current_minute to now
        if current_minute < now:
            if state == "RUNNING":
                elapsed = (
                    total_biz_minutes(now, sorted_holidays, business_holidays)
                    - total_biz_minutes(current_minute, sorted_holidays, business_holidays)
                )
                if not breached and priority is not None:
                    limit = LIMITS[priority]
                    k = limit + 1 - used_minutes
                    if k <= elapsed:
                        target = (
                            total_biz_minutes(current_minute, sorted_holidays, business_holidays)
                            + k
                        )
                        t = find_first_minute(current_minute, now, target, sorted_holidays, business_holidays)
                        breached = True
                        breached_at = t
                used_minutes += elapsed
            current_minute = now

        if had_valid_open:
            results.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": state.lower(),
            })

    results.sort(key=lambda x: x["ticket_id"])
    return results