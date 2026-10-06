from bisect import bisect_left


def compute_sla(stream):
    """
    Computes SLA tracking metrics for tickets processed through an event stream.
    Uses a per-ticket state machine advanced with closed-form business-minute arithmetic.
    """
    holidays_set = set()
    ticket_events = []
    order = 0

    for raw_line in stream:
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(",")
        n = len(parts)
        if n not in (3, 4):
            continue

        f0 = parts[0].strip()
        if not (f0.isdigit() and f0.isascii()):
            continue
        minute = int(f0)

        ticket_id = parts[1].strip()
        if not ticket_id:
            continue

        event = parts[2].strip()

        if event in ("OPEN", "PRIORITY"):
            if n != 4 or ticket_id == "*":
                continue
            p = parts[3].strip()
            if p not in ("P1", "P2", "P3", "P4"):
                continue
            ticket_events.append((minute, order, ticket_id, event, p))
            order += 1

        elif event in ("PAUSE", "RESUME", "CLOSE", "REOPEN"):
            if n != 3 or ticket_id == "*":
                continue
            ticket_events.append((minute, order, ticket_id, event, None))
            order += 1

        elif event == "HOLIDAY":
            if n != 3 or ticket_id != "*":
                continue
            day = minute // 1440
            if day % 7 < 5:  # Weekend days are already non-business days
                holidays_set.add(day)

        else:
            continue

    if not ticket_events:
        return []

    now = max(ev[0] for ev in ticket_events)
    holidays_list = sorted(holidays_set)

    def business_minutes_at_day_start(d):
        w = d // 7
        dow = d % 7
        std = w * 2400 + (5 if dow > 5 else dow) * 480
        k = bisect_left(holidays_list, d)
        return std - k * 480

    def cumulative_business_minutes(m):
        d = m // 1440
        mod = m % 1440
        w = d // 7
        dow = d % 7
        if dow < 5:
            std = w * 2400 + dow * 480 + min(max(0, mod - 540), 480)
        else:
            std = w * 2400 + 2400
        k = bisect_left(holidays_list, d)
        std -= k * 480
        if d in holidays_set:
            std -= min(max(0, mod - 540), 480)
        return std

    def business_minutes_between(start_m, end_m):
        if start_m >= end_m:
            return 0
        return cumulative_business_minutes(end_m) - cumulative_business_minutes(start_m)

    def find_breach_minute(start_m, end_m, target_b):
        low_d = start_m // 1440
        high_d = end_m // 1440

        while low_d < high_d:
            mid_d = (low_d + high_d) // 2
            if business_minutes_at_day_start(mid_d + 1) >= target_b:
                high_d = mid_d
            else:
                low_d = mid_d + 1

        d = low_d
        b_at_start = business_minutes_at_day_start(d)
        needed = target_b - b_at_start
        return d * 1440 + 540 + needed

    # Group ticket events by ticket_id
    ticket_events_by_id = {}
    for minute, ev_order, ticket_id, event, priority in ticket_events:
        if ticket_id not in ticket_events_by_id:
            ticket_events_by_id[ticket_id] = []
        ticket_events_by_id[ticket_id].append((minute, ev_order, event, priority))

    limits = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
    status_map = {"RUNNING": "running", "PAUSED": "paused", "CLOSED": "closed"}
    result = []

    for ticket_id in sorted(ticket_events_by_id.keys()):
        raw_events = ticket_events_by_id[ticket_id]
        raw_events.sort(key=lambda x: (x[0], x[1]))

        # Group events occurring at the exact same minute
        grouped_by_minute = []
        for ev in raw_events:
            m = ev[0]
            if not grouped_by_minute or grouped_by_minute[-1][0] != m:
                grouped_by_minute.append((m, [ev]))
            else:
                grouped_by_minute[-1][1].append(ev)

        state = "NOT_OPENED"
        priority = None
        used = 0
        breached = False
        breached_at = None
        ever_opened = False
        last_m = None

        for m, ev_list in grouped_by_minute:
            if last_m is not None and last_m < m:
                if state == "RUNNING":
                    b = business_minutes_between(last_m, m)
                    if breached:
                        used += b
                    else:
                        limit = limits[priority]
                        if used + b <= limit:
                            used += b
                        else:
                            needed = (limit + 1) - used
                            t_breach = find_breach_minute(
                                last_m, m, cumulative_business_minutes(last_m) + needed
                            )
                            if t_breach < m:
                                breached = True
                                breached_at = t_breach
                            used += b
                last_m = m
            elif last_m is None:
                last_m = m

            # Apply all events at minute m in stream order
            for _, _, event, p in ev_list:
                if event == "OPEN":
                    if state in ("NOT_OPENED", "CLOSED"):
                        state = "RUNNING"
                        priority = p
                        used = 0
                        breached = False
                        breached_at = None
                        ever_opened = True
                elif event == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = p
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

            # Check breach at minute m after applying all events at minute m
            if ever_opened and not breached:
                limit = limits[priority]
                if used > limit:
                    breached = True
                    breached_at = m

        # Advance ticket from its last event minute to "now"
        if last_m is not None and last_m < now:
            if state == "RUNNING":
                b = business_minutes_between(last_m, now)
                if breached:
                    used += b
                else:
                    limit = limits[priority]
                    if used + b <= limit:
                        used += b
                    else:
                        needed = (limit + 1) - used
                        t_breach = find_breach_minute(
                            last_m, now, cumulative_business_minutes(last_m) + needed
                        )
                        breached = True
                        breached_at = t_breach
                        used += b

        if ever_opened:
            result.append(
                {
                    "ticket_id": ticket_id,
                    "priority": priority,
                    "used_minutes": used,
                    "breached": breached,
                    "breached_at": breached_at,
                    "status": status_map[state],
                }
            )

    return result