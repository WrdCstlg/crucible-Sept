from bisect import bisect_left

LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}

VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}
VALID_EVENTS = {"OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}


def _biz_days_before(d, sorted_holidays):
    """Number of business days strictly before calendar day d."""
    return (d // 7) * 5 + min(d % 7, 5) - bisect_left(sorted_holidays, d)


def _biz_mins_before(m, sorted_holidays, holiday_set):
    """Number of business minutes strictly before minute m."""
    if m <= 0:
        return 0
    d = m // 1440
    r = m % 1440

    full_biz_days = (d // 7) * 5 + min(d % 7, 5) - bisect_left(sorted_holidays, d)
    total = full_biz_days * 480

    if d % 7 < 5 and d not in holiday_set:
        if r > 540:
            total += min(r, 1020) - 540

    return total


def _find_breach_minute(t_start, needed_mins, sorted_holidays, holiday_set, n_holidays):
    """
    Find the smallest minute t such that the number of business minutes
    in [t_start, t) equals needed_mins (where needed_mins >= 1).
    """
    b_start = _biz_mins_before(t_start, sorted_holidays, holiday_set)
    b_target = b_start + needed_mins

    full_biz_days = b_target // 480
    rem_biz_mins = b_target % 480

    if rem_biz_mins > 0:
        k = full_biz_days + 1
    else:
        k = full_biz_days

    # Binary search for calendar day d of the k-th business day
    low = 0
    high = ((k + n_holidays) // 5 + 2) * 7
    while low < high:
        mid = (low + high) // 2
        d_next = mid + 1
        cnt = (d_next // 7) * 5 + min(d_next % 7, 5) - bisect_left(sorted_holidays, d_next)
        if cnt >= k:
            high = mid
        else:
            low = mid + 1

    target_day = low
    if rem_biz_mins > 0:
        return target_day * 1440 + 540 + rem_biz_mins
    else:
        return target_day * 1440 + 1020


def compute_sla(stream):
    holiday_days = set()
    events_by_ticket = {}
    now = None
    stream_index = 0

    # 1. Parse and validate stream
    for line in stream:
        line = line.strip()
        if not line:
            continue

        fields = [f.strip() for f in line.split(",")]
        n_fields = len(fields)
        if n_fields not in (3, 4):
            continue

        f0, f1, f2 = fields[0], fields[1], fields[2]

        # Field 1: base-10 ASCII digits
        if not f0 or not all("0" <= c <= "9" for c in f0):
            continue
        minute = int(f0)

        # Field 2: non-empty ticket ID
        if not f1:
            continue

        # Field 3: event
        if f2 not in VALID_EVENTS:
            continue

        # Event-specific field count and priority checks
        if f2 in ("OPEN", "PRIORITY"):
            if n_fields != 4:
                continue
            f3 = fields[3]
            if f3 not in VALID_PRIORITIES:
                continue
            priority_arg = f3
        else:
            if n_fields != 3:
                continue
            priority_arg = None

        # Ticket ID check: HOLIDAY requires '*', all other events disallow '*'
        if f2 == "HOLIDAY":
            if f1 != "*":
                continue
            holiday_days.add(minute // 1440)
        else:
            if f1 == "*":
                continue
            if now is None or minute > now:
                now = minute
            if f1 not in events_by_ticket:
                events_by_ticket[f1] = []
            events_by_ticket[f1].append((minute, stream_index, f2, priority_arg))
            stream_index += 1

    # If no well-formed ticket events, return empty list
    if now is None:
        return []

    # 2. Prepare calendar structures
    # Only keep holidays falling on weekdays (Monday-Friday)
    weekday_holidays = {d for d in holiday_days if d % 7 < 5}
    sorted_holidays = sorted(weekday_holidays)
    n_holidays = len(sorted_holidays)

    # 3. Simulate each ticket independently
    status_map = {
        "RUNNING": "running",
        "PAUSED": "paused",
        "CLOSED": "closed",
    }

    results = []

    for ticket_id, raw_events in events_by_ticket.items():
        # Sort stably by minute
        raw_events.sort(key=lambda x: x[0])

        # Group events by minute
        grouped_events = []
        cur_m = None
        cur_group = []
        for ev in raw_events:
            m = ev[0]
            if m != cur_m:
                if cur_group:
                    grouped_events.append((cur_m, cur_group))
                cur_m = m
                cur_group = [ev]
            else:
                cur_group.append(ev)
        if cur_group:
            grouped_events.append((cur_m, cur_group))

        state = "NOT_OPENED"
        priority = None
        used = 0
        breached = False
        breached_at = None
        had_valid_open = False
        prev_minute = None

        for m, ev_list in grouped_events:
            if prev_minute is not None and prev_minute < m:
                if state == "RUNNING":
                    # Check breach during (prev_minute, m)
                    if not breached:
                        limit = LIMITS[priority]
                        r = limit - used + 1
                        t_star = _find_breach_minute(prev_minute, r, sorted_holidays, weekday_holidays, n_holidays)
                        if t_star < m:
                            breached = True
                            breached_at = t_star
                    delta = _biz_mins_before(m, sorted_holidays, weekday_holidays) - _biz_mins_before(
                        prev_minute, sorted_holidays, weekday_holidays
                    )
                    used += delta

            # Apply all events at minute m in original order
            for ev in ev_list:
                etype = ev[2]
                eprio = ev[3]

                if etype == "OPEN":
                    if state == "NOT_OPENED":
                        state = "RUNNING"
                        priority = eprio
                        used = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                    elif state == "CLOSED":
                        state = "RUNNING"
                        priority = eprio
                        used = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif etype == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = eprio
                elif etype == "PAUSE":
                    if state == "RUNNING":
                        state = "PAUSED"
                elif etype == "RESUME":
                    if state == "PAUSED":
                        state = "RUNNING"
                elif etype == "CLOSE":
                    if state in ("RUNNING", "PAUSED"):
                        state = "CLOSED"
                elif etype == "REOPEN":
                    if state == "CLOSED":
                        state = "RUNNING"

            # Check breach at minute m after all events at minute m are applied
            if had_valid_open and not breached and priority is not None:
                if used > LIMITS[priority]:
                    breached = True
                    breached_at = m

            prev_minute = m

        # Interval after the last event minute up to "now"
        if prev_minute is not None and prev_minute < now:
            if state == "RUNNING":
                if not breached:
                    limit = LIMITS[priority]
                    r = limit - used + 1
                    t_star = _find_breach_minute(prev_minute, r, sorted_holidays, weekday_holidays, n_holidays)
                    if t_star <= now:
                        breached = True
                        breached_at = t_star
                delta = _biz_mins_before(now, sorted_holidays, weekday_holidays) - _biz_mins_before(
                    prev_minute, sorted_holidays, weekday_holidays
                )
                used += delta

        if had_valid_open:
            results.append(
                {
                    "ticket_id": ticket_id,
                    "priority": priority,
                    "used_minutes": used,
                    "breached": breached,
                    "breached_at": breached_at,
                    "status": status_map[state],
                }
            )

    # 4. Sort results by ticket_id ascending
    results.sort(key=lambda x: x["ticket_id"])
    return results