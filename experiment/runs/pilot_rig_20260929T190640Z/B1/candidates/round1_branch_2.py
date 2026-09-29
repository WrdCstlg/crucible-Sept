"""Module for computing support-ticket SLA clocks."""

from collections import defaultdict

VALID_EVENTS = {'OPEN', 'PAUSE', 'RESUME', 'CLOSE', 'REOPEN'}
SLA_LIMIT_MS = 14_400_000


def _parse_well_formed_events(stream):
    """Parse and filter well-formed events from the raw stream."""
    well_formed = []
    for line in stream:
        if not isinstance(line, str):
            continue
        trimmed_line = line.strip()
        parts = trimmed_line.split(',')
        if len(parts) != 3:
            continue

        ts_str = parts[0].strip()
        ticket_id = parts[1].strip()
        event = parts[2].strip()

        if not ts_str or not all('0' <= c <= '9' for c in ts_str):
            continue
        if not ticket_id:
            continue
        if event not in VALID_EVENTS:
            continue

        ts = int(ts_str, 10)
        well_formed.append((ts, ticket_id, event))

    return well_formed


def _rebuild_running_intervals(events, now):
    """
    Rebuild running time intervals for a single ticket.

    Returns:
        (has_valid_open, intervals, final_state)
        where intervals is a list of (start_ms, end_ms) tuples.
    """
    state = 'NOT_OPENED'
    has_valid_open = False
    intervals = []
    running_start = None

    for ts, event in events:
        if event == 'OPEN':
            if state in ('NOT_OPENED', 'CLOSED'):
                state = 'RUNNING'
                has_valid_open = True
                intervals = []  # Used time starts at 0 or resets to 0
                running_start = ts
            # If RUNNING or PAUSED: ignored
        elif event == 'PAUSE':
            if state == 'RUNNING':
                state = 'PAUSED'
                intervals.append((running_start, ts))
                running_start = None
            # Otherwise ignored
        elif event == 'RESUME':
            if state == 'PAUSED':
                state = 'RUNNING'
                running_start = ts
            # Otherwise ignored
        elif event == 'CLOSE':
            if state == 'RUNNING':
                state = 'CLOSED'
                intervals.append((running_start, ts))
                running_start = None
            elif state == 'PAUSED':
                state = 'CLOSED'
            # Otherwise ignored
        elif event == 'REOPEN':
            if state == 'CLOSED':
                state = 'RUNNING'
                running_start = ts
                # Used time continues from total; existing intervals preserved
            # Otherwise ignored

    if not has_valid_open:
        return False, [], state

    if state == 'RUNNING':
        intervals.append((running_start, now))
        running_start = None

    return True, intervals, state


def compute_sla(stream):
    """
    Compute SLA used time and breach status for all opened tickets in stream.

    Architectural approach: Rebuild each ticket's running time intervals,
    then sum them.
    """
    events = _parse_well_formed_events(stream)
    if not events:
        return []

    # Sort events by timestamp stably to preserve original arrival order
    events.sort(key=lambda x: x[0])

    # "Now" is the largest timestamp among all well-formed lines
    now = events[-1][0]

    # Group events by ticket preserving sorted timestamp order
    events_by_ticket = defaultdict(list)
    for ts, ticket_id, event in events:
        events_by_ticket[ticket_id].append((ts, event))

    results = []
    for ticket_id in sorted(events_by_ticket.keys()):
        has_valid_open, intervals, final_state = _rebuild_running_intervals(
            events_by_ticket[ticket_id], now
        )
        if not has_valid_open:
            continue

        # Sum the running time intervals
        used_ms = sum(end - start for start, end in intervals)
        breached = used_ms > SLA_LIMIT_MS
        status = 'closed' if final_state == 'CLOSED' else 'open'

        results.append({
            'ticket_id': ticket_id,
            'used_ms': used_ms,
            'breached': breached,
            'status': status,
        })

    return results