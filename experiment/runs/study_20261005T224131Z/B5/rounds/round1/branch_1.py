from bisect import bisect_left
from collections import defaultdict

LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}

STATUS_MAP = {
    "RUNNING": "running",
    "PAUSED": "paused",
    "CLOSED": "closed",
}


def compute_sla(stream):
    holidays = set()
    ticket_events = []

    # 1. Parse stream
    for line in stream:
        raw = line.strip()
        if not raw:
            continue
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) not in (3, 4):
            continue

        f1, tid, ev = parts[0], parts[1], parts[2]
        if not (f1 and all("0" <= c <= "9" for c in f1)):
            continue
        if not tid:
            continue
        if ev not in (
            "OPEN",
            "PRIORITY",
            "PAUSE",
            "RESUME",
            "CLOSE",
            "REOPEN",
            "HOLIDAY",
        ):
            continue

        m = int(f1)

        if ev == "HOLIDAY":
            if tid != "*" or len(parts) != 3:
                continue
            holidays.add(m // 1440)
        else:
            if tid == "*":
                continue
            if ev in ("OPEN", "PRIORITY"):
                if len(parts) != 4 or parts[3] not in ("P1", "P2", "P3", "P4"):
                    continue
                p_arg = parts[3]
            else:
                if len(parts) != 3:
                    continue
                p_arg = None

            ticket_events.append((m, tid, ev, p_arg))

    if not ticket_events:
        return []

    # "Now" is the largest minute among all well-formed ticket events
    now = max(ev[0] for ev in ticket_events)

    # 2. Calendar setup
    # Holidays only reduce business minutes if they fall on Monday-Friday (day % 7 < 5)
    valid_holidays_list = sorted(d for d in holidays if d % 7 < 5)
    valid_holidays_set = set(valid_holidays_list)

    def F(t):
        """Closed-form business minutes in [0, t)."""
        if t <= 0:
            return 0
        d = t // 1440
        min_of_day = t % 1440
        weeks = d // 7
        rem_days = d % 7

        # Standard business minutes up to the start of day d
        bm_full_days = weeks * 2400 + (rem_days if rem_days < 5 else 5) * 480

        # Full business-day holidays strictly before day d
        h_count = bisect_left(valid_holidays_list, d)
        res = bm_full_days - h_count * 480

        # Business minutes on day d itself
        if rem_days < 5 and d not in valid_holidays_set:
            if min_of_day > 540:
                res += 480 if min_of_day >= 1020 else (min_of_day - 540)

        return res

    def find_breach_time(start_m, end_m, rem):
        """Find the earliest minute t in [start_m + 1, end_m] where F(t) - F(start_m) >= rem."""
        target = F(start_m) + rem
        low = start_m + 1
        high = end_m
        while low < high:
            mid = (low + high) // 2
            if F(mid) >= target:
                high = mid
            else:
                low = mid + 1
        return low

    # 3. Stable sort ticket events by minute and group by ticket
    ticket_events.sort(key=lambda x: x[0])

    events_by_ticket = defaultdict(list)
    for ev in ticket_events:
        events_by_ticket[ev[1]].append(ev)

    results = []

    # 4. Advance per-ticket state machines
    for tid, events in events_by_ticket.items():
        state = "NOT_OPENED"
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        t_prev = None

        # Group consecutive events by minute for this ticket
        grouped_events = []
        for ev in events:
            if grouped_events and grouped_events[-1][0] == ev[0]:
                grouped_events[-1][1].append(ev)
            else:
                grouped_events.append((ev[0], [ev]))

        for m, events_at_m in grouped_events:
            if t_prev is not None and m > t_prev:
                if state == "RUNNING":
                    delta = F(m) - F(t_prev)
                    if breached:
                        used_minutes += delta
                    else:
                        rem = LIMITS[priority] - used_minutes + 1
                        if delta >= rem:
                            b_time = find_breach_time(t_prev, m, rem)
                            if b_time < m:
                                breached = True
                                breached_at = b_time
                            used_minutes += delta
                        else:
                            used_minutes += delta
            t_prev = m

            # Apply all events at minute m
            for _, _, ev_type, p_arg in events_at_m:
                if ev_type == "OPEN":
                    if state in ("NOT_OPENED", "CLOSED"):
                        state = "RUNNING"
                        priority = p_arg
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif ev_type == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = p_arg
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

            # Check breach at minute m after every event at m has taken effect
            if had_valid_open and not breached and priority is not None:
                if used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = m

        # Advance ticket from its last event minute to "now"
        if t_prev is not None and now > t_prev:
            if state == "RUNNING":
                delta = F(now) - F(t_prev)
                if breached:
                    used_minutes += delta
                else:
                    rem = LIMITS[priority] - used_minutes + 1
                    if delta >= rem:
                        b_time = find_breach_time(t_prev, now, rem)
                        breached = True
                        breached_at = b_time
                        used_minutes += delta
                    else:
                        used_minutes += delta

        if had_valid_open:
            results.append(
                {
                    "ticket_id": tid,
                    "priority": priority,
                    "used_minutes": used_minutes,
                    "breached": breached,
                    "breached_at": breached_at,
                    "status": STATUS_MAP[state],
                }
            )

    results.sort(key=lambda d: d["ticket_id"])
    return results