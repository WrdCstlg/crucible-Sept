import solution
import sys


def validate_result_structure(result):
    if type(result) is not list:
        raise AssertionError(f"Expected return type list, got {type(result)}")
    for i, item in enumerate(result):
        if type(item) is not dict:
            raise AssertionError(f"Element at index {i} is not a dict: {type(item)}")
        expected_keys = {"ticket_id", "used_ms", "breached", "status"}
        if set(item.keys()) != expected_keys:
            raise AssertionError(
                f"Element at index {i} has keys {set(item.keys())}, expected exactly {expected_keys}"
            )
        if type(item["ticket_id"]) is not str:
            raise AssertionError(
                f"Element at index {i} 'ticket_id' must be str, got {type(item['ticket_id'])}"
            )
        if type(item["used_ms"]) is not int or type(item["used_ms"]) is bool:
            raise AssertionError(
                f"Element at index {i} 'used_ms' must be int (and not bool), got {type(item['used_ms'])}"
            )
        if type(item["breached"]) is not bool:
            raise AssertionError(
                f"Element at index {i} 'breached' must be bool, got {type(item['breached'])}"
            )
        if type(item["status"]) is not str or item["status"] not in ("open", "closed"):
            raise AssertionError(
                f"Element at index {i} 'status' must be 'open' or 'closed', got {item['status']!r}"
            )


def run_test(name, stream, expected):
    print(f"Running test: {name} ... ", end="")
    try:
        actual = solution.compute_sla(stream)
        validate_result_structure(actual)
        if actual != expected:
            raise AssertionError(
                f"\nTest '{name}' failed!\nExpected:\n  {expected}\nGot:\n  {actual}"
            )
        print("PASSED")
        return True
    except Exception as e:
        print(f"FAILED: {e}")
        return False


def main():
    tests_passed = 0
    tests_failed = 0

    test_cases = []

    # --------------------------------------------------------------------------
    # 1. Empty and trivial streams
    # --------------------------------------------------------------------------
    test_cases.append((
        "Empty stream returns empty list",
        [],
        []
    ))

    test_cases.append((
        "Stream with only blank/whitespace lines returns empty list",
        ["", "   ", "\t\t", "  \n  ", "\r\n"],
        []
    ))

    test_cases.append((
        "Single ticket OPEN and CLOSE",
        [
            "100,A,OPEN",
            "400,A,CLOSE",
        ],
        [{"ticket_id": "A", "used_ms": 300, "breached": False, "status": "closed"}]
    ))

    # --------------------------------------------------------------------------
    # 2. Tickets that never had a valid OPEN
    # --------------------------------------------------------------------------
    test_cases.append((
        "All events on NOT_OPENED tickets are ignored and tickets are omitted",
        [
            "100,T1,PAUSE",
            "200,T1,RESUME",
            "300,T1,CLOSE",
            "400,T1,REOPEN",
            "500,T2,PAUSE",
            "600,T2,CLOSE",
        ],
        []
    ))

    test_cases.append((
        "Ignored events on NOT_OPENED ticket do not output that ticket, but contribute to now",
        [
            "100,VALID,OPEN",
            "500,IGNORED,PAUSE",  # Ignored transition on NOT_OPENED, but valid CSV -> now is 500
        ],
        # VALID ticket is RUNNING from 100 to 500 = 400 ms. IGNORED ticket is omitted.
        [{"ticket_id": "VALID", "used_ms": 400, "breached": False, "status": "open"}]
    ))

    # --------------------------------------------------------------------------
    # 3. State Transition Matrix: Every cell of 4 states x 5 events
    # States: NOT_OPENED, RUNNING, PAUSED, CLOSED
    # Events: OPEN, PAUSE, RESUME, CLOSE, REOPEN
    # --------------------------------------------------------------------------

    # Cell 1: NOT_OPENED + OPEN -> RUNNING, used time 0
    test_cases.append((
        "Transition: NOT_OPENED + OPEN -> RUNNING",
        ["100,T,OPEN"],
        [{"ticket_id": "T", "used_ms": 0, "breached": False, "status": "open"}]
    ))

    # Cell 2: NOT_OPENED + PAUSE -> ignored
    test_cases.append((
        "Transition: NOT_OPENED + PAUSE -> ignored (subsequent OPEN starts at 0)",
        [
            "50,T,PAUSE",
            "100,T,OPEN",
            "200,T,CLOSE",
        ],
        [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    ))

    # Cell 3: NOT_OPENED + RESUME -> ignored
    test_cases.append((
        "Transition: NOT_OPENED + RESUME -> ignored",
        [
            "50,T,RESUME",
            "100,T,OPEN",
            "200,T,CLOSE",
        ],
        [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    ))

    # Cell 4: NOT_OPENED + CLOSE -> ignored
    test_cases.append((
        "Transition: NOT_OPENED + CLOSE -> ignored",
        [
            "50,T,CLOSE",
            "100,T,OPEN",
            "200,T,CLOSE",
        ],
        [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    ))

    # Cell 5: NOT_OPENED + REOPEN -> ignored
    test_cases.append((
        "Transition: NOT_OPENED + REOPEN -> ignored",
        [
            "50,T,REOPEN",
            "100,T,OPEN",
            "200,T,CLOSE",
        ],
        [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    ))

    # Cell 6: RUNNING + OPEN -> ignored
    test_cases.append((
        "Transition: RUNNING + OPEN -> ignored (clock keeps running from first OPEN)",
        [
            "100,T,OPEN",
            "200,T,OPEN",   # ignored
            "300,T,CLOSE",
        ],
        # 100 to 300 = 200 ms (not 100 ms)
        [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    ))

    # Cell 7: RUNNING + PAUSE -> to PAUSED
    test_cases.append((
        "Transition: RUNNING + PAUSE -> PAUSED (still open at stream end, counts up to pause)",
        [
            "100,T,OPEN",
            "250,T,PAUSE",
            "500,OTHER,CLOSE",  # establishes now = 500
        ],
        # T paused at 250: used_ms = 150, status = open
        [{"ticket_id": "T", "used_ms": 150, "breached": False, "status": "open"}]
    ))

    # Cell 8: RUNNING + RESUME -> ignored
    test_cases.append((
        "Transition: RUNNING + RESUME -> ignored",
        [
            "100,T,OPEN",
            "200,T,RESUME",  # ignored
            "350,T,CLOSE",
        ],
        # 100 to 350 = 250 ms
        [{"ticket_id": "T", "used_ms": 250, "breached": False, "status": "closed"}]
    ))

    # Cell 9: RUNNING + CLOSE -> to CLOSED
    test_cases.append((
        "Transition: RUNNING + CLOSE -> CLOSED",
        [
            "100,T,OPEN",
            "300,T,CLOSE",
            "600,OTHER,CLOSE",  # establishes now = 600
        ],
        # 100 to 300 = 200 ms, status = closed
        [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    ))

    # Cell 10: RUNNING + REOPEN -> ignored
    test_cases.append((
        "Transition: RUNNING + REOPEN -> ignored",
        [
            "100,T,OPEN",
            "200,T,REOPEN",  # ignored
            "350,T,CLOSE",
        ],
        # 100 to 350 = 250 ms
        [{"ticket_id": "T", "used_ms": 250, "breached": False, "status": "closed"}]
    ))

    # Cell 11: PAUSED + OPEN -> ignored
    test_cases.append((
        "Transition: PAUSED + OPEN -> ignored (remains paused)",
        [
            "100,T,OPEN",
            "200,T,PAUSE",   # used = 100
            "300,T,OPEN",    # ignored
            "400,T,RESUME",  # enters RUNNING at 400
            "500,T,CLOSE",   # used = 100 + (500 - 400) = 200
        ],
        [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    ))

    # Cell 12: PAUSED + PAUSE -> ignored
    test_cases.append((
        "Transition: PAUSED + PAUSE -> ignored",
        [
            "100,T,OPEN",
            "200,T,PAUSE",   # used = 100
            "300,T,PAUSE",   # ignored
            "400,T,RESUME",
            "500,T,CLOSE",
        ],
        # used = 100 + (500 - 400) = 200
        [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    ))

    # Cell 13: PAUSED + RESUME -> to RUNNING
    test_cases.append((
        "Transition: PAUSED + RESUME -> to RUNNING",
        [
            "100,T,OPEN",
            "200,T,PAUSE",
            "300,T,RESUME",
            "450,T,CLOSE",
        ],
        # (200 - 100) + (450 - 300) = 100 + 150 = 250
        [{"ticket_id": "T", "used_ms": 250, "breached": False, "status": "closed"}]
    ))

    # Cell 14: PAUSED + CLOSE -> to CLOSED (stretch between PAUSE and CLOSE does not count)
    test_cases.append((
        "Transition: PAUSED + CLOSE -> to CLOSED (paused stretch does not count)",
        [
            "100,T,OPEN",
            "200,T,PAUSE",
            "600,T,CLOSE",
        ],
        # used = 200 - 100 = 100 (stretch 200 to 600 does not count)
        [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    ))

    # Cell 15: PAUSED + REOPEN -> ignored
    test_cases.append((
        "Transition: PAUSED + REOPEN -> ignored",
        [
            "100,T,OPEN",
            "200,T,PAUSE",
            "300,T,REOPEN",  # ignored
            "400,T,RESUME",
            "500,T,CLOSE",
        ],
        # 100 + (500 - 400) = 200
        [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    ))

    # Cell 16: CLOSED + OPEN -> to RUNNING, used time RESETS to 0
    test_cases.append((
        "Transition: CLOSED + OPEN -> to RUNNING (resets used time to 0)",
        [
            "100,T,OPEN",
            "300,T,CLOSE",   # used was 200
            "500,T,OPEN",    # resets used to 0
            "650,T,CLOSE",   # used = 650 - 500 = 150
        ],
        [{"ticket_id": "T", "used_ms": 150, "breached": False, "status": "closed"}]
    ))

    # Cell 17: CLOSED + PAUSE -> ignored
    test_cases.append((
        "Transition: CLOSED + PAUSE -> ignored",
        [
            "100,T,OPEN",
            "200,T,CLOSE",
            "300,T,PAUSE",  # ignored
        ],
        # now = 300, status remains closed, used = 100
        [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    ))

    # Cell 18: CLOSED + RESUME -> ignored
    test_cases.append((
        "Transition: CLOSED + RESUME -> ignored",
        [
            "100,T,OPEN",
            "200,T,CLOSE",
            "300,T,RESUME",  # ignored
        ],
        [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    ))

    # Cell 19: CLOSED + CLOSE -> ignored
    test_cases.append((
        "Transition: CLOSED + CLOSE -> ignored",
        [
            "100,T,OPEN",
            "200,T,CLOSE",
            "300,T,CLOSE",  # ignored
        ],
        [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    ))

    # Cell 20: CLOSED + REOPEN -> to RUNNING, used time CONTINUES from total
    test_cases.append((
        "Transition: CLOSED + REOPEN -> to RUNNING (used time continues from total)",
        [
            "100,T,OPEN",
            "300,T,CLOSE",    # used = 200
            "500,T,REOPEN",   # continues from 200
            "650,T,CLOSE",    # used = 200 + (650 - 500) = 350
        ],
        [{"ticket_id": "T", "used_ms": 350, "breached": False, "status": "closed"}]
    ))

    # --------------------------------------------------------------------------
    # 4. Exact SLA boundary (14,400,000 ms) and breach conditions
    # --------------------------------------------------------------------------
    test_cases.append((
        "SLA exact boundary: exactly 14,400,000 ms used does NOT breach",
        [
            "0,T_EXACT,OPEN",
            "14400000,T_EXACT,CLOSE",
        ],
        [{"ticket_id": "T_EXACT", "used_ms": 14400000, "breached": False, "status": "closed"}]
    ))

    test_cases.append((
        "SLA boundary: 14,399,999 ms used does NOT breach",
        [
            "0,T_UNDER,OPEN",
            "14399999,T_UNDER,CLOSE",
        ],
        [{"ticket_id": "T_UNDER", "used_ms": 14399999, "breached": False, "status": "closed"}]
    ))

    test_cases.append((
        "SLA boundary: 14,400,001 ms used DOES breach (strictly greater)",
        [
            "0,T_OVER,OPEN",
            "14400001,T_OVER,CLOSE",
        ],
        [{"ticket_id": "T_OVER", "used_ms": 14400001, "breached": True, "status": "closed"}]
    ))

    test_cases.append((
        "SLA boundary on open tickets: open ticket reaching > 14,400,000 ms breaches",
        [
            "0,T_OPEN_BREACH,OPEN",
            "14400001,OTHER,CLOSE",  # establishes now = 14400001
        ],
        [{"ticket_id": "T_OPEN_BREACH", "used_ms": 14400001, "breached": True, "status": "open"}]
    ))

    test_cases.append((
        "SLA boundary on open tickets: open ticket at exactly 14,400,000 ms does NOT breach",
        [
            "0,T_OPEN_EXACT,OPEN",
            "14400000,OTHER,CLOSE",  # establishes now = 14400000
        ],
        [{"ticket_id": "T_OPEN_EXACT", "used_ms": 14400000, "breached": False, "status": "open"}]
    ))

    test_cases.append((
        "SLA accumulation across multiple intervals with REOPEN",
        [
            "0,T_ACC,OPEN",
            "7200000,T_ACC,CLOSE",    # used: 7,200,000
            "10000000,T_ACC,REOPEN",  # continues
            "17200001,T_ACC,CLOSE",   # used: 7,200,000 + 7,200,001 = 14,400,001 (breached!)
        ],
        [{"ticket_id": "T_ACC", "used_ms": 14400001, "breached": True, "status": "closed"}]
    ))

    test_cases.append((
        "SLA accumulation reset with OPEN does NOT breach",
        [
            "0,T_RESET,OPEN",
            "10000000,T_RESET,CLOSE",   # used: 10,000,000
            "12000000,T_RESET,OPEN",    # reset to 0!
            "20000000,T_RESET,CLOSE",   # used: 8,000,000 (not 18,000,000)
        ],
        [{"ticket_id": "T_RESET", "used_ms": 8000000, "breached": False, "status": "closed"}]
    ))

    # --------------------------------------------------------------------------
    # 5. Timestamp Ties and Stable Sort Preservation
    # --------------------------------------------------------------------------
    test_cases.append((
        "Ties at same timestamp: OPEN, PAUSE, RESUME, CLOSE at exact same ms",
        [
            "1000,T,OPEN",
            "1000,T,PAUSE",
            "1000,T,RESUME",
            "1000,T,CLOSE",
        ],
        # All happen at ms 1000 in sequence: used_ms = 0, closed
        [{"ticket_id": "T", "used_ms": 0, "breached": False, "status": "closed"}]
    ))

    test_cases.append((
        "Ties: PAUSE before RESUME at same timestamp must be preserved by stable sort",
        [
            "100,T,OPEN",
            "200,T,PAUSE",   # at 200, pause: used accumulates 100
            "200,T,RESUME",  # at 200, resume running
            "300,T,CLOSE",   # at 300, close: used accumulates (300-200) = 100. Total = 200.
        ],
        # If order were unstable and RESUME was processed before PAUSE:
        # RESUME on RUNNING is ignored; PAUSE puts it in PAUSED; CLOSE at 300 closes without adding -> used would be 100.
        # Stable sort ensures 200 ms.
        [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    ))

    test_cases.append((
        "Ties: CLOSE before OPEN at same timestamp (reset at end of stream)",
        [
            "100,T,OPEN",
            "200,T,CLOSE",  # at 200, close: used = 100
            "200,T,OPEN",   # at 200, OPEN resets used to 0 and state to RUNNING!
        ],
        # now = 200. Final state is RUNNING, used_ms = 0 (200-200), status = open.
        # If unstable and OPEN processed before CLOSE:
        # OPEN on RUNNING ignored; CLOSE at 200 closes ticket -> status = closed, used = 100.
        [{"ticket_id": "T", "used_ms": 0, "breached": False, "status": "open"}]
    ))

    test_cases.append((
        "Ties: CLOSE before REOPEN at same timestamp (reopen at end of stream)",
        [
            "100,T,OPEN",
            "200,T,CLOSE",   # at 200, closes: used = 100
            "200,T,REOPEN",  # at 200, reopen: RUNNING, used continues at 100
        ],
        # now = 200. Final state is RUNNING, used_ms = 100, status = open.
        # If unstable and REOPEN processed before CLOSE:
        # REOPEN on RUNNING ignored; CLOSE closes ticket -> status = closed.
        [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "open"}]
    ))

    # --------------------------------------------------------------------------
    # 6. Out-of-order events arrival
    # --------------------------------------------------------------------------
    test_cases.append((
        "Out-of-order arrival correctly sorted by timestamp",
        [
            "600,A,CLOSE",
            "100,A,OPEN",
            "400,A,RESUME",
            "200,A,PAUSE",
            "500,B,OPEN",
            "300,B,PAUSE",  # Ignored because B was NOT_OPENED at 300
        ],
        # Sorted order:
        # 100: A OPEN -> RUNNING
        # 200: A PAUSE -> PAUSED (used 100)
        # 300: B PAUSE -> ignored (B not opened yet)
        # 400: A RESUME -> RUNNING
        # 500: B OPEN -> RUNNING
        # 600: A CLOSE -> CLOSED (used 100 + (600-400) = 300)
        # Stream ends at now = 600.
        # B is still RUNNING: used = 600 - 500 = 100, status = open.
        # Output order by ticket_id: "A" then "B".
        [
            {"ticket_id": "A", "used_ms": 300, "breached": False, "status": "closed"},
            {"ticket_id": "B", "used_ms": 100, "breached": False, "status": "open"},
        ]
    ))

    # --------------------------------------------------------------------------
    # 7. Malformed lines handling and Definition of 'Now'
    # --------------------------------------------------------------------------
    test_cases.append((
        "Malformed lines are ignored completely and do not affect 'now'",
        [
            "100,A,OPEN",
            # All following are malformed and must have no effect, especially on 'now':
            "",
            "   ",
            "999999999,A",                    # less than 3 fields
            "999999999,A,OPEN,EXTRA",          # more than 3 fields
            "999999999,A,OPEN,",               # trailing empty field (4 fields)
            ",999999999,A,OPEN",               # leading empty field
            "999999999,,OPEN",                 # empty ticket ID
            "999999999,   ,OPEN",              # ticket ID trims to empty
            "999999999,A,open",                # lowercase event
            "999999999,A,Open",                # mixed-case event
            "999999999,A,INVALID",             # unknown event
            "999999999,A,PAUSED",              # event name mismatch
            "-100,A,OPEN",                     # negative timestamp
            "+999999999,A,OPEN",               # plus sign in timestamp
            "999999999.0,A,OPEN",              # decimal timestamp
            "1e9,A,OPEN",                      # scientific notation
            "999 999,A,OPEN",                  # space inside timestamp
            ",A,OPEN",                         # empty timestamp
            "999999999,A,",                    # empty event
        ],
        # Only '100,A,OPEN' is well-formed. 'now' is 100.
        # A is still RUNNING at 100: used = 100 - 100 = 0.
        [{"ticket_id": "A", "used_ms": 0, "breached": False, "status": "open"}]
    ))

    test_cases.append((
        "Well-formed lines with leading zeros, whitespace around fields, and CR/LF",
        [
            "  000100  ,  A  ,  OPEN  \r\n",
            "\t000300\t,\tA\t,\tCLOSE\t\n",
        ],
        # Both lines well-formed. Timestamp 000100 -> 100, 000300 -> 300.
        # used_ms = 200, status = closed.
        [{"ticket_id": "A", "used_ms": 200, "breached": False, "status": "closed"}]
    ))

    test_cases.append((
        "Ticket ID with internal space is valid after trimming",
        [
            " 100 , TICKET WITH SPACES , OPEN ",
            " 250 , TICKET WITH SPACES , CLOSE ",
        ],
        [{"ticket_id": "TICKET WITH SPACES", "used_ms": 150, "breached": False, "status": "closed"}]
    ))

    test_cases.append((
        "Definition of 'now': includes well-formed lines that are invalid transitions",
        [
            "100,A,OPEN",
            "200,A,PAUSE",    # A paused at 200: used = 100
            "500,B,PAUSE",    # Well-formed, but invalid transition (B not opened). Sets now = 500!
        ],
        # now = 500. A is PAUSED, so counts only up to its pause (200 - 100 = 100).
        # B never had a valid OPEN -> omitted!
        [{"ticket_id": "A", "used_ms": 100, "breached": False, "status": "open"}]
    ))

    # --------------------------------------------------------------------------
    # 8. Output ordering (code-point order) and Case-sensitivity
    # --------------------------------------------------------------------------
    test_cases.append((
        "Case-sensitivity and Python code-point order sorting",
        [
            # Input given in arbitrary order:
            "100,t1,OPEN", "200,t1,CLOSE",
            "100,T1,OPEN", "200,T1,CLOSE",
            "100,T2,OPEN", "200,T2,CLOSE",
            "100,T10,OPEN", "200,T10,CLOSE",
            "100,2,OPEN", "200,2,CLOSE",
            "100,10,OPEN", "200,10,CLOSE",
            "100,1,OPEN", "200,1,CLOSE",
            "100,a,OPEN", "200,a,CLOSE",
            "100,A,OPEN", "200,A,CLOSE",
            "100,_,OPEN", "200,_,CLOSE",
        ],
        # Python default string sort (code-point order):
        # '1' (49) < '10' < '2' (50) < 'A' (65) < 'T1' (84) < 'T10' < 'T2' < '_' (95) < 'a' (97) < 't1' (116)
        [
            {"ticket_id": "1", "used_ms": 100, "breached": False, "status": "closed"},
            {"ticket_id": "10", "used_ms": 100, "breached": False, "status": "closed"},
            {"ticket_id": "2", "used_ms": 100, "breached": False, "status": "closed"},
            {"ticket_id": "A", "used_ms": 100, "breached": False, "status": "closed"},
            {"ticket_id": "T1", "used_ms": 100, "breached": False, "status": "closed"},
            {"ticket_id": "T10", "used_ms": 100, "breached": False, "status": "closed"},
            {"ticket_id": "T2", "used_ms": 100, "breached": False, "status": "closed"},
            {"ticket_id": "_", "used_ms": 100, "breached": False, "status": "closed"},
            {"ticket_id": "a", "used_ms": 100, "breached": False, "status": "closed"},
            {"ticket_id": "t1", "used_ms": 100, "breached": False, "status": "closed"},
        ]
    ))

    # --------------------------------------------------------------------------
    # 9. Complex interleaved lifecycle with multiple tickets
    # --------------------------------------------------------------------------
    test_cases.append((
        "Interleaved lifecycles: resets, continuations, pauses, ignored events, now",
        [
            # Ticket A: OPEN, PAUSE, RESUME, CLOSE, REOPEN, CLOSE
            "10,A,OPEN",
            "50,A,PAUSE",      # used = 40
            "100,A,RESUME",
            "200,A,CLOSE",     # used = 40 + (200 - 100) = 140
            "300,A,REOPEN",    # continues from 140
            "500,A,CLOSE",     # used = 140 + (500 - 300) = 340, closed

            # Ticket B: OPEN, CLOSE, OPEN (reset), PAUSE, RESUME, ends RUNNING
            "20,B,OPEN",
            "80,B,CLOSE",      # used = 60
            "150,B,OPEN",      # resets to 0!
            "250,B,PAUSE",     # used = 100
            "350,B,RESUME",    # resumes running; stream ends at now=600 -> used = 100 + (600-350) = 350, open

            # Ticket C: OPEN, PAUSE, ends PAUSED
            "30,C,OPEN",
            "70,C,PAUSE",      # used = 40; paused tickets count only up to pause -> used = 40, open

            # Ticket D: never opened, all ignored
            "40,D,PAUSE",
            "90,D,RESUME",
            "120,D,CLOSE",
            "180,D,REOPEN",

            # Ticket E: well-formed CLOSE on never-opened ticket -> ignored, sets now = 600
            "600,E,CLOSE",
        ],
        [
            {"ticket_id": "A", "used_ms": 340, "breached": False, "status": "closed"},
            {"ticket_id": "B", "used_ms": 350, "breached": False, "status": "open"},
            {"ticket_id": "C", "used_ms": 40, "breached": False, "status": "open"},
        ]
    ))

    # --------------------------------------------------------------------------
    # Run all test cases
    # --------------------------------------------------------------------------
    print("=" * 70)
    print(f"Starting test suite ({len(test_cases)} tests)...")
    print("=" * 70)

    for name, stream, expected in test_cases:
        if run_test(name, stream, expected):
            tests_passed += 1
        else:
            tests_failed += 1

    print("=" * 70)
    print(f"Summary: {tests_passed} passed, {tests_failed} failed, {len(test_cases)} total")
    print("=" * 70)

    if tests_failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()