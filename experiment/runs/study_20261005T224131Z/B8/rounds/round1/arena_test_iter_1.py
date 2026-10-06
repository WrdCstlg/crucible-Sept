import sys
import traceback
import solution

total_tests = 0
passed_tests = 0
failed_tests = 0


def check_result(test_name, stream, expected):
    global total_tests, passed_tests, failed_tests
    total_tests += 1
    try:
        actual = solution.compute_sla(stream)
    except Exception as e:
        print(f"FAIL: {test_name} raised exception: {e}")
        traceback.print_exc()
        failed_tests += 1
        return False

    if type(actual) is not list:
        print(f"FAIL: {test_name}: return value type is {type(actual)}, expected list")
        failed_tests += 1
        return False

    for i, item in enumerate(actual):
        if type(item) is not dict:
            print(f"FAIL: {test_name}: item {i} type is {type(item)}, expected dict")
            failed_tests += 1
            return False
        expected_keys = {"ticket_id", "priority", "used_minutes", "breached", "breached_at", "status"}
        if set(item.keys()) != expected_keys:
            print(f"FAIL: {test_name}: item {i} keys {set(item.keys())} != {expected_keys}")
            failed_tests += 1
            return False
        if type(item["ticket_id"]) is not str:
            print(f"FAIL: {test_name}: item {i} ticket_id is {type(item['ticket_id'])}, expected str")
            failed_tests += 1
            return False
        if type(item["priority"]) is not str or item["priority"] not in {"P1", "P2", "P3", "P4"}:
            print(f"FAIL: {test_name}: item {i} priority invalid: {item.get('priority')}")
            failed_tests += 1
            return False
        if type(item["used_minutes"]) is not int or isinstance(item["used_minutes"], bool):
            print(f"FAIL: {test_name}: item {i} used_minutes is {type(item['used_minutes'])}, expected int")
            failed_tests += 1
            return False
        if type(item["breached"]) is not bool:
            print(f"FAIL: {test_name}: item {i} breached is {type(item['breached'])}, expected bool")
            failed_tests += 1
            return False
        if item["breached"] is False and item["breached_at"] is not None:
            print(f"FAIL: {test_name}: item {i} breached is False but breached_at is {item['breached_at']}")
            failed_tests += 1
            return False
        if item["breached"] is True and (type(item["breached_at"]) is not int or isinstance(item["breached_at"], bool)):
            print(f"FAIL: {test_name}: item {i} breached is True but breached_at is {item['breached_at']}")
            failed_tests += 1
            return False
        if item["status"] not in {"running", "paused", "closed"}:
            print(f"FAIL: {test_name}: item {i} status invalid: {item.get('status')}")
            failed_tests += 1
            return False

    if actual != expected:
        print(f"FAIL: {test_name}")
        print(f"  Input:    {stream}")
        print(f"  Expected: {expected}")
        print(f"  Actual:   {actual}")
        failed_tests += 1
        return False

    passed_tests += 1
    return True


# ==============================================================================
# 1. SPECIFICATION EXAMPLES
# ==============================================================================

def test_specification_examples():
    # Example 1
    s1 = [
        "540,A,OPEN,P2",
        "600,A,CLOSE",
    ]
    e1 = [{"ticket_id": "A", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Spec Example 1", s1, e1)

    # Example 2
    s2 = [
        "6720,B,OPEN,P1",
        "10680,B,PAUSE",
    ]
    e2 = [{"ticket_id": "B", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "paused"}]
    check_result("Spec Example 2", s2, e2)

    # Example 3
    s3 = [
        "540,C,OPEN,P1",
        "900,C,CLOSE",
    ]
    e3 = [{"ticket_id": "C", "priority": "P1", "used_minutes": 360, "breached": True, "breached_at": 781, "status": "closed"}]
    check_result("Spec Example 3", s3, e3)

    # Example 4
    s4 = [
        "540,D,OPEN,P3",
        "2040,D,PAUSE",
        "open,D,RESUME",
        "2100,D,RESUME,P1",
        "5,*,HOLIDAY",
    ]
    e4 = [{"ticket_id": "D", "priority": "P3", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}]
    check_result("Spec Example 4", s4, e4)


# ==============================================================================
# 2. DEFINITION OF "NOW" AND EMPTY STREAMS
# ==============================================================================

def test_definition_of_now_and_empty():
    # Empty stream
    check_result("Empty stream", [], [])

    # Stream with only empty or malformed lines
    check_result("Only malformed lines", [
        "",
        "   ",
        "invalid line",
        "100",
        "100,A",
        "-50,A,OPEN,P1",
        "540,A,OPEN,P9",
    ], [])

    # Stream with only HOLIDAY lines: no ticket events, must return []
    check_result("Only holidays", [
        "0,*,HOLIDAY",
        "1440,*,HOLIDAY",
        "2880,*,HOLIDAY",
    ], [])

    # Stream with only ignored transitions on tickets never opened:
    # All are well-formed ticket events, but none had a valid OPEN -> []
    check_result("Only invalid transitions on un-opened tickets", [
        "540,T1,PAUSE",
        "600,T2,CLOSE",
        "700,T3,RESUME",
        "800,T4,REOPEN",
        "900,T5,PRIORITY,P1",
    ], [])

    # Ignored ticket event determines "now" for valid tickets!
    # T1 opened at 540 P1, closed at 600.
    # T2 sends PAUSE at 1000 while NOT_OPENED. T2 ignored, but now is 1000!
    # T1 is closed, so its used time remains 60, status closed. T2 not in output.
    s = [
        "540,T1,OPEN,P1",
        "600,T1,CLOSE",
        "1000,T2,PAUSE",
    ]
    e = [{"ticket_id": "T1", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Ignored event sets now for valid closed ticket", s, e)

    # Ignored ticket event sets "now" while valid ticket is RUNNING
    # T1 opened at 540 P1, runs to 700. T2 sends CLOSE at 700 while NOT_OPENED.
    # Now is 700. T1 used minutes: 700 - 540 = 160. Limit is 240. Status running.
    s = [
        "540,T1,OPEN,P1",
        "700,T2,CLOSE",
    ]
    e = [{"ticket_id": "T1", "priority": "P1", "used_minutes": 160, "breached": False, "breached_at": None, "status": "running"}]
    check_result("Ignored event sets now for running ticket", s, e)

    # HOLIDAY line at minute 999999 must NOT affect "now"
    s = [
        "540,T1,OPEN,P1",
        "600,T1,CLOSE",
        "999999,*,HOLIDAY",
    ]
    e = [{"ticket_id": "T1", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Holiday does not advance now", s, e)

    # Malformed line at minute 999999 must NOT affect "now"
    s = [
        "540,T1,OPEN,P1",
        "600,T1,CLOSE",
        "999999,T1,INVALID_EVENT",
    ]
    e = [{"ticket_id": "T1", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Malformed line does not advance now", s, e)


# ==============================================================================
# 3. COMPLETE STATE-TRANSITION TABLE (ALL 24 CELLS)
# ==============================================================================

def test_state_transitions():
    # 4 states: NOT_OPENED, RUNNING, PAUSED, CLOSED
    # 6 events: OPEN, PRIORITY, PAUSE, RESUME, CLOSE, REOPEN

    # Cell 1: NOT_OPENED + OPEN -> to RUNNING, priority P, used 0
    s = ["540,T,OPEN,P1"]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "running"}]
    check_result("Cell 1: NOT_OPENED + OPEN", s, e)

    # Cell 2: NOT_OPENED + PRIORITY -> ignored
    check_result("Cell 2: NOT_OPENED + PRIORITY", ["540,T,PRIORITY,P1"], [])

    # Cell 3: NOT_OPENED + PAUSE -> ignored
    check_result("Cell 3: NOT_OPENED + PAUSE", ["540,T,PAUSE"], [])

    # Cell 4: NOT_OPENED + RESUME -> ignored
    check_result("Cell 4: NOT_OPENED + RESUME", ["540,T,RESUME"], [])

    # Cell 5: NOT_OPENED + CLOSE -> ignored
    check_result("Cell 5: NOT_OPENED + CLOSE", ["540,T,CLOSE"], [])

    # Cell 6: NOT_OPENED + REOPEN -> ignored
    check_result("Cell 6: NOT_OPENED + REOPEN", ["540,T,REOPEN"], [])

    # Cell 7: RUNNING + OPEN -> ignored (priority keeps P1, used not reset, stays RUNNING)
    s = [
        "540,T,OPEN,P1",
        "600,T,OPEN,P2",
        "660,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 7: RUNNING + OPEN", s, e)

    # Cell 8: RUNNING + PRIORITY -> priority becomes P
    s = [
        "540,T,OPEN,P1",
        "600,T,PRIORITY,P2",
        "660,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P2", "used_minutes": 120, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 8: RUNNING + PRIORITY", s, e)

    # Cell 9: RUNNING + PAUSE -> to PAUSED
    s = [
        "540,T,OPEN,P1",
        "600,T,PAUSE",
        "660,OTHER,OPEN,P1",
        "660,OTHER,CLOSE",
    ]
    e = [
        {"ticket_id": "OTHER", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "closed"},
        {"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"},
    ]
    check_result("Cell 9: RUNNING + PAUSE", s, e)

    # Cell 10: RUNNING + RESUME -> ignored (stays RUNNING)
    s = [
        "540,T,OPEN,P1",
        "600,T,RESUME",
        "660,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 10: RUNNING + RESUME", s, e)

    # Cell 11: RUNNING + CLOSE -> to CLOSED
    s = [
        "540,T,OPEN,P1",
        "600,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 11: RUNNING + CLOSE", s, e)

    # Cell 12: RUNNING + REOPEN -> ignored (stays RUNNING)
    s = [
        "540,T,OPEN,P1",
        "600,T,REOPEN",
        "660,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 12: RUNNING + REOPEN", s, e)

    # Cell 13: PAUSED + OPEN -> ignored (stays PAUSED, priority stays P1)
    s = [
        "540,T,OPEN,P1",
        "570,T,PAUSE",
        "600,T,OPEN,P3",
        "660,T,RESUME",
        "700,T,CLOSE",
    ]
    # Running 540..570 (30m), paused 570..660 (0m), running 660..700 (40m) = 70m
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 70, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 13: PAUSED + OPEN", s, e)

    # Cell 14: PAUSED + PRIORITY -> priority becomes P
    s = [
        "540,T,OPEN,P1",
        "570,T,PAUSE",
        "600,T,PRIORITY,P3",
        "660,T,RESUME",
        "700,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P3", "used_minutes": 70, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 14: PAUSED + PRIORITY", s, e)

    # Cell 15: PAUSED + PAUSE -> ignored
    s = [
        "540,T,OPEN,P1",
        "570,T,PAUSE",
        "600,T,PAUSE",
        "660,T,RESUME",
        "700,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 70, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 15: PAUSED + PAUSE", s, e)

    # Cell 16: PAUSED + RESUME -> to RUNNING
    s = [
        "540,T,OPEN,P1",
        "570,T,PAUSE",
        "600,T,RESUME",
        "660,T,CLOSE",
    ]
    # Running 540..570 (30m), paused 570..600 (0m), running 600..660 (60m) = 90m
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 90, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 16: PAUSED + RESUME", s, e)

    # Cell 17: PAUSED + CLOSE -> to CLOSED
    s = [
        "540,T,OPEN,P1",
        "570,T,PAUSE",
        "600,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 30, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 17: PAUSED + CLOSE", s, e)

    # Cell 18: PAUSED + REOPEN -> ignored (stays PAUSED)
    s = [
        "540,T,OPEN,P1",
        "570,T,PAUSE",
        "600,T,REOPEN",
        "660,T,RESUME",
        "700,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 70, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 18: PAUSED + REOPEN", s, e)

    # Cell 19: CLOSED + OPEN -> to RUNNING, priority P, used resets to 0, breach cleared
    s = [
        "540,T,OPEN,P1",
        "600,T,CLOSE",
        "660,T,OPEN,P2",
        "700,T,CLOSE",
    ]
    # Running 660..700 (40m), reset used
    e = [{"ticket_id": "T", "priority": "P2", "used_minutes": 40, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 19: CLOSED + OPEN", s, e)

    # Cell 20: CLOSED + PRIORITY -> ignored
    s = [
        "540,T,OPEN,P1",
        "600,T,CLOSE",
        "630,T,PRIORITY,P2",
        "660,T,REOPEN",
        "700,T,CLOSE",
    ]
    # Priority stays P1; running 540..600 (60m) + 660..700 (40m) = 100m
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 100, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 20: CLOSED + PRIORITY", s, e)

    # Cell 21: CLOSED + PAUSE -> ignored
    s = [
        "540,T,OPEN,P1",
        "600,T,CLOSE",
        "630,T,PAUSE",
        "660,T,REOPEN",
        "700,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 100, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 21: CLOSED + PAUSE", s, e)

    # Cell 22: CLOSED + RESUME -> ignored
    s = [
        "540,T,OPEN,P1",
        "600,T,CLOSE",
        "630,T,RESUME",
        "660,T,REOPEN",
        "700,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 100, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 22: CLOSED + RESUME", s, e)

    # Cell 23: CLOSED + CLOSE -> ignored
    s = [
        "540,T,OPEN,P1",
        "600,T,CLOSE",
        "630,T,CLOSE",
        "660,T,REOPEN",
        "700,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 100, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 23: CLOSED + CLOSE", s, e)

    # Cell 24: CLOSED + REOPEN -> to RUNNING, used continues, breach kept, priority kept
    s = [
        "540,T,OPEN,P1",
        "600,T,CLOSE",
        "660,T,REOPEN",
        "700,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 100, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Cell 24: CLOSED + REOPEN", s, e)


# ==============================================================================
# 4. EXACT SLA BOUNDARIES, PRIORITIES, AND STICKY/CLEARED BREACHES
# ==============================================================================

def test_sla_boundaries_and_breaches():
    # Priority limits: P1=240, P2=480, P3=1440, P4=2400

    # Boundary 1: P1 used exactly 240 -> NOT breached
    s = [
        "540,T,OPEN,P1",
        "780,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 240, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Boundary P1: exactly 240 min", s, e)

    # Boundary 2: P1 used 241 -> breached at 781
    s = [
        "540,T,OPEN,P1",
        "781,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "closed"}]
    check_result("Boundary P1: exactly 241 min breaches at 781", s, e)

    # Boundary 3: P2 limit 480. Day 0 has 480 business minutes (540 to 1020).
    # At 1020, used = 480 -> NOT breached!
    # Tuesday 09:00 is minute 1980. At 1980, used = 480 (night minutes don't count).
    # At 1981, used = 481 -> breached at 1981!
    s = [
        "540,T,OPEN,P2",
        "1980,T,PAUSE",
    ]
    e = [{"ticket_id": "T", "priority": "P2", "used_minutes": 480, "breached": False, "breached_at": None, "status": "paused"}]
    check_result("Boundary P2: used 480 after overnight gap not breached", s, e)

    s = [
        "540,T,OPEN,P2",
        "1981,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P2", "used_minutes": 481, "breached": True, "breached_at": 1981, "status": "closed"}]
    check_result("Boundary P2: used 481 breaches next morning at 1981", s, e)

    # Boundary 4: P3 limit 1440 (3 full business days).
    # Day 0 Mon (480), Day 1 Tue (480), Day 2 Wed (480) -> 1440 min at Wed 17:00 (3900).
    # Thursday 09:00 is minute 4860. At 4860, used is 1440 -> not breached.
    # At 4861, used is 1441 -> breached at 4861!
    s = [
        "540,T,OPEN,P3",
        "4860,T,PAUSE",
    ]
    e = [{"ticket_id": "T", "priority": "P3", "used_minutes": 1440, "breached": False, "breached_at": None, "status": "paused"}]
    check_result("Boundary P3: used 1440 after 3 business days not breached", s, e)

    s = [
        "540,T,OPEN,P3",
        "4861,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P3", "used_minutes": 1441, "breached": True, "breached_at": 4861, "status": "closed"}]
    check_result("Boundary P3: used 1441 breaches Thursday morning at 4861", s, e)

    # Boundary 5: P4 limit 2400 (5 full business days: Mon-Fri).
    # Friday 17:00 is minute 6780 (used = 2400).
    # Weekend passes: Saturday (day 5), Sunday (day 6).
    # Next Monday (day 7) 09:00 is minute 10620 (used = 2400).
    # At 10621, used = 2401 -> breached at 10621!
    s = [
        "540,T,OPEN,P4",
        "10620,T,PAUSE",
    ]
    e = [{"ticket_id": "T", "priority": "P4", "used_minutes": 2400, "breached": False, "breached_at": None, "status": "paused"}]
    check_result("Boundary P4: used 2400 across weekend not breached", s, e)

    s = [
        "540,T,OPEN,P4",
        "10621,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P4", "used_minutes": 2401, "breached": True, "breached_at": 10621, "status": "closed"}]
    check_result("Boundary P4: used 2401 breaches next Monday morning at 10621", s, e)

    # Sticky breach: raising priority after breach does NOT un-breach
    s = [
        "540,T,OPEN,P1",
        "800,T,PRIORITY,P4",
        "850,T,CLOSE",
    ]
    # Breached at 781 (P1 limit 240). Raised to P4 at 800.
    # Breach remains True, breached_at remains 781!
    e = [{"ticket_id": "T", "priority": "P4", "used_minutes": 310, "breached": True, "breached_at": 781, "status": "closed"}]
    check_result("Sticky breach: PRIORITY raise does not clear breach", s, e)

    # Sticky breach kept across CLOSE and REOPEN
    s = [
        "540,T,OPEN,P1",
        "800,T,CLOSE",
        "850,T,REOPEN",
        "900,T,CLOSE",
    ]
    # Running 540..800 (260m) + 850..900 (50m) = 310m. Breached at 781.
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 310, "breached": True, "breached_at": 781, "status": "closed"}]
    check_result("Sticky breach kept across REOPEN", s, e)

    # Breach cleared ONLY on valid OPEN from CLOSED
    s = [
        "540,T,OPEN,P1",
        "800,T,CLOSE",
        "850,T,OPEN,P1",
        "900,T,CLOSE",
    ]
    # Running 850..900 (50m). Breach cleared!
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 50, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Breach cleared on OPEN from CLOSED", s, e)

    # Breach cleared on OPEN from CLOSED, and breaches again later!
    s = [
        "540,T,OPEN,P1",
        "800,T,CLOSE",
        "850,T,OPEN,P1",
        "2100,T,CLOSE",
    ]
    # Second run: opens Monday 850.
    # Monday business minutes left: 850 to 1020 = 170m (used = 170).
    # Tuesday 09:00 is 1980. Needs 70 more min to reach 240: 1980 + 70 = 2050 (used = 240).
    # At 2051, used = 241 -> breaches AGAIN at 2051!
    # Tuesday running to 2100: 170 + 120 = 290m used.
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 290, "breached": True, "breached_at": 2051, "status": "closed"}]
    check_result("Breach re-occurs after being cleared", s, e)


# ==============================================================================
# 5. TIES AND SAME-MINUTE PRECEDENCE
# ==============================================================================

def test_ties_and_precedence():
    # Tie 1: PRIORITY raise at minute 781 prevents breach!
    # 540 OPEN P1. At 781, used reaches 241. At 781, PRIORITY P2 arrives.
    # Priority becomes P2 (limit 480) before minute 781 is evaluated -> NO breach!
    s = [
        "540,T,OPEN,P1",
        "781,T,PRIORITY,P2",
        "800,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P2", "used_minutes": 260, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Tie: PRIORITY raise at exact breach minute prevents breach", s, e)

    # Tie 2: PRIORITY raise after breach minute (at 782) does NOT prevent breach
    s = [
        "540,T,OPEN,P1",
        "782,T,PRIORITY,P2",
        "800,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P2", "used_minutes": 260, "breached": True, "breached_at": 781, "status": "closed"}]
    check_result("Tie: PRIORITY raise 1 minute late fails to prevent breach", s, e)

    # Tie 3: Multiple priority changes at minute 781: P2 then P1 in stream order
    # P1 arrives last at 781, so priority at 781 is P1 -> breaches at 781!
    s = [
        "540,T,OPEN,P1",
        "781,T,PRIORITY,P2",
        "781,T,PRIORITY,P1",
        "800,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 260, "breached": True, "breached_at": 781, "status": "closed"}]
    check_result("Tie: Multiple priority events at same minute preserves stream order", s, e)

    # Tie 4: Multiple events at minute 540 in stream order: OPEN -> PAUSE
    s = [
        "540,T,OPEN,P1",
        "540,T,PAUSE",
        "600,OTHER,OPEN,P1",
        "600,OTHER,CLOSE",
    ]
    # T was paused at 540, so used time at 600 is 0!
    e = [
        {"ticket_id": "OTHER", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "closed"},
        {"ticket_id": "T", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "paused"},
    ]
    check_result("Tie: OPEN then PAUSE at same minute", s, e)

    # Tie 5: PAUSE then OPEN from NOT_OPENED: PAUSE ignored, OPEN applies!
    s = [
        "540,T,PAUSE",
        "540,T,OPEN,P1",
        "600,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Tie: PAUSE ignored then OPEN valid at same minute", s, e)

    # Tie 6: PRIORITY drop causes breach immediately while PAUSED
    # Open P2 (limit 480). Runs 540..800 (260m). At 800: PAUSE.
    # At 850: PRIORITY P1 (limit 240). Used is 260 > 240! Breaches at 850 while paused!
    s = [
        "540,T,OPEN,P2",
        "800,T,PAUSE",
        "850,T,PRIORITY,P1",
        "900,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 260, "breached": True, "breached_at": 850, "status": "closed"}]
    check_result("Tie: PRIORITY drop causes immediate breach while PAUSED", s, e)

    # Tie 7: PRIORITY drop causes breach immediately while RUNNING
    s = [
        "540,T,OPEN,P2",
        "800,T,PRIORITY,P1",
        "850,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 310, "breached": True, "breached_at": 800, "status": "closed"}]
    check_result("Tie: PRIORITY drop causes immediate breach while RUNNING", s, e)

    # Tie 8: PRIORITY drop while CLOSED is ignored, so no breach occurs
    s = [
        "540,T,OPEN,P2",
        "800,T,CLOSE",
        "850,T,PRIORITY,P1",
        "900,OTHER,OPEN,P1",
        "900,OTHER,CLOSE",
    ]
    # T is closed, PRIORITY P1 is ignored, priority remains P2, no breach!
    e = [
        {"ticket_id": "OTHER", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "closed"},
        {"ticket_id": "T", "priority": "P2", "used_minutes": 260, "breached": False, "breached_at": None, "status": "closed"},
    ]
    check_result("Tie: PRIORITY drop while CLOSED is ignored", s, e)


# ==============================================================================
# 6. CALENDAR: BUSINESS HOURS, WEEKENDS, HOLIDAYS
# ==============================================================================

def test_calendar_and_holidays():
    # 1. Non-business hour event: opened at night (minute 100 = Monday 01:40)
    # Business hours don't start until 540. Closes at 600. Used time = 60m.
    s = [
        "100,T,OPEN,P1",
        "600,T,CLOSE",
    ]
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Calendar: Opened during non-business hours", s, e)

    # 2. Weekend span: Friday 16:00 (6720) to Monday 12:01 (10801)
    # Friday business minutes: [6720, 6780) = 60m.
    # Weekend = 0m.
    # Monday business starts at 10620. 180m to reach 240: 10620 + 180 = 10800.
    # At 10801, used = 241 -> breaches at 10801!
    s = [
        "6720,T,OPEN,P1",
        "10900,T,CLOSE",
    ]
    # Used at 10900: 60 (Fri) + 280 (Mon 10620..10900) = 340m.
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 340, "breached": True, "breached_at": 10801, "status": "closed"}]
    check_result("Calendar: Weekend gap calculation and breach time", s, e)

    # 3. Breach crossing over end of day: opened Friday 13:00 (6540) P1
    # 13:00 to 17:00 (6780) is 240 business minutes.
    # Over weekend and Monday morning before 09:00: used remains 240.
    # The 241st business minute is Monday 09:00 (minute 10620).
    # Breach occurs at minute 10621!
    s = [
        "6540,T,OPEN,P1",
        "10700,T,CLOSE",
    ]
    # Friday 240m + Monday (10620..10700) 80m = 320m.
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 320, "breached": True, "breached_at": 10621, "status": "closed"}]
    check_result("Calendar: Breach occurs at 09:01 on Monday after Friday 17:00 cutoff", s, e)

    # 4. Monday week 1 is declared a holiday!
    # Same as above, but Monday (day 7 = minute 10080) is a holiday.
    # Tuesday 09:00 is minute 12060. Breach occurs at 12061!
    s = [
        "6540,T,OPEN,P1",
        "12100,T,CLOSE",
        "10080,*,HOLIDAY",
    ]
    # Used: 240 (Fri) + 0 (Mon holiday) + 40 (Tue 12060..12100) = 280m.
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 280, "breached": True, "breached_at": 12061, "status": "closed"}]
    check_result("Calendar: Holiday shifts breach minute to Tuesday morning", s, e)

    # 5. Duplicate holiday declarations
    s = [
        "10500,*,HOLIDAY",
        "6540,T,OPEN,P1",
        "12100,T,CLOSE",
        "10080,*,HOLIDAY",
    ]
    check_result("Calendar: Duplicate holiday lines idempotent", s, e)

    # 6. Entire week holiday: all days declared holiday
    s = [
        "0,*,HOLIDAY",
        "1440,*,HOLIDAY",
        "2880,*,HOLIDAY",
        "4320,*,HOLIDAY",
        "5760,*,HOLIDAY",
        "540,T,OPEN,P1",
        "6780,T,CLOSE",
    ]
    # All 5 weekdays are holidays -> 0 used minutes, no breach!
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Calendar: Full week of holidays results in 0 used minutes", s, e)

    # 7. Exact minute-of-day boundaries [540, 1020)
    # Minute 539 is non-business, 540 is business
    # Minute 1019 is business, 1020 is non-business
    s = [
        "539,T1,OPEN,P1",
        "540,T1,PAUSE",
        "1019,T2,OPEN,P1",
        "1020,T2,PAUSE",
        "1020,T3,OPEN,P1",
        "1021,T3,PAUSE",
    ]
    e = [
        {"ticket_id": "T1", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "paused"},
        {"ticket_id": "T2", "priority": "P1", "used_minutes": 1, "breached": False, "breached_at": None, "status": "paused"},
        {"ticket_id": "T3", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "paused"},
    ]
    check_result("Calendar: Minute-of-day boundary precision", s, e)


# ==============================================================================
# 7. OUT-OF-ORDER EVENTS AND SHUFFLED INPUT
# ==============================================================================

def test_out_of_order_events():
    # Events given in reversed chronological order
    s = [
        "1000,T,CLOSE",
        "900,T,RESUME",
        "800,T,PAUSE",
        "600,T,PRIORITY,P1",
        "540,T,OPEN,P2",
    ]
    # Chronological:
    # 540: OPEN P2
    # 600: PRIORITY P1 (used 60)
    # 781: reaches 241 -> breaches at 781!
    # 800: PAUSE (used 260)
    # 900: RESUME
    # 1000: CLOSE (running 900..1000 = 100m, total used = 360m)
    e = [{"ticket_id": "T", "priority": "P1", "used_minutes": 360, "breached": True, "breached_at": 781, "status": "closed"}]
    check_result("Out of order: reversed event stream", s, e)

    # Shuffled multiple tickets with interleaved events
    s = [
        "600,B,CLOSE",
        "540,A,OPEN,P1",
        "540,B,OPEN,P2",
        "600,A,CLOSE",
    ]
    e = [
        {"ticket_id": "A", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
        {"ticket_id": "B", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
    ]
    check_result("Out of order: interleaved tickets", s, e)


# ==============================================================================
# 8. MALFORMED LINES, WHITESPACE, AND SPECIAL CHARACTERS
# ==============================================================================

def test_malformed_lines():
    malformed = [
        "",                             # empty
        "   \t  \n ",                   # whitespace only
        "540",                          # 1 field
        "540,A",                        # 2 fields
        "540,A,OPEN,P1,EXTRA",          # 5 fields
        "540,A,PAUSE,EXTRA",            # 4 fields for PAUSE
        "540,A,RESUME,P1",              # 4 fields for RESUME
        "540,A,CLOSE,P1",               # 4 fields for CLOSE
        "540,A,REOPEN,P1",              # 4 fields for REOPEN
        "540,*,HOLIDAY,EXTRA",          # 4 fields for HOLIDAY
        "-540,A,OPEN,P1",               # negative minute
        "+540,A,OPEN,P1",               # plus sign minute
        "540.5,A,OPEN,P1",              # float minute
        "540a,A,OPEN,P1",               # non-digit minute
        ",A,OPEN,P1",                   # empty minute
        "540,,OPEN,P1",                 # empty ticket ID
        "540,   ,OPEN,P1",              # whitespace ticket ID
        "540,*,OPEN,P1",                # * ticket ID for non-holiday
        "540,*,PRIORITY,P1",            # * ticket ID for PRIORITY
        "540,*,PAUSE",                  # * ticket ID for PAUSE
        "540,*,CLOSE",                  # * ticket ID for CLOSE
        "540,*,RESUME",                 # * ticket ID for RESUME
        "540,*,REOPEN",                 # * ticket ID for REOPEN
        "540,A,HOLIDAY",                # holiday with non-* ticket ID
        "540,,HOLIDAY",                 # holiday with empty ticket ID
        "540,**,HOLIDAY",               # holiday with ** ticket ID
        "540,A,open,P1",                # lowercase event
        "540,A,Open,P1",                # mixed-case event
        "540,A,pause",                  # lowercase event
        "540,A,UNKNOWN,P1",             # unknown event
        "540,A,OPEN",                   # 3 fields for OPEN
        "540,A,PRIORITY",               # 3 fields for PRIORITY
        "540,A,OPEN,p1",                # lowercase priority
        "540,A,OPEN,P0",                # invalid priority
        "540,A,OPEN,P5",                # invalid priority
        "540,A,OPEN,HIGH",              # invalid priority
        "540,A,PRIORITY,P99",           # invalid priority
        "999999,INVALID,OPEN,P1,X,Y",   # malformed at huge minute
    ]

    valid = [
        "  000540  ,  OK  ,  OPEN  ,  P2  ",
        "  0600  ,  OK  ,  CLOSE  ",
    ]

    stream = malformed + valid
    expected = [{"ticket_id": "OK", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    check_result("Malformed lines thoroughly filtered", stream, expected)


# ==============================================================================
# 9. OUTPUT ORDERING, CODE-POINT SORTING, CASE SENSITIVITY
# ==============================================================================

def test_output_ordering():
    # Default Python code-point order:
    # "T10" < "T2" because '1' < '2'
    # "A" < "T" < "a" < "t"
    s = [
        "540,t1,OPEN,P1",
        "540,T2,OPEN,P1",
        "540,T10,OPEN,P1",
        "540,T1,OPEN,P1",
        "540,a,OPEN,P1",
        "540,A,OPEN,P1",
        "600,A,CLOSE",
        "600,T1,CLOSE",
        "600,T10,CLOSE",
        "600,T2,CLOSE",
        "600,a,CLOSE",
        "600,t1,CLOSE",
    ]
    expected_ids = ["A", "T1", "T10", "T2", "a", "t1"]
    expected = [
        {"ticket_id": tid, "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
        for tid in expected_ids
    ]
    check_result("Output ordering: code-point sort and case sensitivity", s, expected)


# ==============================================================================
# 10. MULTI-WEEK AND LARGE TIMESTAMP PERFORMANCE
# ==============================================================================

def test_multi_week_and_large_timestamps():
    # 1. Ticket running across 3 full weeks
    # Week 0 Mon 09:00 (540) to Week 3 Mon 09:00 (30780).
    # 3 weeks * 2400 business minutes = 7200 used minutes.
    # P4 limit is 2400. Reached at Week 0 Fri 17:00 (6780).
    # 2401st business minute is Week 1 Mon 09:00 (10620).
    # Breached at 10621!
    s = [
        "540,RUNNER,OPEN,P4",
        "30780,RUNNER,CLOSE",
    ]
    e = [{"ticket_id": "RUNNER", "priority": "P4", "used_minutes": 7200, "breached": True, "breached_at": 10621, "status": "closed"}]
    check_result("Multi-week: 3-week continuous run", s, e)

    # 2. Large timestamp jump test: verify no minute-by-minute looping hangs
    s = [
        "540,A,OPEN,P1",
        "600,A,PAUSE",
        "500000000,B,OPEN,P2",
        "500000000,B,CLOSE",
    ]
    e = [
        {"ticket_id": "A", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"},
        {"ticket_id": "B", "priority": "P2", "used_minutes": 0, "breached": False, "breached_at": None, "status": "closed"},
    ]
    check_result("Performance: Large timestamp jump without timeout", s, e)


# ==============================================================================
# MAIN TEST RUNNER
# ==============================================================================

def main():
    print("Running Business-Hours SLA Clock Adversarial Test Suite...")
    test_specification_examples()
    test_definition_of_now_and_empty()
    test_state_transitions()
    test_sla_boundaries_and_breaches()
    test_ties_and_precedence()
    test_calendar_and_holidays()
    test_out_of_order_events()
    test_malformed_lines()
    test_output_ordering()
    test_multi_week_and_large_timestamps()

    print("\n" + "=" * 50)
    print(f"Test Summary: {total_tests} executed, {passed_tests} passed, {failed_tests} failed.")
    print("=" * 50)

    if failed_tests == 0:
        print("ALL TESTS PASSED.")
        sys.exit(0)
    else:
        print(f"FAILURE: {failed_tests} tests failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()