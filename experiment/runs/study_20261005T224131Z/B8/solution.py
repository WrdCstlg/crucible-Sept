from bisect import bisect_left, bisect_right
from itertools import groupby

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

VALID_EVENTS = {"OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}
VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}


def compute_sla(stream):
    holidays = set()
    ticket_events = {}
    max_ticket_minute = -1
    order = 0

    for raw_line in stream:
        line = raw_line.strip()
        if not line:
            continue
        fields = [f.strip() for f in line.split(",")]
        if len(fields) not in (3, 4):
            continue

        f0, f1, f2 = fields[0], fields[1], fields[2]
        f3 = fields[3] if len(fields) == 4 else None

        if not (f0 and all("0" <= c <= "9" for c in f0)):
            continue
        minute = int(f0)
        ticket_id = f1
        if not ticket_id:
            continue
        event = f2
        if event not in VALID_EVENTS:
            continue

        if event in ("OPEN", "PRIORITY"):
            if len(fields) != 4 or f3 not in VALID_PRIORITIES or ticket_id == "*":
                continue
            priority_field = f3
        elif event == "HOLIDAY":
            if len(fields) != 3 or ticket_id != "*":
                continue
            holidays.add(minute // 1440)
            continue
        else:
            if len(fields) != 3 or ticket_id == "*":
                continue
            priority_field = None

        if minute > max_ticket_minute:
            max_ticket_minute = minute

        if ticket_id not in ticket_events:
            ticket_events[ticket_id] = []
        ticket_events[ticket_id].append((minute, order, event, priority_field))
        order += 1

    if max_ticket_minute < 0:
        return []

    now = max_ticket_minute

    # Calendar structures: filter weekday holidays (0=Mon .. 4=Fri)
    weekday_holidays = {d for d in holidays if d % 7 < 5}
    holiday_list = sorted(weekday_holidays)
    holiday_set = weekday_holidays

    # holiday_diff[i] = nom_bday(holiday_list[i]) - i
    # Since each weekday holiday is distinct, holiday_diff is non-decreasing.
    holiday_diff = [((d // 7) * 5 + (d % 7)) - i for i, d in enumerate(holiday_list)]

    def total_business_minutes(m):
        if m <= 0:
            return 0
        d = m // 1440
        minute_of_day = m % 1440

        weeks = d // 7
        rem = d % 7
        nominal_bdays = weeks * 5 + (rem if rem < 5 else 5)
        num_holidays = bisect_left(holiday_list, d)
        full_day_bminutes = (nominal_bdays - num_holidays) * 480

        if rem < 5 and d not in holiday_set:
            partial = max(0, min(minute_of_day, 1020) - 540)
        else:
            partial = 0

        return full_day_bminutes + partial

    def find_breach_minute(start, k):
        bm_target = total_business_minutes(start) + k
        target_bm = bm_target - 1  # 0-indexed business minute
        b = target_bm // 480       # available business day index

        count = bisect_right(holiday_diff, b)
        B = b + count              # nominal business day index
        weeks = B // 5
        rem = B % 5
        d = weeks * 7 + rem

        minute_in_day = target_bm % 480
        x = d * 1440 + 540 + minute_in_day
        return x + 1

    results = []

    for ticket_id, events in ticket_events.items():
        events.sort(key=lambda x: x[0])  # Stable sort by minute

        state = "NOT_OPENED"
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        last_m = 0

        for m, group in groupby(events, key=lambda x: x[0]):
            events_at_m = [(item[2], item[3]) for item in group]

            if m > last_m:
                if state == "RUNNING":
                    if not breached:
                        k = LIMITS[priority] + 1 - used_minutes
                        bm = find_breach_minute(last_m, k)
                        if bm < m:
                            breached = True
                            breached_at = bm
                    used_minutes += total_business_minutes(m) - total_business_minutes(last_m)
                last_m = m

            for event, p_arg in events_at_m:
                if event == "OPEN":
                    if state == "NOT_OPENED":
                        state = "RUNNING"
                        priority = p_arg
                        used_minutes = 0
                        had_valid_open = True
                    elif state == "CLOSED":
                        state = "RUNNING"
                        priority = p_arg
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif event == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = p_arg
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

            if had_valid_open and not breached and state != "NOT_OPENED":
                if used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = m

        if last_m < now:
            if state == "RUNNING":
                if not breached:
                    k = LIMITS[priority] + 1 - used_minutes
                    bm = find_breach_minute(last_m, k)
                    if bm <= now:
                        breached = True
                        breached_at = bm
                used_minutes += total_business_minutes(now) - total_business_minutes(last_m)
            last_m = now

        if had_valid_open:
            results.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": STATUS_MAP[state],
            })

    results.sort(key=lambda x: x["ticket_id"])
    return results