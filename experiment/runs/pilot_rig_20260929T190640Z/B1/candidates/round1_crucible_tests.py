import solution
import sys


def validate_result_format(result, test_name):
    """Verify that result conforms strictly to the specified output format and types."""
    if type(result) is not list:
        return False, f"{test_name}: Expected result to be a list, got {type(result).__name__}"
    expected_keys = {"ticket_id", "used_ms", "breached", "status"}
    for idx, item in enumerate(result):
        if type(item) is not dict:
            return False, f"{test_name}: Item {idx} is not a dict: {type(item).__name__}"
        if set(item.keys()) != expected_keys or len(item) != 4:
            return False, f"{test_name}: Item {idx} keys do not match {expected_keys}: got {list(item.keys())}"
        if type(item["ticket_id"]) is not str:
            return False, f"{test_name}: Item {idx} ticket_id is not str: {type(item['ticket_id']).__name__}"
        if type(item["used_ms"]) is not int:
            return False, f"{test_name}: Item {idx} used_ms is not int: {type(item['used_ms']).__name__}"
        if type(item["breached"]) is not bool:
            return False, f"{test_name}: Item {idx} breached is not bool: {type(item['breached']).__name__}"
        if type(item["status"]) is not str or item["status"] not in ("open", "closed"):
            return False, f"{test_name}: Item {idx} status must be 'open' or 'closed', got {item['status']!r}"
    return True, ""


def run_tests():
    tests = []

    # -------------------------------------------------------------------------
    # Test 1: Empty stream returns []
    # -------------------------------------------------------------------------
    tests.append({
        "name": "Empty stream list",
        "stream": [],
        "expected": []
    })

    # -------------------------------------------------------------------------
    # Test 2: Stream as an iterator/generator
    # -------------------------------------------------------------------------
    def empty_gen():
        if False:
            yield ""

    tests.append({
        "name": "Empty generator stream",
        "stream": empty_gen(),
        "expected": []
    })

    # -------------------------------------------------------------------------
    # Test 3: Completely malformed lines (must all be ignored, return [])
    # -------------------------------------------------------------------------
    malformed_stream = [
        "",                             # Empty line
        "   ",                          # Whitespace line
        "\t\r\n",                      # Whitespace control characters
        "100",                          # Missing commas (1 field)
        "100,T1",                       # Only 2 fields
        "100,T1,OPEN,EXTRA",            # 4 fields
        "100,T1,OPEN,EXTRA1,EXTRA2",    # 5 fields
        ",,",                           # 3 empty fields
        "   ,   ,   ",                  # 3 whitespace fields
        "abc,T1,OPEN",                  # Timestamp not all digits
        "-100,T1,OPEN",                 # Negative timestamp
        "+100,T1,OPEN",                 # Plus sign in timestamp
        "100.0,T1,OPEN",                # Decimal timestamp
        "100 000,T1,OPEN",              # Internal space in timestamp
        "100,,OPEN",                    # Empty ticket ID
        "100,   ,OPEN",                 # Whitespace-only ticket ID
        "100,T1,open",                  # Lowercase event
        "100,T1,Open",                  # Mixed-case event
        "100,T1,START",                 # Unknown event
        "100,T1,CLOSE1",                # Unknown event
        "100,T1,PENDING",               # Unknown event
        "100,T1,",                     # Empty event
        "100,T1,   ",                  # Whitespace event
        "\u0661\u0660\u0660,T1,OPEN",   # Non-ASCII Eastern Arabic digits in timestamp
        "\uff11\uff10\uff10,T1,OPEN",   # Fullwidth ASCII digits in timestamp
    ]
    tests.append({
        "name": "All malformed lines return empty list",
        "stream": malformed_stream,
        "expected": []
    })

    # -------------------------------------------------------------------------
    # Test 4: Tickets that never had a valid OPEN must be omitted
    # -------------------------------------------------------------------------
    never_opened_stream = [
        "100,T1,PAUSE",
        "200,T1,RESUME",
        "300,T1,CLOSE",
        "400,T1,REOPEN",
        "500,T2,CLOSE",
        "600,T2,RESUME",
        "700,T3,REOPEN",
    ]
    tests.append({
        "name": "Tickets never validly opened are omitted",
        "stream": never_opened_stream,
        "expected": []
    })

    # -------------------------------------------------------------------------
    # Test 5: Format example from the specification
    # -------------------------------------------------------------------------
    tests.append({
        "name": "Specification format example",
        "stream": [
            "100,A,OPEN",
            "400,A,CLOSE",
        ],
        "expected": [
            {"ticket_id": "A", "used_ms": 300, "breached": False, "status": "closed"}
        ]
    })

    # -------------------------------------------------------------------------
    # Test 6: Running ticket at end of stream accumulates up to "now"
    # -------------------------------------------------------------------------
    # A is OPEN at 100, still RUNNING at end of stream.
    # B is OPEN at 400, CLOSED at 600 (used 200).
    # "Now" is 600 (largest well-formed timestamp).
    # A used_ms = 600 - 100 = 500, status = "open".
    tests.append({
        "name": "Running ticket at end of stream accumulates to now",
        "stream": [
            "100,A,OPEN",
            "400,B,OPEN",
            "600,B,CLOSE",
        ],
        "expected": [
            {"ticket_id": "A", "used_ms": 500, "breached": False, "status": "open"},
            {"ticket_id": "B", "used_ms": 200, "breached": False, "status": "closed"},
        ]
    })

    # -------------------------------------------------------------------------
    # Test 7: Paused ticket at end of stream accumulates only up to its pause
    # -------------------------------------------------------------------------
    # A is OPEN at 100, PAUSED at 300 (used 200).
    # B is OPEN at 600, CLOSED at 800 (used 200).
    # "Now" is 800.
    # A final state is PAUSED, so status is "open" and used_ms is 200 (not 800-100).
    tests.append({
        "name": "Paused ticket at end of stream counts only up to pause",
        "stream": [
            "100,A,OPEN",
            "300,A,PAUSE",
            "600,B,OPEN",
            "800,B,CLOSE",
        ],
        "expected": [
            {"ticket_id": "A", "used_ms": 200, "breached": False, "status": "open"},
            {"ticket_id": "B", "used_ms": 200, "breached": False, "status": "closed"},
        ]
    })

    # -------------------------------------------------------------------------
    # Test 8: Definition of "Now"
    # - Largest timestamp among well-formed lines, even if transition is ignored
    # - Malformed lines do NOT advance "now"
    # - Ticket that was never opened does NOT appear in output
    # -------------------------------------------------------------------------
    # Stream:
    # 100,A,OPEN -> A starts RUNNING at 100
    # 999999999,MALFORMED_LINE -> malformed! Must NOT affect now.
    # 500,GHOST,PAUSE -> well-formed, ignored transition (NOT_OPENED), but now = 500!
    # A still RUNNING at end of stream: used = 500 - 100 = 400.
    tests.append({
        "name": "Definition of now with ignored event and malformed line",
        "stream": [
            "100,A,OPEN",
            "999999999,MALFORMED_LINE",
            "500,GHOST,PAUSE",
            "300,GHOST,RESUME",
        ],
        "expected": [
            {"ticket_id": "A", "used_ms": 400, "breached": False, "status": "open"}
        ]
    })

    # -------------------------------------------------------------------------
    # Test 9: Out-of-order events
    # -------------------------------------------------------------------------
    # Events given in completely reverse chronological order:
    # 600,T1,CLOSE
    # 400,T1,RESUME
    # 250,T1,PAUSE
    # 100,T1,OPEN
    # Sorted order: 100 OPEN (RUNNING), 250 PAUSE (used 150), 400 RESUME (RUNNING), 600 CLOSE (used 150 + 200 = 350)
    tests.append({
        "name": "Out-of-order event timestamps",
        "stream": [
            "600,T1,CLOSE",
            "400,T1,RESUME",
            "250,T1,PAUSE",
            "100,T1,OPEN",
        ],
        "expected": [
            {"ticket_id": "T1", "used_ms": 350, "breached": False, "status": "closed"}
        ]
    })

    # -------------------------------------------------------------------------
    # Test 10: Equal timestamps (Ties) and Stable Sort Preservation
    # -------------------------------------------------------------------------
    # Scenario A: Multiple transitions at exact same timestamp
    # 100: OPEN -> PAUSE -> RESUME -> CLOSE
    # used_ms must be 0, status closed
    tests.append({
        "name": "Ties: Multiple events at identical timestamp",
        "stream": [
            "100,T1,OPEN",
            "100,T1,PAUSE",
            "100,T1,RESUME",
            "100,T1,CLOSE",
        ],
        "expected": [
            {"ticket_id": "T1", "used_ms": 0, "breached": False, "status": "closed"}
        ]
    })

    # Scenario B: Stable sort preserves order among tied events arriving out-of-order
    # Stream order:
    # Index 0: 200,T2,CLOSE
    # Index 1: 100,T2,PAUSE
    # Index 2: 100,T2,OPEN
    # Stable sort by timestamp:
    # Index 1 (100, PAUSE) is processed BEFORE Index 2 (100, OPEN).
    # At t=100, state is NOT_OPENED, so Index 1 PAUSE is ignored!
    # Then Index 2 OPEN sets state to RUNNING at 100.
    # At t=200, CLOSE sets state to CLOSED.
    # used_ms = 200 - 100 = 100.
    # (If stable sort failed and OPEN was processed before PAUSE, used_ms would be 0!)
    tests.append({
        "name": "Ties: Stable sort preserves stream order on ties",
        "stream": [
            "200,T2,CLOSE",
            "100,T2,PAUSE",
            "100,T2,OPEN",
        ],
        "expected": [
            {"ticket_id": "T2", "used_ms": 100, "breached": False, "status": "closed"}
        ]
    })

    # Scenario C: Stable sort between OPEN and PAUSE at t=100
    # Stream:
    # Index 0: 100,T3,OPEN
    # Index 1: 100,T3,PAUSE
    # Index 2: 300,OTHER,OPEN
    # Chronology:
    # t=100: OPEN (RUNNING), PAUSE (PAUSED, used = 0)
    # t=300: OTHER OPEN (RUNNING at 300)
    # T3 is PAUSED at end of stream, used = 0, status = "open".
    # OTHER is RUNNING at end of stream (now=300), used = 0, status = "open".
    tests.append({
        "name": "Ties: OPEN then PAUSE at identical timestamp",
        "stream": [
            "100,T3,OPEN",
            "100,T3,PAUSE",
            "300,OTHER,OPEN",
        ],
        "expected": [
            {"ticket_id": "OTHER", "used_ms": 0, "breached": False, "status": "open"},
            {"ticket_id": "T3", "used_ms": 0, "breached": False, "status": "open"},
        ]
    })

    # -------------------------------------------------------------------------
    # Test 11: Comprehensive State-Transition Table Coverage (All 20 cells)
    # -------------------------------------------------------------------------
    # Cell breakdown:
    # 1. NOT_OPENED + PAUSE  -> ignored (T01 at 10)
    # 2. NOT_OPENED + RESUME -> ignored (T01 at 20)
    # 3. NOT_OPENED + CLOSE  -> ignored (T01 at 30)
    # 4. NOT_OPENED + REOPEN -> ignored (T01 at 40)
    # 5. NOT_OPENED + OPEN   -> to RUNNING, used starts at 0 (T01 at 50)
    # 6. RUNNING + OPEN      -> ignored (T02 at 200)
    # 7. RUNNING + RESUME    -> ignored (T02 at 300)
    # 8. RUNNING + REOPEN    -> ignored (T02 at 400)
    # 9. RUNNING + PAUSE     -> to PAUSED, accumulates time (T03 at 200, T04 at 200)
    # 10. RUNNING + CLOSE    -> to CLOSED, accumulates time (T01 at 150, T02 at 600)
    # 11. PAUSED + OPEN      -> ignored (T03 at 250)
    # 12. PAUSED + PAUSE     -> ignored (T03 at 300)
    # 13. PAUSED + REOPEN    -> ignored (T03 at 350)
    # 14. PAUSED + RESUME    -> to RUNNING, resumes time (T03 at 400)
    # 15. PAUSED + CLOSE     -> to CLOSED, pause time does not count (T04 at 500)
    # 16. CLOSED + PAUSE     -> ignored (T05 at 250)
    # 17. CLOSED + RESUME    -> ignored (T05 at 300)
    # 18. CLOSED + CLOSE     -> ignored (T05 at 350)
    # 19. CLOSED + OPEN      -> to RUNNING, resets used to 0 (T06 at 300)
    # 20. CLOSED + REOPEN    -> to RUNNING, continues used (T07 at 300)
    state_table_stream = [
        # T01: NOT_OPENED ignored events, then OPEN, then CLOSE
        "10,T01_NO_IGN,PAUSE",
        "20,T01_NO_IGN,RESUME",
        "30,T01_NO_IGN,CLOSE",
        "40,T01_NO_IGN,REOPEN",
        "50,T01_NO_IGN,OPEN",
        "150,T01_NO_IGN,CLOSE",

        # T02: RUNNING ignored events (OPEN, RESUME, REOPEN), then CLOSE
        "100,T02_RUN_IGN,OPEN",
        "200,T02_RUN_IGN,OPEN",
        "300,T02_RUN_IGN,RESUME",
        "400,T02_RUN_IGN,REOPEN",
        "600,T02_RUN_IGN,CLOSE",

        # T03: PAUSED ignored events (OPEN, PAUSE, REOPEN), then RESUME, CLOSE
        "100,T03_PAU_IGN,OPEN",
        "200,T03_PAU_IGN,PAUSE",
        "250,T03_PAU_IGN,OPEN",
        "300,T03_PAU_IGN,PAUSE",
        "350,T03_PAU_IGN,REOPEN",
        "400,T03_PAU_IGN,RESUME",
        "600,T03_PAU_IGN,CLOSE",

        # T04: PAUSED to CLOSE (stretch between pause and close does not count)
        "100,T04_PAU_CLOSE,OPEN",
        "200,T04_PAU_CLOSE,PAUSE",
        "500,T04_PAU_CLOSE,CLOSE",

        # T05: CLOSED ignored events (PAUSE, RESUME, CLOSE)
        "100,T05_CLS_IGN,OPEN",
        "200,T05_CLS_IGN,CLOSE",
        "250,T05_CLS_IGN,PAUSE",
        "300,T05_CLS_IGN,RESUME",
        "350,T05_CLS_IGN,CLOSE",

        # T06: CLOSED + OPEN resets used time to 0
        "100,T06_CLS_OPEN,OPEN",
        "200,T06_CLS_OPEN,CLOSE",
        "300,T06_CLS_OPEN,OPEN",
        "450,T06_CLS_OPEN,CLOSE",

        # T07: CLOSED + REOPEN continues used time
        "100,T07_CLS_REOPEN,OPEN",
        "200,T07_CLS_REOPEN,CLOSE",
        "300,T07_CLS_REOPEN,REOPEN",
        "450,T07_CLS_REOPEN,CLOSE",
    ]
    tests.append({
        "name": "State-transition table: all 20 cells covered",
        "stream": state_table_stream,
        "expected": [
            {"ticket_id": "T01_NO_IGN", "used_ms": 100, "breached": False, "status": "closed"},
            {"ticket_id": "T02_RUN_IGN", "used_ms": 500, "breached": False, "status": "closed"},
            {"ticket_id": "T03_PAU_IGN", "used_ms": 300, "breached": False, "status": "closed"},
            {"ticket_id": "T04_PAU_CLOSE", "used_ms": 100, "breached": False, "status": "closed"},
            {"ticket_id": "T05_CLS_IGN", "used_ms": 100, "breached": False, "status": "closed"},
            {"ticket_id": "T06_CLS_OPEN", "used_ms": 150, "breached": False, "status": "closed"},
            {"ticket_id": "T07_CLS_REOPEN", "used_ms": 250, "breached": False, "status": "closed"},
        ]
    })

    # -------------------------------------------------------------------------
    # Test 12: SLA Boundaries & Status Combinations
    # SLA Limit: 14,400,000 ms.
    # Breached is True ONLY if used_ms > 14,400,000.
    # Exactly 14,400,000 does not breach.
    # Applies to open tickets too.
    # -------------------------------------------------------------------------
    # We construct 9 tickets covering all combinations:
    # - CLOSED: exactly at limit, strictly above limit, strictly below limit
    # - RUNNING (open): exactly at limit, strictly above limit, strictly below limit
    # - PAUSED (open): exactly at limit, strictly above limit, strictly below limit
    sla_boundary_stream = [
        # CLOSED
        "0,T_CLOSED_EXACT,OPEN",
        "14400000,T_CLOSED_EXACT,CLOSE",

        "0,T_CLOSED_OVER,OPEN",
        "14400001,T_CLOSED_OVER,CLOSE",

        "0,T_CLOSED_UNDER,OPEN",
        "14399999,T_CLOSED_UNDER,CLOSE",

        # RUNNING (open, counts up to now = 14400001)
        "1,T_OPEN_EXACT,OPEN",       # used = 14400001 - 1 = 14400000 -> not breached
        "0,T_OPEN_OVER,OPEN",        # used = 14400001 - 0 = 14400001 -> breached
        "2,T_OPEN_UNDER,OPEN",       # used = 14400001 - 2 = 14399999 -> not breached

        # PAUSED (open, counts only to its pause)
        "0,T_PAUSED_EXACT,OPEN",
        "14400000,T_PAUSED_EXACT,PAUSE",

        "0,T_PAUSED_OVER,OPEN",
        "14400001,T_PAUSED_OVER,PAUSE",

        "0,T_PAUSED_UNDER,OPEN",
        "14399999,T_PAUSED_UNDER,PAUSE",
    ]
    tests.append({
        "name": "SLA boundary exact 14,400,000 ms and status combinations",
        "stream": sla_boundary_stream,
        "expected": [
            {"ticket_id": "T_CLOSED_EXACT", "used_ms": 14400000, "breached": False, "status": "closed"},
            {"ticket_id": "T_CLOSED_OVER", "used_ms": 14400001, "breached": True, "status": "closed"},
            {"ticket_id": "T_CLOSED_UNDER", "used_ms": 14399999, "breached": False, "status": "closed"},
            {"ticket_id": "T_OPEN_EXACT", "used_ms": 14400000, "breached": False, "status": "open"},
            {"ticket_id": "T_OPEN_OVER", "used_ms": 14400001, "breached": True, "status": "open"},
            {"ticket_id": "T_OPEN_UNDER", "used_ms": 14399999, "breached": False, "status": "open"},
            {"ticket_id": "T_PAUSED_EXACT", "used_ms": 14400000, "breached": False, "status": "open"},
            {"ticket_id": "T_PAUSED_OVER", "used_ms": 14400001, "breached": True, "status": "open"},
            {"ticket_id": "T_PAUSED_UNDER", "used_ms": 14399999, "breached": False, "status": "open"},
        ]
    })

    # -------------------------------------------------------------------------
    # Test 13: Ticket ID Case Sensitivity and Code-Point Sorting Order
    # -------------------------------------------------------------------------
    # Spec: "ticket IDs are case-sensitive: t1 and T1 are different tickets"
    # "sorted by ticket_id ascending in Python's default string order (code-point order, so 'T10' sorts before 'T2')"
    case_sort_stream = [
        "0,t2,OPEN",
        "10,t2,CLOSE",
        "0,t10,OPEN",
        "20,t10,CLOSE",
        "0,t1,OPEN",
        "30,t1,CLOSE",
        "0,T2,OPEN",
        "40,T2,CLOSE",
        "0,T10,OPEN",
        "50,T10,CLOSE",
        "0,T1,OPEN",
        "60,T1,CLOSE",
    ]
    tests.append({
        "name": "Ticket ID case sensitivity and code-point sort order",
        "stream": case_sort_stream,
        "expected": [
            {"ticket_id": "T1", "used_ms": 60, "breached": False, "status": "closed"},
            {"ticket_id": "T10", "used_ms": 50, "breached": False, "status": "closed"},
            {"ticket_id": "T2", "used_ms": 40, "breached": False, "status": "closed"},
            {"ticket_id": "t1", "used_ms": 30, "breached": False, "status": "closed"},
            {"ticket_id": "t10", "used_ms": 20, "breached": False, "status": "closed"},
            {"ticket_id": "t2", "used_ms": 10, "breached": False, "status": "closed"},
        ]
    })

    # -------------------------------------------------------------------------
    # Test 14: Complex Lifecycle: Multi-cycle transitions
    # -------------------------------------------------------------------------
    # Ticket CYCLE:
    # 100: OPEN -> RUNNING
    # 200: PAUSE -> PAUSED (used = 100)
    # 250: RESUME -> RUNNING
    # 350: PAUSE -> PAUSED (used = 100 + 100 = 200)
    # 400: RESUME -> RUNNING
    # 500: CLOSE -> CLOSED (used = 200 + 100 = 300)
    # 600: REOPEN -> RUNNING (used continues from 300)
    # 700: CLOSE -> CLOSED (used = 300 + 100 = 400)
    # 800: OPEN -> RUNNING (used resets to 0!)
    # 950: PAUSE -> PAUSED (used = 150)
    # Ticket DUMMY:
    # 1000: OPEN
    # 1000: CLOSE (sets now = 1000)
    # CYCLE ends PAUSED at 950, so used = 150, status = "open".
    # DUMMY ends CLOSED, used = 0, status = "closed".
    complex_lifecycle_stream = [
        "100,CYCLE,OPEN",
        "200,CYCLE,PAUSE",
        "250,CYCLE,RESUME",
        "350,CYCLE,PAUSE",
        "400,CYCLE,RESUME",
        "500,CYCLE,CLOSE",
        "600,CYCLE,REOPEN",
        "700,CYCLE,CLOSE",
        "800,CYCLE,OPEN",
        "950,CYCLE,PAUSE",
        "1000,DUMMY,OPEN",
        "1000,DUMMY,CLOSE",
    ]
    tests.append({
        "name": "Complex multi-cycle lifecycle with reset and continue",
        "stream": complex_lifecycle_stream,
        "expected": [
            {"ticket_id": "CYCLE", "used_ms": 150, "breached": False, "status": "open"},
            {"ticket_id": "DUMMY", "used_ms": 0, "breached": False, "status": "closed"},
        ]
    })

    # -------------------------------------------------------------------------
    # Test 15: Whitespace trimming on fields and records
    # -------------------------------------------------------------------------
    # Leading/trailing spaces and tabs on line and on individual fields
    whitespace_stream = [
        "  00100  ,  TICKET_WS  ,  OPEN  \t\r\n",
        "\t 00250 ,\t TICKET_WS \t, CLOSE \n",
    ]
    tests.append({
        "name": "Whitespace trimming on records and fields",
        "stream": whitespace_stream,
        "expected": [
            {"ticket_id": "TICKET_WS", "used_ms": 150, "breached": False, "status": "closed"}
        ]
    })

    # -------------------------------------------------------------------------
    # Test 16: Zero timestamp and leading zeros
    # -------------------------------------------------------------------------
    zero_stream = [
        "000000,T0,OPEN",
        "000000,T0,CLOSE",
    ]
    tests.append({
        "name": "Timestamp zero and leading zeros",
        "stream": zero_stream,
        "expected": [
            {"ticket_id": "T0", "used_ms": 0, "breached": False, "status": "closed"}
        ]
    })

    # -------------------------------------------------------------------------
    # Test 17: Valid ticket ID with punctuation and internal spaces
    # -------------------------------------------------------------------------
    punct_stream = [
        "100,T-1#A B,OPEN",
        "200,T-1#A B,CLOSE",
    ]
    tests.append({
        "name": "Ticket ID with special characters and internal spaces",
        "stream": punct_stream,
        "expected": [
            {"ticket_id": "T-1#A B", "used_ms": 100, "breached": False, "status": "closed"}
        ]
    })

    # -------------------------------------------------------------------------
    # Test 18: Malformed lines mixed with well-formed lines
    # Malformed lines with huge timestamps must not affect "now" for running ticket
    # -------------------------------------------------------------------------
    mixed_stream = [
        "  \n",
        "100,VALID,OPEN",
        "not,a,valid,csv,line",
        "999999999,INVALID_TS,OPEN,EXTRA",
        "999999999, ,OPEN",
        "999999999,VALID,INVALID_EVENT",
        "200,RUNNING_T,OPEN",
        "400,VALID,CLOSE",
    ]
    # Well-formed lines:
    # 100,VALID,OPEN
    # 200,RUNNING_T,OPEN
    # 400,VALID,CLOSE
    # Largest well-formed timestamp: 400 ("now" = 400).
    # VALID: 400 - 100 = 300, closed.
    # RUNNING_T: 400 - 200 = 200, open.
    tests.append({
        "name": "Malformed lines mixed with well-formed lines",
        "stream": mixed_stream,
        "expected": [
            {"ticket_id": "RUNNING_T", "used_ms": 200, "breached": False, "status": "open"},
            {"ticket_id": "VALID", "used_ms": 300, "breached": False, "status": "closed"},
        ]
    })

    # -------------------------------------------------------------------------
    # Execute Test Suite
    # -------------------------------------------------------------------------
    passed = 0
    failed = 0

    print("=" * 70)
    print("RUNNING ADVERSARIAL SLA CLOCK TEST SUITE")
    print("=" * 70)

    for i, test in enumerate(tests, 1):
        name = test["name"]
        stream = test["stream"]
        expected = test["expected"]

        try:
            result = solution.compute_sla(stream)
        except Exception as e:
            print(f"[FAIL] Test {i:02d}: {name}")
            print(f"       Raised unexpected exception: {e!r}")
            failed += 1
            continue

        valid_fmt, err_msg = validate_result_format(result, name)
        if not valid_fmt:
            print(f"[FAIL] Test {i:02d}: {name}")
            print(f"       Output validation error: {err_msg}")
            print(f"       Got: {result!r}")
            failed += 1
            continue

        if result != expected:
            print(f"[FAIL] Test {i:02d}: {name}")
            print(f"       Expected: {expected!r}")
            print(f"       Got:      {result!r}")
            failed += 1
        else:
            print(f"[PASS] Test {i:02d}: {name}")
            passed += 1

    print("=" * 70)
    print(f"SUMMARY: {passed} passed, {failed} failed out of {len(tests)} tests")
    print("=" * 70)

    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    run_tests()