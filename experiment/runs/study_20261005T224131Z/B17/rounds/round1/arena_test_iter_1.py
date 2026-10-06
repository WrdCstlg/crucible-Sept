import solution
import sys


def run_tests():
    total_tests = 0
    passed_tests = 0
    failed_tests = []

    def assert_result(test_name, stream, expected):
        nonlocal total_tests, passed_tests
        total_tests += 1
        try:
            actual = solution.compute_sla(stream)

            if not isinstance(actual, list):
                raise AssertionError(
                    f"Expected list, got {type(actual).__name__}"
                )

            if len(actual) != len(expected):
                raise AssertionError(
                    f"Expected {len(expected)} items, got {len(actual)} items.\n"
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
            valid_statuses = {"running", "paused", "closed"}
            valid_priorities = {"P1", "P2", "P3", "P4"}

            for idx, (act, exp) in enumerate(zip(actual, expected)):
                if not isinstance(act, dict):
                    raise AssertionError(
                        f"Item {idx} is not a dict: {type(act).__name__}"
                    )

                if set(act.keys()) != required_keys:
                    raise AssertionError(
                        f"Item {idx} keys mismatch. Expected {required_keys}, got {set(act.keys())}"
                    )

                # Type checks
                if not isinstance(act["ticket_id"], str):
                    raise AssertionError(
                        f"Item {idx} 'ticket_id' must be str, got {type(act['ticket_id'])}"
                    )
                if (
                    not isinstance(act["priority"], str)
                    or act["priority"] not in valid_priorities
                ):
                    raise AssertionError(
                        f"Item {idx} 'priority' invalid: {act['priority']}"
                    )
                if (
                    type(act["used_minutes"]) is not int
                    or act["used_minutes"] < 0
                ):
                    raise AssertionError(
                        f"Item {idx} 'used_minutes' must be non-negative int, got {act['used_minutes']} ({type(act['used_minutes'])})"
                    )
                if type(act["breached"]) is not bool:
                    raise AssertionError(
                        f"Item {idx} 'breached' must be bool, got {type(act['breached'])}"
                    )
                if act["breached_at"] is not None and type(
                    act["breached_at"]
                ) not in (int,):
                    raise AssertionError(
                        f"Item {idx} 'breached_at' must be int or None, got {type(act['breached_at'])}"
                    )
                if (
                    not isinstance(act["status"], str)
                    or act["status"] not in valid_statuses
                ):
                    raise AssertionError(
                        f"Item {idx} 'status' invalid: {act['status']}"
                    )

                # Value checks
                if act != exp:
                    raise AssertionError(
                        f"Item {idx} mismatch:\nActual:   {act}\nExpected: {exp}"
                    )

            passed_tests += 1
        except Exception as e:
            failed_tests.append((test_name, str(e)))

    # =========================================================================
    # Group 1: Specification Examples
    # =========================================================================
    assert_result(
        "Example 1: basic open, close",
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

    assert_result(
        "Example 2: business hours over weekend",
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

    assert_result(
        "Example 3: breach time calculation",
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

    assert_result(
        "Example 4: holiday declared at stream end and malformed lines",
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

    # =========================================================================
    # Group 2: Empty, Malformed, and Unopened Streams
    # =========================================================================
    assert_result("Empty stream", [], [])
    assert_result("Stream with only whitespace lines", ["", "   ", "\t\n"], [])
    assert_result(
        "Stream with only HOLIDAY lines",
        ["500,*,HOLIDAY", "2000,*,HOLIDAY", "  0 , * , HOLIDAY  "],
        [],
    )
    assert_result(
        "Stream with only malformed lines",
        [
            "-10,A,OPEN,P1",
            "10.5,A,OPEN,P1",
            "10,*,OPEN,P1",
            "10,A,HOLIDAY",
            "10,A,OPEN,P5",
            "10,A,OPEN",
            "10,A,PAUSE,EXTRA",
            "10,,OPEN,P1",
            "abc,A,OPEN,P1",
            "10,A,open,P1",
            "10,A,OPEN,p1",
        ],
        [],
    )
    assert_result(
        "Stream with ticket events that never had a valid OPEN",
        [
            "540,X,PAUSE",
            "600,X,RESUME",
            "700,X,CLOSE",
            "800,X,REOPEN",
            "900,X,PRIORITY,P1",
        ],
        [],
    )

    # =========================================================================
    # Group 3: Definition of 'now' and Malformed/Holiday Isolation
    # =========================================================================
    assert_result(
        "Malformed line with large minute does not affect 'now'",
        [
            "540,A,OPEN,P1",
            "999999,A,OPEN",
            "999999,*,PAUSE",
            "999999,A,OPEN,P5",
            "999999,A,UNKNOWN",
        ],
        [
            {
                "ticket_id": "A",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    assert_result(
        "HOLIDAY line with large minute does not affect 'now'",
        ["540,A,OPEN,P1", "999999,*,HOLIDAY"],
        [
            {
                "ticket_id": "A",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    assert_result(
        "Ignored transition on opened ticket updates 'now'",
        [
            "540,A,OPEN,P1",
            "600,A,RESUME",  # RUNNING + RESUME is ignored, but updates now to 600
        ],
        [
            {
                "ticket_id": "A",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    assert_result(
        "Unopened ticket event updates 'now' but unopened ticket is omitted",
        [
            "540,A,OPEN,P1",
            "660,B,PAUSE",  # B has no valid OPEN -> ignored, but updates now to 660
        ],
        [
            {
                "ticket_id": "A",
                "priority": "P1",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # =========================================================================
    # Group 4: State Transition Table - Complete 24 Cells
    # =========================================================================
    # State: NOT_OPENED
    # Cell 1: NOT_OPENED + OPEN -> tested in Example 1

    # Cells 2-6: NOT_OPENED + PRIORITY, PAUSE, RESUME, CLOSE, REOPEN are ignored
    assert_result(
        "NOT_OPENED transitions: ignored events on X do not open X",
        [
            "540,X,PRIORITY,P1",
            "550,X,PAUSE",
            "560,X,RESUME",
            "570,X,CLOSE",
            "580,X,REOPEN",
            "600,Y,OPEN,P2",
        ],
        [
            {
                "ticket_id": "Y",
                "priority": "P2",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # State: RUNNING
    # Cell 7: RUNNING + OPEN is ignored
    assert_result(
        "RUNNING + OPEN is ignored",
        [
            "540,T,OPEN,P1",
            "600,T,OPEN,P2",  # ignored: priority stays P1, used not reset
            "660,T,PAUSE",
        ],
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

    # Cell 8: RUNNING + PRIORITY -> updates priority
    assert_result(
        "RUNNING + PRIORITY updates priority",
        ["540,T,OPEN,P1", "600,T,PRIORITY,P2", "660,T,PAUSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P2",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # Cell 9: RUNNING + PAUSE -> to PAUSED
    assert_result(
        "RUNNING + PAUSE transitions to PAUSED",
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

    # Cell 10: RUNNING + RESUME -> ignored
    assert_result(
        "RUNNING + RESUME is ignored",
        ["540,T,OPEN,P1", "600,T,RESUME", "660,T,CLOSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # Cell 11: RUNNING + CLOSE -> to CLOSED
    assert_result(
        "RUNNING + CLOSE transitions to CLOSED",
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

    # Cell 12: RUNNING + REOPEN -> ignored
    assert_result(
        "RUNNING + REOPEN is ignored",
        ["540,T,OPEN,P1", "600,T,REOPEN", "660,T,CLOSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # State: PAUSED
    # Cell 13: PAUSED + OPEN is ignored
    assert_result(
        "PAUSED + OPEN is ignored",
        [
            "540,T,OPEN,P1",
            "570,T,PAUSE",
            "600,T,OPEN,P2",  # ignored: stays paused, priority P1
            "660,T,CLOSE",
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 30,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # Cell 14: PAUSED + PRIORITY -> updates priority
    assert_result(
        "PAUSED + PRIORITY updates priority",
        [
            "540,T,OPEN,P1",
            "570,T,PAUSE",
            "600,T,PRIORITY,P3",
            "660,T,CLOSE",
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P3",
                "used_minutes": 30,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # Cell 15: PAUSED + PAUSE -> ignored
    assert_result(
        "PAUSED + PAUSE is ignored",
        [
            "540,T,OPEN,P1",
            "570,T,PAUSE",
            "600,T,PAUSE",  # ignored
            "660,T,RESUME",
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 30,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # Cell 16: PAUSED + RESUME -> to RUNNING
    assert_result(
        "PAUSED + RESUME transitions to RUNNING",
        [
            "540,T,OPEN,P1",
            "570,T,PAUSE",
            "600,T,RESUME",
            "660,T,CLOSE",
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 90,  # 30 before pause + 60 after resume
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # Cell 17: PAUSED + CLOSE -> to CLOSED
    assert_result(
        "PAUSED + CLOSE transitions to CLOSED",
        ["540,T,OPEN,P1", "570,T,PAUSE", "600,T,CLOSE"],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 30,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # Cell 18: PAUSED + REOPEN -> ignored
    assert_result(
        "PAUSED + REOPEN is ignored",
        [
            "540,T,OPEN,P1",
            "570,T,PAUSE",
            "600,T,REOPEN",  # ignored
            "660,T,RESUME",
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 30,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # State: CLOSED
    # Cell 19: CLOSED + OPEN -> to RUNNING, resets used to 0, breach cleared
    assert_result(
        "CLOSED + OPEN resets used to 0 and clears breach",
        [
            "540,T,OPEN,P1",
            "800,T,CLOSE",  # breached at 781, closed with 260 used minutes
            "900,T,OPEN,P2",  # resets used to 0, breach cleared, priority P2
            "950,T,PAUSE",
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P2",
                "used_minutes": 50,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # Cell 20: CLOSED + PRIORITY -> ignored
    assert_result(
        "CLOSED + PRIORITY is ignored",
        [
            "540,T,OPEN,P1",
            "600,T,CLOSE",
            "700,T,PRIORITY,P3",  # ignored: priority remains P1
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

    # Cell 21: CLOSED + PAUSE -> ignored
    assert_result(
        "CLOSED + PAUSE is ignored",
        ["540,T,OPEN,P1", "600,T,CLOSE", "700,T,PAUSE"],
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

    # Cell 22: CLOSED + RESUME -> ignored
    assert_result(
        "CLOSED + RESUME is ignored",
        ["540,T,OPEN,P1", "600,T,CLOSE", "700,T,RESUME"],
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

    # Cell 23: CLOSED + CLOSE -> ignored
    assert_result(
        "CLOSED + CLOSE is ignored",
        ["540,T,OPEN,P1", "600,T,CLOSE", "700,T,CLOSE"],
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

    # Cell 24: CLOSED + REOPEN -> to RUNNING, used continues, breach kept, priority kept
    assert_result(
        "CLOSED + REOPEN continues used minutes and keeps breach and priority",
        [
            "540,T,OPEN,P1",
            "800,T,CLOSE",  # breached at 781, used 260
            "900,T,REOPEN",  # used continues from 260, breach kept (781), priority P1
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 260,
                "breached": True,
                "breached_at": 781,
                "status": "running",
            }
        ],
    )

    # =========================================================================
    # Group 5: SLA Boundaries and Exact Breach Minute
    # =========================================================================
    assert_result(
        "Exact SLA boundary: P1 runs exactly 240 minutes -> no breach",
        [
            "540,T,OPEN,P1",
            "780,T,PAUSE",  # 540..779 is exactly 240 business minutes
        ],
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

    assert_result(
        "Exact SLA boundary: P1 runs 241 minutes -> breaches at 781",
        [
            "540,T,OPEN,P1",
            "781,T,PAUSE",  # 540..780 is 241 business minutes
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

    assert_result(
        "Exact SLA boundary: P2 limit 480 runs across overnight -> breaches at 1981",
        [
            "540,T,OPEN,P2",
            "2000,T,CLOSE",  # Mon 540..1019 = 480 mins. Tue 1980 is 481st min -> breaches at 1981
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P2",
                "used_minutes": 500,  # 480 + 20
                "breached": True,
                "breached_at": 1981,
                "status": "closed",
            }
        ],
    )

    assert_result(
        "Exact SLA boundary: P3 limit 1440 runs across 3 days -> breaches Thursday 4861",
        [
            "540,T,OPEN,P3",
            "4900,T,CLOSE",  # Mon, Tue, Wed = 3*480 = 1440. Thu 4860 is 1441st min -> breaches at 4861
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P3",
                "used_minutes": 1480,
                "breached": True,
                "breached_at": 4861,
                "status": "closed",
            }
        ],
    )

    assert_result(
        "Exact SLA boundary: P4 limit 2400 runs across full week -> breaches Monday week 1 at 10621",
        [
            "540,T,OPEN,P4",
            "10700,T,CLOSE",  # Week 0 Mon-Fri = 2400. Week 1 Mon 10620 is 2401st min -> breaches at 10621
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P4",
                "used_minutes": 2480,
                "breached": True,
                "breached_at": 10621,
                "status": "closed",
            }
        ],
    )

    # =========================================================================
    # Group 6: Priority Changes and Immediate Breaches
    # =========================================================================
    assert_result(
        "Priority downgrade causes immediate breach while RUNNING",
        [
            "540,T,OPEN,P2",
            "800,T,PRIORITY,P1",  # used at 800 is 260 > 240 -> breaches at 800
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 260,
                "breached": True,
                "breached_at": 800,
                "status": "running",
            }
        ],
    )

    assert_result(
        "Priority downgrade causes immediate breach while PAUSED",
        [
            "540,T,OPEN,P2",
            "790,T,PAUSE",  # used is 250
            "850,T,PRIORITY,P1",  # limit becomes 240, 250 > 240 -> breaches at 850
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P1",
                "used_minutes": 250,
                "breached": True,
                "breached_at": 850,
                "status": "paused",
            }
        ],
    )

    assert_result(
        "Priority raise at exact breach minute prevents breach",
        [
            "540,T,OPEN,P1",
            "781,T,PRIORITY,P2",  # at 781, priority becomes P2 (limit 480), used 241 <= 480 -> no breach!
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P2",
                "used_minutes": 241,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    assert_result(
        "Priority raise 1 minute AFTER breach does NOT undo breach (breach is sticky)",
        [
            "540,T,OPEN,P1",
            "782,T,PRIORITY,P2",  # at 781 breached! At 782 priority raised, breach remains
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P2",
                "used_minutes": 242,
                "breached": True,
                "breached_at": 781,
                "status": "running",
            }
        ],
    )

    assert_result(
        "Reopened ticket breaches later on second run",
        [
            "540,A,OPEN,P1",
            "700,A,CLOSE",  # used = 160
            "1000,A,REOPEN",  # 20 mins on Mon (1000..1019) -> 180 mins. Tue 1980..2039 -> 60 mins (240).
            # 2040 is 241st business min -> breaches at 2041!
            "2050,A,CLOSE",
        ],
        [
            {
                "ticket_id": "A",
                "priority": "P1",
                "used_minutes": 250,  # 160 + 20 + 70
                "breached": True,
                "breached_at": 2041,
                "status": "closed",
            }
        ],
    )

    # =========================================================================
    # Group 7: Calendar, Weekends, Holidays, and Minute Boundaries
    # =========================================================================
    assert_result(
        "Minute 539 before 09:00 accumulates 0 business minutes",
        ["539,A,OPEN,P1", "540,A,CLOSE"],
        [
            {
                "ticket_id": "A",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    assert_result(
        "Minute 540 to 541 accumulates exactly 1 business minute",
        ["540,A,OPEN,P1", "541,A,CLOSE"],
        [
            {
                "ticket_id": "A",
                "priority": "P1",
                "used_minutes": 1,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    assert_result(
        "Minute 1019 to 1020 accumulates exactly 1 business minute",
        ["1019,A,OPEN,P1", "1020,A,CLOSE"],
        [
            {
                "ticket_id": "A",
                "priority": "P1",
                "used_minutes": 1,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    assert_result(
        "Minute 1020 to 1021 after 17:00 accumulates 0 business minutes",
        ["1020,A,OPEN,P1", "1021,A,CLOSE"],
        [
            {
                "ticket_id": "A",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    assert_result(
        "Weekend running accumulates 0 business minutes",
        [
            "7740,A,OPEN,P1",  # Saturday 09:00
            "9500,A,CLOSE",  # Sunday 14:20
        ],
        [
            {
                "ticket_id": "A",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    assert_result(
        "Friday evening to Monday morning over holiday on Monday",
        [
            "6750,A,OPEN,P1",  # Friday 16:30 -> 30 mins (6750..6779)
            "12090,A,CLOSE",  # Tuesday 09:30 -> 30 mins (12060..12089)
            "10080,*,HOLIDAY",  # Monday day 7 declared holiday
            "10500,*,HOLIDAY",  # Duplicate holiday on same day 7
        ],
        [
            {
                "ticket_id": "A",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    assert_result(
        "Whole day 0 holiday makes ticket running Monday accumulate 0 used minutes",
        ["540,A,OPEN,P1", "1020,A,CLOSE", "0,*,HOLIDAY"],
        [
            {
                "ticket_id": "A",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # =========================================================================
    # Group 8: Out-of-Order Events and Stable Sort on Same-Minute Ties
    # =========================================================================
    assert_result(
        "Out of order events sorted correctly",
        ["900,A,CLOSE", "540,A,OPEN,P1"],
        [
            {
                "ticket_id": "A",
                "priority": "P1",
                "used_minutes": 360,
                "breached": True,
                "breached_at": 781,
                "status": "closed",
            }
        ],
    )

    # Tie contrast: OPEN then CLOSE vs CLOSE then OPEN
    assert_result(
        "Tie at minute 600: OPEN then CLOSE (OPEN ignored from RUNNING)",
        [
            "540,T,OPEN,P1",
            "600,T,OPEN,P2",  # from RUNNING -> ignored
            "600,T,CLOSE",  # from RUNNING -> CLOSED
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

    assert_result(
        "Tie at minute 600: CLOSE then OPEN (OPEN from CLOSED resets used to 0)",
        [
            "540,T,OPEN,P1",
            "600,T,CLOSE",  # from RUNNING -> CLOSED
            "600,T,OPEN,P2",  # from CLOSED -> RUNNING, priority P2, used resets to 0
        ],
        [
            {
                "ticket_id": "T",
                "priority": "P2",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # Stable sort tie across out-of-order records
    assert_result(
        "Out of order with same-minute ties preserves stream order",
        [
            "600,B,OPEN,P2",
            "540,B,OPEN,P1",
            "600,B,CLOSE",
        ],
        [
            {
                "ticket_id": "B",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # =========================================================================
    # Group 9: Output Sorting, Formats, and Case Sensitivity
    # =========================================================================
    assert_result(
        "Output sorted by ticket_id ascending (code point order) and case sensitivity",
        [
            "540,T10,OPEN,P1",
            "540,T2,OPEN,P1",
            "540,t1,OPEN,P1",
            "540,T1,OPEN,P1",
        ],
        [
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

    assert_result(
        "Whitespace trimming and leading zero parsing",
        [
            "  00540  ,  A  ,  OPEN  ,  P1  \n",
            " \t00600\t , A , CLOSE\r\n",
        ],
        [
            {
                "ticket_id": "A",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # =========================================================================
    # Group 10: Scale and Performance (Minutes up to 1,000,000,000)
    # =========================================================================
    # 1,000,000,000 = 99206 * 10080 + 3520
    # Full weeks 0..99205 have 99206 * 2400 = 238,094,400 business minutes.
    # Tuesday week 0 (day 1, minute 1440) is a holiday -> -480 business minutes = 238,093,920.
    # In week 99206, 3520 minutes:
    # Day 0 (Mon): 480 business minutes
    # Day 1 (Tue): 480 business minutes
    # Day 2 (Wed): 3520 - (2880 + 540) = 3520 - 3420 = 100 business minutes
    # Total week 99206 = 480 + 480 + 100 = 1060 business minutes.
    # Total business minutes in [540, 1000000000) = 238,093,920 + 1060 = 238,094,980.
    # P4 limit is 2400. In week 0: Mon=480, Tue=0(holiday), Wed=480, Thu=480, Fri=480 -> 1920 mins.
    # In week 1: Mon 10620..11100 = 480 mins -> exactly 2400 mins used at Mon 17:00 (11100).
    # Tuesday week 1 09:00 is minute 12060 (2401st business min) -> breaches at 12061!
    assert_result(
        "Large timestamp up to 1,000,000,000 with calendar arithmetic",
        [
            "540,T_HUGE,OPEN,P4",
            "1440,*,HOLIDAY",  # Tuesday week 0 is holiday
            "1000000000,T_HUGE,CLOSE",
        ],
        [
            {
                "ticket_id": "T_HUGE",
                "priority": "P4",
                "used_minutes": 238094980,
                "breached": True,
                "breached_at": 12061,
                "status": "closed",
            }
        ],
    )

    # High event-count batch performance test
    batch_stream = []
    expected_batch = []
    # 500 tickets, each opened and closed on Monday week 0
    # Day 0 Monday: minutes 540 to 1019
    for i in range(200):
        t_id = f"T_{i:04d}"
        open_min = 540 + i * 2
        close_min = open_min + 1
        batch_stream.append(f"{open_min},{t_id},OPEN,P1")
        batch_stream.append(f"{close_min},{t_id},CLOSE")
        expected_batch.append(
            {
                "ticket_id": t_id,
                "priority": "P1",
                "used_minutes": 1,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        )
    # Add 100 holiday lines
    for h in range(100):
        batch_stream.append(f"{50000 + h * 1440},*,HOLIDAY")

    assert_result(
        "Batch performance: 400 events + 100 holidays",
        batch_stream,
        expected_batch,
    )

    # =========================================================================
    # Summary and Exit
    # =========================================================================
    print("=" * 60)
    print(
        f"Test Summary: {passed_tests}/{total_tests} tests passed ({len(failed_tests)} failed)"
    )
    print("=" * 60)

    if failed_tests:
        print("FAILURES:")
        for name, err in failed_tests:
            print(f"- {name}:\n  {err}\n")
        sys.exit(1)
    else:
        print("All tests passed successfully.")
        sys.exit(0)


if __name__ == "__main__":
    run_tests()