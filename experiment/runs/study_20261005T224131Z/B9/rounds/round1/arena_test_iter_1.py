import solution
import sys
import time

def check(actual, expected, test_name):
    assert isinstance(actual, list), f"[{test_name}] Output is not a list: {type(actual)}"
    assert len(actual) == len(expected), (
        f"[{test_name}] Output length mismatch: got {len(actual)}, expected {len(expected)}.\n"
        f"  Got:      {actual}\n"
        f"  Expected: {expected}"
    )
    for i, (act, exp) in enumerate(zip(actual, expected)):
        assert isinstance(act, dict), f"[{test_name}] Item {i} is not a dict: {type(act)}"
        expected_keys = {"ticket_id", "priority", "used_minutes", "breached", "breached_at", "status"}
        assert set(act.keys()) == expected_keys, f"[{test_name}] Keys mismatch at {i}: {act.keys()} != {expected_keys}"
        assert isinstance(act["ticket_id"], str), f"[{test_name}] ticket_id not str: {type(act['ticket_id'])}"
        assert isinstance(act["priority"], str) and act["priority"] in {"P1", "P2", "P3", "P4"}, (
            f"[{test_name}] Invalid priority: {act.get('priority')}"
        )
        assert type(act["used_minutes"]) is int, f"[{test_name}] used_minutes not int: {type(act['used_minutes'])}"
        assert type(act["breached"]) is bool, f"[{test_name}] breached not bool: {type(act['breached'])}"
        if act["breached"]:
            assert type(act["breached_at"]) is int, (
                f"[{test_name}] breached_at must be int when breached=True, got {type(act['breached_at'])}"
            )
        else:
            assert act["breached_at"] is None, (
                f"[{test_name}] breached_at must be None when breached=False, got {act['breached_at']}"
            )
        assert act["status"] in {"running", "paused", "closed"}, f"[{test_name}] Invalid status: {act['status']}"
        assert act == exp, f"[{test_name}] Mismatch at index {i}:\n  Got:      {act}\n  Expected: {exp}"

def test_specification_examples():
    # Example 1
    res1 = solution.compute_sla([
        "540,A,OPEN,P2",
        "600,A,CLOSE",
    ])
    check(res1, [{
        "ticket_id": "A",
        "priority": "P2",
        "used_minutes": 60,
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "Spec Example 1")

    # Example 2
    res2 = solution.compute_sla([
        "6720,B,OPEN,P1",
        "10680,B,PAUSE",
    ])
    check(res2, [{
        "ticket_id": "B",
        "priority": "P1",
        "used_minutes": 120,
        "breached": False,
        "breached_at": None,
        "status": "paused",
    }], "Spec Example 2")

    # Example 3
    res3 = solution.compute_sla([
        "540,C,OPEN,P1",
        "900,C,CLOSE",
    ])
    check(res3, [{
        "ticket_id": "C",
        "priority": "P1",
        "used_minutes": 360,
        "breached": True,
        "breached_at": 781,
        "status": "closed",
    }], "Spec Example 3")

    # Example 4
    res4 = solution.compute_sla([
        "540,D,OPEN,P3",
        "2040,D,PAUSE",
        "open,D,RESUME",
        "2100,D,RESUME,P1",
        "5,*,HOLIDAY",
    ])
    check(res4, [{
        "ticket_id": "D",
        "priority": "P3",
        "used_minutes": 60,
        "breached": False,
        "breached_at": None,
        "status": "paused",
    }], "Spec Example 4")

def test_malformed_and_empty_inputs():
    # Empty stream
    check(solution.compute_sla([]), [], "Empty stream")

    # Whitespace only lines
    check(solution.compute_sla(["", "   ", "\t\t", "\n", "  \r\n  "]), [], "Whitespace only lines")

    # Various malformed lines that must be completely ignored
    malformed_lines = [
        "not,a,valid,csv,at,all",
        "540,T1",                           # only 2 fields
        "540,T1,OPEN",                      # OPEN needs 4 fields
        "540,T1,PRIORITY",                  # PRIORITY needs 4 fields
        "540,T1,OPEN,P1,EXTRA",             # OPEN 5 fields
        "540,T1,PRIORITY,P1,EXTRA",         # PRIORITY 5 fields
        "540,T1,PAUSE,P1",                  # PAUSE with 4 fields
        "540,T1,RESUME,P1",                 # RESUME with 4 fields
        "540,T1,CLOSE,P1",                  # CLOSE with 4 fields
        "540,T1,REOPEN,P1",                 # REOPEN with 4 fields
        "540,*,HOLIDAY,EXTRA",              # HOLIDAY with 4 fields
        "abc,T1,OPEN,P1",                   # non-digit minute
        "-50,T1,OPEN,P1",                   # negative minute
        "+540,T1,OPEN,P1",                  # minute with '+'
        "540.0,T1,OPEN,P1",                 # float minute
        "5 40,T1,OPEN,P1",                  # space inside minute
        ",T1,OPEN,P1",                      # empty minute
        "540,,OPEN,P1",                     # empty ticket ID
        "540,   ,OPEN,P1",                  # whitespace ticket ID
        "540,*,OPEN,P1",                    # non-holiday event with ID '*'
        "540,*,PAUSE",                      # PAUSE with ID '*'
        "540,*,CLOSE",                      # CLOSE with ID '*'
        "540,T1,HOLIDAY",                   # HOLIDAY with non-'*' ID
        "540,T1,open,P1",                   # lowercase event
        "540,T1,pause",                     # lowercase event
        "540,T1,START,P1",                  # unknown event
        "540,T1,OPEN,P0",                   # invalid priority P0
        "540,T1,OPEN,P5",                   # invalid priority P5
        "540,T1,OPEN,p1",                   # lowercase priority
        "540,T1,OPEN,P 1",                  # space in priority
    ]
    check(solution.compute_sla(malformed_lines), [], "All malformed lines")

    # Only holiday lines -> return []
    check(solution.compute_sla(["0,*,HOLIDAY", "1000,*,HOLIDAY"]), [], "Only holiday lines")

    # Only events on tickets never opened -> return []
    check(solution.compute_sla([
        "600,T1,PAUSE",
        "700,T1,RESUME",
        "800,T1,CLOSE",
        "900,T1,REOPEN",
        "1000,T1,PRIORITY,P1",
    ]), [], "Events on ticket never opened")

def test_transition_table_complete_matrix():
    # 1. NOT_OPENED state:
    # - PRIORITY ignored
    # - PAUSE ignored
    # - RESUME ignored
    # - CLOSE ignored
    # - REOPEN ignored
    check(solution.compute_sla([
        "500,T,PRIORITY,P2",
        "510,T,PAUSE",
        "520,T,RESUME",
        "525,T,CLOSE",
        "530,T,REOPEN",
        "540,T,OPEN,P1",
        "600,T,CLOSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 60,
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "NOT_OPENED invalid transitions ignored before valid OPEN")

    # 2. RUNNING state:
    # - OPEN ignored
    # - RESUME ignored
    # - REOPEN ignored
    # - PRIORITY applied
    # - PAUSE applied
    # - CLOSE applied
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "560,T,OPEN,P3",      # ignored, priority remains P1, used not reset
        "580,T,RESUME",       # ignored
        "600,T,REOPEN",       # ignored
        "620,T,PRIORITY,P2",  # priority becomes P2
        "680,T,CLOSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P2",
        "used_minutes": 140,  # 680 - 540 = 140
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "RUNNING invalid transitions ignored, valid applied")

    # 3. PAUSED state:
    # - OPEN ignored
    # - PAUSE ignored
    # - REOPEN ignored
    # - PRIORITY applied
    # - RESUME applied
    # - CLOSE applied
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "600,T,PAUSE",        # to PAUSED (used: 60)
        "620,T,OPEN,P4",      # ignored
        "640,T,PAUSE",        # ignored
        "650,T,REOPEN",       # ignored
        "660,T,PRIORITY,P2",  # priority becomes P2
        "700,T,RESUME",       # to RUNNING
        "750,T,PAUSE",        # to PAUSED (used: 60 + 50 = 110)
        "780,T,CLOSE",        # to CLOSED from PAUSED
    ]), [{
        "ticket_id": "T",
        "priority": "P2",
        "used_minutes": 110,
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "PAUSED transitions verified")

    # 4. CLOSED state:
    # - PRIORITY ignored
    # - PAUSE ignored
    # - RESUME ignored
    # - CLOSE ignored
    # - REOPEN applied (continues used, keeps breach, keeps priority)
    # - OPEN applied (resets used to 0, clears breach, new priority)
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "600,T,CLOSE",
        "620,T,PRIORITY,P4",  # ignored
        "640,T,PAUSE",        # ignored
        "660,T,RESUME",       # ignored
        "680,T,CLOSE",        # ignored
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 60,
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "CLOSED ignored events")

def test_exact_sla_boundaries():
    # Monday 09:00 is 540.
    # P1 limit: 240
    # Exactly 240 business minutes: 540 + 240 = 780.
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "780,T,PAUSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 240,
        "breached": False,
        "breached_at": None,
        "status": "paused",
    }], "P1 exact limit 240 (not breached)")

    # Exactly 241 business minutes: 540 + 241 = 781.
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "781,T,PAUSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 241,
        "breached": True,
        "breached_at": 781,
        "status": "paused",
    }], "P1 exact breach at 241")

    # P2 limit: 480 (full business day: 540 to 1020 is 480 mins)
    # Paused at 17:00 (1020)
    check(solution.compute_sla([
        "540,T,OPEN,P2",
        "1020,T,PAUSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P2",
        "used_minutes": 480,
        "breached": False,
        "breached_at": None,
        "status": "paused",
    }], "P2 exact limit 480 at 17:00 (not breached)")

    # Running overnight into Tuesday 09:00 (1980) -> still 480 used
    check(solution.compute_sla([
        "540,T,OPEN,P2",
        "1980,T,PAUSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P2",
        "used_minutes": 480,
        "breached": False,
        "breached_at": None,
        "status": "paused",
    }], "P2 overnight to Tue 09:00 (480 used, not breached)")

    # Running into Tuesday 09:01 (1981) -> 481 used -> breaches at 1981
    check(solution.compute_sla([
        "540,T,OPEN,P2",
        "1981,T,PAUSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P2",
        "used_minutes": 481,
        "breached": True,
        "breached_at": 1981,
        "status": "paused",
    }], "P2 breach at Tue 09:01 (1981)")

    # P3 limit: 1440 (3 full business days: Mon, Tue, Wed)
    # Wed 17:00 is 2 * 1440 + 1020 = 3900. Used: 1440.
    check(solution.compute_sla([
        "540,T,OPEN,P3",
        "3900,T,PAUSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P3",
        "used_minutes": 1440,
        "breached": False,
        "breached_at": None,
        "status": "paused",
    }], "P3 exact limit 1440 at Wed 17:00 (not breached)")

    # Thursday 09:01 is 3 * 1440 + 541 = 4861. Used: 1441.
    check(solution.compute_sla([
        "540,T,OPEN,P3",
        "4861,T,PAUSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P3",
        "used_minutes": 1441,
        "breached": True,
        "breached_at": 4861,
        "status": "paused",
    }], "P3 breach at Thu 09:01 (4861)")

    # P4 limit: 2400 (5 full business days: Mon-Fri)
    # Friday 17:00 is 4 * 1440 + 1020 = 6780. Used: 2400.
    check(solution.compute_sla([
        "540,T,OPEN,P4",
        "6780,T,PAUSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P4",
        "used_minutes": 2400,
        "breached": False,
        "breached_at": None,
        "status": "paused",
    }], "P4 exact limit 2400 at Fri 17:00 (not breached)")

    # Next Monday 09:00 is 7 * 1440 + 540 = 10620. Weekend added 0 used minutes.
    check(solution.compute_sla([
        "540,T,OPEN,P4",
        "10620,T,PAUSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P4",
        "used_minutes": 2400,
        "breached": False,
        "breached_at": None,
        "status": "paused",
    }], "P4 across weekend at next Mon 09:00 (2400 used, not breached)")

    # Next Monday 09:01 is 10621. Used: 2401 -> breached at 10621!
    check(solution.compute_sla([
        "540,T,OPEN,P4",
        "10621,T,PAUSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P4",
        "used_minutes": 2401,
        "breached": True,
        "breached_at": 10621,
        "status": "paused",
    }], "P4 breach at next Mon 09:01 (10621)")

def test_priority_changes_and_breach_mechanics():
    # Priority raise at the exact breach minute prevents breach
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "781,T,PRIORITY,P2",  # at 781, used is 241, new limit is 480 -> no breach!
        "800,T,PAUSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P2",
        "used_minutes": 260,
        "breached": False,
        "breached_at": None,
        "status": "paused",
    }], "Priority raise at exact breach minute prevents breach")

    # Priority downgrade causes immediate breach while PAUSED
    check(solution.compute_sla([
        "540,T,OPEN,P2",
        "800,T,PAUSE",        # used = 260
        "900,T,PRIORITY,P1",  # limit becomes 240; 260 > 240 -> breach at 900!
        "950,T,CLOSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 260,
        "breached": True,
        "breached_at": 900,
        "status": "closed",
    }], "Priority downgrade causes immediate breach while PAUSED")

    # Priority downgrade outside business hours causes immediate breach
    # Mon 18:20 is minute 1100 (non-business minute)
    check(solution.compute_sla([
        "540,T,OPEN,P2",
        "840,T,PAUSE",        # used = 300
        "1100,T,PRIORITY,P1", # non-business minute, limit 240; 300 > 240 -> breach at 1100!
        "1200,T,CLOSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 300,
        "breached": True,
        "breached_at": 1100,
        "status": "closed",
    }], "Priority downgrade outside business hours breaches immediately")

    # Breach is sticky: later PRIORITY raise does not clear breach
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "800,T,PAUSE",        # breached at 781
        "900,T,PRIORITY,P4",  # limit becomes 2400, but breach is sticky!
        "1000,T,CLOSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P4",
        "used_minutes": 260,
        "breached": True,
        "breached_at": 781,
        "status": "closed",
    }], "Breach is sticky despite later priority raise")

    # Same minute priority oscillation: check after ALL events at minute applied
    check(solution.compute_sla([
        "540,T,OPEN,P2",
        "800,T,PAUSE",        # used = 260
        "900,T,PRIORITY,P1",  # temporarily P1 (limit 240)
        "900,T,PRIORITY,P3",  # final priority at 900 is P3 (limit 1440) -> no breach!
        "950,T,CLOSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P3",
        "used_minutes": 260,
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "Multiple priority changes at same minute evaluate net state")

def test_reopen_and_open_from_closed():
    # REOPEN keeps used time, keeps breach, keeps priority
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "800,T,CLOSE",        # breached at 781, used = 260
        "900,T,REOPEN",       # continues running with used = 260, breach kept
        "960,T,CLOSE",        # used = 260 + 60 = 320
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 320,
        "breached": True,
        "breached_at": 781,
        "status": "closed",
    }], "REOPEN continues used time and keeps breach")

    # OPEN from CLOSED resets used to 0, clears breach, sets new priority
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "800,T,CLOSE",        # breached at 781
        "900,T,OPEN,P2",      # resets used to 0, clears breach!
        "960,T,CLOSE",        # used = 60
    ]), [{
        "ticket_id": "T",
        "priority": "P2",
        "used_minutes": 60,
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "OPEN from CLOSED clears breach and resets used minutes")

    # OPEN from CLOSED, clears breach, then breaches AGAIN later
    # Mon 900 to 1020 = 120 mins.
    # Tue starts 1980. Needs 121 mins on Tue to reach 241 -> 1980 + 121 = 2101!
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "800,T,CLOSE",        # first breach at 781
        "900,T,OPEN,P1",      # cleared, used resets to 0
        "2105,T,CLOSE",       # Tue 11:05. Used = 120 + (2105 - 1980) = 245
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 245,
        "breached": True,
        "breached_at": 2101,  # new breach time, not 781
        "status": "closed",
    }], "OPEN from CLOSED clears breach and breaches again with new breached_at")

def test_same_minute_ties_and_ordering():
    # 1. Ticket is CLOSED.
    # Stream order: REOPEN then PRIORITY,P1
    # At 900: REOPEN to RUNNING, then PRIORITY,P1 applies.
    # Used is 260 > 240 -> breaches at 900!
    check(solution.compute_sla([
        "540,T,OPEN,P2",
        "800,T,CLOSE",
        "900,T,REOPEN",
        "900,T,PRIORITY,P1",
        "900,T,CLOSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 260,
        "breached": True,
        "breached_at": 900,
        "status": "closed",
    }], "Same minute: REOPEN then PRIORITY causes breach")

    # 2. Ticket is CLOSED.
    # Stream order: PRIORITY,P1 then REOPEN
    # At 900: PRIORITY,P1 is IGNORED because ticket is CLOSED!
    # Then REOPEN to RUNNING with priority still P2!
    # Used is 260 <= 480 -> NOT breached!
    check(solution.compute_sla([
        "540,T,OPEN,P2",
        "800,T,CLOSE",
        "900,T,PRIORITY,P1",  # ignored while closed
        "900,T,REOPEN",
        "900,T,CLOSE",
    ]), [{
        "ticket_id": "T",
        "priority": "P2",
        "used_minutes": 260,
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "Same minute: PRIORITY while closed ignored, then REOPEN")

    # 3. Stable sort with out-of-order minutes:
    check(solution.compute_sla([
        "700,T,CLOSE",
        "650,T,RESUME",
        "600,T,PAUSE",
        "540,T,OPEN,P1",
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 110,  # (600-540) + (700-650) = 60 + 50 = 110
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "Completely reversed stream correctly sorted and processed")

def test_definition_of_now_and_holidays():
    # 1. Holiday line with large minute NEVER affects 'now'
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "600,T,CLOSE",
        "50000,*,HOLIDAY",
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 60,
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "Holiday line never affects 'now'")

    # 2. Invalid transition DOES advance 'now'
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "600,T,CLOSE",
        "700,T,CLOSE",        # invalid transition, but valid ticket event
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 60,
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "Invalid transition advances 'now'")

    # 3. Other ticket event advances 'now', even if that ticket never had valid OPEN
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "600,T,CLOSE",
        "800,X,PAUSE",        # X never opened, not in output, but advances now to 800
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 60,
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "Unopened ticket event advances 'now'")

    # 4. Ticket RUNNING at 'now'
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "800,X,CLOSE",        # now = 800. T running 540..800 -> 260 mins -> breaches at 781
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 260,
        "breached": True,
        "breached_at": 781,
        "status": "running",
    }], "Ticket running at 'now'")

    # 5. Ticket OPEN at exactly 'now'
    check(solution.compute_sla([
        "540,T,OPEN,P1",
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 0,
        "breached": False,
        "breached_at": None,
        "status": "running",
    }], "Ticket OPEN at 'now' has 0 used minutes")

def test_calendar_and_holidays():
    # 1. Retroactive holiday declared at the end of the stream
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "1000,T,PAUSE",
        "0,*,HOLIDAY",        # Day 0 is holiday -> 0 business minutes
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 0,
        "breached": False,
        "breached_at": None,
        "status": "paused",
    }], "Retroactive holiday on Day 0")

    # 2. Duplicate holiday lines have identical effect
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "1000,T,PAUSE",
        "0,*,HOLIDAY",
        "100,*,HOLIDAY",
        "1439,*,HOLIDAY",
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 0,
        "breached": False,
        "breached_at": None,
        "status": "paused",
    }], "Duplicate holidays on Day 0")

    # 3. Holiday on Tuesday (Day 1: 1440..2880)
    # Mon: 540 to 1020 = 480 mins.
    # Tue: holiday = 0 mins.
    # Wed: 3420 to 3480 = 60 mins.
    # Limit P2 = 480.
    # Breaches at Wed 09:01 (3421)!
    check(solution.compute_sla([
        "540,T,OPEN,P2",
        "3480,T,CLOSE",
        "2000,*,HOLIDAY",     # Day 1 is holiday
    ]), [{
        "ticket_id": "T",
        "priority": "P2",
        "used_minutes": 540,
        "breached": True,
        "breached_at": 3421,
        "status": "closed",
    }], "Holiday on Tuesday: breach time accounts for holiday")

    # 4. Weekend holiday (Day 5: Saturday)
    check(solution.compute_sla([
        "540,T,OPEN,P1",
        "600,T,CLOSE",
        "7200,*,HOLIDAY",     # Saturday
    ]), [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 60,
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "Holiday on weekend accepted without error")

    # 5. Multi-week spanning test with holiday
    # Week 0 Thu 15:00 is 3 * 1440 + 900 = 5220.
    # Thu: 900..1020 = 120 mins.
    # Fri: full day = 480 mins.
    # Sat, Sun: 0 mins.
    # Week 1 Mon (Day 7: 10080) is holiday.
    # Week 1 Tue: full day = 480 mins.
    # Week 1 Wed 09:00 (12960 + 540 = 13500) to 12:00 (13680) = 180 mins.
    # Total = 120 + 480 + 0 + 480 + 180 = 1260 mins.
    # P3 limit = 1440 -> not breached.
    check(solution.compute_sla([
        "5220,T,OPEN,P3",
        "13680,T,CLOSE",
        "10080,*,HOLIDAY",    # Day 7 (Week 1 Mon)
    ]), [{
        "ticket_id": "T",
        "priority": "P3",
        "used_minutes": 1260,
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "Multi-week spanning test with holiday (not breached)")

    # Same setup, but Wed closes at 16:00 (13920) -> used = 1500 > 1440.
    # Prior to Wed: 120 + 480 + 480 = 1080 used.
    # Reaches 1441 at: 1441 - 1080 = 361st business min on Wed -> 13500 + 361 = 13861!
    check(solution.compute_sla([
        "5220,T,OPEN,P3",
        "13920,T,CLOSE",
        "10080,*,HOLIDAY",
    ]), [{
        "ticket_id": "T",
        "priority": "P3",
        "used_minutes": 1500,
        "breached": True,
        "breached_at": 13861,
        "status": "closed",
    }], "Multi-week spanning test with holiday (breached at 13861)")

def test_output_sorting_and_types():
    # Tickets sorted by code-point order: "A" < "T1" < "T10" < "T2" < "a" < "t1"
    stream = [
        "540,t1,OPEN,P1",
        "540,T1,OPEN,P1",
        "540,T10,OPEN,P1",
        "540,T2,OPEN,P1",
        "540,A,OPEN,P1",
        "540,a,OPEN,P1",
        "600,t1,CLOSE",
        "600,T1,CLOSE",
        "600,T10,CLOSE",
        "600,T2,CLOSE",
        "600,A,CLOSE",
        "600,a,CLOSE",
    ]
    res = solution.compute_sla(stream)
    expected_ids = ["A", "T1", "T10", "T2", "a", "t1"]
    actual_ids = [item["ticket_id"] for item in res]
    assert actual_ids == expected_ids, f"Output sorting mismatch: {actual_ids} != {expected_ids}"

    # Verify types of all fields
    for item in res:
        assert isinstance(item["ticket_id"], str)
        assert isinstance(item["priority"], str)
        assert type(item["used_minutes"]) is int
        assert type(item["breached"]) is bool
        assert item["breached_at"] is None
        assert item["status"] == "closed"

def test_large_minutes_and_performance():
    # Minute 1,000,000,000:
    # 1,000,000,000 // 1440 = 694444 (Day 694444)
    # 694444 % 7 = 2 (Wednesday)
    # Minute-of-day = 640 (10:40 AM)
    # End at 1,000,000,600 -> minute-of-day = 1240 (20:40 PM)
    # Business hours [540, 1020) -> 1020 - 640 = 380 used minutes.
    # P1 limit: 240.
    # 241st min reached at minute-of-day: 640 + 241 = 881.
    # Breach minute: 694444 * 1440 + 881 = 1000000241!
    t0 = time.perf_counter()
    res = solution.compute_sla([
        "1000000000,T,OPEN,P1",
        "1000000600,T,CLOSE",
    ])
    t1 = time.perf_counter()
    assert t1 - t0 < 2.0, f"Large minute test too slow: {t1 - t0:.2f}s (must not count minute by minute)"
    check(res, [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 380,
        "breached": True,
        "breached_at": 1000000241,
        "status": "closed",
    }], "Large minute SLA calculation")

    # Large minute with holiday on day 694444
    res_hol = solution.compute_sla([
        "1000000000,T,OPEN,P1",
        "1000000600,T,CLOSE",
        "1000000200,*,HOLIDAY",
    ])
    check(res_hol, [{
        "ticket_id": "T",
        "priority": "P1",
        "used_minutes": 0,
        "breached": False,
        "breached_at": None,
        "status": "closed",
    }], "Large minute with holiday")

    # Volume test: 5,000 events across 50 tickets
    events = []
    for day in range(100):
        # 10 holidays
        if day % 10 == 0:
            events.append(f"{day * 1440},*,HOLIDAY")
        # 50 ticket events per day
        for t_idx in range(50):
            tid = f"T_{t_idx:02d}"
            m_open = day * 1440 + 540 + t_idx * 5
            m_close = day * 1440 + 600 + t_idx * 5
            if day == 0:
                events.append(f"{m_open},{tid},OPEN,P2")
            else:
                events.append(f"{m_open},{tid},RESUME")
            events.append(f"{m_close},{tid},PAUSE")

    t0 = time.perf_counter()
    res_vol = solution.compute_sla(events)
    t1 = time.perf_counter()
    assert t1 - t0 < 5.0, f"Volume test took {t1 - t0:.2f}s, expected < 5.0s"
    assert len(res_vol) == 50, f"Expected 50 tickets in output, got {len(res_vol)}"

def main():
    tests = [
        test_specification_examples,
        test_malformed_and_empty_inputs,
        test_transition_table_complete_matrix,
        test_exact_sla_boundaries,
        test_priority_changes_and_breach_mechanics,
        test_reopen_and_open_from_closed,
        test_same_minute_ties_and_ordering,
        test_definition_of_now_and_holidays,
        test_calendar_and_holidays,
        test_output_sorting_and_types,
        test_large_minutes_and_performance,
    ]

    passed = 0
    failed = 0
    for test in tests:
        name = test.__name__
        try:
            test()
            print(f"PASS: {name}")
            passed += 1
        except Exception as e:
            print(f"FAIL: {name} - {e}")
            failed += 1

    print("\n" + "=" * 50)
    print(f"Summary: {passed} passed, {failed} failed out of {len(tests)} test suites.")
    print("=" * 50)
    if failed == 0:
        sys.exit(0)
    else:
        sys.exit(1)

if __name__ == "__main__":
    main()