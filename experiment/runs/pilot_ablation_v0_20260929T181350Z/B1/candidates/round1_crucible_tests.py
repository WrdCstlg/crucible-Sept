import sys
import solution

def run_tests():
    passed = 0
    failed = 0
    failures = []

    def check(test_name, stream, expected):
        nonlocal passed, failed
        try:
            # Ensure stream is passed as a list of CSV strings as required
            stream_input = list(stream)
            actual = solution.compute_sla(stream_input)

            # Check top-level type
            if not isinstance(actual, list):
                raise AssertionError(f"Expected list, got {type(actual).__name__}")

            # Check length
            if len(actual) != len(expected):
                raise AssertionError(
                    f"Length mismatch: expected {len(expected)} items, got {len(actual)}.\n"
                    f"Actual: {actual}\nExpected: {expected}"
                )

            # Check individual records, types, keys, and values
            for idx, (act, exp) in enumerate(zip(actual, expected)):
                if not isinstance(act, dict):
                    raise AssertionError(f"Item {idx} is not a dict: {type(act).__name__}")

                act_keys = set(act.keys())
                exp_keys = {"ticket_id", "used_ms", "breached", "status"}
                if act_keys != exp_keys:
                    raise AssertionError(
                        f"Item {idx} keys mismatch. Expected {exp_keys}, got {act_keys}"
                    )

                # Strict type checks
                if type(act["ticket_id"]) is not str:
                    raise AssertionError(
                        f"Item {idx} ticket_id type error: expected str, got {type(act['ticket_id']).__name__}"
                    )
                if type(act["used_ms"]) is not int:
                    raise AssertionError(
                        f"Item {idx} used_ms type error: expected int, got {type(act['used_ms']).__name__}"
                    )
                if type(act["breached"]) is not bool:
                    raise AssertionError(
                        f"Item {idx} breached type error: expected bool, got {type(act['breached']).__name__}"
                    )
                if type(act["status"]) is not str:
                    raise AssertionError(
                        f"Item {idx} status type error: expected str, got {type(act['status']).__name__}"
                    )

                # Value checks
                if act["ticket_id"] != exp["ticket_id"]:
                    raise AssertionError(
                        f"Item {idx} ticket_id mismatch: expected '{exp['ticket_id']}', got '{act['ticket_id']}'"
                    )
                if act["used_ms"] != exp["used_ms"]:
                    raise AssertionError(
                        f"Item {idx} (ticket '{act['ticket_id']}') used_ms mismatch: "
                        f"expected {exp['used_ms']}, got {act['used_ms']}"
                    )
                if act["breached"] != exp["breached"]:
                    raise AssertionError(
                        f"Item {idx} (ticket '{act['ticket_id']}') breached mismatch: "
                        f"expected {exp['breached']}, got {act['breached']}"
                    )
                if act["status"] != exp["status"]:
                    raise AssertionError(
                        f"Item {idx} (ticket '{act['ticket_id']}') status mismatch: "
                        f"expected '{exp['status']}', got '{act['status']}'"
                    )

            passed += 1
            print(f"PASS: {test_name}")
        except Exception as e:
            failed += 1
            failures.append((test_name, str(e)))
            print(f"FAIL: {test_name} - {e}")

    # ==========================================
    # TEST SUITE
    # ==========================================

    # 1. Empty streams & streams with no valid OPEN
    check("1.1 Empty stream", [], [])
    check(
        "1.2 Only whitespace and empty lines",
        ["", "   ", "\t", "  \n  "],
        []
    )
    check(
        "1.3 Events before first valid OPEN are silently ignored",
        [
            "100, T1, PAUSE",
            "200, T1, RESUME",
            "300, T1, CLOSE",
            "400, T1, REOPEN",
            "500, T2, CLOSE",
        ],
        []
    )
    check(
        "1.4 Malformed lines ignored and produce no tickets",
        [
            "not_a_number, T1, OPEN",
            "-100, T2, OPEN",
            "100.5, T3, OPEN",
            "100, T4",
            "100, T5, OPEN, extra",
            "100, T6, UNKNOWN_EVENT",
            ",,",
        ],
        []
    )

    # 2. Basic Ticket Lifecycles
    check(
        "2.1 Simple OPEN -> CLOSE",
        [
            "1000, T1, OPEN",
            "2500, T1, CLOSE",
        ],
        [
            {"ticket_id": "T1", "used_ms": 1500, "breached": False, "status": "closed"}
        ]
    )
    check(
        "2.2 OPEN -> PAUSE -> RESUME -> CLOSE",
        [
            "100, T1, OPEN",
            "300, T1, PAUSE",   # used: 200
            "600, T1, RESUME",  # pause duration 300 ignored
            "900, T1, CLOSE",   # used: 200 + 300 = 500
        ],
        [
            {"ticket_id": "T1", "used_ms": 500, "breached": False, "status": "closed"}
        ]
    )
    check(
        "2.3 OPEN -> PAUSE -> CLOSE (time from PAUSE to CLOSE does not count)",
        [
            "1000, T1, OPEN",
            "1400, T1, PAUSE",  # used: 400
            "2000, T1, CLOSE",  # time 1400..2000 does not count
        ],
        [
            {"ticket_id": "T1", "used_ms": 400, "breached": False, "status": "closed"}
        ]
    )

    # 3. Stream End ("Now") Handling
    check(
        "3.1 Ticket open and running at end of stream",
        [
            "1000, T1, OPEN",
            "3000, T2, OPEN",
            "4500, T2, CLOSE",  # now = 4500
        ],
        [
            # T1 ran from 1000 to 4500 -> 3500 ms
            {"ticket_id": "T1", "used_ms": 3500, "breached": False, "status": "open"},
            # T2 ran from 3000 to 4500 -> 1500 ms
            {"ticket_id": "T2", "used_ms": 1500, "breached": False, "status": "closed"},
        ]
    )
    check(
        "3.2 Ticket open and paused at end of stream",
        [
            "1000, T1, OPEN",
            "2000, T1, PAUSE",  # paused at 2000, used = 1000
            "5000, T2, OPEN",
            "6000, T2, CLOSE",  # now = 6000
        ],
        [
            # T1 paused counts only up to pause (1000 ms), status "open"
            {"ticket_id": "T1", "used_ms": 1000, "breached": False, "status": "open"},
            {"ticket_id": "T2", "used_ms": 1000, "breached": False, "status": "closed"},
        ]
    )
    check(
        "3.3 Now defined by an invalid event line",
        [
            "1000, T_VALID, OPEN",
            # Invalid event: PAUSE before OPEN on T_INVALID; sets stream max timestamp ("now") to 10000
            "10000, T_INVALID, PAUSE",
        ],
        [
            # T_VALID ran 1000..10000 = 9000 ms, T_INVALID omitted
            {"ticket_id": "T_VALID", "used_ms": 9000, "breached": False, "status": "open"}
        ]
    )
    check(
        "3.4 Now defined by invalid event on closed ticket",
        [
            "1000, T1, OPEN",
            "2000, T1, CLOSE",  # closed at 2000, used = 1000
            # Invalid event: CLOSE when already closed; max timestamp = 25000
            "25000, T1, CLOSE",
        ],
        [
            # T1 is closed, so used_ms does NOT advance past 2000
            {"ticket_id": "T1", "used_ms": 1000, "breached": False, "status": "closed"}
        ]
    )

    # 4. Exact SLA Boundaries (Limit = 14,400,000 ms; breach iff used_ms > limit)
    SLA = 14_400_000
    check(
        "4.1 SLA boundary tests for closed tickets (exact, under, over)",
        [
            f"0, T_EXACT, OPEN",
            f"{SLA}, T_EXACT, CLOSE",          # used = 14400000 -> NOT breached
            f"0, T_UNDER, OPEN",
            f"{SLA - 1}, T_UNDER, CLOSE",      # used = 14399999 -> NOT breached
            f"0, T_OVER, OPEN",
            f"{SLA + 1}, T_OVER, CLOSE",       # used = 14400001 -> BREACHED
        ],
        [
            {"ticket_id": "T_EXACT", "used_ms": SLA, "breached": False, "status": "closed"},
            {"ticket_id": "T_OVER", "used_ms": SLA + 1, "breached": True, "status": "closed"},
            {"ticket_id": "T_UNDER", "used_ms": SLA - 1, "breached": False, "status": "closed"},
        ]
    )
    check(
        "4.2 SLA boundary tests for open tickets evaluated at now",
        [
            "0, T_OPEN_EXACT, OPEN",
            "0, T_OPEN_OVER, OPEN",
            # T_REF sets now to SLA + 1
            f"{SLA + 1}, T_REF, OPEN",
            f"{SLA + 1}, T_REF, CLOSE",
            # Pause T_OPEN_EXACT at exactly SLA
            f"{SLA}, T_OPEN_EXACT, PAUSE",
        ],
        [
            # T_OPEN_EXACT: paused at SLA -> used = 14400000, status "open", NOT breached
            {"ticket_id": "T_OPEN_EXACT", "used_ms": SLA, "breached": False, "status": "open"},
            # T_OPEN_OVER: running until now (SLA + 1) -> used = 14400001, status "open", BREACHED
            {"ticket_id": "T_OPEN_OVER", "used_ms": SLA + 1, "breached": True, "status": "open"},
            {"ticket_id": "T_REF", "used_ms": 0, "breached": False, "status": "closed"},
        ]
    )

    # 5. Full State-Transition Table Coverage (4 states x 5 events = 20 cells)
    # States: NOT_OPEN, RUNNING, PAUSED, CLOSED
    # Events: OPEN, PAUSE, RESUME, CLOSE, REOPEN
    check(
        "5.1 Complete state-transition coverage & invalid event handling",
        [
            # --- State: NOT_OPEN ---
            # Cells 1-4: Invalid events before first OPEN
            "10, TX, PAUSE",   # invalid, ignored
            "20, TX, RESUME",  # invalid, ignored
            "30, TX, CLOSE",   # invalid, ignored
            "40, TX, REOPEN",  # invalid, ignored
            # Cell 5: OPEN when NOT_OPEN -> RUNNING
            "100, TX, OPEN",   # start clock at 100

            # --- State: RUNNING ---
            # Cells 6-8: Invalid events while RUNNING
            "120, TX, OPEN",   # invalid (OPEN when already open), ignored
            "140, TX, RESUME", # invalid (RESUME when running), ignored
            "160, TX, REOPEN", # invalid (REOPEN when not closed), ignored
            # Cell 9: PAUSE when RUNNING -> PAUSED
            "200, TX, PAUSE",  # used = 100 (100..200)

            # --- State: PAUSED ---
            # Cells 10-12: Invalid events while PAUSED
            "220, TX, OPEN",   # invalid (OPEN when already open), ignored
            "240, TX, PAUSE",  # invalid (PAUSE when already paused), ignored
            "260, TX, REOPEN", # invalid (REOPEN when not closed), ignored
            # Cell 13: RESUME when PAUSED -> RUNNING
            "300, TX, RESUME", # clock resumes at 300
            "400, TX, PAUSE",  # used = 100 + 100 = 200
            # Cell 14: CLOSE when PAUSED -> CLOSED
            "450, TX, CLOSE",  # pause to close time (400..450) does not count; used remains 200

            # --- State: CLOSED ---
            # Cells 15-18: Invalid events while CLOSED
            "500, TX, OPEN",   # invalid (already opened in past), ignored
            "520, TX, PAUSE",  # invalid (not open), ignored
            "540, TX, RESUME", # invalid (not paused), ignored
            "560, TX, CLOSE",  # invalid (CLOSE when already closed), ignored
            # Cell 19: REOPEN when CLOSED -> RUNNING
            "600, TX, REOPEN", # running from 600, total continues from 200
            # Cell 20: CLOSE when RUNNING -> CLOSED tested below in T_DIRECT

            # Reference ticket sets stream now = 700
            "700, TY, OPEN",
            "700, TY, CLOSE",
        ],
        [
            # TX: 200 used prior to reopen + (700 - 600) = 300 ms, status "open"
            {"ticket_id": "TX", "used_ms": 300, "breached": False, "status": "open"},
            {"ticket_id": "TY", "used_ms": 0, "breached": False, "status": "closed"},
        ]
    )

    # 6. Reopen Accumulation across Multiple Cycles
    check(
        "6.1 Running total continues across multiple REOPEN cycles without resetting",
        [
            "1000, TR, OPEN",
            "2500, TR, CLOSE",    # used: 1500
            "4000, TR, REOPEN",   # clock restarts at 4000
            "6000, TR, PAUSE",    # used: 1500 + 2000 = 3500
            "7000, TR, RESUME",   # clock restarts at 7000
            "8000, TR, CLOSE",    # used: 3500 + 1000 = 4500
            "10000, TR, REOPEN",  # clock restarts at 10000
            "11000, TR, CLOSE",   # used: 4500 + 1000 = 5500
        ],
        [
            {"ticket_id": "TR", "used_ms": 5500, "breached": False, "status": "closed"}
        ]
    )

    # 7. Out-of-Order Events
    check(
        "7.1 Out-of-order event timestamps properly sorted before processing",
        [
            "5000, T_OOO, CLOSE",
            "1000, T_OOO, OPEN",
            "4000, T_OOO, RESUME",
            "2000, T_OOO, PAUSE",
        ],
        [
            # Chronological: 1000 OPEN -> 2000 PAUSE (1000ms) -> 4000 RESUME -> 5000 CLOSE (1000ms) = 2000ms
            {"ticket_id": "T_OOO", "used_ms": 2000, "breached": False, "status": "closed"}
        ]
    )

    # 8. Ties Broken by Original Arrival Order (Stable Sort)
    check(
        "8.1 Tie: OPEN then CLOSE at identical timestamp vs CLOSE then OPEN",
        [
            # TIE1: OPEN arrived first, then CLOSE at timestamp 1000
            "1000, TIE1, OPEN",
            "1000, TIE1, CLOSE",

            # TIE2: CLOSE arrived first at 1000 (invalid, ignored), then OPEN at 1000
            "1000, TIE2, CLOSE",
            "1000, TIE2, OPEN",

            # Reference to set now = 2000
            "2000, T_NOW, OPEN",
            "2000, T_NOW, CLOSE",
        ],
        [
            {"ticket_id": "TIE1", "used_ms": 0, "breached": False, "status": "closed"},
            # TIE2 remains open from 1000 to now (2000) -> 1000 ms
            {"ticket_id": "TIE2", "used_ms": 1000, "breached": False, "status": "open"},
            {"ticket_id": "T_NOW", "used_ms": 0, "breached": False, "status": "closed"},
        ]
    )
    check(
        "8.2 Tie: PAUSE then RESUME at identical timestamp vs RESUME then PAUSE",
        [
            # TIE3: PAUSE then RESUME at 500
            "100, TIE3, OPEN",
            "500, TIE3, PAUSE",   # clock paused at 500 (used: 400)
            "500, TIE3, RESUME",  # clock resumed at 500
            "1000, TIE3, CLOSE",  # closed at 1000 (used: 400 + 500 = 900)

            # TIE4: RESUME then PAUSE at 500
            "100, TIE4, OPEN",
            "300, TIE4, PAUSE",   # clock paused at 300 (used: 200)
            "500, TIE4, RESUME",  # clock resumed at 500
            "500, TIE4, PAUSE",   # clock paused at 500 (used: 200 + 0 = 200)
            "1000, TIE4, CLOSE",  # closed at 1000 while paused (used stays 200)
        ],
        [
            {"ticket_id": "TIE3", "used_ms": 900, "breached": False, "status": "closed"},
            {"ticket_id": "TIE4", "used_ms": 200, "breached": False, "status": "closed"},
        ]
    )
    check(
        "8.3 Tie: CLOSE then REOPEN at identical timestamp vs REOPEN then CLOSE",
        [
            # TIE5: CLOSE then REOPEN at 2000
            "1000, TIE5, OPEN",
            "2000, TIE5, CLOSE",   # closed (used: 1000)
            "2000, TIE5, REOPEN",  # reopened at 2000

            # TIE6: REOPEN then CLOSE at 2000
            "1000, TIE6, OPEN",
            "2000, TIE6, REOPEN",  # invalid (not closed), ignored
            "2000, TIE6, CLOSE",   # closed (used: 1000)

            # Reference to set now = 3000
            "3000, T_REF, OPEN",
            "3000, T_REF, CLOSE",
        ],
        [
            {"ticket_id": "TIE5", "used_ms": 2000, "breached": False, "status": "open"},
            {"ticket_id": "TIE6", "used_ms": 1000, "breached": False, "status": "closed"},
            {"ticket_id": "T_REF", "used_ms": 0, "breached": False, "status": "closed"},
        ]
    )

    # 9. Output Ordering: Ticket IDs sorted ascending in lexicographical order
    check(
        "9.1 Output sorted by ticket_id string ascending",
        [
            "0, ticket_2, OPEN",
            "10, ticket_2, CLOSE",
            "0, ticket_10, OPEN",
            "10, ticket_10, CLOSE",
            "0, ticket_1, OPEN",
            "10, ticket_1, CLOSE",
            "0, 100, OPEN",
            "10, 100, CLOSE",
            "0, 20, OPEN",
            "10, 20, CLOSE",
            "0, Ticket_A, OPEN",
            "10, Ticket_A, CLOSE",
        ],
        [
            # Standard ASCII string sort: '100' < '20' < 'Ticket_A' < 'ticket_1' < 'ticket_10' < 'ticket_2'
            {"ticket_id": "100", "used_ms": 10, "breached": False, "status": "closed"},
            {"ticket_id": "20", "used_ms": 10, "breached": False, "status": "closed"},
            {"ticket_id": "Ticket_A", "used_ms": 10, "breached": False, "status": "closed"},
            {"ticket_id": "ticket_1", "used_ms": 10, "breached": False, "status": "closed"},
            {"ticket_id": "ticket_10", "used_ms": 10, "breached": False, "status": "closed"},
            {"ticket_id": "ticket_2", "used_ms": 10, "breached": False, "status": "closed"},
        ]
    )

    # 10. Whitespace and Embedded Malformed Lines with Valid Events
    check(
        "10.1 Whitespace around fields and interleaved malformed lines",
        [
            "   \t  ",
            "",
            "   100  ,   T_CLEAN  ,   OPEN   ",
            "invalid line with no commas",
            "bad_ts, T_CLEAN, PAUSE",
            "200, T_CLEAN, PAUSE, extra_field",
            "-50, T_CLEAN, PAUSE",
            "300.5, T_CLEAN, PAUSE",
            "  300  ,  T_CLEAN  ,  PAUSE  ",  # used: 200
            "400, T_CLEAN, UNKNOWN",
            "  600  ,  T_CLEAN  ,  RESUME  ",
            "  900  ,  T_CLEAN  ,  CLOSE  ",   # used: 200 + 300 = 500
        ],
        [
            {"ticket_id": "T_CLEAN", "used_ms": 500, "breached": False, "status": "closed"}
        ]
    )

    # 11. Multiple Interleaved Tickets with Complex Timelines
    check(
        "11.1 Interleaved multi-ticket scenario with breach, pause, close, and reopen",
        [
            "0, T1, OPEN",
            "0, T2, OPEN",
            "0, T3, OPEN",
            "5000000, T1, PAUSE",         # T1 used = 5,000,000
            "6000000, T2, CLOSE",         # T2 used = 6,000,000
            "10000000, T1, RESUME",       # T1 clock resumes
            "15000000, T1, CLOSE",        # T1 used = 5M + 5M = 10,000,000
            "14400001, T3, PAUSE",        # T3 paused at 14,400,001 -> BREACHED (>14.4M)
        ],
        [
            {"ticket_id": "T1", "used_ms": 10000000, "breached": False, "status": "closed"},
            {"ticket_id": "T2", "used_ms": 6000000, "breached": False, "status": "closed"},
            {"ticket_id": "T3", "used_ms": 14400001, "breached": True, "status": "open"},
        ]
    )

    # 12. Non-list Iterable Support (e.g., generator)
    def generator_stream():
        yield " 100 , T_GEN , OPEN "
        yield " 400 , T_GEN , CLOSE "

    check(
        "12.1 Stream passed as generator / iterator",
        generator_stream(),
        [
            {"ticket_id": "T_GEN", "used_ms": 300, "breached": False, "status": "closed"}
        ]
    )

    # Print summary
    print("\n" + "=" * 50)
    print(f"Summary: {passed} passed, {failed} failed")
    print("=" * 50)

    if failed > 0:
        print("\nFailure Details:")
        for name, err in failures:
            print(f"- {name}: {err}")
        sys.exit(1)
    else:
        print("All tests passed successfully.")
        sys.exit(0)

if __name__ == "__main__":
    run_tests()