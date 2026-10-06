from bisect import bisect_left, bisect_right


def compute_sla(stream):
    VALID_EVENTS = {'OPEN', 'PRIORITY', 'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'}
    VALID_PRIORITIES = {'P1', 'P2', 'P3', 'P4'}
    LIMITS = {'P1': 240, 'P2': 480, 'P3': 1440, 'P4': 2400}
    STATUS_MAP = {'RUNNING': 'running', 'PAUSED': 'paused', 'CLOSED': 'closed'}

    raw_holidays = set()
    ticket_events = {}  # tid -> list of (m, stream_idx, ev, prio)
    max_ticket_m = None
    stream_idx = 0

    for line in stream:
        stream_idx += 1
        line = line.strip()
        if not line:
            continue
        parts = line.split(',')
        if len(parts) not in (3, 4):
            continue
        fields = [p.strip() for p in parts]
        m_str, tid, ev = fields[0], fields[1], fields[2]

        if not (m_str.isascii() and m_str.isdigit()):
            continue
        if not tid:
            continue
        if ev not in VALID_EVENTS:
            continue

        if ev in ('OPEN', 'PRIORITY'):
            if len(fields) != 4 or fields[3] not in VALID_PRIORITIES:
                continue
            prio = fields[3]
        else:
            if len(fields) != 3:
                continue
            prio = None

        if ev == 'HOLIDAY':
            if tid != '*':
                continue
            m = int(m_str)
            raw_holidays.add(m // 1440)
        else:
            if tid == '*':
                continue
            m = int(m_str)
            if max_ticket_m is None or m > max_ticket_m:
                max_ticket_m = m
            if tid not in ticket_events:
                ticket_events[tid] = []
            ticket_events[tid].append((m, stream_idx, ev, prio))

    if max_ticket_m is None:
        return []

    now = max_ticket_m

    # Only weekday holidays affect business minutes
    H = sorted(d for d in raw_holidays if d % 7 < 5)

    def raw_biz_minutes(t):
        w = t // 10080
        rem_t = t % 10080
        d_rem = rem_t // 1440
        m_of_day = rem_t % 1440
        ans = w * 2400 + min(d_rem, 5) * 480
        if d_rem < 5:
            ans += max(0, min(m_of_day, 1020) - 540)
        return ans

    def biz_minutes(t):
        raw = raw_biz_minutes(t)
        d = t // 1440
        idx = bisect_left(H, d)
        deduction = idx * 480
        if idx < len(H) and H[idx] == d:
            m_of_day = t % 1440
            deduction += max(0, min(m_of_day, 1020) - 540)
        return raw - deduction

    def actual_biz_days_up_to(d):
        if d < 0:
            return 0
        full_weeks = (d + 1) // 7
        rem_days = (d + 1) % 7
        raw_days = full_weeks * 5 + min(rem_days, 5)
        h_count = bisect_right(H, d)
        return raw_days - h_count

    def find_breach_minute(m_start, need, m_end):
        target = biz_minutes(m_start) + need
        full_days = (target - 1) // 480
        rem_minutes = target - full_days * 480
        K = full_days + 1
        low = m_start // 1440
        high = m_end // 1440
        while low < high:
            mid = (low + high) // 2
            if actual_biz_days_up_to(mid) >= K:
                high = mid
            else:
                low = mid + 1
        D = low
        return D * 1440 + 540 + rem_minutes

    results = []

    for tid, evs in ticket_events.items():
        evs.sort(key=lambda x: (x[0], x[1]))

        # Group events by minute
        grouped = []
        for m, _, ev, prio in evs:
            if grouped and grouped[-1][0] == m:
                grouped[-1][1].append((ev, prio))
            else:
                grouped.append((m, [(ev, prio)]))

        if grouped[-1][0] < now:
            grouped.append((now, []))

        state = 'NOT_OPENED'
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        has_valid_open = False
        prev_m = None

        for m, ev_list in grouped:
            if prev_m is not None:
                if state == 'RUNNING':
                    delta_biz = biz_minutes(m) - biz_minutes(prev_m)
                    if not breached:
                        need = LIMITS[priority] + 1 - used_minutes
                        if delta_biz >= need:
                            t_b = find_breach_minute(prev_m, need, m)
                            if t_b < m:
                                breached = True
                                breached_at = t_b
                    used_minutes += delta_biz

            for ev, prio in ev_list:
                if ev == 'OPEN':
                    if state == 'NOT_OPENED' or state == 'CLOSED':
                        state = 'RUNNING'
                        priority = prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        has_valid_open = True
                elif ev == 'PRIORITY':
                    if state in ('RUNNING', 'PAUSED'):
                        priority = prio
                elif ev == 'PAUSE':
                    if state == 'RUNNING':
                        state = 'PAUSED'
                elif ev == 'RESUME':
                    if state == 'PAUSED':
                        state = 'RUNNING'
                elif ev == 'CLOSE':
                    if state in ('RUNNING', 'PAUSED'):
                        state = 'CLOSED'
                elif ev == 'REOPEN':
                    if state == 'CLOSED':
                        state = 'RUNNING'

            if has_valid_open and not breached:
                if used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = m

            prev_m = m

        if has_valid_open:
            results.append({
                "ticket_id": tid,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": STATUS_MAP[state],
            })

    results.sort(key=lambda d: d["ticket_id"])
    return results