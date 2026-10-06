from bisect import bisect_left
from collections import defaultdict

VALID_EVENTS_4 = {"OPEN", "PRIORITY"}
VALID_EVENTS_3 = {"PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}
VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}
LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}


def compute_sla(stream):
    holiday_days = set()
    events_by_ticket = defaultdict(list)
    max_ticket_minute = None

    for stream_idx, line in enumerate(stream):
        line = line.strip()
        if not line:
            continue

        raw_fields = line.split(",")
        if len(raw_fields) not in (3, 4):
            continue

        fields = [f.strip() for f in raw_fields]

        f0 = fields[0]
        if not (f0 and f0.isascii() and f0.isdigit()):
            continue
        minute = int(f0)

        ticket_id = fields[1]
        if not ticket_id:
            continue

        event = fields[2]

        if event in VALID_EVENTS_4:
            if len(fields) != 4:
                continue
            priority = fields[3]
            if priority not in VALID_PRIORITIES:
                continue
            if ticket_id == "*":
                continue
            events_by_ticket[ticket_id].append((minute, stream_idx, event, priority))
            if max_ticket_minute is None or minute > max_ticket_minute:
                max_ticket_minute = minute

        elif event in VALID_EVENTS_3:
            if len(fields) != 3:
                continue
            if event == "HOLIDAY":
                if ticket_id != "*":
                    continue
                holiday_days.add(minute // 1440)
            else:
                if ticket_id == "*":
                    continue
                events_by_ticket[ticket_id].append((minute, stream_idx, event, None))
                if max_ticket_minute is None or minute > max_ticket_minute:
                    max_ticket_minute = minute

    if max_ticket_minute is None:
        return []

    now = max_ticket_minute

    # Calendar structures: only weekday holidays affect business minutes
    weekday_holidays_set = {d for d in holiday_days if d % 7 < 5}
    sorted_weekday_holidays = sorted(weekday_holidays_set)
    num_weekday_holidays = len(sorted_weekday_holidays)

    def biz_days_before(d):
        if d <= 0:
            return 0
        num_weekdays = (d // 7) * 5 + min(5, d % 7)
        num_hols = bisect_left(sorted_weekday_holidays, d)
        return num_weekdays - num_hols

    def biz_minutes_before(m):
        d = m // 1440
        mod = m % 1440
        full_day_mins = biz_days_before(d) * 480
        if (d % 7 < 5) and (d not in weekday_holidays_set):
            today_mins = max(0, min(1020, mod) - 540)
        else:
            today_mins = 0
        return full_day_mins + today_mins

    def find_minute_for_biz_minutes(target_biz):
        target_day_index = (target_biz - 1) // 480
        b_target = target_day_index + 1

        low = target_day_index
        high = (b_target // 5 + 1) * 7 + num_weekday_holidays * 2 + 14

        while low < high:
            mid = (low + high) // 2
            if biz_days_before(mid + 1) >= b_target:
                high = mid
            else:
                low = mid + 1

        d = low
        prior_mins = biz_days_before(d) * 480
        rem = target_biz - prior_mins
        return d * 1440 + 540 + rem

    results = []

    for ticket_id, raw_events in events_by_ticket.items():
        raw_events.sort(key=lambda x: (x[0], x[1]))

        # Group events by minute, preserving stream arrival order
        grouped_events = []
        for minute, _, event_type, prio in raw_events:
            if grouped_events and grouped_events[-1][0] == minute:
                grouped_events[-1][1].append((event_type, prio))
            else:
                grouped_events.append((minute, [(event_type, prio)]))

        state = "NOT_OPENED"
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        last_minute = None

        for m, events_at_m in grouped_events:
            if had_valid_open and last_minute is not None and m > last_minute:
                if state == "RUNNING":
                    delta = biz_minutes_before(m) - biz_minutes_before(last_minute)
                    if not breached:
                        limit = LIMITS[priority]
                        if used_minutes + delta > limit:
                            k = limit + 1 - used_minutes
                            t_breach = find_minute_for_biz_minutes(
                                biz_minutes_before(last_minute) + k
                            )
                            if t_breach < m:
                                breached = True
                                breached_at = t_breach
                    used_minutes += delta
                last_minute = m

            for event_type, event_prio in events_at_m:
                if event_type == "OPEN":
                    if state == "NOT_OPENED":
                        state = "RUNNING"
                        priority = event_prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                        last_minute = m
                    elif state == "CLOSED":
                        state = "RUNNING"
                        priority = event_prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                        last_minute = m
                elif event_type == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = event_prio
                elif event_type == "PAUSE":
                    if state == "RUNNING":
                        state = "PAUSED"
                elif event_type == "RESUME":
                    if state == "PAUSED":
                        state = "RUNNING"
                elif event_type == "CLOSE":
                    if state in ("RUNNING", "PAUSED"):
                        state = "CLOSED"
                elif event_type == "REOPEN":
                    if state == "CLOSED":
                        state = "RUNNING"

            if had_valid_open and not breached:
                if used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = m

        if had_valid_open and last_minute is not None and last_minute < now:
            if state == "RUNNING":
                delta = biz_minutes_before(now) - biz_minutes_before(last_minute)
                if not breached:
                    limit = LIMITS[priority]
                    if used_minutes + delta > limit:
                        k = limit + 1 - used_minutes
                        t_breach = find_minute_for_biz_minutes(
                            biz_minutes_before(last_minute) + k
                        )
                        breached = True
                        breached_at = t_breach
                used_minutes += delta
            last_minute = now

        if had_valid_open:
            results.append(
                {
                    "ticket_id": ticket_id,
                    "priority": priority,
                    "used_minutes": used_minutes,
                    "breached": breached,
                    "breached_at": breached_at,
                    "status": state.lower(),
                }
            )

    results.sort(key=lambda x: x["ticket_id"])
    return results