from bisect import bisect_left
from collections import defaultdict

PRIORITY_LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}

VALID_EVENTS = {"OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}
VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}


def compute_sla(stream):
    holiday_days = set()
    ticket_events = []

    for stream_idx, line in enumerate(stream):
        s = line.strip()
        if not s:
            continue
        parts = [p.strip() for p in s.split(",")]
        num_parts = len(parts)
        if num_parts not in (3, 4):
            continue

        minute_str, ticket_id, event = parts[0], parts[1], parts[2]

        if not (minute_str.isascii() and minute_str.isdigit()):
            continue
        m = int(minute_str)

        if not ticket_id:
            continue

        if event not in VALID_EVENTS:
            continue

        if event in ("OPEN", "PRIORITY"):
            if num_parts != 4:
                continue
            priority = parts[3]
            if priority not in VALID_PRIORITIES:
                continue
        else:
            if num_parts != 3:
                continue
            priority = None

        if event == "HOLIDAY":
            if ticket_id != "*":
                continue
            holiday_days.add(m // 1440)
        else:
            if ticket_id == "*":
                continue
            ticket_events.append((m, stream_idx, ticket_id, event, priority))

    if not ticket_events:
        return []

    now = max(ev[0] for ev in ticket_events)

    # Weekday holidays calendar
    weekday_holidays = sorted(d for d in holiday_days if d % 7 < 5)
    weekday_holiday_set = set(weekday_holidays)

    def business_days(D):
        """Number of business days strictly before calendar day D."""
        if D <= 0:
            return 0
        raw_weekdays = (D // 7) * 5 + min(D % 7, 5)
        num_holidays = bisect_left(weekday_holidays, D)
        return raw_weekdays - num_holidays

    def total_bm(m):
        """Total business minutes in [0, m)."""
        d = m // 1440
        m_mod = m % 1440
        res = business_days(d) * 480
        if (d % 7 < 5) and (d not in weekday_holiday_set):
            if m_mod > 540:
                res += min(m_mod, 1020) - 540
        return res

    def get_kth_business_day(k):
        """Smallest calendar day d such that business_days(d + 1) >= k + 1."""
        low = (k // 5) * 7 + (k % 5)
        high = low + len(weekday_holidays) * 3 + 14
        target = k + 1
        ans = high
        while low <= high:
            mid = (low + high) // 2
            if business_days(mid + 1) >= target:
                ans = mid
                high = mid - 1
            else:
                low = mid + 1
        return ans

    def minute_of_business_minute(target_bm):
        """Smallest minute t such that total_bm(t) == target_bm."""
        rem = target_bm % 480
        if rem == 0:
            k = target_bm // 480 - 1
            d = get_kth_business_day(k)
            return d * 1440 + 1020
        else:
            k = target_bm // 480
            d = get_kth_business_day(k)
            return d * 1440 + 540 + rem

    events_by_ticket = defaultdict(list)
    for m, idx, ticket_id, event, priority in ticket_events:
        events_by_ticket[ticket_id].append((m, idx, event, priority))

    results = []

    for ticket_id in sorted(events_by_ticket.keys()):
        raw_evs = sorted(events_by_ticket[ticket_id], key=lambda x: (x[0], x[1]))

        # Group events by minute
        grouped_events = []
        for m, idx, event, priority in raw_evs:
            if grouped_events and grouped_events[-1][0] == m:
                grouped_events[-1][1].append((event, priority))
            else:
                grouped_events.append((m, [(event, priority)]))

        state = "NOT_OPENED"
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        curr_m = grouped_events[0][0]

        for m, evs in grouped_events:
            if m > curr_m:
                if state == "RUNNING":
                    bm = total_bm(m) - total_bm(curr_m)
                    if not breached:
                        limit = PRIORITY_LIMITS[priority]
                        need = limit - used_minutes + 1
                        if bm >= need:
                            target_bm = total_bm(curr_m) + need
                            t_b = minute_of_business_minute(target_bm)
                            if t_b < m:
                                breached = True
                                breached_at = t_b
                    used_minutes += bm
                curr_m = m

            # Apply all events at minute m in order
            for event, prio in evs:
                if event == "OPEN":
                    if state == "NOT_OPENED" or state == "CLOSED":
                        state = "RUNNING"
                        priority = prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif event == "PRIORITY":
                    if state == "RUNNING" or state == "PAUSED":
                        priority = prio
                elif event == "PAUSE":
                    if state == "RUNNING":
                        state = "PAUSED"
                elif event == "RESUME":
                    if state == "PAUSED":
                        state = "RUNNING"
                elif event == "CLOSE":
                    if state == "RUNNING" or state == "PAUSED":
                        state = "CLOSED"
                elif event == "REOPEN":
                    if state == "CLOSED":
                        state = "RUNNING"

            # Check breach after all events at minute m have been applied
            if not breached and had_valid_open and priority is not None and m <= now:
                limit = PRIORITY_LIMITS[priority]
                if used_minutes > limit:
                    breached = True
                    breached_at = m

        # Advance ticket from last event minute to "now"
        if curr_m < now:
            if state == "RUNNING":
                bm = total_bm(now) - total_bm(curr_m)
                if not breached:
                    limit = PRIORITY_LIMITS[priority]
                    need = limit - used_minutes + 1
                    if bm >= need:
                        target_bm = total_bm(curr_m) + need
                        t_b = minute_of_business_minute(target_bm)
                        breached = True
                        breached_at = t_b
                used_minutes += bm
            curr_m = now

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