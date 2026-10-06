from bisect import bisect_left
from collections import defaultdict


LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}

VALID_EVENTS_4 = {"OPEN", "PRIORITY"}
VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}
VALID_EVENTS_3 = {"PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}


def _business_minutes_up_to(t: int, holidays_weekday: list) -> int:
    """
    Returns the total number of business minutes in [0, t).
    Closed-form calendar arithmetic taking into account weekend days and weekday holidays.
    """
    if t <= 0:
        return 0

    d = t // 1440
    mod = t % 1440

    # Count weekday holidays strictly before day d
    k = bisect_left(holidays_weekday, d)

    # Full business days strictly before day d (excluding holidays)
    full_bus_days = (d // 7) * 5 + min(d % 7, 5) - k

    # Minutes on day d
    if (d % 7 >= 5) or (k < len(holidays_weekday) and holidays_weekday[k] == d):
        day_minutes = 0
    else:
        day_minutes = max(0, min(mod, 1020) - 540)

    return full_bus_days * 480 + day_minutes


def _get_business_day(k_bus: int, holidays_weekday: list) -> int:
    """
    Finds the calendar day d of the k_bus-th business day (0-indexed).
    That is, the unique day d where exactly k_bus business days precede d,
    and day d is itself a business day (weekday and not in holidays_weekday).
    """
    d_low = (k_bus // 5) * 7 + (k_bus % 5)
    d_high = ((k_bus + len(holidays_weekday)) // 5) * 7 + 6

    low = d_low
    high = d_high
    while low < high:
        mid = (low + high) // 2
        # Number of business days strictly before mid + 1
        k_mid = bisect_left(holidays_weekday, mid + 1)
        bus_days = ((mid + 1) // 7) * 5 + min((mid + 1) % 7, 5) - k_mid
        if bus_days >= k_bus + 1:
            high = mid
        else:
            low = mid + 1
    return low


def _invert_business_minutes(y: int, holidays_weekday: list) -> int:
    """
    Finds the smallest minute t such that _business_minutes_up_to(t, holidays_weekday) >= y.
    """
    if y <= 0:
        return 0

    d_full = y // 480
    r_min = y % 480

    if r_min > 0:
        d = _get_business_day(d_full, holidays_weekday)
        return d * 1440 + 540 + r_min
    else:
        d = _get_business_day(d_full - 1, holidays_weekday)
        return d * 1440 + 1020


def compute_sla(stream):
    raw_holidays = set()
    ticket_events_by_id = defaultdict(list)
    has_any_ticket_event = False
    max_ticket_minute = -1

    # 1. Parse stream
    for stream_idx, line in enumerate(stream):
        stripped = line.strip()
        if not stripped:
            continue

        fields = [f.strip() for f in stripped.split(",")]
        n_fields = len(fields)
        if n_fields not in (3, 4):
            continue

        m_str = fields[0]
        if not (m_str and all("0" <= c <= "9" for c in m_str)):
            continue
        m = int(m_str)

        tid = fields[1]
        if not tid:
            continue

        ev = fields[2]

        if ev in VALID_EVENTS_4:
            if n_fields != 4 or tid == "*":
                continue
            prio = fields[3]
            if prio not in VALID_PRIORITIES:
                continue
            ticket_events_by_id[tid].append((m, stream_idx, ev, prio))
            has_any_ticket_event = True
            if m > max_ticket_minute:
                max_ticket_minute = m

        elif ev == "HOLIDAY":
            if n_fields != 3 or tid != "*":
                continue
            raw_holidays.add(m // 1440)

        elif ev in VALID_EVENTS_3:
            if n_fields != 3 or tid == "*":
                continue
            ticket_events_by_id[tid].append((m, stream_idx, ev, None))
            has_any_ticket_event = True
            if m > max_ticket_minute:
                max_ticket_minute = m

    if not has_any_ticket_event:
        return []

    now = max_ticket_minute

    # 2. Build sorted list of weekday holidays
    holidays_weekday = sorted([d for d in raw_holidays if d % 7 < 5])

    # 3. Simulate state machine per ticket
    results = []

    for tid in sorted(ticket_events_by_id.keys()):
        events = ticket_events_by_id[tid]
        # Stable sort by minute
        events.sort(key=lambda x: (x[0], x[1]))

        state = "NOT_OPENED"  # 'NOT_OPENED', 'RUNNING', 'PAUSED', 'CLOSED'
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        m_last = 0

        idx = 0
        n_events = len(events)

        while idx < n_events:
            m_curr = events[idx][0]
            ev_list = []
            while idx < n_events and events[idx][0] == m_curr:
                ev_list.append(events[idx])
                idx += 1

            # Advance running ticket from m_last to m_curr
            if had_valid_open and m_curr > m_last:
                if state == "RUNNING":
                    if not breached:
                        limit = LIMITS[priority]
                        needed = limit - used_minutes + 1
                        if needed > 0:
                            b_last = _business_minutes_up_to(m_last, holidays_weekday)
                            t_breach = _invert_business_minutes(b_last + needed, holidays_weekday)
                            if t_breach < m_curr:
                                breached = True
                                breached_at = t_breach
                    used_minutes += (
                        _business_minutes_up_to(m_curr, holidays_weekday)
                        - _business_minutes_up_to(m_last, holidays_weekday)
                    )
                m_last = m_curr

            # Apply all events at m_curr in stream order
            for _, _, ev, prio in ev_list:
                if ev == "OPEN":
                    if state == "NOT_OPENED":
                        state = "RUNNING"
                        priority = prio
                        used_minutes = 0
                        had_valid_open = True
                    elif state == "CLOSED":
                        state = "RUNNING"
                        priority = prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                    # RUNNING or PAUSED: ignored
                elif ev == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = prio
                    # NOT_OPENED or CLOSED: ignored
                elif ev == "PAUSE":
                    if state == "RUNNING":
                        state = "PAUSED"
                    # NOT_OPENED, PAUSED, or CLOSED: ignored
                elif ev == "RESUME":
                    if state == "PAUSED":
                        state = "RUNNING"
                    # NOT_OPENED, RUNNING, or CLOSED: ignored
                elif ev == "CLOSE":
                    if state in ("RUNNING", "PAUSED"):
                        state = "CLOSED"
                    # NOT_OPENED or CLOSED: ignored
                elif ev == "REOPEN":
                    if state == "CLOSED":
                        state = "RUNNING"
                    # NOT_OPENED, RUNNING, or PAUSED: ignored

            # Check breach at m_curr after all events at m_curr have been applied
            if had_valid_open and not breached and state != "NOT_OPENED":
                limit = LIMITS[priority]
                if used_minutes > limit:
                    breached = True
                    breached_at = m_curr

            m_last = m_curr

        # Advance ticket from m_last to now
        if had_valid_open and now > m_last:
            if state == "RUNNING":
                if not breached:
                    limit = LIMITS[priority]
                    needed = limit - used_minutes + 1
                    if needed > 0:
                        b_last = _business_minutes_up_to(m_last, holidays_weekday)
                        t_breach = _invert_business_minutes(b_last + needed, holidays_weekday)
                        if t_breach <= now:
                            breached = True
                            breached_at = t_breach
                used_minutes += (
                    _business_minutes_up_to(now, holidays_weekday)
                    - _business_minutes_up_to(m_last, holidays_weekday)
                )
            m_last = now

        if had_valid_open:
            results.append({
                "ticket_id": tid,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": state.lower(),
            })

    return results