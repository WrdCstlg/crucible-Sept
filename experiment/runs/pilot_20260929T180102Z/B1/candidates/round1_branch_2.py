def compute_sla(stream):
    """
    Computes SLA metrics for support tickets from an event stream.
    Rebuilds each ticket's running time intervals and sums them.
    """
    well_formed_events = []

    for line in stream:
        trimmed_line = line.strip()
        if not trimmed_line:
            continue

        fields = trimmed_line.split(',')
        if len(fields) != 3:
            continue

        ts_part = fields[0].strip()
        ticket_id = fields[1].strip()
        event = fields[2].strip()

        if not ts_part or not ts_part.isascii() or not ts_part.isdigit():
            continue
        if not ticket_id:
            continue
        if event not in {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}:
            continue

        well_formed_events.append((int(ts_part), ticket_id, event))

    if not well_formed_events:
        return []

    # Stably sort events by timestamp
    well_formed_events.sort(key=lambda item: item[0])

    # "Now" is the largest timestamp among all well-formed lines
    now = max(ts for ts, _, _ in well_formed_events)

    ticket_state = {}
    ticket_run_start = {}
    ticket_intervals = {}
    valid_opened_tickets = set()

    # Process events to reconstruct intervals
    for ts, tid, event in well_formed_events:
        state = ticket_state.get(tid, "NOT_OPENED")

        if event == "OPEN":
            if state == "NOT_OPENED":
                ticket_state[tid] = "RUNNING"
                ticket_run_start[tid] = ts
                ticket_intervals[tid] = []
                valid_opened_tickets.add(tid)
            elif state == "CLOSED":
                ticket_state[tid] = "RUNNING"
                ticket_run_start[tid] = ts
                ticket_intervals[tid] = []  # Resets used time to 0
                valid_opened_tickets.add(tid)
            # Ignored if RUNNING or PAUSED

        elif event == "PAUSE":
            if state == "RUNNING":
                ticket_intervals[tid].append((ticket_run_start[tid], ts))
                ticket_run_start[tid] = None
                ticket_state[tid] = "PAUSED"
            # Ignored otherwise

        elif event == "RESUME":
            if state == "PAUSED":
                ticket_state[tid] = "RUNNING"
                ticket_run_start[tid] = ts
            # Ignored otherwise

        elif event == "CLOSE":
            if state == "RUNNING":
                ticket_intervals[tid].append((ticket_run_start[tid], ts))
                ticket_run_start[tid] = None
                ticket_state[tid] = "CLOSED"
            elif state == "PAUSED":
                ticket_state[tid] = "CLOSED"
            # Ignored otherwise

        elif event == "REOPEN":
            if state == "CLOSED":
                ticket_state[tid] = "RUNNING"
                ticket_run_start[tid] = ts
                # Used time continues from total; intervals are retained
            # Ignored otherwise

    sla_limit_ms = 14_400_000
    results = []

    # Output sorted by ticket_id ascending (Python code-point order)
    for tid in sorted(valid_opened_tickets):
        state = ticket_state[tid]
        intervals = list(ticket_intervals.get(tid, []))

        # A ticket still RUNNING when the stream ends counts up to "now"
        if state == "RUNNING":
            intervals.append((ticket_run_start[tid], now))

        used_ms = sum(end - start for start, end in intervals)
        breached = used_ms > sla_limit_ms
        status = "closed" if state == "CLOSED" else "open"

        results.append({
            "ticket_id": tid,
            "used_ms": used_ms,
            "breached": breached,
            "status": status,
        })

    return results