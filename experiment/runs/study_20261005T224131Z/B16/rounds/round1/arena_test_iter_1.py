import solution
import sys
import time

# Test runner infrastructure
passed_count = 0
failed_count = 0
failures = []


def run_test(name, func):
    global passed_count, failed_count
    try:
        func()
        passed_count += 1
        print(f"PASS: {name}")
    except AssertionError as e:
        failed_count += 1
        failures.append((name, str(e)))
        print(f"FAIL: {name} - {e}")
    except Exception as e:
        failed_count += 1
        failures.append((name, f"Unexpected exception: {type(e).__name__}: {e}"))
        print(f"FAIL: {name} - Unexpected exception: {type(e).__name__}: {e}")


def assert_equal(actual, expected, msg=""):
    assert actual == expected, (
        f"{msg}\nExpected: {expected!r}\nActual:   {actual!r}"
    )


def assert_ticket_dict(t):
    expected_keys = {"ticket_id", "priority", "used_minutes", "breached", "breached_at", "status"}
    assert isinstance(t, dict), f"Expected dict, got {type(t)}"
    assert set(t.keys()) == expected_keys, f"Keys mismatch. Expected {expected_keys}, got {set(t.keys())}"
    assert isinstance(t["ticket_id"], str), f"ticket_id must be str, got {type(t['ticket_id'])}"
    assert t["priority"] in {"P1", "P2", "P3", "P4"}, f"invalid priority {t['priority']}"
    assert type(t["used_minutes"]) is int, f"used_minutes must be int, got {type(t['used_minutes'])}"
    assert type(t["breached"]) is bool, f"breached must be bool, got {type(t['breached'])}"
    if t["breached"]:
        assert type(t["breached_at"]) is int, f"breached_at must be int when breached, got {type(t['breached_at'])}"
    else:
        assert t["breached_at"] is None, f"breached_at must be None when not breached, got {t['breached_at']}"
    assert t["status"] in {"running", "paused", "closed"}, f"invalid status {t['status']}"


# ---------------------------------------------------------------------------
# 1. Spec Examples
# ---------------------------------------------------------------------------
def test_spec_example_1():
    stream = [
        "540,A,OPEN,P2",
        "600,A,CLOSE",
    ]
    res = solution.compute_sla(stream)
    assert type(res) is list
    assert len(res) == 1
    assert_ticket_dict(res[0])
    expected = [
        {"ticket_id": "A", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
    ]
    assert_equal(res, expected, "Example 1 mismatch")


def test_spec_example_2():
    stream = [
        "6720,B,OPEN,P1",
        "10680,B,PAUSE",
    ]
    res = solution.compute_sla(stream)
    expected = [
        {"ticket_id": "B", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "paused"}
    ]
    assert_equal(res, expected, "Example 2 mismatch")


def test_spec_example_3():
    stream = [
        "540,C,OPEN,P1",
        "900,C,CLOSE",
    ]
    res = solution.compute_sla(stream)
    expected = [
        {"ticket_id": "C", "priority": "P1", "used_minutes": 360, "breached": True, "breached_at": 781, "status": "closed"}
    ]
    assert_equal(res, expected, "Example 3 mismatch")


def test_spec_example_4():
    stream = [
        "540,D,OPEN,P3",
        "2040,D,PAUSE",
        "open,D,RESUME",
        "2100,D,RESUME,P1",
        "5,*,HOLIDAY",
    ]
    res = solution.compute_sla(stream)
    expected = [
        {"ticket_id": "D", "priority": "P3", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}
    ]
    assert_equal(res, expected, "Example 4 mismatch")


# ---------------------------------------------------------------------------
# 2. State-Transition Table (All 24 Cells Tested Explicitly)
# ---------------------------------------------------------------------------
def test_state_table_cell_1_to_6_not_opened():
    # Tickets only receiving ignored events when NOT_OPENED should NEVER appear in output
    stream = [
        "540,T_PRIO,PRIORITY,P1",
        "540,T_PAUSE,PAUSE",
        "540,T_RES,RESUME",
        "540,T_CLOSE,CLOSE",
        "540,T_REOPEN,REOPEN",
        "540,VALID,OPEN,P1",
        "600,VALID,CLOSE",
    ]
    res = solution.compute_sla(stream)
    assert_equal(len(res), 1)
    assert_equal(res[0]["ticket_id"], "VALID")

    # When valid OPEN follows previously ignored events on NOT_OPENED, OPEN works cleanly
    stream2 = [
        "500,T,PRIORITY,P2",
        "510,T,PAUSE",
        "520,T,RESUME",
        "530,T,CLOSE",
        "535,T,REOPEN",
        "540,T,OPEN,P1",
        "600,T,CLOSE",
    ]
    res2 = solution.compute_sla(stream2)
    expected2 = [
        {"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
    ]
    assert_equal(res2, expected2, "Cell 1-6 recovery mismatch")


def test_state_table_running_cells_7_to_12():
    # Cell 7: RUNNING + OPEN -> ignored
    stream_7 = ["540,T,OPEN,P1", "560,T,OPEN,P2", "600,T,CLOSE"]
    res_7 = solution.compute_sla(stream_7)
    assert_equal(res_7, [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}])

    # Cell 8: RUNNING + PRIORITY -> updates priority
    stream_8 = ["540,T,OPEN,P1", "560,T,PRIORITY,P2", "600,T,CLOSE"]
    res_8 = solution.compute_sla(stream_8)
    assert_equal(res_8, [{"ticket_id": "T", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}])

    # Cell 9: RUNNING + PAUSE -> to PAUSED
    stream_9 = ["540,T,OPEN,P1", "600,T,PAUSE"]
    res_9 = solution.compute_sla(stream_9)
    assert_equal(res_9, [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}])

    # Cell 10: RUNNING + RESUME -> ignored
    stream_10 = ["540,T,OPEN,P1", "560,T,RESUME", "600,T,CLOSE"]
    res_10 = solution.compute_sla(stream_10)
    assert_equal(res_10, [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}])

    # Cell 11: RUNNING + CLOSE -> to CLOSED
    stream_11 = ["540,T,OPEN,P1", "600,T,CLOSE"]
    res_11 = solution.compute_sla(stream_11)
    assert_equal(res_11, [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}])

    # Cell 12: RUNNING + REOPEN -> ignored
    stream_12 = ["540,T,OPEN,P1", "560,T,REOPEN", "600,T,CLOSE"]
    res_12 = solution.compute_sla(stream_12)
    assert_equal(res_12, [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}])


def test_state_table_paused_cells_13_to_18():
    # Cell 13: PAUSED + OPEN -> ignored
    stream_13 = ["540,T,OPEN,P1", "560,T,PAUSE", "580,T,OPEN,P2", "600,B,PAUSE"]
    res_13 = solution.compute_sla(stream_13)
    assert_equal(res_13, [{"ticket_id": "T", "priority": "P1", "used_minutes": 20, "breached": False, "breached_at": None, "status": "paused"}])

    # Cell 14: PAUSED + PRIORITY -> updates priority
    stream_14 = ["540,T,OPEN,P1", "560,T,PAUSE", "580,T,PRIORITY,P2", "600,B,PAUSE"]
    res_14 = solution.compute_sla(stream_14)
    assert_equal(res_14, [{"ticket_id": "T", "priority": "P2", "used_minutes": 20, "breached": False, "breached_at": None, "status": "paused"}])

    # Cell 15: PAUSED + PAUSE -> ignored
    stream_15 = ["540,T,OPEN,P1", "560,T,PAUSE", "580,T,PAUSE", "600,B,PAUSE"]
    res_15 = solution.compute_sla(stream_15)
    assert_equal(res_15, [{"ticket_id": "T", "priority": "P1", "used_minutes": 20, "breached": False, "breached_at": None, "status": "paused"}])

    # Cell 16: PAUSED + RESUME -> to RUNNING
    stream_16 = ["540,T,OPEN,P1", "560,T,PAUSE", "580,T,RESUME", "600,T,CLOSE"]
    res_16 = solution.compute_sla(stream_16)
    assert_equal(res_16, [{"ticket_id": "T", "priority": "P1", "used_minutes": 40, "breached": False, "breached_at": None, "status": "closed"}])

    # Cell 17: PAUSED + CLOSE -> to CLOSED
    stream_17 = ["540,T,OPEN,P1", "560,T,PAUSE", "600,T,CLOSE"]
    res_17 = solution.compute_sla(stream_17)
    assert_equal(res_17, [{"ticket_id": "T", "priority": "P1", "used_minutes": 20, "breached": False, "breached_at": None, "status": "closed"}])

    # Cell 18: PAUSED + REOPEN -> ignored
    stream_18 = ["540,T,OPEN,P1", "560,T,PAUSE", "580,T,REOPEN", "600,B,PAUSE"]
    res_18 = solution.compute_sla(stream_18)
    assert_equal(res_18, [{"ticket_id": "T", "priority": "P1", "used_minutes": 20, "breached": False, "breached_at": None, "status": "paused"}])


def test_state_table_closed_cells_19_to_24():
    # Cell 19: CLOSED + OPEN -> to RUNNING, priority P, used resets to 0, breach cleared
    stream_19 = [
        "540,T,OPEN,P1",
        "900,T,CLOSE",      # ran 360 mins, breached at 781
        "1000,T,OPEN,P2",   # resets used to 0, breach cleared, priority P2
        "1020,T,CLOSE",     # ran 20 mins
    ]
    res_19 = solution.compute_sla(stream_19)
    assert_equal(res_19, [{"ticket_id": "T", "priority": "P2", "used_minutes": 20, "breached": False, "breached_at": None, "status": "closed"}])

    # Cell 20: CLOSED + PRIORITY -> ignored
    stream_20 = ["540,T,OPEN,P1", "600,T,CLOSE", "660,T,PRIORITY,P2"]
    res_20 = solution.compute_sla(stream_20)
    assert_equal(res_20, [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}])

    # Cell 21: CLOSED + PAUSE -> ignored
    stream_21 = ["540,T,OPEN,P1", "600,T,CLOSE", "660,T,PAUSE"]
    res_21 = solution.compute_sla(stream_21)
    assert_equal(res_21, [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}])

    # Cell 22: CLOSED + RESUME -> ignored
    stream_22 = ["540,T,OPEN,P1", "600,T,CLOSE", "660,T,RESUME"]
    res_22 = solution.compute_sla(stream_22)
    assert_equal(res_22, [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}])

    # Cell 23: CLOSED + CLOSE -> ignored
    stream_23 = ["540,T,OPEN,P1", "600,T,CLOSE", "660,T,CLOSE"]
    res_23 = solution.compute_sla(stream_23)
    assert_equal(res_23, [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}])

    # Cell 24: CLOSED + REOPEN -> to RUNNING, used continues, breach kept, priority kept
    stream_24 = [
        "540,T,OPEN,P1",
        "900,T,CLOSE",      # breached at 781, used 360
        "1000,T,REOPEN",    # continues, keeps breach and priority
        "1020,T,CLOSE",     # ran 20 more mins
    ]
    res_24 = solution.compute_sla(stream_24)
    expected_24 = [
        {"ticket_id": "T", "priority": "P1", "used_minutes": 380, "breached": True, "breached_at": 781, "status": "closed"}
    ]
    assert_equal(res_24, expected_24, "Cell 24 mismatch")


# ---------------------------------------------------------------------------
# 3. Exact SLA Boundaries & Breaches Across Priorities
# ---------------------------------------------------------------------------
def test_exact_sla_boundaries():
    # P1: limit 240
    # 240 used -> NOT breached
    s_p1_exact = ["540,A,OPEN,P1", "780,A,CLOSE"]
    res = solution.compute_sla(s_p1_exact)
    assert_equal(res, [{"ticket_id": "A", "priority": "P1", "used_minutes": 240, "breached": False, "breached_at": None, "status": "closed"}])

    # 241 used -> breached at 781
    s_p1_over = ["540,A,OPEN,P1", "781,A,CLOSE"]
    res = solution.compute_sla(s_p1_over)
    assert_equal(res, [{"ticket_id": "A", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "closed"}])

    # P2: limit 480 (all day Monday 540 to 1020 is 480 business minutes)
    # Overnight, closed Tuesday morning at 09:00 (1980) -> used 480 -> NOT breached
    s_p2_exact = ["540,B,OPEN,P2", "1980,B,CLOSE"]
    res = solution.compute_sla(s_p2_exact)
    assert_equal(res, [{"ticket_id": "B", "priority": "P2", "used_minutes": 480, "breached": False, "breached_at": None, "status": "closed"}])

    # Runs 1 business minute on Tuesday morning -> 1981 -> breached at 1981
    s_p2_over = ["540,B,OPEN,P2", "1981,B,CLOSE"]
    res = solution.compute_sla(s_p2_over)
    assert_equal(res, [{"ticket_id": "B", "priority": "P2", "used_minutes": 481, "breached": True, "breached_at": 1981, "status": "closed"}])

    # P3: limit 1440 (exactly 3 full days: Mon 480, Tue 480, Wed 480)
    # Thursday 09:00 is minute 4860 (3*1440 + 540).
    # At 4860, used is 1440 -> NOT breached
    s_p3_exact = ["540,C,OPEN,P3", "4860,C,CLOSE"]
    res = solution.compute_sla(s_p3_exact)
    assert_equal(res, [{"ticket_id": "C", "priority": "P3", "used_minutes": 1440, "breached": False, "breached_at": None, "status": "closed"}])

    # Thursday 09:01 is minute 4861 -> breached at 4861
    s_p3_over = ["540,C,OPEN,P3", "4861,C,CLOSE"]
    res = solution.compute_sla(s_p3_over)
    assert_equal(res, [{"ticket_id": "C", "priority": "P3", "used_minutes": 1441, "breached": True, "breached_at": 4861, "status": "closed"}])

    # P4: limit 2400 (5 full days: Mon..Fri = 2400 mins). Ends Friday 17:00 (6780).
    # Sat (Day 5), Sun (Day 6) = 0 mins.
    # Next Monday 09:00 is 10620. Used is 2400 -> NOT breached
    s_p4_exact = ["540,D,OPEN,P4", "10620,D,CLOSE"]
    res = solution.compute_sla(s_p4_exact)
    assert_equal(res, [{"ticket_id": "D", "priority": "P4", "used_minutes": 2400, "breached": False, "breached_at": None, "status": "closed"}])

    # Next Monday 09:01 is 10621 -> breached at 10621
    s_p4_over = ["540,D,OPEN,P4", "10621,D,CLOSE"]
    res = solution.compute_sla(s_p4_over)
    assert_equal(res, [{"ticket_id": "D", "priority": "P4", "used_minutes": 2401, "breached": True, "breached_at": 10621, "status": "closed"}])


# ---------------------------------------------------------------------------
# 4. Breach Mechanics, Priority Shifts & Stickiness
# ---------------------------------------------------------------------------
def test_priority_change_preventing_breach():
    # Ticket at P1 would breach at 781. Priority raised to P2 at minute 781.
    # Because events at a minute are applied before checking breach, it does NOT breach at 781!
    stream = [
        "540,A,OPEN,P1",
        "781,A,PRIORITY,P2",
        "800,A,CLOSE",
    ]
    res = solution.compute_sla(stream)
    assert_equal(res, [{"ticket_id": "A", "priority": "P2", "used_minutes": 260, "breached": False, "breached_at": None, "status": "closed"}])


def test_priority_change_causing_immediate_breach_while_paused():
    # Ticket runs 300 business minutes under P2 (limit 480).
    # Pauses at 840 (540 + 300).
    # At minute 900 (while paused!), priority changed to P1 (limit 240).
    # Used is 300 > 240. Breaches immediately at 900!
    stream = [
        "540,A,OPEN,P2",
        "840,A,PAUSE",
        "900,A,PRIORITY,P1",
    ]
    res = solution.compute_sla(stream)
    assert_equal(res, [{"ticket_id": "A", "priority": "P1", "used_minutes": 300, "breached": True, "breached_at": 900, "status": "paused"}])


def test_priority_change_outside_business_hours():
    # Priority changed at minute 1200 (Monday 20:00, outside business hours)
    stream = [
        "540,A,OPEN,P2",
        "840,A,PAUSE",
        "1200,A,PRIORITY,P1",
    ]
    res = solution.compute_sla(stream)
    assert_equal(res, [{"ticket_id": "A", "priority": "P1", "used_minutes": 300, "breached": True, "breached_at": 1200, "status": "paused"}])


def test_breach_stickiness_after_priority_raise():
    # Ticket breaches at 781 under P1. Later at 900, priority raised to P4.
    # Breach remains sticky!
    stream = [
        "540,A,OPEN,P1",
        "900,A,PRIORITY,P4",
        "960,A,CLOSE",
    ]
    res = solution.compute_sla(stream)
    expected = [
        {"ticket_id": "A", "priority": "P4", "used_minutes": 420, "breached": True, "breached_at": 781, "status": "closed"}
    ]
    assert_equal(res, expected, "Breach stickiness mismatch")


def test_multiple_priority_changes_at_same_minute():
    # Case 1: P2 -> P1 -> P3 at minute 900 (used 300). Final priority is P3 (limit 1440).
    # Evaluated AFTER all events at 900: 300 <= 1440 -> NO breach!
    stream_1 = [
        "540,A,OPEN,P2",
        "840,A,PAUSE",
        "900,A,PRIORITY,P1",
        "900,A,PRIORITY,P3",
    ]
    res_1 = solution.compute_sla(stream_1)
    assert_equal(res_1, [{"ticket_id": "A", "priority": "P3", "used_minutes": 300, "breached": False, "breached_at": None, "status": "paused"}])

    # Case 2: P2 -> P3 -> P1 at minute 900 (used 300). Final priority is P1 (limit 240).
    # Evaluated AFTER all events at 900: 300 > 240 -> breaches at 900!
    stream_2 = [
        "540,A,OPEN,P2",
        "840,A,PAUSE",
        "900,A,PRIORITY,P3",
        "900,A,PRIORITY,P1",
    ]
    res_2 = solution.compute_sla(stream_2)
    assert_equal(res_2, [{"ticket_id": "A", "priority": "P1", "used_minutes": 300, "breached": True, "breached_at": 900, "status": "paused"}])


def test_reopen_and_second_breach():
    # Ticket breaches, closes, opens anew (breach cleared), and breaches AGAIN at a new minute!
    stream = [
        "540,A,OPEN,P1",
        "800,A,CLOSE",      # breached at 781
        "900,A,OPEN,P1",    # breach cleared, used resets to 0
        "1000,A,CLOSE",     # used 100 on Mon (900..1000)
        "1980,A,REOPEN",    # Tue 09:00: needs 140 more mins to reach 240 (1980 + 140 = 2120)
        "2200,A,CLOSE",     # runs until 2200. Breaches at 2121!
    ]
    res = solution.compute_sla(stream)
    expected = [
        {"ticket_id": "A", "priority": "P1", "used_minutes": 320, "breached": True, "breached_at": 2121, "status": "closed"}
    ]
    assert_equal(res, expected, "Second breach mismatch")


# ---------------------------------------------------------------------------
# 5. Calendar, Weekends, Non-Business Hours, and Holidays
# ---------------------------------------------------------------------------
def test_calendar_weekend_and_night_hours():
    # Open on Friday 16:30 (Day 4: 4*1440 + 990 = 6750).
    # Runs until Monday 09:30 (Day 7: 7*1440 + 570 = 10650).
    # Friday business: 6780 - 6750 = 30 mins.
    # Weekend: 0 mins.
    # Monday business: 10650 - 10620 = 30 mins.
    # Total = 60 mins.
    stream = [
        "6750,A,OPEN,P1",
        "10650,A,CLOSE",
    ]
    res = solution.compute_sla(stream)
    assert_equal(res, [{"ticket_id": "A", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}])


def test_holiday_declarations():
    # Holiday declared on weekend has NO effect on business hours
    # Holiday on Wednesday (Day 2) wipes Wednesday business hours
    # Duplicate holiday lines handled cleanly
    # Multi-week span
    # Week 0: Mon=480, Tue=480, Wed(Holiday)=0, Thu=480, Fri=120 (paused at 11:00 = 6420)
    # Day 0 Mon: 600..1020 = 420 mins
    # Day 1 Tue: 480 mins
    # Day 2 Wed: HOLIDAY = 0 mins
    # Day 3 Thu: 480 mins
    # Day 4 Fri: 6300..6420 = 120 mins
    # Total used = 420 + 480 + 0 + 480 + 120 = 1500 mins.
    # Limit P3 is 1440. Breaches on Friday at 6300 + (1440 - 1380) + 1 = 6361!
    stream = [
        "600,W,OPEN,P3",
        "3420,*,HOLIDAY",   # Wed Day 2
        "3500,*,HOLIDAY",   # duplicate
        "8000,*,HOLIDAY",   # weekend Day 5 (Saturday) holiday
        "6420,W,PAUSE",
    ]
    res = solution.compute_sla(stream)
    expected = [
        {"ticket_id": "W", "priority": "P3", "used_minutes": 1500, "breached": True, "breached_at": 6361, "status": "paused"}
    ]
    assert_equal(res, expected, "Multi-day holiday mismatch")


def test_holiday_does_not_affect_now():
    # Holiday at minute 999999 must NOT push 'now' to 999999
    stream = [
        "540,A,OPEN,P1",
        "600,A,CLOSE",
        "999999,*,HOLIDAY",
    ]
    res = solution.compute_sla(stream)
    expected = [
        {"ticket_id": "A", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
    ]
    assert_equal(res, expected, "Holiday affecting now")


# ---------------------------------------------------------------------------
# 6. Definition of "Now", Ties and Out-of-Order Events
# ---------------------------------------------------------------------------
def test_now_driven_by_invalid_transition_on_another_ticket():
    # Ticket A opens at 540 P1. Ticket B has an invalid transition at 900.
    # 'now' becomes 900. Ticket A runs continuously until 900!
    # Ticket B never had a valid OPEN, so it does not appear in output.
    stream = [
        "540,A,OPEN,P1",
        "900,B,PAUSE",
    ]
    res = solution.compute_sla(stream)
    expected = [
        {"ticket_id": "A", "priority": "P1", "used_minutes": 360, "breached": True, "breached_at": 781, "status": "running"}
    ]
    assert_equal(res, expected, "Now driven by invalid transition mismatch")


def test_now_with_only_invalid_or_holiday_or_empty():
    assert_equal(solution.compute_sla([]), [])
    assert_equal(solution.compute_sla([""]), [])
    assert_equal(solution.compute_sla(["   "]), [])
    assert_equal(solution.compute_sla(["540,*,HOLIDAY"]), [])
    assert_equal(solution.compute_sla(["540,A,PAUSE"]), [])  # invalid transition, never opened -> []
    assert_equal(solution.compute_sla(["540,A,CLOSE"]), [])
    assert_equal(solution.compute_sla(["540,A,RESUME"]), [])
    assert_equal(solution.compute_sla(["540,A,REOPEN"]), [])
    assert_equal(solution.compute_sla(["540,A,PRIORITY,P1"]), [])


def test_stable_sorting_ties_at_same_minute():
    # OPEN then PAUSE -> ends in PAUSED, 0 business minutes at 540
    stream_open_pause = ["540,T,OPEN,P1", "540,T,PAUSE", "600,X,PAUSE"]
    res1 = solution.compute_sla(stream_open_pause)
    assert_equal(res1, [{"ticket_id": "T", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "paused"}])

    # PAUSE then OPEN -> PAUSE ignored on NOT_OPENED, ends in RUNNING, 60 business minutes
    stream_pause_open = ["540,T,PAUSE", "540,T,OPEN,P1", "600,X,PAUSE"]
    res2 = solution.compute_sla(stream_pause_open)
    assert_equal(res2, [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "running"}])

    # CLOSE then OPEN at minute 600: OPEN from CLOSED resets used to 0
    stream_close_open = [
        "540,T,OPEN,P1",
        "600,T,CLOSE",
        "600,T,OPEN,P2",
        "660,T,CLOSE",
    ]
    res3 = solution.compute_sla(stream_close_open)
    assert_equal(res3, [{"ticket_id": "T", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}])

    # OPEN then CLOSE at minute 600: OPEN ignored on RUNNING, CLOSE makes it CLOSED, used 60
    stream_open_close = [
        "540,T,OPEN,P1",
        "600,T,OPEN,P2",
        "600,T,CLOSE",
        "660,T,CLOSE",
    ]
    res4 = solution.compute_sla(stream_open_close)
    assert_equal(res4, [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}])


def test_completely_out_of_order_stream():
    # Stream in reverse / shuffled order
    stream = [
        "900,C,CLOSE",
        "5,*,HOLIDAY",
        "600,A,CLOSE",
        "540,C,OPEN,P1",
        "540,A,OPEN,P2",
    ]
    res = solution.compute_sla(stream)
    # Day 0 is HOLIDAY! So both tickets run on Day 0 which has 0 business minutes!
    # A runs 540..600 on Mon (holiday) -> 0 mins
    # C runs 540..900 on Mon (holiday) -> 0 mins
    expected = [
        {"ticket_id": "A", "priority": "P2", "used_minutes": 0, "breached": False, "breached_at": None, "status": "closed"},
        {"ticket_id": "C", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "closed"},
    ]
    assert_equal(res, expected, "Shuffled stream mismatch")


# ---------------------------------------------------------------------------
# 7. Malformed Lines (Must Be Completely Ignored)
# ---------------------------------------------------------------------------
def test_malformed_lines_adversarial():
    stream = [
        # Valid ticket event
        "540,T1,OPEN,P1",
        # Various malformed lines that must be ignored
        "",
        "   ",
        "\t\r\n",
        "540",
        "540,T1",
        "540,T1,OPEN",                  # OPEN needs 4 fields
        "540,T1,OPEN,P1,EXTRA",          # OPEN has 5 fields
        "540,T1,PRIORITY",              # PRIORITY needs 4 fields
        "540,T1,PRIORITY,P1,EXTRA",      # PRIORITY has 5 fields
        "540,T1,PAUSE,EXTRA",           # PAUSE needs 3 fields
        "540,T1,RESUME,P1",             # RESUME needs 3 fields
        "540,T1,CLOSE,EXTRA",           # CLOSE needs 3 fields
        "540,T1,REOPEN,EXTRA",          # REOPEN needs 3 fields
        "540,*,HOLIDAY,EXTRA",          # HOLIDAY needs 3 fields
        "540,T1,HOLIDAY",               # HOLIDAY with ticket ID != *
        "540,*,OPEN,P1",                # Non-HOLIDAY with ticket ID *
        "540,*,PAUSE",                  # Non-HOLIDAY with ticket ID *
        "-540,T1,OPEN,P1",              # Negative minute
        "+540,T1,OPEN,P1",              # Plus sign
        "540.0,T1,OPEN,P1",             # Float minute
        "54a,T1,OPEN,P1",               # Letters in minute
        ",T1,OPEN,P1",                  # Empty minute
        "540,,OPEN,P1",                 # Empty ticket ID
        "540,   ,OPEN,P1",              # Whitespace ticket ID
        "540,T1,open,P1",               # Lowercase event
        "540,T1,INVALID,P1",            # Invalid event
        "540,T1,OPEN,p1",               # Lowercase priority
        "540,T1,OPEN,P0",               # Invalid priority
        "540,T1,OPEN,P5",               # Invalid priority
        "540,T1,OPEN,HIGH",             # Invalid priority
        "١٢٣,T1,OPEN,P1",               # Non-ASCII digits
        "999999999,T1,BAD_EVENT",       # Malformed huge minute must not affect 'now'
        # Valid ticket event
        "600,T1,CLOSE",
    ]
    res = solution.compute_sla(stream)
    expected = [
        {"ticket_id": "T1", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
    ]
    assert_equal(res, expected, "Malformed line pollution detected")


def test_whitespace_and_leading_zeros_handling():
    # Leading zeros in minute are VALID
    # Surrounding whitespace around fields is VALID
    # Internal whitespace in ticket ID is VALID
    stream = [
        "  00540  ,  My Ticket  ,  OPEN  ,  P1  ",
        "\t00600\t,\tMy Ticket\t,\tCLOSE\t",
    ]
    res = solution.compute_sla(stream)
    expected = [
        {"ticket_id": "My Ticket", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
    ]
    assert_equal(res, expected, "Whitespace / leading zero handling mismatch")


# ---------------------------------------------------------------------------
# 8. Output Ordering and Generator Input
# ---------------------------------------------------------------------------
def test_output_sorting_code_point_order():
    # Must sort by ticket_id code-point order: "10" < "2" < "A" < "T1" < "T10" < "T2" < "a" < "t1"
    ids = ["t1", "T1", "T10", "T2", "10", "2", "a", "A"]
    stream = []
    for tid in ids:
        stream.append(f"540,{tid},OPEN,P2")
        stream.append(f"600,{tid},CLOSE")

    res = solution.compute_sla(stream)
    actual_ids = [t["ticket_id"] for t in res]
    expected_ids = sorted(ids)
    assert_equal(actual_ids, expected_ids, "Ticket ID sorting mismatch")


def test_generator_input():
    def stream_gen():
        yield "540,A,OPEN,P1"
        yield "600,A,CLOSE"

    res = solution.compute_sla(stream_gen())
    assert type(res) is list
    assert_equal(len(res), 1)


# ---------------------------------------------------------------------------
# 9. Performance & Large Minutes (Anti-O(Minute) Check)
# ---------------------------------------------------------------------------
def test_large_minute_numbers_fast():
    # Day 100,001 (Monday 09:00 = 100001 * 1440 + 540 = 144001980)
    # Minute values up to 1,000,000,000. Naive minute-by-minute loop will freeze.
    m_start = 144001980
    m_end = m_start + 60
    stream = [
        f"{m_start},FAST,OPEN,P1",
        f"{m_end},FAST,CLOSE",
    ]
    t0 = time.perf_counter()
    res = solution.compute_sla(stream)
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, f"Solution took too long ({elapsed:.2f}s); likely looping minute-by-minute"
    expected = [
        {"ticket_id": "FAST", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
    ]
    assert_equal(res, expected, "Large minute computation mismatch")


def test_moderate_sized_adversarial_stream():
    # 5000 lines alternating events across 50 tickets
    stream = []
    for i in range(50):
        tid = f"T_{i:03d}"
        stream.append(f"{540 + i},*,HOLIDAY" if i % 10 == 0 else f"{540 + i},{tid},OPEN,P1")
        stream.append(f"{600 + i},{tid},PAUSE")
        stream.append(f"{700 + i},{tid},RESUME")
        stream.append(f"{800 + i},{tid},CLOSE")

    t0 = time.perf_counter()
    res = solution.compute_sla(stream)
    elapsed = time.perf_counter() - t0
    assert elapsed < 2.0, f"Bulk stream took too long: {elapsed:.2f}s"
    assert isinstance(res, list)


# ---------------------------------------------------------------------------
# Main Execution
# ---------------------------------------------------------------------------
def main():
    print("=" * 60)
    print("Running Adversarial QA Test Suite for compute_sla")
    print("=" * 60)

    tests = [
        ("Spec Example 1", test_spec_example_1),
        ("Spec Example 2", test_spec_example_2),
        ("Spec Example 3", test_spec_example_3),
        ("Spec Example 4", test_spec_example_4),
        ("State Table: Cells 1-6 (NOT_OPENED)", test_state_table_cell_1_to_6_not_opened),
        ("State Table: Cells 7-12 (RUNNING)", test_state_table_running_cells_7_to_12),
        ("State Table: Cells 13-18 (PAUSED)", test_state_table_paused_cells_13_to_18),
        ("State Table: Cells 19-24 (CLOSED)", test_state_table_closed_cells_19_to_24),
        ("Exact SLA Boundaries across P1-P4", test_exact_sla_boundaries),
        ("Priority change preventing breach", test_priority_change_preventing_breach),
        ("Priority change causing immediate breach while paused", test_priority_change_causing_immediate_breach_while_paused),
        ("Priority change outside business hours", test_priority_change_outside_business_hours),
        ("Breach stickiness after priority raise", test_breach_stickiness_after_priority_raise),
        ("Multiple priority changes at same minute", test_multiple_priority_changes_at_same_minute),
        ("Reopen and second breach", test_reopen_and_second_breach),
        ("Calendar weekend and night hours", test_calendar_weekend_and_night_hours),
        ("Holiday declarations and duplicates", test_holiday_declarations),
        ("Holiday does not affect 'now'", test_holiday_does_not_affect_now),
        ("Now driven by invalid transition on another ticket", test_now_driven_by_invalid_transition_on_another_ticket),
        ("Now with only invalid, holiday, or empty stream", test_now_with_only_invalid_or_holiday_or_empty),
        ("Stable sorting ties at same minute", test_stable_sorting_ties_at_same_minute),
        ("Completely out of order stream", test_completely_out_of_order_stream),
        ("Adversarial malformed lines", test_malformed_lines_adversarial),
        ("Whitespace and leading zeros handling", test_whitespace_and_leading_zeros_handling),
        ("Output sorting code-point order", test_output_sorting_code_point_order),
        ("Generator input compatibility", test_generator_input),
        ("Large minute numbers (anti-O(minute) check)", test_large_minute_numbers_fast),
        ("Moderate sized stream performance", test_moderate_sized_adversarial_stream),
    ]

    for name, func in tests:
        run_test(name, func)

    print("=" * 60)
    print(f"Summary: {passed_count} passed, {failed_count} failed out of {len(tests)} tests.")
    print("=" * 60)

    if failed_count > 0:
        print("\nFailures:")
        for name, msg in failures:
            print(f"- {name}: {msg}")
        sys.exit(1)
    else:
        print("\nAll tests passed successfully.")
        sys.exit(0)


if __name__ == "__main__":
    main()