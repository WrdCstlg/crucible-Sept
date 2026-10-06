from bisect import bisect_left
from collections import defaultdict
from itertools import groupby

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

STATUS_MAP = {
    RUNNING: "running",
    PAUSED: "paused",
    CLOSED: "closed",
}


def compute_sla(stream):
    holiday_days = set()
    ticket_events_by_id = defaultdict(list)
    has_ticket_events = False
    now = -1

    for line in stream:
        s = line.strip()
        if not s:
            continue
        parts = s.split(",")
        if len(parts) not in (3, 4):
            continue

        f0 = parts[0].strip()
        f1 = parts[1].strip()
        f2 = parts[2].strip()

        if not f0 or not all("0" <= c <= "9" for c in f0):
            continue
        minute = int(f0)

        if not f1:
            continue
        ticket_id = f1

        event = f2
        if event not in (
            "OPEN",
            "PRIORITY",
            "PAUSE",
            "RESUME",
            "CLOSE",
            "REOPEN",
            "HOLIDAY",
        ):
            continue

        if event in ("OPEN", "PRIORITY"):
            if len(parts) != 4:
                continue
            priority = parts[3].strip()
            if priority not in ("P1", "P2", "P3", "P4"):
                continue
        else:
            if len(parts) != 3:
                continue
            priority = None

        if event == "HOLIDAY":
            if ticket_id != "*":
                continue
            holiday_days.add(minute // 1440)
        else:
            if ticket_id == "*":
                continue
            has_ticket_events = True
            if minute > now:
                now = minute
            ticket_events_by_id[ticket_id].append((minute, event, priority))

    if not has_ticket_events:
        return []

    weekday_holidays = sorted(d for d in holiday_days if d % 7 < 5)
    num_holidays = len(weekday_holidays)

    def actual_business_minutes(t):
        if t <= 0:
            return 0
        d, m = divmod(t, 1440)
        weeks, rem_days = divmod(d, 7)
        res = weeks * 2400
        if rem_days >= 5:
            res += 2400
        else:
            res += rem_days * 480
            if m > 540:
                res += min(m - 540, 480)

        if num_holidays:
            idx = bisect_left(weekday_holidays, d)
            res -= idx * 480
            if idx < num_holidays and weekday_holidays[idx] == d:
                if m > 540:
                    res -= min(m - 540, 480)
        return res

    def find_first_minute(low, high, target):
        ans = high
        l = low
        r = high
        while l <= r:
            mid = (l + r) // 2
            if actual_business_minutes(mid) >= target:
                ans = mid
                r = mid - 1
            else:
                l = mid + 1
        return ans

    results = []

    for ticket_id in sorted(ticket_events_by_id.keys()):
        events = ticket_events_by_id[ticket_id]
        events.sort(key=lambda x: x[0])

        state = NOT_OPENED
        priority = None
        used = 0
        breached = False
        breached_at = None
        had_valid_open = False
        last_m = 0

        for m, group in groupby(events, key=lambda x: x[0]):
            events_at_m = [(ev, p) for _, ev, p in group]

            if state == RUNNING:
                if not breached:
                    need = LIMITS[priority] + 1 - used
                    target = actual_business_minutes(last_m) + need
                    if actual_business_minutes(m) >= target:
                        ans = find_first_minute(last_m, m, target)
                        if ans < m:
                            breached = True
                            breached_at = ans
                used += actual_business_minutes(m) - actual_business_minutes(last_m)

            last_m = m

            for ev, p_arg in events_at_m:
                if ev == "OPEN":
                    if state == NOT_OPENED:
                        state = RUNNING
                        priority = p_arg
                        used = 0
                        had_valid_open = True
                    elif state == CLOSED:
                        state = RUNNING
                        priority = p_arg
                        used = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif ev == "PRIORITY":
                    if state in (RUNNING, PAUSED):
                        priority = p_arg
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

            if had_valid_open and not breached:
                if used > LIMITS[priority]:
                    breached = True
                    breached_at = m

        if state == RUNNING:
            if not breached:
                need = LIMITS[priority] + 1 - used
                target = actual_business_minutes(last_m) + need
                if actual_business_minutes(now) >= target:
                    ans = find_first_minute(last_m, now, target)
                    breached = True
                    breached_at = ans
            used += actual_business_minutes(now) - actual_business_minutes(last_m)

        if had_valid_open:
            results.append(
                {
                    "ticket_id": ticket_id,
                    "priority": priority,
                    "used_minutes": used,
                    "breached": breached,
                    "breached_at": breached_at,
                    "status": STATUS_MAP[state],
                }
            )

    return results