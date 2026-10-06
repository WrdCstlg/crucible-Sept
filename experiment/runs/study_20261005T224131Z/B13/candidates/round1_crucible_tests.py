import solution
import sys


def validate_schema(res):
    """Validate that the output satisfies all schema constraints."""
    if not isinstance(res, list):
        return False, f"Expected list, got {type(res).__name__}"
    for idx, d in enumerate(res):
        if not isinstance(d, dict):
            return False, f"Item {idx} is not a dict: {type(d).__name__}"
        expected_keys = {
            "ticket_id",
            "priority",
            "used_minutes",
            "breached",
            "breached_at",
            "status",
        }
        if set(d.keys()) != expected_keys:
            return (
                False,
                f"Item {idx} keys mismatch: {set(d.keys())} != {expected_keys}",
            )
        if not isinstance(d["ticket_id"], str):
            return False, f"Item {idx} ticket_id is not str"
        if d["priority"] not in {"P1", "P2", "P3", "P4"}:
            return False, f"Item {idx} invalid priority: {d['priority']}"
        if type(d["used_minutes"]) is not int:
            return (
                False,
                f"Item {idx} used_minutes is not int: {type(d['used_minutes']).__name__}",
            )
        if type(d["breached"]) is not bool:
            return (
                False,
                f"Item {idx} breached is not bool: {type(d['breached']).__name__}",
            )
        if d["breached"]:
            if type(d["breached_at"]) is not int:
                return (
                    False,
                    f"Item {idx} breached_at must be int when breached: {d['breached_at']}",
                )
        else:
            if d["breached_at"] is not None:
                return (
                    False,
                    f"Item {idx} breached_at must be None when not breached: {d['breached_at']}",
                )
        if d["status"] not in {"running", "paused", "closed"}:
            return False, f"Item {idx} invalid status: {d['status']}"
    return True, ""


def run_tests():
    tests_passed = 0
    tests_failed = 0

    def assert_test(name, stream, expected):
        nonlocal tests_passed, tests_failed
        try:
            actual = solution.compute_sla(stream)
            schema_ok, schema_err = validate_schema(actual)
            if not schema_ok:
                print(f"[FAIL] {name}: Schema violation: {schema_err}")
                tests_failed += 1
                return
            if actual != expected:
                print(f"[FAIL] {name}")
                print(f"  Stream:   {stream}")
                print(f"  Expected: {expected}")
                print(f"  Actual:   {actual}")
                tests_failed += 1
            else:
                tests_passed += 1
        except Exception as e:
            print(f"[FAIL] {name}: Exception raised: {e}")
            import traceback

            traceback.print_exc()
            tests_failed += 1

    # -------------------------------------------------------------------------
    # 1. Specification Examples
    # -------------------------------------------------------------------------
    assert_test(
        "Spec Example 1: Basic lifecycle and format",
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

    assert_test(
        "Spec Example 2: Weekend exclusion",
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

    assert_test(
        "Spec Example 3: Exact breach time",
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

    assert_test(
        "Spec Example 4: Holiday declared at end, malformed lines ignored",
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

    # -------------------------------------------------------------------------
    # 2. Malformed lines and Empty Streams
    # -------------------------------------------------------------------------
    assert_test("Empty stream", [], [])

    assert_test(
        "Only malformed lines",
        [
            "",
            "   ",
            "\t\n",
            "540",
            "540,T1",
            "540,T1,OPEN",
            "540,T1,PRIORITY",
            "540,T1,OPEN,P1,EXTRA",
            "540,T1,PAUSE,P1",
            "540,T1,RESUME,P1",
            "540,T1,CLOSE,P1",
            "540,T1,REOPEN,P1",
            "540,*,HOLIDAY,EXTRA",
            "540,T1,OPEN,P5",
            "540,T1,OPEN,p1",
            "540,T1,open,P1",
            "540,T1,START,P1",
            "540,T1,STOP",
            "-540,T1,OPEN,P1",
            "+540,T1,OPEN,P1",
            "540.0,T1,OPEN,P1",
            "abc,T1,OPEN,P1",
            "5 40,T1,OPEN,P1",
            ",T1,OPEN,P1",
            "540,,OPEN,P1",
            "540,   ,OPEN,P1",
            "540,*,OPEN,P1",
            "540,*,PAUSE",
            "540,*,CLOSE",
            "540,*,PRIORITY,P1",
            "540,*,RESUME",
            "540,*,REOPEN",
            "540,T1,HOLIDAY",
            "540,,HOLIDAY",
            "540,**,HOLIDAY",
            ",,,",
            ",,,,",
        ],
        [],
    )

    assert_test(
        "Only HOLIDAY lines (no ticket events -> return [])",
        ["0,*,HOLIDAY", "1440,*,HOLIDAY", "2880,*,HOLIDAY"],
        [],
    )

    assert_test(
        "Valid lines with whitespace trimming and leading zeros",
        ["  00540  ,  T1  ,  OPEN  ,  P1  ", "\t00600\t,\tT1\t,\tPAUSE\t"],
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

    # -------------------------------------------------------------------------
    # 3. Definition of 'now'
    # -------------------------------------------------------------------------
    assert_test(
        "'now' set by ignored event on ticket that never opened",
        [
            "540,T_VALID,OPEN,P1",
            "600,T_VALID,PAUSE",
            "1000,GHOST,PAUSE",  # Ignored transition, GHOST never opened; sets now=1000
        ],
        [
            {
                "ticket_id": "T_VALID",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    assert_test(
        "'now' is NOT affected by HOLIDAY line or malformed lines",
        [
            "540,T_VALID,OPEN,P1",
            "600,T_VALID,PAUSE",
            "99999,*,HOLIDAY",  # HOLIDAY does not affect now
            "88888,T_VALID,INVALID_EVENT",  # Malformed line does not affect now
        ],
        [
            {
                "ticket_id": "T_VALID",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    assert_test(
        "Ticket running up to 'now' when 'now' > last event on that ticket",
        [
            "540,T1,OPEN,P1",  # No more events for T1; runs up to now=700
            "600,T2,OPEN,P2",
            "700,T2,PAUSE",  # now = 700
        ],
        [
            {
                "ticket_id": "T1",
                "priority": "P1",
                "used_minutes": 160,
                "breached": False,
                "breached_at": None,
                "status": "running",
            },
            {
                "ticket_id": "T2",
                "priority": "P2",
                "used_minutes": 100,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
        ],
    )

    # -------------------------------------------------------------------------
    # 4. Output Ordering and Case Sensitivity
    # -------------------------------------------------------------------------
    assert_test(
        "ASCII string code-point sort order and case-sensitivity",
        [
            "540,t1,OPEN,P1",
            "540,T1,OPEN,P1",
            "540,T2,OPEN,P1",
            "540,T10,OPEN,P1",
            "540,2,OPEN,P1",
            "540,10,OPEN,P1",
        ],
        [
            {
                "ticket_id": "10",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            },
            {
                "ticket_id": "2",
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
                "ticket_id": "t1",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            },
        ],
    )

    # -------------------------------------------------------------------------
    # 5. State Transition Table Exhaustive Tests (All 24 Cells)
    # -------------------------------------------------------------------------

    # Cells 1-6: NOT_OPENED transitions
    # Only OPEN transitions to RUNNING. All other 5 events ignored, tickets never appear in output.
    assert_test(
        "State Transitions: NOT_OPENED with all events",
        [
            "500,NO_PRIO,PRIORITY,P1",  # Cell 2: ignored
            "500,NO_PAUSE,PAUSE",  # Cell 3: ignored
            "500,NO_RESUME,RESUME",  # Cell 4: ignored
            "500,NO_CLOSE,CLOSE",  # Cell 5: ignored
            "500,NO_REOPEN,REOPEN",  # Cell 6: ignored
            "540,OK_OPEN,OPEN,P1",  # Cell 1: valid
        ],
        [
            {
                "ticket_id": "OK_OPEN",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # Cells 7-12: RUNNING transitions
    assert_test(
        "State Transitions: RUNNING with all events",
        [
            # Anchor to set now=720
            "720,ANCHOR,OPEN,P1",
            # Cell 7: RUNNING + OPEN -> ignored! Priority remains P1, used continues
            "540,T_R_OPEN,OPEN,P1",
            "600,T_R_OPEN,OPEN,P2",
            "660,T_R_OPEN,PAUSE",
            # Cell 8: RUNNING + PRIORITY -> priority becomes P2
            "540,T_R_PRIO,OPEN,P1",
            "600,T_R_PRIO,PRIORITY,P2",
            "660,T_R_PRIO,PAUSE",
            # Cell 9: RUNNING + PAUSE -> to PAUSED
            "540,T_R_PAUSE,OPEN,P1",
            "600,T_R_PAUSE,PAUSE",
            # Cell 10: RUNNING + RESUME -> ignored! Runs continuously to 660
            "540,T_R_RES,OPEN,P1",
            "600,T_R_RES,RESUME",
            "660,T_R_RES,PAUSE",
            # Cell 11: RUNNING + CLOSE -> to CLOSED
            "540,T_R_CLOSE,OPEN,P1",
            "600,T_R_CLOSE,CLOSE",
            # Cell 12: RUNNING + REOPEN -> ignored! Runs continuously to 660
            "540,T_R_REOP,OPEN,P1",
            "600,T_R_REOP,REOPEN",
            "660,T_R_REOP,PAUSE",
        ],
        [
            {
                "ticket_id": "ANCHOR",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            },
            {
                "ticket_id": "T_R_CLOSE",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T_R_OPEN",
                "priority": "P1",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
            {
                "ticket_id": "T_R_PAUSE",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
            {
                "ticket_id": "T_R_PRIO",
                "priority": "P2",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
            {
                "ticket_id": "T_R_REOP",
                "priority": "P1",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
            {
                "ticket_id": "T_R_RES",
                "priority": "P1",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
        ],
    )

    # Cells 13-18: PAUSED transitions
    assert_test(
        "State Transitions: PAUSED with all events",
        [
            "780,ANCHOR,OPEN,P1",
            # Cell 13: PAUSED + OPEN -> ignored! Priority remains P1, stays paused
            "540,T_P_OPEN,OPEN,P1",
            "600,T_P_OPEN,PAUSE",
            "660,T_P_OPEN,OPEN,P2",
            "720,T_P_OPEN,RESUME",
            "780,T_P_OPEN,PAUSE",
            # Cell 14: PAUSED + PRIORITY -> priority becomes P2, stays paused
            "540,T_P_PRIO,OPEN,P1",
            "600,T_P_PRIO,PAUSE",
            "660,T_P_PRIO,PRIORITY,P2",
            # Cell 15: PAUSED + PAUSE -> ignored! Stays paused
            "540,T_P_PAUSE,OPEN,P1",
            "600,T_P_PAUSE,PAUSE",
            "660,T_P_PAUSE,PAUSE",
            # Cell 16: PAUSED + RESUME -> to RUNNING
            "540,T_P_RES,OPEN,P1",
            "600,T_P_RES,PAUSE",
            "660,T_P_RES,RESUME",
            "720,T_P_RES,PAUSE",
            # Cell 17: PAUSED + CLOSE -> to CLOSED
            "540,T_P_CLOSE,OPEN,P1",
            "600,T_P_CLOSE,PAUSE",
            "660,T_P_CLOSE,CLOSE",
            # Cell 18: PAUSED + REOPEN -> ignored! Stays paused
            "540,T_P_REOP,OPEN,P1",
            "600,T_P_REOP,PAUSE",
            "660,T_P_REOP,REOPEN",
            "720,T_P_REOP,RESUME",
            "780,T_P_REOP,PAUSE",
        ],
        [
            {
                "ticket_id": "ANCHOR",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            },
            {
                "ticket_id": "T_P_CLOSE",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T_P_OPEN",
                "priority": "P1",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
            {
                "ticket_id": "T_P_PAUSE",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
            {
                "ticket_id": "T_P_PRIO",
                "priority": "P2",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
            {
                "ticket_id": "T_P_REOP",
                "priority": "P1",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
            {
                "ticket_id": "T_P_RES",
                "priority": "P1",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
        ],
    )

    # Cells 19-24: CLOSED transitions
    assert_test(
        "State Transitions: CLOSED with all events",
        [
            "1020,ANCHOR,OPEN,P1",
            # Cell 19: CLOSED + OPEN -> to RUNNING, used resets to 0, breach cleared
            "540,T_C_OPEN,OPEN,P1",
            "900,T_C_OPEN,CLOSE",
            "960,T_C_OPEN,OPEN,P2",
            "1020,T_C_OPEN,PAUSE",
            # Cell 20: CLOSED + PRIORITY -> ignored! Priority remains P1
            "540,T_C_PRIO,OPEN,P1",
            "600,T_C_PRIO,CLOSE",
            "660,T_C_PRIO,PRIORITY,P2",
            # Cell 21: CLOSED + PAUSE -> ignored!
            "540,T_C_PAUSE,OPEN,P1",
            "600,T_C_PAUSE,CLOSE",
            "660,T_C_PAUSE,PAUSE",
            # Cell 22: CLOSED + RESUME -> ignored!
            "540,T_C_RES,OPEN,P1",
            "600,T_C_RES,CLOSE",
            "660,T_C_RES,RESUME",
            # Cell 23: CLOSED + CLOSE -> ignored!
            "540,T_C_CLOSE,OPEN,P1",
            "600,T_C_CLOSE,CLOSE",
            "660,T_C_CLOSE,CLOSE",
            # Cell 24: CLOSED + REOPEN -> to RUNNING, used continues, breach kept, priority kept
            "540,T_C_REOP,OPEN,P1",
            "900,T_C_REOP,CLOSE",
            "960,T_C_REOP,REOPEN",
            "1020,T_C_REOP,PAUSE",
        ],
        [
            {
                "ticket_id": "ANCHOR",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            },
            {
                "ticket_id": "T_C_CLOSE",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T_C_OPEN",
                "priority": "P2",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
            {
                "ticket_id": "T_C_PAUSE",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T_C_PRIO",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T_C_REOP",
                "priority": "P1",
                "used_minutes": 420,
                "breached": True,
                "breached_at": 781,
                "status": "paused",
            },
            {
                "ticket_id": "T_C_RES",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
        ],
    )

    # -------------------------------------------------------------------------
    # 6. Exact SLA Boundaries for all Priorities
    # -------------------------------------------------------------------------
    # P1: Limit 240
    assert_test(
        "P1 Exact Boundary: 240 vs 241 minutes",
        [
            "540,P1_OK,OPEN,P1",
            "780,P1_OK,PAUSE",  # exactly 240 used minutes
            "540,P1_BR,OPEN,P1",
            "781,P1_BR,PAUSE",  # 241 used minutes -> breach at 781
        ],
        [
            {
                "ticket_id": "P1_BR",
                "priority": "P1",
                "used_minutes": 241,
                "breached": True,
                "breached_at": 781,
                "status": "paused",
            },
            {
                "ticket_id": "P1_OK",
                "priority": "P1",
                "used_minutes": 240,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
        ],
    )

    # P2: Limit 480
    # Day 0: 540 to 1020 = 480 business minutes.
    # Tuesday 09:00 is 1980. At 1980, used=480. At 1981, used=481.
    assert_test(
        "P2 Exact Boundary: 480 vs 481 minutes across overnight",
        [
            "540,P2_OK,OPEN,P2",
            "1980,P2_OK,PAUSE",
            "540,P2_BR,OPEN,P2",
            "1981,P2_BR,PAUSE",
        ],
        [
            {
                "ticket_id": "P2_BR",
                "priority": "P2",
                "used_minutes": 481,
                "breached": True,
                "breached_at": 1981,
                "status": "paused",
            },
            {
                "ticket_id": "P2_OK",
                "priority": "P2",
                "used_minutes": 480,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
        ],
    )

    # P3: Limit 1440
    # Mon (480) + Tue (480) + Wed (480) = 1440 business minutes.
    # Thursday 09:00 is 4860. At 4860, used=1440. At 4861, used=1441.
    assert_test(
        "P3 Exact Boundary: 1440 vs 1441 minutes",
        [
            "540,P3_OK,OPEN,P3",
            "4860,P3_OK,PAUSE",
            "540,P3_BR,OPEN,P3",
            "4861,P3_BR,PAUSE",
        ],
        [
            {
                "ticket_id": "P3_BR",
                "priority": "P3",
                "used_minutes": 1441,
                "breached": True,
                "breached_at": 4861,
                "status": "paused",
            },
            {
                "ticket_id": "P3_OK",
                "priority": "P3",
                "used_minutes": 1440,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
        ],
    )

    # P4: Limit 2400
    # Mon..Fri = 5 * 480 = 2400.
    # Week 1 Monday 09:00 is 10620. At 10620, used=2400. At 10621, used=2401.
    assert_test(
        "P4 Exact Boundary: 2400 vs 2401 minutes across weekend",
        [
            "540,P4_OK,OPEN,P4",
            "10620,P4_OK,PAUSE",
            "540,P4_BR,OPEN,P4",
            "10621,P4_BR,PAUSE",
        ],
        [
            {
                "ticket_id": "P4_BR",
                "priority": "P4",
                "used_minutes": 2401,
                "breached": True,
                "breached_at": 10621,
                "status": "paused",
            },
            {
                "ticket_id": "P4_OK",
                "priority": "P4",
                "used_minutes": 2400,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
        ],
    )

    # Breach exactly at 17:00 (minute 1020)
    # Ticket opened at 779 (12:59 Monday), P1 (limit 240).
    # Minute 1019 is the 241st business minute.
    # At minute 1020, used time is 241 > 240 -> breached at 1020.
    assert_test(
        "Breach at the exact boundary of business day (17:00 / 1020)",
        ["779,T_EOD,OPEN,P1", "1020,T_EOD,PAUSE"],
        [
            {
                "ticket_id": "T_EOD",
                "priority": "P1",
                "used_minutes": 241,
                "breached": True,
                "breached_at": 1020,
                "status": "paused",
            }
        ],
    )

    # -------------------------------------------------------------------------
    # 7. Priority Changes, Sticky Breaches, and Mid-stream Dynamics
    # -------------------------------------------------------------------------
    # Sticky breach: PRIORITY raise does not clear breach
    assert_test(
        "Sticky breach: PRIORITY raise does not undo breach",
        [
            "540,T_STICKY,OPEN,P1",  # Breaches at 781
            "800,T_STICKY,PRIORITY,P4",  # Limit becomes 2400, breach remains sticky
            "850,T_STICKY,PAUSE",
        ],
        [
            {
                "ticket_id": "T_STICKY",
                "priority": "P4",
                "used_minutes": 310,
                "breached": True,
                "breached_at": 781,
                "status": "paused",
            }
        ],
    )

    # PRIORITY raise at exact breach minute prevents breach
    assert_test(
        "PRIORITY raise at exact minute of potential breach prevents it",
        [
            "540,T_PREVENT,OPEN,P1",
            "781,T_PREVENT,PRIORITY,P2",  # At 781, used is 241; new limit 480 prevents breach
            "800,T_PREVENT,PAUSE",
        ],
        [
            {
                "ticket_id": "T_PREVENT",
                "priority": "P2",
                "used_minutes": 260,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # PRIORITY lower while PAUSED triggers breach immediately
    assert_test(
        "PRIORITY lower while PAUSED triggers immediate breach",
        [
            "540,T_PAUSE_BR,OPEN,P2",
            "800,T_PAUSE_BR,PAUSE",  # used = 260
            "900,T_PAUSE_BR,PRIORITY,P1",  # limit becomes 240; used 260 > 240 -> breaches at 900
        ],
        [
            {
                "ticket_id": "T_PAUSE_BR",
                "priority": "P1",
                "used_minutes": 260,
                "breached": True,
                "breached_at": 900,
                "status": "paused",
            }
        ],
    )

    # PRIORITY lower while RUNNING triggers immediate breach
    assert_test(
        "PRIORITY lower while RUNNING triggers immediate breach",
        [
            "540,T_RUN_BR,OPEN,P2",
            "800,T_RUN_BR,PRIORITY,P1",  # at 800, used=260 > 240 -> breaches at 800
            "850,T_RUN_BR,PAUSE",
        ],
        [
            {
                "ticket_id": "T_RUN_BR",
                "priority": "P1",
                "used_minutes": 310,
                "breached": True,
                "breached_at": 800,
                "status": "paused",
            }
        ],
    )

    # -------------------------------------------------------------------------
    # 8. Ties, Event Ordering, and Chronological Stability
    # -------------------------------------------------------------------------
    assert_test(
        "Out of order events and ties at the same minute",
        [
            "600,T_ORDER,PAUSE",
            "540,T_ORDER,OPEN,P1",
            "600,T_ORDER,RESUME",
            "700,T_ORDER,CLOSE",
            "600,T_ORDER,PRIORITY,P2",
            "700,T_ORDER,REOPEN",
            "750,T_ORDER,PAUSE",
        ],
        # At 540: OPEN P1 (running)
        # At 600: PAUSE, then RESUME (running), then PRIORITY P2 (running, P2)
        # At 700: CLOSE, then REOPEN (running)
        # At 750: PAUSE (paused)
        # Total used: (600-540) + (700-600) + (750-700) = 60 + 100 + 50 = 210
        [
            {
                "ticket_id": "T_ORDER",
                "priority": "P2",
                "used_minutes": 210,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    assert_test(
        "Ties at breach minute: multiple priority changes",
        [
            "540,T_TIE1,OPEN,P1",
            "781,T_TIE1,PRIORITY,P2",
            "781,T_TIE1,PRIORITY,P1",  # Final at 781 is P1 -> breached at 781
            "540,T_TIE2,OPEN,P1",
            "781,T_TIE2,PRIORITY,P1",
            "781,T_TIE2,PRIORITY,P2",  # Final at 781 is P2 -> not breached
        ],
        [
            {
                "ticket_id": "T_TIE1",
                "priority": "P1",
                "used_minutes": 241,
                "breached": True,
                "breached_at": 781,
                "status": "running",
            },
            {
                "ticket_id": "T_TIE2",
                "priority": "P2",
                "used_minutes": 241,
                "breached": False,
                "breached_at": None,
                "status": "running",
            },
        ],
    )

    assert_test(
        "OPEN and PAUSE at same minute in different order",
        [
            "540,T_A,OPEN,P1",
            "540,T_A,PAUSE",  # OPEN then PAUSE -> ends in PAUSED, 0 used minutes
            "540,T_B,PAUSE",  # PAUSE ignored (NOT_OPENED), then OPEN -> ends in RUNNING
            "540,T_B,OPEN,P1",
            "600,ANCHOR,OPEN,P1",  # now = 600
        ],
        [
            {
                "ticket_id": "ANCHOR",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            },
            {
                "ticket_id": "T_A",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
            {
                "ticket_id": "T_B",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "running",
            },
        ],
    )

    # -------------------------------------------------------------------------
    # 9. Complex Calendar and Holidays
    # -------------------------------------------------------------------------
    # Monday (day 0) holiday, Wednesday (day 2) holiday
    # Ticket P2 runs Mon 09:00 to Thu 10:00 (4920)
    # Day 0: 0 min (holiday)
    # Day 1: 480 min (1980 to 2460)
    # Day 2: 0 min (holiday)
    # Day 3 (Thu): 4860 is 09:00 (used=480). 4861 is 481st minute -> breaches at 4861!
    # Thu 10:00 (4920): used = 480 + 60 = 540 min.
    assert_test(
        "Multiple holidays and duplicate holiday lines across week",
        [
            "540,T_HOL,OPEN,P2",
            "4920,T_HOL,PAUSE",
            "100,*,HOLIDAY",  # day 0
            "200,*,HOLIDAY",  # day 0 duplicate
            "3000,*,HOLIDAY",  # day 2 (Wednesday)
            "7200,*,HOLIDAY",  # day 5 (Saturday - weekend holiday)
        ],
        [
            {
                "ticket_id": "T_HOL",
                "priority": "P2",
                "used_minutes": 540,
                "breached": True,
                "breached_at": 4861,
                "status": "paused",
            }
        ],
    )

    # Ticket opened during non-business hours
    # Opened Friday 20:00 (6960), P1 (limit 240).
    # Runs over weekend to Monday 13:01 (10861).
    # Monday 09:00 is 10620. 240 business minutes end at 10860.
    # Breaches at 10861.
    assert_test(
        "Ticket opened on Friday night running into next week",
        ["6960,T_WEEKEND,OPEN,P1", "10861,T_WEEKEND,PAUSE"],
        [
            {
                "ticket_id": "T_WEEKEND",
                "priority": "P1",
                "used_minutes": 241,
                "breached": True,
                "breached_at": 10861,
                "status": "paused",
            }
        ],
    )

    # -------------------------------------------------------------------------
    # 10. Large Minute Efficiency Test
    # -------------------------------------------------------------------------
    # Week 100,000 Monday: 100000 * 10080 = 1,008,000,000.
    # 09:00 Monday is 1,008,000,540.
    # 10:00 Monday is 1,008,000,600.
    # If implementation counts minute-by-minute from 0, it will time out.
    assert_test(
        "Large minute numbers (1,008,000,000+)",
        ["1008000540,T_BIG,OPEN,P1", "1008000600,T_BIG,CLOSE"],
        [
            {
                "ticket_id": "T_BIG",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # -------------------------------------------------------------------------
    # Summary
    # -------------------------------------------------------------------------
    total_tests = tests_passed + tests_failed
    print("\n" + "=" * 60)
    print(f"TEST SUMMARY: {tests_passed}/{total_tests} passed.")
    print("=" * 60)

    if tests_failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    run_tests()