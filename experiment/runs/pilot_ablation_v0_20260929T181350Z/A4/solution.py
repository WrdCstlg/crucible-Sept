import csv
from typing import Any, Dict, Iterable, List, Optional


def compute_sla(stream: Iterable[str]) -> List[Dict[str, Any]]:
    SLA_LIMIT_MS = 14_400_000
    VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}

    raw_events = []
    now: Optional[int] = None

    for arrival_idx, line in enumerate(stream):
        if not isinstance(line, str):
            continue
        stripped = line.strip()
        if not stripped:
            continue

        try:
            parsed_rows = list(csv.reader([stripped]))
        except Exception:
            continue

        if not parsed_rows or len(parsed_rows[0]) != 3:
            continue

        row = [field.strip() for field in parsed_rows[0]]
        ts_str, ticket_id, event = row

        if not ticket_id:
            continue

        try:
            ts = int(ts_str)
            if ts < 0:
                continue
        except ValueError:
            continue

        if now is None or ts > now:
            now = ts

        if event in VALID_EVENTS:
            raw_events.append((ts, arrival_idx, ticket_id, event))

    if now is None or not raw_events:
        return []

    # Sort events by timestamp_ms; ties broken by arrival order (stable sort)
    raw_events.sort(key=lambda x: (x[0], x[1]))

    # Ticket tracking: ticket_id -> state dict
    # state can be: "RUNNING", "PAUSED", "CLOSED"
    tickets: Dict[str, Dict[str, Any]] = {}

    for ts, _, ticket_id, event in raw_events:
        if ticket_id not in tickets:
            if event == "OPEN":
                tickets[ticket_id] = {
                    "has_valid_open": True,
                    "state": "RUNNING",
                    "used_ms": 0,
                    "last_start": ts,
                }
            # All other events before first valid OPEN are silently ignored
            continue

        t_data = tickets[ticket_id]
        state = t_data["state"]

        if event == "OPEN":
            # OPEN when already open or closed is ignored
            continue
        elif event == "PAUSE":
            if state == "RUNNING":
                t_data["used_ms"] += ts - t_data["last_start"]
                t_data["state"] = "PAUSED"
            # PAUSE when already paused or closed is ignored
        elif event == "RESUME":
            if state == "PAUSED":
                t_data["last_start"] = ts
                t_data["state"] = "RUNNING"
            # RESUME when clock is running or ticket closed is ignored
        elif event == "CLOSE":
            if state == "RUNNING":
                t_data["used_ms"] += ts - t_data["last_start"]
                t_data["state"] = "CLOSED"
            elif state == "PAUSED":
                t_data["state"] = "CLOSED"
            # CLOSE when already closed is ignored
        elif event == "REOPEN":
            if state == "CLOSED":
                t_data["last_start"] = ts
                t_data["state"] = "RUNNING"
            # REOPEN when not closed is ignored

    results = []
    for ticket_id, t_data in tickets.items():
        if not t_data["has_valid_open"]:
            continue

        state = t_data["state"]
        used_ms = t_data["used_ms"]

        if state == "RUNNING":
            used_ms += now - t_data["last_start"]
            status = "open"
        elif state == "PAUSED":
            status = "open"
        else:  # CLOSED
            status = "closed"

        breached = used_ms > SLA_LIMIT_MS

        results.append({
            "ticket_id": ticket_id,
            "used_ms": used_ms,
            "breached": breached,
            "status": status,
        })

    results.sort(key=lambda x: str(x["ticket_id"]))
    return results