def compute_sla(stream):
    sla_limit = 14_400_000
    valid_events = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}

    well_formed = []
    for idx, line in enumerate(stream):
        if not isinstance(line, str):
            continue
        trimmed = line.strip()
        parts = trimmed.split(",")
        if len(parts) != 3:
            continue

        ts_str = parts[0].strip()
        ticket_id = parts[1].strip()
        event = parts[2].strip()

        if not (ts_str and all("0" <= c <= "9" for c in ts_str)):
            continue
        if not ticket_id:
            continue
        if event not in valid_events:
            continue

        ts = int(ts_str, 10)
        well_formed.append((ts, idx, ticket_id, event))

    if not well_formed:
        return []

    now = max(item[0] for item in well_formed)
    well_formed.sort(key=lambda x: (x[0], x[1]))

    # Ticket state machine
    # States: 'NOT_OPENED', 'RUNNING', 'PAUSED', 'CLOSED'
    tickets = {}

    for ts, _, tid, event in well_formed:
        if tid not in tickets:
            tickets[tid] = {
                "state": "NOT_OPENED",
                "used_ms": 0,
                "running_start": None,
                "had_valid_open": False,
            }
        t = tickets[tid]
        state = t["state"]

        if event == "OPEN":
            if state == "NOT_OPENED" or state == "CLOSED":
                t["state"] = "RUNNING"
                t["used_ms"] = 0
                t["running_start"] = ts
                t["had_valid_open"] = True
            # RUNNING or PAUSED: ignored
        elif event == "PAUSE":
            if state == "RUNNING":
                t["used_ms"] += ts - t["running_start"]
                t["running_start"] = None
                t["state"] = "PAUSED"
            # NOT_OPENED, PAUSED, CLOSED: ignored
        elif event == "RESUME":
            if state == "PAUSED":
                t["running_start"] = ts
                t["state"] = "RUNNING"
            # NOT_OPENED, RUNNING, CLOSED: ignored
        elif event == "CLOSE":
            if state == "RUNNING":
                t["used_ms"] += ts - t["running_start"]
                t["running_start"] = None
                t["state"] = "CLOSED"
            elif state == "PAUSED":
                t["state"] = "CLOSED"
            # NOT_OPENED, CLOSED: ignored
        elif event == "REOPEN":
            if state == "CLOSED":
                t["running_start"] = ts
                t["state"] = "RUNNING"
            # NOT_OPENED, RUNNING, PAUSED: ignored

    results = []
    for tid in sorted(tickets.keys()):
        t = tickets[tid]
        if not t["had_valid_open"]:
            continue

        used = t["used_ms"]
        if t["state"] == "RUNNING":
            used += now - t["running_start"]

        status = "closed" if t["state"] == "CLOSED" else "open"
        breached = used > sla_limit

        results.append(
            {
                "ticket_id": tid,
                "used_ms": used,
                "breached": breached,
                "status": status,
            }
        )

    return results