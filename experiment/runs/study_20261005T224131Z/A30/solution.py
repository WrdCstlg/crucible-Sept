from bisect import bisect_left
from collections import defaultdict

PRIORITY_LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}

VALID_EVENTS_4 = {'OPEN', 'PRIORITY'}
VALID_EVENTS_3 = {'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'}
VALID_PRIORITIES = {'P1', 'P2', 'P3', 'P4'}

STATUS_MAP = {
    'RUNNING': 'running',
    'PAUSED': 'paused',
    'CLOSED': 'closed',
}


def compute_sla(stream):
    holiday_days = set()
    ticket_events = defaultdict(list)
    now = -1
    has_ticket_events = False

    for idx, line in enumerate(stream):
        raw = line.strip()
        if not raw:
            continue
        parts = raw.split(',')
        if len(parts) not in (3, 4):
            continue
        parts = [p.strip() for p in parts]

        m_str = parts[0]
        if not m_str or not (m_str.isascii() and m_str.isdigit()):
            continue
        minute = int(m_str)

        tid = parts[1]
        if not tid:
            continue

        event = parts[2]

        if event in VALID_EVENTS_4:
            if len(parts) != 4:
                continue
            prio = parts[3]
            if prio not in VALID_PRIORITIES:
                continue
            if tid == '*':
                continue
            has_ticket_events = True
            if minute > now:
                now = minute
            ticket_events[tid].append((minute, idx, event, prio))

        elif event in VALID_EVENTS_3:
            if len(parts) != 3:
                continue
            if event == 'HOLIDAY':
                if tid != '*':
                    continue
                day = minute // 1440
                if day % 7 < 5:
                    holiday_days.add(day)
            else:
                if tid == '*':
                    continue
                has_ticket_events = True
                if minute > now:
                    now = minute
                ticket_events[tid].append((minute, idx, event, None))
        else:
            continue

    if not has_ticket_events:
        return []

    holidays_list = sorted(holiday_days)
    holiday_set = holiday_days

    def biz_mins_before(m):
        d = m // 1440
        mod = m % 1440
        weeks = d // 7
        dow = d % 7

        mins = weeks * 2400 + min(dow, 5) * 480
        today_nominal = 0
        if dow < 5:
            today_nominal = max(0, min(mod, 1020) - 540)
            mins += today_nominal

        idx = bisect_left(holidays_list, d)
        mins -= idx * 480
        if d in holiday_set:
            mins -= today_nominal

        return mins

    results = []

    for tid in sorted(ticket_events.keys()):
        events = sorted(ticket_events[tid], key=lambda x: (x[0], x[1]))

        grouped = []
        for m, idx, ev, param in events:
            if grouped and grouped[-1][0] == m:
                grouped[-1][1].append((ev, param))
            else:
                grouped.append((m, [(ev, param)]))

        state = 'NOT_OPENED'
        priority = None
        used_time = 0
        breached = False
        breached_at = None
        has_had_valid_open = False
        t_prev = None

        for m, ev_list in grouped:
            if t_prev is not None and m > t_prev:
                if state == 'RUNNING':
                    elapsed_biz = biz_mins_before(m) - biz_mins_before(t_prev)
                    if not breached:
                        limit = PRIORITY_LIMITS[priority]
                        needed = (limit + 1) - used_time
                        if elapsed_biz >= needed:
                            target = biz_mins_before(t_prev) + needed
                            low = t_prev + 1
                            high = m
                            while low < high:
                                mid = (low + high) // 2
                                if biz_mins_before(mid) >= target:
                                    high = mid
                                else:
                                    low = mid + 1
                            if low < m:
                                breached = True
                                breached_at = low
                    used_time += elapsed_biz

            for ev, param in ev_list:
                if ev == 'OPEN':
                    if state in ('NOT_OPENED', 'CLOSED'):
                        state = 'RUNNING'
                        priority = param
                        used_time = 0
                        breached = False
                        breached_at = None
                        has_had_valid_open = True
                elif ev == 'PRIORITY':
                    if state in ('RUNNING', 'PAUSED'):
                        priority = param
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

            if state != 'NOT_OPENED' and not breached:
                limit = PRIORITY_LIMITS[priority]
                if used_time > limit:
                    breached = True
                    breached_at = m

            t_prev = m

        if has_had_valid_open:
            if t_prev < now:
                if state == 'RUNNING':
                    elapsed_biz = biz_mins_before(now) - biz_mins_before(t_prev)
                    if not breached:
                        limit = PRIORITY_LIMITS[priority]
                        needed = (limit + 1) - used_time
                        if elapsed_biz >= needed:
                            target = biz_mins_before(t_prev) + needed
                            low = t_prev + 1
                            high = now
                            while low < high:
                                mid = (low + high) // 2
                                if biz_mins_before(mid) >= target:
                                    high = mid
                                else:
                                    low = mid + 1
                            breached = True
                            breached_at = low
                    used_time += elapsed_biz

            results.append({
                "ticket_id": tid,
                "priority": priority,
                "used_minutes": used_time,
                "breached": breached,
                "breached_at": breached_at,
                "status": STATUS_MAP[state],
            })

    return results