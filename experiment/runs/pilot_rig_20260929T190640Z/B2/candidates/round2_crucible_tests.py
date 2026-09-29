import solution
import sys

# Test runner infrastructure
passed = 0
failed = 0


def run_test(name, stream, expected):
    global passed, failed
    try:
        actual = solution.compute_sla(stream)

        # Check return type
        if not isinstance(actual, list):
            raise AssertionError(f"Expected list, got {type(actual)}")

        # Check length
        if len(actual) != len(expected):
            raise AssertionError(
                f"Expected {len(expected)} items, got {len(actual)}.\n"
                f"Actual:   {actual}\n"
                f"Expected: {expected}"
            )

        # Check each item
        for i, (act, exp) in enumerate(zip(actual, expected)):
            if not isinstance(act, dict):
                raise AssertionError(f"Item {i} is not a dict: {type(act)}")

            expected_keys = {"ticket_id", "used_ms", "breached", "status"}
            if set(act.keys()) != expected_keys:
                raise AssertionError(
                    f"Item {i} keys mismatch. Expected {expected_keys}, got {set(act.keys())}"
                )

            # Strict type checking
            if type(act["ticket_id"]) is not str:
                raise AssertionError(
                    f"Item {i} 'ticket_id' must be str, got {type(act['ticket_id'])}"
                )
            if type(act["used_ms"]) is not int:
                raise AssertionError(
                    f"Item {i} 'used_ms' must be int, got {type(act['used_ms'])}"
                )
            if type(act["breached"]) is not bool:
                raise AssertionError(
                    f"Item {i} 'breached' must be bool, got {type(act['breached'])}"
                )
            if type(act["status"]) is not str:
                raise AssertionError(
                    f"Item {i} 'status' must be str, got {type(act['status'])}"
                )

            if act != exp:
                raise AssertionError(
                    f"Item {i} mismatch.\n"
                    f"Actual:   {act}\n"
                    f"Expected: {exp}"
                )

        passed += 1
    except Exception as e:
        print(f"FAIL: {name}")
        print(f"      {e}")
        failed += 1


# ----------------------------------------------------------------------
# 1. Spec Format Example & Empty Streams
# ----------------------------------------------------------------------
run_test(
    "Spec format example",
    ["100,A,OPEN", "400,A,CLOSE"],
    [{"ticket_id": "A", "used_ms": 300, "breached": False, "status": "closed"}],
)

run_test("Empty stream", [], [])

run_test(
    "Stream of empty and blank whitespace lines",
    ["", "   ", "\t\t", "\n", " \r\n "],
    [],
)

run_test(
    "Generator input stream (iterable support)",
    (line for line in ["100,A,OPEN", "200,A,CLOSE"]),
    [{"ticket_id": "A", "used_ms": 100, "breached": False, "status": "closed"}],
)

# ----------------------------------------------------------------------
# 2. Malformed Line Handling
# ----------------------------------------------------------------------
# Malformed lines must be completely ignored and NOT affect "now".
run_test(
    "Malformed lines ignored and do not affect 'now'",
    [
        "100,A,OPEN",
        # Wrong field counts
        "200",
        "200,A",
        "200,A,OPEN,EXTRA",
        ",,",
        " , , ",
        # Non-digit timestamps
        "-100,A,CLOSE",
        "+500,A,CLOSE",
        "500.0,A,CLOSE",
        "1e5,A,CLOSE",
        "five,A,CLOSE",
        ",A,CLOSE",
        " 5 00 ,A,CLOSE",
        "500a,A,CLOSE",
        # Non-ASCII digits (e.g. Arabic-Indic digits)
        "١٢٣,A,CLOSE",
        "100\u0660,A,CLOSE",
        # Empty ticket ID
        "500,,CLOSE",
        "500,   ,CLOSE",
        # Invalid / lowercase / mixed-case events
        "500,A,open",
        "500,A,Open",
        "500,A,START",
        "500,A,STOP",
        "500,A,CLOSE ",  # wait, trimmed event is CLOSE, so that WOULD be valid if line valid
        "500,A,CL OSE",  # internal space makes it invalid
        "999999999,A,INVALID_EVENT",
    ],
    # 'now' remains 100 because all subsequent lines are malformed.
    # A opened at 100, RUNNING until now (100) -> 0 ms used.
    [{"ticket_id": "A", "used_ms": 0, "breached": False, "status": "open"}],
)

# Valid trimming around lines and fields
run_test(
    "Valid whitespace trimming around line and fields",
    [
        "  00100  ,  A  ,  OPEN  ",
        "\t00400\t,\tA\t,\tCLOSE\t\r\n",
    ],
    [{"ticket_id": "A", "used_ms": 300, "breached": False, "status": "closed"}],
)

# ----------------------------------------------------------------------
# 3. Definition of "Now"
# ----------------------------------------------------------------------
# "Now" is the largest timestamp among ALL well-formed lines,
# including well-formed lines that represent ignored transitions.
run_test(
    "Now is max timestamp including ignored transitions",
    [
        "100,A,OPEN",
        "500,B,PAUSE",  # B not opened -> PAUSE ignored, but well-formed: advances 'now' to 500
    ],
    # A opened at 100, still RUNNING at now=500 -> used_ms = 400. B never opened -> omitted.
    [{"ticket_id": "A", "used_ms": 400, "breached": False, "status": "open"}],
)

run_test(
    "Now is max timestamp even if arriving early in stream",
    [
        "1000,IGNORED_TICKET,CLOSE",  # Ignored transition, sets now to 1000
        "100,A,OPEN",
        "200,A,PAUSE",  # Paused at 200, used_ms = 100
        "300,B,OPEN",   # Running from 300 to now=1000 -> used_ms = 700
    ],
    [
        {"ticket_id": "A", "used_ms": 100, "breached": False, "status": "open"},
        {"ticket_id": "B", "used_ms": 700, "breached": False, "status": "open"},
    ],
)

# ----------------------------------------------------------------------
# 4. State Transition Table: All 20 cells
# ----------------------------------------------------------------------
# NOT_OPENED:
#   OPEN   -> to RUNNING, used starts at 0
#   PAUSE  -> ignored
#   RESUME -> ignored
#   CLOSE  -> ignored
#   REOPEN -> ignored
run_test(
    "Transitions from NOT_OPENED",
    [
        "10,T,PAUSE",   # ignored
        "20,T,RESUME",  # ignored
        "30,T,CLOSE",   # ignored
        "40,T,REOPEN",  # ignored
        "100,T,OPEN",   # transitions to RUNNING at 100
        "300,T,CLOSE",  # to CLOSED at 300
    ],
    [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}],
)

# Tickets that NEVER had a valid OPEN must be omitted
run_test(
    "Tickets that never had a valid OPEN are omitted",
    [
        "10,T1,PAUSE",
        "20,T1,RESUME",
        "30,T1,CLOSE",
        "40,T1,REOPEN",
        "100,T2,OPEN",
        "200,T2,CLOSE",
    ],
    [{"ticket_id": "T2", "used_ms": 100, "breached": False, "status": "closed"}],
)

# RUNNING:
#   OPEN   -> ignored
#   PAUSE  -> to PAUSED
#   RESUME -> ignored
#   CLOSE  -> to CLOSED
#   REOPEN -> ignored
run_test(
    "Transitions from RUNNING: ignored OPEN, RESUME, REOPEN",
    [
        "100,T,OPEN",    # to RUNNING (start=100)
        "150,T,OPEN",    # ignored: still RUNNING from 100
        "200,T,RESUME",  # ignored: still RUNNING from 100
        "250,T,REOPEN",  # ignored: still RUNNING from 100
        "400,T,CLOSE",   # to CLOSED (used = 300)
    ],
    [{"ticket_id": "T", "used_ms": 300, "breached": False, "status": "closed"}],
)

# PAUSED:
#   OPEN   -> ignored
#   PAUSE  -> ignored
#   RESUME -> to RUNNING
#   CLOSE  -> to CLOSED (accumulates 0 additional time)
#   REOPEN -> ignored
run_test(
    "Transitions from PAUSED: ignored OPEN, PAUSE, REOPEN, and PAUSED->RESUME",
    [
        "100,T,OPEN",    # RUNNING (100)
        "200,T,PAUSE",   # PAUSED (used = 100)
        "220,T,OPEN",    # ignored
        "240,T,PAUSE",   # ignored
        "260,T,REOPEN",  # ignored
        "300,T,RESUME",  # to RUNNING (start=300, used=100)
        "500,T,CLOSE",   # to CLOSED (used = 100 + 200 = 300)
    ],
    [{"ticket_id": "T", "used_ms": 300, "breached": False, "status": "closed"}],
)

run_test(
    "Transitions from PAUSED: PAUSED -> CLOSE",
    [
        "100,T,OPEN",    # RUNNING (100)
        "200,T,PAUSE",   # PAUSED (used = 100)
        "500,T,CLOSE",   # to CLOSED directly from PAUSED (used remains 100)
    ],
    [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}],
)

# CLOSED:
#   OPEN   -> to RUNNING, used time RESETS to 0
#   PAUSE  -> ignored
#   RESUME -> ignored
#   CLOSE  -> ignored
#   REOPEN -> to RUNNING, used time CONTINUES from total
run_test(
    "Transitions from CLOSED: ignored PAUSE, RESUME, CLOSE",
    [
        "100,T,OPEN",    # RUNNING
        "200,T,CLOSE",   # CLOSED (used = 100)
        "250,T,PAUSE",   # ignored
        "300,T,RESUME",  # ignored
        "350,T,CLOSE",   # ignored
        "400,T,REOPEN",  # to RUNNING, continues from used=100
        "600,T,CLOSE",   # to CLOSED, used = 100 + 200 = 300
    ],
    [{"ticket_id": "T", "used_ms": 300, "breached": False, "status": "closed"}],
)

run_test(
    "Transitions from CLOSED: OPEN resets used time to 0",
    [
        "100,T,OPEN",    # RUNNING (100)
        "500,T,CLOSE",   # CLOSED (used = 400)
        "600,T,OPEN",    # to RUNNING, resets used time to 0!
        "750,T,CLOSE",   # CLOSED (used = 150)
    ],
    [{"ticket_id": "T", "used_ms": 150, "breached": False, "status": "closed"}],
)

run_test(
    "Transitions from CLOSED: REOPEN continues used time",
    [
        "100,T,OPEN",    # RUNNING (100)
        "500,T,CLOSE",   # CLOSED (used = 400)
        "600,T,REOPEN",  # to RUNNING, continues with used=400
        "750,T,CLOSE",   # CLOSED (used = 400 + 150 = 550)
    ],
    [{"ticket_id": "T", "used_ms": 550, "breached": False, "status": "closed"}],
)

# ----------------------------------------------------------------------
# 5. SLA Boundaries (Limit = 14,400,000 ms)
# ----------------------------------------------------------------------
# "A ticket breaches only if its used time is strictly greater than the limit.
#  Exactly 14,400,000 ms does not breach."
run_test(
    "SLA boundary: 14,399,999 ms does not breach",
    ["0,T,OPEN", "14399999,T,CLOSE"],
    [{"ticket_id": "T", "used_ms": 14399999, "breached": False, "status": "closed"}],
)

run_test(
    "SLA boundary: exactly 14,400,000 ms does not breach",
    ["0,T,OPEN", "14400000,T,CLOSE"],
    [{"ticket_id": "T", "used_ms": 14400000, "breached": False, "status": "closed"}],
)

run_test(
    "SLA boundary: 14,400,001 ms breaches",
    ["0,T,OPEN", "14400001,T,CLOSE"],
    [{"ticket_id": "T", "used_ms": 14400001, "breached": True, "status": "closed"}],
)

run_test(
    "SLA boundary on open tickets: exactly 14,400,000 ms vs 14,400,001 ms at 'now'",
    [
        # T1 opened at 0, runs until now=14400000 -> used_ms = 14400000 -> breached: False
        "0,T1,OPEN",
        "14400000,DUMMY1,OPEN",
        "14400000,DUMMY1,CLOSE",
    ],
    [
        {"ticket_id": "DUMMY1", "used_ms": 0, "breached": False, "status": "closed"},
        {"ticket_id": "T1", "used_ms": 14400000, "breached": False, "status": "open"},
    ],
)

run_test(
    "SLA boundary on open ticket strictly greater than 14,400,000 ms at 'now'",
    [
        # T2 opened at 0, runs until now=14400001 -> used_ms = 14400001 -> breached: True
        "0,T2,OPEN",
        "14400001,DUMMY2,OPEN",
        "14400001,DUMMY2,CLOSE",
    ],
    [
        {"ticket_id": "DUMMY2", "used_ms": 0, "breached": False, "status": "closed"},
        {"ticket_id": "T2", "used_ms": 14400001, "breached": True, "status": "open"},
    ],
)

run_test(
    "SLA reset: ticket breaches, closes, then opens fresh under limit",
    [
        "0,T,OPEN",
        "15000000,T,CLOSE",  # Breached (15M > 14.4M)
        "16000000,T,OPEN",   # Resets to 0
        "16000100,T,CLOSE",  # Closes with used = 100
    ],
    [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}],
)

# ----------------------------------------------------------------------
# 6. Stable Sorting on Equal Timestamps (Ties)
# ----------------------------------------------------------------------
run_test(
    "Stable sort on tie: PAUSE then OPEN at same timestamp",
    [
        # If stable: PAUSE is ignored (NOT_OPENED), then OPEN transitions to RUNNING.
        # If unstable: OPEN happens, then PAUSE pauses it at 100!
        "100,T,PAUSE",
        "100,T,OPEN",
        "300,T,CLOSE",
    ],
    [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}],
)

run_test(
    "Stable sort on tie: OPEN then PAUSE at same timestamp",
    [
        # OPEN to RUNNING, then PAUSE to PAUSED at t=100.
        # Ticket is PAUSED, so it does not accumulate to now=500.
        "100,T,OPEN",
        "100,T,PAUSE",
        "500,DUMMY,OPEN",
        "500,DUMMY,CLOSE",
    ],
    [
        {"ticket_id": "DUMMY", "used_ms": 0, "breached": False, "status": "closed"},
        {"ticket_id": "T", "used_ms": 0, "breached": False, "status": "open"},
    ],
)

run_test(
    "Stable sort on tie: multiple transitions at exact same timestamp",
    [
        "100,T,OPEN",    # RUNNING (100)
        "100,T,CLOSE",   # CLOSED (used=0)
        "100,T,REOPEN",  # RUNNING (100, used=0)
        "250,T,CLOSE",   # CLOSED (used=150)
    ],
    [{"ticket_id": "T", "used_ms": 150, "breached": False, "status": "closed"}],
)

# ----------------------------------------------------------------------
# 7. Out-of-Order Events & Numeric Sorting
# ----------------------------------------------------------------------
run_test(
    "Out-of-order events processed chronologically",
    [
        "500,A,CLOSE",
        "100,A,OPEN",
        "400,A,RESUME",
        "200,A,PAUSE",
    ],
    # Chronological: 100 OPEN, 200 PAUSE (100ms), 400 RESUME, 500 CLOSE (100ms) -> 200ms
    [{"ticket_id": "A", "used_ms": 200, "breached": False, "status": "closed"}],
)

run_test(
    "Numeric vs lexicographic timestamp sorting",
    [
        # If sorted as strings: "00200" < "100", so CLOSE would process before OPEN!
        # Numerically: 100 OPEN processes before 200 CLOSE.
        "00200,A,CLOSE",
        "100,A,OPEN",
    ],
    [{"ticket_id": "A", "used_ms": 100, "breached": False, "status": "closed"}],
)

# ----------------------------------------------------------------------
# 8. Output Ordering and Case Sensitivity
# ----------------------------------------------------------------------
run_test(
    "Output sorted by ticket_id ascending in code-point order",
    [
        "100,t2,OPEN",
        "100,T10,OPEN",
        "100,T2,OPEN",
        "100,t1,OPEN",
        "100,T1,OPEN",
        "100,2,OPEN",
        "100,10,OPEN",
        "100,A,OPEN",
        "100,a,OPEN",
        "200,a,CLOSE",
    ],
    # Code points: digits ("10", "2") < uppercase ("A", "T1", "T10", "T2") < lowercase ("a", "t1", "t2")
    # All open tickets run 100..200 (100 ms). 'a' closed at 200 (100 ms).
    [
        {"ticket_id": "10", "used_ms": 100, "breached": False, "status": "open"},
        {"ticket_id": "2", "used_ms": 100, "breached": False, "status": "open"},
        {"ticket_id": "A", "used_ms": 100, "breached": False, "status": "open"},
        {"ticket_id": "T1", "used_ms": 100, "breached": False, "status": "open"},
        {"ticket_id": "T10", "used_ms": 100, "breached": False, "status": "open"},
        {"ticket_id": "T2", "used_ms": 100, "breached": False, "status": "open"},
        {"ticket_id": "a", "used_ms": 100, "breached": False, "status": "closed"},
        {"ticket_id": "t1", "used_ms": 100, "breached": False, "status": "open"},
        {"ticket_id": "t2", "used_ms": 100, "breached": False, "status": "open"},
    ],
)

# ----------------------------------------------------------------------
# 9. Complex Multi-Ticket Scenario
# ----------------------------------------------------------------------
run_test(
    "Comprehensive multi-ticket interleaving scenario",
    [
        # T1: OPEN, PAUSE, RESUME, CLOSE
        "100,T1,OPEN",
        "200,T1,PAUSE",
        "400,T1,RESUME",
        "700,T1,CLOSE",  # used = (200-100) + (700-400) = 400, closed
        # T2: OPEN and stays RUNNING to now=10000
        "500,T2,OPEN",   # used = 10000 - 500 = 9500, open
        # T3: OPEN, CLOSE, REOPEN, PAUSE (stays paused to now)
        "1000,T3,OPEN",
        "1500,T3,CLOSE",
        "2000,T3,REOPEN",
        "2500,T3,PAUSE", # used = (1500-1000) + (2500-2000) = 1000, open
        # T4: OPEN, CLOSE, OPEN (resets!), stays RUNNING to now
        "1000,T4,OPEN",
        "2000,T4,CLOSE",
        "3000,T4,OPEN",  # reset at 3000, runs to 10000 -> used = 7000, open
        # T5: Only malformed lines -> omitted
        "bad_line_for_T5",
        "-10,T5,OPEN",
        # T6: Ignored events before OPEN, then CLOSE
        "50,T6,PAUSE",
        "50,T6,CLOSE",
        "6000,T6,OPEN",
        "8000,T6,CLOSE", # used = 2000, closed
        # T7: OPEN, PAUSE, CLOSE while PAUSED
        "500,T7,OPEN",
        "1000,T7,PAUSE",
        "9000,T7,CLOSE", # used = 500, closed
        # Line setting now to 10000 (valid well-formed line for an un-opened ticket)
        "10000,UNOPENED,CLOSE",
    ],
    [
        {"ticket_id": "T1", "used_ms": 400, "breached": False, "status": "closed"},
        {"ticket_id": "T2", "used_ms": 9500, "breached": False, "status": "open"},
        {"ticket_id": "T3", "used_ms": 1000, "breached": False, "status": "open"},
        {"ticket_id": "T4", "used_ms": 7000, "breached": False, "status": "open"},
        {"ticket_id": "T6", "used_ms": 2000, "breached": False, "status": "closed"},
        {"ticket_id": "T7", "used_ms": 500, "breached": False, "status": "closed"},
    ],
)

# ----------------------------------------------------------------------
# Summary and Exit
# ----------------------------------------------------------------------
print(f"\n--- Summary: {passed} passed, {failed} failed ---")
if failed == 0:
    sys.exit(0)
else:
    sys.exit(1)