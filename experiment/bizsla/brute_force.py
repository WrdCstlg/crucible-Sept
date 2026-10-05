"""Brute-force oracle for experiment/bizsla/SPEC.md: simulates every minute from the first event to "now".

Written to mirror the spec sentence by sentence, not to be fast: O((now - first) x tickets). Used only on small
spans, to check the efficient reference (reference.py) by differential fuzzing. Never shown to any model.
"""
import re

DIGITS = re.compile(r"[0-9]+")
LIMITS = {"P1": 240, "P2": 480, "P3": 1440, "P4": 2400}
EVENTS3 = {"PAUSE", "RESUME", "CLOSE", "REOPEN", "HOLIDAY"}
EVENTS4 = {"OPEN", "PRIORITY"}


def parse(line):
    if not isinstance(line, str):
        return None
    fields = [f.strip() for f in line.strip().split(",")]
    if len(fields) not in (3, 4):
        return None
    minute, tid, event = fields[0], fields[1], fields[2]
    if not DIGITS.fullmatch(minute) or not tid:
        return None
    if event in EVENTS4:
        if len(fields) != 4 or fields[3] not in LIMITS:
            return None
        arg = fields[3]
    elif event in EVENTS3:
        if len(fields) != 3:
            return None
        arg = None
    else:
        return None
    if (event == "HOLIDAY") != (tid == "*"):
        return None
    return int(minute), tid, event, arg


def is_business(m, holidays):
    day = m // 1440
    return day % 7 < 5 and 540 <= m % 1440 < 1020 and day not in holidays


def compute_sla(stream):
    holidays, events = set(), []
    for line in stream:
        p = parse(line)
        if p is None:
            continue
        if p[2] == "HOLIDAY":
            holidays.add(p[0] // 1440)
        else:
            events.append(p)
    if not events:
        return []
    now = max(e[0] for e in events)
    by_minute = {}
    for e in events:                       # insertion order = stream order: a stable sort per minute
        by_minute.setdefault(e[0], []).append(e)
    tickets = {}                           # tid -> dict(state, prio, used, breached_at, opened)
    for t in range(min(by_minute), now + 1):
        for _, tid, ev, arg in by_minute.get(t, []):
            k = tickets.setdefault(tid, {"state": "NOT_OPENED", "prio": None, "used": 0, "breached_at": None,
                                         "opened": False})
            s = k["state"]
            if ev == "OPEN" and s in ("NOT_OPENED", "CLOSED"):
                k.update(state="RUNNING", prio=arg, used=0, breached_at=None, opened=True)
            elif ev == "PRIORITY" and s in ("RUNNING", "PAUSED"):
                k["prio"] = arg
            elif ev == "PAUSE" and s == "RUNNING":
                k["state"] = "PAUSED"
            elif ev == "RESUME" and s == "PAUSED":
                k["state"] = "RUNNING"
            elif ev == "CLOSE" and s in ("RUNNING", "PAUSED"):
                k["state"] = "CLOSED"
            elif ev == "REOPEN" and s == "CLOSED":
                k["state"] = "RUNNING"
        for k in tickets.values():         # check minute t after its events
            if k["opened"] and k["breached_at"] is None and k["used"] > LIMITS[k["prio"]]:
                k["breached_at"] = t
        if t < now and is_business(t, holidays):
            for k in tickets.values():     # minute t counts towards used time at t + 1
                if k["state"] == "RUNNING":
                    k["used"] += 1
    status = {"RUNNING": "running", "PAUSED": "paused", "CLOSED": "closed"}
    return [{"ticket_id": tid, "priority": k["prio"], "used_minutes": k["used"],
             "breached": k["breached_at"] is not None, "breached_at": k["breached_at"], "status": status[k["state"]]}
            for tid, k in sorted(tickets.items()) if k["opened"]]
