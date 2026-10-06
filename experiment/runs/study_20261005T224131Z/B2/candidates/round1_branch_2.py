from bisect import bisect_left


def compute_sla(stream):
    raw_holidays = set()
    ticket_events = []

    for stream_idx, line in enumerate(stream):
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split(",")
        n_parts = len(parts)
        if n_parts not in (3, 4):
            continue

        f0 = parts[0].strip()
        f1 = parts[1].strip()
        f2 = parts[2].strip()
        f3 = parts[3].strip() if n_parts == 4 else None

        if not (f0.isascii() and f0.isdigit()):
            continue
        m = int(f0)

        if not f1:
            continue
        ticket_id = f1
        event = f2

        if event == "HOLIDAY":
            if n_parts != 3 or ticket_id != "*":
                continue
            raw_holidays.add(m // 1440)
        else:
            if ticket_id == "*":
                continue
            if event in ("OPEN", "PRIORITY"):
                if n_parts != 4 or f3 not in ("P1", "P2", "P3", "P4"):
                    continue
                param = f3
            elif event in ("PAUSE", "RESUME", "CLOSE", "REOPEN"):
                if n_parts != 3:
                    continue
                param = None
            else:
                continue

            ticket_events.append((m, stream_idx, ticket_id, event, param))

    if not ticket_events:
        return []

    ticket_events.sort(key=lambda x: (x[0], x[1]))
    now = ticket_events[-1][0]

    weekday_holiday_set = {d for d in raw_holidays if d % 7 < 5}
    sorted_holidays = sorted(weekday_holiday_set)

    def total_business_minutes(minute):
        if minute <= 0:
            return 0
        d = minute // 1440
        rem = minute % 1440
        weekdays = (d // 7) * 5 + min(d % 7, 5)
        hols = bisect_left(sorted_holidays, d)
        biz_days = weekdays - hols
        ans = biz_days * 480
        if (d % 7 < 5) and (d not in weekday_holiday_set):
            ans += max(0, min(rem, 1020) - 540)
        return ans

    def count_business_minutes(m1, m2):
        if m2 <= m1:
            return 0
        return total_business_minutes(m2) - total_business_minutes(m1)

    def get_business_day(target_biz_days):
        low = (target_biz_days // 5) * 7
        w = target_biz_days + 1 + len(sorted_holidays)
        high = (w // 5) * 7 + 14
        while low < high:
            mid = (low + high) // 2
            d_next = mid + 1
            weekdays = (d_next // 7) * 5 + min(d_next % 7, 5)
            hols = bisect_left(sorted_holidays, d_next)
            if weekdays - hols > target_biz_days:
                high = mid
            else:
                low = mid + 1
        return low

    def find_minute_of_target_business_minutes(target):
        full_days = (target - 1) // 480
        rem_mins = target - full_days * 480
        d = get_business_day(full_days)
        return d * 1440 + 540 + rem_mins

    events_by_ticket = {}
    for m, s_idx, t_id, ev, param in ticket_events:
        if t_id not in events_by_ticket:
            events_by_ticket[t_id] = []
        events_by_ticket[t_id].append((m, ev, param))

    limits = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
    results = []

    for t_id, ev_seq in events_by_ticket.items():
        grouped_events = []
        for m, ev, param in ev_seq:
            if not grouped_events or grouped_events[-1][0] != m:
                grouped_events.append((m, []))
            grouped_events[-1][1].append((ev, param))

        had_valid_open = False
        state = "NOT_OPENED"
        priority = None
        cur_start = None
        intervals = []

        for m, ev_list in grouped_events:
            old_state = state
            old_priority = priority
            valid_open_occurred = False

            for ev, param in ev_list:
                if ev == "OPEN":
                    if state == "NOT_OPENED":
                        state = "RUNNING"
                        priority = param
                        had_valid_open = True
                        valid_open_occurred = True
                    elif state == "CLOSED":
                        state = "RUNNING"
                        priority = param
                        valid_open_occurred = True
                elif ev == "PRIORITY":
                    if state in ("RUNNING", "PAUSED"):
                        priority = param
                elif ev == "PAUSE":
                    if state == "RUNNING":
                        state = "PAUSED"
                elif ev == "RESUME":
                    if state == "PAUSED":
                        state = "RUNNING"
                elif ev == "CLOSE":
                    if state in ("RUNNING", "PAUSED"):
                        state = "CLOSED"
                elif ev == "REOPEN":
                    if state == "CLOSED":
                        state = "RUNNING"

            if valid_open_occurred:
                intervals.clear()
                cur_start = m
            else:
                if had_valid_open and cur_start is not None and m > cur_start:
                    intervals.append((cur_start, m, old_state == "RUNNING", old_priority))
                    cur_start = m

        if not had_valid_open:
            continue

        if cur_start is not None and now > cur_start:
            intervals.append((cur_start, now, state == "RUNNING", priority))

        if not intervals:
            intervals.append((now, now, state == "RUNNING", priority))

        used_minutes = 0
        breached = False
        breached_at = None

        for start, end, is_running, prio in intervals:
            limit = limits[prio]

            if not breached and used_minutes > limit:
                breached = True
                breached_at = start

            if is_running and start < end:
                bm = count_business_minutes(start, end)
                if not breached:
                    needed = limit - used_minutes + 1
                    if needed <= bm:
                        t = find_minute_of_target_business_minutes(
                            total_business_minutes(start) + needed
                        )
                        if t < end:
                            breached = True
                            breached_at = t
                used_minutes += bm

        final_limit = limits[priority]
        if not breached and used_minutes > final_limit:
            breached = True
            breached_at = now

        results.append({
            "ticket_id": t_id,
            "priority": priority,
            "used_minutes": used_minutes,
            "breached": breached,
            "breached_at": breached_at,
            "status": state.lower(),
        })

    results.sort(key=lambda d: d["ticket_id"])
    return results