from bisect import bisect_left

LIMITS = {
    "P1": 240,
    "P2": 480,
    "P3": 1440,
    "P4": 2400,
}


def compute_sla(stream):
    raw_holidays = set()
    ticket_events = {}  # tid -> list of (minute, event, prio)
    has_ticket_events = False
    now = -1

    for line in stream:
        s = line.strip()
        if not s:
            continue
        parts = s.split(",")
        n = len(parts)
        if n not in (3, 4):
            continue
        parts = [p.strip() for p in parts]

        m_str = parts[0]
        if not (m_str and m_str.isascii() and m_str.isdigit()):
            continue
        minute = int(m_str)

        tid = parts[1]
        if not tid:
            continue

        event = parts[2]

        if event == "HOLIDAY":
            if n != 3 or tid != "*":
                continue
            raw_holidays.add(minute // 1440)
            continue

        if tid == "*":
            continue

        if event in ("OPEN", "PRIORITY"):
            if n != 4:
                continue
            prio = parts[3]
            if prio not in ("P1", "P2", "P3", "P4"):
                continue
            has_ticket_events = True
            if minute > now:
                now = minute
            if tid not in ticket_events:
                ticket_events[tid] = []
            ticket_events[tid].append((minute, event, prio))
        elif event in ("PAUSE", "RESUME", "CLOSE", "REOPEN"):
            if n != 3:
                continue
            has_ticket_events = True
            if minute > now:
                now = minute
            if tid not in ticket_events:
                ticket_events[tid] = []
            ticket_events[tid].append((minute, event, None))
        else:
            continue

    if not has_ticket_events:
        return []

    # Calendar model: holidays on weekdays (0..4)
    H = sorted(d for d in raw_holidays if (d % 7) < 5)
    len_H = len(H)

    def business_minutes_at(m):
        d, mod = divmod(m, 1440)
        wks, rem = divmod(d, 7)
        full_bdays = wks * 5 + (rem if rem < 5 else 5)

        idx = bisect_left(H, d)
        is_holiday = idx < len_H and H[idx] == d

        if is_holiday:
            return (full_bdays - idx) * 480
        else:
            if rem >= 5:
                bm_today = 0
            else:
                if mod <= 540:
                    bm_today = 0
                elif mod >= 1020:
                    bm_today = 480
                else:
                    bm_today = mod - 540
            return (full_bdays - idx) * 480 + bm_today

    def find_bday(target_bday):
        if not H:
            wks, rem = divmod(target_bday, 5)
            return wks * 7 + rem

        low = (target_bday // 5) * 7
        high = ((target_bday + len_H) // 5) * 7 + 7
        while low < high:
            mid = (low + high + 1) // 2
            wks, rem = divmod(mid, 7)
            b_before = wks * 5 + (rem if rem < 5 else 5) - bisect_left(H, mid)
            if b_before <= target_bday:
                low = mid
            else:
                high = mid - 1
        return low

    def find_minute(target):
        target_full_bdays, target_rem = divmod(target, 480)
        if target_rem > 0:
            bday_idx = target_full_bdays
            D = find_bday(bday_idx)
            return D * 1440 + 540 + target_rem
        else:
            bday_idx = target_full_bdays - 1
            D = find_bday(bday_idx)
            return D * 1440 + 1020

    results = []

    for tid in sorted(ticket_events.keys()):
        events = ticket_events[tid]
        events.sort(key=lambda x: x[0])

        status = "NOT_OPENED"
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        has_valid_open = False
        current_time = events[0][0]

        # Group events by minute
        i = 0
        n_events = len(events)
        while i < n_events:
            m = events[i][0]
            m_events = []
            while i < n_events and events[i][0] == m:
                m_events.append((events[i][1], events[i][2]))
                i += 1

            if m > current_time:
                if status == "RUNNING":
                    bm = business_minutes_at(m) - business_minutes_at(current_time)
                    if not breached:
                        limit = LIMITS[priority]
                        needed = (limit + 1) - used_minutes
                        if needed <= bm:
                            b_min = find_minute(business_minutes_at(current_time) + needed)
                            if b_min < m:
                                breached = True
                                breached_at = b_min
                    used_minutes += bm
                current_time = m

            for event, prio in m_events:
                if event == "OPEN":
                    if status == "NOT_OPENED":
                        status = "RUNNING"
                        priority = prio
                        used_minutes = 0
                        has_valid_open = True
                    elif status == "CLOSED":
                        status = "RUNNING"
                        priority = prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        has_valid_open = True
                elif event == "PRIORITY":
                    if status in ("RUNNING", "PAUSED"):
                        priority = prio
                elif event == "PAUSE":
                    if status == "RUNNING":
                        status = "PAUSED"
                elif event == "RESUME":
                    if status == "PAUSED":
                        status = "RUNNING"
                elif event == "CLOSE":
                    if status in ("RUNNING", "PAUSED"):
                        status = "CLOSED"
                elif event == "REOPEN":
                    if status == "CLOSED":
                        status = "RUNNING"

            if status != "NOT_OPENED" and not breached:
                if used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = m

        if current_time < now:
            if status == "RUNNING":
                bm = business_minutes_at(now) - business_minutes_at(current_time)
                if not breached:
                    limit = LIMITS[priority]
                    needed = (limit + 1) - used_minutes
                    if needed <= bm:
                        b_min = find_minute(business_minutes_at(current_time) + needed)
                        if b_min <= now:
                            breached = True
                            breached_at = b_min
                used_minutes += bm
            current_time = now

        if has_valid_open:
            results.append({
                "ticket_id": tid,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": status.lower(),
            })

    results.sort(key=lambda x: x["ticket_id"])
    return results