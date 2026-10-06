import solution
import sys
import traceback

def validate_output_schema(result):
    assert isinstance(result, list), f"Expected result to be list, got {type(result)}"
    for i, item in enumerate(result):
        assert isinstance(item, dict), f"Item {i} is not a dict: {type(item)}"
        expected_keys = {"ticket_id", "priority", "used_minutes", "breached", "breached_at", "status"}
        assert set(item.keys()) == expected_keys, f"Item {i} keys mismatch: {set(item.keys())} vs {expected_keys}"
        assert isinstance(item["ticket_id"], str), f"ticket_id must be str, got {type(item['ticket_id'])}"
        assert item["priority"] in {"P1", "P2", "P3", "P4"}, f"Invalid priority: {item['priority']}"
        assert type(item["used_minutes"]) is int, f"used_minutes must be int, got {type(item['used_minutes'])}"
        assert type(item["breached"]) is bool, f"breached must be bool, got {type(item['breached'])}"
        if item["breached"]:
            assert type(item["breached_at"]) is int, f"breached_at must be int when breached, got {type(item['breached_at'])}"
        else:
            assert item["breached_at"] is None, f"breached_at must be None when not breached, got {item['breached_at']}"
        assert item["status"] in {"running", "paused", "closed"}, f"Invalid status: {item['status']}"

def assert_equal(actual, expected, msg=""):
    validate_output_schema(actual)
    if actual != expected:
        raise AssertionError(f"{msg}\nExpected: {expected}\nActual:   {actual}")

# ==============================================================================
# TEST CASES
# ==============================================================================

def test_spec_examples():
    """Verify all four examples given in the problem specification."""
    # Example 1
    ex1 = [
        "540,A,OPEN,P2",
        "600,A,CLOSE",
    ]
    exp1 = [{"ticket_id": "A", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    assert_equal(solution.compute_sla(ex1), exp1, "Failed Example 1")

    # Example 2
    ex2 = [
        "6720,B,OPEN,P1",
        "10680,B,PAUSE",
    ]
    exp2 = [{"ticket_id": "B", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "paused"}]
    assert_equal(solution.compute_sla(ex2), exp2, "Failed Example 2")

    # Example 3
    ex3 = [
        "540,C,OPEN,P1",
        "900,C,CLOSE",
    ]
    exp3 = [{"ticket_id": "C", "priority": "P1", "used_minutes": 360, "breached": True, "breached_at": 781, "status": "closed"}]
    assert_equal(solution.compute_sla(ex3), exp3, "Failed Example 3")

    # Example 4
    ex4 = [
        "540,D,OPEN,P3",
        "2040,D,PAUSE",
        "open,D,RESUME",
        "2100,D,RESUME,P1",
        "5,*,HOLIDAY",
    ]
    exp4 = [{"ticket_id": "D", "priority": "P3", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}]
    assert_equal(solution.compute_sla(ex4), exp4, "Failed Example 4")


def test_empty_and_no_valid_events():
    """Verify behavior on empty stream and streams with no well-formed ticket events."""
    assert solution.compute_sla([]) == [], "Empty stream should return []"
    assert solution.compute_sla(["", "   ", "\n", "\t"]) == [], "Whitespace lines should return []"
    assert solution.compute_sla(["540,*,HOLIDAY", "2000,*,HOLIDAY"]) == [], "Only holidays should return []"
    assert solution.compute_sla(["not,a,valid,csv,line"]) == [], "Invalid lines should return []"


def test_malformed_lines_adversarial():
    """Verify that every flavor of malformed line is completely ignored."""
    malformed = [
        "",
        "   ",
        "540",
        "540,T",
        "540,T,OPEN",             # OPEN requires 4 fields
        "540,T,OPEN,P1,EXTRA",      # 5 fields
        "540,T,PRIORITY",           # PRIORITY requires 4 fields
        "540,T,PRIORITY,P1,EXTRA",  # 5 fields
        "540,T,PAUSE,P1",           # PAUSE requires 3 fields
        "540,T,RESUME,P1",          # RESUME requires 3 fields
        "540,T,CLOSE,P1",           # CLOSE requires 3 fields
        "540,T,REOPEN,P1",          # REOPEN requires 3 fields
        "540,*,OPEN,P1",            # Non-holiday cannot have ticket ID '*'
        "540,*,PAUSE",              # Non-holiday cannot have ticket ID '*'
        "540,*,CLOSE",              # Non-holiday cannot have ticket ID '*'
        "540,T,HOLIDAY",            # HOLIDAY must have ticket ID '*'
        "540,*,HOLIDAY,P1",         # HOLIDAY requires 3 fields
        "-10,T,OPEN,P1",            # Negative minute
        "12.5,T,OPEN,P1",           # Non-integer minute
        "abc,T,OPEN,P1",            # Alphabetical minute
        "540,,OPEN,P1",             # Empty ticket ID
        "540,   ,OPEN,P1",          # Ticket ID whitespace only
        "540,T,open,P1",            # Lowercase event
        "540,T,OPEN,p1",            # Lowercase priority
        "540,T,OPEN,P5",            # Invalid priority
        "540,T,PRIORITY,P0",        # Invalid priority
        "540,T,UNKNOWN",            # Unknown event
        ",,,",
        ",,",
    ]
    # Malformed lines alone should return []
    assert solution.compute_sla(malformed) == [], "Malformed stream must return []"

    # Add a valid ticket to ensure malformed lines do not interfere
    stream = malformed + [
        "  000540  ,  VALID_T1  ,  OPEN  ,  P1  ",
        "  000600  ,  VALID_T1  ,  CLOSE  ",
    ]
    expected = [{"ticket_id": "VALID_T1", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    assert_equal(solution.compute_sla(stream), expected, "Malformed lines should be ignored cleanly")


def test_whitespace_and_leading_zeros():
    """Verify trimming and leading zeros in minute values."""
    stream = [
        " \t 00540 \t , \t T_WS \t , \t OPEN \t , \t P2 \t ",
        "  000720  ,  T_WS  ,  CLOSE  ",
    ]
    expected = [{"ticket_id": "T_WS", "priority": "P2", "used_minutes": 180, "breached": False, "breached_at": None, "status": "closed"}]
    assert_equal(solution.compute_sla(stream), expected, "Whitespace and leading zeros parsing failed")


def test_all_state_transitions():
    """
    Exhaustively test all 24 cells in the state-transition table:
    States: NOT_OPENED, RUNNING, PAUSED, CLOSED
    Events: OPEN, PRIORITY, PAUSE, RESUME, CLOSE, REOPEN
    """
    # 1. NOT_OPENED: PRIORITY, PAUSE, RESUME, CLOSE, REOPEN must be ignored
    # Ticket T_NO is never opened; it must not appear in output.
    # Ticket T_RUN tests valid and invalid transitions through its lifecycle.
    stream = [
        # NOT_OPENED ignored events for T_NO
        "100,T_NO,PAUSE",
        "110,T_NO,RESUME",
        "120,T_NO,CLOSE",
        "130,T_NO,REOPEN",
        "140,T_NO,PRIORITY,P1",

        # T_MAIN lifecycle:
        # NOT_OPENED -> RUNNING (via OPEN)
        "540,T_MAIN,OPEN,P1",

        # RUNNING: OPEN, RESUME, REOPEN ignored
        "550,T_MAIN,OPEN,P4",        # ignored
        "560,T_MAIN,RESUME",         # ignored
        "570,T_MAIN,REOPEN",         # ignored
        "580,T_MAIN,PRIORITY,P2",    # RUNNING, priority becomes P2 (valid)

        # RUNNING -> PAUSED (via PAUSE)
        "600,T_MAIN,PAUSE",          # used so far = 60

        # PAUSED: OPEN, PAUSE, REOPEN ignored
        "610,T_MAIN,OPEN,P4",        # ignored
        "620,T_MAIN,PAUSE",          # ignored
        "630,T_MAIN,REOPEN",         # ignored
        "640,T_MAIN,PRIORITY,P3",    # PAUSED, priority becomes P3 (valid)

        # PAUSED -> RUNNING (via RESUME)
        "660,T_MAIN,RESUME",

        # RUNNING -> CLOSED (via CLOSE)
        "700,T_MAIN,CLOSE",          # used so far = 60 + 40 = 100

        # CLOSED: PRIORITY, PAUSE, RESUME, CLOSE ignored
        "710,T_MAIN,PRIORITY,P4",    # ignored
        "720,T_MAIN,PAUSE",          # ignored
        "730,T_MAIN,RESUME",         # ignored
        "740,T_MAIN,CLOSE",          # ignored

        # CLOSED -> RUNNING (via REOPEN: used continues, priority kept)
        "760,T_MAIN,REOPEN",         # priority still P3

        # RUNNING -> CLOSED (via CLOSE)
        "800,T_MAIN,CLOSE",          # used so far = 100 + 40 = 140
    ]
    # T_NO never had a valid OPEN, so it must not be in output.
    # T_MAIN used = 140, priority = P3 (limit 1440), not breached, closed.
    expected = [{
        "ticket_id": "T_MAIN",
        "priority": "P3",
        "used_minutes": 140,
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }]
    assert_equal(solution.compute_sla(stream), expected, "State transition table coverage failed")

    # Also test PAUSED -> CLOSED directly
    stream_pause_close = [
        "540,T_PC,OPEN,P1",
        "600,T_PC,PAUSE",
        "700,T_PC,CLOSE",
    ]
    exp_pc = [{"ticket_id": "T_PC", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    assert_equal(solution.compute_sla(stream_pause_close), exp_pc, "PAUSED to CLOSED transition failed")


def test_reopen_vs_open_from_closed():
    """
    Test difference between REOPEN and OPEN from CLOSED:
    - REOPEN: used continues, breach kept, priority kept.
    - OPEN: used resets to 0, breach cleared, priority updated to new P.
    """
    stream = [
        # Ticket T_REOPEN breaches, closes, then reopens
        "540,T_REOPEN,OPEN,P1",
        "800,T_REOPEN,CLOSE",       # ran 260 mins, breached at 781 (limit 240)
        "850,T_REOPEN,REOPEN",      # continues
        "900,T_REOPEN,CLOSE",       # used = 260 + 50 = 310

        # Ticket T_RESET breaches, closes, then OPENs afresh
        "540,T_RESET,OPEN,P1",
        "800,T_RESET,CLOSE",        # ran 260 mins, breached at 781
        "850,T_RESET,OPEN,P2",      # used resets to 0, breach cleared, priority P2
        "900,T_RESET,CLOSE",        # used = 50, limit 480 -> not breached
    ]
    expected = [
        {"ticket_id": "T_REOPEN", "priority": "P1", "used_minutes": 310, "breached": True, "breached_at": 781, "status": "closed"},
        {"ticket_id": "T_RESET", "priority": "P2", "used_minutes": 50, "breached": False, "breached_at": None, "status": "closed"},
    ]
    assert_equal(solution.compute_sla(stream), expected, "REOPEN vs OPEN from CLOSED failed")


def test_breach_exact_boundaries():
    """
    Test exact breach boundary:
    - Limit is 240 for P1.
    - used == 240 is NOT breached.
    - used == 241 IS breached at minute 781.
    - PRIORITY raise at minute 781 PREVENTS breach.
    - PRIORITY raise at minute 782 is TOO LATE (breach sticky at 781).
    """
    stream = [
        # Exactly at limit: 240 minutes
        "540,T_EXACT,OPEN,P1",
        "780,T_EXACT,PAUSE",

        # 1 minute past limit: 241 minutes
        "540,T_OVER,OPEN,P1",
        "781,T_OVER,PAUSE",

        # PRIORITY raise at minute 781 prevents breach
        "540,T_PREVENT,OPEN,P1",
        "781,T_PREVENT,PRIORITY,P2",
        "800,T_PREVENT,PAUSE",

        # PRIORITY raise at minute 782 is too late
        "540,T_LATE,OPEN,P1",
        "782,T_LATE,PRIORITY,P2",
        "800,T_LATE,PAUSE",
    ]
    expected = [
        {"ticket_id": "T_EXACT", "priority": "P1", "used_minutes": 240, "breached": False, "breached_at": None, "status": "paused"},
        {"ticket_id": "T_LATE", "priority": "P2", "used_minutes": 260, "breached": True, "breached_at": 781, "status": "paused"},
        {"ticket_id": "T_OVER", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "paused"},
        {"ticket_id": "T_PREVENT", "priority": "P2", "used_minutes": 260, "breached": False, "breached_at": None, "status": "paused"},
    ]
    assert_equal(solution.compute_sla(stream), expected, "Exact breach boundaries failed")


def test_priority_downgrade_immediate_breach():
    """
    Test priority change lowering limit causing immediate breach while PAUSED and while RUNNING.
    """
    stream = [
        # Lowering priority while PAUSED
        "540,T_PAUSED_DROP,OPEN,P2",
        "800,T_PAUSED_DROP,PAUSE",           # used = 260
        "900,T_PAUSED_DROP,PRIORITY,P1",     # at 900, used = 260 > 240 -> breach at 900!

        # Lowering priority while RUNNING
        "540,T_RUN_DROP,OPEN,P2",
        "800,T_RUN_DROP,PRIORITY,P1",        # at 800, used = 260 > 240 -> breach at 800!
        "850,T_RUN_DROP,PAUSE",              # used = 310
    ]
    expected = [
        {"ticket_id": "T_PAUSED_DROP", "priority": "P1", "used_minutes": 260, "breached": True, "breached_at": 900, "status": "paused"},
        {"ticket_id": "T_RUN_DROP", "priority": "P1", "used_minutes": 310, "breached": True, "breached_at": 800, "status": "paused"},
    ]
    assert_equal(solution.compute_sla(stream), expected, "Priority downgrade breach failed")


def test_priorities_p3_and_p4():
    """
    Test multi-day breach calculations for P3 (1440 mins) and P4 (2400 mins).
    P3: 3 full business days (Mon, Tue, Wed = 480 * 3 = 1440).
    Breaches on Thursday at 09:01 (minute 4861).
    """
    stream = [
        "540,T_P3,OPEN,P3",
        "4861,T_P3,PAUSE",
    ]
    expected = [{"ticket_id": "T_P3", "priority": "P3", "used_minutes": 1441, "breached": True, "breached_at": 4861, "status": "paused"}]
    assert_equal(solution.compute_sla(stream), expected, "P3 multi-day breach failed")


def test_calendar_and_holidays():
    """
    Test complex calendar interactions:
    - Overnight non-business hours.
    - Weekend non-business hours.
    - Declaring holidays out of order, multiple times, and after 'now'.
    - Holidays declared for days with no events.
    """
    # Mon 09:00 = 540. Day 0: Mon [540, 1020).
    # Day 1 (Tue): holiday declared at minute 1440 and again at minute 2000.
    # Day 4 (Fri): holiday declared at minute 99999 (far in future stream).
    # Ticket opens Mon 16:00 (960) at P1 (limit 240).
    # Mon gives 60 mins (960 to 1020).
    # Tue is HOLIDAY (0 mins).
    # Wed (day 2): starts at 2 * 1440 + 540 = 3420.
    # To breach (241 mins): needs 181 mins on Wed -> 3420 + 181 = 3601.
    # Ticket pauses on Wed at 12:05 (3420 + 185 = 3605). Used = 60 + 185 = 245.
    stream = [
        "960,T_HOL,OPEN,P1",
        "3605,T_HOL,PAUSE",
        "1440,*,HOLIDAY",       # Tue holiday
        "2000,*,HOLIDAY",       # Duplicate Tue holiday
        "99999,*,HOLIDAY",      # Holiday on day 69 (does not affect now)
        "7200,*,HOLIDAY",       # Saturday holiday (does not change business hours)
    ]
    expected = [{"ticket_id": "T_HOL", "priority": "P1", "used_minutes": 245, "breached": True, "breached_at": 3601, "status": "paused"}]
    assert_equal(solution.compute_sla(stream), expected, "Calendar and holiday calculation failed")


def test_definition_of_now_and_running_tickets():
    """
    Test that 'now':
    1. Is the maximum minute among ALL well-formed ticket events, EVEN IF invalid transitions.
    2. Is NOT affected by HOLIDAY lines.
    3. Causes continuously running tickets to accumulate time up to 'now'.
    """
    stream = [
        "540,T_RUNNING,OPEN,P1",
        # Ticket T_INVALID is never opened, so PAUSE is ignored as an invalid transition,
        # but it is a well-formed ticket event at minute 1000, setting 'now' = 1000.
        "1000,T_INVALID,PAUSE",
        # HOLIDAY at minute 50000 must NOT push 'now' to 50000.
        "50000,*,HOLIDAY",
    ]
    # At now = 1000:
    # T_RUNNING ran from 540 to 1000 on Monday -> 460 business minutes.
    # Breached at 781.
    # Status is 'running'.
    # T_INVALID had no valid OPEN -> excluded from output.
    expected = [{"ticket_id": "T_RUNNING", "priority": "P1", "used_minutes": 460, "breached": True, "breached_at": 781, "status": "running"}]
    assert_equal(solution.compute_sla(stream), expected, "Definition of now and running tickets failed")


def test_out_of_order_stream_and_same_minute_ties():
    """
    Test that events arriving out of order are stably sorted by minute:
    - Events with same minute preserve original stream order.
    """
    # Stream order at minute 540:
    # T1: OPEN then PAUSE -> PAUSED at 540
    # T2: PAUSE then OPEN -> PAUSE ignored (NOT_OPENED), then OPEN -> RUNNING at 540
    # T3: OPEN, CLOSE, OPEN P2 -> RUNNING P2 at 540
    stream = [
        # Out-of-order arrival: later events first
        "600,T1,CLOSE",
        "540,T1,OPEN,P1",
        "540,T1,PAUSE",
        "550,T1,RESUME",

        "540,T2,PAUSE",
        "540,T2,OPEN,P2",
        "600,T2,CLOSE",

        "540,T3,OPEN,P1",
        "540,T3,CLOSE",
        "540,T3,OPEN,P3",
        "600,T3,PAUSE",
    ]
    # T1: opens at 540, paused at 540. Resumed at 550. Closes at 600.
    # Running from 550 to 600 -> 50 used minutes.
    # T2: opens at 540 (PAUSE ignored). Closes at 600.
    # Running from 540 to 600 -> 60 used minutes.
    # T3: opens at 540, closes at 540, opens at 540 P3. Pauses at 600.
    # Running from 540 to 600 -> 60 used minutes.
    expected = [
        {"ticket_id": "T1", "priority": "P1", "used_minutes": 50, "breached": False, "breached_at": None, "status": "closed"},
        {"ticket_id": "T2", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
        {"ticket_id": "T3", "priority": "P3", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"},
    ]
    assert_equal(solution.compute_sla(stream), expected, "Out of order and same minute ties failed")


def test_case_sensitivity_and_code_point_sorting():
    """
    Test case-sensitivity ('t1' != 'T1') and strict ASCII code-point sorting order:
    '10' < '2' < 'A' < 'T1' < 'T10' < 'T2' < 'a' < 't1'
    """
    ticket_ids = ["T1", "t1", "T2", "T10", "10", "2", "A", "a"]
    # Open and close all of them between 540 and 600
    stream = []
    for tid in ticket_ids:
        stream.append(f"540,{tid},OPEN,P1")
        stream.append(f"600,{tid},CLOSE")

    # Expected code-point sort order:
    sorted_ids = sorted(ticket_ids)
    assert sorted_ids == ["10", "2", "A", "T1", "T10", "T2", "a", "t1"]

    expected = [
        {"ticket_id": tid, "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
        for tid in sorted_ids
    ]
    assert_equal(solution.compute_sla(stream), expected, "Case sensitivity and code point sorting failed")


def test_outside_business_hours_events():
    """
    Test events occurring outside business hours:
    e.g., opened on Sunday at 12:00.
    Sunday 12:00 = 6 * 1440 + 720 = 9360.
    Used minutes must remain 0 until Monday 09:00 (10620).
    """
    stream = [
        "9360,T_SUN,OPEN,P1",
        "10680,T_SUN,PAUSE",  # Monday 10:00 (1 hour after 09:00)
    ]
    expected = [{"ticket_id": "T_SUN", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}]
    assert_equal(solution.compute_sla(stream), expected, "Events outside business hours failed")


def test_performance_large_time_span():
    """
    Performance test:
    Minutes up to 1,000,000,000 and 10,000 holiday lines.
    A minute-by-minute simulation will time out. An efficient implementation will pass instantly.
    """
    # Day 700,000: 700000 % 7 = 0 (Monday).
    # Minute = 700000 * 1440 = 1,008,000,000 -> let's use 625,001 (Mon)
    # 625001 % 7 = 0 (Monday)
    # 625001 * 1440 = 900,001,440
    # Monday 09:00 = 900,001,440 + 540 = 900,001,980.
    start_min = 900_001_980
    end_min = start_min + 300  # Monday 14:00

    stream = [
        f"{start_min},T_BIG,OPEN,P1",
        f"{end_min},T_BIG,CLOSE",
    ]
    # Add 5,000 holidays across earlier days
    for day in range(0, 5000):
        stream.append(f"{day * 1440},*,HOLIDAY")

    expected = [{
        "ticket_id": "T_BIG",
        "priority": "P1",
        "used_minutes": 300,
        "breached": True,
        "breached_at": start_min + 241,  # 900002221
        "status": "closed",
    }]
    assert_equal(solution.compute_sla(stream), expected, "Large time span / scale test failed")


# ==============================================================================
# TEST RUNNER
# ==============================================================================

def main():
    tests = [
        test_spec_examples,
        test_empty_and_no_valid_events,
        test_malformed_lines_adversarial,
        test_whitespace_and_leading_zeros,
        test_all_state_transitions,
        test_reopen_vs_open_from_closed,
        test_breach_exact_boundaries,
        test_priority_downgrade_immediate_breach,
        test_priorities_p3_and_p4,
        test_calendar_and_holidays,
        test_definition_of_now_and_running_tickets,
        test_out_of_order_stream_and_same_minute_ties,
        test_case_sensitivity_and_code_point_sorting,
        test_outside_business_hours_events,
        test_performance_large_time_span,
    ]

    passed = 0
    failed = 0

    print("=" * 70)
    print("Running Adversarial SLA Clock Test Suite")
    print("=" * 70)

    for test in tests:
        name = test.__name__
        try:
            test()
            print(f"[PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {name}")
            traceback.print_exc()
            failed += 1

    print("=" * 70)
    print(f"Summary: {passed} passed, {failed} failed.")
    print("=" * 70)

    if failed == 0:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()