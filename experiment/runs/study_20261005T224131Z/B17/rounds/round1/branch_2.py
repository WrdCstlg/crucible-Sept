from bisect import bisect_left

LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}

VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}
VALID_EVENTS = {"OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}


def compute_sla(stream):
    holidays = set()
    ticket_events = []

    # Parse and validate stream
    for stream_idx, line in enumerate(stream):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(",")]
        if len(parts) not in (3, 4):
            continue

        f1 = parts[0]
        if not f1 or not (f1.isascii() and f1.isdigit()):
            continue
        minute = int(f1)

        ticket_id = parts[1]
        if not ticket_id:
            continue

        event = parts[2]
        if event not in VALID_EVENTS:
            continue

        if event == "HOLIDAY":
            if len(parts) != 3 or ticket_id != "*":
                continue
            holidays.add(minute // 1440)
        else:
            if ticket_id == "*":
                continue
            if event in ("OPEN", "PRIORITY"):
                if len(parts) != 4 or parts[3] not in VALID_PRIORITIES:
                    continue
                ticket_events.append((minute, stream_idx, ticket_id, event, parts[3]))
            else:
                if len(parts) != 3:
                    continue
                ticket_events.append((minute, stream_idx, ticket_id, event, None))

    if not ticket_events:
        return []

    # "Now" is the largest minute among all well-formed ticket events
    now = max(ev[0] for ev in ticket_events)

    # Sort ticket events by minute; stable sort preserves original stream order
    ticket_events.sort(key=lambda x: x[0])

    # Calendar helpers
    weekday_holidays = sorted([d for d in holidays if d % 7 < 5])
    holiday_set = set(weekday_holidays)

    def actual_business_days_before(d):
        """Count of business days strictly before day d."""
        weeks = d // 7
        rem = d % 7
        base = weeks * 5 + (rem if rem < 5 else 5)
        h = bisect_left(weekday_holidays, d)
        return base - h

    def business_minutes_up_to(m):
        """Count of business minutes strictly before minute m."""
        d = m // 1440
        mod = m % 1440
        act = actual_business_days_before(d)
        ans = act * 480
        if (d % 7 < 5) and (d not in holiday_set):
            if mod > 540:
                ans += min(mod - 540, 480)
        return ans

    def find_breach_minute(start, needed):
        """Find the earliest minute b + 1 where business minutes in [start, b + 1) == needed."""
        target = business_minutes_up_to(start) + needed
        target_actual = (target - 1) // 480 + 1

        low = start // 1440
        high = now // 1440
        ans_d = None
        while low <= high:
            mid = (low + high) // 2
            if actual_business_days_before(mid + 1) >= target_actual:
                ans_d = mid
                high = mid - 1
            else:
                low = mid + 1

        if ans_d is None:
            return now + 1

        d = ans_d
        act_d = actual_business_days_before(d)
        rem = target - act_d * 480
        return d * 1440 + 540 + rem

    # Group events by ticket_id preserving minute and stream order
    events_by_ticket = {}
    for minute, _, ticket_id, event, priority in ticket_events:
        if ticket_id not in events_by_ticket:
            events_by_ticket[ticket_id] = []
        events_by_ticket[ticket_id].append((minute, event, priority))

    results = []

    for ticket_id, evs in events_by_ticket.items():
        # Check if the ticket had at least one valid OPEN
        # Group events by distinct minute
        grouped_by_minute = {}
        for m, ev_type, p in evs:
            if m not in grouped_by_minute:
                grouped_by_minute[m] = []
            grouped_by_minute[m].append((ev_type, p))

        distinct_minutes = sorted(grouped_by_minute.keys())

        # Phase 1: Event sweep to rebuild each ticket's running intervals
        # State machine transitions:
        # States: NOT_OPENED, RUNNING, PAUSED, CLOSED
        state = "NOT_OPENED"
        curr_p = None
        has_valid_open = False

        # Intervals since most recent valid OPEN:
        # Each interval: (start_minute, end_minute, is_running, priority_during, priority_after_end)
        intervals = []
        prev_m = None

        for m in distinct_minutes:
            if state != "NOT_OPENED":
                # Record the interval [prev_m, m)
                intervals.append((prev_m, m, state == "RUNNING", curr_p))

            # Apply all events at minute m
            events_at_m = grouped_by_minute[m]
            for ev_type, p in events_at_m:
                if ev_type == "OPEN":
                    if state in ("NOT_OPENED", "CLOSED"):
                        state = "RUNNING"
                        curr_p = p
                        has_valid_open = True
                        # A valid OPEN clears prior intervals and resets used time
                        intervals.clear()
                elif ev_type == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        curr_p = p
                elif ev_type == "PAUSE":
                    if state == "RUNNING":
                        state = "PAUSED"
                elif ev_type == "RESUME":
                    if state == "PAUSED":
                        state = "RUNNING"
                elif ev_type == "CLOSE":
                    if state in ("RUNNING", "PAUSED"):
                        state = "CLOSED"
                elif ev_type == "REOPEN":
                    if state == "CLOSED":
                        state = "RUNNING"

            prev_m = m

        if not has_valid_open:
            continue

        # If now > last event minute, extend to now
        if now > prev_m:
            intervals.append((prev_m, now, state == "RUNNING", curr_p))

        # Phase 2: Count business minutes per interval and evaluate breach
        used_minutes = 0
        breached = False
        breached_at = None

        for idx, (t_start, t_end, is_running, p_during) in enumerate(intervals):
            if is_running:
                bm = business_minutes_up_to(t_end) - business_minutes_up_to(t_start)
                if not breached:
                    needed = LIMITS[p_during] + 1 - used_minutes
                    if bm >= needed:
                        b_plus_1 = find_breach_minute(t_start, needed)
                        if b_plus_1 < t_end:
                            breached = True
                            breached_at = b_plus_1
                        elif b_plus_1 == t_end and t_end == now and idx == len(intervals) - 1:
                            breached = True
                            breached_at = now
                used_minutes += bm

            # Check for breach at minute t_end (after events at t_end have been applied)
            if not breached and t_end <= now:
                if idx + 1 < len(intervals):
                    p_after = intervals[idx + 1][3]
                else:
                    p_after = curr_p
                if used_minutes > LIMITS[p_after]:
                    breached = True
                    breached_at = t_end

        results.append({
            "ticket_id": ticket_id,
            "priority": curr_p,
            "used_minutes": used_minutes,
            "breached": breached,
            "breached_at": breached_at,
            "status": state.lower(),
        })

    # Output sorted by ticket_id ascending in Python's default string order
    results.sort(key=lambda d: d["ticket_id"])
    return results