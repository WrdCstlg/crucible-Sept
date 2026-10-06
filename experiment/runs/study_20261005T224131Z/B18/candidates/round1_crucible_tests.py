import solution
import sys
import traceback

# ---------------------------------------------------------------------------
# Adversarial Test Suite for compute_sla
# ---------------------------------------------------------------------------

passed_count = 0
failed_count = 0

EXPECTED_KEYS = {
    "ticket_id",
    "priority",
    "used_minutes",
    "breached",
    "breached_at",
    "status",
}
VALID_STATUSES = {"running", "paused", "closed"}
VALID_PRIORITIES = {"P1", "P2", "P3", "P4"}


def assert_result(actual, expected, test_name):
    global passed_count, failed_count
    try:
        assert isinstance(
            actual, list
        ), f"Expected list, got {type(actual).__name__}"
        assert len(actual) == len(
            expected
        ), f"Expected {len(expected)} items, got {len(actual)}: {actual}"

        # Verify ordering: ticket_id ascending by default python string order
        ticket_ids = [t["ticket_id"] for t in actual]
        assert ticket_ids == sorted(
            ticket_ids
        ), f"Output not sorted by ticket_id ascending: {ticket_ids}"

        for idx, (act, exp) in enumerate(zip(actual, expected)):
            assert isinstance(
                act, dict
            ), f"Item {idx} is not a dict: {type(act)}"
            assert (
                set(act.keys()) == EXPECTED_KEYS
            ), f"Item {idx} keys mismatch. Expected {EXPECTED_KEYS}, got {set(act.keys())}"

            # Type validations
            assert isinstance(
                act["ticket_id"], str
            ), f"Item {idx} ticket_id is not str"
            assert (
                act["priority"] in VALID_PRIORITIES
            ), f"Item {idx} invalid priority: {act['priority']}"
            assert (
                type(act["used_minutes"]) is int
            ), f"Item {idx} used_minutes not int: {type(act['used_minutes'])}"
            assert (
                type(act["breached"]) is bool
            ), f"Item {idx} breached not bool: {type(act['breached'])}"
            assert (
                act["status"] in VALID_STATUSES
            ), f"Item {idx} invalid status: {act['status']}"

            if act["breached"]:
                assert (
                    type(act["breached_at"]) is int
                ), f"Item {idx} breached_at should be int when breached=True, got {type(act['breached_at'])}"
            else:
                assert (
                    act["breached_at"] is None
                ), f"Item {idx} breached_at should be None when breached=False, got {act['breached_at']}"

            # Value validations against hand-computed expected
            for k in EXPECTED_KEYS:
                assert (
                    act[k] == exp[k]
                ), f"Item {idx} ({act.get('ticket_id')}): key '{k}' expected {exp[k]!r}, got {act[k]!r}"

        passed_count += 1
        print(f"PASS: {test_name}")
    except AssertionError as e:
        failed_count += 1
        print(f"FAIL: {test_name}")
        print(f"      {e}")
    except Exception as e:
        failed_count += 1
        print(f"ERROR: {test_name}")
        traceback.print_exc()


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


def run_spec_examples():
    """Verify the 4 examples directly from the problem description."""
    # Example 1
    s1 = ["540,A,OPEN,P2", "600,A,CLOSE"]
    exp1 = [
        {
            "ticket_id": "A",
            "priority": "P2",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s1), exp1, "Spec Example 1")

    # Example 2
    s2 = ["6720,B,OPEN,P1", "10680,B,PAUSE"]
    exp2 = [
        {
            "ticket_id": "B",
            "priority": "P1",
            "used_minutes": 120,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_result(solution.compute_sla(s2), exp2, "Spec Example 2")

    # Example 3
    s3 = ["540,C,OPEN,P1", "900,C,CLOSE"]
    exp3 = [
        {
            "ticket_id": "C",
            "priority": "P1",
            "used_minutes": 360,
            "breached": True,
            "breached_at": 781,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s3), exp3, "Spec Example 3")

    # Example 4
    s4 = [
        "540,D,OPEN,P3",
        "2040,D,PAUSE",
        "open,D,RESUME",
        "2100,D,RESUME,P1",
        "5,*,HOLIDAY",
    ]
    exp4 = [
        {
            "ticket_id": "D",
            "priority": "P3",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_result(solution.compute_sla(s4), exp4, "Spec Example 4")


def run_state_transition_table():
    """Exhaustively cover all 24 cells of the state transition table."""

    # 1. NOT_OPENED + OPEN -> to RUNNING, priority P, used 0 (covered in basic open)
    s = ["540,T1,OPEN,P1"]
    exp = [
        {
            "ticket_id": "T1",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "Transition NOT_OPENED + OPEN")

    # 2-6: NOT_OPENED with PRIORITY, PAUSE, RESUME, CLOSE, REOPEN
    # These events must be ignored and tickets never opened must NOT be returned.
    # But well-formed lines must update 'now'.
    s = [
        "100,U1,PRIORITY,P1",
        "200,U2,PAUSE",
        "300,U3,RESUME",
        "400,U4,CLOSE",
        "500,U5,REOPEN",
        "540,VALID,OPEN,P2",
        "600,VALID,CLOSE",
        "700,U6,PAUSE",  # updates 'now' to 700!
    ]
    # VALID was closed at 600, so used = 60 min. Status = closed. U1..U6 omitted.
    exp = [
        {
            "ticket_id": "VALID",
            "priority": "P2",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "Transitions NOT_OPENED + others (ignored)"
    )

    # 7. RUNNING + OPEN -> ignored
    s = ["540,T,OPEN,P1", "600,T,OPEN,P2", "700,T,CLOSE"]
    # At 600, OPEN,P2 is ignored: priority stays P1, used time does not reset.
    # At 700, CLOSE: used = 160 min. Limit P1 is 240, not breached.
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 160,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "Transition RUNNING + OPEN (ignored)")

    # 8. RUNNING + PRIORITY -> priority becomes P
    s = ["540,T,OPEN,P1", "600,T,PRIORITY,P3", "700,T,CLOSE"]
    exp = [
        {
            "ticket_id": "T",
            "priority": "P3",
            "used_minutes": 160,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "Transition RUNNING + PRIORITY"
    )

    # 9. RUNNING + PAUSE -> to PAUSED
    s = ["540,T,OPEN,P1", "600,T,PAUSE"]
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "Transition RUNNING + PAUSE")

    # 10. RUNNING + RESUME -> ignored
    s = ["540,T,OPEN,P1", "600,T,RESUME", "700,T,CLOSE"]
    # RESUME while RUNNING is ignored; continues running
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 160,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "Transition RUNNING + RESUME (ignored)"
    )

    # 11. RUNNING + CLOSE -> to CLOSED
    s = ["540,T,OPEN,P1", "600,T,CLOSE"]
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "Transition RUNNING + CLOSE")

    # 12. RUNNING + REOPEN -> ignored
    s = ["540,T,OPEN,P1", "600,T,REOPEN", "700,T,CLOSE"]
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 160,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "Transition RUNNING + REOPEN (ignored)"
    )

    # 13. PAUSED + OPEN -> ignored
    s = [
        "540,T,OPEN,P1",
        "600,T,PAUSE",
        "650,T,OPEN,P3",
        "700,T,RESUME",
        "750,T,CLOSE",
    ]
    # OPEN,P3 ignored while PAUSED. Priority remains P1.
    # Running: 540-600 (60), 700-750 (50) -> used 110.
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 110,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "Transition PAUSED + OPEN (ignored)")

    # 14. PAUSED + PRIORITY -> priority becomes P
    s = ["540,T,OPEN,P1", "600,T,PAUSE", "650,T,PRIORITY,P4", "700,T,CLOSE"]
    exp = [
        {
            "ticket_id": "T",
            "priority": "P4",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "Transition PAUSED + PRIORITY")

    # 15. PAUSED + PAUSE -> ignored
    s = ["540,T,OPEN,P1", "600,T,PAUSE", "650,T,PAUSE", "700,T,CLOSE"]
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "Transition PAUSED + PAUSE (ignored)"
    )

    # 16. PAUSED + RESUME -> to RUNNING
    s = ["540,T,OPEN,P1", "600,T,PAUSE", "650,T,RESUME", "700,T,CLOSE"]
    # Running: 540-600 (60), 650-700 (50) -> 110
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 110,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "Transition PAUSED + RESUME")

    # 17. PAUSED + CLOSE -> to CLOSED
    s = ["540,T,OPEN,P1", "600,T,PAUSE", "700,T,CLOSE"]
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "Transition PAUSED + CLOSE")

    # 18. PAUSED + REOPEN -> ignored
    s = [
        "540,T,OPEN,P1",
        "600,T,PAUSE",
        "650,T,REOPEN",
        "700,T,CLOSE",
    ]  # REOPEN ignored while PAUSED
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "Transition PAUSED + REOPEN (ignored)"
    )

    # 19. CLOSED + OPEN -> to RUNNING, priority P, used resets to 0, breach CLEARED
    s = [
        "540,T,OPEN,P1",
        "800,T,CLOSE",  # Breached at 781 (P1 limit 240, used 260)
        "900,T,OPEN,P2",  # Reset to 0, priority P2, breach cleared
        "960,T,CLOSE",  # Used 60 min
    ]
    exp = [
        {
            "ticket_id": "T",
            "priority": "P2",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "Transition CLOSED + OPEN (reset & clear)"
    )

    # 20. CLOSED + PRIORITY -> ignored
    s = [
        "540,T,OPEN,P1",
        "600,T,CLOSE",
        "650,T,PRIORITY,P4",  # Ignored
        "700,OTHER,OPEN,P1",
    ]
    # Priority of T must remain P1
    exp = [
        {
            "ticket_id": "OTHER",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        },
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
    ]
    assert_result(
        solution.compute_sla(s), exp, "Transition CLOSED + PRIORITY (ignored)"
    )

    # 21. CLOSED + PAUSE -> ignored
    s = ["540,T,OPEN,P1", "600,T,CLOSE", "650,T,PAUSE"]
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "Transition CLOSED + PAUSE (ignored)"
    )

    # 22. CLOSED + RESUME -> ignored
    s = ["540,T,OPEN,P1", "600,T,CLOSE", "650,T,RESUME"]
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "Transition CLOSED + RESUME (ignored)"
    )

    # 23. CLOSED + CLOSE -> ignored
    s = ["540,T,OPEN,P1", "600,T,CLOSE", "650,T,CLOSE"]
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "Transition CLOSED + CLOSE (ignored)"
    )

    # 24. CLOSED + REOPEN -> to RUNNING, used continues, breach kept, priority kept
    # 24a: Not breached
    s = ["540,T,OPEN,P1", "600,T,CLOSE", "650,T,REOPEN", "700,T,CLOSE"]
    # 540-600 (60) + 650-700 (50) = 110 min
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 110,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s),
        exp,
        "Transition CLOSED + REOPEN (not breached)",
    )

    # 24b: Breached
    s = ["540,T,OPEN,P1", "800,T,CLOSE", "850,T,REOPEN", "900,T,CLOSE"]
    # Breached at 781. Closed at 800. Reopened at 850.
    # 540-800 (260) + 850-900 (50) = 310 min. Breach kept at 781!
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 310,
            "breached": True,
            "breached_at": 781,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "Transition CLOSED + REOPEN (breached)"
    )


def run_sla_boundaries_and_breaches():
    """Test exact limit boundaries for all priorities and edge case timings."""

    # Priority 1: limit 240
    # Exactly at limit: 540 + 240 = 780. At 780, used = 240 -> NOT breached.
    s = ["540,P1_EXACT,OPEN,P1", "780,P1_EXACT,CLOSE"]
    exp = [
        {
            "ticket_id": "P1_EXACT",
            "priority": "P1",
            "used_minutes": 240,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "P1 Exact Boundary (240 min)")

    # 1 minute past limit: 540 + 241 = 781. At 781, used = 241 -> Breached at 781.
    s = ["540,P1_BREACH,OPEN,P1", "781,P1_BREACH,CLOSE"]
    exp = [
        {
            "ticket_id": "P1_BREACH",
            "priority": "P1",
            "used_minutes": 241,
            "breached": True,
            "breached_at": 781,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "P1 Breach Boundary (241 min)")

    # Priority 2: limit 480
    # Day 0 (Monday) business minutes: [540, 1020) = 480 minutes.
    # At minute 1020 (Mon 17:00), ticket has run for exactly 480 minutes.
    s = ["540,P2_EXACT,OPEN,P2", "1020,P2_EXACT,CLOSE"]
    exp = [
        {
            "ticket_id": "P2_EXACT",
            "priority": "P2",
            "used_minutes": 480,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "P2 Exact End-of-Day Boundary (480 min)"
    )

    # Overnight into Tuesday: Tuesday starts at 1440, business hours start at 1440+540 = 1980 (Tue 09:00).
    # At 1980, used time is still 480. At 1981, used time becomes 481 > 480!
    # Breach at 1981!
    s = ["540,P2_BREACH,OPEN,P2", "1981,P2_BREACH,CLOSE"]
    exp = [
        {
            "ticket_id": "P2_BREACH",
            "priority": "P2",
            "used_minutes": 481,
            "breached": True,
            "breached_at": 1981,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "P2 Overnight Breach Boundary (1981 min)"
    )

    # Breach occurring exactly at 1020 (end of business day / non-business minute):
    # Opened at 779 (Mon 12:59). Monday business minutes 779..1019 = 1020 - 779 = 241 minutes.
    # At 1019: used = 240 <= 240 (P1).
    # At 1020: used = 241 > 240! Breach minute is 1020!
    s = ["779,P1_EOD,OPEN,P1", "1020,P1_EOD,CLOSE"]
    exp = [
        {
            "ticket_id": "P1_EOD",
            "priority": "P1",
            "used_minutes": 241,
            "breached": True,
            "breached_at": 1020,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "P1 Breach at minute 1020 (17:00)")

    # Priority 3: limit 1440 (3 full business days: Mon, Tue, Wed)
    # Mon: 480, Tue: 480, Wed: 480 -> 1440.
    # Wed ends at 2*1440 + 1020 = 3900.
    # Thu 09:00 is 3*1440 + 540 = 4860 (used = 1440).
    # Thu 09:01 is 4861 (used = 1441 > 1440).
    s = ["540,P3_BREACH,OPEN,P3", "4861,P3_BREACH,CLOSE"]
    exp = [
        {
            "ticket_id": "P3_BREACH",
            "priority": "P3",
            "used_minutes": 1441,
            "breached": True,
            "breached_at": 4861,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "P3 Multi-day Breach Boundary")

    # Priority 4: limit 2400 (5 full business days: Mon-Fri)
    # Fri ends at 4*1440 + 1020 = 6780 (used = 2400).
    # Sat & Sun = 0 business minutes.
    # Mon week 1 09:00 = 7*1440 + 540 = 10620 (used = 2400).
    # Mon week 1 09:01 = 10621 (used = 2401 > 2400).
    s = ["540,P4_BREACH,OPEN,P4", "10621,P4_BREACH,CLOSE"]
    exp = [
        {
            "ticket_id": "P4_BREACH",
            "priority": "P4",
            "used_minutes": 2401,
            "breached": True,
            "breached_at": 10621,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "P4 Weekend-Spanning Breach Boundary"
    )


def run_priority_interaction_tests():
    """Test PRIORITY changes preventing or triggering breaches."""

    # 1. PRIORITY raise at the very minute a breach would occur prevents it
    s = ["540,T,OPEN,P1", "781,T,PRIORITY,P2", "781,T,CLOSE"]
    # At 781, used = 241. P2 limit is 480. 241 <= 480 -> No breach!
    exp = [
        {
            "ticket_id": "T",
            "priority": "P2",
            "used_minutes": 241,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s), exp, "PRIORITY Raise at 781 Prevents Breach"
    )

    # 2. PRIORITY decrease while PAUSED causes immediate breach
    # Open P2 (480), run 300 business min (540 to 840), PAUSE at 840.
    # At minute 1200 (outside business hours, while paused), PRIORITY becomes P1 (limit 240).
    # Used is 300 > 240 -> Immediate breach at 1200!
    s = [
        "540,T,OPEN,P2",
        "840,T,PAUSE",
        "1200,T,PRIORITY,P1",
    ]  # 'now' = 1200
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 300,
            "breached": True,
            "breached_at": 1200,
            "status": "paused",
        }
    ]
    assert_result(
        solution.compute_sla(s),
        exp,
        "PRIORITY Decrease while PAUSED Triggers Breach",
    )

    # 3. PRIORITY raise AFTER breach occurred does not undo breach
    s = ["540,T,OPEN,P1", "800,T,PRIORITY,P3", "850,T,CLOSE"]
    # Breached at 781. Raised to P3 at 800. Closed at 850.
    # Used = 850 - 540 = 310. Breached remains True, breached_at remains 781.
    exp = [
        {
            "ticket_id": "T",
            "priority": "P3",
            "used_minutes": 310,
            "breached": True,
            "breached_at": 781,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s),
        exp,
        "PRIORITY Raise After Breach Does Not Undo It",
    )


def run_holidays_tests():
    """Test calendar holidays declared anywhere in the stream."""

    # 1. Holiday declared AFTER ticket events on that day
    s = ["540,T,OPEN,P1", "1020,T,CLOSE", "1439,*,HOLIDAY"]  # Day 0 is holiday
    # All 480 minutes on day 0 are invalidated
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "Holiday Declared After Events")

    # 2. HOLIDAY lines never affect 'now'
    s = [
        "540,T,OPEN,P1",
        "999999,*,HOLIDAY",  # Day 694. Must NOT make 'now' = 999999!
    ]
    # 'now' must be 540. At 540, used = 0.
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "Holiday Does Not Affect 'now'")

    # 3. Duplicate holidays on same day
    s = [
        "10,*,HOLIDAY",
        "1000,*,HOLIDAY",  # Both 10//1440 and 1000//1440 are day 0
        "540,T,OPEN,P1",
        "600,T,CLOSE",
    ]
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "Duplicate Holiday Declarations")

    # 4. Multi-day span with a holiday in the middle
    # Opened Mon 540 P1. Tuesday (day 1) is a holiday.
    # Mon 540 to 600 = 60 min.
    # Mon 600 PAUSE, Wed 540 (minute 2*1440 + 540 = 3420) RESUME.
    # Wed 3420 to 3600 = 180 min. Total used = 60 + 180 = 240.
    s = [
        "540,T,OPEN,P1",
        "600,T,PAUSE",
        "2000,*,HOLIDAY",  # 2000 // 1440 = 1 (Tuesday)
        "3420,T,RESUME",
        "3600,T,CLOSE",
    ]
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 240,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "Holiday in Midst of Multi-day")


def run_ordering_and_ties():
    """Test out-of-order events and same-minute tie-breaking."""

    # 1. Out of order events sorted correctly
    s = [
        "800,T,CLOSE",
        "540,T,OPEN,P1",
        "600,T,PAUSE",
        "700,T,RESUME",
    ]
    # In time order: 540 OPEN -> 600 PAUSE (60 min) -> 700 RESUME -> 800 CLOSE (100 min)
    # Total used = 160 min.
    exp = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 160,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s), exp, "Out of Order Events")

    # 2. Same-minute tie-breaking: stable sort preserving input order
    # Test A: PAUSE then RESUME at 600 -> Ticket is RUNNING during minute 600
    s_a = [
        "540,T,OPEN,P1",
        "600,T,PAUSE",
        "600,T,RESUME",
        "700,T,CLOSE",
    ]
    # Running from 540 to 700: 160 min
    exp_a = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 160,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s_a), exp_a, "Tie: PAUSE then RESUME")

    # Test B: RESUME then PAUSE at 600 -> RESUME ignored (already running), then PAUSE -> PAUSED during 600
    s_b = [
        "540,T,OPEN,P1",
        "600,T,RESUME",
        "600,T,PAUSE",
        "700,T,CLOSE",
    ]
    # Paused from 600 to 700. Running only 540 to 600 = 60 min.
    exp_b = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s_b), exp_b, "Tie: RESUME then PAUSE")

    # 3. Same-minute CLOSE then REOPEN
    s_c = [
        "540,T,OPEN,P1",
        "600,T,CLOSE",
        "600,T,REOPEN",
        "700,T,CLOSE",
    ]
    # Running 540 to 700: 160 min.
    exp_c = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 160,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(s_c), exp_c, "Tie: CLOSE then REOPEN")


def run_output_ordering_and_filtering():
    """Verify lexicographical sorting of ticket_id and omitting unopened tickets."""

    # Python default string order: "A" < "T1" < "T10" < "T2" < "a" < "t1"
    s = [
        "540,T2,OPEN,P1",
        "540,T10,OPEN,P1",
        "540,t1,OPEN,P1",
        "540,T1,OPEN,P1",
        "540,A,OPEN,P1",
        "540,a,OPEN,P1",
        "540,NEVER_OPEN,PAUSE",  # Unopened, must not appear in output
    ]
    exp = [
        {
            "ticket_id": "A",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        },
        {
            "ticket_id": "T1",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        },
        {
            "ticket_id": "T10",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        },
        {
            "ticket_id": "T2",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        },
        {
            "ticket_id": "a",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        },
        {
            "ticket_id": "t1",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        },
    ]
    assert_result(solution.compute_sla(s), exp, "Ticket ID Code-Point Sorting")


def run_malformed_lines_tests():
    """Test extensive variations of malformed lines."""

    malformed_variations = [
        "",  # empty line
        "    \t  \n ",  # whitespace only
        "540,A",  # 2 fields
        "540,A,OPEN",  # OPEN with 3 fields
        "540,A,OPEN,P1,EXTRA",  # 5 fields
        "540,A,PAUSE,EXTRA",  # PAUSE with 4 fields
        "540,A,RESUME,P1",  # RESUME with 4 fields
        "540,A,CLOSE,NOW",  # CLOSE with 4 fields
        "540,A,REOPEN,AGAIN",  # REOPEN with 4 fields
        "540,*,HOLIDAY,EXTRA",  # HOLIDAY with 4 fields
        "-540,A,OPEN,P1",  # negative minute
        "+540,A,OPEN,P1",  # '+' sign in minute
        "54a,A,OPEN,P1",  # alpha in minute
        "12.5,A,OPEN,P1",  # float in minute
        ",A,OPEN,P1",  # empty minute
        "540,,OPEN,P1",  # empty ticket ID
        "540,   ,OPEN,P1",  # whitespace ticket ID
        "540,*,OPEN,P1",  # '*' ticket ID for non-holiday
        "540,*,CLOSE",  # '*' ticket ID for CLOSE
        "540,*,PAUSE",  # '*' ticket ID for PAUSE
        "540,*,RESUME",  # '*' ticket ID for RESUME
        "540,*,REOPEN",  # '*' ticket ID for REOPEN
        "540,*,PRIORITY,P1",  # '*' ticket ID for PRIORITY
        "540,A,HOLIDAY",  # non-'*' ticket ID for HOLIDAY
        "540,A,open,P1",  # lowercase event
        "540,A,Open,P1",  # mixed case event
        "540,A,UNKNOWN,P1",  # invalid event
        "540,A,OPEN,p1",  # lowercase priority
        "540,A,OPEN,P0",  # invalid priority P0
        "540,A,OPEN,P5",  # invalid priority P5
        "540,A,OPEN,HIGH",  # invalid priority HIGH
        "540,A,PRIORITY,P5",  # invalid priority in PRIORITY
        "999999,MALFORMED,INVALID",  # invalid minute & event, must not set now
    ]

    valid_lines = [
        "  00540  ,  VALID  ,  OPEN  ,  P2  ",  # Leading zeros and spaces allowed
        "600,VALID,CLOSE",
    ]

    stream = malformed_variations + valid_lines
    exp = [
        {
            "ticket_id": "VALID",
            "priority": "P2",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_result(solution.compute_sla(stream), exp, "Malformed Lines Filtered")

    # Stream with ONLY malformed or holiday lines
    assert_result(
        solution.compute_sla([]), [], "Empty Stream Returns Empty List"
    )
    assert_result(
        solution.compute_sla(["540,*,HOLIDAY", "1000,*,HOLIDAY"]),
        [],
        "Only Holiday Lines",
    )
    assert_result(
        solution.compute_sla(malformed_variations), [], "Only Malformed Lines"
    )


def run_large_span_scale_tests():
    """Verify performance and correct math for large minute values up to 10,000,000 and 1,000,000,000."""

    # Test 1: Minute 10,000,000
    # Day 0 (Mon): 540 to 1020 -> 480 min.
    # Day 100: Holiday (Wednesday, 100 % 7 = 2).
    # Days 1 to 6943: 6943 days = 991 weeks + 6 days (Tue-Sun -> 4 weekdays).
    # Total weekdays in [1, 6943] = 991*5 + 4 = 4959 weekdays.
    # Subtract 1 for holiday day 100 -> 4958 business days.
    # Day 6944 (Mon): 10,000,000 % 1440 = 640. Overlap with [540, 1020) = 640 - 540 = 100 min.
    # Total used = 480 + 4958 * 480 + 100 = 2,380,420 min.
    # P4 limit is 2400. Breached back in week 1 on Mon 09:01 (minute 10621).
    s1 = [
        "540,BIG,OPEN,P4",
        "144000,*,HOLIDAY",  # day 100
        "10000000,BIG,CLOSE",
    ]
    exp1 = [
        {
            "ticket_id": "BIG",
            "priority": "P4",
            "used_minutes": 2380420,
            "breached": True,
            "breached_at": 10621,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s1), exp1, "Scale Test: Minute 10,000,000"
    )

    # Test 2: Minute 900,001,000
    # 900,000,000 // 1440 = 625000. 625000 % 7 = 3 (Thursday). 900,000,000 % 1440 = 0.
    # Business hours start at Thursday 540 (900,000,540).
    # P1 limit is 240. Breach at 540 + 241 = 781 -> minute 900,000,781.
    # Closed at 900,001,000 (minute 1000 of Thursday).
    # Thursday business minutes in [540, 1000) = 460 min.
    s2 = ["900000000,LARGE,OPEN,P1", "900001000,LARGE,CLOSE"]
    exp2 = [
        {
            "ticket_id": "LARGE",
            "priority": "P1",
            "used_minutes": 460,
            "breached": True,
            "breached_at": 900000781,
            "status": "closed",
        }
    ]
    assert_result(
        solution.compute_sla(s2), exp2, "Scale Test: Minute 900,000,000"
    )


# ---------------------------------------------------------------------------
# Main Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Running Adversarial SLA Clock Test Suite...\n")

    run_spec_examples()
    run_state_transition_table()
    run_sla_boundaries_and_breaches()
    run_priority_interaction_tests()
    run_holidays_tests()
    run_ordering_and_ties()
    run_output_ordering_and_filtering()
    run_malformed_lines_tests()
    run_large_span_scale_tests()

    print("\n" + "=" * 50)
    print(f"Summary: {passed_count} passed, {failed_count} failed")
    print("=" * 50)

    if failed_count == 0:
        sys.exit(0)
    else:
        sys.exit(1)