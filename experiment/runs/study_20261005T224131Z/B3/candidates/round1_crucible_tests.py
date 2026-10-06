import sys
import solution


def validate_record_types(record, context=""):
    expected_keys = {
        "ticket_id",
        "priority",
        "used_minutes",
        "breached",
        "breached_at",
        "status",
    }
    actual_keys = set(record.keys())
    assert (
        actual_keys == expected_keys
    ), f"{context}: keys mismatch: {actual_keys} != {expected_keys}"

    assert isinstance(
        record["ticket_id"], str
    ), f"{context}: ticket_id not str"
    assert (
        record["priority"] in {"P1", "P2", "P3", "P4"}
    ), f"{context}: invalid priority {record['priority']}"
    assert type(record["used_minutes"]) is int and not isinstance(
        record["used_minutes"], bool
    ), f"{context}: used_minutes not int"
    assert record["used_minutes"] >= 0, f"{context}: used_minutes negative"
    assert isinstance(record["breached"], bool), f"{context}: breached not bool"
    if record["breached"]:
        assert type(record["breached_at"]) is int and not isinstance(
            record["breached_at"], bool
        ), f"{context}: breached_at not int when breached=True"
    else:
        assert (
            record["breached_at"] is None
        ), f"{context}: breached_at not None when breached=False"
    assert record["status"] in {
        "running",
        "paused",
        "closed",
    }, f"{context}: invalid status {record['status']}"


def assert_sla(stream, expected, test_name):
    res = solution.compute_sla(stream)
    assert type(res) is list, f"{test_name}: return type must be list, got {type(res)}"
    assert len(res) == len(
        expected
    ), f"{test_name}: expected {len(expected)} records, got {len(res)}: {res}"
    for i, (act, exp) in enumerate(zip(res, expected)):
        validate_record_types(act, f"{test_name}[{i}]")
        assert act == exp, (
            f"{test_name} failed at index {i}:\n"
            f"  Expected: {exp}\n"
            f"  Actual:   {act}"
        )


def test_spec_examples():
    # Example 1
    s1 = ["540,A,OPEN,P2", "600,A,CLOSE"]
    e1 = [
        {
            "ticket_id": "A",
            "priority": "P2",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_sla(s1, e1, "Spec Example 1")

    # Example 2
    s2 = ["6720,B,OPEN,P1", "10680,B,PAUSE"]
    e2 = [
        {
            "ticket_id": "B",
            "priority": "P1",
            "used_minutes": 120,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_sla(s2, e2, "Spec Example 2")

    # Example 3
    s3 = ["540,C,OPEN,P1", "900,C,CLOSE"]
    e3 = [
        {
            "ticket_id": "C",
            "priority": "P1",
            "used_minutes": 360,
            "breached": True,
            "breached_at": 781,
            "status": "closed",
        }
    ]
    assert_sla(s3, e3, "Spec Example 3")

    # Example 4
    s4 = [
        "540,D,OPEN,P3",
        "2040,D,PAUSE",
        "open,D,RESUME",
        "2100,D,RESUME,P1",
        "5,*,HOLIDAY",
    ]
    e4 = [
        {
            "ticket_id": "D",
            "priority": "P3",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_sla(s4, e4, "Spec Example 4")


def test_empty_and_trivial():
    assert_sla([], [], "Empty stream")
    assert_sla(["", "   ", "\t\n", "\r\n"], [], "Whitespace stream")
    assert_sla(["540,*,HOLIDAY", "2000,*,HOLIDAY"], [], "Holidays only")
    assert_sla(
        [
            "invalid,line",
            "100",
            "100,200,300,400,500",
            "100,A,FOO",
        ],
        [],
        "Malformed lines only",
    )
    # Tickets never validly opened
    assert_sla(
        [
            "540,U,PRIORITY,P1",
            "600,U,PAUSE",
            "700,U,RESUME",
            "800,U,CLOSE",
            "900,U,REOPEN",
        ],
        [],
        "Unopened ticket ignored transitions only",
    )


def test_state_machine_24_transitions():
    # 1. NOT_OPENED transitions:
    # PRIORITY, PAUSE, RESUME, CLOSE, REOPEN are ignored on NOT_OPENED
    s_not_opened = [
        "500,U,PRIORITY,P1",
        "510,U,PAUSE",
        "520,U,RESUME",
        "530,U,CLOSE",
        "540,U,REOPEN",
        "600,V,OPEN,P2",  # valid ticket to establish 'now'
    ]
    e_not_opened = [
        {
            "ticket_id": "V",
            "priority": "P2",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_sla(s_not_opened, e_not_opened, "NOT_OPENED invalid transitions")

    # 2. RUNNING transitions:
    # RUNNING -> OPEN is ignored
    s_run_open = ["540,T,OPEN,P1", "600,T,OPEN,P2"]
    e_run_open = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_sla(s_run_open, e_run_open, "RUNNING + OPEN ignored")

    # RUNNING -> RESUME and REOPEN are ignored
    s_run_res_reop = [
        "540,T,OPEN,P1",
        "560,T,RESUME",
        "580,T,REOPEN",
        "600,T,PAUSE",
    ]
    e_run_res_reop = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_sla(s_run_res_reop, e_run_res_reop, "RUNNING + RESUME/REOPEN ignored")

    # RUNNING -> PRIORITY updates priority
    s_run_prio = ["540,T,OPEN,P1", "600,T,PRIORITY,P3"]
    e_run_prio = [
        {
            "ticket_id": "T",
            "priority": "P3",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_sla(s_run_prio, e_run_prio, "RUNNING + PRIORITY")

    # RUNNING -> PAUSE -> PAUSED
    s_run_pause = ["540,T,OPEN,P1", "600,T,PAUSE"]
    e_run_pause = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_sla(s_run_pause, e_run_pause, "RUNNING + PAUSE")

    # RUNNING -> CLOSE -> CLOSED
    s_run_close = ["540,T,OPEN,P1", "600,T,CLOSE"]
    e_run_close = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_sla(s_run_close, e_run_close, "RUNNING + CLOSE")

    # 3. PAUSED transitions:
    # PAUSED -> OPEN, PAUSE, REOPEN ignored
    s_p_ign = [
        "540,T,OPEN,P1",
        "560,T,PAUSE",
        "570,T,OPEN,P2",
        "580,T,PAUSE",
        "590,T,REOPEN",
    ]
    e_p_ign = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 20,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_sla(s_p_ign, e_p_ign, "PAUSED + OPEN/PAUSE/REOPEN ignored")

    # PAUSED -> PRIORITY updates priority
    s_p_prio = ["540,T,OPEN,P1", "560,T,PAUSE", "590,T,PRIORITY,P4"]
    e_p_prio = [
        {
            "ticket_id": "T",
            "priority": "P4",
            "used_minutes": 20,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_sla(s_p_prio, e_p_prio, "PAUSED + PRIORITY")

    # PAUSED -> RESUME -> RUNNING
    s_p_res = ["540,T,OPEN,P1", "560,T,PAUSE", "590,T,RESUME"]
    e_p_res = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 20,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_sla(s_p_res, e_p_res, "PAUSED + RESUME")

    # PAUSED -> CLOSE -> CLOSED
    s_p_close = ["540,T,OPEN,P1", "560,T,PAUSE", "590,T,CLOSE"]
    e_p_close = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 20,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_sla(s_p_close, e_p_close, "PAUSED + CLOSE")

    # 4. CLOSED transitions:
    # CLOSED -> PRIORITY, PAUSE, RESUME, CLOSE ignored
    s_c_ign = [
        "540,T,OPEN,P1",
        "560,T,CLOSE",
        "570,T,PRIORITY,P3",
        "580,T,PAUSE",
        "590,T,RESUME",
        "600,T,CLOSE",
    ]
    e_c_ign = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 20,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_sla(s_c_ign, e_c_ign, "CLOSED + PRIORITY/PAUSE/RESUME/CLOSE ignored")

    # CLOSED -> REOPEN: used continues, priority kept, breach kept
    s_c_reopen = [
        "540,T,OPEN,P1",
        "560,T,CLOSE",
        "600,T,REOPEN",
    ]
    e_c_reopen = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 20,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_sla(s_c_reopen, e_c_reopen, "CLOSED + REOPEN")

    # CLOSED -> OPEN: used resets to 0, priority set, breach cleared
    s_c_open = [
        "540,T,OPEN,P1",
        "800,T,CLOSE",  # Breached at 781
        "900,T,OPEN,P2",  # Resets used to 0, breach cleared, priority P2
    ]
    e_c_open = [
        {
            "ticket_id": "T",
            "priority": "P2",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_sla(s_c_open, e_c_open, "CLOSED + OPEN resets used and breach")

    # CLOSED with existing breach -> REOPEN keeps breach!
    s_c_reopen_breached = [
        "540,T,OPEN,P1",
        "800,T,CLOSE",  # Breached at 781
        "900,T,REOPEN",
    ]
    e_c_reopen_breached = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 260,
            "breached": True,
            "breached_at": 781,
            "status": "running",
        }
    ]
    assert_sla(s_c_reopen_breached, e_c_reopen_breached, "CLOSED + REOPEN keeps breach")


def test_exact_sla_boundaries():
    # P1 (limit 240)
    # Exactly 240 minutes: 540 to 779 inclusive. At 780, used is 240 -> NOT breached
    s_p1_exact = ["540,T,OPEN,P1", "780,T,PAUSE"]
    e_p1_exact = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 240,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_sla(s_p1_exact, e_p1_exact, "P1 boundary: 240 not breached")

    # 241 minutes: At 781, used is 241 -> BREACHED at 781
    s_p1_breach = ["540,T,OPEN,P1", "781,T,PAUSE"]
    e_p1_breach = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 241,
            "breached": True,
            "breached_at": 781,
            "status": "paused",
        }
    ]
    assert_sla(s_p1_breach, e_p1_breach, "P1 boundary: 241 breached at 781")

    # P2 (limit 480)
    # Day 0 (Monday) has 480 business minutes (540..1019).
    # Tuesday 09:00 is minute 1980 (1*1440 + 540).
    # At 1980, used time is 480 -> NOT breached
    s_p2_exact = ["540,T,OPEN,P2", "1980,T,PAUSE"]
    e_p2_exact = [
        {
            "ticket_id": "T",
            "priority": "P2",
            "used_minutes": 480,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_sla(s_p2_exact, e_p2_exact, "P2 boundary: 480 not breached at 1980")

    # At 1981, used time is 481 -> BREACHED at 1981
    s_p2_breach = ["540,T,OPEN,P2", "1981,T,PAUSE"]
    e_p2_breach = [
        {
            "ticket_id": "T",
            "priority": "P2",
            "used_minutes": 481,
            "breached": True,
            "breached_at": 1981,
            "status": "paused",
        }
    ]
    assert_sla(s_p2_breach, e_p2_breach, "P2 boundary: 481 breached at 1981")

    # P3 (limit 1440 = 3 days * 480)
    # Mon, Tue, Wed = 3 days. Thursday 09:00 is minute 3*1440 + 540 = 4860.
    # At 4860, used is 1440 -> NOT breached
    s_p3_exact = ["540,T,OPEN,P3", "4860,T,PAUSE"]
    e_p3_exact = [
        {
            "ticket_id": "T",
            "priority": "P3",
            "used_minutes": 1440,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_sla(s_p3_exact, e_p3_exact, "P3 boundary: 1440 not breached at 4860")

    # At 4861, used is 1441 -> BREACHED at 4861
    s_p3_breach = ["540,T,OPEN,P3", "4861,T,PAUSE"]
    e_p3_breach = [
        {
            "ticket_id": "T",
            "priority": "P3",
            "used_minutes": 1441,
            "breached": True,
            "breached_at": 4861,
            "status": "paused",
        }
    ]
    assert_sla(s_p3_breach, e_p3_breach, "P3 boundary: 1441 breached at 4861")

    # P4 (limit 2400 = 5 days * 480)
    # Mon to Fri = 5 days. Next Monday 09:00 is week 1 Monday, minute 7*1440 + 540 = 10620.
    # At 10620, used is 2400 -> NOT breached
    s_p4_exact = ["540,T,OPEN,P4", "10620,T,PAUSE"]
    e_p4_exact = [
        {
            "ticket_id": "T",
            "priority": "P4",
            "used_minutes": 2400,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_sla(s_p4_exact, e_p4_exact, "P4 boundary: 2400 not breached at 10620")

    # At 10621, used is 2401 -> BREACHED at 10621
    s_p4_breach = ["540,T,OPEN,P4", "10621,T,PAUSE"]
    e_p4_breach = [
        {
            "ticket_id": "T",
            "priority": "P4",
            "used_minutes": 2401,
            "breached": True,
            "breached_at": 10621,
            "status": "paused",
        }
    ]
    assert_sla(s_p4_breach, e_p4_breach, "P4 boundary: 2401 breached at 10621")


def test_priority_changes_and_breach_timing():
    # Priority raise at exact breach minute (781) PREVENTS breach
    s_raise_save = ["540,T,OPEN,P1", "781,T,PRIORITY,P2"]
    e_raise_save = [
        {
            "ticket_id": "T",
            "priority": "P2",
            "used_minutes": 241,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_sla(
        s_raise_save, e_raise_save, "PRIORITY raise at breach minute prevents breach"
    )

    # Priority downgrade while RUNNING causing immediate breach
    s_down_run = ["540,T,OPEN,P2", "800,T,PRIORITY,P1"]
    e_down_run = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 260,
            "breached": True,
            "breached_at": 800,
            "status": "running",
        }
    ]
    assert_sla(
        s_down_run, e_down_run, "PRIORITY downgrade while RUNNING causes breach"
    )

    # Priority downgrade while PAUSED causing immediate breach
    s_down_pause = ["540,T,OPEN,P2", "850,T,PAUSE", "900,T,PRIORITY,P1"]
    e_down_pause = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 310,
            "breached": True,
            "breached_at": 900,
            "status": "paused",
        }
    ]
    assert_sla(
        s_down_pause, e_down_pause, "PRIORITY downgrade while PAUSED causes breach"
    )

    # Priority downgrade during non-business hours (e.g. 18:00 = minute 1080)
    s_down_non_biz = ["540,T,OPEN,P2", "1020,T,PAUSE", "1080,T,PRIORITY,P1"]
    e_down_non_biz = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 480,
            "breached": True,
            "breached_at": 1080,
            "status": "paused",
        }
    ]
    assert_sla(
        s_down_non_biz,
        e_down_non_biz,
        "PRIORITY downgrade during non-biz hours causes breach",
    )

    # Sticky breach: Priority raise AFTER breach does NOT undo breach
    s_raise_after = ["540,T,OPEN,P1", "800,T,PRIORITY,P4"]
    e_raise_after = [
        {
            "ticket_id": "T",
            "priority": "P4",
            "used_minutes": 260,
            "breached": True,
            "breached_at": 781,
            "status": "running",
        }
    ]
    assert_sla(
        s_raise_after, e_raise_after, "PRIORITY raise after breach does not undo breach"
    )

    # CLOSE at exact minute 781 breaches at 781
    s_close_breach = ["540,T,OPEN,P1", "781,T,CLOSE"]
    e_close_breach = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 241,
            "breached": True,
            "breached_at": 781,
            "status": "closed",
        }
    ]
    assert_sla(
        s_close_breach, e_close_breach, "CLOSE at exact 781 results in breached_at=781"
    )

    # CLOSE at 780 prevents breach even if stream ends later
    s_close_prevent = [
        "540,T,OPEN,P1",
        "780,T,CLOSE",
        "1000,OTHER,OPEN,P1",
    ]
    e_close_prevent = [
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
            "used_minutes": 240,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
    ]
    assert_sla(s_close_prevent, e_close_prevent, "CLOSE at 780 prevents breach")


def test_reopen_and_multiple_breaches():
    # Ticket cleared by OPEN, then breaches again under second lifecycle
    # Lifecycle 1: 540 to 800 (breached at 781)
    # Closed at 800.
    # Lifecycle 2: OPEN P1 at 1000 (Mon 16:40).
    # Runs 1000..1019 = 20 biz minutes on Monday.
    # Tuesday 09:00 is 1980.
    # Needs 241 - 20 = 221 biz minutes on Tuesday.
    # 1980 + 221 = 2201 -> breaches at 2201!
    s_re_breach = ["540,T,OPEN,P1", "800,T,CLOSE", "1000,T,OPEN,P1", "2250,T,PAUSE"]
    e_re_breach = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 20 + (2250 - 1980),  # 20 + 270 = 290
            "breached": True,
            "breached_at": 2201,
            "status": "paused",
        }
    ]
    assert_sla(s_re_breach, e_re_breach, "Ticket cleared by OPEN breaches again later")


def test_definition_of_now():
    # Ignored ticket event sets 'now'
    # RESUME on RUNNING is ignored, but sets now=1000
    s_now_ign = ["540,T,OPEN,P1", "1000,T,RESUME"]
    e_now_ign = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 460,
            "breached": True,
            "breached_at": 781,
            "status": "running",
        }
    ]
    assert_sla(s_now_ign, e_now_ign, "Ignored event sets 'now'")

    # Event on unopened ticket sets 'now', but unopened ticket not in output
    s_unopened_now = ["540,T,OPEN,P1", "600,UNOPENED,CLOSE"]
    e_unopened_now = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_sla(s_unopened_now, e_unopened_now, "Unopened ticket sets 'now'")

    # HOLIDAY lines NEVER affect 'now'
    s_hol_now = ["540,T,OPEN,P1", "100000,*,HOLIDAY"]
    e_hol_now = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_sla(s_hol_now, e_hol_now, "HOLIDAY never affects 'now'")

    # Malformed lines NEVER affect 'now'
    s_mal_now = ["540,T,OPEN,P1", "999999,MALFORMED,EXTRA,FIELDS,HERE"]
    e_mal_now = [
        {
            "ticket_id": "T",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_sla(s_mal_now, e_mal_now, "Malformed line never affects 'now'")


def test_ordering_and_ties():
    # Out of order events in stream
    s_ooo = [
        "700,A,PAUSE",
        "1000,A,CLOSE",
        "540,A,OPEN,P1",
        "800,A,RESUME",
    ]
    # Trace:
    # 540: OPEN P1 -> RUNNING
    # 700: PAUSE -> PAUSED (used = 160)
    # 800: RESUME -> RUNNING (needs 81 more min: 800 + 81 - 1 = 880, breach at 881)
    # 1000: CLOSE -> CLOSED (used = 160 + 200 = 360)
    e_ooo = [
        {
            "ticket_id": "A",
            "priority": "P1",
            "used_minutes": 360,
            "breached": True,
            "breached_at": 881,
            "status": "closed",
        }
    ]
    assert_sla(s_ooo, e_ooo, "Out-of-order events processed chronologically")

    # Ties at the same minute: stable order preserved
    # 1. OPEN then PAUSE at 540 -> PAUSED
    s_tie1 = ["540,A,OPEN,P1", "540,A,PAUSE"]
    e_tie1 = [
        {
            "ticket_id": "A",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_sla(s_tie1, e_tie1, "Tie: OPEN then PAUSE")

    # 2. PAUSE then OPEN at 540 -> PAUSE ignored on NOT_OPENED -> RUNNING
    s_tie2 = ["540,A,PAUSE", "540,A,OPEN,P1"]
    e_tie2 = [
        {
            "ticket_id": "A",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_sla(s_tie2, e_tie2, "Tie: PAUSE then OPEN")

    # 3. Priority changes at same minute
    s_tie3 = ["540,A,OPEN,P1", "540,A,PRIORITY,P2", "540,A,PRIORITY,P3"]
    e_tie3 = [
        {
            "ticket_id": "A",
            "priority": "P3",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_sla(s_tie3, e_tie3, "Tie: multiple PRIORITY updates")


def test_calendar_and_holidays():
    # Ticket opened on weekend: Saturday 12:00 (day 5, minute 5*1440 + 720 = 7920)
    # Week 0 Monday to Friday = days 0..4.
    # Saturday is day 5.
    # Next Monday 09:00 is day 7, minute 7*1440 + 540 = 10620.
    # Ticket runs on Monday: 241 business minutes -> breach at 10620 + 241 = 10861!
    s_weekend = [
        "7920,W,OPEN,P1",
        "10900,W,PAUSE",
    ]
    e_weekend = [
        {
            "ticket_id": "W",
            "priority": "P1",
            "used_minutes": 10900 - 10620,  # 280
            "breached": True,
            "breached_at": 10861,
            "status": "paused",
        }
    ]
    assert_sla(s_weekend, e_weekend, "Weekend open: business hours start Monday 09:00")

    # Ticket spanning holiday declared at end of stream
    # Week 0 Friday 16:30 (minute 4*1440 + 990 = 6750).
    # Friday 16:30 to 17:00 (6780) = 30 minutes.
    # Saturday (day 5), Sunday (day 6): 0 biz min.
    # Monday (day 7) declared holiday by "10080,*,HOLIDAY" -> 0 biz min.
    # Tuesday (day 8) starts 09:00 (8*1440 + 540 = 12060).
    # P2 limit = 480. Needs 481 - 30 = 451 biz min on Tuesday.
    # 12060 + 451 - 1 = 12510 (451st minute). Breach at 12511!
    # Ticket closes at Tuesday 17:00 (12540). Total used = 30 + 480 = 510.
    s_holiday_span = [
        "6750,H,OPEN,P2",
        "12540,H,CLOSE",
        "10080,*,HOLIDAY",  # Day 7 (Monday) is holiday
        "10100,*,HOLIDAY",  # Duplicate holiday on day 7
    ]
    e_holiday_span = [
        {
            "ticket_id": "H",
            "priority": "P2",
            "used_minutes": 510,
            "breached": True,
            "breached_at": 12511,
            "status": "closed",
        }
    ]
    assert_sla(
        s_holiday_span,
        e_holiday_span,
        "Holiday spanning weekend and declared at end of stream",
    )


def test_malformed_lines_comprehensive():
    malformed_lines = [
        "",  # empty
        "   ",  # spaces
        "\t",  # tab
        "540",  # 1 field
        "540,A",  # 2 fields
        "540,A,OPEN",  # OPEN with 3 fields
        "540,A,PRIORITY",  # PRIORITY with 3 fields
        "540,A,PAUSE,P1",  # PAUSE with 4 fields
        "540,A,RESUME,P1",  # RESUME with 4 fields
        "540,A,CLOSE,P1",  # CLOSE with 4 fields
        "540,A,REOPEN,P1",  # REOPEN with 4 fields
        "540,*,HOLIDAY,P1",  # HOLIDAY with 4 fields
        "540,A,OPEN,P1,EXTRA",  # 5 fields
        "-540,A,OPEN,P1",  # negative minute
        "+540,A,OPEN,P1",  # plus sign
        "540.0,A,OPEN,P1",  # float minute
        "540a,A,OPEN,P1",  # letters in minute
        "5 40,A,OPEN,P1",  # space inside minute
        ",A,OPEN,P1",  # empty minute
        "540,,OPEN,P1",  # empty ticket ID
        "540,   ,OPEN,P1",  # whitespace ticket ID
        "540,*,OPEN,P1",  # * with OPEN
        "540,*,PAUSE",  # * with PAUSE
        "540,*,RESUME",  # * with RESUME
        "540,*,CLOSE",  # * with CLOSE
        "540,*,REOPEN",  # * with REOPEN
        "540,*,PRIORITY,P1",  # * with PRIORITY
        "540,A,HOLIDAY",  # HOLIDAY with non-*
        "540,**,HOLIDAY",  # HOLIDAY with **
        "540,A,open,P1",  # lowercase event
        "540,A,Pause",  # mixed case event
        "540,A,UNKNOWN,P1",  # unknown event
        "540,A,OPEN,p1",  # lowercase priority
        "540,A,OPEN,P5",  # invalid priority P5
        "540,A,OPEN,HIGH",  # invalid priority name
        "540,A,OPEN,",  # empty priority
        "540,A,OPEN,P1,",  # trailing comma -> 5 fields
    ]

    # Valid lines intermingled with all malformed lines
    # Leading zeros in minute and whitespace trimming around fields are VALID!
    stream = [
        "  00540  ,  A  ,  OPEN  ,  P1  ",  # valid: minute=540, id=A, OPEN, P1
    ]
    stream.extend(malformed_lines)
    stream.append("00600,A,CLOSE")  # valid: minute=600

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
    assert_sla(
        stream, expected, "Malformed lines ignored, whitespace and leading zeros valid"
    )


def test_output_sorting_and_types():
    # Tickets sorted by code-point order: "T1" < "T10" < "T2" < "t1"
    stream = [
        "540,T2,OPEN,P1",
        "540,T10,OPEN,P2",
        "540,T1,OPEN,P3",
        "540,t1,OPEN,P4",
    ]
    res = solution.compute_sla(stream)
    ticket_ids = [r["ticket_id"] for r in res]
    expected_ids = ["T1", "T10", "T2", "t1"]
    assert (
        ticket_ids == expected_ids
    ), f"Sorting failed: expected {expected_ids}, got {ticket_ids}"


def test_large_span_and_large_timestamp():
    # Large timestamp to ensure the solution does not allocate arrays of size `minute`
    # or iterate minute by minute from 0 to 1,000,000,000.
    # 1000000000 // 1440 = 694444. 694444 % 7 = 4 (Friday).
    # 1000000000 % 1440 = 640 (10:40 AM).
    # 640 is in [540, 1020), so minute 1,000,000,000 is on a Friday during business hours!
    stream = [
        "1000000000,LARGE,OPEN,P1",
        "1000000060,LARGE,CLOSE",
    ]
    expected = [
        {
            "ticket_id": "LARGE",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_sla(stream, expected, "Large timestamp (1 billion) handled efficiently")

    # Ticket spanning across 1000 days (1,440,000 minutes)
    # Day 0 Monday 09:00 (minute 540) to Day 1000 (minute 1440000).
    # 1000 days = 142 weeks + 6 days.
    # Total business days = 142 * 5 + 5 = 715 days = 343,200 biz min.
    # P1 limit = 240. Breached at 781!
    stream_span = [
        "540,BIG,OPEN,P1",
        "1440000,BIG,CLOSE",
    ]
    expected_span = [
        {
            "ticket_id": "BIG",
            "priority": "P1",
            "used_minutes": 343200,
            "breached": True,
            "breached_at": 781,
            "status": "closed",
        }
    ]
    assert_sla(
        stream_span, expected_span, "Large minute span computed without timeout"
    )


def run_all_tests():
    tests = [
        ("Spec Examples", test_spec_examples),
        ("Empty and Trivial", test_empty_and_trivial),
        ("State Machine (24 Transitions)", test_state_machine_24_transitions),
        ("Exact SLA Boundaries", test_exact_sla_boundaries),
        (
            "Priority Changes & Breach Timing",
            test_priority_changes_and_breach_timing,
        ),
        ("Reopen & Multiple Breaches", test_reopen_and_multiple_breaches),
        ("Definition of 'now'", test_definition_of_now),
        ("Ordering & Ties", test_ordering_and_ties),
        ("Calendar & Holidays", test_calendar_and_holidays),
        ("Malformed Lines Comprehensive", test_malformed_lines_comprehensive),
        ("Output Sorting & Types", test_output_sorting_and_types),
        ("Large Span & Performance", test_large_span_and_large_timestamp),
    ]

    passed = 0
    failed = 0
    print("=" * 70)
    print("RUNNING ADVERSARIAL TEST SUITE FOR compute_sla")
    print("=" * 70)

    for name, test_fn in tests:
        try:
            test_fn()
            print(f"  [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}")
            print(f"         Error: {e}")
            failed += 1

    print("=" * 70)
    print(
        f"TOTAL TESTS: {len(tests)} | PASSED: {passed} | FAILED: {failed}"
    )
    print("=" * 70)

    if failed == 0:
        print("ALL TESTS PASSED SUCCESSFULLY!")
        sys.exit(0)
    else:
        print(f"TEST SUITE FAILED with {failed} failure(s).")
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()