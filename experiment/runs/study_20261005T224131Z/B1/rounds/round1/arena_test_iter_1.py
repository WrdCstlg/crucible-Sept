import solution
import sys


def run_tests():
    total_tests = 0
    passed_tests = 0
    failures = []

    def check(name, stream, expected):
        nonlocal total_tests, passed_tests
        total_tests += 1
        try:
            actual = solution.compute_sla(stream)
            if actual != expected:
                failures.append(
                    f"FAIL: {name}\n"
                    f"  Input:    {stream}\n"
                    f"  Expected: {expected}\n"
                    f"  Actual:   {actual}"
                )
            else:
                passed_tests += 1
        except Exception as e:
            failures.append(
                f"ERROR: {name}\n"
                f"  Input:     {stream}\n"
                f"  Exception: {type(e).__name__}: {e}"
            )

    # =========================================================================
    # 1. Spec Examples
    # =========================================================================
    check(
        "Spec Example 1 (Format, basic open and close)",
        [
            "540,A,OPEN,P2",
            "600,A,CLOSE",
        ],
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

    check(
        "Spec Example 2 (Business hours and weekend span)",
        [
            "6720,B,OPEN,P1",
            "10680,B,PAUSE",
        ],
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

    check(
        "Spec Example 3 (Breach minute boundary)",
        [
            "540,C,OPEN,P1",
            "900,C,CLOSE",
        ],
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

    check(
        "Spec Example 4 (Holiday declared at stream end, malformed lines ignored)",
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
    # 2. Malformed Lines and Syntactic Edge Cases
    # =========================================================================
    check(
        "Malformed lines: various invalid records are ignored",
        [
            "",  # empty
            "   ",  # whitespace only
            "\t\n",
            "-10,T1,OPEN,P1",  # negative minute
            "+540,T1,OPEN,P1",  # plus sign in minute
            "540.0,T1,OPEN,P1",  # float minute
            "12a,T1,OPEN,P1",  # non-digit minute
            "540,,OPEN,P1",  # empty ticket ID
            "540,   ,OPEN,P1",  # whitespace ticket ID
            "540,T1,open,P1",  # lowercase event
            "540,T1,OPEN,p1",  # lowercase priority
            "540,T1,OPEN,P0",  # invalid priority P0
            "540,T1,OPEN,P5",  # invalid priority P5
            "540,T1,OPEN,HIGH",  # invalid priority word
            "540,T1,OPEN",  # 3 fields for OPEN
            "540,T1,OPEN,P1,EXTRA",  # 5 fields for OPEN
            "540,T1,PRIORITY",  # 3 fields for PRIORITY
            "540,T1,PRIORITY,P1,EXTRA",  # 5 fields for PRIORITY
            "540,T1,PAUSE,P1",  # 4 fields for PAUSE
            "540,T1,RESUME,P1",  # 4 fields for RESUME
            "540,T1,CLOSE,P1",  # 4 fields for CLOSE
            "540,T1,REOPEN,P1",  # 4 fields for REOPEN
            "540,T1,UNKNOWN",  # unknown event
            "540,*,OPEN,P1",  # ticket ID '*' on non-HOLIDAY
            "540,*,PAUSE",  # ticket ID '*' on PAUSE
            "540,T1,HOLIDAY",  # non-'*' on HOLIDAY
            "540,*,HOLIDAY,P1",  # 4 fields for HOLIDAY
            "  000540  ,  T1  ,  OPEN  ,  P1  ",  # valid: leading zeros + whitespace trimming
            "000600,T1,CLOSE",  # valid: leading zeros
        ],
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

    # =========================================================================
    # 3. 'now' Definition and Filtering
    # =========================================================================
    check("Empty stream returns empty list", [], [])

    check(
        "Only malformed lines returns empty list",
        ["not,a,valid,csv", ",,,", "abc,def,ghi", "100,T1,BAD,P1"],
        [],
    )

    check(
        "Only HOLIDAY lines returns empty list (no ticket events)",
        ["540,*,HOLIDAY", "2000,*,HOLIDAY"],
        [],
    )

    check(
        "Ticket events exist but no ticket had a valid OPEN",
        [
            "540,T1,PAUSE",
            "600,T1,RESUME",
            "700,T1,CLOSE",
            "800,T1,REOPEN",
            "900,T1,PRIORITY,P1",
        ],
        [],
    )

    check(
        "'now' set by ignored event of another un-opened ticket",
        [
            "540,T1,OPEN,P1",
            "600,T2,PAUSE",  # T2 ignored transition, never validly opened, but sets 'now' to 600
        ],
        [
            {
                "ticket_id": "T1",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    check(
        "HOLIDAY lines never affect 'now'",
        [
            "540,T1,OPEN,P1",
            "50000,*,HOLIDAY",  # HOLIDAY far in future: must NOT advance 'now' to 50000
        ],
        [
            {
                "ticket_id": "T1",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "running",
            }
        ],
    )

    # =========================================================================
    # 4. State Transition Table (Exhaustive Coverage of All 24 Cells)
    # =========================================================================
    # Cell 1..6: NOT_OPENED state
    check(
        "State transitions from NOT_OPENED: OPEN is valid, others ignored",
        [
            "500,T_NO,PRIORITY,P2",  # ignored
            "510,T_NO,PAUSE",  # ignored
            "520,T_NO,RESUME",  # ignored
            "530,T_NO,CLOSE",  # ignored
            "535,T_NO,REOPEN",  # ignored
            "540,T_NO,OPEN,P1",  # to RUNNING, priority P1, used 0
            "600,T_NO,PAUSE",  # to PAUSED
        ],
        [
            {
                "ticket_id": "T_NO",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    # Cell 7..12: RUNNING state
    check(
        "State transitions from RUNNING: OPEN, RESUME, REOPEN ignored; PRIORITY updates; PAUSE, CLOSE work",
        [
            "540,T_RUN,OPEN,P1",  # RUNNING
            "560,T_RUN,OPEN,P3",  # ignored: priority remains P1, used continues
            "570,T_RUN,RESUME",  # ignored: already RUNNING
            "580,T_RUN,REOPEN",  # ignored: already RUNNING
            "590,T_RUN,PRIORITY,P2",  # priority becomes P2
            "600,T_RUN,PAUSE",  # to PAUSED
            "600,T_RUN,RESUME",  # to RUNNING (tied minute)
            "610,T_RUN,CLOSE",  # to CLOSED
        ],
        [
            {
                "ticket_id": "T_RUN",
                "priority": "P2",
                "used_minutes": 70,  # 540 to 610
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # Cell 13..18: PAUSED state
    check(
        "State transitions from PAUSED: OPEN, PAUSE, REOPEN ignored; PRIORITY updates; RESUME, CLOSE work",
        [
            "540,T_PAU,OPEN,P1",  # RUNNING
            "550,T_PAU,PAUSE",  # PAUSED
            "560,T_PAU,OPEN,P3",  # ignored: stays PAUSED, priority stays P1
            "570,T_PAU,PAUSE",  # ignored: already PAUSED
            "580,T_PAU,REOPEN",  # ignored: stays PAUSED
            "590,T_PAU,PRIORITY,P4",  # priority becomes P4
            "610,T_PAU,RESUME",  # to RUNNING
            "630,T_PAU,CLOSE",  # to CLOSED
        ],
        [
            {
                "ticket_id": "T_PAU",
                "priority": "P4",
                "used_minutes": 30,  # (550-540) + (630-610) = 10 + 20
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    check(
        "State transitions from PAUSED directly to CLOSED",
        [
            "540,T_PC,OPEN,P1",  # RUNNING
            "550,T_PC,PAUSE",  # PAUSED
            "570,T_PC,CLOSE",  # CLOSED directly from PAUSED
        ],
        [
            {
                "ticket_id": "T_PC",
                "priority": "P1",
                "used_minutes": 10,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # Cell 19..24: CLOSED state
    check(
        "State transitions from CLOSED: PRIORITY, PAUSE, RESUME, CLOSE ignored; REOPEN continues",
        [
            "540,T_CL,OPEN,P1",  # RUNNING
            "550,T_CL,CLOSE",  # CLOSED
            "560,T_CL,PRIORITY,P2",  # ignored on CLOSED
            "570,T_CL,PAUSE",  # ignored on CLOSED
            "580,T_CL,RESUME",  # ignored on CLOSED
            "590,T_CL,CLOSE",  # ignored on CLOSED
            "600,T_CL,REOPEN",  # to RUNNING, priority kept as P1, used continues
            "620,T_CL,CLOSE",  # to CLOSED
        ],
        [
            {
                "ticket_id": "T_CL",
                "priority": "P1",
                "used_minutes": 30,  # (550-540) + (620-600) = 10 + 20
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    check(
        "OPEN on CLOSED resets used time to 0, clears breach, sets new priority",
        [
            "540,T_CR,OPEN,P1",  # RUNNING
            "900,T_CR,CLOSE",  # CLOSED, used=360, breached at 781
            "950,T_CR,OPEN,P2",  # OPEN on CLOSED: used resets to 0, breach cleared, priority P2
            "970,T_CR,CLOSE",  # CLOSED
        ],
        [
            {
                "ticket_id": "T_CR",
                "priority": "P2",
                "used_minutes": 20,  # 970 - 950
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # =========================================================================
    # 5. Exact SLA Boundary & Priority Shifts
    # =========================================================================
    check(
        "Exact boundary: used == limit (240) does NOT breach",
        [
            "540,T_EXACT,OPEN,P1",
            "780,T_EXACT,PAUSE",  # 780 - 540 = 240 business minutes
        ],
        [
            {
                "ticket_id": "T_EXACT",
                "priority": "P1",
                "used_minutes": 240,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    check(
        "Exact boundary: used == limit + 1 (241) breaches at minute 781",
        [
            "540,T_PLUS1,OPEN,P1",
            "781,T_PLUS1,PAUSE",  # 781 - 540 = 241 business minutes
        ],
        [
            {
                "ticket_id": "T_PLUS1",
                "priority": "P1",
                "used_minutes": 241,
                "breached": True,
                "breached_at": 781,
                "status": "paused",
            }
        ],
    )

    check(
        "PRIORITY raise at breach minute prevents breach",
        [
            "540,T_UP,OPEN,P1",
            "781,T_UP,PRIORITY,P2",  # limit becomes 480 before breach check
            "781,T_UP,PAUSE",
        ],
        [
            {
                "ticket_id": "T_UP",
                "priority": "P2",
                "used_minutes": 241,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ],
    )

    check(
        "PRIORITY downgrade while PAUSED immediately triggers breach",
        [
            "540,T_DOWN_P,OPEN,P2",  # limit 480
            "781,T_DOWN_P,PAUSE",  # used = 241, paused
            "800,T_DOWN_P,PRIORITY,P1",  # limit becomes 240 while paused; 241 > 240 -> breach at 800!
        ],
        [
            {
                "ticket_id": "T_DOWN_P",
                "priority": "P1",
                "used_minutes": 241,
                "breached": True,
                "breached_at": 800,
                "status": "paused",
            }
        ],
    )

    check(
        "PRIORITY downgrade while RUNNING immediately triggers breach",
        [
            "540,T_DOWN_R,OPEN,P2",
            "781,T_DOWN_R,PRIORITY,P1",  # used = 241 > 240 -> breach at 781!
            "781,T_DOWN_R,PAUSE",
        ],
        [
            {
                "ticket_id": "T_DOWN_R",
                "priority": "P1",
                "used_minutes": 241,
                "breached": True,
                "breached_at": 781,
                "status": "paused",
            }
        ],
    )

    check(
        "Breach is sticky: raising priority later does not undo it",
        [
            "540,T_STICKY,OPEN,P1",
            "781,T_STICKY,PAUSE",  # breached at 781
            "800,T_STICKY,PRIORITY,P4",  # limit 2400, but already breached
        ],
        [
            {
                "ticket_id": "T_STICKY",
                "priority": "P4",
                "used_minutes": 241,
                "breached": True,
                "breached_at": 781,
                "status": "paused",
            }
        ],
    )

    check(
        "REOPEN preserves existing breach",
        [
            "540,T_RBK,OPEN,P1",
            "781,T_RBK,CLOSE",  # breached at 781
            "800,T_RBK,REOPEN",  # REOPEN keeps breach
            "810,T_RBK,CLOSE",
        ],
        [
            {
                "ticket_id": "T_RBK",
                "priority": "P1",
                "used_minutes": 251,
                "breached": True,
                "breached_at": 781,
                "status": "closed",
            }
        ],
    )

    check(
        "REOPEN ticket breaches later as used time continues",
        [
            "540,T_RLB,OPEN,P1",
            "640,T_RLB,CLOSE",  # used 100, not breached
            "700,T_RLB,REOPEN",  # used continues from 100
            "850,T_RLB,CLOSE",  # breaches at 700 + 141 = 841
        ],
        [
            {
                "ticket_id": "T_RLB",
                "priority": "P1",
                "used_minutes": 250,  # 100 + (850 - 700) = 250
                "breached": True,
                "breached_at": 841,
                "status": "closed",
            }
        ],
    )

    # =========================================================================
    # 6. Stable Sort and Same-Minute Ties
    # =========================================================================
    check(
        "Ties: stream order PAUSE then RESUME at same minute leaves ticket RUNNING",
        [
            "540,TIE_1,OPEN,P1",
            "600,TIE_1,PAUSE",
            "600,TIE_1,RESUME",
            "610,TIE_1,CLOSE",
        ],
        [
            {
                "ticket_id": "TIE_1",
                "priority": "P1",
                "used_minutes": 70,  # (600-540) + (610-600)
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    check(
        "Ties: stream order RESUME then PAUSE at same minute leaves ticket PAUSED",
        [
            "540,TIE_2,OPEN,P1",
            "570,TIE_2,PAUSE",
            "600,TIE_2,RESUME",
            "600,TIE_2,PAUSE",
            "610,TIE_2,CLOSE",
        ],
        [
            {
                "ticket_id": "TIE_2",
                "priority": "P1",
                "used_minutes": 30,  # 570 - 540; paused from 570 to 610
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    check(
        "Ties: OPEN and CLOSE at the same minute",
        [
            "540,TIE_3,OPEN,P1",
            "540,TIE_3,CLOSE",
        ],
        [
            {
                "ticket_id": "TIE_3",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    check(
        "Ties: CLOSE and REOPEN at the same minute",
        [
            "540,TIE_4,OPEN,P1",
            "600,TIE_4,CLOSE",
            "600,TIE_4,REOPEN",
            "610,TIE_4,CLOSE",
        ],
        [
            {
                "ticket_id": "TIE_4",
                "priority": "P1",
                "used_minutes": 70,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # =========================================================================
    # 7. Calendar, Weekends, Holidays, and Out-of-Order Events
    # =========================================================================
    check(
        "Calendar: Weekend span with Monday Holiday",
        [
            # Friday 16:00 is 4 * 1440 + 960 = 6720
            # Friday 17:00 is 4 * 1440 + 1020 = 6780 (60 business minutes on Friday)
            # Monday (Day 7) is a holiday: 7 * 1440 = 10080
            # Tuesday (Day 8) starts at 8 * 1440 = 11520. Business hours: 11520 + 540 = 12060
            # Tuesday 10:00 is 12060 + 60 = 12120 (60 business minutes on Tuesday)
            "10080,*,HOLIDAY",  # declared before ticket events
            "10100,*,HOLIDAY",  # duplicate holiday on day 7
            "6720,H_TICK,OPEN,P1",
            "12120,H_TICK,CLOSE",
        ],
        [
            {
                "ticket_id": "H_TICK",
                "priority": "P1",
                "used_minutes": 120,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    check(
        "Breach across weekend and holiday",
        [
            # P1 limit = 240. Opened Friday 15:00: 5760 + 900 = 6660.
            # Friday business minutes left: 6780 - 6660 = 120.
            # Monday Day 7 is holiday: 10080.
            # Tuesday Day 8 starts business at 12060.
            # Needs 241 - 120 = 121 business minutes on Tuesday.
            # 12060 + 121 = 12181 breach minute!
            "10080,*,HOLIDAY",
            "12300,BREACH_HOL,CLOSE",
            "6660,BREACH_HOL,OPEN,P1",  # out of order arrival
        ],
        [
            {
                "ticket_id": "BREACH_HOL",
                "priority": "P1",
                "used_minutes": 360,  # 120 (Fri) + 240 (Tue 12060 to 12300)
                "breached": True,
                "breached_at": 12181,
                "status": "closed",
            }
        ],
    )

    check(
        "Events completely outside business hours have 0 used business minutes",
        [
            # Saturday 10:00 (Day 5, minute 7200 + 600 = 7800)
            # Sunday 12:00 (Day 6, minute 8640 + 720 = 9360)
            "7800,WKND,OPEN,P1",
            "9360,WKND,CLOSE",
        ],
        [
            {
                "ticket_id": "WKND",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ],
    )

    # =========================================================================
    # 8. Priorities P3 (1440) and P4 (2400) Limits
    # =========================================================================
    check(
        "Priority P3 breach: limit is 1440 (3 business days)",
        [
            # Opened Mon 09:00 (540).
            # Mon: 480 mins. Tue: 480 mins. Wed: 480 mins. Total 1440 mins.
            # Wed business ends at 3900.
            # Thu (Day 3) business starts at 3 * 1440 + 540 = 4860.
            # 1441st business minute is [4860, 4861), breach at 4861!
            "540,P3_TICK,OPEN,P3",
            "4861,P3_TICK,CLOSE",
        ],
        [
            {
                "ticket_id": "P3_TICK",
                "priority": "P3",
                "used_minutes": 1441,
                "breached": True,
                "breached_at": 4861,
                "status": "closed",
            }
        ],
    )

    check(
        "Priority P4 breach: limit is 2400 (5 business days / 1 full week)",
        [
            # Opened Mon 09:00 (540).
            # Mon-Fri: 5 * 480 = 2400 business minutes. Ends Friday 17:00 (6780).
            # Weekend has 0 business minutes.
            # Next Mon (Day 7) business starts at 7 * 1440 + 540 = 10620.
            # 2401st business minute is [10620, 10621), breach at 10621!
            "540,P4_TICK,OPEN,P4",
            "10621,P4_TICK,CLOSE",
        ],
        [
            {
                "ticket_id": "P4_TICK",
                "priority": "P4",
                "used_minutes": 2401,
                "breached": True,
                "breached_at": 10621,
                "status": "closed",
            }
        ],
    )

    # =========================================================================
    # 9. Output Sorting, Keys, and Code-Point Ordering
    # =========================================================================
    check(
        "Output code-point sorting and case-sensitive ticket IDs",
        [
            "540,T10,OPEN,P1",
            "540,T2,OPEN,P1",
            "540,T1,OPEN,P1",
            "540,t1,OPEN,P1",
            "540,a,OPEN,P1",
            "540,A,OPEN,P1",
            "540,10,OPEN,P1",
            "540,2,OPEN,P1",
            "550,T10,CLOSE",
            "550,T2,CLOSE",
            "550,T1,CLOSE",
            "550,t1,CLOSE",
            "550,a,CLOSE",
            "550,A,CLOSE",
            "550,10,CLOSE",
            "550,2,CLOSE",
        ],
        [
            {"ticket_id": "10", "priority": "P1", "used_minutes": 10, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "2", "priority": "P1", "used_minutes": 10, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "A", "priority": "P1", "used_minutes": 10, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T1", "priority": "P1", "used_minutes": 10, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T10", "priority": "P1", "used_minutes": 10, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T2", "priority": "P1", "used_minutes": 10, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "a", "priority": "P1", "used_minutes": 10, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "t1", "priority": "P1", "used_minutes": 10, "breached": False, "breached_at": None, "status": "closed"},
        ],
    )

    # =========================================================================
    # 10. Large Minutes / Performance Non-loop Verification
    # =========================================================================
    check(
        "Large minutes (up to 1,000,000,000): runs efficiently without minute-by-minute loop",
        [
            # Day 625,000: 900,000,000 // 1440 = 625,000. 625,000 % 7 = 3 (Thursday).
            # Thursday 09:00 is 900,000,540.
            # Thursday 10:00 is 900,000,600.
            "900000540,LARGE,OPEN,P1",
            "900000600,LARGE,CLOSE",
            # Another ticket with large minute setting 'now' to 1,000,000,000
            "1000000000,FAR,OPEN,P1",
            "1000000000,FAR,CLOSE",
        ],
        [
            {
                "ticket_id": "FAR",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "LARGE",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
        ],
    )

    # =========================================================================
    # 11. Type & Key Strict Validation
    # =========================================================================
    total_tests += 1
    sample_out = solution.compute_sla(["540,TYPE_CHECK,OPEN,P1", "781,TYPE_CHECK,CLOSE"])
    if not isinstance(sample_out, list):
        failures.append(f"FAIL: Return type must be list, got {type(sample_out)}")
    elif len(sample_out) != 1:
        failures.append(f"FAIL: Expected 1 ticket in output, got {len(sample_out)}")
    else:
        d = sample_out[0]
        expected_keys = {"ticket_id", "priority", "used_minutes", "breached", "breached_at", "status"}
        if set(d.keys()) != expected_keys:
            failures.append(f"FAIL: Keys mismatch. Expected {expected_keys}, got {set(d.keys())}")
        elif not (
            isinstance(d["ticket_id"], str)
            and isinstance(d["priority"], str)
            and isinstance(d["used_minutes"], int)
            and isinstance(d["breached"], bool)
            and isinstance(d["breached_at"], int)
            and isinstance(d["status"], str)
        ):
            failures.append(f"FAIL: Value types incorrect in dict {d}")
        else:
            passed_tests += 1

    # =========================================================================
    # Summary & Exit
    # =========================================================================
    print("=" * 60)
    print(f"Business-Hours SLA Clock Adversarial Test Suite")
    print(f"Total tests run: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {len(failures)}")
    print("=" * 60)

    if failures:
        print("\nFailures encountered:\n")
        for f in failures:
            print(f)
            print("-" * 40)
        sys.exit(1)
    else:
        print("ALL TESTS PASSED SUCCESSFULLY.")
        sys.exit(0)


if __name__ == "__main__":
    run_tests()