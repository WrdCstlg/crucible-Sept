"""Module for computing support-ticket SLA clocks."""


def compute_sla(stream):
    """Compute SLA clock metrics for a stream of ticket events."""
    valid_events = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}

    events = []
    for line in stream:
        if not isinstance(line, str):
            continue
        trimmed = line.strip()
        parts = trimmed.split(",")
        if len(parts) != 3:
            continue

        ts_str = parts[0].strip()
        ticket_id = parts[1].strip()
        event = parts[2].strip()

        if not ts_str or not all("0" <= c <= "9" for c in ts_str):
            continue
        if not ticket_id:
            continue
        if event not in valid_events:
            continue

        events.append((int(ts_str), ticket_id, event))

    if not events:
        return []

    # Stable sort by timestamp
    events.sort(key=lambda x: x[0])

    now = events[-1][0]

    # Track state for tickets that have had at least one valid OPEN
    tickets = {}

    for ts, ticket_id, event in events:
        if ticket_id not in tickets:
            # Ticket is in NOT_OPENED state
            if event == "OPEN":
                tickets[ticket_id] = {
                    "state": "RUNNING",
                    "used_ms": 0,
                    "running_start": ts,
                }
            # All other events in NOT_OPENED are ignored
            continue

        t = tickets[ticket_id]
        state = t["state"]

        if state == "RUNNING":
            if event == "PAUSE":
                t["used_ms"] += ts - t["running_start"]
                t["state"] = "PAUSED"
            elif event == "CLOSE":
                t["used_ms"] += ts - t["running_start"]
                t["state"] = "CLOSED"
            # OPEN, RESUME, REOPEN are ignored

        elif state == "PAUSED":
            if event == "RESUME":
                t["running_start"] = ts
                t["state"] = "RUNNING"
            elif event == "CLOSE":
                t["state"] = "CLOSED"
            # OPEN, PAUSE, REOPEN are ignored

        elif state == "CLOSED":
            if event == "OPEN":
                t["used_ms"] = 0
                t["running_start"] = ts
                t["state"] = "RUNNING"
            elif event == "REOPEN":
                t["running_start"] = ts
                t["state"] = "RUNNING"
            # PAUSE, RESUME, CLOSE are ignored

    sla_limit = 14_400_000
    result = []

    for tid in sorted(tickets.keys()):
        t = tickets[tid]
        used = t["used_ms"]
        if t["state"] == "RUNNING":
            used += now - t["running_start"]

        result.append(
            {
                "ticket_id": tid,
                "used_ms": used,
                "breached": used > sla_limit,
                "status": "closed" if t["state"] == "CLOSED" else "open",
            }
        )

    return result