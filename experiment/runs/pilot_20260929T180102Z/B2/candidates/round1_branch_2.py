def compute_sla(stream):
    valid_events = []

    for raw_line in stream:
        if not isinstance(raw_line, str):
            continue
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(",")
        if len(parts) != 3:
            continue

        ts_part = parts[0].strip()
        ticket_id = parts[1].strip()
        event = parts[2].strip()

        if not (ts_part.isascii() and ts_part.isdigit() and len(ts_part) > 0):
            continue
        if not ticket_id:
            continue
        if event not in {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}:
            continue

        valid_events.append((int(ts_part), ticket_id, event))

    if not valid_events:
        return []

    # Events may arrive out of order; sort stably by timestamp
    valid_events.sort(key=lambda x: x[0])

    # "Now" is the largest timestamp among all well-formed lines
    now = valid_events[-1][0]

    # Rebuild running intervals for each ticket
    tickets = {}

    for ts, ticket_id, event in valid_events:
        if ticket_id not in tickets:
            tickets[ticket_id] = {
                "state": "NOT_OPENED",
                "opened": False,
                "intervals": [],
                "current_run_start": None,
            }

        t = tickets[ticket_id]
        state = t["state"]

        if event == "OPEN":
            if state == "NOT_OPENED":
                t["opened"] = True
                t["state"] = "RUNNING"
                t["current_run_start"] = ts
                t["intervals"] = []
            elif state == "CLOSED":
                t["state"] = "RUNNING"
                t["current_run_start"] = ts
                t["intervals"] = []  # used time resets to 0
        elif event == "PAUSE":
            if state == "RUNNING":
                t["intervals"].append((t["current_run_start"], ts))
                t["current_run_start"] = None
                t["state"] = "PAUSED"
        elif event == "RESUME":
            if state == "PAUSED":
                t["current_run_start"] = ts
                t["state"] = "RUNNING"
        elif event == "CLOSE":
            if state == "RUNNING":
                t["intervals"].append((t["current_run_start"], ts))
                t["current_run_start"] = None
                t["state"] = "CLOSED"
            elif state == "PAUSED":
                t["state"] = "CLOSED"
        elif event == "REOPEN":
            if state == "CLOSED":
                t["current_run_start"] = ts
                t["state"] = "RUNNING"

    results = []
    for ticket_id, t in tickets.items():
        if not t["opened"]:
            continue

        # A ticket still RUNNING when the stream ends counts up to "now"
        if t["state"] == "RUNNING":
            t["intervals"].append((t["current_run_start"], now))

        used_ms = sum(end - start for start, end in t["intervals"])
        breached = used_ms > 14_400_000
        status = "closed" if t["state"] == "CLOSED" else "open"

        results.append({
            "ticket_id": ticket_id,
            "used_ms": used_ms,
            "breached": breached,
            "status": status,
        })

    results.sort(key=lambda x: x["ticket_id"])
    return results