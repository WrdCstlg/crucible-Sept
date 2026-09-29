import csv
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional


class TicketState(Enum):
    UNOPENED = "UNOPENED"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    CLOSED = "CLOSED"


SLA_LIMIT_MS = 14_400_000


class TicketStateMachine:
    """State machine tracking elapsed SLA time and status for a single ticket."""

    def __init__(self, ticket_id: str) -> None:
        self.ticket_id = ticket_id
        self.state = TicketState.UNOPENED
        self.used_ms = 0
        self.last_start_ms = 0
        self.had_valid_open = False

    def process_event(self, event_type: str, timestamp_ms: int) -> None:
        """Update ticket state machine event by event, ignoring invalid events."""
        if self.state == TicketState.UNOPENED:
            if event_type == "OPEN":
                self.state = TicketState.RUNNING
                self.last_start_ms = timestamp_ms
                self.had_valid_open = True
            # Any other event before first valid OPEN is silently ignored

        elif self.state == TicketState.RUNNING:
            if event_type == "PAUSE":
                self.used_ms += timestamp_ms - self.last_start_ms
                self.state = TicketState.PAUSED
            elif event_type == "CLOSE":
                self.used_ms += timestamp_ms - self.last_start_ms
                self.state = TicketState.CLOSED
            # OPEN (already open), RESUME (already running), REOPEN (not closed) ignored

        elif self.state == TicketState.PAUSED:
            if event_type == "RESUME":
                self.last_start_ms = timestamp_ms
                self.state = TicketState.RUNNING
            elif event_type == "CLOSE":
                # Clock was already stopped at pause; stretch does not count
                self.state = TicketState.CLOSED
            # OPEN (already open), PAUSE (already paused), REOPEN (not closed) ignored

        elif self.state == TicketState.CLOSED:
            if event_type == "REOPEN":
                self.last_start_ms = timestamp_ms
                self.state = TicketState.RUNNING
            # OPEN, PAUSE, RESUME, CLOSE (already closed) ignored

    def finalize(self, now: int) -> Dict[str, Any]:
        """Compute final used time and SLA breach status at the current 'now' timestamp."""
        total_used = self.used_ms
        if self.state == TicketState.RUNNING:
            total_used += now - self.last_start_ms
            status = "open"
        elif self.state == TicketState.PAUSED:
            status = "open"
        else:  # CLOSED
            status = "closed"

        return {
            "ticket_id": self.ticket_id,
            "used_ms": total_used,
            "breached": total_used > SLA_LIMIT_MS,
            "status": status,
        }


def _parse_timestamp(val_str: str) -> Optional[int]:
    """Parse a non-negative integer of whole milliseconds, or return None."""
    s = val_str.strip()
    try:
        val = int(s)
        if val >= 0:
            return val
    except (ValueError, TypeError):
        pass
    return None


def compute_sla(stream: Iterable[str]) -> List[Dict[str, Any]]:
    """Compute SLA clock metrics for tickets in stream using a per-ticket state machine."""
    max_now: Optional[int] = None
    raw_events: List[tuple] = []
    valid_event_types = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}

    for arrival_order, raw_line in enumerate(stream):
        if isinstance(raw_line, bytes):
            try:
                line_str = raw_line.decode("utf-8", errors="replace")
            except Exception:
                continue
        elif isinstance(raw_line, str):
            line_str = raw_line
        else:
            continue

        line_str = line_str.strip()
        if not line_str:
            continue

        try:
            parsed_rows = list(csv.reader([line_str]))
            if not parsed_rows or not parsed_rows[0]:
                continue
            fields = [f.strip() for f in parsed_rows[0]]
        except Exception:
            fields = [f.strip() for f in line_str.split(",")]

        if not fields:
            continue

        # "Now" is the maximum timestamp_ms appearing anywhere in the stream
        # (including lines that are otherwise invalid).
        ts = _parse_timestamp(fields[0])
        if ts is not None:
            if max_now is None or ts > max_now:
                max_now = ts

        # Validate line structure for event processing
        if len(fields) != 3 or ts is None:
            continue

        ticket_id = fields[1]
        event_type = fields[2]

        if not ticket_id or event_type not in valid_event_types:
            continue

        raw_events.append((ts, arrival_order, ticket_id, event_type))

    # If stream yielded no valid timestamp anywhere, no tickets had a valid OPEN
    if max_now is None:
        return []

    # Sort all events by timestamp_ms; ties are broken by original arrival order (stable sort)
    raw_events.sort(key=lambda item: (item[0], item[1]))

    # Per-ticket state machine updated event by event
    ticket_machines: Dict[str, TicketStateMachine] = {}

    for ts, _, ticket_id, event_type in raw_events:
        if ticket_id not in ticket_machines:
            ticket_machines[ticket_id] = TicketStateMachine(ticket_id)
        ticket_machines[ticket_id].process_event(event_type, ts)

    # Return output for every ticket that had at least one valid OPEN, sorted by ticket_id ascending
    results = [
        sm.finalize(max_now)
        for sm in ticket_machines.values()
        if sm.had_valid_open
    ]
    results.sort(key=lambda r: r["ticket_id"])
    return results