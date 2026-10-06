from bisect import bisect_left
from itertools import groupby


def compute_sla(stream):
    """
    Computes SLA metrics for tickets from a CSV stream of events.
    Uses a per-ticket state machine with closed-form business-minute arithmetic.
    """
    valid_events = {'OPEN', 'PRIORITY', 'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'}
    valid_priorities = {'P1', 'P2', 'P3', 'P4'}
    limits = {'P1': 240, 'P2': 480, 'P3': 1440, 'P4': 2400}

    holidays = set()
    ticket_events_by_id = {}
    now = -1

    for raw_line in stream:
        line = raw_line.strip()
        if not line:
            continue
        fields = [f.strip() for f in line.split(',')]
        if len(fields) not in (3, 4):
            continue

        minute_str, ticket_id, event = fields[0], fields[1], fields[2]
        if not minute_str or not minute_str.isascii() or not minute_str.isdigit():
            continue
        if not ticket_id:
            continue
        if event not in valid_events:
            continue

        minute = int(minute_str)

        if event in ('OPEN', 'PRIORITY'):
            if len(fields) != 4:
                continue
            priority_arg = fields[3]
            if priority_arg not in valid_priorities:
                continue
            if ticket_id == '*':
                continue
            if minute > now:
                now = minute
            if ticket_id not in ticket_events_by_id:
                ticket_events_by_id[ticket_id] = []
            ticket_events_by_id[ticket_id].append((minute, event, priority_arg))
        else:
            if len(fields) != 3:
                continue
            if event == 'HOLIDAY':
                if ticket_id != '*':
                    continue
                holidays.add(minute // 1440)
            else:
                if ticket_id == '*':
                    continue
                if minute > now:
                    now = minute
                if ticket_id not in ticket_events_by_id:
                    ticket_events_by_id[ticket_id] = []
                ticket_events_by_id[ticket_id].append((minute, event, None))

    if now < 0:
        return []

    # Prepare holiday structures for closed-form calendar calculations
    weekday_holidays = sorted(h for h in holidays if h % 7 < 5)
    num_holidays = len(weekday_holidays)

    def count_biz_days_before(d):
        w = d % 7
        raw = (d // 7) * 5 + min(w, 5)
        k = bisect_left(weekday_holidays, d)
        return raw - k

    def biz_minutes_from_zero(t):
        d, mod = divmod(t, 1440)
        w = d % 7
        raw_full_weekdays = (d // 7) * 5 + min(w, 5)
        k = bisect_left(weekday_holidays, d)
        full_biz_days = raw_full_weekdays - k
        total = full_biz_days * 480
        if w < 5 and d not in holidays:
            total += max(0, min(mod, 1020) - 540)
        return total

    def find_business_day(target_k):
        low = 0
        high = (target_k // 5 + num_holidays + 2) * 7
        while low < high:
            mid = (low + high) // 2
            if count_biz_days_before(mid + 1) > target_k:
                high = mid
            else:
                low = mid + 1
        return low

    def minute_of_target_biz(target):
        biz_days = target // 480
        rem = target % 480
        if rem > 0:
            d = find_business_day(biz_days)
            return d * 1440 + 540 + rem
        else:
            d = find_business_day(biz_days - 1)
            return d * 1440 + 1020

    # Ticket states
    NOT_OPENED = 0
    RUNNING = 1
    PAUSED = 2
    CLOSED = 3
    status_map = {RUNNING: "running", PAUSED: "paused", CLOSED: "closed"}

    results = []

    for ticket_id, raw_events in ticket_events_by_id.items():
        # Stable sort by minute
        raw_events.sort(key=lambda x: x[0])

        state = NOT_OPENED
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        has_valid_open = False
        prev_minute = None

        for minute, group in groupby(raw_events, key=lambda x: x[0]):
            events_at_minute = list(group)

            # Advance time from prev_minute to minute
            if prev_minute is not None and minute > prev_minute:
                if state == RUNNING:
                    start_biz = biz_minutes_from_zero(prev_minute)
                    end_biz = biz_minutes_from_zero(minute)
                    delta = end_biz - start_biz
                    if not breached:
                        rem_to_breach = limits[priority] - used_minutes + 1
                        if delta >= rem_to_breach:
                            t_b = minute_of_target_biz(start_biz + rem_to_breach)
                            if t_b < minute:
                                breached = True
                                breached_at = t_b
                    used_minutes += delta

            # Apply all events at minute
            for _, event, prio_arg in events_at_minute:
                if event == 'OPEN':
                    if state == NOT_OPENED or state == CLOSED:
                        state = RUNNING
                        priority = prio_arg
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        has_valid_open = True
                elif event == 'PRIORITY':
                    if state == RUNNING or state == PAUSED:
                        priority = prio_arg
                elif event == 'PAUSE':
                    if state == RUNNING:
                        state = PAUSED
                elif event == 'RESUME':
                    if state == PAUSED:
                        state = RUNNING
                elif event == 'CLOSE':
                    if state == RUNNING or state == PAUSED:
                        state = CLOSED
                elif event == 'REOPEN':
                    if state == CLOSED:
                        state = RUNNING

            # Check breach at minute after all events at minute are applied
            if not breached and state != NOT_OPENED:
                if used_minutes > limits[priority]:
                    breached = True
                    breached_at = minute

            prev_minute = minute

        # Advance from last event minute to "now"
        if prev_minute is not None and prev_minute < now:
            if state == RUNNING:
                start_biz = biz_minutes_from_zero(prev_minute)
                end_biz = biz_minutes_from_zero(now)
                delta = end_biz - start_biz
                if not breached:
                    rem_to_breach = limits[priority] - used_minutes + 1
                    if delta >= rem_to_breach:
                        t_b = minute_of_target_biz(start_biz + rem_to_breach)
                        breached = True
                        breached_at = t_b
                used_minutes += delta

        if has_valid_open:
            results.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": status_map[state]
            })

    results.sort(key=lambda x: x["ticket_id"])
    return results