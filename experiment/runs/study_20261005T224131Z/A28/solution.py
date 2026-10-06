from bisect import bisect_right
from collections import defaultdict

LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}

STATUS_MAP = {
    'RUNNING': 'running',
    'PAUSED': 'paused',
    'CLOSED': 'closed',
}


def compute_sla(stream):
    holiday_days = set()
    ticket_events = defaultdict(list)
    max_ticket_minute = -1

    # 1. Parse and validate stream
    for raw_line in stream:
        line = raw_line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) not in (3, 4):
            continue

        m_str, tid, ev = parts[0], parts[1], parts[2]
        if not m_str or not m_str.isascii() or not m_str.isdigit():
            continue
        minute = int(m_str)

        if not tid:
            continue

        if ev == 'HOLIDAY':
            if len(parts) != 3 or tid != '*':
                continue
            holiday_days.add(minute // 1440)
        elif ev in ('OPEN', 'PRIORITY'):
            if len(parts) != 4 or tid == '*':
                continue
            prio = parts[3]
            if prio not in LIMITS:
                continue
            ticket_events[tid].append((minute, ev, prio))
            if minute > max_ticket_minute:
                max_ticket_minute = minute
        elif ev in ('PAUSE', 'RESUME', 'CLOSE', 'REOPEN'):
            if len(parts) != 3 or tid == '*':
                continue
            ticket_events[tid].append((minute, ev, None))
            if minute > max_ticket_minute:
                max_ticket_minute = minute
        else:
            continue

    if max_ticket_minute == -1:
        return []

    now = max_ticket_minute

    # 2. Calendar preparation
    weekday_holidays = sorted(d for d in holiday_days if d % 7 < 5)
    num_weekday_holidays = len(weekday_holidays)

    def count_bd_up_to(d):
        if d < 0:
            return 0
        w, r = divmod(d + 1, 7)
        weekdays = w * 5 + (r if r < 5 else 5)
        return weekdays - bisect_right(weekday_holidays, d)

    def count_business_minutes_up_to(t):
        if t <= 0:
            return 0
        d, mod = divmod(t, 1440)
        full_day_bms = count_bd_up_to(d - 1) * 480
        if (d % 7 < 5) and (d not in holiday_days):
            if mod > 540:
                return full_day_bms + (mod - 540 if mod < 1020 else 480)
        return full_day_bms

    def find_kth_business_minute(t1, k):
        d1, mod1 = divmod(t1, 1440)
        is_biz = (d1 % 7 < 5) and (d1 not in holiday_days)
        rem1 = 0
        if is_biz:
            if mod1 < 540:
                rem1 = 480
            elif mod1 < 1020:
                rem1 = 1020 - mod1

        if rem1 > 0 and k <= rem1:
            first_bm = 540 if mod1 < 540 else mod1
            return d1 * 1440 + first_bm + k - 1

        k_prime = k - rem1
        full_days = (k_prime - 1) // 480
        rem = (k_prime - 1) % 480 + 1
        N = full_days + 1

        target = count_bd_up_to(d1) + N
        low = d1 + 1
        high = d1 + (N + num_weekday_holidays + 2) * 2
        while low < high:
            mid = (low + high) // 2
            if count_bd_up_to(mid) >= target:
                high = mid
            else:
                low = mid + 1
        return low * 1440 + 540 + rem - 1

    # 3. Simulate tickets
    results = []
    for tid, raw_events in ticket_events.items():
        raw_events.sort(key=lambda x: x[0])

        grouped = []
        for m, ev, arg in raw_events:
            if grouped and grouped[-1][0] == m:
                grouped[-1][1].append((ev, arg))
            else:
                grouped.append((m, [(ev, arg)]))

        if grouped[-1][0] < now:
            grouped.append((now, []))

        state = 'NOT_OPENED'
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        prev_m = None

        for m, ev_list in grouped:
            if prev_m is not None:
                if state == 'RUNNING':
                    delta_bus = (
                        count_business_minutes_up_to(m)
                        - count_business_minutes_up_to(prev_m)
                    )
                    if not breached:
                        limit = LIMITS[priority]
                        k = limit + 1 - used_minutes
                        if delta_bus >= k:
                            x_star = find_kth_business_minute(prev_m, k)
                            t_star = x_star + 1
                            if t_star < m:
                                breached = True
                                breached_at = t_star
                    used_minutes += delta_bus

            prev_m = m

            for ev, arg in ev_list:
                if ev == 'OPEN':
                    if state in ('NOT_OPENED', 'CLOSED'):
                        state = 'RUNNING'
                        priority = arg
                        used_minutes = 0
                        breached = False
                        breached_at = None
                elif ev == 'PRIORITY':
                    if state in ('RUNNING', 'PAUSED'):
                        priority = arg
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

            if state != 'NOT_OPENED':
                if not breached:
                    if used_minutes > LIMITS[priority]:
                        breached = True
                        breached_at = m

        if state != 'NOT_OPENED':
            results.append({
                "ticket_id": tid,
                "priority": priority,
                "used_minutes": used_minutes,
                "breached": breached,
                "breached_at": breached_at,
                "status": STATUS_MAP[state],
            })

    results.sort(key=lambda d: d['ticket_id'])
    return results