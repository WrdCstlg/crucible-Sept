import solution
import sys
import time


def assert_equal(actual, expected, msg=""):
    assert actual == expected, f"{msg}\nExpected: {expected}\nActual:   {actual}"


def assert_output_structure(result):
    assert isinstance(result, list), f"Expected list, got {type(result)}"
    for item in result:
        assert isinstance(item, dict), f"Expected dict in list, got {type(item)}"
        assert set(item.keys()) == {
            "ticket_id",
            "priority",
            "used_minutes",
            "breached",
            "breached_at",
            "status",
        }, f"Keys mismatch: {item.keys()}"
        assert isinstance(item["ticket_id"], str), f"ticket_id not str: {type(item['ticket_id'])}"
        assert item["priority"] in ("P1", "P2", "P3", "P4"), f"Invalid priority: {item['priority']}"
        assert type(item["used_minutes"]) is int, f"used_minutes not int: {type(item['used_minutes'])}"
        assert type(item["breached"]) is bool, f"breached not bool: {type(item['breached'])}"
        if item["breached"]:
            assert type(item["breached_at"]) is int, f"breached_at not int when breached: {type(item['breached_at'])}"
        else:
            assert item["breached_at"] is None, f"breached_at not None when not breached: {item['breached_at']}"
        assert item["status"] in ("running", "paused", "closed"), f"Invalid status: {item['status']}"


def test_specification_examples():
    # Example 1
    stream1 = [
        "540,A,OPEN,P2",
        "600,A,CLOSE",
    ]
    exp1 = [{"ticket_id": "A", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res1 = solution.compute_sla(stream1)
    assert_output_structure(res1)
    assert_equal(res1, exp1, "Example 1 failed")

    # Example 2
    stream2 = [
        "6720,B,OPEN,P1",
        "10680,B,PAUSE",
    ]
    exp2 = [{"ticket_id": "B", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "paused"}]
    res2 = solution.compute_sla(stream2)
    assert_output_structure(res2)
    assert_equal(res2, exp2, "Example 2 failed")

    # Example 3
    stream3 = [
        "540,C,OPEN,P1",
        "900,C,CLOSE",
    ]
    exp3 = [{"ticket_id": "C", "priority": "P1", "used_minutes": 360, "breached": True, "breached_at": 781, "status": "closed"}]
    res3 = solution.compute_sla(stream3)
    assert_output_structure(res3)
    assert_equal(res3, exp3, "Example 3 failed")

    # Example 4
    stream4 = [
        "540,D,OPEN,P3",
        "2040,D,PAUSE",
        "open,D,RESUME",
        "2100,D,RESUME,P1",
        "5,*,HOLIDAY",
    ]
    exp4 = [{"ticket_id": "D", "priority": "P3", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}]
    res4 = solution.compute_sla(stream4)
    assert_output_structure(res4)
    assert_equal(res4, exp4, "Example 4 failed")


def test_malformed_inputs_and_trimming():
    # Only malformed lines -> []
    malformed = [
        "",
        "   ",
        "\t\t",
        "540",
        "540,T1",
        "540,T1,OPEN",
        "540,T1,OPEN,P1,EXTRA",
        "540,T1,PRIORITY",
        "540,T1,PRIORITY,P1,EXTRA",
        "540,T1,PAUSE,P1",
        "540,T1,PAUSE,",
        "540,T1,RESUME,P2",
        "540,T1,CLOSE,P3",
        "540,T1,REOPEN,P4",
        "540,*,HOLIDAY,P1",
        "540,T1,HOLIDAY",
        "540,*,OPEN,P1",
        "540,*,PAUSE",
        "540,*,CLOSE",
        "540,*,RESUME",
        "540,*,REOPEN",
        "540,*,PRIORITY,P1",
        "540,T1,UNKNOWN,P1",
        "540,T1,open,P1",
        "540,T1,OPEN,p1",
        "540,T1,OPEN,P0",
        "540,T1,OPEN,P5",
        "540,T1,PRIORITY,HIGH",
        "-540,T1,OPEN,P1",
        "+540,T1,OPEN,P1",
        "540.0,T1,OPEN,P1",
        "540a,T1,OPEN,P1",
        ",T1,OPEN,P1",
        "540,,OPEN,P1",
        "540,   ,OPEN,P1",
        "540,T1,,P1",
        "540,T1,OPEN,",
    ]
    res_empty = solution.compute_sla(malformed)
    assert_equal(res_empty, [], "All malformed lines should return empty list")

    # Mixed with valid lines having whitespace and leading zeros
    mixed = malformed + [
        "  00540  ,  VALID  ,  OPEN  ,  P1  ",
        "  00600  ,  VALID  ,  CLOSE  ",
    ]
    exp = [{"ticket_id": "VALID", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res_mixed = solution.compute_sla(mixed)
    assert_output_structure(res_mixed)
    assert_equal(res_mixed, exp, "Valid ticket with surrounding whitespace and leading zeros failed")


def test_definition_of_now():
    # 1. Empty stream
    assert_equal(solution.compute_sla([]), [], "Empty stream must return []")

    # 2. Only holidays in stream -> no well-formed ticket events -> return []
    assert_equal(solution.compute_sla(["540,*,HOLIDAY", "2000,*,HOLIDAY"]), [], "Only holidays must return []")

    # 3. Ignored ticket event sets 'now'
    # Ticket T1 opened at 540, closed at 600.
    # Ticket T_IGN never opened, but has well-formed event at 1000: '1000,T_IGN,PAUSE'
    # 'now' must be 1000. T_IGN is not in output because it never had valid OPEN.
    stream = [
        "540,T1,OPEN,P1",
        "600,T1,CLOSE",
        "1000,T_IGN,PAUSE",
        "5000,*,HOLIDAY",  # HOLIDAY does not affect 'now'
    ]
    exp = [{"ticket_id": "T1", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    assert_output_structure(res)
    assert_equal(res, exp, "Ignored event setting now failed")

    # 4. Ignored ticket event advances time while ticket is RUNNING
    # T1 opened at 540 (Monday 09:00), P1 (limit 240).
    # Well-formed event at 1000 (Monday 16:40).
    # Used time at 1000 is 1000 - 540 = 460. Breached at 781!
    stream2 = [
        "540,T1,OPEN,P1",
        "1000,T_IGN,RESUME",
        "5000,*,HOLIDAY",
    ]
    exp2 = [{"ticket_id": "T1", "priority": "P1", "used_minutes": 460, "breached": True, "breached_at": 781, "status": "running"}]
    res2 = solution.compute_sla(stream2)
    assert_output_structure(res2)
    assert_equal(res2, exp2, "Running ticket up to now with ignored event failed")


def test_ties_and_out_of_order_events():
    # 1. Reverse chronological order
    stream_rev = [
        "900,REV,CLOSE",
        "700,REV,RESUME",
        "650,REV,PAUSE",
        "600,REV,PRIORITY,P2",
        "540,REV,OPEN,P1",
    ]
    # 540..650 is 110 business mins. 650..700 paused. 700..900 is 200 business mins. Total = 310.
    exp_rev = [{"ticket_id": "REV", "priority": "P2", "used_minutes": 310, "breached": False, "breached_at": None, "status": "closed"}]
    res_rev = solution.compute_sla(stream_rev)
    assert_output_structure(res_rev)
    assert_equal(res_rev, exp_rev, "Reverse chronological order failed")

    # 2. Stable sort ties at minute 540: OPEN then PRIORITY -> P2
    stream_tie1 = [
        "600,T1,PAUSE",
        "540,T1,OPEN,P1",
        "540,T1,PRIORITY,P2",
    ]
    exp_tie1 = [{"ticket_id": "T1", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}]
    assert_equal(solution.compute_sla(stream_tie1), exp_tie1, "Tie OPEN then PRIORITY failed")

    # 3. Stable sort ties at minute 540: PRIORITY then OPEN -> PRIORITY ignored, remains P1
    stream_tie2 = [
        "600,T2,PAUSE",
        "540,T2,PRIORITY,P2",  # ignored while NOT_OPENED
        "540,T2,OPEN,P1",
    ]
    exp_tie2 = [{"ticket_id": "T2", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}]
    assert_equal(solution.compute_sla(stream_tie2), exp_tie2, "Tie PRIORITY then OPEN failed")

    # 4. Tie at minute 600: PAUSE then RESUME -> RUNNING
    stream_tie3 = [
        "540,T3,OPEN,P1",
        "600,T3,PAUSE",
        "600,T3,RESUME",
        "660,T3,PAUSE",
    ]
    exp_tie3 = [{"ticket_id": "T3", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "paused"}]
    assert_equal(solution.compute_sla(stream_tie3), exp_tie3, "Tie PAUSE then RESUME failed")

    # 5. Tie at minute 600: RESUME then PAUSE -> PAUSED
    stream_tie4 = [
        "540,T4,OPEN,P1",
        "600,T4,RESUME",  # ignored while RUNNING
        "600,T4,PAUSE",   # becomes PAUSED
        "660,T4,RESUME",  # resumes at 660, now is 660
    ]
    exp_tie4 = [{"ticket_id": "T4", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "running"}]
    assert_equal(solution.compute_sla(stream_tie4), exp_tie4, "Tie RESUME then PAUSE failed")


def test_state_transitions_exhaustive():
    # Cover every cell of the transition table (4 states x 6 events = 24 transitions)
    stream = [
        # NOT_OPENED:
        # OPEN,P1 -> RUNNING (tested elsewhere)
        # PRIORITY, PAUSE, RESUME, CLOSE, REOPEN all ignored:
        "100,T_NO,PRIORITY,P1",
        "200,T_NO,PAUSE",
        "300,T_NO,RESUME",
        "400,T_NO,CLOSE",
        "500,T_NO,REOPEN",
        # RUNNING:
        # OPEN ignored:
        "540,T_RO,OPEN,P1",
        "570,T_RO,OPEN,P2",
        "600,T_RO,CLOSE",
        # RESUME ignored:
        "540,T_RR,OPEN,P1",
        "570,T_RR,RESUME",
        "600,T_RR,CLOSE",
        # REOPEN ignored:
        "540,T_RRE,OPEN,P1",
        "570,T_RRE,REOPEN",
        "600,T_RRE,CLOSE",
        # PAUSED:
        # OPEN ignored:
        "540,T_PO,OPEN,P1",
        "570,T_PO,PAUSE",
        "580,T_PO,OPEN,P2",
        "600,T_PO,RESUME",
        "620,T_PO,CLOSE",
        # PAUSE ignored:
        "540,T_PP,OPEN,P1",
        "570,T_PP,PAUSE",
        "580,T_PP,PAUSE",
        "600,T_PP,RESUME",
        "620,T_PP,CLOSE",
        # REOPEN ignored:
        "540,T_PRE,OPEN,P1",
        "570,T_PRE,PAUSE",
        "580,T_PRE,REOPEN",
        "600,T_PRE,RESUME",
        "620,T_PRE,CLOSE",
        # CLOSE while PAUSED:
        "540,T_PC,OPEN,P1",
        "570,T_PC,PAUSE",
        "600,T_PC,CLOSE",
        # CLOSED:
        # PRIORITY ignored:
        "540,T_CP,OPEN,P1",
        "600,T_CP,CLOSE",
        "650,T_CP,PRIORITY,P2",
        "700,T_CP,REOPEN",
        "720,T_CP,CLOSE",
        # PAUSE ignored:
        "540,T_CPA,OPEN,P1",
        "600,T_CPA,CLOSE",
        "650,T_CPA,PAUSE",
        "700,T_CPA,REOPEN",
        "720,T_CPA,CLOSE",
        # RESUME ignored:
        "540,T_CR,OPEN,P1",
        "600,T_CR,CLOSE",
        "650,T_CR,RESUME",
        "700,T_CR,CLOSE",
        # CLOSE ignored:
        "540,T_CC,OPEN,P1",
        "600,T_CC,CLOSE",
        "650,T_CC,CLOSE",
        # OPEN from CLOSED resets used to 0, clears breach, sets priority:
        "540,T_CO,OPEN,P1",
        "800,T_CO,CLOSE",
        "850,T_CO,OPEN,P2",
        "900,T_CO,CLOSE",
        # REOPEN from CLOSED keeps breach, continues used, keeps priority:
        "540,T_CRE,OPEN,P1",
        "800,T_CRE,CLOSE",
        "850,T_CRE,REOPEN",
        "900,T_CRE,CLOSE",
    ]

    res = solution.compute_sla(stream)
    res_map = {item["ticket_id"]: item for item in res}

    assert "T_NO" not in res_map, "T_NO should not be in output (never opened)"

    assert_equal(res_map["T_RO"], {"ticket_id": "T_RO", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"})
    assert_equal(res_map["T_RR"], {"ticket_id": "T_RR", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"})
    assert_equal(res_map["T_RRE"], {"ticket_id": "T_RRE", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"})

    assert_equal(res_map["T_PO"], {"ticket_id": "T_PO", "priority": "P1", "used_minutes": 50, "breached": False, "breached_at": None, "status": "closed"})
    assert_equal(res_map["T_PP"], {"ticket_id": "T_PP", "priority": "P1", "used_minutes": 50, "breached": False, "breached_at": None, "status": "closed"})
    assert_equal(res_map["T_PRE"], {"ticket_id": "T_PRE", "priority": "P1", "used_minutes": 50, "breached": False, "breached_at": None, "status": "closed"})
    assert_equal(res_map["T_PC"], {"ticket_id": "T_PC", "priority": "P1", "used_minutes": 30, "breached": False, "breached_at": None, "status": "closed"})

    assert_equal(res_map["T_CP"], {"ticket_id": "T_CP", "priority": "P1", "used_minutes": 80, "breached": False, "breached_at": None, "status": "closed"})
    assert_equal(res_map["T_CPA"], {"ticket_id": "T_CPA", "priority": "P1", "used_minutes": 80, "breached": False, "breached_at": None, "status": "closed"})
    assert_equal(res_map["T_CR"], {"ticket_id": "T_CR", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"})
    assert_equal(res_map["T_CC"], {"ticket_id": "T_CC", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"})

    assert_equal(res_map["T_CO"], {"ticket_id": "T_CO", "priority": "P2", "used_minutes": 50, "breached": False, "breached_at": None, "status": "closed"})
    assert_equal(res_map["T_CRE"], {"ticket_id": "T_CRE", "priority": "P1", "used_minutes": 310, "breached": True, "breached_at": 781, "status": "closed"})


def test_sla_breach_boundaries_and_priority_changes():
    # 1. Exact boundary: ran 240 minutes for P1 (540 to 780). Used == limit -> NOT breached.
    stream1 = [
        "540,EXACT,OPEN,P1",
        "780,EXACT,CLOSE",
    ]
    exp1 = [{"ticket_id": "EXACT", "priority": "P1", "used_minutes": 240, "breached": False, "breached_at": None, "status": "closed"}]
    assert_equal(solution.compute_sla(stream1), exp1, "Ran exactly limit minutes must not breach")

    # 2. Limit + 1 minute: ran 241 minutes for P1 (540 to 781). Used > limit -> breached at 781!
    stream2 = [
        "540,PLUS1,OPEN,P1",
        "781,PLUS1,CLOSE",
    ]
    exp2 = [{"ticket_id": "PLUS1", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "closed"}]
    assert_equal(solution.compute_sla(stream2), exp2, "Ran limit + 1 minutes must breach at 781")

    # 3. PRIORITY raise at minute 781 prevents breach (events applied before check)
    stream3 = [
        "540,PREVENT,OPEN,P1",
        "781,PREVENT,PRIORITY,P2",
        "800,PREVENT,CLOSE",
    ]
    exp3 = [{"ticket_id": "PREVENT", "priority": "P2", "used_minutes": 260, "breached": False, "breached_at": None, "status": "closed"}]
    assert_equal(solution.compute_sla(stream3), exp3, "Priority raise at exact breach minute must prevent breach")

    # 4. PRIORITY downgrade causes immediate breach while PAUSED
    stream4 = [
        "540,DOWN,OPEN,P2",
        "840,DOWN,PAUSE",          # used = 300 <= 480
        "860,DOWN,PRIORITY,P1",    # P1 limit = 240. Used 300 > 240 -> breached immediately at 860!
    ]
    exp4 = [{"ticket_id": "DOWN", "priority": "P1", "used_minutes": 300, "breached": True, "breached_at": 860, "status": "paused"}]
    assert_equal(solution.compute_sla(stream4), exp4, "Priority downgrade while paused must breach immediately")

    # 5. PRIORITY raise after breach does NOT undo breach (breach is sticky)
    stream5 = [
        "540,STICKY,OPEN,P1",
        "781,STICKY,PAUSE",        # breached at 781
        "800,STICKY,PRIORITY,P4",  # limit raised to 2400
        "850,STICKY,CLOSE",
    ]
    exp5 = [{"ticket_id": "STICKY", "priority": "P4", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "closed"}]
    assert_equal(solution.compute_sla(stream5), exp5, "Breach must remain sticky after priority raise")

    # 6. Same minute tie: CLOSE then PRIORITY vs PRIORITY then CLOSE
    # A: PRIORITY then CLOSE at 781: priority becomes P1 (limit 240), then closed. Used 241 > 240 -> breached at 781!
    stream6a = [
        "540,T_A,OPEN,P2",
        "781,T_A,PRIORITY,P1",
        "781,T_A,CLOSE",
    ]
    exp6a = [{"ticket_id": "T_A", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "closed"}]
    assert_equal(solution.compute_sla(stream6a), exp6a, "PRIORITY then CLOSE at 781 failed")

    # B: CLOSE then PRIORITY at 781: closed first, PRIORITY is ignored! Priority remains P2 (limit 480). Not breached!
    stream6b = [
        "540,T_B,OPEN,P2",
        "781,T_B,CLOSE",
        "781,T_B,PRIORITY,P1",
    ]
    exp6b = [{"ticket_id": "T_B", "priority": "P2", "used_minutes": 241, "breached": False, "breached_at": None, "status": "closed"}]
    assert_equal(solution.compute_sla(stream6b), exp6b, "CLOSE then PRIORITY at 781 failed")


def test_business_hours_and_calendar_boundaries():
    # Boundary minutes:
    # Day 0 Monday:
    # 539: non-business
    # 540: business
    # 1019: business
    # 1020: non-business
    stream = [
        "539,B_PRE,OPEN,P1",
        "540,B_PRE,CLOSE",

        "540,B_EX,OPEN,P1",
        "600,B_EX,CLOSE",

        "1019,B_IN,OPEN,P1",
        "1020,B_IN,CLOSE",

        "1020,B_POST,OPEN,P1",
        "1021,B_POST,CLOSE",

        # Weekend (Day 5 Saturday: 7200 to 8639)
        "7200,B_SAT,OPEN,P1",
        "8640,B_SAT,CLOSE",
    ]
    res = solution.compute_sla(stream)
    res_map = {item["ticket_id"]: item for item in res}

    assert_equal(res_map["B_PRE"]["used_minutes"], 0, "539..540 is 0 business minutes")
    assert_equal(res_map["B_EX"]["used_minutes"], 60, "540..600 is 60 business minutes")
    assert_equal(res_map["B_IN"]["used_minutes"], 1, "1019..1020 is 1 business minute")
    assert_equal(res_map["B_POST"]["used_minutes"], 0, "1020..1021 is 0 business minutes")
    assert_equal(res_map["B_SAT"]["used_minutes"], 0, "Saturday is 0 business minutes")

    # Breach occurring exactly at 17:00 (minute 1020):
    # Opened Monday 12:59 (minute 779) at P1 (limit 240).
    # Minute 779..1019 is 240 business minutes.
    # Minute 1019..1020 is 241st business minute.
    # At minute 1020, used time is 241 > 240 -> breached at 1020!
    # Even if closed later at 1100, breached_at is 1020.
    stream_1020 = [
        "779,E1020,OPEN,P1",
        "1100,E1020,CLOSE",
    ]
    exp_1020 = [{"ticket_id": "E1020", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 1020, "status": "closed"}]
    assert_equal(solution.compute_sla(stream_1020), exp_1020, "Breach at 17:00 (1020) failed")


def test_holidays_and_multi_week():
    # Day 0 (Mon) 540 to Day 2 (Wed) 3500.
    # Tuesday (Day 1, 1440) is a holiday.
    # Mon 540..1020 = 480 mins.
    # Tue: 0 mins.
    # Wed 09:00 is 2 * 1440 + 540 = 3420.
    # Limit P2 = 480.
    # At Wed 3420: used is 480 <= 480.
    # 481st minute is 3420..3421.
    # Breached at 3421!
    # Closed Wed 3500 (used = 480 + 80 = 560).
    # Holiday declared duplicate and declared at the end of the stream.
    stream = [
        "540,H_TICKET,OPEN,P2",
        "3500,H_TICKET,CLOSE",
        "1440,*,HOLIDAY",
        "2000,*,HOLIDAY",  # duplicate holiday for day 1
        "7200,*,HOLIDAY",  # holiday on Saturday (no-op on business days)
    ]
    exp = [{"ticket_id": "H_TICKET", "priority": "P2", "used_minutes": 560, "breached": True, "breached_at": 3421, "status": "closed"}]
    assert_equal(solution.compute_sla(stream), exp, "Holiday and multi-day breach failed")


def test_clearing_breach_and_second_breach():
    # 1st run: breaches at 781. Closed at 790.
    # OPEN,P1 at 800: clears breach and resets used to 0.
    # 2nd run: Mon 800..1020 is 220 mins.
    # Closed at 1100.
    # Reopened Tue 09:00 (1980). Needs 20 mins to reach 240 (at 2000).
    # 241st minute is 2000..2001. Breached at 2001!
    # Closed at 2020 (used = 220 + 40 = 260).
    stream = [
        "540,RE_BREACH,OPEN,P1",
        "790,RE_BREACH,CLOSE",
        "800,RE_BREACH,OPEN,P1",
        "1100,RE_BREACH,CLOSE",
        "1980,RE_BREACH,REOPEN",
        "2020,RE_BREACH,CLOSE",
    ]
    exp = [{"ticket_id": "RE_BREACH", "priority": "P1", "used_minutes": 260, "breached": True, "breached_at": 2001, "status": "closed"}]
    assert_equal(solution.compute_sla(stream), exp, "Clearing breach and second breach failed")


def test_sorting_order_and_case_sensitivity():
    stream = [
        "540,T10,OPEN,P1",
        "600,T10,CLOSE",
        "540,T2,OPEN,P1",
        "600,T2,CLOSE",
        "540,T1,OPEN,P1",
        "600,T1,CLOSE",
        "540,t1,OPEN,P2",
        "600,t1,CLOSE",
        "540,a,OPEN,P1",
        "600,a,CLOSE",
        "540,A,OPEN,P1",
        "600,A,CLOSE",
        "540,1,OPEN,P1",
        "600,1,CLOSE",
    ]
    # Expected order: "1", "A", "T1", "T10", "T2", "a", "t1"
    res = solution.compute_sla(stream)
    ticket_ids = [d["ticket_id"] for d in res]
    expected_ids = ["1", "A", "T1", "T10", "T2", "a", "t1"]
    assert_equal(ticket_ids, expected_ids, "Code-point order and case sensitivity failed")
    assert res[ticket_ids.index("T1")]["priority"] == "P1"
    assert res[ticket_ids.index("t1")]["priority"] == "P2"


def test_large_minute_jump_and_performance():
    # 1. Large minute jump while PAUSED: must not loop minute-by-minute
    t0 = time.time()
    stream_big = [
        "540,BIG,OPEN,P1",
        "600,BIG,PAUSE",
        "1000000000,BIG,CLOSE",
    ]
    res_big = solution.compute_sla(stream_big)
    elapsed = time.time() - t0
    assert elapsed < 3.0, f"Large minute jump took too long ({elapsed:.2f}s) - likely looping minute-by-minute!"
    exp_big = [{"ticket_id": "BIG", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    assert_equal(res_big, exp_big, "Large minute jump calculation failed")

    # 2. Multi-week run with exact breach calculation across weekend
    # Opened Mon week 0 at 540 with P4 (limit 2400).
    # Runs Mon..Fri week 0 (5 * 480 = 2400 business minutes).
    # Used reaches 2400 at Fri 17:00 (minute 6780). Not breached.
    # Weekend: 0.
    # Mon week 1 09:00 is minute 10620.
    # 2401st business minute is 10620..10621.
    # Breached at 10621!
    # Closed Mon week 1 10:00 (minute 10680).
    # Used = 2400 + 60 = 2460.
    stream_multi = [
        "540,MULTI,OPEN,P4",
        "10680,MULTI,CLOSE",
    ]
    exp_multi = [{"ticket_id": "MULTI", "priority": "P4", "used_minutes": 2460, "breached": True, "breached_at": 10621, "status": "closed"}]
    assert_equal(solution.compute_sla(stream_multi), exp_multi, "Multi-week breach across weekend failed")

    # 3. Stream with moderate number of events (2,000 lines)
    stream_vol = []
    # 200 tickets
    for i in range(200):
        tid = f"T_{i:03d}"
        stream_vol.append(f"540,{tid},OPEN,P1")
        stream_vol.append(f"600,{tid},PAUSE")
        stream_vol.append(f"660,{tid},RESUME")
        stream_vol.append(f"720,{tid},CLOSE")
    stream_vol.append("1440,*,HOLIDAY")
    t0 = time.time()
    res_vol = solution.compute_sla(stream_vol)
    elapsed_vol = time.time() - t0
    assert elapsed_vol < 3.0, f"Volume test took {elapsed_vol:.2f}s"
    assert len(res_vol) == 200, f"Expected 200 tickets, got {len(res_vol)}"
    assert res_vol[0]["used_minutes"] == 120


def main():
    tests = [
        test_specification_examples,
        test_malformed_inputs_and_trimming,
        test_definition_of_now,
        test_ties_and_out_of_order_events,
        test_state_transitions_exhaustive,
        test_sla_breach_boundaries_and_priority_changes,
        test_business_hours_and_calendar_boundaries,
        test_holidays_and_multi_week,
        test_clearing_breach_and_second_breach,
        test_sorting_order_and_case_sensitivity,
        test_large_minute_jump_and_performance,
    ]

    passed = 0
    failed = 0

    print("Running Business-hours SLA Clock adversarial test suite...")
    for t in tests:
        name = t.__name__
        try:
            t()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1

    print("\nTest Summary:")
    print(f"  Passed: {passed}/{len(tests)}")
    print(f"  Failed: {failed}/{len(tests)}")

    if failed == 0:
        print("\nAll tests passed successfully.")
        sys.exit(0)
    else:
        print(f"\n{failed} test(s) failed.")
        sys.exit(1)


if __name__ == "__main__":
    main()