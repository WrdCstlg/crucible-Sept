def compute_sla(stream):
    valid_events = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}
    sla_limit = 14_400_000

    well_formed = []
    for line in stream:
        if not isinstance(line, str):
            continue
        trimmed = line.strip()
        parts = trimmed.split(",")
        if len(parts) != 3:
            continue
        f0 = parts[0].strip()
        f1 = parts[1].strip()
        f2 = parts[2].strip()

        if not f0 or not all("0" <= c <= "9" for c in f0):
            continue
        if not f1:
            continue
        if f2 not in valid_events:
            continue

        ts = int(f0)
        well_formed.append((ts, f1, f2))

    if not well_formed:
        return []

    # Process events in timestamp order; stable sort preserves original order
    well_formed.sort(key=lambda x: x[0])

    now = well_formed[-1][0]

    tickets = {}

    for ts, ticket_id, event in well_formed:
        if ticket_id not in tickets:
            tickets[ticket_id] = {
                "state": "NOT_OPENED",
                "used_ms": 0,
                "last_running_ts": 0,
                "ever_opened": False,
            }

        t = tickets[ticket_id]
        state = t["state"]

        if event == "OPEN":
            if state in ("NOT_OPENED", "CLOSED"):
                t["state"] = "RUNNING"
                t["used_ms"] = 0
                t["last_running_ts"] = ts
                t["ever_opened"] = True
        elif event == "PAUSE":
            if state == "RUNNING":
                t["used_ms"] += ts - t["last_running_ts"]
                t["state"] = "PAUSED"
        elif event == "RESUME":
            if state == "PAUSED":
                t["last_running_ts"] = ts
                t["state"] = "RUNNING"
        elif event == "CLOSE":
            if state == "RUNNING":
                t["used_ms"] += ts - t["last_running_ts"]
                t["state"] = "CLOSED"
            elif state == "PAUSED":
                t["state"] = "CLOSED"
        elif event == "REOPEN":
            if state == "CLOSED":
                t["last_running_ts"] = ts
                t["state"] = "RUNNING"

    result = []
    for ticket_id, t in tickets.items():
        if not t["ever_opened"]:
            continue
        used_ms = t["used_ms"]
        if t["state"] == "RUNNING":
            used_ms += now - t["last_running_ts"]

        result.append(
            {
                "ticket_id": ticket_id,
                "used_ms": used_ms,
                "breached": used_ms > sla_limit,
                "status": "closed" if t["state"] == "CLOSED" else "open",
            }
        )

    result.sort(key=lambda x: x["ticket_id"])
    return result