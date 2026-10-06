from bisect import bisect_left
from collections import defaultdict


LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}


def _cum_biz_minutes(m, weekday_holidays):
    """
    Returns the cumulative number of business minutes in [0, m).
    """
    if m <= 0:
        return 0

    d = m // 1440
    rem = m % 1440

    weeks = d // 7
    rem_days = d % 7
    full_biz_days = weeks * 5 + min(rem_days, 5)
    total = full_biz_days * 480

    if rem_days < 5 and rem > 540:
        total += min(rem, 1020) - 540

    idx = bisect_left(weekday_holidays, d)
    total -= idx * 480

    if idx < len(weekday_holidays) and weekday_holidays[idx] == d:
        if rem_days < 5 and rem > 540:
            total -= min(rem, 1020) - 540

    return total


def _find_breach_minute(current_time, needed, weekday_holidays):
    """
    Finds the smallest minute t >= current_time such that
    the business minutes elapsed in [current_time, t) is >= needed.
    """
    base = _cum_biz_minutes(current_time, weekday_holidays)
    target = base + needed

    step = 1
    while _cum_biz_minutes(current_time + step, weekday_holidays) < target:
        step *= 2

    low = current_time + step // 2
    high = current_time + step
    ans = high
    while low <= high:
        mid = (low + high) // 2
        if _cum_biz_minutes(mid, weekday_holidays) >= target:
            ans = mid
            high = mid - 1
        else:
            low = mid + 1

    return ans


def _parse_line(line):
    line = line.strip()
    if not line:
        return None
    parts = line.split(",")
    if len(parts) not in (3, 4):
        return None

    f0 = parts[0].strip()
    f1 = parts[1].strip()
    f2 = parts[2].strip()

    if not f0 or not all("0" <= c <= "9" for c in f0):
        return None
    minute = int(f0)

    ticket_id = f1
    if not ticket_id:
        return None

    event = f2
    if event not in ("OPEN", "PRIORITY", "PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"):
        return None

    if event in ("OPEN", "PRIORITY"):
        if len(parts) != 4:
            return None
        f3 = parts[3].strip()
        if f3 not in ("P1", "P2", "P3", "P4"):
            return None
        if ticket_id == "*":
            return None
        return (minute, ticket_id, event, f3)
    else:
        if len(parts) != 3:
            return None
        if event == "HOLIDAY":
            if ticket_id != "*":
                return None
            return (minute, "*", "HOLIDAY", None)
        else:
            if ticket_id == "*":
                return None
            return (minute, ticket_id, event, None)


def compute_sla(stream):
    holiday_days = set()
    ticket_events_by_id = defaultdict(list)
    has_ticket_events = False
    now = -1

    for original_idx, line in enumerate(stream):
        parsed = _parse_line(line)
        if parsed is None:
            continue
        minute, ticket_id, event, priority = parsed
        if event == "HOLIDAY":
            holiday_days.add(minute // 1440)
        else:
            has_ticket_events = True
            if minute > now:
                now = minute
            ticket_events_by_id[ticket_id].append((minute, original_idx, event, priority))

    if not has_ticket_events:
        return []

    weekday_holidays = sorted(d for d in holiday_days if d % 7 < 5)

    results = []

    for ticket_id in sorted(ticket_events_by_id.keys()):
        raw_events = ticket_events_by_id[ticket_id]
        raw_events.sort(key=lambda x: (x[0], x[1]))

        # Group events by minute
        events_by_minute = []
        for m, _, ev, prio in raw_events:
            if not events_by_minute or events_by_minute[-1][0] != m:
                events_by_minute.append((m, [(ev, prio)]))
            else:
                events_by_minute[-1][1].append((ev, prio))

        # Advance to "now" if not already present
        if events_by_minute[-1][0] < now:
            events_by_minute.append((now, []))

        status = "NOT_OPENED"
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        current_time = None

        for next_time, ev_list in events_by_minute:
            if status != "NOT_OPENED":
                # Advance time from current_time to next_time
                if status == "RUNNING":
                    delta_biz = _cum_biz_minutes(next_time, weekday_holidays) - _cum_biz_minutes(
                        current_time, weekday_holidays
                    )
                    if not breached:
                        limit = LIMITS[priority]
                        needed = limit - used_minutes + 1
                        if delta_biz >= needed:
                            b_min = _find_breach_minute(current_time, needed, weekday_holidays)
                            if b_min < next_time:
                                breached = True
                                breached_at = b_min
                    used_minutes += delta_biz

                current_time = next_time

            # Apply events taking effect at next_time
            for ev, prio in ev_list:
                if ev == "OPEN":
                    if status == "NOT_OPENED":
                        status = "RUNNING"
                        priority = prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                        current_time = next_time
                    elif status == "CLOSED":
                        status = "RUNNING"
                        priority = prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                elif ev == "PRIORITY":
                    if status in ("RUNNING", "PAUSED"):
                        priority = prio
                elif ev == "PAUSE":
                    if status == "RUNNING":
                        status = "PAUSED"
                elif ev == "RESUME":
                    if status == "PAUSED":
                        status = "RUNNING"
                elif ev == "CLOSE":
                    if status in ("RUNNING", "PAUSED"):
                        status = "CLOSED"
                elif ev == "REOPEN":
                    if status == "CLOSED":
                        status = "RUNNING"

            # Check breach at next_time after all events at next_time are applied
            if status != "NOT_OPENED" and not breached:
                if used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = next_time

        if had_valid_open:
            results.append(
                {
                    "ticket_id": ticket_id,
                    "priority": priority,
                    "used_minutes": used_minutes,
                    "breached": breached,
                    "breached_at": breached_at,
                    "status": status.lower(),
                }
            )

    return results