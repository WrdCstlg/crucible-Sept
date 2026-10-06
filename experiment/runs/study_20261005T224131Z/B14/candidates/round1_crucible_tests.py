import solution
import sys


def assert_result(actual, expected, test_name):
    assert isinstance(actual, list), f"[{test_name}] Expected list, got {type(actual)}"
    assert len(actual) == len(expected), (
        f"[{test_name}] Expected {len(expected)} items, got {len(actual)}:\n"
        f"Actual:   {actual}\n"
        f"Expected: {expected}"
    )
    expected_keys = {"ticket_id", "priority", "used_minutes", "breached", "breached_at", "status"}
    for i, (act, exp) in enumerate(zip(actual, expected)):
        assert isinstance(act, dict), f"[{test_name}] Item {i} is not a dict: {type(act)}"
        assert set(act.keys()) == expected_keys, f"[{test_name}] Item {i} keys mismatch: {set(act.keys())}"
        assert isinstance(act["ticket_id"], str), f"[{test_name}] ticket_id is not str"
        assert isinstance(act["priority"], str), f"[{test_name}] priority is not str"
        assert type(act["used_minutes"]) is int, f"[{test_name}] used_minutes is not int"
        assert type(act["breached"]) is bool, f"[{test_name}] breached is not bool"
        assert act["breached_at"] is None or (
            type(act["breached_at"]) is int and type(act["breached_at"]) is not bool
        ), f"[{test_name}] breached_at is not int or None"
        assert act["status"] in ("running", "paused", "closed"), f"[{test_name}] status invalid: {act['status']}"
        assert act == exp, (
            f"[{test_name}] Item {i} mismatch:\n"
            f"Actual:   {act}\n"
            f"Expected: {exp}"
        )


def test_spec_examples():
    # Example 1
    stream1 = [
        "540,A,OPEN,P2",
        "600,A,CLOSE",
    ]
    exp1 = [{"ticket_id": "A", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    assert_result(solution.compute_sla(stream1), exp1, "Example 1")

    # Example 2
    stream2 = [
        "6720,B,OPEN,P1",
        "10680,B,PAUSE",
    ]
    exp2 = [{"ticket_id": "B", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "paused"}]
    assert_result(solution.compute_sla(stream2), exp2, "Example 2")

    # Example 3
    stream3 = [
        "540,C,OPEN,P1",
        "900,C,CLOSE",
    ]
    exp3 = [{"ticket_id": "C", "priority": "P1", "used_minutes": 360, "breached": True, "breached_at": 781, "status": "closed"}]
    assert_result(solution.compute_sla(stream3), exp3, "Example 3")

    # Example 4
    stream4 = [
        "540,D,OPEN,P3",
        "2040,D,PAUSE",
        "open,D,RESUME",
        "2100,D,RESUME,P1",
        "5,*,HOLIDAY",
    ]
    exp4 = [{"ticket_id": "D", "priority": "P3", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}]
    assert_result(solution.compute_sla(stream4), exp4, "Example 4")


def test_empty_and_no_valid_tickets():
    assert_result(solution.compute_sla([]), [], "Empty stream")
    assert_result(solution.compute_sla(["", "   ", "\t\n"]), [], "Whitespace only stream")
    assert_result(solution.compute_sla(["100,*,HOLIDAY", "2000,*,HOLIDAY"]), [], "Holiday only stream")
    assert_result(solution.compute_sla(["not,a,valid,csv,line"]), [], "Malformed only stream")

    # Ticket events for ticket that was never OPENED:
    # "Now" is 1000, but no ticket had a valid OPEN -> returns []
    stream = [
        "100,T1,PAUSE",
        "200,T1,RESUME",
        "300,T1,CLOSE",
        "500,T1,PRIORITY,P1",
        "1000,T1,REOPEN",
    ]
    assert_result(solution.compute_sla(stream), [], "Never opened ticket")


def test_malformed_lines_comprehensive():
    # Various malformations ignored completely while valid ticket is processed
    stream = [
        "",                             # empty
        "   ",                          # whitespace
        ",,,",                          # commas only
        "540,A",                        # 2 fields
        "540,A,PAUSE,extra",            # PAUSE with 4 fields
        "540,A,RESUME,P1",              # RESUME with 4 fields
        "540,A,CLOSE,P1",               # CLOSE with 4 fields
        "540,A,REOPEN,P1",              # REOPEN with 4 fields
        "540,*,HOLIDAY,extra",          # HOLIDAY with 4 fields
        "540,A,OPEN",                   # OPEN with 3 fields
        "540,A,PRIORITY",               # PRIORITY with 3 fields
        "540,A,OPEN,P1,extra",          # OPEN with 5 fields
        "-10,A,OPEN,P1",                # negative minute
        "+10,A,OPEN,P1",                # plus sign in minute
        "10.5,A,OPEN,P1",               # float minute
        "abc,A,OPEN,P1",                # letters in minute
        ",A,OPEN,P1",                   # empty minute
        "540,,OPEN,P1",                 # empty ticket ID
        "540,   ,OPEN,P1",              # whitespace ticket ID
        "540,*,OPEN,P1",                # ticket ID * for OPEN
        "540,*,PRIORITY,P1",            # ticket ID * for PRIORITY
        "540,*,PAUSE",                  # ticket ID * for PAUSE
        "540,*,RESUME",                 # ticket ID * for RESUME
        "540,*,CLOSE",                  # ticket ID * for CLOSE
        "540,*,REOPEN",                 # ticket ID * for REOPEN
        "540,A,HOLIDAY",                # non-* for HOLIDAY
        "540,,HOLIDAY",                 # empty ID for HOLIDAY
        "540,A,open,P1",                # lowercase event
        "540,A,Priority,P1",            # mixed case event
        "540,A,UNKNOWN,P1",             # unknown event
        "540,A,OPEN,p1",                # lowercase priority
        "540,A,OPEN,P5",                # invalid priority P5
        "540,A,OPEN,HIGH",              # invalid priority HIGH
        "540,A,OPEN,",                  # empty priority
        # And valid lines with whitespace trimming:
        "  00540  ,  A  ,  OPEN  ,  P2  ",
        "\t600\t,\tA\t,\tCLOSE\t",
    ]
    exp = [{"ticket_id": "A", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    assert_result(solution.compute_sla(stream), exp, "Malformed lines ignored")


def test_definition_of_now():
    # 1. Ignored transition still sets "now"
    # T1 opened at 540 (Mon 09:00). T2 has an invalid CLOSE at 1000.
    # "now" is 1000. T1 was running from 540 to 1000 (460 business minutes).
    # T2 never had a valid OPEN so T2 is not in output.
    stream1 = [
        "540,T1,OPEN,P4",
        "1000,T2,CLOSE",
    ]
    exp1 = [{"ticket_id": "T1", "priority": "P4", "used_minutes": 460, "breached": False, "breached_at": None, "status": "running"}]
    assert_result(solution.compute_sla(stream1), exp1, "Now set by ignored event")

    # 2. HOLIDAY lines never affect "now"
    # Even if HOLIDAY has minute 50000, "now" is 540.
    stream2 = [
        "540,T1,OPEN,P1",
        "50000,*,HOLIDAY",
    ]
    exp2 = [{"ticket_id": "T1", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "running"}]
    assert_result(solution.compute_sla(stream2), exp2, "Holiday does not advance now")

    # 3. Out-of-order events establish "now" as maximum ticket minute
    stream3 = [
        "700,T1,PAUSE",
        "540,T1,OPEN,P1",
        "600,T2,OPEN,P2",
    ]
    # now = 700.
    # T1: 540 to 700 (160 mins), paused at 700.
    # T2: 600 to 700 (100 mins), running at 700.
    exp3 = [
        {"ticket_id": "T1", "priority": "P1", "used_minutes": 160, "breached": False, "breached_at": None, "status": "paused"},
        {"ticket_id": "T2", "priority": "P2", "used_minutes": 100, "breached": False, "breached_at": None, "status": "running"},
    ]
    assert_result(solution.compute_sla(stream3), exp3, "Now with out-of-order events")


def test_calendar_and_business_hours():
    # Monday 00:00 is 0. Business minutes [540, 1020).
    # 1. Non-business hours only:
    # Opened at 100 (Mon 01:40), paused at 500 (Mon 08:20). now = 500.
    stream1 = [
        "100,T,OPEN,P1",
        "500,T,PAUSE",
    ]
    exp1 = [{"ticket_id": "T", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "paused"}]
    assert_result(solution.compute_sla(stream1), exp1, "Non-business hours morning")

    # 2. Spanning exact boundary: 539 to 541.
    # 539 is non-business, 540 is business minute [540, 541).
    stream2 = [
        "539,T,OPEN,P1",
        "541,T,PAUSE",
    ]
    exp2 = [{"ticket_id": "T", "priority": "P1", "used_minutes": 1, "breached": False, "breached_at": None, "status": "paused"}]
    assert_result(solution.compute_sla(stream2), exp2, "Minute 540 counted")

    # 3. Spanning end of day boundary: 1019 to 1021.
    # 1019 is business minute [1019, 1020). 1020 is not business minute.
    stream3 = [
        "1019,T,OPEN,P1",
        "1021,T,PAUSE",
    ]
    exp3 = [{"ticket_id": "T", "priority": "P1", "used_minutes": 1, "breached": False, "breached_at": None, "status": "paused"}]
    assert_result(solution.compute_sla(stream3), exp3, "Minute 1019 counted, 1020 not")

    # 4. Spanning weekend:
    # Friday 16:30 is 4*1440 + 990 = 6750.
    # Friday 17:00 is 6780 (30 business mins: 6750..6779).
    # Saturday (Day 5: 7200..8639) & Sunday (Day 6: 8640..10079): 0 mins.
    # Monday 09:30 is 7*1440 + 570 = 10650 (30 business mins: 10620..10649).
    stream4 = [
        "6750,T,OPEN,P1",
        "10650,T,CLOSE",
    ]
    exp4 = [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    assert_result(solution.compute_sla(stream4), exp4, "Weekend spanning")

    # 5. Holiday on a weekend day (idempotent / no effect):
    stream5 = [
        "6750,T,OPEN,P1",
        "10650,T,CLOSE",
        "7500,*,HOLIDAY",  # Saturday
        "9000,*,HOLIDAY",  # Sunday
    ]
    assert_result(solution.compute_sla(stream5), exp4, "Weekend holidays have no effect")

    # 6. Duplicate holiday declarations on a weekday:
    # Tuesday of week 0 is day 1 (1440..2879).
    # Opened Mon 09:00 (540), paused Wed 10:00 (2*1440 + 600 = 3480).
    # Tuesday is declared holiday twice.
    # Monday business mins: 480 (540..1019).
    # Tuesday: 0 mins.
    # Wednesday: 60 mins (3420..3479). Total = 540.
    stream6 = [
        "540,T,OPEN,P3",
        "3480,T,PAUSE",
        "1500,*,HOLIDAY",
        "2000,*,HOLIDAY",
    ]
    exp6 = [{"ticket_id": "T", "priority": "P3", "used_minutes": 540, "breached": False, "breached_at": None, "status": "paused"}]
    assert_result(solution.compute_sla(stream6), exp6, "Duplicate holiday declarations")


def test_exact_sla_boundaries_all_priorities():
    # P1: Limit = 240
    # Opened Monday 09:00 (540)
    # Minute 780 (540 + 240) -> used 240 <= 240 -> NOT breached
    s_p1_ok = ["540,T,OPEN,P1", "780,OTHER,CLOSE"]
    e_p1_ok = [{"ticket_id": "T", "priority": "P1", "used_minutes": 240, "breached": False, "breached_at": None, "status": "running"}]
    assert_result(solution.compute_sla(s_p1_ok), e_p1_ok, "P1 exact limit 240")

    # Minute 781 -> used 241 > 240 -> Breached at 781
    s_p1_br = ["540,T,OPEN,P1", "781,OTHER,CLOSE"]
    e_p1_br = [{"ticket_id": "T", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "running"}]
    assert_result(solution.compute_sla(s_p1_br), e_p1_br, "P1 breached at 781")

    # P2: Limit = 480 (Exactly 1 business day: Monday 540 to 1020)
    # At 1020 (Mon 17:00), used is 480 <= 480 -> NOT breached
    s_p2_1020 = ["540,T,OPEN,P2", "1020,OTHER,CLOSE"]
    e_p2_1020 = [{"ticket_id": "T", "priority": "P2", "used_minutes": 480, "breached": False, "breached_at": None, "status": "running"}]
    assert_result(solution.compute_sla(s_p2_1020), e_p2_1020, "P2 at 1020 (end of day)")

    # At 1980 (Tue 09:00), used is still 480 <= 480 -> NOT breached
    s_p2_1980 = ["540,T,OPEN,P2", "1980,OTHER,CLOSE"]
    e_p2_1980 = [{"ticket_id": "T", "priority": "P2", "used_minutes": 480, "breached": False, "breached_at": None, "status": "running"}]
    assert_result(solution.compute_sla(s_p2_1980), e_p2_1980, "P2 at Tue 09:00")

    # At 1981 (Tue 09:01), used becomes 481 > 480 -> Breached at 1981
    s_p2_1981 = ["540,T,OPEN,P2", "1981,OTHER,CLOSE"]
    e_p2_1981 = [{"ticket_id": "T", "priority": "P2", "used_minutes": 481, "breached": True, "breached_at": 1981, "status": "running"}]
    assert_result(solution.compute_sla(s_p2_1981), e_p2_1981, "P2 breached at 1981")

    # P3: Limit = 1440 (Exactly 3 business days: Mon, Tue, Wed)
    # Wed 17:00 is 2*1440 + 1020 = 3900.
    # At 3900, used is 1440 <= 1440 -> NOT breached
    s_p3_3900 = ["540,T,OPEN,P3", "3900,OTHER,CLOSE"]
    e_p3_3900 = [{"ticket_id": "T", "priority": "P3", "used_minutes": 1440, "breached": False, "breached_at": None, "status": "running"}]
    assert_result(solution.compute_sla(s_p3_3900), e_p3_3900, "P3 at Wed 17:00")

    # Thu 09:01 is 3*1440 + 541 = 4861.
    # At 4861, used is 1441 > 1440 -> Breached at 4861
    s_p3_4861 = ["540,T,OPEN,P3", "4861,OTHER,CLOSE"]
    e_p3_4861 = [{"ticket_id": "T", "priority": "P3", "used_minutes": 1441, "breached": True, "breached_at": 4861, "status": "running"}]
    assert_result(solution.compute_sla(s_p3_4861), e_p3_4861, "P3 breached at Thu 09:01")

    # P4: Limit = 2400 (Exactly 5 business days: Mon to Fri)
    # Fri 17:00 is 4*1440 + 1020 = 6780.
    # At 6780, used is 2400 <= 2400 -> NOT breached
    s_p4_6780 = ["540,T,OPEN,P4", "6780,OTHER,CLOSE"]
    e_p4_6780 = [{"ticket_id": "T", "priority": "P4", "used_minutes": 2400, "breached": False, "breached_at": None, "status": "running"}]
    assert_result(solution.compute_sla(s_p4_6780), e_p4_6780, "P4 at Fri 17:00")

    # Next Mon 09:01 is 7*1440 + 541 = 10621.
    # At 10621, used is 2401 > 2400 -> Breached at 10621
    s_p4_10621 = ["540,T,OPEN,P4", "10621,OTHER,CLOSE"]
    e_p4_10621 = [{"ticket_id": "T", "priority": "P4", "used_minutes": 2401, "breached": True, "breached_at": 10621, "status": "running"}]
    assert_result(solution.compute_sla(s_p4_10621), e_p4_10621, "P4 breached at next Mon 09:01")


def test_priority_changes_and_edge_cases():
    # 1. Raising priority at exact minute of breach PREVENTS breach
    # Mon 09:00 (540) P1. At 781, used becomes 241.
    # PRIORITY P2 applies at 781 -> limit becomes 480. 241 <= 480 -> No breach!
    stream1 = [
        "540,T,OPEN,P1",
        "781,T,PRIORITY,P2",
    ]
    exp1 = [{"ticket_id": "T", "priority": "P2", "used_minutes": 241, "breached": False, "breached_at": None, "status": "running"}]
    assert_result(solution.compute_sla(stream1), exp1, "Priority raise at 781 prevents breach")

    # 2. Raising priority AFTER breach does NOT undo breach (breach is sticky)
    # At 781, breached. At 782, PRIORITY P2 raised.
    stream2 = [
        "540,T,OPEN,P1",
        "782,T,PRIORITY,P2",
    ]
    exp2 = [{"ticket_id": "T", "priority": "P2", "used_minutes": 242, "breached": True, "breached_at": 781, "status": "running"}]
    assert_result(solution.compute_sla(stream2), exp2, "Priority raise after breach keeps breach")

    # 3. Lowering priority causes immediate breach even while PAUSED
    # Opened at 540 with P2 (limit 480).
    # Paused at 800 (used = 260).
    # At 850, PRIORITY P1 (limit 240). Used is 260 > 240 -> breached at 850!
    stream3 = [
        "540,T,OPEN,P2",
        "800,T,PAUSE",
        "850,T,PRIORITY,P1",
    ]
    exp3 = [{"ticket_id": "T", "priority": "P1", "used_minutes": 260, "breached": True, "breached_at": 850, "status": "paused"}]
    assert_result(solution.compute_sla(stream3), exp3, "Priority drop while paused breaches immediately")

    # 4. Priority drop outside business hours breaches at that minute
    # Opened Mon 540 P2 (limit 480). Runs all Monday (480 mins).
    # At 1200 (Mon 20:00, outside business hours), PRIORITY P1 (limit 240).
    # Used at 1200 is 480 > 240. Breached at 1200!
    stream4 = [
        "540,T,OPEN,P2",
        "1200,T,PRIORITY,P1",
    ]
    exp4 = [{"ticket_id": "T", "priority": "P1", "used_minutes": 480, "breached": True, "breached_at": 1200, "status": "running"}]
    assert_result(solution.compute_sla(stream4), exp4, "Priority drop outside business hours breaches at event minute")

    # 5. Lowering priority when used time <= new limit does not breach
    # Opened at 540 with P2 (limit 480). Paused at 700 (used = 160).
    # At 750, PRIORITY P1 (limit 240). 160 <= 240 -> No breach.
    stream5 = [
        "540,T,OPEN,P2",
        "700,T,PAUSE",
        "750,T,PRIORITY,P1",
    ]
    exp5 = [{"ticket_id": "T", "priority": "P1", "used_minutes": 160, "breached": False, "breached_at": None, "status": "paused"}]
    assert_result(solution.compute_sla(stream5), exp5, "Priority drop when used <= limit does not breach")


def test_all_24_state_transitions():
    # Helper to test a ticket with stream and compare to expected
    # 1. NOT_OPENED + OPEN -> to RUNNING, priority P, used 0
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "running"}],
        "NOT_OPENED + OPEN",
    )

    # 2-6. NOT_OPENED + {PRIORITY, PAUSE, RESUME, CLOSE, REOPEN} are ignored,
    # and followed by valid OPEN starts fresh.
    stream_not_opened = [
        "100,T,PRIORITY,P4",
        "200,T,PAUSE",
        "300,T,RESUME",
        "400,T,CLOSE",
        "450,T,REOPEN",
        "540,T,OPEN,P2",
    ]
    assert_result(
        solution.compute_sla(stream_not_opened),
        [{"ticket_id": "T", "priority": "P2", "used_minutes": 0, "breached": False, "breached_at": None, "status": "running"}],
        "NOT_OPENED invalid transitions ignored",
    )

    # 7. RUNNING + OPEN -> ignored
    # Priority stays P1, used time does not reset.
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,OPEN,P4", "700,OTHER,CLOSE"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 160, "breached": False, "breached_at": None, "status": "running"}],
        "RUNNING + OPEN ignored",
    )

    # 8. RUNNING + PRIORITY -> priority becomes P
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,PRIORITY,P3", "700,OTHER,CLOSE"]),
        [{"ticket_id": "T", "priority": "P3", "used_minutes": 160, "breached": False, "breached_at": None, "status": "running"}],
        "RUNNING + PRIORITY",
    )

    # 9. RUNNING + PAUSE -> to PAUSED
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,PAUSE"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}],
        "RUNNING + PAUSE",
    )

    # 10. RUNNING + RESUME -> ignored
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,RESUME", "700,OTHER,CLOSE"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 160, "breached": False, "breached_at": None, "status": "running"}],
        "RUNNING + RESUME ignored",
    )

    # 11. RUNNING + CLOSE -> to CLOSED
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,CLOSE"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}],
        "RUNNING + CLOSE",
    )

    # 12. RUNNING + REOPEN -> ignored
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,REOPEN", "700,OTHER,CLOSE"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 160, "breached": False, "breached_at": None, "status": "running"}],
        "RUNNING + REOPEN ignored",
    )

    # 13. PAUSED + OPEN -> ignored
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,PAUSE", "650,T,OPEN,P4", "700,OTHER,CLOSE"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}],
        "PAUSED + OPEN ignored",
    )

    # 14. PAUSED + PRIORITY -> priority becomes P
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,PAUSE", "650,T,PRIORITY,P3", "700,OTHER,CLOSE"]),
        [{"ticket_id": "T", "priority": "P3", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}],
        "PAUSED + PRIORITY",
    )

    # 15. PAUSED + PAUSE -> ignored
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,PAUSE", "650,T,PAUSE", "700,OTHER,CLOSE"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}],
        "PAUSED + PAUSE ignored",
    )

    # 16. PAUSED + RESUME -> to RUNNING
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,PAUSE", "650,T,RESUME", "700,OTHER,CLOSE"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 110, "breached": False, "breached_at": None, "status": "running"}],
        "PAUSED + RESUME",
    )

    # 17. PAUSED + CLOSE -> to CLOSED
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,PAUSE", "650,T,CLOSE"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}],
        "PAUSED + CLOSE",
    )

    # 18. PAUSED + REOPEN -> ignored
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,PAUSE", "650,T,REOPEN", "700,OTHER,CLOSE"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}],
        "PAUSED + REOPEN ignored",
    )

    # 19. CLOSED + OPEN -> to RUNNING, priority P, used resets to 0, breach cleared
    assert_result(
        solution.compute_sla([
            "540,T,OPEN,P1",
            "900,T,CLOSE",      # breached at 781, used 360
            "950,T,OPEN,P2",      # resets used to 0, breach cleared, priority P2
            "1000,T,CLOSE",
        ]),
        [{"ticket_id": "T", "priority": "P2", "used_minutes": 50, "breached": False, "breached_at": None, "status": "closed"}],
        "CLOSED + OPEN resets used and clears breach",
    )

    # 20. CLOSED + PRIORITY -> ignored
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,CLOSE", "650,T,PRIORITY,P4", "700,OTHER,CLOSE"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}],
        "CLOSED + PRIORITY ignored",
    )

    # 21. CLOSED + PAUSE -> ignored
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,CLOSE", "650,T,PAUSE", "700,OTHER,CLOSE"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}],
        "CLOSED + PAUSE ignored",
    )

    # 22. CLOSED + RESUME -> ignored
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,CLOSE", "650,T,RESUME", "700,OTHER,CLOSE"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}],
        "CLOSED + RESUME ignored",
    )

    # 23. CLOSED + CLOSE -> ignored
    assert_result(
        solution.compute_sla(["540,T,OPEN,P1", "600,T,CLOSE", "650,T,CLOSE", "700,OTHER,CLOSE"]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}],
        "CLOSED + CLOSE ignored",
    )

    # 24. CLOSED + REOPEN -> to RUNNING, used continues, breach kept, priority kept
    assert_result(
        solution.compute_sla([
            "540,T,OPEN,P1",
            "900,T,CLOSE",      # breached at 781, used 360
            "950,T,REOPEN",     # continues used from 360, keeps breach at 781
            "1000,T,CLOSE",     # ran 950 to 1000 (50 mins) -> 360 + 50 = 410
        ]),
        [{"ticket_id": "T", "priority": "P1", "used_minutes": 410, "breached": True, "breached_at": 781, "status": "closed"}],
        "CLOSED + REOPEN continues used and keeps breach",
    )


def test_ties_and_same_minute_events():
    # 1. Stable sort: events at same minute keep stream order
    # PAUSE then RESUME at 600 -> final state RUNNING
    s1 = [
        "540,T,OPEN,P1",
        "600,T,PAUSE",
        "600,T,RESUME",
    ]
    exp1 = [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "running"}]
    assert_result(solution.compute_sla(s1), exp1, "Same minute PAUSE then RESUME")

    # RESUME then PAUSE at 600 -> RESUME ignored (already running), then PAUSE -> final state PAUSED
    s2 = [
        "540,T,OPEN,P1",
        "600,T,RESUME",
        "600,T,PAUSE",
    ]
    exp2 = [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}]
    assert_result(solution.compute_sla(s2), exp2, "Same minute RESUME then PAUSE")

    # 2. OPEN, CLOSE, OPEN, P2 at minute 540:
    # First OPEN P1, then CLOSE, then OPEN P2 from CLOSED -> final state RUNNING with P2
    s3 = [
        "540,T,OPEN,P1",
        "540,T,CLOSE",
        "540,T,OPEN,P2",
    ]
    exp3 = [{"ticket_id": "T", "priority": "P2", "used_minutes": 0, "breached": False, "breached_at": None, "status": "running"}]
    assert_result(solution.compute_sla(s3), exp3, "Same minute OPEN, CLOSE, OPEN")

    # 3. Breach check occurs after all events at minute t have been applied
    # At 781: Ticket is RUNNING with P1. Events at 781: CLOSE.
    # Event applies: Ticket becomes CLOSED.
    # Breach check: used time at 781 is 241 > 240. Breached at 781!
    s4 = [
        "540,T,OPEN,P1",
        "781,T,CLOSE",
    ]
    exp4 = [{"ticket_id": "T", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "closed"}]
    assert_result(solution.compute_sla(s4), exp4, "Breach check after CLOSE at exact breach minute")

    # 4. At 781: PRIORITY P2 then PRIORITY P1 -> Final priority P1 -> breaches at 781!
    s5 = [
        "540,T,OPEN,P1",
        "781,T,PRIORITY,P2",
        "781,T,PRIORITY,P1",
    ]
    exp5 = [{"ticket_id": "T", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "running"}]
    assert_result(solution.compute_sla(s5), exp5, "Ties: P2 then P1 results in breach")

    # 5. At 781: PRIORITY P1 then PRIORITY P2 -> Final priority P2 -> NO breach!
    s6 = [
        "540,T,OPEN,P1",
        "781,T,PRIORITY,P1",
        "781,T,PRIORITY,P2",
    ]
    exp6 = [{"ticket_id": "T", "priority": "P2", "used_minutes": 241, "breached": False, "breached_at": None, "status": "running"}]
    assert_result(solution.compute_sla(s6), exp6, "Ties: P1 then P2 prevents breach")


def test_out_of_order_stream():
    # Tickets events arrive completely out of order
    stream = [
        "600,A,CLOSE",
        "900,B,PAUSE",
        "540,A,OPEN,P2",
        "200,*,HOLIDAY",  # Day 0 is NOT holiday (200 // 1440 == 0 wait, 200 // 1440 is day 0!)
    ]
    # Day 0 is declared holiday! So Monday 540 to 600 has 0 business minutes!
    # A was open 540 to 600, used_minutes = 0. Status closed.
    # B never opened -> not in output.
    # now = 900.
    exp = [{"ticket_id": "A", "priority": "P2", "used_minutes": 0, "breached": False, "breached_at": None, "status": "closed"}]
    assert_result(solution.compute_sla(stream), exp, "Out-of-order with holiday")


def test_output_ordering_and_types():
    # Output must be sorted by ticket_id in Python's default string order (code-point order)
    # IDs: "10", "2", "A", "B", "T1", "T10", "T2", "t1"
    stream = [
        "540,t1,OPEN,P1",
        "540,T2,OPEN,P2",
        "540,T10,OPEN,P3",
        "540,T1,OPEN,P4",
        "540,B,OPEN,P1",
        "540,A,OPEN,P2",
        "540,2,OPEN,P3",
        "540,10,OPEN,P4",
    ]
    res = solution.compute_sla(stream)
    expected_ids = ["10", "2", "A", "B", "T1", "T10", "T2", "t1"]
    actual_ids = [d["ticket_id"] for d in res]
    assert actual_ids == expected_ids, f"Sorting mismatch: got {actual_ids}, expected {expected_ids}"


def test_large_timestamp_performance():
    # Minute 999,999,000
    # 999999000 // 1440 = 694443. 694443 % 7 = 1 (Tuesday).
    # Minute of day: 999999000 % 1440 = 1080 (18:00, after business hours).
    # Next day (Wednesday, day 694444): starts at 694444 * 1440 = 999999360.
    # Wed 09:00 is 999999360 + 540 = 999999900.
    # Wed 10:00 is 999999900 + 60 = 999999960.
    # Ticket open at 999999000, paused at 999999960.
    # Used minutes = 60.
    stream = [
        "999999000,T,OPEN,P1",
        "999999960,T,PAUSE",
    ]
    exp = [{"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}]
    assert_result(solution.compute_sla(stream), exp, "Large timestamp 1,000,000,000")

    # Wednesday declared holiday on day 694444
    stream_hol = [
        "999999000,T,OPEN,P1",
        "999999960,T,PAUSE",
        "999999360,*,HOLIDAY",
    ]
    exp_hol = [{"ticket_id": "T", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "paused"}]
    assert_result(solution.compute_sla(stream_hol), exp_hol, "Large timestamp with holiday")


def main():
    tests = [
        ("Spec Examples", test_spec_examples),
        ("Empty and No Valid Tickets", test_empty_and_no_valid_tickets),
        ("Comprehensive Malformed Lines", test_malformed_lines_comprehensive),
        ("Definition of Now", test_definition_of_now),
        ("Calendar and Business Hours", test_calendar_and_business_hours),
        ("Exact SLA Boundaries All Priorities", test_exact_sla_boundaries_all_priorities),
        ("Priority Changes and Edge Cases", test_priority_changes_and_edge_cases),
        ("All 24 State Transitions", test_all_24_state_transitions),
        ("Ties and Same Minute Events", test_ties_and_same_minute_events),
        ("Out-of-Order Stream", test_out_of_order_stream),
        ("Output Ordering and Types", test_output_ordering_and_types),
        ("Large Timestamp Performance", test_large_timestamp_performance),
    ]

    passed = 0
    failed = 0

    print("Running Business-Hours SLA Clock Adversarial Test Suite...")
    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            failed += 1

    print("\nSummary:")
    print(f"  Total tests:  {len(tests)}")
    print(f"  Passed:       {passed}")
    print(f"  Failed:       {failed}")

    if failed == 0:
        print("ALL TESTS PASSED.")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    main()