import solution
import sys
import time


def assert_sla_result(actual, expected, test_name=""):
    """Validates the output structure, types, ordering, and exact values."""
    if not isinstance(actual, list):
        raise AssertionError(
            f"[{test_name}] Output must be a list, got {type(actual)}"
        )

    if len(actual) != len(expected):
        raise AssertionError(
            f"[{test_name}] Length mismatch: expected {len(expected)} tickets, got {len(actual)}.\n"
            f"Actual: {actual}\nExpected: {expected}"
        )

    required_keys = {
        "ticket_id",
        "priority",
        "used_minutes",
        "breached",
        "breached_at",
        "status",
    }

    # Verify code-point ascending order of ticket_ids
    actual_ids = [t["ticket_id"] for t in actual]
    if actual_ids != sorted(actual_ids):
        raise AssertionError(
            f"[{test_name}] Tickets are not sorted in code-point order: {actual_ids}"
        )

    for i, (act, exp) in enumerate(zip(actual, expected)):
        if not isinstance(act, dict):
            raise AssertionError(
                f"[{test_name}] Item {i} must be a dict, got {type(act)}"
            )

        act_keys = set(act.keys())
        if act_keys != required_keys:
            raise AssertionError(
                f"[{test_name}] Item {i} keys mismatch. Expected {required_keys}, got {act_keys}"
            )

        # Type validations
        if not isinstance(act["ticket_id"], str):
            raise AssertionError(
                f"[{test_name}] Item {i} ticket_id must be str, got {type(act['ticket_id'])}"
            )
        if not isinstance(act["priority"], str):
            raise AssertionError(
                f"[{test_name}] Item {i} priority must be str, got {type(act['priority'])}"
            )
        if (
            not isinstance(act["used_minutes"], int)
            or type(act["used_minutes"]) is bool
        ):
            raise AssertionError(
                f"[{test_name}] Item {i} used_minutes must be int, got {type(act['used_minutes'])}"
            )
        if not isinstance(act["breached"], bool):
            raise AssertionError(
                f"[{test_name}] Item {i} breached must be bool, got {type(act['breached'])}"
            )
        if act["breached_at"] is not None and (
            not isinstance(act["breached_at"], int)
            or type(act["breached_at"]) is bool
        ):
            raise AssertionError(
                f"[{test_name}] Item {i} breached_at must be int or None, got {type(act['breached_at'])}"
            )
        if not isinstance(act["status"], str):
            raise AssertionError(
                f"[{test_name}] Item {i} status must be str, got {type(act['status'])}"
            )

        # Value validations
        for key in required_keys:
            if act[key] != exp[key]:
                raise AssertionError(
                    f"[{test_name}] Ticket {exp['ticket_id']} field '{key}' mismatch: "
                    f"expected {exp[key]!r}, got {act[key]!r}\nFull actual: {act}\nFull expected: {exp}"
                )


def run_tests():
    total_checks = 0

    # -------------------------------------------------------------------------
    # 1. Specification Examples
    # -------------------------------------------------------------------------
    # Example 1
    stream = ["540,A,OPEN,P2", "600,A,CLOSE"]
    expected = [
        {
            "ticket_id": "A",
            "priority": "P2",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_sla_result(solution.compute_sla(stream), expected, "Example 1")
    total_checks += 1

    # Example 2
    stream = ["6720,B,OPEN,P1", "10680,B,PAUSE"]
    expected = [
        {
            "ticket_id": "B",
            "priority": "P1",
            "used_minutes": 120,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_sla_result(solution.compute_sla(stream), expected, "Example 2")
    total_checks += 1

    # Example 3
    stream = ["540,C,OPEN,P1", "900,C,CLOSE"]
    expected = [
        {
            "ticket_id": "C",
            "priority": "P1",
            "used_minutes": 360,
            "breached": True,
            "breached_at": 781,
            "status": "closed",
        }
    ]
    assert_sla_result(solution.compute_sla(stream), expected, "Example 3")
    total_checks += 1

    # Example 4
    stream = [
        "540,D,OPEN,P3",
        "2040,D,PAUSE",
        "open,D,RESUME",
        "2100,D,RESUME,P1",
        "5,*,HOLIDAY",
    ]
    expected = [
        {
            "ticket_id": "D",
            "priority": "P3",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        }
    ]
    assert_sla_result(solution.compute_sla(stream), expected, "Example 4")
    total_checks += 1

    # -------------------------------------------------------------------------
    # 2. Empty stream, only malformed, only holidays, or never opened
    # -------------------------------------------------------------------------
    assert_sla_result(solution.compute_sla([]), [], "Empty stream")
    total_checks += 1

    assert_sla_result(
        solution.compute_sla(["", "   ", "\n"]),
        [],
        "Whitespace only lines",
    )
    total_checks += 1

    assert_sla_result(
        solution.compute_sla(["540,*,HOLIDAY", "1000,*,HOLIDAY"]),
        [],
        "Holidays only (no ticket events -> [])",
    )
    total_checks += 1

    assert_sla_result(
        solution.compute_sla(
            [
                "invalid,line",
                "-5,T1,OPEN,P1",
                "540,*,OPEN,P1",
                "540,A,UNKNOWN",
            ]
        ),
        [],
        "Malformed only lines",
    )
    total_checks += 1

    # Well-formed ticket events, but ticket never had a valid OPEN
    assert_sla_result(
        solution.compute_sla(
            [
                "600,T1,PAUSE",
                "700,T1,RESUME",
                "800,T1,PRIORITY,P1",
                "900,T1,CLOSE",
                "1000,T1,REOPEN",
            ]
        ),
        [],
        "Never opened ticket ignored in output",
    )
    total_checks += 1

    # -------------------------------------------------------------------------
    # 3. Comprehensive State-Transition Table Coverage (All 24 Cells)
    # States: NOT_OPENED, RUNNING, PAUSED, CLOSED
    # Events: OPEN, PRIORITY, PAUSE, RESUME, CLOSE, REOPEN
    # -------------------------------------------------------------------------
    # Ticket T_NO: NOT_OPENED transitions
    # - PRIORITY, PAUSE, RESUME, CLOSE, REOPEN are ignored, ticket never in output.
    # Ticket T_RUN: RUNNING transitions
    # - OPEN: ignored
    # - PRIORITY: priority updated
    # - RESUME: ignored
    # - REOPEN: ignored
    # - PAUSE: -> PAUSED
    # Ticket T_PAU: PAUSED transitions
    # - OPEN: ignored
    # - PAUSE: ignored
    # - REOPEN: ignored
    # - PRIORITY: priority updated
    # - RESUME: -> RUNNING
    # - CLOSE: -> CLOSED
    # Ticket T_CLS: CLOSED transitions
    # - PRIORITY: ignored
    # - PAUSE: ignored
    # - RESUME: ignored
    # - CLOSE: ignored
    # - REOPEN: -> RUNNING (used continues, breach kept)
    # - OPEN: -> RUNNING (used resets, breach cleared)
    stream_transitions = [
        # T_NO operations (all ignored)
        "540,T_NO,PRIORITY,P1",
        "541,T_NO,PAUSE",
        "542,T_NO,RESUME",
        "543,T_NO,CLOSE",
        "544,T_NO,REOPEN",
        # T_RUN operations
        "540,T_RUN,OPEN,P3",  # to RUNNING
        "550,T_RUN,OPEN,P1",  # RUNNING + OPEN -> ignored, priority stays P3
        "560,T_RUN,RESUME",  # RUNNING + RESUME -> ignored
        "570,T_RUN,REOPEN",  # RUNNING + REOPEN -> ignored
        "580,T_RUN,PRIORITY,P2",  # RUNNING + PRIORITY -> priority becomes P2
        "600,T_RUN,PAUSE",  # RUNNING + PAUSE -> to PAUSED
        # T_PAU operations
        "540,T_PAU,OPEN,P2",  # to RUNNING
        "550,T_PAU,PAUSE",  # to PAUSED (ran 10 mins: 540-550)
        "560,T_PAU,OPEN,P1",  # PAUSED + OPEN -> ignored
        "570,T_PAU,PAUSE",  # PAUSED + PAUSE -> ignored
        "580,T_PAU,REOPEN",  # PAUSED + REOPEN -> ignored
        "590,T_PAU,PRIORITY,P4",  # PAUSED + PRIORITY -> priority becomes P4
        "600,T_PAU,RESUME",  # PAUSED + RESUME -> to RUNNING
        "610,T_PAU,CLOSE",  # RUNNING + CLOSE -> to CLOSED (ran 10 mins: 600-610)
        # T_CLS operations
        "540,T_CLS,OPEN,P1",  # to RUNNING
        "550,T_CLS,PAUSE",  # to PAUSED
        "560,T_CLS,CLOSE",  # PAUSED + CLOSE -> to CLOSED
        "570,T_CLS,PRIORITY,P3",  # CLOSED + PRIORITY -> ignored
        "580,T_CLS,PAUSE",  # CLOSED + PAUSE -> ignored
        "590,T_CLS,RESUME",  # CLOSED + RESUME -> ignored
        "600,T_CLS,CLOSE",  # CLOSED + CLOSE -> ignored
    ]
    expected_transitions = [
        {
            "ticket_id": "T_CLS",
            "priority": "P1",
            "used_minutes": 10,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
        {
            "ticket_id": "T_PAU",
            "priority": "P4",
            "used_minutes": 20,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
        {
            "ticket_id": "T_RUN",
            "priority": "P2",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        },
    ]
    assert_sla_result(
        solution.compute_sla(stream_transitions),
        expected_transitions,
        "Transition table 24 cells",
    )
    total_checks += 1

    # -------------------------------------------------------------------------
    # 4. Exact SLA Boundaries (Used == Limit vs Used == Limit + 1)
    # -------------------------------------------------------------------------
    # Priority P1: Limit 240
    # Boundary: at 780, used = 240 <= 240 (NOT breached)
    # At 781, used = 241 > 240 (BREACHED at 781)
    stream_p1_boundary = [
        "540,P1_exact,OPEN,P1",
        "780,P1_exact,PAUSE",
        "540,P1_plus1,OPEN,P1",
        "781,P1_plus1,PAUSE",
    ]
    expected_p1_boundary = [
        {
            "ticket_id": "P1_exact",
            "priority": "P1",
            "used_minutes": 240,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        },
        {
            "ticket_id": "P1_plus1",
            "priority": "P1",
            "used_minutes": 241,
            "breached": True,
            "breached_at": 781,
            "status": "paused",
        },
    ]
    assert_sla_result(
        solution.compute_sla(stream_p1_boundary),
        expected_p1_boundary,
        "P1 SLA exact boundary",
    )
    total_checks += 1

    # Priority P2: Limit 480
    # Day 0 Monday: 540 to 1020 is 480 mins.
    # At 1020: used = 480 <= 480 (NOT breached).
    # Tuesday starts at 1440, business hours start at 1980.
    # At 1980: used = 480 <= 480 (NOT breached).
    # At 1981: used = 481 > 480 (BREACHED at 1981).
    stream_p2_boundary = [
        "540,P2_exact,OPEN,P2",
        "1020,P2_exact,PAUSE",
        "540,P2_plus1,OPEN,P2",
        "1981,P2_plus1,PAUSE",
    ]
    expected_p2_boundary = [
        {
            "ticket_id": "P2_exact",
            "priority": "P2",
            "used_minutes": 480,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        },
        {
            "ticket_id": "P2_plus1",
            "priority": "P2",
            "used_minutes": 481,
            "breached": True,
            "breached_at": 1981,
            "status": "paused",
        },
    ]
    assert_sla_result(
        solution.compute_sla(stream_p2_boundary),
        expected_p2_boundary,
        "P2 SLA exact boundary",
    )
    total_checks += 1

    # Priority P3: Limit 1440 (3 business days: Mon, Tue, Wed = 480*3 = 1440 mins)
    # Mon: 540..1020 (480)
    # Tue: 1980..2460 (480)
    # Wed: 3420..3900 (480) -> cumulative 1440 at 3900.
    # Thu business starts at 4860 (3*1440 + 540 = 4320 + 540 = 4860).
    # At 4860: used = 1440 <= 1440 (NOT breached).
    # At 4861: used = 1441 > 1440 (BREACHED at 4861).
    stream_p3_boundary = [
        "540,P3_exact,OPEN,P3",
        "4860,P3_exact,PAUSE",
        "540,P3_plus1,OPEN,P3",
        "4861,P3_plus1,PAUSE",
    ]
    expected_p3_boundary = [
        {
            "ticket_id": "P3_exact",
            "priority": "P3",
            "used_minutes": 1440,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        },
        {
            "ticket_id": "P3_plus1",
            "priority": "P3",
            "used_minutes": 1441,
            "breached": True,
            "breached_at": 4861,
            "status": "paused",
        },
    ]
    assert_sla_result(
        solution.compute_sla(stream_p3_boundary),
        expected_p3_boundary,
        "P3 SLA exact boundary",
    )
    total_checks += 1

    # Priority P4: Limit 2400 (5 business days: Mon..Fri = 480*5 = 2400 mins)
    # Friday ends at 5760 + 1020 = 6780. At 6780: used = 2400.
    # Weekend: Sat (day 5), Sun (day 6).
    # Next Monday (day 7) starts at 10080, business starts at 10620.
    # At 10620: used = 2400 <= 2400 (NOT breached).
    # At 10621: used = 2401 > 2400 (BREACHED at 10621).
    stream_p4_boundary = [
        "540,P4_exact,OPEN,P4",
        "10620,P4_exact,PAUSE",
        "540,P4_plus1,OPEN,P4",
        "10621,P4_plus1,PAUSE",
    ]
    expected_p4_boundary = [
        {
            "ticket_id": "P4_exact",
            "priority": "P4",
            "used_minutes": 2400,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        },
        {
            "ticket_id": "P4_plus1",
            "priority": "P4",
            "used_minutes": 2401,
            "breached": True,
            "breached_at": 10621,
            "status": "paused",
        },
    ]
    assert_sla_result(
        solution.compute_sla(stream_p4_boundary),
        expected_p4_boundary,
        "P4 SLA exact boundary",
    )
    total_checks += 1

    # -------------------------------------------------------------------------
    # 5. Priority Changes: Upgrades, Downgrades, Immediate Breach, Sticky Breach
    # -------------------------------------------------------------------------
    stream_priority = [
        # Case A: Priority upgrade at the very minute breach would occur prevents it
        "540,T_PREVENT,OPEN,P1",
        "781,T_PREVENT,PRIORITY,P2",  # P1 would breach at 781; P2 limit is 480; 241 <= 480 -> prevented!
        # Case B: Priority upgrade AFTER breach does not undo it (sticky breach)
        "540,T_STICKY,OPEN,P1",
        "782,T_STICKY,PRIORITY,P4",  # breached at 781; P4 limit 2400 does not clear it
        # Case C: Priority downgrade while PAUSED causes immediate breach
        "540,T_DOWN_PAUSE,OPEN,P2",
        "790,T_DOWN_PAUSE,PAUSE",  # ran 250 mins; paused at 790
        "850,T_DOWN_PAUSE,PRIORITY,P1",  # P1 limit 240 < 250 -> breaches immediately at 850!
        # Case D: Priority downgrade outside business hours causes breach at event minute
        "540,T_DOWN_OFFHOURS,OPEN,P2",
        "790,T_DOWN_OFFHOURS,PAUSE",  # ran 250 mins
        "1100,T_DOWN_OFFHOURS,PRIORITY,P1",  # minute 1100 is 18:20 (after hours); breaches at 1100!
        # Case E: Priority change on CLOSED ticket is ignored
        "540,T_CLOSED_PRIO,OPEN,P1",
        "600,T_CLOSED_PRIO,CLOSE",
        "700,T_CLOSED_PRIO,PRIORITY,P3",  # ignored!
    ]
    expected_priority = [
        {
            "ticket_id": "T_CLOSED_PRIO",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
        {
            "ticket_id": "T_DOWN_OFFHOURS",
            "priority": "P1",
            "used_minutes": 250,
            "breached": True,
            "breached_at": 1100,
            "status": "paused",
        },
        {
            "ticket_id": "T_DOWN_PAUSE",
            "priority": "P1",
            "used_minutes": 250,
            "breached": True,
            "breached_at": 850,
            "status": "paused",
        },
        {
            "ticket_id": "T_PREVENT",
            "priority": "P2",
            "used_minutes": 560,
            "breached": False,
            "breached_at": None,
            "status": "running",
        },  # ran 540 to 1100; business mins: [540,1020)=480; [1020,1100)=0 -> wait!
        # Let's verify T_PREVENT used_minutes:
        # "now" is max minute of stream = 1100.
        # T_PREVENT opened at 540, priority P2 at 781, running until 1100.
        # Monday business minutes are in [540, 1020).
        # T_PREVENT was RUNNING throughout [540, 1020) = 480 mins.
        # Between 1020 and 1100 are outside business hours, so 0 mins.
        # Total used_minutes = 480!
        # Limit of P2 is 480. 480 <= 480, so NOT breached!
        {
            "ticket_id": "T_STICKY",
            "priority": "P4",
            "used_minutes": 480,
            "breached": True,
            "breached_at": 781,
            "status": "running",
        },
    ]
    expected_priority[3]["used_minutes"] = 480
    assert_sla_result(
        solution.compute_sla(stream_priority),
        expected_priority,
        "Priority changes and breach stickiness",
    )
    total_checks += 1

    # -------------------------------------------------------------------------
    # 6. REOPEN vs OPEN from CLOSED
    # - REOPEN continues used time, keeps breach and priority
    # - OPEN from CLOSED resets used to 0, clears breach, sets priority
    # -------------------------------------------------------------------------
    stream_reopen_vs_open = [
        # Ticket 1: REOPEN
        "540,T_REOPEN,OPEN,P1",
        "781,T_REOPEN,CLOSE",  # breached at 781 (used 241)
        "800,T_REOPEN,REOPEN",  # continues from 241
        "830,T_REOPEN,PAUSE",  # ran 800 to 830: 30 mins -> total 271 mins
        # Ticket 2: OPEN from CLOSED
        "540,T_RESET,OPEN,P1",
        "781,T_RESET,CLOSE",  # breached at 781 (used 241)
        "800,T_RESET,OPEN,P2",  # resets used to 0, clears breach, priority P2
        "830,T_RESET,PAUSE",  # ran 800 to 830: 30 mins
    ]
    expected_reopen_vs_open = [
        {
            "ticket_id": "T_REOPEN",
            "priority": "P1",
            "used_minutes": 271,
            "breached": True,
            "breached_at": 781,
            "status": "paused",
        },
        {
            "ticket_id": "T_RESET",
            "priority": "P2",
            "used_minutes": 30,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        },
    ]
    assert_sla_result(
        solution.compute_sla(stream_reopen_vs_open),
        expected_reopen_vs_open,
        "REOPEN vs OPEN from CLOSED",
    )
    total_checks += 1

    # -------------------------------------------------------------------------
    # 7. Calendar: Boundaries, Overnights, Weekends, Holidays
    # -------------------------------------------------------------------------
    # Boundary checks:
    # 539 is non-business, 540 is business.
    # 1019 is business, 1020 is non-business.
    # Friday 6779 is business, 6780 is non-business.
    # Saturday (7200..8639) non-business, Sunday (8640..10079) non-business.
    # Monday 10619 is non-business, 10620 is business.
    stream_calendar = [
        # Opens before business hours, closes at start: 0 business mins
        "420,T_EARLY,OPEN,P1",
        "540,T_EARLY,CLOSE",
        # Opens at 1019, closes at 1021: 1 business min (minute 1019)
        "1019,T_EOD,OPEN,P1",
        "1021,T_EOD,CLOSE",
        # Opens on Friday 16:59 (6779), closes Monday 09:01 (10621)
        # Business mins: 6779 (1 min) + 10620 (1 min) = 2 mins
        "6779,T_WKND,OPEN,P1",
        "10621,T_WKND,CLOSE",
        # Ticket running across holiday:
        # Opens Friday 16:59 (6779) P1.
        # Next Monday (Day 7, starts at 10080) is declared holiday!
        # Breach would need 240 mins on Monday (10620 + 240 = 10860).
        # But Monday is a holiday! So it breaches on Tuesday (Day 8)!
        # Tuesday business starts at 8*1440 + 540 = 11520 + 540 = 12060.
        # Breach at 12060 + 240 = 12300!
        "6779,T_HOLI,OPEN,P1",
        "10500,*,HOLIDAY",  # 10500 // 1440 = 7 (Monday is holiday)
        "12350,T_HOLI,CLOSE",  # Closed Tuesday at 12350
    ]
    # T_HOLI used mins: 1 min (Fri) + 0 (Mon) + (12350 - 12060) = 1 + 290 = 291 mins.
    # Breached at 12300!
    expected_calendar = [
        {
            "ticket_id": "T_EARLY",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
        {
            "ticket_id": "T_EOD",
            "priority": "P1",
            "used_minutes": 1,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
        {
            "ticket_id": "T_HOLI",
            "priority": "P1",
            "used_minutes": 291,
            "breached": True,
            "breached_at": 12300,
            "status": "closed",
        },
        {
            "ticket_id": "T_WKND",
            "priority": "P1",
            "used_minutes": 2,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
    ]
    assert_sla_result(
        solution.compute_sla(stream_calendar),
        expected_calendar,
        "Calendar boundaries, weekends, holidays",
    )
    total_checks += 1

    # -------------------------------------------------------------------------
    # 8. Same-Minute Ordering (Stable Sort) and Out-Of-Order Processing
    # -------------------------------------------------------------------------
    stream_order = [
        # Out-of-order: CLOSE arrives before OPEN
        "600,T_OOO,CLOSE",
        "540,T_OOO,OPEN,P2",
        # Same minute ties: PAUSE then RESUME -> RUNNING
        "600,T_TIE1,RESUME",
        "600,T_TIE1,PAUSE",
        "540,T_TIE1,OPEN,P1",
        # (Wait, stream order at 600: RESUME first, then PAUSE!
        # At 540 OPEN -> RUNNING. At 600: RESUME is ignored, then PAUSE -> PAUSED!)
        # Same minute ties: CLOSE then OPEN from closed -> RUNNING with 0 used
        "600,T_TIE2,OPEN,P2",
        "600,T_TIE2,CLOSE",
        "540,T_TIE2,OPEN,P1",
        # (Stream order at 600: OPEN,P2 first (ignored while RUNNING), then CLOSE -> CLOSED!)
        # Let's explicitly test CLOSE then OPEN:
        "540,T_TIE3,OPEN,P1",
        "600,T_TIE3,CLOSE",
        "600,T_TIE3,OPEN,P3",
        # (Stream order at 600: CLOSE -> CLOSED, then OPEN,P3 -> RUNNING with 0 used!)
    ]
    expected_order = [
        {
            "ticket_id": "T_OOO",
            "priority": "P2",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
        {
            "ticket_id": "T_TIE1",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "paused",
        },
        {
            "ticket_id": "T_TIE2",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
        {
            "ticket_id": "T_TIE3",
            "priority": "P3",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        },
    ]
    assert_sla_result(
        solution.compute_sla(stream_order),
        expected_order,
        "Same minute ties and out-of-order events",
    )
    total_checks += 1

    # -------------------------------------------------------------------------
    # 9. Definition of 'now'
    # - Largest minute among all well-formed ticket events
    # - Invalid transitions DO advance 'now'
    # - Malformed lines DO NOT advance 'now'
    # - HOLIDAY lines DO NOT advance 'now'
    # -------------------------------------------------------------------------
    stream_now = [
        "540,T_VALID,OPEN,P1",
        # Event at 700 is an invalid transition for T_GHOST (never opened), but well-formed ticket event
        "700,T_GHOST,CLOSE",
        # Event at 800 is malformed (ticket ID * for PAUSE)
        "800,*,PAUSE",
        # Event at 900 is HOLIDAY: valid holiday, but never affects 'now'
        "900,*,HOLIDAY",
        # Event at 1000 is malformed (OPEN missing priority)
        "1000,T_VALID,OPEN",
    ]
    # 'now' must be 700!
    # At 700, T_VALID has run from 540 to 700 = 160 business mins.
    # T_GHOST is not in output because it never had a valid OPEN.
    expected_now = [
        {
            "ticket_id": "T_VALID",
            "priority": "P1",
            "used_minutes": 160,
            "breached": False,
            "breached_at": None,
            "status": "running",
        }
    ]
    assert_sla_result(
        solution.compute_sla(stream_now), expected_now, "Definition of 'now'"
    )
    total_checks += 1

    # -------------------------------------------------------------------------
    # 10. Malformed Lines (Comprehensive Rejection) & Whitespace Trimming
    # -------------------------------------------------------------------------
    stream_malformed = [
        # Valid ticket with leading/trailing spaces and leading zeros
        "  00540  ,  T_CLEAN  ,  OPEN  ,  P1  ",
        # Valid close at 600
        "600,T_CLEAN,CLOSE",
        # Malformed variants that must be completely ignored
        "",
        "   ",
        "540",
        "540,A",
        "540,A,OPEN",
        "540,A,OPEN,P1,extra",
        "540,A,PRIORITY",
        "540,A,PRIORITY,P1,extra",
        "540,A,PAUSE,extra",
        "540,A,RESUME,extra",
        "540,A,CLOSE,extra",
        "540,A,REOPEN,extra",
        "540,*,HOLIDAY,extra",
        "-540,A,OPEN,P1",
        "+540,A,OPEN,P1",
        "540.5,A,OPEN,P1",
        "abc,A,OPEN,P1",
        "540,,OPEN,P1",
        "540,   ,OPEN,P1",
        "540,*,OPEN,P1",
        "540,*,PRIORITY,P1",
        "540,*,CLOSE",
        "540,A,HOLIDAY",
        "540,A,open,P1",
        "540,A,priority,P1",
        "540,A,pause",
        "540,A,resume",
        "540,A,close",
        "540,A,reopen",
        "540,*,holiday",
        "540,A,OPEN,p1",
        "540,A,OPEN,P5",
        "540,A,OPEN,P0",
        "540,A,OPEN,HIGH",
        "540,A,PRIORITY,p2",
        "540,A,PRIORITY,P5",
        "540,A,UNKNOWN,P1",
        "540,A,UNKNOWN",
    ]
    expected_malformed = [
        {
            "ticket_id": "T_CLEAN",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        }
    ]
    assert_sla_result(
        solution.compute_sla(stream_malformed),
        expected_malformed,
        "Malformed line rejection and whitespace trimming",
    )
    total_checks += 1

    # -------------------------------------------------------------------------
    # 11. Code-Point Ordering & Case Sensitivity
    # '10' < '2' < 'A' < 'T1' < 'T10' < 'T2' < 'a' < 't1'
    # -------------------------------------------------------------------------
    stream_order_ids = [
        "540,t1,OPEN,P1",
        "540,T1,OPEN,P1",
        "540,T10,OPEN,P1",
        "540,T2,OPEN,P1",
        "540,10,OPEN,P1",
        "540,2,OPEN,P1",
        "540,a,OPEN,P1",
        "540,A,OPEN,P1",
        "600,10,CLOSE",
        "600,2,CLOSE",
        "600,A,CLOSE",
        "600,T1,CLOSE",
        "600,T10,CLOSE",
        "600,T2,CLOSE",
        "600,a,CLOSE",
        "600,t1,CLOSE",
    ]
    expected_order_ids = [
        {
            "ticket_id": "10",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
        {
            "ticket_id": "2",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
        {
            "ticket_id": "A",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
        {
            "ticket_id": "T1",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
        {
            "ticket_id": "T10",
            "priority": "P1",
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
            "status": "closed",
        },
        {
            "ticket_id": "a",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
        {
            "ticket_id": "t1",
            "priority": "P1",
            "used_minutes": 60,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
    ]
    assert_sla_result(
        solution.compute_sla(stream_order_ids),
        expected_order_ids,
        "Code-point ordering and case-sensitivity",
    )
    total_checks += 1

    # -------------------------------------------------------------------------
    # 12. Multi-Week Ticket with Multiple Holidays
    # Week 0 Mon 540 OPEN P4 (limit 2400 mins = 5 full business days)
    # Week 0 Mon is Holiday!
    # Week 0 Thu is Holiday!
    # Week 0 business days: Tue (480), Wed (480), Fri (480) = 1440 mins.
    # Week 1: Mon (480) -> total 1920 mins.
    # Week 1: Tue (480) -> total 2400 mins (Tue ends at 8*1440 + 1020 = 12540).
    # Week 1: Wed (Day 9) business starts at 9*1440 + 540 = 13500.
    # Breach occurs at 13501!
    # Ticket paused at 13600:
    # Used minutes = 2400 + (13600 - 13500) = 2500 mins.
    # -------------------------------------------------------------------------
    stream_multiweek = [
        "540,T_MULTI,OPEN,P4",
        "540,*,HOLIDAY",  # Day 0 Holiday
        "4500,*,HOLIDAY",  # 4500 // 1440 = 3 (Day 3 Thu Holiday)
        "13600,T_MULTI,PAUSE",
    ]
    expected_multiweek = [
        {
            "ticket_id": "T_MULTI",
            "priority": "P4",
            "used_minutes": 2500,
            "breached": True,
            "breached_at": 13501,
            "status": "paused",
        }
    ]
    assert_sla_result(
        solution.compute_sla(stream_multiweek),
        expected_multiweek,
        "Multi-week run with multiple holidays",
    )
    total_checks += 1

    # -------------------------------------------------------------------------
    # 13. Large Minute Performance & Anti-Naive-Looping Check
    # Minutes up to 900,000,000. Naive minute-by-minute simulation will timeout.
    # Day 625002 is a Monday (625002 % 7 == 0).
    # Day starts at 625002 * 1440 = 900,002,880.
    # Monday 09:00 is 900,002,880 + 540 = 900,003,420.
    # Monday 15:00 is 900,002,880 + 900 = 900,003,780.
    # P1 limit: 240 mins.
    # Breaches at 900,003,420 + 241 = 900,003,661!
    # Used minutes at 900,003,780 = 360 mins.
    # -------------------------------------------------------------------------
    # Include 100 holiday declarations on distant days to test calendar efficiency
    holiday_lines = [f"{day * 1440},*,HOLIDAY" for day in range(100, 200)]
    stream_large = (
        holiday_lines
        + [
            "900003420,T_BIG,OPEN,P1",
            "900003780,T_BIG,CLOSE",
        ]
    )
    expected_large = [
        {
            "ticket_id": "T_BIG",
            "priority": "P1",
            "used_minutes": 360,
            "breached": True,
            "breached_at": 900003661,
            "status": "closed",
        }
    ]
    start_time = time.time()
    actual_large = solution.compute_sla(stream_large)
    duration = time.time() - start_time
    if duration > 5.0:
        raise AssertionError(
            f"Performance failure: Large minute test took {duration:.2f}s (must be < 5s)"
        )
    assert_sla_result(
        actual_large, expected_large, "Large minute performance and correctness"
    )
    total_checks += 1

    # -------------------------------------------------------------------------
    # 14. Minute 0 and Zero-Used Boundary Cases
    # -------------------------------------------------------------------------
    stream_zero = [
        # Opened at minute 0 (Monday 00:00), closed at minute 0
        "0,T_ZERO,OPEN,P1",
        "0,T_ZERO,CLOSE",
        # Opened at 540 (Monday 09:00), 'now' is 540 -> used_minutes must be 0
        "540,T_NOW540,OPEN,P2",
    ]
    expected_zero = [
        {
            "ticket_id": "T_NOW540",
            "priority": "P2",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "running",
        },
        {
            "ticket_id": "T_ZERO",
            "priority": "P1",
            "used_minutes": 0,
            "breached": False,
            "breached_at": None,
            "status": "closed",
        },
    ]
    assert_sla_result(
        solution.compute_sla(stream_zero),
        expected_zero,
        "Minute 0 and zero used minutes at now",
    )
    total_checks += 1

    print(
        f"All {total_checks} test suites passed successfully! Adversarial verification complete."
    )
    sys.exit(0)


if __name__ == "__main__":
    try:
        run_tests()
    except Exception as e:
        print(f"TEST FAILED: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)