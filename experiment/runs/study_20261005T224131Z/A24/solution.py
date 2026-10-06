from bisect import bisect_left

LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}

STATE_NOT_OPENED = 0
STATE_RUNNING = 1
STATE_PAUSED = 2
STATE_CLOSED = 3

STATUS_STR = {
    STATE_RUNNING: "running",
    STATE_PAUSED: "paused",
    STATE_CLOSED: "closed",
}


def compute_sla(stream):
    holiday_days = set()
    events_by_ticket = {}
    now = None
    order_idx = 0

    valid_events = {'OPEN', 'PRIORITY', 'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'}
    valid_priorities = {'P1', 'P2', 'P3', 'P4'}

    for line in stream:
        line = line.strip()
        if not line:
            continue

        fields = [f.strip() for f in line.split(',')]
        n_fields = len(fields)
        if n_fields not in (3, 4):
            continue

        f0, f1, ev = fields[0], fields[1], fields[2]

        if not f0 or not all('0' <= c <= '9' for c in f0):
            continue
        if not f1:
            continue
        if ev not in valid_events:
            continue

        m = int(f0)

        if ev == 'HOLIDAY':
            if n_fields != 3 or f1 != '*':
                continue
            day = m // 1440
            if day % 7 < 5:
                holiday_days.add(day)
        else:
            if f1 == '*':
                continue
            if ev in ('OPEN', 'PRIORITY'):
                if n_fields != 4:
                    continue
                p = fields[3]
                if p not in valid_priorities:
                    continue
            else:
                if n_fields != 3:
                    continue
                p = None

            if now is None or m > now:
                now = m

            if f1 not in events_by_ticket:
                events_by_ticket[f1] = []
            events_by_ticket[f1].append((m, order_idx, ev, p))
            order_idx += 1

    if now is None:
        return []

    holidays = sorted(holiday_days)

    def biz_minutes_before_day(d):
        weeks, dow = divmod(d, 7)
        idx = bisect_left(holidays, d)
        return weeks * 2400 + (5 if dow > 5 else dow) * 480 - idx * 480

    def biz_minutes_before(minute):
        d, minute_of_day = divmod(minute, 1440)
        weeks, dow = divmod(d, 7)
        if dow < 5:
            biz_today = max(0, min(minute_of_day, 1020) - 540)
            raw = weeks * 2400 + dow * 480 + biz_today
        else:
            biz_today = 0
            raw = weeks * 2400 + 2400

        idx = bisect_left(holidays, d)
        holiday_sub = idx * 480
        if dow < 5 and idx < len(holidays) and holidays[idx] == d:
            holiday_sub += biz_today

        return raw - holiday_sub

    def find_breach_minute(target, start_day, end_day):
        low = start_day
        high = end_day
        while low < high:
            mid = (low + high) // 2
            if biz_minutes_before_day(mid) >= target:
                high = mid
            else:
                low = mid + 1
        d = low - 1
        rem = target - biz_minutes_before_day(d)
        return d * 1440 + 540 + rem

    results = []

    for ticket_id, events in events_by_ticket.items():
        events.sort(key=lambda x: (x[0], x[1]))

        state = STATE_NOT_OPENED
        priority = None
        used = 0
        breached = False
        breached_at = None
        has_valid_open = False
        last_m = 0

        i = 0
        n = len(events)
        while i < n:
            m = events[i][0]

            if m > last_m:
                if state == STATE_RUNNING:
                    biz = biz_minutes_before(m) - biz_minutes_before(last_m)
                    if not breached:
                        limit = LIMITS[priority]
                        needed = limit + 1 - used
                        if biz >= needed:
                            target = biz_minutes_before(last_m) + needed
                            t = find_breach_minute(target, last_m // 1440, m // 1440 + 1)
                            if t < m:
                                breached = True
                                breached_at = t
                    used += biz
                last_m = m

            while i < n and events[i][0] == m:
                _, _, ev, p_arg = events[i]
                i += 1

                if ev == 'OPEN':
                    if state == STATE_NOT_OPENED or state == STATE_CLOSED:
                        state = STATE_RUNNING
                        priority = p_arg
                        used = 0
                        breached = False
                        breached_at = None
                        has_valid_open = True
                elif ev == 'PRIORITY':
                    if state == STATE_RUNNING or state == STATE_PAUSED:
                        priority = p_arg
                elif ev == 'PAUSE':
                    if state == STATE_RUNNING:
                        state = STATE_PAUSED
                elif ev == 'RESUME':
                    if state == STATE_PAUSED:
                        state = STATE_RUNNING
                elif ev == 'CLOSE':
                    if state == STATE_RUNNING or state == STATE_PAUSED:
                        state = STATE_CLOSED
                elif ev == 'REOPEN':
                    if state == STATE_CLOSED:
                        state = STATE_RUNNING

            if has_valid_open and not breached and priority is not None:
                if used > LIMITS[priority]:
                    breached = True
                    breached_at = m

        if now > last_m:
            if state == STATE_RUNNING:
                biz = biz_minutes_before(now) - biz_minutes_before(last_m)
                if not breached:
                    limit = LIMITS[priority]
                    needed = limit + 1 - used
                    if biz >= needed:
                        target = biz_minutes_before(last_m) + needed
                        t = find_breach_minute(target, last_m // 1440, now // 1440 + 1)
                        breached = True
                        breached_at = t
                used += biz
            last_m = now

        if has_valid_open:
            results.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used,
                "breached": breached,
                "breached_at": breached_at,
                "status": STATUS_STR[state],
            })

    results.sort(key=lambda x: x["ticket_id"])
    return results