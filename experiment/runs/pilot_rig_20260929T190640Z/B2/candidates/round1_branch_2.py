from collections import defaultdict

SLA_LIMIT_MS = 14_400_000
VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}


def _rebuild_running_intervals(ticket_events, now):
    """
    Rebuild the list of running time intervals [(start, end), ...] for a ticket.
    Returns (intervals, final_state, had_valid_open).
    """
    state = "NOT_OPENED"
    had_valid_open = False
    running_start = None
    intervals = []

    for ts, event in ticket_events:
        if event == "OPEN":
            if state == "NOT_OPENED":
                had_valid_open = True
                state = "RUNNING"
                running_start = ts
                intervals = []
            elif state == "CLOSED":
                had_valid_open = True
                state = "RUNNING"
                running_start = ts
                intervals = []
            # RUNNING or PAUSED: ignored
        elif event == "PAUSE":
            if state == "RUNNING":
                intervals.append((running_start, ts))
                running_start = None
                state = "PAUSED"
            # NOT_OPENED, PAUSED, CLOSED: ignored
        elif event == "RESUME":
            if state == "PAUSED":
                state = "RUNNING"
                running_start = ts
            # NOT_OPENED, RUNNING, CLOSED: ignored
        elif event == "CLOSE":
            if state == "RUNNING":
                intervals.append((running_start, ts))
                running_start = None
                state = "CLOSED"
            elif state == "PAUSED":
                state = "CLOSED"
            # NOT_OPENED, CLOSED: ignored
        elif event == "REOPEN":
            if state == "CLOSED":
                state = "RUNNING"
                running_start = ts
            # NOT_OPENED, RUNNING, PAUSED: ignored

    if state == "RUNNING":
        intervals.append((running_start, now))

    return intervals, state, had_valid_open


def compute_sla(stream):
    """
    Compute SLA status for tickets in the provided event stream.
    Rebuilds each ticket's running time intervals, then sums them.
    """
    well_formed_events = []

    for line in stream:
        if not isinstance(line, str):
            continue
        trimmed_line = line.strip()
        parts = trimmed_line.split(",")
        if len(parts) != 3:
            continue

        ts_str = parts[0].strip()
        ticket_id = parts[1].strip()
        event = parts[2].strip()

        if not ts_str or not ts_str.isascii() or not ts_str.isdigit():
            continue
        if not ticket_id:
            continue
        if event not in VALID_EVENTS:
            continue

        timestamp = int(ts_str)
        well_formed_events.append((timestamp, ticket_id, event))

    if not well_formed_events:
        return []

    # Sort events stably by timestamp
    well_formed_events.sort(key=lambda item: item[0])

    # "Now" is the largest timestamp among all well-formed lines
    now = well_formed_events[-1][0]

    # Group events by ticket preserving sorted order
    events_by_ticket = defaultdict(list)
    for ts, ticket_id, event in well_formed_events:
        events_by_ticket[ticket_id].append((ts, event))

    results = []
    for ticket_id in sorted(events_by_ticket.keys()):
        ticket_events = events_by_ticket[ticket_id]
        intervals, final_state, had_valid_open = _rebuild_running_intervals(
            ticket_events, now
        )

        if not had_valid_open:
            continue

        used_ms = sum(end - start for start, end in intervals)
        breached = used_ms > SLA_LIMIT_MS
        status = "closed" if final_state == "CLOSED" else "open"

        results.append(
            {
                "ticket_id": ticket_id,
                "used_ms": used_ms,
                "breached": breached,
                "status": status,
            }
        )

    return results