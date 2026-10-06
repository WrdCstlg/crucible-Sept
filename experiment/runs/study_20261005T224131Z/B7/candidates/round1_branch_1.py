from bisect import bisect_left
from collections import defaultdict
from itertools import groupby

VALID_EVENTS = {"OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}
VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}
PRIORITY_LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}


def compute_sla(stream):
    holiday_days = set()
    ticket_events = []

    # 1. Parse stream
    stream_idx = 0
    for line in stream:
        trimmed = line.strip()
        if not trimmed:
            continue
        parts = trimmed.split(",")
        if len(parts) not in (3, 4):
            continue

        f0 = parts[0].strip()
        f1 = parts[1].strip()
        f2 = parts[2].strip()

        if not f0 or not f0.isascii() or not all("0" <= c <= "9" for c in f0):
            continue
        minute = int(f0)

        ticket_id = f1
        if not ticket_id:
            continue

        event = f2
        if event not in VALID_EVENTS:
            continue

        if event == "HOLIDAY":
            if len(parts) != 3 or ticket_id != "*":
                continue
            holiday_days.add(minute // 1440)
            continue

        if ticket_id == "*":
            continue

        if event in ("OPEN", "PRIORITY"):
            if len(parts) != 4:
                continue
            p = parts[3].strip()
            if p not in VALID_PRIORITIES:
                continue
            ticket_events.append((minute, stream_idx, ticket_id, event, p))
            stream_idx += 1
        else:
            if len(parts) != 3:
                continue
            ticket_events.append((minute, stream_idx, ticket_id, event, None))
            stream_idx += 1

    if not ticket_events:
        return []

    now = max(ev[0] for ev in ticket_events)

    # 2. Calendar calendar pre-computation
    weekday_holidays = sorted(d for d in holiday_days if d % 7 < 5)
    holiday_set = set(weekday_holidays)

    def business_minutes_in_day_prefix(d, m_day):
        if d % 7 >= 5 or d in holiday_set:
            return 0
        if m_day <= 540:
            return 0
        if m_day < 1020:
            return m_day - 540
        return 480

    def total_business_minutes(m):
        d = m // 1440
        m_day = m % 1440
        std_days = (d // 7) * 5 + min(d % 7, 5)
        hols = bisect_left(weekday_holidays, d)
        full_days_b_mins = (std_days - hols) * 480
        return full_days_b_mins + business_minutes_in_day_prefix(d, m_day)

    def get_kth_business_day(k):
        # 0-indexed k. Smallest d such that F(d + 1) >= k + 1
        low = 0
        high = (k + len(weekday_holidays)) // 5 * 7 + 14
        target = k + 1
        while low < high:
            mid = (low + high) // 2
            d_next = mid + 1
            std_days = (d_next // 7) * 5 + min(d_next % 7, 5)
            hols = bisect_left(weekday_holidays, d_next)
            f = std_days - hols
            if f >= target:
                high = mid
            else:
                low = mid + 1
        return low

    def get_minute_for_target_business_minutes(target):
        full_b_days = target // 480
        rem_m = target % 480
        if rem_m == 0:
            day = get_kth_business_day(full_b_days - 1)
            return day * 1440 + 1020
        else:
            day = get_kth_business_day(full_b_days)
            return day * 1440 + 540 + rem_m

    # 3. Group events by ticket
    events_by_ticket = defaultdict(list)
    for ev in ticket_events:
        events_by_ticket[ev[2]].append(ev)

    results = []

    # 4. Advance each ticket state machine
    for ticket_id, raw_events in events_by_ticket.items():
        # Sort stably by minute
        raw_events.sort(key=lambda x: x[0])

        events_by_minute = []
        for m, group in groupby(raw_events, key=lambda x: x[0]):
            events_by_minute.append((m, list(group)))

        status = "NOT_OPENED"
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        has_valid_open = False
        current_time = events_by_minute[0][0]

        def advance(t_start, t_end):
            nonlocal used_minutes, breached, breached_at
            if status != "RUNNING":
                return

            b_mins = total_business_minutes(t_end) - total_business_minutes(t_start)
            if b_mins == 0:
                return

            if breached:
                used_minutes += b_mins
                return

            limit = PRIORITY_LIMITS[priority]
            rem = limit - used_minutes + 1
            if b_mins < rem:
                used_minutes += b_mins
                return

            target = total_business_minutes(t_start) + rem
            t_breach = get_minute_for_target_business_minutes(target)

            if t_breach < t_end:
                breached = True
                breached_at = t_breach
                used_minutes += b_mins
            else:
                # t_breach == t_end; events at t_end apply before checking breach
                used_minutes += b_mins

        def apply_event(event_type, param):
            nonlocal status, priority, used_minutes, breached, breached_at, has_valid_open
            if event_type == "OPEN":
                if status in ("NOT_OPENED", "CLOSED"):
                    status = "RUNNING"
                    priority = param
                    used_minutes = 0
                    breached = False
                    breached_at = None
                    has_valid_open = True
            elif event_type == "PRIORITY":
                if status in ("RUNNING", "PAUSED"):
                    priority = param
            elif event_type == "PAUSE":
                if status == "RUNNING":
                    status = "PAUSED"
            elif event_type == "RESUME":
                if status == "PAUSED":
                    status = "RUNNING"
            elif event_type == "CLOSE":
                if status in ("RUNNING", "PAUSED"):
                    status = "CLOSED"
            elif event_type == "REOPEN":
                if status == "CLOSED":
                    status = "RUNNING"

        for m, ev_list in events_by_minute:
            if m > current_time:
                advance(current_time, m)
                current_time = m

            for _, _, _, ev_type, param in ev_list:
                apply_event(ev_type, param)

            if not breached and status != "NOT_OPENED" and priority is not None:
                if used_minutes > PRIORITY_LIMITS[priority]:
                    breached = True
                    breached_at = m

        if now > current_time:
            advance(current_time, now)
            current_time = now

        if not breached and status != "NOT_OPENED" and priority is not None:
            if used_minutes > PRIORITY_LIMITS[priority]:
                breached = True
                breached_at = now

        if has_valid_open:
            results.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": status.lower(),
            })

    results.sort(key=lambda d: d["ticket_id"])
    return results