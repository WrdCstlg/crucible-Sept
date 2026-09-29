import csv
from typing import Any, Dict, Iterable, List, Optional, Tuple


def compute_sla(stream: Iterable[str]) -> List[Dict[str, Any]]:
    SLA_LIMIT_MS = 14_400_000
    VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}

    now: Optional[int] = None
    parsed_events: List[Tuple[int, int, str, str]] = []

    for arrival_idx, line in enumerate(stream):
        if not isinstance(line, str):
            continue
        line_str = line.strip()
        if not line_str:
            continue

        try:
            reader = csv.reader([line_str])
            row = next(reader)
        except Exception:
            continue

        if len(row) != 3:
            continue

        ts_raw, ticket_id, event = row[0].strip(), row[1].strip(), row[2].strip()

        try:
            ts = int(ts_raw)
            if ts < 0:
                continue
        except ValueError:
            continue

        # "Now" is defined as the maximum timestamp_ms appearing anywhere in the stream
        # (including lines that are otherwise invalid).
        if now is None or ts > now:
            now = ts

        if not ticket_id:
            continue

        if event not in VALID_EVENTS:
            continue

        parsed_events.append((ts, arrival_idx, ticket_id, event))

    # Sort all events by timestamp_ms; ties are broken by original arrival order (stable sort).
    parsed_events.sort(key=lambda x: (x[0], x[1]))

    # Track lifecycle state and running time intervals per ticket
    ticket_state: Dict[str, str] = {}
    ticket_intervals: Dict[str, List[Tuple[int, int]]] = {}
    current_run_start: Dict[str, int] = {}
    had_valid_open: set = set()

    for ts, _, ticket_id, event in parsed_events:
        state = ticket_state.get(ticket_id, "unopened")

        if state == "unopened":
            if event == "OPEN":
                had_valid_open.add(ticket_id)
                ticket_state[ticket_id] = "running"
                current_run_start[ticket_id] = ts
                ticket_intervals[ticket_id] = []
            # Any event before first valid OPEN is silently ignored
        elif state == "running":
            if event == "PAUSE":
                ticket_intervals[ticket_id].append((current_run_start[ticket_id], ts))
                ticket_state[ticket_id] = "paused"
            elif event == "CLOSE":
                ticket_intervals[ticket_id].append((current_run_start[ticket_id], ts))
                ticket_state[ticket_id] = "closed"
            # OPEN when already open, RESUME when running, REOPEN when not closed -> ignored
        elif state == "paused":
            if event == "RESUME":
                ticket_state[ticket_id] = "running"
                current_run_start[ticket_id] = ts
            elif event == "CLOSE":
                ticket_state[ticket_id] = "closed"
            # OPEN when already open, PAUSE when already paused, REOPEN when not closed -> ignored
        elif state == "closed":
            if event == "REOPEN":
                ticket_state[ticket_id] = "running"
                current_run_start[ticket_id] = ts
            # CLOSE when already closed, OPEN/PAUSE/RESUME when closed -> ignored

    # For tickets still open when the stream ends:
    # If the clock is running, count up to now; if paused, it counts only up to the pause.
    if now is not None:
        for ticket_id in had_valid_open:
            if ticket_state[ticket_id] == "running":
                ticket_intervals[ticket_id].append((current_run_start[ticket_id], now))

    # Rebuild each ticket's running time intervals, then sum them
    results: List[Dict[str, Any]] = []
    for ticket_id in sorted(had_valid_open):
        intervals = ticket_intervals[ticket_id]
        used_ms = sum(end - start for start, end in intervals)
        breached = used_ms > SLA_LIMIT_MS
        status = "closed" if ticket_state[ticket_id] == "closed" else "open"

        results.append({
            "ticket_id": ticket_id,
            "used_ms": used_ms,
            "breached": breached,
            "status": status,
        })

    return results