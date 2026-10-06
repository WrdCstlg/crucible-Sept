from bisect import bisect_left
from collections import defaultdict
from itertools import groupby

LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}

VALID_EVENTS = {'OPEN', 'PRIORITY', 'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'}


def compute_sla(stream):
    holiday_days = set()
    ticket_events = defaultdict(list)
    now = -1

    for raw_line in stream:
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(',')
        if len(parts) not in (3, 4):
            continue

        f0 = parts[0].strip()
        f1 = parts[1].strip()
        f2 = parts[2].strip()

        if not (f0.isascii() and f0.isdigit()):
            continue
        minute = int(f0)

        if not f1:
            continue

        if f2 not in VALID_EVENTS:
            continue

        if f2 in ('OPEN', 'PRIORITY'):
            if len(parts) != 4:
                continue
            f3 = parts[3].strip()
            if f3 not in ('P1', 'P2', 'P3', 'P4'):
                continue
            extra = f3
        else:
            if len(parts) != 3:
                continue
            extra = None

        if f2 == 'HOLIDAY':
            if f1 != '*':
                continue
            holiday_days.add(minute // 1440)
        else:
            if f1 == '*':
                continue
            ticket_events[f1].append((minute, f2, extra))
            if minute > now:
                now = minute

    if now < 0:
        return []

    holidays_list = sorted(d for d in holiday_days if d % 7 < 5)
    num_holidays = len(holidays_list)

    def biz_minutes_up_to(t):
        D = t // 1440
        m = t % 1440
        r = D % 7
        w = D // 7
        raw_weekdays = w * 5 + (r if r < 5 else 5)
        h_idx = bisect_left(holidays_list, D)
        biz_days = raw_weekdays - h_idx

        if r < 5 and (h_idx == num_holidays or holidays_list[h_idx] != D):
            if m > 540:
                return biz_days * 480 + (480 if m >= 1020 else (m - 540))
        return biz_days * 480

    def invert_biz_minutes(K):
        day_index = (K - 1) // 480
        rem_minutes = (K - 1) % 480 + 1

        target = day_index + 1
        low = (day_index // 5) * 7
        high = ((day_index + num_holidays) // 5) * 7 + 6

        while low < high:
            mid = (low + high) // 2
            D1 = mid + 1
            w = D1 // 7
            r = D1 % 7
            raw = w * 5 + (r if r < 5 else 5)
            h = bisect_left(holidays_list, D1)
            if raw - h >= target:
                high = mid
            else:
                low = mid + 1

        return low * 1440 + 540 + rem_minutes

    results = []

    for ticket_id, events in ticket_events.items():
        events.sort(key=lambda x: x[0])

        status = 'not_opened'
        priority = None
        used = 0
        breached = False
        breached_at = None
        has_opened = False
        m_prev = None

        for m, minute_events in groupby(events, key=lambda x: x[0]):
            if m_prev is not None and m > m_prev:
                if status == 'running':
                    L = LIMITS[priority]
                    if not breached:
                        K_breach = biz_minutes_up_to(m_prev) + (L - used + 1)
                        t_breach = invert_biz_minutes(K_breach)
                        if t_breach < m:
                            breached = True
                            breached_at = t_breach
                    used += biz_minutes_up_to(m) - biz_minutes_up_to(m_prev)
                m_prev = m

            for _, event, extra in minute_events:
                if event == 'OPEN':
                    if status in ('not_opened', 'closed'):
                        status = 'running'
                        priority = extra
                        used = 0
                        breached = False
                        breached_at = None
                        has_opened = True
                        if m_prev is None:
                            m_prev = m
                elif event == 'PRIORITY':
                    if status in ('running', 'paused'):
                        priority = extra
                elif event == 'PAUSE':
                    if status == 'running':
                        status = 'paused'
                elif event == 'RESUME':
                    if status == 'paused':
                        status = 'running'
                elif event == 'CLOSE':
                    if status in ('running', 'paused'):
                        status = 'closed'
                elif event == 'REOPEN':
                    if status == 'closed':
                        status = 'running'

            if status != 'not_opened' and not breached:
                L = LIMITS[priority]
                if used > L:
                    breached = True
                    breached_at = m

        if not has_opened:
            continue

        if m_prev < now:
            if status == 'running':
                L = LIMITS[priority]
                if not breached:
                    K_breach = biz_minutes_up_to(m_prev) + (L - used + 1)
                    t_breach = invert_biz_minutes(K_breach)
                    if t_breach <= now:
                        breached = True
                        breached_at = t_breach
                used += biz_minutes_up_to(now) - biz_minutes_up_to(m_prev)
            m_prev = now

        results.append({
            'ticket_id': ticket_id,
            'priority': priority,
            'used_minutes': used,
            'breached': breached,
            'breached_at': breached_at,
            'status': status,
        })

    results.sort(key=lambda d: d['ticket_id'])
    return results