from bisect import bisect_left
from collections import defaultdict

LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}

NOT_OPENED = 0
RUNNING = 1
PAUSED = 2
CLOSED = 3


def compute_sla(stream):
    holiday_days = set()
    ticket_events = []
    line_idx = 0

    valid_events = {"OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}
    priorities = {"P1", "P2", "P3", "P4"}

    for raw_line in stream:
        line_idx += 1
        line = raw_line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(",")]
        n = len(parts)
        if n not in (3, 4):
            continue

        p0 = parts[0]
        if not (p0.isascii() and p0.isdigit() and len(p0) > 0):
            continue
        minute = int(p0)

        ticket_id = parts[1]
        if not ticket_id:
            continue

        event = parts[2]
        if event not in valid_events:
            continue

        if event in ("OPEN", "PRIORITY"):
            if n != 4:
                continue
            prio = parts[3]
            if prio not in priorities:
                continue
            if ticket_id == "*":
                continue
            ticket_events.append((minute, line_idx, ticket_id, event, prio))
        else:
            if n != 3:
                continue
            if event == "HOLIDAY":
                if ticket_id != "*":
                    continue
                holiday_days.add(minute // 1440)
            else:
                if ticket_id == "*":
                    continue
                ticket_events.append((minute, line_idx, ticket_id, event, None))

    if not ticket_events:
        return []

    ticket_events.sort(key=lambda x: (x[0], x[1]))
    now = max(ev[0] for ev in ticket_events)

    sorted_holidays = sorted(d for d in holiday_days if d % 7 < 5)

    def count_biz_minutes(T):
        if T <= 0:
            return 0
        num_weeks = T // 10080
        rem = T % 10080
        raw = num_weeks * 2400
        rem_days = rem // 1440
        rem_mins = rem % 1440

        raw += min(rem_days, 5) * 480
        if rem_days < 5:
            raw += max(0, min(rem_mins, 1020) - 540)

        D = T // 1440
        idx = bisect_left(sorted_holidays, D)
        hol_mins = idx * 480
        if idx < len(sorted_holidays) and sorted_holidays[idx] == D:
            hol_mins += max(0, min(T % 1440, 1020) - 540)

        return raw - hol_mins

    def find_breach(start, end, needed):
        target = count_biz_minutes(start) + needed
        low = start
        high = end
        while low < high:
            mid = (low + high) // 2
            if count_biz_minutes(mid) >= target:
                high = mid
            else:
                low = mid + 1
        return low

    events_by_ticket = defaultdict(list)
    for minute, _, tid, event, prio in ticket_events:
        events_by_ticket[tid].append((minute, event, prio))

    results = []

    for tid, events in events_by_ticket.items():
        # Group events by minute
        minute_groups = []
        curr_m = None
        curr_evs = []
        for m, ev, prio in events:
            if m != curr_m:
                if curr_m is not None:
                    minute_groups.append((curr_m, curr_evs))
                curr_m = m
                curr_evs = []
            curr_evs.append((ev, prio))
        if curr_m is not None:
            minute_groups.append((curr_m, curr_evs))

        # Event sweep that rebuilds each ticket's running intervals
        state = NOT_OPENED
        priority = None
        had_valid_open = False
        prev_m = None
        steps = []  # list of (interval or None, checkpoint_minute, checkpoint_priority)

        for m, ev_list in minute_groups:
            valid_open_in_group = False
            for ev, p in ev_list:
                if ev == "OPEN" and state in (NOT_OPENED, CLOSED):
                    valid_open_in_group = True
                    break

            if valid_open_in_group:
                # Wipes out prior history; start fresh epoch
                steps = []
                state = NOT_OPENED
                priority = None
                prev_m = None

            interval = None
            if prev_m is not None and state == RUNNING and prev_m < m:
                interval = (prev_m, m, priority)

            for ev, p in ev_list:
                if ev == "OPEN":
                    if state in (NOT_OPENED, CLOSED):
                        had_valid_open = True
                        state = RUNNING
                        priority = p
                elif ev == "PRIORITY":
                    if state in (RUNNING, PAUSED):
                        priority = p
                elif ev == "PAUSE":
                    if state == RUNNING:
                        state = PAUSED
                elif ev == "RESUME":
                    if state == PAUSED:
                        state = RUNNING
                elif ev == "CLOSE":
                    if state in (RUNNING, PAUSED):
                        state = CLOSED
                elif ev == "REOPEN":
                    if state == CLOSED:
                        state = RUNNING

            if had_valid_open:
                steps.append((interval, m, priority))
            prev_m = m

        if not had_valid_open:
            continue

        if state == RUNNING and prev_m < now:
            steps.append(((prev_m, now, priority), now, priority))

        # Count business minutes per interval
        used_minutes = 0
        breached = False
        breached_at = None

        for interval, cp_m, cp_prio in steps:
            if interval is not None:
                start, end, prio = interval
                b = count_biz_minutes(end) - count_biz_minutes(start)
                if not breached and b > 0:
                    needed = LIMITS[prio] - used_minutes + 1
                    if b >= needed:
                        bt = find_breach(start, end, needed)
                        if bt < end:
                            breached = True
                            breached_at = bt
                used_minutes += b

            if not breached:
                if used_minutes > LIMITS[cp_prio]:
                    breached = True
                    breached_at = cp_m

        status_str = {RUNNING: "running", PAUSED: "paused", CLOSED: "closed"}[state]

        results.append({
            "ticket_id": tid,
            "priority": priority,
            "used_minutes": used_minutes,
            "breached": breached,
            "breached_at": breached_at,
            "status": status_str,
        })

    results.sort(key=lambda d: d["ticket_id"])
    return results