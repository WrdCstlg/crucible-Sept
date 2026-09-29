def compute_sla(stream):
    valid_events = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}
    well_formed = []

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

        if not (ts_str.isascii() and ts_str.isdigit()):
            continue
        if not ticket_id:
            continue
        if event not in valid_events:
            continue

        well_formed.append((int(ts_str), ticket_id, event))

    if not well_formed:
        return []

    # Events with equal timestamps preserve original stream order (stable sort)
    well_formed.sort(key=lambda x: x[0])
    now = well_formed[-1][0]

    tickets = {}

    for ts, tid, event in well_formed:
        if tid not in tickets:
            tickets[tid] = {
                "state": "NOT_OPENED",
                "used_ms": 0,
                "last_running_start": 0,
                "had_valid_open": False,
            }
        ticket = tickets[tid]
        state = ticket["state"]

        if event == "OPEN":
            if state in ("NOT_OPENED", "CLOSED"):
                ticket["state"] = "RUNNING"
                ticket["used_ms"] = 0
                ticket["last_running_start"] = ts
                ticket["had_valid_open"] = True
        elif event == "PAUSE":
            if state == "RUNNING":
                ticket["used_ms"] += ts - ticket["last_running_start"]
                ticket["state"] = "PAUSED"
        elif event == "RESUME":
            if state == "PAUSED":
                ticket["state"] = "RUNNING"
                ticket["last_running_start"] = ts
        elif event == "CLOSE":
            if state == "RUNNING":
                ticket["used_ms"] += ts - ticket["last_running_start"]
                ticket["state"] = "CLOSED"
            elif state == "PAUSED":
                ticket["state"] = "CLOSED"
        elif event == "REOPEN":
            if state == "CLOSED":
                ticket["state"] = "RUNNING"
                ticket["last_running_start"] = ts

    sla_limit = 14_400_000
    results = []

    for tid in sorted(tickets.keys()):
        ticket = tickets[tid]
        if not ticket["had_valid_open"]:
            continue

        used_ms = ticket["used_ms"]
        if ticket["state"] == "RUNNING":
            used_ms += now - ticket["last_running_start"]

        status = "closed" if ticket["state"] == "CLOSED" else "open"
        breached = used_ms > sla_limit

        results.append({
            "ticket_id": tid,
            "used_ms": used_ms,
            "breached": breached,
            "status": status,
        })

    return results