"""Support-ticket SLA clock implementation."""

NOT_OPENED = 0
RUNNING = 1
PAUSED = 2
CLOSED = 3

VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}
SLA_LIMIT = 14_400_000


class _Ticket:
    __slots__ = ("ticket_id", "state", "used_ms", "running_start", "had_valid_open")

    def __init__(self, ticket_id: str):
        self.ticket_id = ticket_id
        self.state = NOT_OPENED
        self.used_ms = 0
        self.running_start = 0
        self.had_valid_open = False


def compute_sla(stream):
    """Compute SLA metrics for tickets from an event stream."""
    well_formed_events = []

    idx = 0
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
        if event not in VALID_EVENTS:
            continue

        well_formed_events.append((int(ts_str), idx, ticket_id, event))
        idx += 1

    if not well_formed_events:
        return []

    # Sort events by timestamp ascending; tie-break on stream arrival order (stable sort)
    well_formed_events.sort(key=lambda x: (x[0], x[1]))

    now = well_formed_events[-1][0]

    tickets = {}
    for ts, _, ticket_id, event in well_formed_events:
        if ticket_id not in tickets:
            tickets[ticket_id] = _Ticket(ticket_id)
        ticket = tickets[ticket_id]

        if event == "OPEN":
            if ticket.state == NOT_OPENED or ticket.state == CLOSED:
                ticket.state = RUNNING
                ticket.used_ms = 0
                ticket.running_start = ts
                ticket.had_valid_open = True
        elif event == "PAUSE":
            if ticket.state == RUNNING:
                ticket.used_ms += ts - ticket.running_start
                ticket.state = PAUSED
        elif event == "RESUME":
            if ticket.state == PAUSED:
                ticket.state = RUNNING
                ticket.running_start = ts
        elif event == "CLOSE":
            if ticket.state == RUNNING:
                ticket.used_ms += ts - ticket.running_start
                ticket.state = CLOSED
            elif ticket.state == PAUSED:
                ticket.state = CLOSED
        elif event == "REOPEN":
            if ticket.state == CLOSED:
                ticket.state = RUNNING
                ticket.running_start = ts

    results = []
    for ticket in tickets.values():
        if not ticket.had_valid_open:
            continue

        if ticket.state == RUNNING:
            final_used = ticket.used_ms + (now - ticket.running_start)
            status = "open"
        elif ticket.state == PAUSED:
            final_used = ticket.used_ms
            status = "open"
        elif ticket.state == CLOSED:
            final_used = ticket.used_ms
            status = "closed"
        else:
            continue

        results.append(
            {
                "ticket_id": ticket.ticket_id,
                "used_ms": final_used,
                "breached": final_used > SLA_LIMIT,
                "status": status,
            }
        )

    results.sort(key=lambda x: x["ticket_id"])
    return results