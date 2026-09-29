def compute_sla(stream):
    VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}
    SLA_LIMIT_MS = 14_400_000

    max_now = None
    raw_events = []

    for idx, line in enumerate(stream):
        if not isinstance(line, str):
            continue
        line_clean = line.strip()
        if not line_clean:
            continue
        parts = [p.strip() for p in line_clean.split(",")]
        try:
            ts = int(parts[0])
            if ts < 0:
                continue
        except (ValueError, IndexError):
            continue

        if max_now is None or ts > max_now:
            max_now = ts

        if len(parts) == 3:
            ticket_id = parts[1]
            event = parts[2]
            if ticket_id and event in VALID_EVENTS:
                raw_events.append((ts, idx, ticket_id, event))

    raw_events.sort(key=lambda x: (x[0], x[1]))

    tickets_events = {}
    for ts, idx, ticket_id, event in raw_events:
        if ticket_id not in tickets_events:
            tickets_events[ticket_id] = []
        tickets_events[ticket_id].append((ts, event))

    results = []

    for ticket_id, events in tickets_events.items():
        has_valid_open = False
        state = "UNOPENED"
        intervals = []
        running_start = None

        for ts, event in events:
            if state == "UNOPENED":
                if event == "OPEN":
                    has_valid_open = True
                    state = "RUNNING"
                    running_start = ts
            elif state == "RUNNING":
                if event == "PAUSE":
                    intervals.append((running_start, ts))
                    running_start = None
                    state = "PAUSED"
                elif event == "CLOSE":
                    intervals.append((running_start, ts))
                    running_start = None
                    state = "CLOSED"
            elif state == "PAUSED":
                if event == "RESUME":
                    running_start = ts
                    state = "RUNNING"
                elif event == "CLOSE":
                    state = "CLOSED"
            elif state == "CLOSED":
                if event == "REOPEN":
                    running_start = ts
                    state = "RUNNING"

        if not has_valid_open:
            continue

        if state == "RUNNING":
            intervals.append((running_start, max_now))
            status = "open"
        elif state == "PAUSED":
            status = "open"
        elif state == "CLOSED":
            status = "closed"
        else:
            continue

        used_ms = sum(end - start for start, end in intervals)
        breached = used_ms > SLA_LIMIT_MS

        results.append({
            "ticket_id": ticket_id,
            "used_ms": used_ms,
            "breached": breached,
            "status": status,
        })

    results.sort(key=lambda x: x["ticket_id"])
    return results