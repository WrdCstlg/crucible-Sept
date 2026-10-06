from bisect import bisect_left
from collections import defaultdict
from itertools import groupby

LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}

VALID_EVENTS = {"OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}
VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}

NOT_OPENED = 0
RUNNING = 1
PAUSED = 2
CLOSED = 3

STATUS_MAP = {
    RUNNING: "running",
    PAUSED: "paused",
    CLOSED: "closed",
}


def _parse_line(line):
    trimmed = line.strip()
    if not trimmed:
        return None
    raw_parts = trimmed.split(",")
    if len(raw_parts) not in (3, 4):
        return None
    parts = [p.strip() for p in raw_parts]

    # Field 1: minute (ASCII digits 0-9 only)
    m_str = parts[0]
    if not (m_str.isdigit() and m_str.isascii()):
        return None
    minute = int(m_str)

    # Field 2: ticket ID
    ticket_id = parts[1]
    if not ticket_id:
        return None

    # Field 3: event
    event = parts[2]
    if event not in VALID_EVENTS:
        return None

    # Field 4 / event rules
    if event in ("OPEN", "PRIORITY"):
        if len(parts) != 4:
            return None
        priority = parts[3]
        if priority not in VALID_PRIORITIES:
            return None
    else:
        if len(parts) != 3:
            return None
        priority = None

    if event == "HOLIDAY":
        if ticket_id != "*":
            return None
    else:
        if ticket_id == "*":
            return None

    return minute, ticket_id, event, priority


def _build_b_func(valid_holidays):
    holidays_len = len(valid_holidays)
    if holidays_len == 0:
        def b_func_no_holidays(m):
            weeks = m // 10080
            rem = m % 10080
            d_week = rem // 1440
            min_in_day = rem % 1440
            res = weeks * 2400 + (d_week if d_week < 5 else 5) * 480
            if d_week < 5 and min_in_day > 540:
                res += (min_in_day - 540) if min_in_day < 1020 else 480
            return res
        return b_func_no_holidays

    def b_func(m):
        weeks = m // 10080
        rem = m % 10080
        d_week = rem // 1440
        min_in_day = rem % 1440
        d_total = m // 1440

        idx = bisect_left(valid_holidays, d_total)
        res = weeks * 2400 + (d_week if d_week < 5 else 5) * 480 - idx * 480
        if d_week < 5:
            if idx == holidays_len or valid_holidays[idx] != d_total:
                if min_in_day > 540:
                    res += (min_in_day - 540) if min_in_day < 1020 else 480
        return res

    return b_func


def compute_sla(stream):
    holidays_set = set()
    ticket_events = defaultdict(list)
    max_ticket_minute = None

    for stream_idx, line in enumerate(stream):
        parsed = _parse_line(line)
        if parsed is None:
            continue
        minute, ticket_id, event, priority = parsed
        if event == "HOLIDAY":
            holidays_set.add(minute // 1440)
        else:
            if max_ticket_minute is None or minute > max_ticket_minute:
                max_ticket_minute = minute
            ticket_events[ticket_id].append((minute, stream_idx, event, priority))

    if max_ticket_minute is None:
        return []

    now = max_ticket_minute
    valid_holidays = sorted(d for d in holidays_set if (d % 7) < 5)
    b_func = _build_b_func(valid_holidays)

    results = []

    for tid in sorted(ticket_events.keys()):
        raw_list = ticket_events[tid]
        raw_list.sort(key=lambda x: (x[0], x[1]))

        grouped = []
        for m, grp in groupby(raw_list, key=lambda x: x[0]):
            grouped.append((m, list(grp)))

        if grouped[-1][0] < now:
            grouped.append((now, []))

        state = NOT_OPENED
        priority = None
        used_time = 0
        breached = False
        breached_at = None
        had_valid_open = False

        # Initialize at first event minute
        first_m, first_evs = grouped[0]
        for _, _, ev_type, ev_p in first_evs:
            if ev_type == "OPEN":
                if state == NOT_OPENED or state == CLOSED:
                    state = RUNNING
                    priority = ev_p
                    used_time = 0
                    breached = False
                    breached_at = None
                    had_valid_open = True
            elif ev_type == "PRIORITY":
                if state == RUNNING or state == PAUSED:
                    priority = ev_p
            elif ev_type == "PAUSE":
                if state == RUNNING:
                    state = PAUSED
            elif ev_type == "RESUME":
                if state == PAUSED:
                    state = RUNNING
            elif ev_type == "CLOSE":
                if state == RUNNING or state == PAUSED:
                    state = CLOSED
            elif ev_type == "REOPEN":
                if state == CLOSED:
                    state = RUNNING

        if had_valid_open and not breached and used_time > LIMITS[priority]:
            breached = True
            breached_at = first_m

        curr_time = first_m
        b_curr = b_func(curr_time)

        for next_time, next_evs in grouped[1:]:
            b_next = b_func(next_time)

            if state == RUNNING:
                if not breached:
                    needed = LIMITS[priority] + 1 - used_time
                    target = b_curr + needed
                    if next_time - 1 > curr_time and b_func(next_time - 1) >= target:
                        low = curr_time + 1
                        high = next_time - 1
                        while low < high:
                            mid = (low + high) // 2
                            if b_func(mid) >= target:
                                high = mid
                            else:
                                low = mid + 1
                        breached = True
                        breached_at = low

                used_time += b_next - b_curr

            for _, _, ev_type, ev_p in next_evs:
                if ev_type == "OPEN":
                    if state == NOT_OPENED or state == CLOSED:
                        state = RUNNING
                        priority = ev_p
                        used_time = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif ev_type == "PRIORITY":
                    if state == RUNNING or state == PAUSED:
                        priority = ev_p
                elif ev_type == "PAUSE":
                    if state == RUNNING:
                        state = PAUSED
                elif ev_type == "RESUME":
                    if state == PAUSED:
                        state = RUNNING
                elif ev_type == "CLOSE":
                    if state == RUNNING or state == PAUSED:
                        state = CLOSED
                elif ev_type == "REOPEN":
                    if state == CLOSED:
                        state = RUNNING

            if had_valid_open and not breached and used_time > LIMITS[priority]:
                breached = True
                breached_at = next_time

            curr_time = next_time
            b_curr = b_next

        if had_valid_open:
            results.append({
                "ticket_id": tid,
                "priority": priority,
                "used_minutes": used_time,
                "breached": breached,
                "breached_at": breached_at,
                "status": STATUS_MAP[state],
            })

    results.sort(key=lambda x: x["ticket_id"])
    return results