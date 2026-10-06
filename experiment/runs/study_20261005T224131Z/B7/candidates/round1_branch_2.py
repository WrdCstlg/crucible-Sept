import bisect
from collections import defaultdict

# Priority limits in business minutes
PRIORITY_LIMITS = {
    'P1': 240,
    'P2': 480,
    'P3': 1440,
    'P4': 2400,
}

# Ticket states
NOT_OPENED = 0
RUNNING = 1
PAUSED = 2
CLOSED = 3

STATUS_NAMES = {
    RUNNING: 'running',
    PAUSED: 'paused',
    CLOSED: 'closed',
}


def _apply_event(state, prio, event, event_prio):
    """
    Applies an event to the ticket state machine.
    Returns (new_state, new_prio, is_cycle_reset).
    """
    if event == 'OPEN':
        if state == NOT_OPENED or state == CLOSED:
            return RUNNING, event_prio, True
        return state, prio, False
    elif event == 'PRIORITY':
        if state in (RUNNING, PAUSED):
            return state, event_prio, False
        return state, prio, False
    elif event == 'PAUSE':
        if state == RUNNING:
            return PAUSED, prio, False
        return state, prio, False
    elif event == 'RESUME':
        if state == PAUSED:
            return RUNNING, prio, False
        return state, prio, False
    elif event == 'CLOSE':
        if state in (RUNNING, PAUSED):
            return CLOSED, prio, False
        return state, prio, False
    elif event == 'REOPEN':
        if state == CLOSED:
            return RUNNING, prio, False
        return state, prio, False
    return state, prio, False


def compute_sla(stream):
    """
    Computes SLA metrics for all tickets in the input CSV stream.
    Uses an event sweep that rebuilds each ticket's running intervals,
    then counts business minutes per interval.
    """
    holidays = set()
    ticket_events = []

    # 1. Parse stream
    for line in stream:
        raw = line.strip()
        if not raw:
            continue
        parts = raw.split(',')
        if len(parts) not in (3, 4):
            continue
        parts = [p.strip() for p in parts]
        f1, f2, f3 = parts[0], parts[1], parts[2]

        if not (f1.isascii() and f1.isdigit()):
            continue
        m = int(f1)

        if not f2:
            continue

        if f3 not in {'OPEN', 'PRIORITY', 'PAUSE', 'RESUME', 'CLOSE', 'REOPEN', 'HOLIDAY'}:
            continue

        if f3 in ('OPEN', 'PRIORITY'):
            if len(parts) != 4:
                continue
            f4 = parts[3]
            if f4 not in ('P1', 'P2', 'P3', 'P4'):
                continue
            if f2 == '*':
                continue
            ticket_events.append((m, f2, f3, f4))
        else:
            if len(parts) != 3:
                continue
            if f3 == 'HOLIDAY':
                if f2 != '*':
                    continue
                holidays.add(m // 1440)
            else:
                if f2 == '*':
                    continue
                ticket_events.append((m, f2, f3, None))

    if not ticket_events:
        return []

    # "Now" is the largest minute among all well-formed ticket events
    now = max(ev[0] for ev in ticket_events)

    # 2. Calendar setup for fast business minute counting
    holiday_days = sorted(d for d in holidays if d % 7 < 5)

    def count_biz_minutes(t):
        if t <= 0:
            return 0
        d = t // 1440
        rem = t % 1440

        # Full business days in [0, d)
        num_weeks = d // 7
        rem_days = d % 7
        num_biz_days = num_weeks * 5 + min(rem_days, 5)
        actual_biz_days = num_biz_days - bisect.bisect_left(holiday_days, d)
        total = actual_biz_days * 480

        # Partial day d
        if d % 7 < 5 and d not in holidays:
            # Business hours [540, 1020)
            overlap = max(0, min(rem, 1020) - 540)
            total += overlap

        return total

    # 3. Sort ticket events stably by minute and group by ticket_id
    ticket_events.sort(key=lambda x: x[0])

    tickets_events_grouped = defaultdict(list)
    for m, tid, event, prio in ticket_events:
        tickets_events_grouped[tid].append((m, event, prio))

    results = []

    # 4. Process each ticket
    for tid, events in tickets_events_grouped.items():
        # Group consecutive events by minute
        grouped_by_minute = []
        for m, event, prio in events:
            if not grouped_by_minute or grouped_by_minute[-1][0] != m:
                grouped_by_minute.append((m, [(event, prio)]))
            else:
                grouped_by_minute[-1][1].append((event, prio))

        # --- Phase 1: Event sweep that rebuilds running intervals ---
        state = NOT_OPENED
        prio = None
        had_valid_open = False
        intervals = []
        last_m = None

        for m, ev_list in grouped_by_minute:
            if last_m is not None and m > last_m:
                intervals.append((last_m, m, state, prio))
                last_m = m

            for ev, ev_prio in ev_list:
                new_state, new_prio, is_reset = _apply_event(state, prio, ev, ev_prio)
                if is_reset:
                    had_valid_open = True
                    intervals.clear()
                    state = new_state
                    prio = new_prio
                    last_m = m
                else:
                    state = new_state
                    prio = new_prio

        if not had_valid_open:
            continue

        if last_m is not None and now > last_m:
            intervals.append((last_m, now, state, prio))

        status_at_now = STATUS_NAMES[state]
        priority_at_now = prio

        # --- Phase 2: Count business minutes per interval and check SLA breach ---
        used = 0
        breached = False
        breached_at = None

        for start, end, st, pr in intervals:
            lim = PRIORITY_LIMITS[pr]

            # Check breach at minute `start` after events at `start`
            if not breached and used > lim:
                breached = True
                breached_at = start

            # If RUNNING, count business minutes in [start, end)
            if st == RUNNING:
                delta = count_biz_minutes(end) - count_biz_minutes(start)
                if not breached:
                    k = (lim + 1) - used
                    if delta >= k:
                        # Find the first minute t where used time reached lim + 1
                        target = count_biz_minutes(start) + k
                        low = start + k
                        high = end
                        t_breach = end
                        while low <= high:
                            mid = (low + high) // 2
                            if count_biz_minutes(mid) >= target:
                                t_breach = mid
                                high = mid - 1
                            else:
                                low = mid + 1

                        if t_breach < end:
                            breached = True
                            breached_at = t_breach
                used += delta

        # Check breach at `now` after all events at `now`
        if not breached and used > PRIORITY_LIMITS[priority_at_now]:
            breached = True
            breached_at = now

        results.append({
            'ticket_id': tid,
            'priority': priority_at_now,
            'used_minutes': used,
            'breached': breached,
            'breached_at': breached_at,
            'status': status_at_now,
        })

    # Sort results by ticket_id ascending (code-point order)
    results.sort(key=lambda x: x['ticket_id'])
    return results