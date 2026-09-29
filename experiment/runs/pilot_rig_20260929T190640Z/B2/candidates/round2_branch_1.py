"""Support-ticket SLA clock calculation module."""


class TicketStateMachine:
    """Per-ticket state machine updated event by event."""

    NOT_OPENED = "NOT_OPENED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"

    def __init__(self, ticket_id: str):
        self.ticket_id = ticket_id
        self.state = self.NOT_OPENED
        self.used_ms = 0
        self.last_running_start = 0
        self.had_valid_open = False

    def process_event(self, event: str, timestamp: int) -> None:
        """Apply an event to the ticket state machine according to transition rules."""
        if self.state == self.NOT_OPENED:
            if event == "OPEN":
                self.state = self.RUNNING
                self.used_ms = 0
                self.last_running_start = timestamp
                self.had_valid_open = True
            # PAUSE, RESUME, CLOSE, REOPEN are ignored

        elif self.state == self.RUNNING:
            if event == "PAUSE":
                self.used_ms += timestamp - self.last_running_start
                self.state = self.PAUSED
            elif event == "CLOSE":
                self.used_ms += timestamp - self.last_running_start
                self.state = self.CLOSED
            # OPEN, RESUME, REOPEN are ignored

        elif self.state == self.PAUSED:
            if event == "RESUME":
                self.state = self.RUNNING
                self.last_running_start = timestamp
            elif event == "CLOSE":
                self.state = self.CLOSED
            # OPEN, PAUSE, REOPEN are ignored

        elif self.state == self.CLOSED:
            if event == "OPEN":
                self.state = self.RUNNING
                self.used_ms = 0
                self.last_running_start = timestamp
                self.had_valid_open = True
            elif event == "REOPEN":
                self.state = self.RUNNING
                self.last_running_start = timestamp
                # used_ms continues from its accumulated total
            # PAUSE, RESUME, CLOSE are ignored

    def finalize(self, now: int) -> dict:
        """Compute the final SLA metrics for the ticket up to 'now'."""
        total_used = self.used_ms
        if self.state == self.RUNNING:
            total_used += now - self.last_running_start

        return {
            "ticket_id": self.ticket_id,
            "used_ms": total_used,
            "breached": total_used > 14_400_000,
            "status": "closed" if self.state == self.CLOSED else "open",
        }


def _parse_line(line):
    """Validate and parse a line. Returns (timestamp, ticket_id, event) or None if malformed."""
    if not isinstance(line, str):
        return None

    stripped = line.strip()
    fields = stripped.split(",")
    if len(fields) != 3:
        return None

    f_ts = fields[0].strip()
    f_ticket = fields[1].strip()
    f_event = fields[2].strip()

    if not f_ts or not all("0" <= ch <= "9" for ch in f_ts):
        return None
    if not f_ticket:
        return None
    if f_event not in {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}:
        return None

    return int(f_ts, 10), f_ticket, f_event


def compute_sla(stream):
    """Compute SLA clock metrics for all tickets in the given stream."""
    well_formed_events = []
    for idx, line in enumerate(stream):
        parsed = _parse_line(line)
        if parsed is not None:
            ts, ticket_id, event = parsed
            well_formed_events.append((ts, idx, ticket_id, event))

    if not well_formed_events:
        return []

    # 'Now' is the largest timestamp among all well-formed lines
    now = max(ev[0] for ev in well_formed_events)

    # Process events in order of timestamp; equal timestamps preserve stream order (stable sort)
    well_formed_events.sort(key=lambda ev: (ev[0], ev[1]))

    # Per-ticket state machines updated event by event
    ticket_machines = {}
    for ts, _idx, ticket_id, event in well_formed_events:
        if ticket_id not in ticket_machines:
            ticket_machines[ticket_id] = TicketStateMachine(ticket_id)
        ticket_machines[ticket_id].process_event(event, ts)

    # Collect and format results for tickets that had at least one valid OPEN
    results = [
        machine.finalize(now)
        for machine in ticket_machines.values()
        if machine.had_valid_open
    ]

    # Sort tickets in ascending code-point order
    results.sort(key=lambda item: item["ticket_id"])
    return results