from bisect import bisect_left
from collections import defaultdict


def compute_sla(stream):
    raw_holidays = set()
    ticket_events = []

    # Parse stream
    for orig_idx, line in enumerate(stream):
        s = line.strip()
        if not s:
            continue
        parts = s.split(",")
        if len(parts) not in (3, 4):
            continue
        f0 = parts[0].strip()
        f1 = parts[1].strip()
        f2 = parts[2].strip()

        # Field 1: Minute (ASCII digits 0-9)
        if not f0 or not all("0" <= c <= "9" for c in f0):
            continue
        minute = int(f0)

        # Field 2: Ticket ID (non-empty)
        ticket_id = f1
        if not ticket_id:
            continue

        # Field 3: Event
        event = f2
        if event not in (
            "OPEN",
            "PRIORITY",
            "PAUSE",
            "RESUME",
            "CLOSE",
            "REOPEN",
            "HOLIDAY",
        ):
            continue

        if event in ("OPEN", "PRIORITY"):
            if len(parts) != 4:
                continue
            priority = parts[3].strip()
            if priority not in ("P1", "P2", "P3", "P4"):
                continue
        else:
            if len(parts) != 3:
                continue
            priority = None

        if event == "HOLIDAY":
            if ticket_id != "*":
                continue
            raw_holidays.add(minute // 1440)
        else:
            if ticket_id == "*":
                continue
            ticket_events.append((minute, orig_idx, ticket_id, event, priority))

    # If there are no well-formed ticket events, return []
    if not ticket_events:
        return []

    now = max(ev[0] for ev in ticket_events)

    # Filter weekday holidays and sort them for binary search
    holiday_days = sorted(d for d in raw_holidays if d % 7 < 5)
    holiday_set = set(holiday_days)

    # Calendar helper: returns count of business minutes in [0, m)
    def B(m):
        if m <= 0:
            return 0
        d = m // 1440
        mod = m % 1440
        full_weekdays = (d // 7) * 5 + min(d % 7, 5)
        h_count = bisect_left(holiday_days, d)
        effective_weekdays = full_weekdays - h_count
        total_bm = effective_weekdays * 480
        if d % 7 < 5 and d not in holiday_set:
            if mod > 540:
                total_bm += min(mod, 1020) - 540
        return total_bm

    def count_business_minutes(start, end):
        if end <= start:
            return 0
        return B(end) - B(start)

    def find_breach_minute(start, end, rem):
        target = B(start) + rem
        low = start
        high = end
        while low < high:
            mid = (low + high) // 2
            if B(mid) >= target:
                high = mid
            else:
                low = mid + 1
        return low

    LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}

    # Stable sort by minute, keeping original stream order for equal minutes
    ticket_events.sort(key=lambda x: (x[0], x[1]))

    # Group ticket events by ticket_id, then by minute
    events_by_ticket = defaultdict(lambda: defaultdict(list))
    for minute, orig_idx, ticket_id, event, priority in ticket_events:
        events_by_ticket[ticket_id][minute].append((event, priority))

    result = []

    # Process each ticket: sweep events to rebuild intervals, then count business minutes
    for ticket_id, minutes_dict in events_by_ticket.items():
        checkpoints = []
        state = "NOT_OPENED"
        priority = None
        ever_valid_open = False

        sorted_minutes = sorted(minutes_dict.keys())
        for m in sorted_minutes:
            ev_list = minutes_dict[m]
            valid_open_at_m = False
            for event, p_arg in ev_list:
                if state == "NOT_OPENED":
                    if event == "OPEN":
                        state = "RUNNING"
                        priority = p_arg
                        valid_open_at_m = True
                        ever_valid_open = True
                elif state == "RUNNING":
                    if event == "PRIORITY":
                        priority = p_arg
                    elif event == "PAUSE":
                        state = "PAUSED"
                    elif event == "CLOSE":
                        state = "CLOSED"
                elif state == "PAUSED":
                    if event == "PRIORITY":
                        priority = p_arg
                    elif event == "RESUME":
                        state = "RUNNING"
                    elif event == "CLOSE":
                        state = "CLOSED"
                elif state == "CLOSED":
                    if event == "OPEN":
                        state = "RUNNING"
                        priority = p_arg
                        valid_open_at_m = True
                        ever_valid_open = True
                    elif event == "REOPEN":
                        state = "RUNNING"

            if not ever_valid_open:
                continue

            # A valid OPEN resets used time and clears previous breach/intervals
            if valid_open_at_m:
                checkpoints = [(m, state, priority)]
            else:
                checkpoints.append((m, state, priority))

        if not ever_valid_open:
            continue

        # Rebuild intervals up to 'now'
        intervals = []
        for i in range(len(checkpoints) - 1):
            start = checkpoints[i][0]
            end = checkpoints[i + 1][0]
            st = checkpoints[i][1]
            pr = checkpoints[i][2]
            intervals.append((start, end, st, pr))

        last_m, last_st, last_pr = checkpoints[-1]
        if last_m < now:
            intervals.append((last_m, now, last_st, last_pr))
            state_at_now = last_st
            priority_at_now = last_pr
        else:
            state_at_now = last_st
            priority_at_now = last_pr

        # Count business minutes per interval and evaluate breach
        used_minutes = 0
        breached = False
        breached_at = None

        for start, end, st, pr in intervals:
            limit = LIMITS[pr]
            if not breached and used_minutes > limit:
                breached = True
                breached_at = start

            if st == "RUNNING":
                bm = count_business_minutes(start, end)
                if not breached:
                    rem = limit - used_minutes + 1
                    if bm >= rem:
                        t = find_breach_minute(start, end, rem)
                        if t < end:
                            breached = True
                            breached_at = t
                used_minutes += bm

        # Check breach condition at 'now'
        now_limit = LIMITS[priority_at_now]
        if not breached and used_minutes > now_limit:
            breached = True
            breached_at = now

        result.append(
            {
                "ticket_id": ticket_id,
                "priority": priority_at_now,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": state_at_now.lower(),
            }
        )

    result.sort(key=lambda d: d["ticket_id"])
    return result