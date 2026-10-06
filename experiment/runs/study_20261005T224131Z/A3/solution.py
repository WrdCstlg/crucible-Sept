from bisect import bisect_left
from itertools import groupby

LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}


def business_minutes_up_to(m: int, sorted_holidays: list[int]) -> int:
    if m <= 0:
        return 0
    day = m // 1440
    mod = m % 1440
    weeks = day // 7
    rem_days = day % 7
    total_b_days = weeks * 5 + min(rem_days, 5)

    idx = bisect_left(sorted_holidays, day)

    if rem_days < 5:
        if idx < len(sorted_holidays) and sorted_holidays[idx] == day:
            day_b_mins = 0
        else:
            day_b_mins = max(0, min(mod, 1020) - 540)
    else:
        day_b_mins = 0

    return (total_b_days - idx) * 480 + day_b_mins


def business_minutes_between(start_m: int, end_m: int, sorted_holidays: list[int]) -> int:
    if end_m <= start_m:
        return 0
    return business_minutes_up_to(end_m, sorted_holidays) - business_minutes_up_to(start_m, sorted_holidays)


def find_reach(prev_m: int, m_end: int, needed: int, sorted_holidays: list[int]) -> int:
    target = business_minutes_up_to(prev_m, sorted_holidays) + needed
    low = prev_m + 1
    high = m_end
    ans = m_end
    while low <= high:
        mid = (low + high) // 2
        if business_minutes_up_to(mid, sorted_holidays) >= target:
            ans = mid
            high = mid - 1
        else:
            low = mid + 1
    return ans


def compute_sla(stream):
    raw_holidays = set()
    ticket_events = {}
    now = None

    for line in stream:
        raw_line = line.strip()
        if not raw_line:
            continue

        parts = [p.strip() for p in raw_line.split(",")]
        if len(parts) not in (3, 4):
            continue

        m_str = parts[0]
        if not (m_str and m_str.isascii() and m_str.isdigit()):
            continue
        minute = int(m_str)

        ticket_id = parts[1]
        if not ticket_id:
            continue

        event = parts[2]
        if event not in ("OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"):
            continue

        if event == "HOLIDAY":
            if len(parts) != 3 or ticket_id != "*":
                continue
            raw_holidays.add(minute // 1440)
            continue

        if ticket_id == "*":
            continue

        if event in ("OPEN", "PRIORITY"):
            if len(parts) != 4:
                continue
            priority_param = parts[3]
            if priority_param not in ("P1", "P2", "P3", "P4"):
                continue
        else:
            if len(parts) != 3:
                continue
            priority_param = None

        if now is None or minute > now:
            now = minute

        if ticket_id not in ticket_events:
            ticket_events[ticket_id] = []
        ticket_events[ticket_id].append((minute, event, priority_param))

    if now is None:
        return []

    valid_holidays = {d for d in raw_holidays if (d % 7) < 5}
    sorted_holidays = sorted(valid_holidays)

    results = []

    for ticket_id, events in ticket_events.items():
        events.sort(key=lambda x: x[0])

        state = "NOT_OPENED"
        priority = None
        used = 0
        breached = False
        breached_at = None
        has_valid_open = False
        prev_m = None

        for m, group in groupby(events, key=lambda x: x[0]):
            ev_list = [(ev, param) for _, ev, param in group]

            if prev_m is not None and m > prev_m:
                if state == "RUNNING":
                    if not breached:
                        needed = LIMITS[priority] - used + 1
                        b_mins = business_minutes_between(prev_m, m, sorted_holidays)
                        if b_mins >= needed:
                            t_reach = find_reach(prev_m, m, needed, sorted_holidays)
                            if t_reach < m:
                                breached = True
                                breached_at = t_reach
                        used += b_mins
                    else:
                        used += business_minutes_between(prev_m, m, sorted_holidays)

            for ev, param in ev_list:
                if ev == "OPEN":
                    if state in ("NOT_OPENED", "CLOSED"):
                        state = "RUNNING"
                        priority = param
                        used = 0
                        breached = False
                        breached_at = None
                        has_valid_open = True
                elif ev == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = param
                elif ev == "PAUSE":
                    if state == "RUNNING":
                        state = "PAUSED"
                elif ev == "RESUME":
                    if state == "PAUSED":
                        state = "RUNNING"
                elif ev == "CLOSE":
                    if state in ("RUNNING", "PAUSED"):
                        state = "CLOSED"
                elif ev == "REOPEN":
                    if state == "CLOSED":
                        state = "RUNNING"

            if not breached and has_valid_open and state != "NOT_OPENED":
                if used > LIMITS[priority]:
                    breached = True
                    breached_at = m

            prev_m = m

        if prev_m is not None and prev_m < now:
            m = now
            if state == "RUNNING":
                if not breached:
                    needed = LIMITS[priority] - used + 1
                    b_mins = business_minutes_between(prev_m, m, sorted_holidays)
                    if b_mins >= needed:
                        t_reach = find_reach(prev_m, m, needed, sorted_holidays)
                        if t_reach < m:
                            breached = True
                            breached_at = t_reach
                        else:
                            breached = True
                            breached_at = m
                    used += b_mins
                else:
                    used += business_minutes_between(prev_m, m, sorted_holidays)

        if has_valid_open:
            results.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used,
                "breached": breached,
                "breached_at": breached_at,
                "status": state.lower(),
            })

    results.sort(key=lambda d: d["ticket_id"])
    return results