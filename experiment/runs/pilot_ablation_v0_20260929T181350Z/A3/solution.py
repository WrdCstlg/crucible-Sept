import csv
from typing import Any, Dict, Iterable, List, Optional


def compute_sla(stream: Iterable[str]) -> List[Dict[str, Any]]:
    SLA_LIMIT_MS = 14_400_000
    VALID_EVENTS = {"OPEN", "PAUSE", "RESUME", "CLOSE", "REOPEN"}

    now: Optional[int] = None
    events = []

    for arrival_idx, raw_line in enumerate(stream):
        if isinstance(raw_line, bytes):
            try:
                line = raw_line.decode("utf-8", errors="ignore")
            except Exception:
                continue
        elif isinstance(raw_line, str):
            line = raw_line
        else:
            continue

        stripped = line.strip()
        if not stripped:
            continue

        # Extract timestamp for "now" (including lines that are otherwise invalid)
        ts_for_now = None
        try:
            row = next(csv.reader([stripped]))
            if row:
                candidate = int(row[0].strip())
                if candidate >= 0:
                    ts_for_now = candidate
        except Exception:
            pass

        if ts_for_now is None:
            try:
                first_part = stripped.split(",")[0].strip().strip("\"'")
                candidate = int(first_part)
                if candidate >= 0:
                    ts_for_now = candidate
            except Exception:
                pass

        if ts_for_now is not None:
            if now is None or ts_for_now > now:
                now = ts_for_now

        # Parse event line
        try:
            row = next(csv.reader([stripped]))
        except Exception:
            continue

        if len(row) != 3:
            continue

        ts_str, ticket_id, event = [field.strip() for field in row]

        try:
            ts = int(ts_str)
            if ts < 0:
                continue
        except ValueError:
            continue

        if not ticket_id:
            continue

        if event not in VALID_EVENTS:
            continue

        events.append((ts, arrival_idx, ticket_id, event))

    # Sort events by timestamp_ms; ties are broken by original arrival order (stable sort)
    events.sort(key=lambda x: (x[0], x[1]))

    # Track ticket states
    tickets: Dict[str, Dict[str, Any]] = {}

    for ts, _, ticket_id, event in events:
        if ticket_id not in tickets:
            if event != "OPEN":
                # Silently ignore any event before the first valid OPEN
                continue
            # First valid OPEN
            tickets[ticket_id] = {
                "ticket_id": ticket_id,
                "status": "open",
                "is_running": True,
                "clock_start_ms": ts,
                "used_ms": 0,
            }
            continue

        t = tickets[ticket_id]

        if event == "OPEN":
            # "OPEN when already open" is invalid; if closed, only REOPEN puts it back in service.
            continue
        elif event == "PAUSE":
            if t["status"] == "open" and t["is_running"]:
                t["used_ms"] += ts - t["clock_start_ms"]
                t["is_running"] = False
        elif event == "RESUME":
            if t["status"] == "open" and not t["is_running"]:
                t["clock_start_ms"] = ts
                t["is_running"] = True
        elif event == "CLOSE":
            if t["status"] == "open":
                if t["is_running"]:
                    t["used_ms"] += ts - t["clock_start_ms"]
                    t["is_running"] = False
                t["status"] = "closed"
        elif event == "REOPEN":
            if t["status"] == "closed":
                t["status"] = "open"
                t["is_running"] = True
                t["clock_start_ms"] = ts

    # Build results
    results = []
    effective_now = now if now is not None else 0

    for ticket_id, t in tickets.items():
        used_ms = t["used_ms"]
        if t["status"] == "open" and t["is_running"]:
            used_ms += effective_now - t["clock_start_ms"]

        breached = used_ms > SLA_LIMIT_MS

        results.append({
            "ticket_id": ticket_id,
            "used_ms": used_ms,
            "breached": breached,
            "status": t["status"],
        })

    # Sort results by ticket_id ascending (string order)
    results.sort(key=lambda d: d["ticket_id"])
    return results