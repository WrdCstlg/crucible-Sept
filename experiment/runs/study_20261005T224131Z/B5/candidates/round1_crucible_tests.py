import solution
import sys


def assert_equal(actual, expected, msg=""):
    if actual != expected:
        raise AssertionError(f"{msg}\nExpected: {expected}\nActual:   {actual}")


def validate_output_structure(result):
    assert_equal(isinstance(result, list), True, "Result must be a list")
    for idx, item in enumerate(result):
        assert_equal(isinstance(item, dict), True, f"Item {idx} must be a dict")
        expected_keys = {
            "ticket_id",
            "priority",
            "used_minutes",
            "breached",
            "breached_at",
            "status",
        }
        assert_equal(
            set(item.keys()), expected_keys, f"Item {idx} keys mismatch"
        )
        assert_equal(
            isinstance(item["ticket_id"], str),
            True,
            f"Item {idx} ticket_id must be str",
        )
        assert_equal(
            item["priority"] in {"P1", "P2", "P3", "P4"},
            True,
            f"Item {idx} priority invalid",
        )
        assert_equal(
            type(item["used_minutes"]) is int,
            True,
            f"Item {idx} used_minutes must be int",
        )
        assert_equal(
            type(item["breached"]) is bool,
            True,
            f"Item {idx} breached must be bool",
        )
        if item["breached"]:
            assert_equal(
                type(item["breached_at"]) is int,
                True,
                f"Item {idx} breached_at must be int when breached is True",
            )
        else:
            assert_equal(
                item["breached_at"] is None,
                True,
                f"Item {idx} breached_at must be None when breached is False",
            )
        assert_equal(
            item["status"] in {"running", "paused", "closed"},
            True,
            f"Item {idx} status invalid",
        )


def run_case(name, stream, expected):
    res = solution.compute_sla(stream)
    validate_output_structure(res)
    assert_equal(res, expected, f"Failure in test case: {name}")


def test_spec_examples():
    # Example 1: Basic Monday open to close
    run_case(
        "spec_example_1",
        ["540,A,OPEN,P2", "600,A,CLOSE"],
        [
            {
                "ticket_id": "A",
                "priority": "P2",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # Example 2: Weekend span
    run_case(
        "spec_example_2",
        ["6720,B,OPEN,P1", "10680,B,PAUSE"],
        [
            {
                "ticket_id": "B",
                "priority": "P1",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # Example 3: Breach at minute 781
    run_case(
        "spec_example_3",
        ["540,C,OPEN,P1", "900,C,CLOSE"],
        [
            {
                "ticket_id": "C",
                "priority": "P1",
                "used_minutes": 360,
                "breached": True,
                "breached_at": 781,
                "status": "closed",
            }
        ],
    )

    # Example 4: Holiday declared at end, malformed lines ignored
    run_case(
        "spec_example_4",
        [
            "540,D,OPEN,P3",
            "2040,D,PAUSE",
            "open,D,RESUME",
            "2100,D,RESUME,P1",
            "5,*,HOLIDAY",
        ],
        [
            {
                "ticket_id": "D",
                "priority": "P3",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )


def test_state_transitions_all_24():
    # Tests all 24 cells in the state-transition table: 6 events x 4 states

    # 1. NOT_OPENED + OPEN -> to RUNNING, priority P, used 0
    run_case(
        "cell_1_not_opened_open",
        ["540,T,OPEN,P1"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # 2. RUNNING + OPEN -> ignored
    run_case(
        "cell_2_running_open_ignored",
        ["540,T,OPEN,P1", "600,T,OPEN,P2"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # 3. PAUSED + OPEN -> ignored
    run_case(
        "cell_3_paused_open_ignored",
        ["540,T,OPEN,P1", "600,T,PAUSE", "660,T,OPEN,P2"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # 4. CLOSED + OPEN -> to RUNNING, priority P, used resets to 0, breach cleared
    run_case(
        "cell_4_closed_open_resets",
        [
            "540,T,OPEN,P1",
            "900,T,CLOSE",  # breached at 781, used 360
            "1000,T,OPEN,P2",  # resets used to 0, breach cleared, priority P2
            "1010,T,PAUSE",
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P2",
                "used_minutes": 10,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # 5. NOT_OPENED + PRIORITY -> ignored
    run_case(
        "cell_5_not_opened_priority_ignored",
        ["540,T_noop,PRIORITY,P1", "540,T_ok,OPEN,P2"],
        [
            {
                "ticket_id": "T_ok",
                "priority": "P2",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # 6. RUNNING + PRIORITY -> priority becomes P
    run_case(
        "cell_6_running_priority",
        ["540,T,OPEN,P1", "600,T,PRIORITY,P3"],
        [
            {
                "ticket_id": "T",
                "priority": "P3",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # 7. PAUSED + PRIORITY -> priority becomes P
    run_case(
        "cell_7_paused_priority",
        ["540,T,OPEN,P1", "600,T,PAUSE", "660,T,PRIORITY,P4"],
        [
            {
                "ticket_id": "T",
                "priority": "P4",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # 8. CLOSED + PRIORITY -> ignored
    run_case(
        "cell_8_closed_priority_ignored",
        ["540,T,OPEN,P1", "600,T,CLOSE", "660,T,PRIORITY,P4"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # 9. NOT_OPENED + PAUSE -> ignored
    run_case(
        "cell_9_not_opened_pause_ignored",
        ["540,T_noop,PAUSE", "540,T_ok,OPEN,P1"],
        [
            {
                "ticket_id": "T_ok",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # 10. RUNNING + PAUSE -> to PAUSED
    run_case(
        "cell_10_running_pause",
        ["540,T,OPEN,P1", "600,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # 11. PAUSED + PAUSE -> ignored
    run_case(
        "cell_11_paused_pause_ignored",
        ["540,T,OPEN,P1", "600,T,PAUSE", "660,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # 12. CLOSED + PAUSE -> ignored
    run_case(
        "cell_12_closed_pause_ignored",
        ["540,T,OPEN,P1", "600,T,CLOSE", "660,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # 13. NOT_OPENED + RESUME -> ignored
    run_case(
        "cell_13_not_opened_resume_ignored",
        ["540,T_noop,RESUME", "540,T_ok,OPEN,P1"],
        [
            {
                "ticket_id": "T_ok",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # 14. RUNNING + RESUME -> ignored
    run_case(
        "cell_14_running_resume_ignored",
        ["540,T,OPEN,P1", "600,T,RESUME", "660,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # 15. PAUSED + RESUME -> to RUNNING
    run_case(
        "cell_15_paused_resume",
        ["540,T,OPEN,P1", "600,T,PAUSE", "660,T,RESUME", "700,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 100,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # 16. CLOSED + RESUME -> ignored
    run_case(
        "cell_16_closed_resume_ignored",
        ["540,T,OPEN,P1", "600,T,CLOSE", "660,T,RESUME"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # 17. NOT_OPENED + CLOSE -> ignored
    run_case(
        "cell_17_not_opened_close_ignored",
        ["540,T_noop,CLOSE", "540,T_ok,OPEN,P1"],
        [
            {
                "ticket_id": "T_ok",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # 18. RUNNING + CLOSE -> to CLOSED
    run_case(
        "cell_18_running_close",
        ["540,T,OPEN,P1", "600,T,CLOSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # 19. PAUSED + CLOSE -> to CLOSED
    run_case(
        "cell_19_paused_close",
        ["540,T,OPEN,P1", "600,T,PAUSE", "660,T,CLOSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # 20. CLOSED + CLOSE -> ignored
    run_case(
        "cell_20_closed_close_ignored",
        ["540,T,OPEN,P1", "600,T,CLOSE", "660,T,CLOSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # 21. NOT_OPENED + REOPEN -> ignored
    run_case(
        "cell_21_not_opened_reopen_ignored",
        ["540,T_noop,REOPEN", "540,T_ok,OPEN,P1"],
        [
            {
                "ticket_id": "T_ok",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # 22. RUNNING + REOPEN -> ignored
    run_case(
        "cell_22_running_reopen_ignored",
        ["540,T,OPEN,P1", "600,T,REOPEN", "660,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # 23. PAUSED + REOPEN -> ignored
    run_case(
        "cell_23_paused_reopen_ignored",
        ["540,T,OPEN,P1", "600,T,PAUSE", "660,T,REOPEN"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # 24. CLOSED + REOPEN -> to RUNNING, used continues, breach kept, priority kept
    run_case(
        "cell_24_closed_reopen",
        ["540,T,OPEN,P1", "600,T,CLOSE", "660,T,REOPEN", "700,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 100,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )


def test_exact_sla_boundaries():
    # Boundary checks for all 4 priorities:
    # Strictly greater (> limit) breaches. Exactly equal (== limit) does NOT breach.

    # P1: Limit = 240
    # Exactly 240 minutes: 540 to 780
    run_case(
        "p1_exact_limit_no_breach",
        ["540,T,OPEN,P1", "780,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 240,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )
    # 241 minutes: 540 to 781 -> breach at 781
    run_case(
        "p1_limit_plus_one_breach",
        ["540,T,OPEN,P1", "781,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 241,
                "breached": True,
                "breached_at": 781,
                "status": "paused",
            }
        ],
    )

    # P2: Limit = 480 (Exact length of 1 business day)
    # Day 0 Monday has 480 business minutes: 540 to 1020.
    run_case(
        "p2_exact_limit_no_breach",
        ["540,T,OPEN,P2", "1020,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P2",
                "used_minutes": 480,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )
    # Next business minute is Tuesday 09:00 (minute 1980).
    # Minute 1980 is 481st running minute. At 1981, used_minutes = 481 -> breach at 1981!
    run_case(
        "p2_limit_plus_one_breach_across_night",
        ["540,T,OPEN,P2", "1981,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P2",
                "used_minutes": 481,
                "breached": True,
                "breached_at": 1981,
                "status": "paused",
            }
        ],
    )

    # P3: Limit = 1440 (Exact length of 3 business days: Mon, Tue, Wed = 3 * 480)
    # Wednesday 17:00 is 2880 + 1020 = 3900.
    run_case(
        "p3_exact_limit_no_breach",
        ["540,T,OPEN,P3", "3900,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P3",
                "used_minutes": 1440,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )
    # Thursday 09:00 is 4320 + 540 = 4860. Minute 4861 has 1441 used minutes -> breach at 4861!
    run_case(
        "p3_limit_plus_one_breach",
        ["540,T,OPEN,P3", "4861,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P3",
                "used_minutes": 1441,
                "breached": True,
                "breached_at": 4861,
                "status": "paused",
            }
        ],
    )

    # P4: Limit = 2400 (Exact length of 5 business days: Mon, Tue, Wed, Thu, Fri = 5 * 480)
    # Friday 17:00 is 5760 + 1020 = 6780.
    run_case(
        "p4_exact_limit_no_breach",
        ["540,T,OPEN,P4", "6780,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P4",
                "used_minutes": 2400,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )
    # Next Monday 09:00 is Day 7: 10080 + 540 = 10620.
    # At 10621, used_minutes = 2401 -> breach at 10621!
    run_case(
        "p4_limit_plus_one_breach_across_weekend",
        ["540,T,OPEN,P4", "10621,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P4",
                "used_minutes": 2401,
                "breached": True,
                "breached_at": 10621,
                "status": "paused",
            }
        ],
    )


def test_ties_and_same_minute():
    # Priority raise at the very minute of breach prevents it:
    # At minute 781, used_minutes reaches 241. Priority is raised to P2 (limit 480).
    run_case(
        "priority_raise_prevents_breach",
        ["540,T,OPEN,P1", "781,T,PRIORITY,P2", "781,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P2",
                "used_minutes": 241,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # Priority downgrade at minute 781 triggers breach immediately:
    run_case(
        "priority_downgrade_triggers_breach",
        ["540,T,OPEN,P2", "781,T,PRIORITY,P1", "781,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 241,
                "breached": True,
                "breached_at": 781,
                "status": "paused",
            }
        ],
    )

    # Stable sort check: multiple priority changes at same minute
    # First sets P2, then sets P1 -> final priority is P1 -> breach at 781
    run_case(
        "stable_sort_priority_p2_then_p1",
        [
            "540,T,OPEN,P1",
            "781,T,PRIORITY,P2",
            "781,T,PRIORITY,P1",
            "781,T,PAUSE",
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 241,
                "breached": True,
                "breached_at": 781,
                "status": "paused",
            }
        ],
    )
    # First sets P1, then sets P2 -> final priority is P2 -> no breach
    run_case(
        "stable_sort_priority_p1_then_p2",
        [
            "540,T,OPEN,P1",
            "781,T,PRIORITY,P1",
            "781,T,PRIORITY,P2",
            "781,T,PAUSE",
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P2",
                "used_minutes": 241,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # Stable sort check: CLOSE then REOPEN then PAUSE at same minute
    run_case(
        "same_minute_close_reopen_pause",
        [
            "540,T,OPEN,P1",
            "600,T,CLOSE",
            "600,T,REOPEN",
            "600,T,PAUSE",
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # Multiple tickets with events at the exact same minute
    run_case(
        "multiple_tickets_same_minute",
        [
            "540,T2,OPEN,P1",
            "540,T1,OPEN,P2",
            "600,T1,CLOSE",
            "600,T2,PAUSE",
        ],
        [
            {
                "ticket_id": "T1",
                "priority": "P2",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T2",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
        ],
    )


def test_out_of_order_and_holidays():
    # Stream in reverse chronological order
    run_case(
        "reverse_order_events",
        ["900,C,CLOSE", "540,C,OPEN,P1"],
        [
            {
                "ticket_id": "C",
                "priority": "P1",
                "used_minutes": 360,
                "breached": True,
                "breached_at": 781,
                "status": "closed",
            }
        ],
    )

    # Holidays declared before, during, and after ticket events
    # Day 0 (Monday) is holiday (minute 100), Day 1 (Tuesday) is holiday (minute 2000)
    # Ticket runs Monday 09:00 (540) to Wednesday 10:00 (Wednesday 09:00 is 2880 + 540 = 3420; 10:00 is 3480)
    # Monday has 0 business mins (holiday).
    # Tuesday has 0 business mins (holiday).
    # Wednesday 09:00 to 10:00 = 60 mins.
    run_case(
        "holidays_everywhere",
        [
            "100,*,HOLIDAY",  # day 0
            "3480,T,PAUSE",
            "540,T,OPEN,P1",
            "2000,*,HOLIDAY",  # day 1
            "1439,*,HOLIDAY",  # day 0 again (idempotent)
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # Holiday on weekend has no effect on business hours
    # Saturday is day 5: 7200.
    run_case(
        "holiday_on_weekend",
        [
            "540,T,OPEN,P1",
            "600,T,CLOSE",
            "7500,*,HOLIDAY",  # Day 5 (Saturday)
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )


def test_definition_of_now():
    # 1. Ignored event on another ticket defines "now"
    # T1 opened at 540, paused at 600.
    # T2 has an invalid transition (PAUSE while NOT_OPENED) at minute 2000.
    # "now" must be 2000!
    # T2 was never validly OPENed, so T2 does not appear in output.
    # T1 was paused at 600, so at minute 2000 its used time is still 60.
    run_case(
        "now_defined_by_ignored_event",
        ["540,T1,OPEN,P1", "600,T1,PAUSE", "2000,T2,PAUSE"],
        [
            {
                "ticket_id": "T1",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # 2. Ticket running up to "now" defined by another ticket's ignored event
    # T1 opened at 540 and not explicitly paused/closed.
    # At minute 800, T2 has an ignored event.
    # "now" is 800. T1 has run from 540 to 800 (260 mins).
    # P1 limit is 240 -> breached at 781!
    run_case(
        "now_advances_running_ticket",
        ["540,T1,OPEN,P1", "800,T2,CLOSE"],
        [
            {
                "ticket_id": "T1",
                "priority": "P1",
                "used_minutes": 260,
                "breached": True,
                "breached_at": 781,
                "status": "running",
            }
        ],
    )

    # 3. HOLIDAY line does NOT affect "now"
    run_case(
        "holiday_does_not_affect_now",
        ["540,T,OPEN,P1", "600,T,CLOSE", "99999,*,HOLIDAY"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # 4. Empty stream or only holidays or only malformed -> returns []
    run_case("empty_stream", [], [])
    run_case("only_holidays", ["540,*,HOLIDAY", "2000,*,HOLIDAY"], [])
    run_case("only_malformed", ["bad,line", "123", ",,,", "open,T,P1"], [])
    run_case(
        "no_valid_open",
        ["540,T,PAUSE", "600,T,CLOSE", "700,T,RESUME", "800,T,REOPEN"],
        [],
    )


def test_malformed_lines():
    # Various malformed lines should all be silently ignored
    malformed_records = [
        "",  # Empty
        "   ",  # Spaces
        "540,*,OPEN,P1",  # Ticket ID * on ticket event
        "540,*,PAUSE",  # Ticket ID * on PAUSE
        "540,*,CLOSE",  # Ticket ID * on CLOSE
        "540,*,RESUME",  # Ticket ID * on RESUME
        "540,*,REOPEN",  # Ticket ID * on REOPEN
        "540,*,PRIORITY,P1",  # Ticket ID * on PRIORITY
        "540,T1,HOLIDAY",  # Ticket ID not * on HOLIDAY
        "540,*,HOLIDAY,P1",  # HOLIDAY with 4 fields
        "540,T1,OPEN",  # OPEN with 3 fields
        "540,T1,OPEN,P1,EXTRA",  # OPEN with 5 fields
        "540,T1,PRIORITY",  # PRIORITY with 3 fields
        "540,T1,PAUSE,P1",  # PAUSE with 4 fields
        "540,T1,RESUME,P1",  # RESUME with 4 fields
        "540,T1,CLOSE,P1",  # CLOSE with 4 fields
        "540,T1,REOPEN,P1",  # REOPEN with 4 fields
        "540,T1,open,P1",  # lowercase event
        "540,T1,pause",  # lowercase event
        "540,T1,UNKNOWN",  # unknown event
        "540,T1,OPEN,p1",  # lowercase priority
        "540,T1,OPEN,P5",  # invalid priority P5
        "540,T1,OPEN,HIGH",  # invalid priority
        "540,T1,PRIORITY,P0",  # invalid priority P0
        "-540,T1,OPEN,P1",  # negative minute
        "+540,T1,OPEN,P1",  # plus sign
        "540.5,T1,OPEN,P1",  # float minute
        "abc,T1,OPEN,P1",  # non-numeric minute
        ",T1,OPEN,P1",  # empty minute
        "540,,OPEN,P1",  # empty ticket ID
        "540,   ,OPEN,P1",  # whitespace ticket ID
        "100000000,T_bad,INVALID_EVENT",  # future malformed event
    ]

    valid_stream = [
        "  00540  ,  T1  ,  OPEN  ,  P1  ",  # Leading zeros and whitespace trimming valid
        "600,T1,CLOSE",
    ]

    # Combine valid stream with all malformed records
    stream = malformed_records[:10] + valid_stream + malformed_records[10:]
    run_case(
        "malformed_lines_handling",
        stream,
        [
            {
                "ticket_id": "T1",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )


def test_output_formatting_and_types():
    # Tickets sorted by ticket_id ascending in Python code-point order
    # Code-point order: "1" < "A" < "T1" < "T10" < "T2" < "a" < "t1"
    stream = [
        "540,T2,OPEN,P1",
        "540,T10,OPEN,P1",
        "540,T1,OPEN,P1",
        "540,t1,OPEN,P1",
        "540,a,OPEN,P1",
        "540,A,OPEN,P1",
        "540,1,OPEN,P1",
    ]
    res = solution.compute_sla(stream)
    validate_output_structure(res)
    ids = [d["ticket_id"] for d in res]
    expected_ids = ["1", "A", "T1", "T10", "T2", "a", "t1"]
    assert_equal(ids, expected_ids, "Ticket IDs output ordering mismatch")


def test_lifecycle_breach_recovery():
    # Complex lifecycle:
    # 1. Opens at 540 (Monday 09:00) with P2 (limit 480).
    # 2. Runs until 840 (300 mins).
    # 3. Pauses at 840.
    # 4. At 900, while PAUSED, priority dropped to P1 (limit 240).
    #    Used time is 300 > 240. Immediate breach at 900!
    # 5. At 950, ticket is CLOSED.
    # 6. At 1000, REOPEN -> breach is KEPT (breached_at=900).
    # 7. At 1010, CLOSE.
    # 8. At 1020, OPEN,P3 -> valid OPEN from CLOSED clears breach and resets used time to 0!
    # 9. Next day (Tuesday) runs 09:00 (1980) to 10:00 (2040) -> used 60 mins, P3 (limit 1440).
    #    Breach is False!
    stream = [
        "540,T,OPEN,P2",
        "840,T,PAUSE",
        "900,T,PRIORITY,P1",
        "950,T,CLOSE",
        "1000,T,REOPEN",
        "1010,T,CLOSE",
        "1020,T,OPEN,P3",
        "2040,T,PAUSE",
    ]
    run_case(
        "lifecycle_breach_recovery",
        stream,
        [
            {
                "ticket_id": "T",
                "priority": "P3",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )


def test_non_business_hours_and_weekend():
    # 1. Ticket opened during non-business hours
    # Monday 01:00 is minute 60. Closed at Monday 08:00 (minute 480).
    # All before 09:00 (540). Used minutes = 0.
    run_case(
        "non_business_night_run",
        ["60,T,OPEN,P1", "480,T,CLOSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # 2. Ticket opened on Saturday and paused on Sunday
    # Saturday is Day 5 (7200 to 8639), Sunday is Day 6 (8640 to 10079).
    run_case(
        "weekend_run",
        ["7500,T,OPEN,P1", "9000,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # 3. Breach on weekend due to PRIORITY drop while PAUSED
    # Runs 250 minutes on Monday: 540 to 790 with P2 (limit 480).
    # Pauses at 790.
    # On Saturday (minute 7500), priority drops to P1 (limit 240).
    # Used time is 250 > 240 -> breaches at minute 7500 on Saturday!
    run_case(
        "breach_on_weekend_priority_drop",
        ["540,T,OPEN,P2", "790,T,PAUSE", "7500,T,PRIORITY,P1"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 250,
                "breached": True,
                "breached_at": 7500,
                "status": "paused",
            }
        ],
    )


def test_performance_and_large_span():
    # 1. Massive minute gap test:
    # If the implementation steps minute-by-minute over the whole gap up to 100,000,000,
    # this will immediately time out.
    stream_large_gap = [
        "540,T1,OPEN,P1",
        "600,T1,CLOSE",
        "100000000,T_noop,PAUSE",  # T_noop ignored
    ]
    run_case(
        "massive_minute_gap_efficiency",
        stream_large_gap,
        [
            {
                "ticket_id": "T1",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # 2. Multi-week business minutes hand-calculated check:
    # Runs from Week 0 Monday 09:00 (540) to Week 10 Monday 09:00 (101340).
    # 10 full weeks span.
    # Day 16 (Wednesday of Week 2) is a holiday (minute 23040).
    # Normal week has 5 * 480 = 2400 business minutes.
    # Week 2 has 4 * 480 = 1920 business minutes.
    # Total business minutes: 9 * 2400 + 1920 = 21600 + 1920 = 23520 business minutes.
    # Priority P4 limit = 2400.
    # Week 0 Monday 09:00 to Friday 17:00 (minute 6780) uses exactly 2400 business minutes.
    # The 2401st business minute is Week 1 Monday 09:00 (minute 10620).
    # Therefore, the breach occurs at minute 10621!
    stream_multi_week = [
        "540,T_long,OPEN,P4",
        "23040,*,HOLIDAY",  # 23040 // 1440 = 16 (Wednesday Week 2)
        "101340,T_long,PAUSE",  # Week 10 Monday 09:00
    ]
    run_case(
        "multi_week_span_calculation",
        stream_multi_week,
        [
            {
                "ticket_id": "T_long",
                "priority": "P4",
                "used_minutes": 23520,
                "breached": True,
                "breached_at": 10621,
                "status": "paused",
            }
        ],
    )


def main():
    test_suites = [
        ("Spec Examples", test_spec_examples),
        ("State Transition Table (all 24 cells)", test_state_transitions_all_24),
        ("Exact SLA Boundaries", test_exact_sla_boundaries),
        ("Ties and Same-Minute Events", test_ties_and_same_minute),
        ("Out-of-Order Events and Holidays", test_out_of_order_and_holidays),
        ("Definition of 'now'", test_definition_of_now),
        ("Malformed Lines Handling", test_malformed_lines),
        ("Output Formatting and Ordering", test_output_formatting_and_types),
        ("Lifecycle and Breach Recovery", test_lifecycle_breach_recovery),
        ("Non-Business Hours and Weekends", test_non_business_hours_and_weekend),
        ("Performance and Large Minute Spans", test_performance_and_large_span),
    ]

    total_passed = 0
    total_failed = 0

    print("Running adversarial SLA test suite...\n" + "=" * 60)

    for suite_name, suite_func in test_suites:
        try:
            suite_func()
            print(f"[PASS] {suite_name}")
            total_passed += 1
        except Exception as e:
            print(f"[FAIL] {suite_name}: {e}")
            total_failed += 1

    print("=" * 60)
    print(f"Summary: {total_passed} passed, {total_failed} failed.")

    if total_failed == 0:
        print("All test suites passed successfully.")
        sys.exit(0)
    else:
        print("Some test suites failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()