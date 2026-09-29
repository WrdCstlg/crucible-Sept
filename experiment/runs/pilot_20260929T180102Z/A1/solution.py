def compute_sla(stream):
    """
    Computes SLA usage and breach status for support tickets from a stream of CSV events.
    """
    valid_events = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}
    SLA_LIMIT = 14_400_000

    parsed_records = []
    max_timestamp = None

    for line in stream:
        trimmed_line = line.strip()
        parts = trimmed_line.split(",")
        if len(parts) != 3:
            continue

        ts_str = parts[0].strip()
        ticket_id = parts[1].strip()
        event = parts[2].strip()

        if not ts_str or not all(c in "0123456789" for c in ts_str):
            continue
        if not ticket_id:
            continue
        if event not in valid_events:
            continue

        ts = int(ts_str)
        if max_timestamp is None or ts > max_timestamp:
            max_timestamp = ts

        parsed_records.append((ts, ticket_id, event))

    if not parsed_records or max_timestamp is None:
        return []

    # Events may arrive out of order; stable sort by timestamp
    parsed_records.sort(key=lambda r: r[0])

    tickets = {}

    for ts, ticket_id, event in parsed_records:
        if ticket_id not in tickets:
            tickets[ticket_id] = {
                "state": "NOT_OPENED",
                "used_ms": 0,
                "running_start": 0,
                "ever_opened": False,
            }

        t = tickets[ticket_id]
        state = t["state"]

        if event == "OPEN":
            if state == "NOT_OPENED":
                t["state"] = "RUNNING"
                t["used_ms"] = 0
                t["running_start"] = ts
                t["ever_opened"] = True
            elif state == "CLOSED":
                t["state"] = "RUNNING"
                t["used_ms"] = 0
                t["running_start"] = ts
        elif event == "PAUSE":
            if state == "RUNNING":
                t["used_ms"] += ts - t["running_start"]
                t["state"] = "PAUSED"
        elif event == "RESUME":
            if state == "PAUSED":
                t["running_start"] = ts
                t["state"] = "RUNNING"
        elif event == "CLOSE":
            if state == "RUNNING":
                t["used_ms"] += ts - t["running_start"]
                t["state"] = "CLOSED"
            elif state == "PAUSED":
                t["state"] = "CLOSED"
        elif event == "REOPEN":
            if state == "CLOSED":
                t["running_start"] = ts
                t["state"] = "RUNNING"

    results = []
    for ticket_id, t in tickets.items():
        if not t["ever_opened"]:
            continue

        used_ms = t["used_ms"]
        if t["state"] == "RUNNING":
            used_ms += max_timestamp - t["running_start"]

        results.append({
            "ticket_id": ticket_id,
            "used_ms": used_ms,
            "breached": used_ms > SLA_LIMIT,
            "status": "closed" if t["state"] == "CLOSED" else "open",
        })

    results.sort(key=lambda x: x["ticket_id"])
    return results