from bisect import bisect_left


def compute_sla(stream):
    holiday_days = set()
    ticket_events = []

    valid_events = {'OPEN', 'PRIORITY', 'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'}
    priorities = {'P1', 'P2', 'P3', 'P4'}
    limits = {'P1': 240, 'P2': 480, 'P3': 1440, 'P4': 2400}

    for idx, line in enumerate(stream):
        line = line.strip()
        if not line:
            continue
        raw_fields = line.split(',')
        n = len(raw_fields)
        if n not in (3, 4):
            continue
        fields = [f.strip() for f in raw_fields]
        f0 = fields[0]
        if not f0 or not all('0' <= c <= '9' for c in f0):
            continue
        minute = int(f0)
        ticket_id = fields[1]
        if not ticket_id:
            continue
        event = fields[2]
        if event not in valid_events:
            continue

        if event == 'HOLIDAY':
            if n != 3 or ticket_id != '*':
                continue
            holiday_days.add(minute // 1440)
        else:
            if ticket_id == '*':
                continue
            if event in ('OPEN', 'PRIORITY'):
                if n != 4:
                    continue
                param = fields[3]
                if param not in priorities:
                    continue
            else:
                if n != 3:
                    continue
                param = None
            ticket_events.append((minute, idx, ticket_id, event, param))

    if not ticket_events:
        return []

    now = max(ev[0] for ev in ticket_events)

    effective_holidays = {d for d in holiday_days if d % 7 < 5}
    sorted_holidays = sorted(effective_holidays)

    def b_day(d):
        weeks = d // 7
        rem_days = d % 7
        std_days = weeks * 5 + min(rem_days, 5)
        h_count = bisect_left(sorted_holidays, d)
        return (std_days - h_count) * 480

    def b_min(t):
        d = t // 1440
        rem = t % 1440
        ans = b_day(d)
        if d % 7 < 5 and d not in effective_holidays:
            ans += max(0, min(rem, 1020) - 540)
        return ans

    events_by_ticket = {}
    for ev in ticket_events:
        tid = ev[2]
        if tid not in events_by_ticket:
            events_by_ticket[tid] = []
        events_by_ticket[tid].append(ev)

    result = []

    for tid, events in events_by_ticket.items():
        events.sort(key=lambda x: (x[0], x[1]))

        grouped_events = []
        for ev in events:
            m = ev[0]
            if not grouped_events or grouped_events[-1][0] != m:
                grouped_events.append((m, [ev]))
            else:
                grouped_events[-1][1].append(ev)

        state = 'NOT_OPENED'
        priority = None
        used = 0
        breached = False
        breached_at = None
        valid_open_seen = False

        def advance_time(t_prev, t_cur):
            nonlocal state, priority, used, breached, breached_at
            if state == 'RUNNING':
                delta = b_min(t_cur) - b_min(t_prev)
                if not breached:
                    limit = limits[priority]
                    if used + delta > limit:
                        needed = limit + 1 - used
                        target = b_min(t_prev) + needed
                        low = (t_prev // 1440) + 1
                        high = (t_cur // 1440) + 1
                        while low < high:
                            mid = (low + high) // 2
                            if b_day(mid) >= target:
                                high = mid
                            else:
                                low = mid + 1
                        d = low - 1
                        rem_needed = target - b_day(d)
                        t_breach = d * 1440 + 540 + rem_needed
                        if t_breach < t_cur:
                            breached = True
                            breached_at = t_breach
                used += delta

        last_m = None
        for m, ev_list in grouped_events:
            if last_m is not None:
                advance_time(last_m, m)

            for ev in ev_list:
                ev_type = ev[3]
                param = ev[4]
                if ev_type == 'OPEN':
                    if state in ('NOT_OPENED', 'CLOSED'):
                        state = 'RUNNING'
                        priority = param
                        used = 0
                        breached = False
                        breached_at = None
                        valid_open_seen = True
                elif ev_type == 'PRIORITY':
                    if state in ('RUNNING', 'PAUSED'):
                        priority = param
                elif ev_type == 'PAUSE':
                    if state == 'RUNNING':
                        state = 'PAUSED'
                elif ev_type == 'RESUME':
                    if state == 'PAUSED':
                        state = 'RUNNING'
                elif ev_type == 'CLOSE':
                    if state in ('RUNNING', 'PAUSED'):
                        state = 'CLOSED'
                elif ev_type == 'REOPEN':
                    if state == 'CLOSED':
                        state = 'RUNNING'

            if not breached and valid_open_seen:
                if used > limits[priority]:
                    breached = True
                    breached_at = m

            last_m = m

        if last_m < now:
            advance_time(last_m, now)
            if not breached and valid_open_seen:
                if used > limits[priority]:
                    breached = True
                    breached_at = now

        if valid_open_seen:
            result.append({
                "ticket_id": tid,
                "priority": priority,
                "used_minutes": used,
                "breached": breached,
                "breached_at": breached_at,
                "status": state.lower()
            })

    result.sort(key=lambda x: x["ticket_id"])
    return result