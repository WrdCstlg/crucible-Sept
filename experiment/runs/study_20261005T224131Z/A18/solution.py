from bisect import bisect_left
from collections import defaultdict

LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}

VALID_EVENTS = {
    'OPEN',
    'PRIORITY',
    'PAUSE',
    'RESUME',
    'CLOSE',
    'REOPEN',
    'HOLIDAY',
}


def parse_line(raw_line):
    line = raw_line.strip()
    if not line:
        return None
    parts = line.split(',')
    if len(parts) not in (3, 4):
        return None
    parts = [p.strip() for p in parts]

    minute_str = parts[0]
    if not minute_str or not all('0' <= c <= '9' for c in minute_str):
        return None
    minute = int(minute_str)

    ticket_id = parts[1]
    if not ticket_id:
        return None

    event = parts[2]
    if event not in VALID_EVENTS:
        return None

    if event in ('OPEN', 'PRIORITY'):
        if len(parts) != 4:
            return None
        prio = parts[3]
        if prio not in ('P1', 'P2', 'P3', 'P4'):
            return None
    else:
        if len(parts) != 3:
            return None
        prio = None

    if event == 'HOLIDAY':
        if ticket_id != '*':
            return None
    else:
        if ticket_id == '*':
            return None

    return minute, ticket_id, event, prio


def compute_sla(stream):
    holiday_days = set()
    ticket_events = defaultdict(list)
    max_ticket_minute = None
    stream_idx = 0

    for raw_line in stream:
        parsed = parse_line(raw_line)
        if parsed is None:
            continue
        minute, ticket_id, event, prio = parsed
        if event == 'HOLIDAY':
            holiday_days.add(minute // 1440)
        else:
            ticket_events[ticket_id].append((minute, stream_idx, event, prio))
            if max_ticket_minute is None or minute > max_ticket_minute:
                max_ticket_minute = minute
            stream_idx += 1

    if max_ticket_minute is None:
        return []

    now = max_ticket_minute
    sorted_holidays = sorted(d for d in holiday_days if d % 7 < 5)
    num_holidays = len(sorted_holidays)

    def total_bm(t):
        if t <= 0:
            return 0
        weeks = t // 10080
        rem = t % 10080
        day = rem // 1440
        mod = rem % 1440
        ans = weeks * 2400
        if day < 5:
            ans += day * 480
            if mod > 540:
                ans += min(mod, 1020) - 540
        else:
            ans += 2400

        if num_holidays:
            d_t = t // 1440
            idx = bisect_left(sorted_holidays, d_t)
            ans -= idx * 480
            if idx < num_holidays and sorted_holidays[idx] == d_t:
                if mod > 540:
                    ans -= min(mod, 1020) - 540
        return ans

    def find_breach_time(start_t, end_t, target):
        if total_bm(end_t) < target:
            return None
        low = start_t
        high = end_t
        while low < high:
            mid = (low + high) // 2
            if total_bm(mid) >= target:
                high = mid
            else:
                low = mid + 1
        return low

    results = []

    for ticket_id, raw_events in ticket_events.items():
        raw_events.sort(key=lambda x: (x[0], x[1]))

        grouped_events = []
        for m, _, ev, pr in raw_events:
            if not grouped_events or grouped_events[-1][0] != m:
                grouped_events.append((m, [(ev, pr)]))
            else:
                grouped_events[-1][1].append((ev, pr))

        state = 'NOT_OPENED'
        priority = None
        used = 0
        breached = False
        breached_at = None
        had_valid_open = False

        prev_m = None

        for m, ev_list in grouped_events:
            if prev_m is not None:
                if state == 'RUNNING':
                    if not breached and m - prev_m >= 2:
                        limit = LIMITS[priority]
                        rem = limit + 1 - used
                        if rem > 0:
                            target = total_bm(prev_m) + rem
                            t_breach = find_breach_time(prev_m + 1, m - 1, target)
                            if t_breach is not None and t_breach <= now:
                                breached = True
                                breached_at = t_breach
                    used += total_bm(m) - total_bm(prev_m)

            prev_m = m

            for ev, pr in ev_list:
                if ev == 'OPEN':
                    if state in ('NOT_OPENED', 'CLOSED'):
                        state = 'RUNNING'
                        priority = pr
                        used = 0
                        breached = False
                        breached_at = None
                        had_valid_open = True
                elif ev == 'PRIORITY':
                    if state in ('RUNNING', 'PAUSED'):
                        priority = pr
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

            if m <= now and not breached and had_valid_open and priority is not None:
                if used > LIMITS[priority]:
                    breached = True
                    breached_at = m

        if prev_m is not None and prev_m < now:
            if state == 'RUNNING':
                if not breached:
                    limit = LIMITS[priority]
                    rem = limit + 1 - used
                    if rem > 0:
                        target = total_bm(prev_m) + rem
                        t_breach = find_breach_time(prev_m + 1, now, target)
                        if t_breach is not None and t_breach <= now:
                            breached = True
                            breached_at = t_breach
                used += total_bm(now) - total_bm(prev_m)

        if had_valid_open:
            results.append({
                'ticket_id': ticket_id,
                'priority': priority,
                'used_minutes': used,
                'breached': breached,
                'breached_at': breached_at,
                'status': state.lower(),
            })

    results.sort(key=lambda x: x['ticket_id'])
    return results