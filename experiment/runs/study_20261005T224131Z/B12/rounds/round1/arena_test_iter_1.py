import solution
import sys


def run_tests():
    total_tests = 0
    passed_tests = 0

    def assert_eq(test_name, actual, expected):
        nonlocal total_tests, passed_tests
        total_tests += 1
        if actual != expected:
            print(f"FAIL: {test_name}")
            print(f"  Expected: {expected}")
            print(f"  Actual:   {actual}")
            return False
        passed_tests += 1
        return True

    def assert_types(test_name, result):
        nonlocal total_tests, passed_tests
        total_tests += 1
        if type(result) is not list:
            print(f"FAIL: {test_name}: return type must be list, got {type(result)}")
            return False
        required_keys = {"ticket_id", "priority", "used_minutes", "breached", "breached_at", "status"}
        for idx, item in enumerate(result):
            if type(item) is not dict:
                print(f"FAIL: {test_name}: item {idx} is not dict, got {type(item)}")
                return False
            if set(item.keys()) != required_keys:
                print(f"FAIL: {test_name}: item {idx} keys mismatch. Got {set(item.keys())}, expected {required_keys}")
                return False
            if type(item["ticket_id"]) is not str:
                print(f"FAIL: {test_name}: item {idx} ticket_id not str")
                return False
            if type(item["priority"]) is not str:
                print(f"FAIL: {test_name}: item {idx} priority not str")
                return False
            if type(item["used_minutes"]) is not int or type(item["used_minutes"]) is bool:
                print(f"FAIL: {test_name}: item {idx} used_minutes not int")
                return False
            if type(item["breached"]) is not bool:
                print(f"FAIL: {test_name}: item {idx} breached not bool")
                return False
            if item["breached_at"] is not None and (type(item["breached_at"]) is not int or type(item["breached_at"]) is bool):
                print(f"FAIL: {test_name}: item {idx} breached_at not int or None")
                return False
            if type(item["status"]) is not str or item["status"] not in ("running", "paused", "closed"):
                print(f"FAIL: {test_name}: item {idx} status invalid")
                return False
        passed_tests += 1
        return True

    all_ok = True

    # =========================================================================
    # Group 1: Specification Examples
    # =========================================================================
    # Example 1
    stream = [
        "540,A,OPEN,P2",
        "600,A,CLOSE",
    ]
    exp = [{"ticket_id": "A", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_types("Example 1 types", res)
    all_ok &= assert_eq("Example 1", res, exp)

    # Example 2
    stream = [
        "6720,B,OPEN,P1",
        "10680,B,PAUSE",
    ]
    exp = [{"ticket_id": "B", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_types("Example 2 types", res)
    all_ok &= assert_eq("Example 2", res, exp)

    # Example 3
    stream = [
        "540,C,OPEN,P1",
        "900,C,CLOSE",
    ]
    exp = [{"ticket_id": "C", "priority": "P1", "used_minutes": 360, "breached": True, "breached_at": 781, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_types("Example 3 types", res)
    all_ok &= assert_eq("Example 3", res, exp)

    # Example 4
    stream = [
        "540,D,OPEN,P3",
        "2040,D,PAUSE",
        "open,D,RESUME",
        "2100,D,RESUME,P1",
        "5,*,HOLIDAY",
    ]
    exp = [{"ticket_id": "D", "priority": "P3", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_types("Example 4 types", res)
    all_ok &= assert_eq("Example 4", res, exp)

    # =========================================================================
    # Group 2: Empty Stream and Ignored Lines
    # =========================================================================
    # Empty stream
    res = solution.compute_sla([])
    all_ok &= assert_types("Empty stream types", res)
    all_ok &= assert_eq("Empty stream", res, [])

    # Stream with only malformed lines
    stream = [
        "",
        "   ",
        "not,a,valid,csv,line",
        "-5,T,OPEN,P1",
        "540,*,OPEN,P1",
        "540,T,UNKNOWN",
    ]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Only malformed lines", res, [])

    # Stream with only HOLIDAY lines
    stream = [
        "540,*,HOLIDAY",
        "2000,*,HOLIDAY",
    ]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Only HOLIDAY lines", res, [])

    # Ticket events for tickets that were NEVER opened (all ignored)
    stream = [
        "100,X,PAUSE",
        "200,X,RESUME",
        "300,X,CLOSE",
        "400,X,REOPEN",
        "500,X,PRIORITY,P1",
    ]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Ticket never opened", res, [])

    # Ticket X never opened, but ticket Y opens; X PAUSE extends 'now'
    stream = [
        "540,Y,OPEN,P1",
        "600,Y,PAUSE",
        "700,X,PAUSE",  # Ignored transition, but well-formed ticket event: extends now to 700
    ]
    exp = [{"ticket_id": "Y", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Ignored ticket event extends now", res, exp)

    # HOLIDAY lines never extend 'now'
    stream = [
        "540,Z,OPEN,P1",
        "600,Z,CLOSE",
        "50000,*,HOLIDAY",  # HOLIDAY must NOT set 'now' to 50000
    ]
    exp = [{"ticket_id": "Z", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Holiday does not extend now", res, exp)

    # =========================================================================
    # Group 3: State Transitions - RUNNING State
    # =========================================================================
    # RUNNING: OPEN is ignored (does not change priority, does not reset used time)
    stream = [
        "540,T1,OPEN,P1",
        "600,T1,OPEN,P2",  # Ignored: priority stays P1 (limit 240)
        "781,T1,PAUSE",
    ]
    exp = [{"ticket_id": "T1", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("RUNNING: OPEN ignored", res, exp)

    # RUNNING: PRIORITY changes priority
    stream = [
        "540,T2,OPEN,P1",
        "600,T2,PRIORITY,P2",  # Priority becomes P2 (limit 480)
        "781,T2,PAUSE",
    ]
    exp = [{"ticket_id": "T2", "priority": "P2", "used_minutes": 241, "breached": False, "breached_at": None, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("RUNNING: PRIORITY changes limit", res, exp)

    # RUNNING: RESUME is ignored
    stream = [
        "540,T3,OPEN,P1",
        "600,T3,RESUME",  # Ignored
        "660,T3,CLOSE",
    ]
    exp = [{"ticket_id": "T3", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("RUNNING: RESUME ignored", res, exp)

    # RUNNING: REOPEN is ignored
    stream = [
        "540,T4,OPEN,P1",
        "600,T4,REOPEN",  # Ignored
        "660,T4,CLOSE",
    ]
    exp = [{"ticket_id": "T4", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("RUNNING: REOPEN ignored", res, exp)

    # =========================================================================
    # Group 4: State Transitions - PAUSED State
    # =========================================================================
    # PAUSED: OPEN is ignored
    stream = [
        "540,U1,OPEN,P1",
        "600,U1,PAUSE",
        "650,U1,OPEN,P2",  # Ignored: priority stays P1
        "700,U1,RESUME",
        "781,U1,CLOSE",
    ]
    # used: (600-540) + (781-700) = 60 + 81 = 141
    exp = [{"ticket_id": "U1", "priority": "P1", "used_minutes": 141, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("PAUSED: OPEN ignored", res, exp)

    # PAUSED: PRIORITY changes priority
    stream = [
        "540,U2,OPEN,P1",
        "600,U2,PAUSE",
        "650,U2,PRIORITY,P3",  # Priority becomes P3
        "700,U2,CLOSE",
    ]
    exp = [{"ticket_id": "U2", "priority": "P3", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("PAUSED: PRIORITY updates priority", res, exp)

    # PAUSED: PAUSE is ignored
    stream = [
        "540,U3,OPEN,P1",
        "600,U3,PAUSE",
        "650,U3,PAUSE",  # Ignored
        "700,U3,RESUME",
        "760,U3,CLOSE",
    ]
    # used: 60 + 60 = 120
    exp = [{"ticket_id": "U3", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("PAUSED: PAUSE ignored", res, exp)

    # PAUSED: REOPEN is ignored (stays PAUSED, does not accumulate used time)
    stream = [
        "540,U4,OPEN,P1",
        "600,U4,PAUSE",
        "650,U4,REOPEN",  # Ignored
        "700,U4,CLOSE",
    ]
    exp = [{"ticket_id": "U4", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("PAUSED: REOPEN ignored", res, exp)

    # PAUSED: CLOSE transitions to CLOSED
    stream = [
        "540,U5,OPEN,P1",
        "600,U5,PAUSE",
        "650,U5,CLOSE",
    ]
    exp = [{"ticket_id": "U5", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("PAUSED: CLOSE to closed", res, exp)

    # =========================================================================
    # Group 5: State Transitions - CLOSED State
    # =========================================================================
    # CLOSED: OPEN resets used to 0 and clears breach!
    stream = [
        "540,V1,OPEN,P1",
        "900,V1,CLOSE",  # Breached at 781, used 360
        "920,V1,OPEN,P2",  # Resets used to 0, clears breach, priority becomes P2
        "1000,V1,CLOSE",
    ]
    # used: 1000 - 920 = 80
    exp = [{"ticket_id": "V1", "priority": "P2", "used_minutes": 80, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("CLOSED: OPEN clears breach and resets used", res, exp)

    # CLOSED: PRIORITY is ignored
    stream = [
        "540,V2,OPEN,P1",
        "600,V2,CLOSE",
        "650,V2,PRIORITY,P2",  # Ignored: priority stays P1
        "700,V2,REOPEN",
        "750,V2,CLOSE",
    ]
    # used: 60 + 50 = 110
    exp = [{"ticket_id": "V2", "priority": "P1", "used_minutes": 110, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("CLOSED: PRIORITY ignored", res, exp)

    # CLOSED: PAUSE is ignored
    stream = [
        "540,V3,OPEN,P1",
        "600,V3,CLOSE",
        "650,V3,PAUSE",  # Ignored
    ]
    exp = [{"ticket_id": "V3", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("CLOSED: PAUSE ignored", res, exp)

    # CLOSED: RESUME is ignored
    stream = [
        "540,V4,OPEN,P1",
        "600,V4,CLOSE",
        "650,V4,RESUME",  # Ignored
    ]
    exp = [{"ticket_id": "V4", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("CLOSED: RESUME ignored", res, exp)

    # CLOSED: CLOSE is ignored
    stream = [
        "540,V5,OPEN,P1",
        "600,V5,CLOSE",
        "650,V5,CLOSE",  # Ignored
    ]
    exp = [{"ticket_id": "V5", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("CLOSED: CLOSE ignored", res, exp)

    # CLOSED: REOPEN keeps breach and continues used time
    stream = [
        "540,V6,OPEN,P1",
        "900,V6,CLOSE",  # Breached at 781, used 360
        "950,V6,REOPEN",  # Resumes RUNNING, breach kept, used continues
        "1000,V6,PAUSE",
    ]
    # used: 360 + 50 = 410
    exp = [{"ticket_id": "V6", "priority": "P1", "used_minutes": 410, "breached": True, "breached_at": 781, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("CLOSED: REOPEN keeps breach and continues used", res, exp)

    # CLOSED: REOPEN when not breached before CLOSE, breaches after REOPEN
    stream = [
        "540,V7,OPEN,P1",
        "700,V7,CLOSE",  # Used 160
        "750,V7,REOPEN",  # Resumes; breaches when used reaches 241 -> 750 + (241 - 160) = 831
        "850,V7,CLOSE",
    ]
    # used: 160 + 100 = 260
    exp = [{"ticket_id": "V7", "priority": "P1", "used_minutes": 260, "breached": True, "breached_at": 831, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("CLOSED: REOPEN breaches after reopening", res, exp)

    # =========================================================================
    # Group 6: Exact SLA Boundaries and Ties
    # =========================================================================
    # B1: P1 exact boundary (240 minutes) - NOT breached
    stream = [
        "540,B1,OPEN,P1",
        "780,B1,PAUSE",
    ]
    exp = [{"ticket_id": "B1", "priority": "P1", "used_minutes": 240, "breached": False, "breached_at": None, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("P1 exact limit not breached", res, exp)

    # B2: P1 exact boundary + 1 (241 minutes) - breached at 781
    stream = [
        "540,B2,OPEN,P1",
        "781,B2,PAUSE",
    ]
    exp = [{"ticket_id": "B2", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("P1 exact limit + 1 breached", res, exp)

    # B3: P2 exact boundary (480 minutes) - full Monday (540 to 1020)
    stream = [
        "540,B3,OPEN,P2",
        "1020,B3,PAUSE",
    ]
    exp = [{"ticket_id": "B3", "priority": "P2", "used_minutes": 480, "breached": False, "breached_at": None, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("P2 exact limit end of Monday not breached", res, exp)

    # B4: P2 exact boundary + 1 spanning overnight into Tuesday 09:01 (1981)
    # Monday 540..1020 (480 mins). Tuesday 09:00 is 1980. At 1981 used is 481.
    stream = [
        "540,B4,OPEN,P2",
        "1981,B4,PAUSE",
    ]
    exp = [{"ticket_id": "B4", "priority": "P2", "used_minutes": 481, "breached": True, "breached_at": 1981, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("P2 exact limit + 1 Tuesday morning", res, exp)

    # B5: Priority raise at exact breach minute prevents breach
    stream = [
        "540,B5,OPEN,P1",
        "781,B5,PRIORITY,P2",  # At 781, used is 241, limit becomes 480 -> no breach!
        "800,B5,PAUSE",
    ]
    exp = [{"ticket_id": "B5", "priority": "P2", "used_minutes": 260, "breached": False, "breached_at": None, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Priority raise at exact breach minute prevents breach", res, exp)

    # B6: Priority change to same priority at exact breach minute does NOT prevent breach
    stream = [
        "540,B6,OPEN,P1",
        "781,B6,PRIORITY,P1",
        "800,B6,PAUSE",
    ]
    exp = [{"ticket_id": "B6", "priority": "P1", "used_minutes": 260, "breached": True, "breached_at": 781, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Same priority at exact breach minute breaches", res, exp)

    # B7: Priority lowered at 781 causes immediate breach
    stream = [
        "540,B7,OPEN,P2",
        "781,B7,PRIORITY,P1",  # Used is 241 > 240
        "800,B7,PAUSE",
    ]
    exp = [{"ticket_id": "B7", "priority": "P1", "used_minutes": 260, "breached": True, "breached_at": 781, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Priority lowered while running causes immediate breach", res, exp)

    # B8: Immediate breach while PAUSED when priority lowered
    stream = [
        "540,B8,OPEN,P2",
        "800,B8,PAUSE",  # Used 260
        "850,B8,PRIORITY,P1",  # Ticket is PAUSED, priority becomes P1 (limit 240). Used 260 > 240!
        "900,B8,CLOSE",
    ]
    exp = [{"ticket_id": "B8", "priority": "P1", "used_minutes": 260, "breached": True, "breached_at": 850, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Immediate breach while PAUSED when priority lowered", res, exp)

    # B9: Priority upgrade later does NOT undo sticky breach
    stream = [
        "540,B9,OPEN,P1",
        "800,B9,PRIORITY,P4",  # Already breached at 781. Upgrade to P4 (2400) does not clear it!
        "900,B9,CLOSE",
    ]
    exp = [{"ticket_id": "B9", "priority": "P4", "used_minutes": 360, "breached": True, "breached_at": 781, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Breach sticky after later priority upgrade", res, exp)

    # =========================================================================
    # Group 7: Stable Sorting (Ties at Same Minute)
    # =========================================================================
    # S1: OPEN then PAUSE at minute 540 -> state during 540 is PAUSED -> used is 0
    stream = [
        "540,S1,OPEN,P1",
        "540,S1,PAUSE",
        "600,OTHER,OPEN,P1",
    ]
    res = solution.compute_sla(stream)
    s1_dict = next(d for d in res if d["ticket_id"] == "S1")
    exp_s1 = {"ticket_id": "S1", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "paused"}
    all_ok &= assert_eq("Same minute OPEN then PAUSE", s1_dict, exp_s1)

    # S2: OPEN then PAUSE then RESUME at minute 540 -> state during 540 is RUNNING
    stream = [
        "540,S2,OPEN,P1",
        "540,S2,PAUSE",
        "540,S2,RESUME",
        "600,S2,PAUSE",
    ]
    exp = [{"ticket_id": "S2", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Same minute OPEN then PAUSE then RESUME", res, exp)

    # S3: PAUSE then OPEN at minute 540 -> PAUSE ignored, OPEN makes it RUNNING
    stream = [
        "540,S3,PAUSE",
        "540,S3,OPEN,P1",
        "600,S3,PAUSE",
    ]
    exp = [{"ticket_id": "S3", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Same minute PAUSE then OPEN", res, exp)

    # S4: OPEN P1, CLOSE, OPEN P2 at minute 540 -> final priority P2
    stream = [
        "540,S4,OPEN,P1",
        "540,S4,CLOSE",
        "540,S4,OPEN,P2",
        "600,S4,CLOSE",
    ]
    exp = [{"ticket_id": "S4", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Same minute OPEN, CLOSE, OPEN P2", res, exp)

    # S5: PRIORITY then OPEN at minute 540 -> PRIORITY ignored, OPEN sets P1
    stream = [
        "540,S5,PRIORITY,P2",
        "540,S5,OPEN,P1",
        "600,S5,CLOSE",
    ]
    exp = [{"ticket_id": "S5", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Same minute PRIORITY then OPEN", res, exp)

    # =========================================================================
    # Group 8: Out-of-Order Events
    # =========================================================================
    # Events arriving in reverse order
    stream = [
        "1000,O1,CLOSE",
        "750,O1,RESUME",
        "650,O1,PAUSE",
        "540,O1,OPEN,P1",
    ]
    # 540..650: 110 mins. Paused 650..750. Resumes 750. Reaches 241 used at 750 + (241 - 110) = 881.
    # Total used at 1000: 110 + 250 = 360.
    exp = [{"ticket_id": "O1", "priority": "P1", "used_minutes": 360, "breached": True, "breached_at": 881, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Out-of-order reverse stream", res, exp)

    # =========================================================================
    # Group 9: Multi-day Spans, Weekends, and Holidays
    # =========================================================================
    # Ticket spanning Friday afternoon to Monday morning
    # Friday 15:40 is 4 * 1440 + 940 = 6700. Friday ends at 6780 (80 mins).
    # Weekend: 0 mins. Monday 09:00 is 10620.
    # Limit P1 = 240. Needs 160 mins on Monday: 10620 + 160 = 10780 (used 240).
    # Breaches at 10781 (used 241).
    stream = [
        "6700,W1,OPEN,P1",
        "10780,W1,PAUSE",
    ]
    exp = [{"ticket_id": "W1", "priority": "P1", "used_minutes": 240, "breached": False, "breached_at": None, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Weekend span at 240 mins not breached", res, exp)

    stream = [
        "6700,W2,OPEN,P1",
        "10781,W2,PAUSE",
    ]
    exp = [{"ticket_id": "W2", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 10781, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Weekend span at 241 mins breached Monday morning", res, exp)

    # Holiday on Monday week 1 pushes breach to Tuesday morning
    # Monday week 1 is Day 7. Holiday declared at 10500 (10500 // 1440 = 7).
    # Tuesday week 1 is Day 8: starts 8 * 1440 + 540 = 12060.
    # Needs 160 mins on Tuesday: 12060 + 160 = 12220 (used 240). Breaches at 12221.
    stream = [
        "6700,W3,OPEN,P1",
        "12221,W3,PAUSE",
        "10500,*,HOLIDAY",  # Declares Day 7 holiday
    ]
    exp = [{"ticket_id": "W3", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 12221, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Holiday shifts breach to Tuesday", res, exp)

    # Ticket opened during weekend / non-business hours
    # Sunday 14:00 is 6 * 1440 + 840 = 9480. Pauses Sunday 16:00 (9600).
    stream = [
        "9480,W4,OPEN,P1",
        "9600,W4,PAUSE",
    ]
    exp = [{"ticket_id": "W4", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Weekend open and pause has 0 used minutes", res, exp)

    # P3 boundary (limit 1440 = 3 full business days: Mon, Tue, Wed = 480 * 3 = 1440)
    # Thursday 09:00 is 3 * 1440 + 540 = 4860. At 4860 used is 1440 (not breached).
    # At 4861 used is 1441 (breached at 4861).
    stream = [
        "540,P3_1,OPEN,P3",
        "4860,P3_1,PAUSE",
    ]
    exp = [{"ticket_id": "P3_1", "priority": "P3", "used_minutes": 1440, "breached": False, "breached_at": None, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("P3 exact boundary Thursday 09:00 not breached", res, exp)

    stream = [
        "540,P3_2,OPEN,P3",
        "4861,P3_2,PAUSE",
    ]
    exp = [{"ticket_id": "P3_2", "priority": "P3", "used_minutes": 1441, "breached": True, "breached_at": 4861, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("P3 breached Thursday 09:01", res, exp)

    # P4 boundary (limit 2400 = 5 full business days = Mon..Fri = 2400 mins)
    # Friday ends at 6780. Weekend 0 mins. Monday week 1 09:00 is 10620.
    # At 10620 used is 2400 (not breached). At 10621 used is 2401 (breached at 10621).
    stream = [
        "540,P4_1,OPEN,P4",
        "10620,P4_1,PAUSE",
    ]
    exp = [{"ticket_id": "P4_1", "priority": "P4", "used_minutes": 2400, "breached": False, "breached_at": None, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("P4 exact boundary Monday week 1 09:00 not breached", res, exp)

    stream = [
        "540,P4_2,OPEN,P4",
        "10621,P4_2,PAUSE",
    ]
    exp = [{"ticket_id": "P4_2", "priority": "P4", "used_minutes": 2401, "breached": True, "breached_at": 10621, "status": "paused"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("P4 breached Monday week 1 09:01", res, exp)

    # =========================================================================
    # Group 10: Sorting Order and Case Sensitivity
    # =========================================================================
    stream = [
        "540,T2,OPEN,P1",
        "540,T10,OPEN,P1",
        "540,t1,OPEN,P1",
        "540,T1,OPEN,P1",
        "540,1,OPEN,P1",
        "540,a,OPEN,P1",
        "540,A,OPEN,P1",
        "600,T2,CLOSE",
        "600,T10,CLOSE",
        "600,t1,CLOSE",
        "600,T1,CLOSE",
        "600,1,CLOSE",
        "600,a,CLOSE",
        "600,A,CLOSE",
    ]
    expected_order = ["1", "A", "T1", "T10", "T2", "a", "t1"]
    res = solution.compute_sla(stream)
    actual_order = [d["ticket_id"] for d in res]
    all_ok &= assert_eq("Default string / code-point ordering and case-sensitivity", actual_order, expected_order)

    # =========================================================================
    # Group 11: Malformed Lines and Whitespace Trimming
    # =========================================================================
    stream = [
        "",
        "   ",
        "\t\r\n",
        "540",
        "540,M",
        "540,M,OPEN,P1,EXTRA",
        "540,M,PAUSE,EXTRA",
        "540,M,RESUME,EXTRA",
        "540,M,CLOSE,EXTRA",
        "540,M,REOPEN,EXTRA",
        "540,*,HOLIDAY,EXTRA",
        "540,M,OPEN",
        "540,M,PRIORITY",
        "540,M,open,P1",
        "540,M,Open,P1",
        "540,M,OPEN,p1",
        "540,M,OPEN,P0",
        "540,M,OPEN,P5",
        "540,M,OPEN,HIGH",
        "540,M,OPEN,",
        "540,M,OPEN,   ",
        "540,M,PRIORITY,p1",
        "540,M,PRIORITY,P5",
        "540,*,OPEN,P1",
        "540,*,PAUSE",
        "540,*,RESUME",
        "540,*,CLOSE",
        "540,*,REOPEN",
        "540,*,PRIORITY,P1",
        "540,M,HOLIDAY",
        "-540,M,OPEN,P1",
        "+540,M,OPEN,P1",
        "540.0,M,OPEN,P1",
        "abc,M,OPEN,P1",
        ",M,OPEN,P1",
        "  ,M,OPEN,P1",
        "540,,OPEN,P1",
        "540,   ,OPEN,P1",
        "540,M,pause",
        "540,M,Resume",
        "540,M,close",
        "540,M,Reopen",
        "540,*,holiday",
        "540,M,UNKNOWN",
        "540,M,UNKNOWN,P1",
        "540,M,PAUSE,",
        "540,M,OPEN,P1,",
        "  00540  ,  VALID  ,  OPEN  ,  P2  ",
        " \t 00600 \t , \t VALID \t , \t CLOSE \t ",
    ]
    exp = [{"ticket_id": "VALID", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Exhaustive malformed line filter and whitespace trimming", res, exp)

    # =========================================================================
    # Group 12: Large Minutes & Performance
    # =========================================================================
    # 1000 full weeks elapsed from week 0 Monday 09:00 (540) to week 1000 Monday 09:00 (10080540).
    # 1000 weeks * 2400 business mins = 2,400,000 mins.
    # Minus 1 holiday on Tuesday of week 500 (Day 3501, minute 3501 * 1440 = 5041440): -480 mins.
    # Used = 2,399,520 mins. Breached at 781.
    stream = [
        "540,BIG,OPEN,P1",
        "10080540,BIG,CLOSE",
        "5041440,*,HOLIDAY",
    ]
    exp = [{"ticket_id": "BIG", "priority": "P1", "used_minutes": 2399520, "breached": True, "breached_at": 781, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Large timestamp 10,080,540 spanning 1000 weeks", res, exp)

    # Large minute near 1,000,000,000
    # Day 694444 (Friday). Minute 540 to 600.
    stream = [
        "999999900,BIG2,OPEN,P4",
        "999999960,BIG2,CLOSE",
    ]
    exp = [{"ticket_id": "BIG2", "priority": "P4", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    res = solution.compute_sla(stream)
    all_ok &= assert_eq("Timestamp near 1 billion", res, exp)

    # Performance: 4000 junk/holiday lines + 1 valid ticket
    perf_stream = []
    for i in range(2000):
        perf_stream.append(f"{i * 1440 + 50},*,HOLIDAY")
        perf_stream.append("invalid,line,format")
    perf_stream.append("540,PERF,OPEN,P1")
    perf_stream.append("600,PERF,CLOSE")
    res = solution.compute_sla(perf_stream)
    exp = [{"ticket_id": "PERF", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}]
    all_ok &= assert_eq("Performance stream with 4000 lines", res, exp)

    # Summary
    print(f"\nTest Summary: {passed_tests}/{total_tests} passed.")
    if all_ok and passed_tests == total_tests:
        print("ALL TESTS PASSED.")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED.")
        sys.exit(1)


if __name__ == "__main__":
    run_tests()