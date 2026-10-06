from bisect import bisect_left
from collections import defaultdict


LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}


def compute_sla(stream):
    ticket_events = []
    effective_holidays = set()
    line_idx = 0

    for raw_line in stream:
        line = raw_line.strip()
        if not line:
            continue

        parts = [p.strip() for p in line.split(",")]
        if len(parts) not in (3, 4):
            continue

        f1 = parts[0]
        if not f1 or not f1.isdigit() or not f1.isascii():
            continue
        minute = int(f1)

        ticket_id = parts[1]
        if not ticket_id:
            continue

        event = parts[2]
        if event not in ("OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"):
            continue

        if event in ("OPEN", "PRIORITY"):
            if len(parts) != 4:
                continue
            priority = parts[3]
            if priority not in ("P1", "P2", "P3", "P4"):
                continue
        else:
            if len(parts) != 3:
                continue
            priority = None

        if event == "HOLIDAY":
            if ticket_id != "*":
                continue
            d = minute // 1440
            if d % 7 < 5:
                effective_holidays.add(d)
        else:
            if ticket_id == "*":
                continue
            ticket_events.append((minute, line_idx, ticket_id, event, priority))
            line_idx += 1

    if not ticket_events:
        return []

    now = max(ev[0] for ev in ticket_events)

    holiday_list = sorted(effective_holidays)
    holiday_set = effective_holidays

    def biz_days_before(d: int) -> int:
        weeks = d // 7
        rem = d % 7
        full = weeks * 5 + (rem if rem < 5 else 5)
        num_h = bisect_left(holiday_list, d)
        return (full - num_h) * 480

    def biz_before(m: int) -> int:
        if m <= 0:
            return 0
        d = m // 1440
        mod = m % 1440
        weeks = d // 7
        rem = d % 7
        full = weeks * 5 + (rem if rem < 5 else 5)
        num_h = bisect_left(holiday_list, d)

        if rem < 5 and d not in holiday_set:
            biz_today = max(0, min(480, mod - 540))
        else:
            biz_today = 0

        return (full - num_h) * 480 + biz_today

    def find_breach_minute(target: int, d_min: int, d_max: int) -> int:
        low = d_min
        high = d_max
        while low < high:
            mid = (low + high) // 2
            if biz_days_before(mid + 1) >= target:
                high = mid
            else:
                low = mid + 1
        d = low
        k = target - biz_days_before(d)
        return d * 1440 + 540 + k

    events_by_ticket = defaultdict(list)
    for ev in ticket_events:
        events_by_ticket[ev[2]].append(ev)

    results = []

    for t_id, ev_list in events_by_ticket.items():
        ev_list.sort(key=lambda x: (x[0], x[1]))

        had_valid_open = False
        status = "NOT_OPENED"
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        last_minute = 0

        i = 0
        n_evs = len(ev_list)

        while i < n_evs:
            m = ev_list[i][0]
            events_at_m = []
            while i < n_evs and ev_list[i][0] == m:
                events_at_m.append(ev_list[i])
                i += 1

            if had_valid_open and m > last_minute:
                if status == "RUNNING":
                    limit = LIMITS[priority]
                    target = biz_before(last_minute) + (limit + 1 - used_minutes)
                    if not breached and biz_before(m - 1) >= target:
                        breached = True
                        breached_at = find_breach_minute(
                            target, last_minute // 1440, (m - 1) // 1440
                        )
                    used_minutes += biz_before(m) - biz_before(last_minute)

            for ev in events_at_m:
                _, _, _, event_type, p = ev
                if event_type == "OPEN":
                    if status in ("NOT_OPENED", "CLOSED"):
                        had_valid_open = True
                        status = "RUNNING"
                        priority = p
                        used_minutes = 0
                        breached = False
                        breached_at = None
                elif event_type == "PRIORITY":
                    if status in ("RUNNING", "PAUSED"):
                        priority = p
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

            if had_valid_open:
                last_minute = m
                if not breached and used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = m

        if had_valid_open:
            if last_minute < now:
                if status == "RUNNING":
                    limit = LIMITS[priority]
                    target = biz_before(last_minute) + (limit + 1 - used_minutes)
                    if not breached and biz_before(now) >= target:
                        breached = True
                        breached_at = find_breach_minute(
                            target, last_minute // 1440, now // 1440
                        )
                    used_minutes += biz_before(now) - biz_before(last_minute)

            results.append({
                "ticket_id": t_id,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": status.lower(),
            })

    results.sort(key=lambda x: x["ticket_id"])
    return results