import solution
import sys
import time

# Adversarial QA Test Suite for Problem 5: Business-hours SLA clock

tests_passed = 0
tests_failed = 0


def run_test(name, stream, expected):
    global tests_passed, tests_failed
    try:
        actual = solution.compute_sla(stream)
        if actual == expected:
            tests_passed += 1
        else:
            tests_failed += 1
            print(f"[FAIL] {name}")
            print(f"  Input:    {stream}")
            print(f"  Expected: {expected}")
            print(f"  Actual:   {actual}")
    except Exception as e:
        tests_failed += 1
        print(f"[ERROR] {name}")
        print(f"  Input:    {stream}")
        print(f"  Exception: {type(e).__name__}: {e}")


def test_spec_examples():
    # Example 1
    stream1 = [
        "540,A,OPEN,P2",
        "600,A,CLOSE",
    ]
    expected1 = [
        {
            "ticket_id": "A",
            "priority": "P2",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("spec_example_1", stream1, expected1)

    # Example 2
    stream2 = [
        "6720,B,OPEN,P1",
        "10680,B,PAUSE",
    ]
    expected2 = [
        {
            "ticket_id": "B",
            "priority": "P1",
            "used_minutes": 120,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    run_test("spec_example_2", stream2, expected2)

    # Example 3
    stream3 = [
        "540,C,OPEN,P1",
        "900,C,CLOSE",
    ]
    expected3 = [
        {
            "ticket_id": "C",
            "priority": "P1",
            "used_minutes": 360,
            "breached": True,
            "breached_at": 781,
            "status": "closed",
        }
    ]
    run_test("spec_example_3", stream3, expected3)

    # Example 4
    stream4 = [
        "540,D,OPEN,P3",
        "2040,D,PAUSE",
        "open,D,RESUME",
        "2100,D,RESUME,P1",
        "5,*,HOLIDAY",
    ]
    expected4 = [
        {
            "ticket_id": "D",
            "priority": "P3",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    run_test("spec_example_4", stream4, expected4)


def test_empty_and_no_ticket_events():
    run_test("empty_list", [], [])
    run_test("empty_string", [""], [])
    run_test("whitespace_only_lines", ["   ", "\t\t\n"], [])
    run_test("only_holidays", ["5,*,HOLIDAY", "2000,*,HOLIDAY"], [])
    run_test("only_malformed", ["foo,bar,baz", "1,2,3,4,5", "-10,A,OPEN,P1"], [])

    # Well-formed ticket events, but none is a valid OPEN -> no ticket ever opened
    run_test("well_formed_events_no_open", ["540,A,PAUSE", "600,B,CLOSE", "700,C,RESUME"], [])
    run_test("well_formed_priority_no_open", ["540,A,PRIORITY,P1"], [])
    run_test("well_formed_reopen_no_open", ["540,A,REOPEN"], [])


def test_malformed_lines():
    # Various malformed lines ignored, while valid lines succeed
    stream = [
        "",                             # empty
        "   ",                          # whitespace
        "540",                          # 1 field
        "540,A",                        # 2 fields
        "540,A,OPEN,P1,EXTRA",          # 5 fields
        "540,A,CLOSE,EXTRA",            # 4 fields for CLOSE
        "540,A,PAUSE,P1",               # 4 fields for PAUSE
        "540,A,RESUME,P1",              # 4 fields for RESUME
        "540,A,REOPEN,P1",              # 4 fields for REOPEN
        "540,*,HOLIDAY,EXTRA",          # 4 fields for HOLIDAY
        "-10,A,OPEN,P1",                # negative minute
        "+540,A,OPEN,P1",               # '+' sign
        "540a,A,OPEN,P1",               # non-digit minute
        "540.0,A,OPEN,P1",              # float minute
        "540,,OPEN,P1",                 # empty ticket ID
        "540,   ,OPEN,P1",              # whitespace ticket ID
        "540,*,OPEN,P1",                # '*' ticket ID for non-holiday
        "540,A,HOLIDAY",                # non-'*' ticket ID for holiday
        "540,,HOLIDAY",                 # empty ticket ID for holiday
        "540,A,open,P1",                # lowercase event
        "540,A,Open,P1",                # mixed case event
        "540,A,UNKNOWN,P1",             # unknown event
        "540,A,OPEN,P5",                # invalid priority
        "540,A,OPEN,P0",                # invalid priority
        "540,A,OPEN,p1",                # lowercase priority
        "540,A,PRIORITY,P5",            # invalid priority
        "540,A,PRIORITY,p1",            # lowercase priority
        "540,A,OPEN",                   # missing priority for OPEN
        "540,A,PRIORITY",               # missing priority for PRIORITY
        "540,A,OPEN,P1,",               # trailing comma -> 5 fields
        # Valid lines with whitespace and leading zeros
        "  00540  ,  A  ,  OPEN  ,  P1  ",
        "00600,A,CLOSE",
    ]
    expected = [
        {
            "ticket_id": "A",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("malformed_lines_comprehensive", stream, expected)


def test_state_machine_all_24_transitions():
    # 1. NOT_OPENED transitions:
    # Events before OPEN are ignored
    stream_not_opened = [
        "100,T1,PRIORITY,P4",   # ignored
        "200,T1,PAUSE",         # ignored
        "300,T1,RESUME",        # ignored
        "400,T1,CLOSE",         # ignored
        "500,T1,REOPEN",        # ignored
        "540,T1,OPEN,P1",       # valid OPEN -> RUNNING, P1, used 0
        "600,T1,CLOSE",         # valid CLOSE
    ]
    expected_not_opened = [
        {
            "ticket_id": "T1",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("transitions_not_opened", stream_not_opened, expected_not_opened)

    # 2. RUNNING transitions:
    # - OPEN: ignored
    # - PRIORITY: priority becomes P
    # - PAUSE: to PAUSED
    # - RESUME: ignored
    # - CLOSE: to CLOSED
    # - REOPEN: ignored
    stream_running = [
        "540,T2,OPEN,P1",
        "560,T2,OPEN,P3",       # ignored (still P1)
        "580,T2,RESUME",        # ignored
        "600,T2,REOPEN",        # ignored
        "620,T2,PRIORITY,P2",   # priority becomes P2
        "640,T2,PAUSE",         # to PAUSED (running 540-640 = 100 min)
        "660,T2,RESUME",        # to RUNNING
        "700,T2,CLOSE",         # to CLOSED (running 660-700 = 40 min)
    ]
    # Total used: 100 + 40 = 140 min. Priority at now: P2. Status: closed.
    expected_running = [
        {
            "ticket_id": "T2",
            "priority": "P2",
            "used_minutes": 140,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("transitions_running", stream_running, expected_running)

    # 3. PAUSED transitions:
    # - OPEN: ignored
    # - PRIORITY: priority becomes P
    # - PAUSE: ignored
    # - RESUME: to RUNNING
    # - CLOSE: to CLOSED
    # - REOPEN: ignored
    stream_paused = [
        "540,T3,OPEN,P1",
        "600,T3,PAUSE",         # to PAUSED (60 min used)
        "620,T3,OPEN,P4",       # ignored (priority still P1)
        "640,T3,PAUSE",         # ignored
        "660,T3,REOPEN",        # ignored
        "680,T3,PRIORITY,P3",   # priority becomes P3
        "700,T3,CLOSE",         # to CLOSED directly from PAUSED
    ]
    expected_paused = [
        {
            "ticket_id": "T3",
            "priority": "P3",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("transitions_paused", stream_paused, expected_paused)

    # 4. CLOSED transitions:
    # - OPEN: to RUNNING, priority P, used resets to 0, breach cleared
    # - PRIORITY: ignored
    # - PAUSE: ignored
    # - RESUME: ignored
    # - CLOSE: ignored
    # - REOPEN: to RUNNING, used continues, breach kept, priority kept
    stream_closed_reopen = [
        "540,T4,OPEN,P1",
        "900,T4,CLOSE",         # 360 min, breached at 781
        "920,T4,PRIORITY,P4",   # ignored (CLOSED)
        "930,T4,PAUSE",         # ignored (CLOSED)
        "940,T4,RESUME",        # ignored (CLOSED)
        "950,T4,CLOSE",         # ignored (CLOSED)
        "960,T4,REOPEN",        # to RUNNING, used continues (360), breach kept (781), priority P1
        "1000,T4,CLOSE",        # running 960-1000 = 40 min. Total used = 400.
    ]
    expected_closed_reopen = [
        {
            "ticket_id": "T4",
            "priority": "P1",
            "used_minutes": 400,
            "breached": True,
            "breached_at": 781,
            "status": "closed",
        }
    ]
    run_test("transitions_closed_reopen", stream_closed_reopen, expected_closed_reopen)

    # Test OPEN from CLOSED clears breach and resets used time
    stream_closed_open = [
        "540,T5,OPEN,P1",
        "900,T5,CLOSE",         # breached at 781, used 360
        "950,T5,OPEN,P2",       # to RUNNING, priority P2, used resets to 0, breach cleared!
        "1000,T5,CLOSE",        # running 950-1000 = 50 min.
    ]
    expected_closed_open = [
        {
            "ticket_id": "T5",
            "priority": "P2",
            "used_minutes": 50,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("transitions_closed_open_resets", stream_closed_open, expected_closed_open)


def test_sla_boundaries_and_priorities():
    # P1 boundary (limit 240)
    # Exactly 240 minutes: 540 to 780
    stream_p1_exact = ["540,B1,OPEN,P1", "780,B1,CLOSE"]
    expected_p1_exact = [
        {
            "ticket_id": "B1",
            "priority": "P1",
            "used_minutes": 240,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("sla_boundary_p1_exact_240", stream_p1_exact, expected_p1_exact)

    # Exactly 241 minutes: 540 to 781
    stream_p1_breach = ["540,B2,OPEN,P1", "781,B2,CLOSE"]
    expected_p1_breach = [
        {
            "ticket_id": "B2",
            "priority": "P1",
            "used_minutes": 241,
            "breached": True,
            "breached_at": 781,
            "status": "closed",
        }
    ]
    run_test("sla_boundary_p1_breach_241", stream_p1_breach, expected_p1_breach)

    # P2 boundary (limit 480)
    # Day 0: 540 to 1020 is 480 minutes. End of business day is minute 1020.
    # At 1020, used time is 480 <= 480. No breach!
    stream_p2_exact = ["540,B3,OPEN,P2", "1020,B3,CLOSE"]
    expected_p2_exact = [
        {
            "ticket_id": "B3",
            "priority": "P2",
            "used_minutes": 480,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("sla_boundary_p2_exact_480", stream_p2_exact, expected_p2_exact)

    # P2 breach: Day 1 (Tuesday) starts at 1440 + 540 = 1980.
    # Minute 1980 is the 481st business minute.
    # At minute 1981, used time is 481 > 480 -> breached_at = 1981!
    stream_p2_breach = ["540,B4,OPEN,P2", "1981,B4,CLOSE"]
    expected_p2_breach = [
        {
            "ticket_id": "B4",
            "priority": "P2",
            "used_minutes": 481,
            "breached": True,
            "breached_at": 1981,
            "status": "closed",
        }
    ]
    run_test("sla_boundary_p2_breach_481", stream_p2_breach, expected_p2_breach)

    # P3 boundary (limit 1440 = 3 days * 480 min)
    # Mon (day 0): 480, Tue (day 1): 480, Wed (day 2): 480.
    # Wed business end is 2 * 1440 + 1020 = 3900.
    stream_p3_exact = ["540,B5,OPEN,P3", "3900,B5,CLOSE"]
    expected_p3_exact = [
        {
            "ticket_id": "B5",
            "priority": "P3",
            "used_minutes": 1440,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("sla_boundary_p3_exact_1440", stream_p3_exact, expected_p3_exact)

    # P3 breach: Thu (day 3) starts at 3 * 1440 + 540 = 4860.
    # Minute 4860 is the 1441st business minute -> breach at 4861!
    stream_p3_breach = ["540,B6,OPEN,P3", "4861,B6,CLOSE"]
    expected_p3_breach = [
        {
            "ticket_id": "B6",
            "priority": "P3",
            "used_minutes": 1441,
            "breached": True,
            "breached_at": 4861,
            "status": "closed",
        }
    ]
    run_test("sla_boundary_p3_breach_1441", stream_p3_breach, expected_p3_breach)

    # P4 boundary (limit 2400 = 5 days * 480 min)
    # Mon-Fri: 5 * 480 = 2400. Fri ends at 4 * 1440 + 1020 = 6780.
    stream_p4_exact = ["540,B7,OPEN,P4", "6780,B7,CLOSE"]
    expected_p4_exact = [
        {
            "ticket_id": "B7",
            "priority": "P4",
            "used_minutes": 2400,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("sla_boundary_p4_exact_2400", stream_p4_exact, expected_p4_exact)

    # P4 breach: Next Mon (day 7) starts at 7 * 1440 + 540 = 10620.
    # Minute 10620 is the 2401st business minute -> breach at 10621!
    stream_p4_breach = ["540,B8,OPEN,P4", "10621,B8,CLOSE"]
    expected_p4_breach = [
        {
            "ticket_id": "B8",
            "priority": "P4",
            "used_minutes": 2401,
            "breached": True,
            "breached_at": 10621,
            "status": "closed",
        }
    ]
    run_test("sla_boundary_p4_breach_2401", stream_p4_breach, expected_p4_breach)


def test_priority_change_rules():
    # 1. Raising priority at exact minute of breach PREVENTS breach
    # At minute 781, used time is 241. P2 limit is 480.
    # Events at 781 applied first -> priority is P2 when 781 is checked -> no breach!
    stream_prevent = [
        "540,P_PREV,OPEN,P1",
        "781,P_PREV,PRIORITY,P2",
        "800,P_PREV,CLOSE",
    ]
    expected_prevent = [
        {
            "ticket_id": "P_PREV",
            "priority": "P2",
            "used_minutes": 260,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("priority_raise_prevents_breach", stream_prevent, expected_prevent)

    # 2. Lowering priority causes immediate breach while RUNNING
    # Opened at 540 (P2, limit 480). Runs until 800 (used = 260).
    # At 800, PRIORITY P1 (limit 240). Used 260 > 240 -> breaches immediately at 800!
    stream_drop_run = [
        "540,P_DROP1,OPEN,P2",
        "800,P_DROP1,PRIORITY,P1",
        "850,P_DROP1,CLOSE",
    ]
    expected_drop_run = [
        {
            "ticket_id": "P_DROP1",
            "priority": "P1",
            "used_minutes": 310,
            "breached": True,
            "breached_at": 800,
            "status": "closed",
        }
    ]
    run_test("priority_drop_immediate_breach_running", stream_drop_run, expected_drop_run)

    # 3. Lowering priority causes immediate breach while PAUSED
    # Opened at 540 (P2). At 800 (used = 260), PAUSE.
    # At 850 (ticket still PAUSED, used = 260), PRIORITY P1.
    # Breaches immediately at 850 while PAUSED!
    stream_drop_pause = [
        "540,P_DROP2,OPEN,P2",
        "800,P_DROP2,PAUSE",
        "850,P_DROP2,PRIORITY,P1",
    ]
    expected_drop_pause = [
        {
            "ticket_id": "P_DROP2",
            "priority": "P1",
            "used_minutes": 260,
            "breached": True,
            "breached_at": 850,
            "status": "paused",
        }
    ]
    run_test("priority_drop_immediate_breach_paused", stream_drop_pause, expected_drop_pause)

    # 4. Lowering priority outside business hours causes immediate breach
    # At 1020 (used = 480). At 1050 (non-business minute), PRIORITY P1.
    # Breaches at 1050!
    stream_drop_outside = [
        "540,P_DROP3,OPEN,P2",
        "1020,P_DROP3,PAUSE",
        "1050,P_DROP3,PRIORITY,P1",
    ]
    expected_drop_outside = [
        {
            "ticket_id": "P_DROP3",
            "priority": "P1",
            "used_minutes": 480,
            "breached": True,
            "breached_at": 1050,
            "status": "paused",
        }
    ]
    run_test("priority_drop_immediate_breach_outside_hours", stream_drop_outside, expected_drop_outside)

    # 5. Raising priority later does NOT undo breach (sticky)
    # Breaches at 781 under P1. At 850, PRIORITY P4 (limit 2400).
    stream_sticky = [
        "540,P_STICKY,OPEN,P1",
        "850,P_STICKY,PRIORITY,P4",
        "900,P_STICKY,CLOSE",
    ]
    expected_sticky = [
        {
            "ticket_id": "P_STICKY",
            "priority": "P4",
            "used_minutes": 360,
            "breached": True,
            "breached_at": 781,
            "status": "closed",
        }
    ]
    run_test("breach_is_sticky_after_priority_raise", stream_sticky, expected_sticky)


def test_definition_of_now_and_ignored_events():
    # 'now' is largest minute among all well-formed ticket events, including invalid transitions
    # Event at 800 is an invalid PAUSE on NOT_OPENED ticket X.
    # Ticket X is never opened -> not in output.
    # But now is 800!
    stream_now_ignored = [
        "540,T_VALID,OPEN,P1",
        "600,T_VALID,CLOSE",
        "800,X_NEVER_OPEN,PAUSE",
    ]
    expected_now_ignored = [
        {
            "ticket_id": "T_VALID",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("now_from_ignored_event", stream_now_ignored, expected_now_ignored)

    # HOLIDAY lines NEVER affect 'now'
    stream_holiday_now = [
        "540,T_HOL,OPEN,P1",
        "600,T_HOL,CLOSE",
        "999999,*,HOLIDAY",
    ]
    expected_holiday_now = [
        {
            "ticket_id": "T_HOL",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("holiday_does_not_affect_now", stream_holiday_now, expected_holiday_now)

    # Ticket opened at 'now': used_minutes must be 0
    stream_zero_used = ["540,T_ZERO,OPEN,P1"]
    expected_zero_used = [
        {
            "ticket_id": "T_ZERO",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    run_test("ticket_opened_at_now_has_zero_used", stream_zero_used, expected_zero_used)


def test_ties_and_stream_ordering():
    # Out of order ticket events
    stream_ooo = [
        "900,T_OOO,CLOSE",
        "540,T_OOO,OPEN,P1",
    ]
    expected_ooo = [
        {
            "ticket_id": "T_OOO",
            "priority": "P1",
            "used_minutes": 360,
            "breached": True,
            "breached_at": 781,
            "status": "closed",
        }
    ]
    run_test("out_of_order_events", stream_ooo, expected_ooo)

    # Same minute: stable ordering matters!
    # OPEN then PAUSE at 540 -> ends minute 540 as PAUSED.
    # During minute 540 it is PAUSED -> used_minutes at 541 is 0!
    stream_tie_pause = [
        "540,T_TIE1,OPEN,P1",
        "540,T_TIE1,PAUSE",
        "541,T_TIE1,CLOSE",
    ]
    expected_tie_pause = [
        {
            "ticket_id": "T_TIE1",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("tie_open_then_pause", stream_tie_pause, expected_tie_pause)

    # PAUSE (ignored) then OPEN at 540 -> ends minute 540 as RUNNING.
    # During minute 540 it is RUNNING -> used_minutes at 541 is 1!
    stream_tie_open = [
        "540,T_TIE2,PAUSE",
        "540,T_TIE2,OPEN,P1",
        "541,T_TIE2,CLOSE",
    ]
    expected_tie_open = [
        {
            "ticket_id": "T_TIE2",
            "priority": "P1",
            "used_minutes": 1,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("tie_pause_then_open", stream_tie_open, expected_tie_open)

    # Tie at 781: PRIORITY P1 then PRIORITY P2 -> final priority P2 -> NO breach!
    stream_tie_p2_last = [
        "540,T_TIE3,OPEN,P1",
        "781,T_TIE3,PRIORITY,P1",
        "781,T_TIE3,PRIORITY,P2",
        "800,T_TIE3,CLOSE",
    ]
    expected_tie_p2_last = [
        {
            "ticket_id": "T_TIE3",
            "priority": "P2",
            "used_minutes": 260,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("tie_p1_then_p2_prevents_breach", stream_tie_p2_last, expected_tie_p2_last)

    # Tie at 781: PRIORITY P2 then PRIORITY P1 -> final priority P1 -> BREACH!
    stream_tie_p1_last = [
        "540,T_TIE4,OPEN,P1",
        "781,T_TIE4,PRIORITY,P2",
        "781,T_TIE4,PRIORITY,P1",
        "800,T_TIE4,CLOSE",
    ]
    expected_tie_p1_last = [
        {
            "ticket_id": "T_TIE4",
            "priority": "P1",
            "used_minutes": 260,
            "breached": True,
            "breached_at": 781,
            "status": "closed",
        }
    ]
    run_test("tie_p2_then_p1_causes_breach", stream_tie_p1_last, expected_tie_p1_last)


def test_calendar_and_holidays():
    # Weekend test: Friday 16:30 (minute 6750) to Monday 09:30 (minute 10650)
    # Fri 16:30-17:00 = 30 min.
    # Mon 09:00-09:30 = 30 min.
    # Total used = 60 min.
    stream_weekend = [
        "6750,T_WKND,OPEN,P1",
        "10650,T_WKND,CLOSE",
    ]
    expected_weekend = [
        {
            "ticket_id": "T_WKND",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("weekend_skipping", stream_weekend, expected_weekend)

    # Holiday declared twice is idempotent
    # Day 0 is Monday. Declare holiday twice. Ticket runs Mon 540-600. Used = 0 min.
    stream_dup_hol = [
        "540,T_DH,OPEN,P1",
        "600,T_DH,CLOSE",
        "0,*,HOLIDAY",
        "1000,*,HOLIDAY",
    ]
    expected_dup_hol = [
        {
            "ticket_id": "T_DH",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    run_test("duplicate_holiday_idempotent", stream_dup_hol, expected_dup_hol)

    # Multi-day with holiday shifting breach
    # Open Mon 15:00 (900). P1 (limit 240).
    # Mon 15:00-17:00 = 120 min.
    # Tue is HOLIDAY (day 1, minute 1440).
    # Wed (day 2): starts 2 * 1440 + 540 = 3420.
    # Needs 121 more minutes on Wed: 3420 + 120 = 3540 (used = 240).
    # During minute 3540: 241st minute. Breach at 3541!
    stream_hol_breach = [
        "900,T_HB,OPEN,P1",
        "1440,*,HOLIDAY",
        "3600,T_HB,CLOSE",
    ]
    expected_hol_breach = [
        {
            "ticket_id": "T_HB",
            "priority": "P1",
            "used_minutes": 300,
            "breached": True,
            "breached_at": 3541,
            "status": "closed",
        }
    ]
    run_test("holiday_shifts_breach_minute", stream_hol_breach, expected_hol_breach)


def test_output_sorting_and_schema():
    # Tickets: "T1", "T10", "T2", "t1", "A", "1"
    # Python code-point order: "1" < "A" < "T1" < "T10" < "T2" < "t1"
    stream_order = [
        "540,t1,OPEN,P1",
        "540,T2,OPEN,P1",
        "540,1,OPEN,P1",
        "540,T10,OPEN,P1",
        "540,A,OPEN,P1",
        "540,T1,OPEN,P1",
        "600,t1,CLOSE",
        "600,T2,CLOSE",
        "600,1,CLOSE",
        "600,T10,CLOSE",
        "600,A,CLOSE",
        "600,T1,CLOSE",
    ]
    # Pass as a generator (not list) to test that arbitrary iterables are accepted
    gen = (line for line in stream_order)
    actual = solution.compute_sla(gen)

    global tests_passed, tests_failed
    test_ok = True

    if not isinstance(actual, list):
        print(f"[FAIL] output_schema: expected list, got {type(actual)}")
        test_ok = False
    elif len(actual) != 6:
        print(f"[FAIL] output_schema: expected 6 tickets, got {len(actual)}")
        test_ok = False
    else:
        expected_ids = ["1", "A", "T1", "T10", "T2", "t1"]
        actual_ids = [d["ticket_id"] for d in actual]
        if actual_ids != expected_ids:
            print(f"[FAIL] output_schema: ticket ordering incorrect. Expected {expected_ids}, got {actual_ids}")
            test_ok = False

        required_keys = {"ticket_id", "priority", "used_minutes", "breached", "breached_at", "status"}
        for item in actual:
            if set(item.keys()) != required_keys:
                print(f"[FAIL] output_schema: invalid keys {set(item.keys())}")
                test_ok = False
                break
            if not isinstance(item["ticket_id"], str):
                test_ok = False
            if not isinstance(item["priority"], str) or item["priority"] not in ("P1", "P2", "P3", "P4"):
                test_ok = False
            if not isinstance(item["used_minutes"], int):
                test_ok = False
            if type(item["breached"]) is not bool:
                print(f"[FAIL] output_schema: breached must be strict bool, got {type(item['breached'])}")
                test_ok = False
            if item["breached_at"] is not None and not isinstance(item["breached_at"], int):
                test_ok = False
            if item["status"] not in ("running", "paused", "closed"):
                test_ok = False

    if test_ok:
        tests_passed += 1
    else:
        tests_failed += 1


def test_performance_and_large_minutes():
    # 1. Large minute jump: minute = 100,000,000
    # Tests that solution does not step minute-by-minute across large gaps!
    # 100,000,000 minutes = 69444 days + 640 min (Friday 10:40).
    # 69444 days = 9920 full weeks + 4 days (Mon, Tue, Wed, Thu).
    # 9920 * 2400 = 23,808,000 min.
    # Mon-Thu = 4 * 480 = 1920 min.
    # Fri (540 to 640) = 100 min.
    # Total business minutes = 23,810,020.
    # Opened at 540 at P4 (limit 2400).
    # Breaches on Monday of week 1 at 10621.
    stream_large = [
        "540,BIG,OPEN,P4",
        "100000000,BIG,CLOSE",
    ]
    expected_large = [
        {
            "ticket_id": "BIG",
            "priority": "P4",
            "used_minutes": 23810020,
            "breached": True,
            "breached_at": 10621,
            "status": "closed",
        }
    ]
    start_t = time.time()
    run_test("performance_large_minute_100M", stream_large, expected_large)
    elapsed = time.time() - start_t
    if elapsed > 3.0:
        global tests_failed
        tests_failed += 1
        print(f"[FAIL] performance_large_minute_100M took {elapsed:.2f}s (exceeded 3.0s threshold)")

    # 2. Stress test: 5,000 holiday lines + 2,000 ticket events
    stream_stress = []
    # Holidays on Saturdays (day 5, 12, 19, ...)
    for w in range(5000):
        sat_min = (w * 7 + 5) * 1440
        stream_stress.append(f"{sat_min},*,HOLIDAY")

    # 500 tickets, each opened and closed within 1 hour on Monday of week 0
    for i in range(500):
        stream_stress.append(f"540,T_STRESS_{i:04d},OPEN,P1")
        stream_stress.append(f"600,T_STRESS_{i:04d},CLOSE")

    start_stress = time.time()
    actual_stress = solution.compute_sla(stream_stress)
    elapsed_stress = time.time() - start_stress

    global tests_passed
    if len(actual_stress) == 500 and actual_stress[0]["used_minutes"] == 60 and elapsed_stress < 4.0:
        tests_passed += 1
    else:
        tests_failed += 1
        print(f"[FAIL] stress_test: len={len(actual_stress)}, elapsed={elapsed_stress:.2f}s")


def main():
    test_spec_examples()
    test_empty_and_no_ticket_events()
    test_malformed_lines()
    test_state_machine_all_24_transitions()
    test_sla_boundaries_and_priorities()
    test_priority_change_rules()
    test_definition_of_now_and_ignored_events()
    test_ties_and_stream_ordering()
    test_calendar_and_holidays()
    test_output_sorting_and_schema()
    test_performance_and_large_minutes()

    total = tests_passed + tests_failed
    print(f"\n==========================================")
    print(f"Summary: {tests_passed}/{total} tests passed.")
    print(f"==========================================")

    if tests_failed == 0:
        print("ALL TESTS PASSED.")
        sys.exit(0)
    else:
        print(f"FAILED: {tests_failed} tests failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()