import solution
import sys


def validate_ticket_dict(act, exp, test_name):
    expected_keys = {"ticket_id", "priority", "used_minutes", "breached", "breached_at", "status"}
    if set(act.keys()) != expected_keys:
        raise AssertionError(f"[{test_name}] Key set mismatch: expected {expected_keys}, got {set(act.keys())}")

    if type(act["ticket_id"]) is not str:
        raise AssertionError(f"[{test_name}] ticket_id must be str, got {type(act['ticket_id'])}")
    if act["ticket_id"] != exp["ticket_id"]:
        raise AssertionError(f"[{test_name}] ticket_id mismatch: expected {exp['ticket_id']}, got {act['ticket_id']}")

    if type(act["priority"]) is not str or act["priority"] not in {"P1", "P2", "P3", "P4"}:
        raise AssertionError(f"[{test_name}] priority invalid: {act['priority']}")
    if act["priority"] != exp["priority"]:
        raise AssertionError(f"[{test_name}] priority mismatch: expected {exp['priority']}, got {act['priority']}")

    if type(act["used_minutes"]) is not int:
        raise AssertionError(f"[{test_name}] used_minutes must be int, got {type(act['used_minutes'])}")
    if act["used_minutes"] != exp["used_minutes"]:
        raise AssertionError(f"[{test_name}] used_minutes mismatch: expected {exp['used_minutes']}, got {act['used_minutes']}")

    if type(act["breached"]) is not bool:
        raise AssertionError(f"[{test_name}] breached must be bool, got {type(act['breached'])}")
    if act["breached"] != exp["breached"]:
        raise AssertionError(f"[{test_name}] breached mismatch: expected {exp['breached']}, got {act['breached']}")

    if exp["breached"]:
        if type(act["breached_at"]) is not int:
            raise AssertionError(f"[{test_name}] breached_at must be int when breached=True, got {type(act['breached_at'])}")
        if act["breached_at"] != exp["breached_at"]:
            raise AssertionError(f"[{test_name}] breached_at mismatch: expected {exp['breached_at']}, got {act['breached_at']}")
    else:
        if act["breached_at"] is not None:
            raise AssertionError(f"[{test_name}] breached_at must be None when breached=False, got {act['breached_at']}")

    if type(act["status"]) is not str or act["status"] not in {"running", "paused", "closed"}:
        raise AssertionError(f"[{test_name}] status invalid: {act['status']}")
    if act["status"] != exp["status"]:
        raise AssertionError(f"[{test_name}] status mismatch: expected {exp['status']}, got {act['status']}")


def check(stream, expected, test_name):
    res = solution.compute_sla(stream)
    if type(res) is not list:
        raise AssertionError(f"[{test_name}] Return value must be a list, got {type(res)}")
    if len(res) != len(expected):
        raise AssertionError(f"[{test_name}] Expected {len(expected)} records, got {len(res)}: {res}")
    for i, (act, exp) in enumerate(zip(res, expected)):
        validate_ticket_dict(act, exp, f"{test_name} item {i}")


def run_all_tests():
    passed = 0
    failed = 0

    def test(fn):
        nonlocal passed, failed
        name = fn.__name__
        try:
            fn()
            print(f"PASS: {name}")
            passed += 1
        except Exception as e:
            print(f"FAIL: {name}: {e}")
            failed += 1

    @test
    def test_example_1():
        stream = [
            "540,A,OPEN,P2",
            "600,A,CLOSE",
        ]
        expected = [
            {"ticket_id": "A", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
        ]
        check(stream, expected, "test_example_1")

    @test
    def test_example_2():
        stream = [
            "6720,B,OPEN,P1",
            "10680,B,PAUSE",
        ]
        expected = [
            {"ticket_id": "B", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "paused"}
        ]
        check(stream, expected, "test_example_2")

    @test
    def test_example_3():
        stream = [
            "540,C,OPEN,P1",
            "900,C,CLOSE",
        ]
        expected = [
            {"ticket_id": "C", "priority": "P1", "used_minutes": 360, "breached": True, "breached_at": 781, "status": "closed"}
        ]
        check(stream, expected, "test_example_3")

    @test
    def test_example_4():
        stream = [
            "540,D,OPEN,P3",
            "2040,D,PAUSE",
            "open,D,RESUME",
            "2100,D,RESUME,P1",
            "5,*,HOLIDAY",
        ]
        expected = [
            {"ticket_id": "D", "priority": "P3", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}
        ]
        check(stream, expected, "test_example_4")

    @test
    def test_empty_and_ignored_streams():
        check([], [], "empty stream")
        check(["", "   ", "\t\r\n", "foo,bar", "invalid line"], [], "malformed only")
        check(["5,*,HOLIDAY", "  1440 , * , HOLIDAY  "], [], "holiday only returns []")
        check(["100,*,OPEN,P1", "200,*,PAUSE", "300,*,CLOSE"], [], "asterisk with non-holiday")
        check(["540,X,PAUSE", "600,X,CLOSE"], [], "ticket without valid OPEN returns []")

    @test
    def test_malformed_lines_filtering():
        stream = [
            "",
            "   ",
            "540,M1",
            "540,M1,OPEN,P1,EXTRA",
            "540,M1,OPEN",
            "540,M1,PRIORITY",
            "540,M1,PAUSE,P1",
            "540,M1,RESUME,P2",
            "540,M1,CLOSE,P3",
            "540,M1,REOPEN,P4",
            "540,*,HOLIDAY,EXTRA",
            "540,*,OPEN,P1",
            "540,*,PAUSE",
            "540,M1,HOLIDAY",
            "-540,M1,OPEN,P1",
            "+540,M1,OPEN,P1",
            "540.5,M1,OPEN,P1",
            "abc,M1,OPEN,P1",
            "540,,OPEN,P1",
            "540,   ,OPEN,P1",
            "540,M1,open,P1",
            "540,M1,pause",
            "540,M1,OPEN,p1",
            "540,M1,OPEN,P0",
            "540,M1,OPEN,P5",
            "540,M1,UNKNOWN,P1",
            "  00540  ,  M1  ,  OPEN  ,  P2  ",
            "600,M1,CLOSE",
        ]
        expected = [
            {"ticket_id": "M1", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
        ]
        check(stream, expected, "test_malformed_lines_filtering")

    @test
    def test_exact_sla_boundaries():
        # P1 limit is 240 business minutes.
        # Opened Monday 540.
        # Boundary 1: Pauses at 780 (used 240). Must NOT breach.
        # Boundary 2: Pauses at 781 (used 241). Must breach at 781.
        stream = [
            "540,T_exact,OPEN,P1",
            "780,T_exact,PAUSE",
            "540,T_breach,OPEN,P1",
            "781,T_breach,PAUSE",
            "1000,OTHER,OPEN,P4",
        ]
        expected = [
            {"ticket_id": "OTHER", "priority": "P4", "used_minutes": 0, "breached": False, "breached_at": None, "status": "running"},
            {"ticket_id": "T_breach", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "paused"},
            {"ticket_id": "T_exact", "priority": "P1", "used_minutes": 240, "breached": False, "breached_at": None, "status": "paused"},
        ]
        check(stream, expected, "test_exact_sla_boundaries")

    @test
    def test_breach_across_overnight_hours():
        # Opened Monday 780 (13:00) with P1 (240 mins).
        # Business day ends at 1020. [780, 1020) = 240 mins.
        # Overnight [1020, 1980) is non-business. Used remains 240.
        # Tuesday 1980 (09:00) is 241st business minute. Breaches at 1981!
        stream = [
            "780,T_overnight,OPEN,P1",
            "2000,T_overnight,CLOSE",
        ]
        expected = [
            {"ticket_id": "T_overnight", "priority": "P1", "used_minutes": 260, "breached": True, "breached_at": 1981, "status": "closed"}
        ]
        check(stream, expected, "test_breach_across_overnight_hours")

    @test
    def test_breach_across_weekend_and_holiday():
        # Friday 13:00 is 6540. Friday business ends at 6780. (240 mins used)
        # Saturday (day 5) & Sunday (day 6) are weekend.
        # Monday (day 7: 10080..11519) is holiday.
        # Tuesday (day 8): 11520 + 540 = 12060.
        # Breach occurs on 1st minute of Tuesday: 12061!
        stream = [
            "6540,T_long,OPEN,P1",
            "12120,T_long,PAUSE",
            "10500,*,HOLIDAY",
        ]
        expected = [
            {"ticket_id": "T_long", "priority": "P1", "used_minutes": 300, "breached": True, "breached_at": 12061, "status": "paused"}
        ]
        check(stream, expected, "test_breach_across_weekend_and_holiday")

    @test
    def test_all_priority_limits():
        # Test exact boundary (ok) and boundary+1 (breach) for P1, P2, P3, P4
        stream = [
            "540,TP1_ok,OPEN,P1",
            "780,TP1_ok,PAUSE",
            "540,TP1_br,OPEN,P1",
            "781,TP1_br,PAUSE",

            "540,TP2_ok,OPEN,P2",
            "1020,TP2_ok,PAUSE",
            "540,TP2_br,OPEN,P2",
            "1981,TP2_br,PAUSE",

            "540,TP3_ok,OPEN,P3",
            "3900,TP3_ok,PAUSE",
            "540,TP3_br,OPEN,P3",
            "4861,TP3_br,PAUSE",

            "540,TP4_ok,OPEN,P4",
            "6780,TP4_ok,PAUSE",
            "540,TP4_br,OPEN,P4",
            "10621,TP4_br,PAUSE",
        ]
        expected = [
            {"ticket_id": "TP1_br", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "paused"},
            {"ticket_id": "TP1_ok", "priority": "P1", "used_minutes": 240, "breached": False, "breached_at": None, "status": "paused"},
            {"ticket_id": "TP2_br", "priority": "P2", "used_minutes": 481, "breached": True, "breached_at": 1981, "status": "paused"},
            {"ticket_id": "TP2_ok", "priority": "P2", "used_minutes": 480, "breached": False, "breached_at": None, "status": "paused"},
            {"ticket_id": "TP3_br", "priority": "P3", "used_minutes": 1441, "breached": True, "breached_at": 4861, "status": "paused"},
            {"ticket_id": "TP3_ok", "priority": "P3", "used_minutes": 1440, "breached": False, "breached_at": None, "status": "paused"},
            {"ticket_id": "TP4_br", "priority": "P4", "used_minutes": 2401, "breached": True, "breached_at": 10621, "status": "paused"},
            {"ticket_id": "TP4_ok", "priority": "P4", "used_minutes": 2400, "breached": False, "breached_at": None, "status": "paused"},
        ]
        check(stream, expected, "test_all_priority_limits")

    @test
    def test_state_transition_table_all_cells():
        # Tests all 24 cells in the state-transition table
        stream = [
            # NOT_OPENED: PRIORITY, PAUSE, RESUME, CLOSE, REOPEN are ignored; ticket never appears
            "100,T_NO,PRIORITY,P1",
            "101,T_NO,PAUSE",
            "102,T_NO,RESUME",
            "103,T_NO,CLOSE",
            "104,T_NO,REOPEN",

            # RUNNING ignored: OPEN, RESUME, REOPEN; valid: PRIORITY, PAUSE
            "540,T_RUN,OPEN,P2",
            "550,T_RUN,OPEN,P1",        # ignored
            "560,T_RUN,RESUME",         # ignored
            "570,T_RUN,REOPEN",         # ignored
            "580,T_RUN,PRIORITY,P3",     # valid: prio -> P3
            "600,T_RUN,CLOSE",          # RUNNING -> CLOSED

            # PAUSED ignored: OPEN, PAUSE, REOPEN; valid: PRIORITY, RESUME, CLOSE
            "540,T_PAU,OPEN,P2",
            "560,T_PAU,PAUSE",          # -> PAUSED
            "570,T_PAU,OPEN,P1",        # ignored
            "580,T_PAU,PAUSE",          # ignored
            "590,T_PAU,REOPEN",         # ignored
            "600,T_PAU,PRIORITY,P4",     # valid: prio -> P4
            "610,T_PAU,CLOSE",          # PAUSED -> CLOSED

            # PAUSED -> RESUME
            "540,T_RES,OPEN,P2",
            "560,T_RES,PAUSE",
            "580,T_RES,RESUME",         # -> RUNNING
            "600,T_RES,CLOSE",

            # CLOSED ignored: PRIORITY, PAUSE, RESUME, CLOSE
            "540,T_CLO,OPEN,P2",
            "560,T_CLO,CLOSE",          # -> CLOSED
            "570,T_CLO,PRIORITY,P1",     # ignored
            "580,T_CLO,PAUSE",          # ignored
            "590,T_CLO,RESUME",         # ignored
            "600,T_CLO,CLOSE",          # ignored
            "620,T_CLO,REOPEN",         # CLOSED -> RUNNING, prio kept (P2), used continues
            "640,T_CLO,CLOSE",
        ]
        expected = [
            {"ticket_id": "T_CLO", "priority": "P2", "used_minutes": 40, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T_PAU", "priority": "P4", "used_minutes": 20, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T_RES", "priority": "P2", "used_minutes": 40, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T_RUN", "priority": "P3", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
        ]
        check(stream, expected, "test_state_transition_table_all_cells")

    @test
    def test_reopen_and_open_from_closed():
        # 1. OPEN on CLOSED clears breach, resets used, changes priority
        # 2. REOPEN on CLOSED keeps breach, continues used, keeps priority
        # 3. OPEN on CLOSED breaches again in second lifecycle
        stream = [
            # T_clear: breach at 781, closed at 790, OPEN at 800 with P3 -> clears breach, used resets
            "540,T_clear,OPEN,P1",
            "790,T_clear,CLOSE",
            "800,T_clear,OPEN,P3",
            "850,T_clear,CLOSE",

            # T_keep: breach at 781, closed at 790, REOPEN at 800 -> keeps breach 781, used continues
            "540,T_keep,OPEN,P1",
            "790,T_keep,CLOSE",
            "800,T_keep,REOPEN",
            "850,T_keep,CLOSE",

            # T_rebreach: breach at 781, closed at 800. OPEN at 850 with P1.
            # Runs Mon [850, 1020) = 170 mins. Needs 70 mins Tue: 1980 + 70 = 2050 (limit 240).
            # Breaches at 2051! Pauses at 2100 (used = 170 + 120 = 290).
            "540,T_rebreach,OPEN,P1",
            "800,T_rebreach,CLOSE",
            "850,T_rebreach,OPEN,P1",
            "2100,T_rebreach,PAUSE",
        ]
        expected = [
            {"ticket_id": "T_clear", "priority": "P3", "used_minutes": 50, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T_keep", "priority": "P1", "used_minutes": 300, "breached": True, "breached_at": 781, "status": "closed"},
            {"ticket_id": "T_rebreach", "priority": "P1", "used_minutes": 290, "breached": True, "breached_at": 2051, "status": "paused"},
        ]
        check(stream, expected, "test_reopen_and_open_from_closed")

    @test
    def test_dynamic_priority_changes():
        # A: Lower priority causing immediate breach while RUNNING
        # B: Lower priority causing immediate breach while PAUSED
        # C: Priority raise at exact breach minute PREVENTS breach
        # D: Priority raise AFTER breach is STICKY (does not clear breach)
        stream = [
            # A: used 300 at 840. Change P2 -> P1 causes immediate breach at 840!
            "540,T_imm_run,OPEN,P2",
            "840,T_imm_run,PRIORITY,P1",
            "840,T_imm_run,PAUSE",

            # B: paused at 840 (used 300). At 870 change to P1 causes immediate breach at 870!
            "540,T_imm_pau,OPEN,P2",
            "840,T_imm_pau,PAUSE",
            "870,T_imm_pau,PRIORITY,P1",

            # C: at 781 used is 241. Priority changed to P2 at 781 prevents breach!
            "540,T_prevent,OPEN,P1",
            "781,T_prevent,PRIORITY,P2",
            "781,T_prevent,PAUSE",

            # D: at 781 breached under P1. At 800 priority changed to P4. Breach remains sticky!
            "540,T_sticky,OPEN,P1",
            "800,T_sticky,PRIORITY,P4",
            "800,T_sticky,PAUSE",

            "900,T_anchor,OPEN,P1",
        ]
        expected = [
            {"ticket_id": "T_anchor", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "running"},
            {"ticket_id": "T_imm_pau", "priority": "P1", "used_minutes": 300, "breached": True, "breached_at": 870, "status": "paused"},
            {"ticket_id": "T_imm_run", "priority": "P1", "used_minutes": 300, "breached": True, "breached_at": 840, "status": "paused"},
            {"ticket_id": "T_prevent", "priority": "P2", "used_minutes": 241, "breached": False, "breached_at": None, "status": "paused"},
            {"ticket_id": "T_sticky", "priority": "P4", "used_minutes": 260, "breached": True, "breached_at": 781, "status": "paused"},
        ]
        check(stream, expected, "test_dynamic_priority_changes")

    @test
    def test_ties_and_stream_order():
        # Events at same minute must preserve input order
        stream = [
            # OPEN then PAUSE at 540 -> ticket is PAUSED during 540..600, used = 0
            "540,T_tie_pau,OPEN,P1",
            "540,T_tie_pau,PAUSE",
            "600,T_tie_pau,CLOSE",

            # OPEN then PAUSE then RESUME at 540 -> ticket is RUNNING during 540..600, used = 60
            "540,T_tie_run,OPEN,P1",
            "540,T_tie_run,PAUSE",
            "540,T_tie_run,RESUME",
            "600,T_tie_run,CLOSE",

            # Multiple PRIORITY at 781: P2 then P1 -> final is P1, breaches at 781!
            "540,T_tie_prio1,OPEN,P1",
            "781,T_tie_prio1,PRIORITY,P2",
            "781,T_tie_prio1,PRIORITY,P1",
            "781,T_tie_prio1,CLOSE",

            # Multiple PRIORITY at 781: P1 then P2 -> final is P2, does NOT breach!
            "540,T_tie_prio2,OPEN,P1",
            "781,T_tie_prio2,PRIORITY,P1",
            "781,T_tie_prio2,PRIORITY,P2",
            "781,T_tie_prio2,CLOSE",
        ]
        expected = [
            {"ticket_id": "T_tie_pau", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T_tie_prio1", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "closed"},
            {"ticket_id": "T_tie_prio2", "priority": "P2", "used_minutes": 241, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T_tie_run", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
        ]
        check(stream, expected, "test_ties_and_stream_order")

    @test
    def test_out_of_order_events():
        # Complete shuffled stream
        stream = [
            "800,ORD,CLOSE",
            "540,ORD,OPEN,P1",
            "700,ORD,RESUME",
            "600,ORD,PAUSE",
        ]
        expected = [
            {"ticket_id": "ORD", "priority": "P1", "used_minutes": 160, "breached": False, "breached_at": None, "status": "closed"}
        ]
        check(stream, expected, "test_out_of_order_events")

    @test
    def test_now_definition_subtleties():
        # 1. Invalid ticket event sets 'now'
        # 2. HOLIDAY lines never set 'now'
        # 3. Malformed lines never set 'now'
        stream = [
            "540,T_now1,OPEN,P1",
            "600,T_now1,PAUSE",
            "2000,INVALID_TICKET,PAUSE",       # invalid transition, ticket not opened, sets now=2000
            "99999,*,HOLIDAY",                 # holiday does not affect now
            "88888,T_now1,INVALID_EVENT,P1",   # malformed line ignored completely
        ]
        # At now = 2000, T_now1 was paused at 600, used = 60
        expected = [
            {"ticket_id": "T_now1", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}
        ]
        check(stream, expected, "test_now_definition_subtleties")

    @test
    def test_ticket_id_case_sensitivity_and_code_point_sorting():
        stream = [
            "540,t1,OPEN,P1",
            "600,t1,CLOSE",
            "540,T1,OPEN,P2",
            "600,T1,CLOSE",
            "540,T10,OPEN,P3",
            "600,T10,CLOSE",
            "540,T2,OPEN,P4",
            "600,T2,CLOSE",
            "540,10,OPEN,P1",
            "600,10,CLOSE",
            "540,2,OPEN,P1",
            "600,2,CLOSE",
            "540,a,OPEN,P1",
            "600,a,CLOSE",
            "540,A,OPEN,P1",
            "600,A,CLOSE",
        ]
        # ASCII order: "10" < "2" < "A" < "T1" < "T10" < "T2" < "a" < "t1"
        expected = [
            {"ticket_id": "10", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "2", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "A", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T1", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T10", "priority": "P3", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T2", "priority": "P4", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "a", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "t1", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
        ]
        check(stream, expected, "test_ticket_id_case_sensitivity_and_code_point_sorting")

    @test
    def test_non_business_hours_events():
        # Opened at Monday 00:00 (minute 0). Runs until 600.
        # Business hours start at 540. Used = [540, 600) = 60.
        # Opened Saturday 12:00 (7920). Closed next Monday 10:00 (10680).
        # Business hours Monday [10620, 10680) = 60.
        stream = [
            "0,T_zero,OPEN,P1",
            "600,T_zero,CLOSE",
            "7920,T_sat,OPEN,P1",
            "10680,T_sat,CLOSE",
        ]
        # At now = 10680, T_zero was closed at 600.
        expected = [
            {"ticket_id": "T_sat", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T_zero", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
        ]
        check(stream, expected, "test_non_business_hours_events")

    @test
    def test_iterator_input():
        # Ensure solution accepts generator/iterator
        def gen():
            yield "540,G,OPEN,P1"
            yield "600,G,CLOSE"

        expected = [
            {"ticket_id": "G", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
        ]
        check(gen(), expected, "test_iterator_input")

    @test
    def test_duplicate_holidays_and_boundary_holidays():
        # Declaring day 0 holiday twice: at minute 0 and minute 1439
        stream = [
            "0,*,HOLIDAY",
            "1439,*,HOLIDAY",
            "540,T_hol,OPEN,P1",
            "2040,T_hol,CLOSE",   # Tuesday 10:00. Day 0 has 0 mins. Tue [1980, 2040) = 60.
        ]
        expected = [
            {"ticket_id": "T_hol", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
        ]
        check(stream, expected, "test_duplicate_holidays_and_boundary_holidays")

    @test
    def test_large_minute_performance():
        # Large minute span: week 50001 (day 50001 is Monday)
        # 50001 * 1440 + 540 = 72001980 (Monday 09:00).
        # P1 limit 240: reaches limit at 72001980 + 240 = 72002220.
        # Breaches at 72002221! Closed at 72002300 (used = 320).
        # Friday of same week: day 50005. 50005 * 1440 + 960 = 72008160 (Fri 16:00).
        # Runs 60m Fri to 72008220. Next Mon 09:00 is 72012060.
        # Breaches at 72012060 + 180 + 1 = 72012241! Closed at 72012300 (used = 300).
        stream = [
            "0,*,HOLIDAY",
            "72001980,PERF_1,OPEN,P1",
            "72002300,PERF_1,CLOSE",
            "72008160,PERF_2,OPEN,P1",
            "72012300,PERF_2,CLOSE",
            "999999999,*,HOLIDAY",
        ]
        expected = [
            {"ticket_id": "PERF_1", "priority": "P1", "used_minutes": 320, "breached": True, "breached_at": 72002221, "status": "closed"},
            {"ticket_id": "PERF_2", "priority": "P1", "used_minutes": 300, "breached": True, "breached_at": 72012241, "status": "closed"},
        ]
        check(stream, expected, "test_large_minute_performance")

    print("\n" + "=" * 50)
    print(f"Summary: {passed} passed, {failed} failed")
    print("=" * 50)
    if failed == 0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()