"""Support-ticket SLA clock calculation module."""

from collections import defaultdict


SLA_LIMIT_MS = 14_400_000
VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}


class TicketState:
    NOT_OPENED = "NOT_OPENED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"


def _parse_record(line):
    """Validate and parse a single stream record.

    A line is well-formed only if, after trimming surrounding whitespace,
    it splits on commas into exactly 3 fields, and, after trimming each field:
    - the timestamp consists only of ASCII digits 0-9;
    - the ticket ID is non-empty;
    - the event is exactly one of OPEN, PAUSE, RESUME, CLOSE, REOPEN (uppercase).

    Returns (ts_ms, ticket_id, event) if well-formed, else None.
    """
    if not isinstance(line, str):
        return None

    trimmed_line = line.strip()
    if not trimmed_line:
        return None

    parts = trimmed_line.split(",")
    if len(parts) != 3:
        return None

    raw_ts = parts[0].strip()
    ticket_id = parts[1].strip()
    event = parts[2].strip()

    if not raw_ts or not all("0" <= c <= "9" for c in raw_ts):
        return None

    if not ticket_id:
        return None

    if event not in VALID_EVENTS:
        return None

    return int(raw_ts), ticket_id, event


def _rebuild_ticket_intervals(events, now):
    """Rebuild the running time intervals for a single ticket.

    Processes chronological events according to the ticket lifecycle state table.
    Returns (intervals, final_state, ever_opened).
    """
    state = TicketState.NOT_OPENED
    ever_opened = False
    intervals = []
    run_start = None

    for ts, event in events:
        if event == "OPEN":
            if state == TicketState.NOT_OPENED:
                state = TicketState.RUNNING
                ever_opened = True
                run_start = ts
                intervals = []
            elif state == TicketState.CLOSED:
                state = TicketState.RUNNING
                ever_opened = True
                run_start = ts
                intervals = []  # used time resets to 0
            # RUNNING or PAUSED: ignored

        elif event == "PAUSE":
            if state == TicketState.RUNNING:
                intervals.append((run_start, ts))
                run_start = None
                state = TicketState.PAUSED
            # NOT_OPENED, PAUSED, CLOSED: ignored

        elif event == "RESUME":
            if state == TicketState.PAUSED:
                state = TicketState.RUNNING
                run_start = ts
            # NOT_OPENED, RUNNING, CLOSED: ignored

        elif event == "CLOSE":
            if state == TicketState.RUNNING:
                intervals.append((run_start, ts))
                run_start = None
                state = TicketState.CLOSED
            elif state == TicketState.PAUSED:
                state = TicketState.CLOSED
            # NOT_OPENED, CLOSED: ignored

        elif event == "REOPEN":
            if state == TicketState.CLOSED:
                state = TicketState.RUNNING
                run_start = ts
                # used time continues from its total (intervals preserved)
            # NOT_OPENED, RUNNING, PAUSED: ignored

    # End-of-stream interval completion
    if state == TicketState.RUNNING:
        intervals.append((run_start, now))
        run_start = None

    return intervals, state, ever_opened


def compute_sla(stream):
    """Compute SLA metrics for all tickets that had at least one valid OPEN."""
    well_formed_events = []

    # Ingestion stage: strict boundary validation drops malformed records
    for original_idx, line in enumerate(stream):
        parsed = _parse_record(line)
        if parsed is not None:
            ts, ticket_id, event = parsed
            well_formed_events.append((ts, original_idx, ticket_id, event))

    if not well_formed_events:
        return []

    # "Now" is the largest timestamp among all well-formed lines
    now = max(record[0] for record in well_formed_events)

    # Stable sort: order by timestamp ascending; ties preserve original order
    well_formed_events.sort(key=lambda record: (record[0], record[1]))

    # Group events by ticket ID while preserving stable chronological order
    ticket_events = defaultdict(list)
    for ts, _idx, ticket_id, event in well_formed_events:
        ticket_events[ticket_id].append((ts, event))

    results = []

    # Domain stage: rebuild running intervals per ticket, then sum them
    for ticket_id, events in ticket_events.items():
        intervals, final_state, ever_opened = _rebuild_ticket_intervals(events, now)

        if not ever_opened:
            continue

        used_ms = sum(end - start for start, end in intervals)
        breached = used_ms > SLA_LIMIT_MS
        status = "closed" if final_state == TicketState.CLOSED else "open"

        results.append({
            "ticket_id": ticket_id,
            "used_ms": used_ms,
            "breached": breached,
            "status": status,
        })

    # Output sorted by ticket_id ascending (Python default code-point order)
    results.sort(key=lambda item: item["ticket_id"])
    return results