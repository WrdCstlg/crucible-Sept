from bisect import bisect_left
from itertools import groupby

LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}


def _parse_line(line):
    s = line.strip()
    if not s:
        return None

    parts = s.split(',')
    if len(parts) not in (3, 4):
        return None

    f0 = parts[0].strip()
    f1 = parts[1].strip()
    f2 = parts[2].strip()

    if not f0 or not f0.isascii() or not f0.isdigit():
        return None
    minute = int(f0)

    ticket_id = f1
    if not ticket_id:
        return None

    event = f2

    if event in ('OPEN', 'PRIORITY'):
        if len(parts) != 4:
            return None
        priority = parts[3].strip()
        if priority not in LIMITS:
            return None
    elif event in ('PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'):
        if len(parts) != 3:
            return None
        priority = None
    else:
        return None

    if event == 'HOLIDAY':
        if ticket_id != '*':
            return None
    else:
        if ticket_id == '*':
            return None

    return minute, ticket_id, event, priority


def compute_sla(stream):
    holiday_days = set()
    ticket_events_by_id = {}
    now = None

    for stream_idx, line in enumerate(stream):
        parsed = _parse_line(line)
        if parsed is None:
            continue

        minute, ticket_id, event, priority = parsed
        if event == 'HOLIDAY':
            holiday_days.add(minute // 1440)
        else:
            if now is None or minute > now:
                now = minute
            if ticket_id not in ticket_events_by_id:
                ticket_events_by_id[ticket_id] = []
            ticket_events_by_id[ticket_id].append((minute, stream_idx, event, priority))

    if now is None:
        return []

    weekday_holidays = sorted(d for d in holiday_days if d % 7 < 5)
    weekday_holidays_set = set(weekday_holidays)

    def biz_minutes_before(m: int) -> int:
        d = m // 1440
        rem = m % 1440

        w = d // 7
        r = d % 7
        base_biz_days = w * 5 + (r if r < 5 else 5)
        h_count = bisect_left(weekday_holidays, d)
        full_day_biz_mins = (base_biz_days - h_count) * 480

        if r < 5 and d not in weekday_holidays_set:
            if rem > 540:
                day_biz = min(rem, 1020) - 540
            else:
                day_biz = 0
        else:
            day_biz = 0

        return full_day_biz_mins + day_biz

    def biz_minutes_between(m1: int, m2: int) -> int:
        if m2 <= m1:
            return 0
        return biz_minutes_before(m2) - biz_minutes_before(m1)

    def find_breach_minute(m_start: int, needed: int, m_end: int) -> int:
        target = biz_minutes_before(m_start) + needed
        low = m_start + needed
        high = m_end
        ans = m_end
        while low <= high:
            mid = (low + high) // 2
            if biz_minutes_before(mid) >= target:
                ans = mid
                high = mid - 1
            else:
                low = mid + 1
        return ans

    result = []

    for ticket_id, events in ticket_events_by_id.items():
        events.sort(key=lambda x: (x[0], x[1]))

        events_by_minute = []
        for m, grp in groupby(events, key=lambda x: x[0]):
            events_by_minute.append((m, list(grp)))

        m_prev = None
        state = 'NOT_OPENED'
        priority = None
        used = 0
        breached = False
        breached_at = None
        had_valid_open = False

        for m_curr, ev_list in events_by_minute:
            if m_prev is not None and m_curr > m_prev:
                if state == 'RUNNING':
                    biz = biz_minutes_between(m_prev, m_curr)
                    if not breached:
                        needed = LIMITS[priority] + 1 - used
                        if biz >= needed:
                            t_b = find_breach_minute(m_prev, needed, m_curr)
                            if t_b < m_curr:
                                breached = True
                                breached_at = t_b
                    used += biz

            m_prev = m_curr

            for _, _, ev, p in ev_list:
                if ev == 'OPEN':
                    if state in ('NOT_OPENED', 'CLOSED'):
                        state = 'RUNNING'
                        priority = p
                        used = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
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

            if state != 'NOT_OPENED':
                if not breached and used > LIMITS[priority]:
                    breached = True
                    breached_at = m_curr

        if m_prev is not None and now > m_prev:
            if state == 'RUNNING':
                biz = biz_minutes_between(m_prev, now)
                if not breached:
                    needed = LIMITS[priority] + 1 - used
                    if biz >= needed:
                        t_b = find_breach_minute(m_prev, needed, now)
                        if t_b <= now:
                            breached = True
                            breached_at = t_b
                used += biz

        if had_valid_open:
            result.append({
                "ticket_id": ticket_id,
                "priority": priority,
                "used_minutes": used,
                "breached": breached,
                "breached_at": breached_at,
                "status": state.lower(),
            })

    result.sort(key=lambda x: x["ticket_id"])
    return result