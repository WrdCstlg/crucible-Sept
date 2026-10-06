import bisect
from collections import defaultdict
import itertools


def compute_sla(stream):
    limits = {'P1': 240, 'P2': 480, 'P3': 1440, 'P4': 2400}
    status_map = {'RUNNING': 'running', 'PAUSED': 'paused', 'CLOSED': 'closed'}

    holiday_days = set()
    ticket_events = defaultdict(list)
    max_ticket_minute = None

    for line in stream:
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split(',')]
        if len(parts) not in (3, 4):
            continue
        m_str = parts[0]
        if not (m_str.isascii() and m_str.isdigit()):
            continue
        m = int(m_str)
        tid = parts[1]
        if not tid:
            continue
        ev = parts[2]
        if ev not in ('OPEN', 'PRIORITY', 'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'):
            continue

        if ev == 'HOLIDAY':
            if tid != '*' or len(parts) != 3:
                continue
            holiday_days.add(m // 1440)
        else:
            if tid == '*':
                continue
            if ev in ('OPEN', 'PRIORITY'):
                if len(parts) != 4:
                    continue
                p = parts[3]
                if p not in ('P1', 'P2', 'P3', 'P4'):
                    continue
                ticket_events[tid].append((m, ev, p))
            else:
                if len(parts) != 3:
                    continue
                ticket_events[tid].append((m, ev, None))

            if max_ticket_minute is None or m > max_ticket_minute:
                max_ticket_minute = m

    if max_ticket_minute is None:
        return []

    now = max_ticket_minute

    effective_holidays = sorted(d for d in holiday_days if d % 7 < 5)
    effective_holiday_set = set(effective_holidays)
    bisect_left = bisect.bisect_left

    def count_business_minutes(t):
        if t <= 0:
            return 0
        d, m = divmod(t, 1440)
        w_week, r_day = divmod(d, 7)
        reg = w_week * 2400 + (r_day if r_day < 5 else 5) * 480
        if r_day < 5:
            if m > 540:
                reg += (m - 540) if m < 1020 else 480

        k = bisect_left(effective_holidays, d)
        ded = k * 480
        if d in effective_holiday_set:
            if m > 540:
                ded += (m - 540) if m < 1020 else 480

        return reg - ded

    results = []

    for tid in sorted(ticket_events.keys()):
        events = ticket_events[tid]
        events.sort(key=lambda x: x[0])

        state = 'NOT_OPENED'
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        last_minute = None
        ever_valid_opened = False

        for m, group in itertools.groupby(events, key=lambda x: x[0]):
            ev_group = [(ev, p) for _, ev, p in group]

            if state == 'RUNNING':
                if not breached and m - 1 > last_minute:
                    u_prev = used_minutes + count_business_minutes(m - 1) - count_business_minutes(last_minute)
                    limit = limits[priority]
                    if u_prev > limit:
                        target_y = count_business_minutes(last_minute) + limit + 1 - used_minutes
                        low = last_minute + 1
                        high = m - 1
                        ans = high
                        while low <= high:
                            mid = (low + high) // 2
                            if count_business_minutes(mid) >= target_y:
                                ans = mid
                                high = mid - 1
                            else:
                                low = mid + 1
                        breached = True
                        breached_at = ans

                used_minutes += count_business_minutes(m) - count_business_minutes(last_minute)

            last_minute = m

            for ev, p in ev_group:
                if ev == 'OPEN':
                    if state in ('NOT_OPENED', 'CLOSED'):
                        state = 'RUNNING'
                        priority = p
                        used_minutes = 0
                        breached = False
                        breached_at = None
                        ever_valid_opened = True
                elif ev == 'PRIORITY':
                    if state in ('RUNNING', 'PAUSED'):
                        priority = p
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

            if ever_valid_opened and not breached:
                if used_minutes > limits[priority]:
                    breached = True
                    breached_at = m

        if not ever_valid_opened:
            continue

        if last_minute < now:
            if state == 'RUNNING':
                if not breached and now - 1 > last_minute:
                    u_prev = used_minutes + count_business_minutes(now - 1) - count_business_minutes(last_minute)
                    limit = limits[priority]
                    if u_prev > limit:
                        target_y = count_business_minutes(last_minute) + limit + 1 - used_minutes
                        low = last_minute + 1
                        high = now - 1
                        ans = high
                        while low <= high:
                            mid = (low + high) // 2
                            if count_business_minutes(mid) >= target_y:
                                ans = mid
                                high = mid - 1
                            else:
                                low = mid + 1
                        breached = True
                        breached_at = ans

                used_minutes += count_business_minutes(now) - count_business_minutes(last_minute)
                last_minute = now

                if not breached and used_minutes > limits[priority]:
                    breached = True
                    breached_at = now

        results.append({
            "ticket_id": tid,
            "priority": priority,
            "used_minutes": used_minutes,
            "breached": breached,
            "breached_at": breached_at,
            "status": status_map[state]
        })

    return results