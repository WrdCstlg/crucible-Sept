from bisect import bisect_left
from collections import defaultdict
from itertools import groupby

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


def _parse_line(line):
    line = line.strip()
    if not line:
        return None
    parts = [p.strip() for p in line.split(',')]
    if len(parts) not in (3, 4):
        return None

    m_str, ticket_id, event = parts[0], parts[1], parts[2]

    if not m_str or not all('0' <= c <= '9' for c in m_str):
        return None
    minute = int(m_str)

    if not ticket_id:
        return None

    if event == 'HOLIDAY':
        if len(parts) != 3 or ticket_id != '*':
            return None
        return (minute, '*', 'HOLIDAY', None)
    else:
        if ticket_id == '*':
            return None
        if event in ('OPEN', 'PRIORITY'):
            if len(parts) != 4:
                return None
            prio = parts[3]
            if prio not in LIMITS:
                return None
            return (minute, ticket_id, event, prio)
        elif event in ('PAUSE', 'RESUME', 'CLOSE', 'REOPEN'):
            if len(parts) != 3:
                return None
            return (minute, ticket_id, event, None)
        else:
            return None


def compute_sla(stream):
    holiday_days_set = set()
    ticket_events = []
    stream_idx = 0

    for raw_line in stream:
        record = _parse_line(raw_line)
        if record is not None:
            minute, ticket_id, event, prio = record
            if event == 'HOLIDAY':
                holiday_days_set.add(minute // 1440)
            else:
                ticket_events.append((minute, stream_idx, ticket_id, event, prio))
        stream_idx += 1

    if not ticket_events:
        return []

    now = max(e[0] for e in ticket_events)

    # Only weekday holidays affect business minutes
    effective_holidays = sorted(d for d in holiday_days_set if d % 7 < 5)

    def biz_minutes_to(M):
        if M <= 0:
            return 0
        D = M // 1440
        mod = M % 1440
        W = D // 7
        rem_days = D % 7
        w = rem_days

        std = W * 2400 + min(rem_days, 5) * 480
        if w < 5:
            std += max(0, min(480, mod - 540))

        idx = bisect_left(effective_holidays, D)
        hol = idx * 480
        if idx < len(effective_holidays) and effective_holidays[idx] == D:
            hol += max(0, min(480, mod - 540))

        return std - hol

    def biz_minutes_between(start_m, end_m):
        if end_m <= start_m:
            return 0
        return biz_minutes_to(end_m) - biz_minutes_to(start_m)

    def biz_days_before(D):
        if D <= 0:
            return 0
        W = D // 7
        rem_days = D % 7
        std_days = W * 5 + min(rem_days, 5)
        hol_days = bisect_left(effective_holidays, D)
        return std_days - hol_days

    def find_breach_minute(start_m, need):
        target_count = biz_minutes_to(start_m) + need
        K = (target_count - 1) // 480
        rem = target_count - K * 480

        # Smallest day D >= 0 such that biz_days_before(D + 1) > K
        low = 0
        high = (K + len(effective_holidays) + 2) * 7 // 5 + 14
        while low < high:
            mid = (low + high) // 2
            if biz_days_before(mid + 1) > K:
                high = mid
            else:
                low = mid + 1
        D = low
        return D * 1440 + 540 + rem

    tickets_events = defaultdict(list)
    for minute, s_idx, ticket_id, event, prio in ticket_events:
        tickets_events[ticket_id].append((minute, s_idx, event, prio))

    results = []

    for ticket_id in sorted(tickets_events.keys()):
        events = tickets_events[ticket_id]
        events.sort(key=lambda x: (x[0], x[1]))

        state = 'NOT_OPENED'
        priority = None
        used_minutes = 0
        breached = False
        breached_at = None
        had_valid_open = False
        t_prev = None

        for m, ev_group in groupby(events, key=lambda x: x[0]):
            ev_list = list(ev_group)

            # 1. Advance ticket to minute m if currently RUNNING
            if state == 'RUNNING':
                B = biz_minutes_between(t_prev, m)
                if B > 0:
                    if not breached:
                        limit = LIMITS[priority]
                        need = limit + 1 - used_minutes
                        if B >= need:
                            b_time = find_breach_minute(t_prev, need)
                            if b_time < m:
                                breached = True
                                breached_at = b_time
                    used_minutes += B

            # 2. Apply all events at minute m in original stream order
            for _, _, ev_type, prio in ev_list:
                if ev_type == 'OPEN':
                    if state in ('NOT_OPENED', 'CLOSED'):
                        had_valid_open = True
                        state = 'RUNNING'
                        priority = prio
                        used_minutes = 0
                        breached = False
                        breached_at = None
                elif ev_type == 'PRIORITY':
                    if state in ('RUNNING', 'PAUSED'):
                        priority = prio
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

            # 3. Check breach at minute m after all events at m are applied
            if had_valid_open and not breached:
                if used_minutes > LIMITS[priority]:
                    breached = True
                    breached_at = m

            t_prev = m

        if not had_valid_open:
            continue

        # 4. Advance ticket from last event to 'now'
        if state == 'RUNNING' and t_prev < now:
            B = biz_minutes_between(t_prev, now)
            if B > 0:
                if not breached:
                    limit = LIMITS[priority]
                    need = limit + 1 - used_minutes
                    if B >= need:
                        b_time = find_breach_minute(t_prev, need)
                        breached = True
                        breached_at = b_time
                used_minutes += B

        results.append({
            "ticket_id": ticket_id,
            "priority": priority,
            "used_minutes": used_minutes,
            "breached": breached,
            "breached_at": breached_at,
            "status": STATUS_MAP[state],
        })

    return results