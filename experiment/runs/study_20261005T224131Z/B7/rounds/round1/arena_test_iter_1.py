import sys
import solution


def validate_schema(res):
    if not isinstance(res, list):
        raise AssertionError(f"Expected list, got {type(res)}")
    for item in res:
        if not isinstance(item, dict):
            raise AssertionError(f"Expected dict element, got {type(item)}")
        expected_keys = {"ticket_id", "priority", "used_minutes", "breached", "breached_at", "status"}
        if set(item.keys()) != expected_keys:
            raise AssertionError(f"Keys mismatch: expected {expected_keys}, got {set(item.keys())}")
        if type(item["ticket_id"]) is not str:
            raise AssertionError(f"ticket_id must be str, got {type(item['ticket_id'])}")
        if type(item["priority"]) is not str or item["priority"] not in {"P1", "P2", "P3", "P4"}:
            raise AssertionError(f"priority invalid: {item['priority']}")
        if type(item["used_minutes"]) is not int:
            raise AssertionError(f"used_minutes must be int, got {type(item['used_minutes'])}")
        if type(item["breached"]) is not bool:
            raise AssertionError(f"breached must be bool, got {type(item['breached'])}")
        if item["breached"]:
            if type(item["breached_at"]) is not int:
                raise AssertionError(f"breached_at must be int when breached, got {type(item['breached_at'])}")
        else:
            if item["breached_at"] is not None:
                raise AssertionError(f"breached_at must be None when not breached, got {item['breached_at']}")
        if type(item["status"]) is not str or item["status"] not in {"running", "paused", "closed"}:
            raise AssertionError(f"status invalid: {item['status']}")


def run_case(name, stream, expected):
    res = solution.compute_sla(stream)
    validate_schema(res)
    if res != expected:
        raise AssertionError(
            f"Test '{name}' failed!\n"
            f"Input:\n{stream}\n"
            f"Expected:\n{expected}\n"
            f"Got:\n{res}"
        )


def main():
    tests = []

    def test(name):
        def decorator(fn):
            tests.append((name, fn))
            return fn
        return decorator

    # -------------------------------------------------------------------------
    # Spec Examples
    # -------------------------------------------------------------------------
    @test("spec_example_1")
    def _():
        stream = [
            "540,A,OPEN,P2",
            "600,A,CLOSE",
        ]
        expected = [
            {"ticket_id": "A", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("spec_example_1", stream, expected)

    @test("spec_example_2")
    def _():
        stream = [
            "6720,B,OPEN,P1",
            "10680,B,PAUSE",
        ]
        expected = [
            {"ticket_id": "B", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "paused"}
        ]
        run_case("spec_example_2", stream, expected)

    @test("spec_example_3")
    def _():
        stream = [
            "540,C,OPEN,P1",
            "900,C,CLOSE",
        ]
        expected = [
            {"ticket_id": "C", "priority": "P1", "used_minutes": 360, "breached": True, "breached_at": 781, "status": "closed"}
        ]
        run_case("spec_example_3", stream, expected)

    @test("spec_example_4")
    def _():
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
        run_case("spec_example_4", stream, expected)

    # -------------------------------------------------------------------------
    # Empty, Whitespace, & No Valid Tickets
    # -------------------------------------------------------------------------
    @test("empty_stream")
    def _():
        run_case("empty_stream", [], [])

    @test("generator_stream")
    def _():
        def gen():
            yield "540,A,OPEN,P2"
            yield "600,A,CLOSE"
        expected = [
            {"ticket_id": "A", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("generator_stream", gen(), expected)

    @test("only_whitespace_and_empty_lines")
    def _():
        stream = ["", "   ", "\t\t", "\n", " \r\n "]
        run_case("only_whitespace", stream, [])

    @test("only_holiday_lines")
    def _():
        stream = ["540,*,HOLIDAY", "0,*,HOLIDAY", "2000,*,HOLIDAY"]
        run_case("only_holiday_lines", stream, [])

    @test("unopened_tickets_ignored")
    def _():
        stream = [
            "540,T1,CLOSE",
            "600,T2,PAUSE",
            "700,T3,RESUME",
            "800,T4,PRIORITY,P1",
            "900,T5,REOPEN",
        ]
        run_case("unopened_tickets_ignored", stream, [])

    # -------------------------------------------------------------------------
    # Malformed Lines
    # -------------------------------------------------------------------------
    @test("malformed_lines_variety")
    def _():
        stream = [
            "-540,A,OPEN,P1",          # negative minute
            "+540,A,OPEN,P1",          # plus sign in minute
            "540.5,A,OPEN,P1",         # float minute
            "abc,A,OPEN,P1",           # alpha minute
            ",A,OPEN,P1",              # empty minute
            "540,,OPEN,P1",            # empty ticket ID
            "540,   ,OPEN,P1",         # whitespace ticket ID
            "540,A,START,P1",          # invalid event
            "540,A,open,P1",           # lowercase event
            "540,A,OPEN,p1",           # lowercase priority
            "540,A,OPEN,P0",           # invalid priority
            "540,A,OPEN,P5",           # invalid priority
            "540,A,OPEN",              # OPEN missing priority (3 fields)
            "540,A,OPEN,P1,EXTRA",     # OPEN with 5 fields
            "540,A,PRIORITY",          # PRIORITY missing priority (3 fields)
            "540,A,PRIORITY,P1,EXTRA", # PRIORITY with 5 fields
            "540,A,PAUSE,P1",          # PAUSE with 4 fields
            "540,A,RESUME,P1",         # RESUME with 4 fields
            "540,A,CLOSE,P1",          # CLOSE with 4 fields
            "540,A,REOPEN,P1",         # REOPEN with 4 fields
            "540,*,OPEN,P1",           # non-holiday with *
            "540,*,PAUSE",             # non-holiday with *
            "540,*,CLOSE",             # non-holiday with *
            "540,A,HOLIDAY",           # holiday with non-* ticket ID
            "540,*,HOLIDAY,EXTRA",     # holiday with 4 fields
            "540,A,CLOSE,",            # trailing comma creates empty 4th field
        ]
        run_case("malformed_lines_variety", stream, [])

    @test("malformed_interspersed_with_valid")
    def _():
        stream = [
            "bad line here",
            "  00540  ,  VALID  ,  OPEN  ,  P2  ",  # leading zeros, spaces
            "540,*,OPEN,P1",                         # malformed
            "  00600  ,  VALID  ,  CLOSE  ",        # leading zeros, spaces
            ",,",                                    # malformed
        ]
        expected = [
            {"ticket_id": "VALID", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("malformed_interspersed_with_valid", stream, expected)

    # -------------------------------------------------------------------------
    # All 24 Cells of the State Transition Table
    # -------------------------------------------------------------------------
    @test("transitions_not_opened_row")
    def _():
        # NOT_OPENED:
        # OPEN -> RUNNING, priority P, used 0
        # PRIORITY, PAUSE, RESUME, CLOSE, REOPEN -> ignored
        stream = [
            "500,T,PRIORITY,P1",  # ignored
            "510,T,PAUSE",        # ignored
            "520,T,RESUME",       # ignored
            "530,T,CLOSE",        # ignored
            "535,T,REOPEN",       # ignored
            "540,T,OPEN,P2",      # valid -> RUNNING, P2
            "600,T,CLOSE",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("transitions_not_opened_row", stream, expected)

    @test("transitions_running_row")
    def _():
        # RUNNING:
        # OPEN -> ignored
        # PRIORITY -> priority P
        # PAUSE -> PAUSED
        # RESUME -> ignored
        # CLOSE -> CLOSED
        # REOPEN -> ignored
        stream = [
            "540,T,OPEN,P1",      # RUNNING, P1
            "550,T,OPEN,P3",      # ignored (stays RUNNING, P1)
            "560,T,RESUME",       # ignored
            "570,T,REOPEN",       # ignored
            "580,T,PRIORITY,P2",  # priority becomes P2
            "600,T,CLOSE",        # to CLOSED
        ]
        expected = [
            {"ticket_id": "T", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("transitions_running_row", stream, expected)

    @test("transitions_paused_row")
    def _():
        # PAUSED:
        # OPEN -> ignored
        # PRIORITY -> priority P
        # PAUSE -> ignored
        # RESUME -> RUNNING
        # CLOSE -> CLOSED
        # REOPEN -> ignored
        stream = [
            "540,T,OPEN,P1",      # RUNNING
            "600,T,PAUSE",        # to PAUSED (used 60)
            "610,T,OPEN,P3",      # ignored
            "620,T,PAUSE",        # ignored
            "630,T,REOPEN",       # ignored
            "640,T,PRIORITY,P4",  # priority becomes P4
            "650,T,RESUME",       # to RUNNING
            "700,T,CLOSE",        # to CLOSED (used 60 + 50 = 110)
        ]
        expected = [
            {"ticket_id": "T", "priority": "P4", "used_minutes": 110, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("transitions_paused_row", stream, expected)

    @test("transitions_closed_row")
    def _():
        # CLOSED:
        # OPEN -> to RUNNING, priority P, used resets to 0, breach cleared
        # PRIORITY -> ignored
        # PAUSE -> ignored
        # RESUME -> ignored
        # CLOSE -> ignored
        # REOPEN -> to RUNNING, used continues, breach kept, priority kept
        stream = [
            "540,T,OPEN,P1",      # RUNNING
            "600,T,CLOSE",        # to CLOSED (used 60)
            "610,T,PRIORITY,P2",  # ignored
            "620,T,PAUSE",        # ignored
            "630,T,RESUME",       # ignored
            "640,T,CLOSE",        # ignored
            "650,T,REOPEN",       # to RUNNING (priority still P1, used continues)
            "700,T,PAUSE",        # to PAUSED (used 60 + 50 = 110)
        ]
        expected = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 110, "breached": False, "breached_at": None, "status": "paused"}
        ]
        run_case("transitions_closed_row", stream, expected)

    # -------------------------------------------------------------------------
    # SLA Exact Boundaries & Limits (P1, P2, P3, P4)
    # -------------------------------------------------------------------------
    @test("boundary_p1_exact_limit")
    def _():
        # P1 limit = 240. 540 to 780 = exactly 240 business minutes.
        stream = [
            "540,T,OPEN,P1",
            "780,T,CLOSE",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 240, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("boundary_p1_exact_limit", stream, expected)

    @test("boundary_p1_limit_plus_one")
    def _():
        # P1 limit = 240. 540 to 781 = 241 business minutes. Breach at 781.
        stream = [
            "540,T,OPEN,P1",
            "781,T,CLOSE",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 241, "breached": True, "breached_at": 781, "status": "closed"}
        ]
        run_case("boundary_p1_limit_plus_one", stream, expected)

    @test("boundary_p2_across_night_exact")
    def _():
        # P2 limit = 480. Day 0 (Mon) 540 to 1020 is exactly 480 business minutes.
        # Ticket closes at Tuesday 09:00 (minute 1980). Between 1020 and 1980 is non-business.
        stream = [
            "540,T,OPEN,P2",
            "1980,T,CLOSE",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P2", "used_minutes": 480, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("boundary_p2_across_night_exact", stream, expected)

    @test("boundary_p2_across_night_breach")
    def _():
        # Tuesday 09:01 (minute 1981): 480 + 1 = 481 business minutes. Breach at 1981.
        stream = [
            "540,T,OPEN,P2",
            "1981,T,CLOSE",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P2", "used_minutes": 481, "breached": True, "breached_at": 1981, "status": "closed"}
        ]
        run_case("boundary_p2_across_night_breach", stream, expected)

    @test("boundary_p3_exact_and_breach")
    def _():
        # P3 limit = 1440 = 3 full business days (Mon, Tue, Wed).
        # Wed business ends at 2 * 1440 + 1020 = 3900.
        # Thursday 09:00 is 3 * 1440 + 540 = 4860 (used 1440, not breached).
        # Thursday 09:01 is 4861 (used 1441, breaches at 4861).
        stream_exact = [
            "540,T,OPEN,P3",
            "4860,T,CLOSE",
        ]
        expected_exact = [
            {"ticket_id": "T", "priority": "P3", "used_minutes": 1440, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("boundary_p3_exact", stream_exact, expected_exact)

        stream_breach = [
            "540,T,OPEN,P3",
            "4861,T,CLOSE",
        ]
        expected_breach = [
            {"ticket_id": "T", "priority": "P3", "used_minutes": 1441, "breached": True, "breached_at": 4861, "status": "closed"}
        ]
        run_case("boundary_p3_breach", stream_breach, expected_breach)

    @test("boundary_p4_across_weekend_exact_and_breach")
    def _():
        # P4 limit = 2400 = 5 full business days (Mon-Fri week 0).
        # Friday ends at 4 * 1440 + 1020 = 6780.
        # Weekend has 0 business minutes.
        # Week 1 Monday 09:00 is 7 * 1440 + 540 = 10620 (used 2400, not breached).
        # Week 1 Monday 09:01 is 10621 (used 2401, breaches at 10621).
        stream_exact = [
            "540,T,OPEN,P4",
            "10620,T,CLOSE",
        ]
        expected_exact = [
            {"ticket_id": "T", "priority": "P4", "used_minutes": 2400, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("boundary_p4_exact", stream_exact, expected_exact)

        stream_breach = [
            "540,T,OPEN,P4",
            "10621,T,CLOSE",
        ]
        expected_breach = [
            {"ticket_id": "T", "priority": "P4", "used_minutes": 2401, "breached": True, "breached_at": 10621, "status": "closed"}
        ]
        run_case("boundary_p4_breach", stream_breach, expected_breach)

    # -------------------------------------------------------------------------
    # Priority Changes & Stickiness
    # -------------------------------------------------------------------------
    @test("priority_raise_at_exact_breach_minute_prevents_breach")
    def _():
        # Without raise, breaches at 781. But at 781 PRIORITY P2 raises limit to 480.
        stream = [
            "540,T,OPEN,P1",
            "781,T,PRIORITY,P2",
            "800,T,CLOSE",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P2", "used_minutes": 260, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("priority_raise_prevents_breach", stream, expected)

    @test("priority_raise_after_breach_does_not_undo_breach")
    def _():
        # Breached at 781. At 782 raised to P2. Breach is sticky!
        stream = [
            "540,T,OPEN,P1",
            "782,T,PRIORITY,P2",
            "800,T,CLOSE",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P2", "used_minutes": 260, "breached": True, "breached_at": 781, "status": "closed"}
        ]
        run_case("priority_raise_after_breach", stream, expected)

    @test("priority_downgrade_causes_immediate_breach_while_paused")
    def _():
        # Ticket runs for 300 business minutes under P2 (limit 480).
        # Pauses at 840 (540 + 300 = 840).
        # At 900, priority lowered to P1 (limit 240). Used is 300 > 240. Immediate breach at 900!
        stream = [
            "540,T,OPEN,P2",
            "840,T,PAUSE",
            "900,T,PRIORITY,P1",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 300, "breached": True, "breached_at": 900, "status": "paused"}
        ]
        run_case("priority_downgrade_while_paused", stream, expected)

    @test("priority_downgrade_causes_immediate_breach_non_business_hours")
    def _():
        # Ticket runs full Monday under P2 (used 480). Pauses at 1020 (17:00).
        # At 1200 (20:00, non-business), PRIORITY P1. Used 480 > 240. Breaches at 1200!
        stream = [
            "540,T,OPEN,P2",
            "1020,T,PAUSE",
            "1200,T,PRIORITY,P1",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 480, "breached": True, "breached_at": 1200, "status": "paused"}
        ]
        run_case("priority_downgrade_non_business_hours", stream, expected)

    # -------------------------------------------------------------------------
    # Breach Clearing vs Keeping
    # -------------------------------------------------------------------------
    @test("breach_kept_on_reopen")
    def _():
        # Breached at 781, closed at 800, reopened at 850. Breach is kept!
        stream = [
            "540,T,OPEN,P1",
            "800,T,CLOSE",
            "850,T,REOPEN",
            "900,T,PAUSE",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 310, "breached": True, "breached_at": 781, "status": "paused"}
        ]
        run_case("breach_kept_on_reopen", stream, expected)

    @test("breach_cleared_on_open_from_closed")
    def _():
        # Breached at 781, closed at 800.
        # At 850 valid OPEN P1 resets used to 0 and clears breach!
        stream = [
            "540,T,OPEN,P1",
            "800,T,CLOSE",
            "850,T,OPEN,P1",
            "900,T,PAUSE",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 50, "breached": False, "breached_at": None, "status": "paused"}
        ]
        run_case("breach_cleared_on_open", stream, expected)

    @test("breach_cleared_then_breaches_again")
    def _():
        # Breached at 781, closed at 800.
        # Re-opened from closed at 850 with P1 (breach cleared, used 0).
        # Mon 850 to 1020: 170 min used.
        # Needs 241 - 170 = 71 min on Tue.
        # Tue starts at 1980. 1980 + 71 = 2051. Breaches at 2051!
        # Closes at 2060. Total used: 170 + 80 = 250 min.
        stream = [
            "540,T,OPEN,P1",
            "800,T,CLOSE",
            "850,T,OPEN,P1",
            "2060,T,CLOSE",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 250, "breached": True, "breached_at": 2051, "status": "closed"}
        ]
        run_case("breach_cleared_then_breaches_again", stream, expected)

    # -------------------------------------------------------------------------
    # Ties & Out-of-Order Handling
    # -------------------------------------------------------------------------
    @test("ties_at_same_minute_stable_order")
    def _():
        # OPEN then PAUSE at 540 -> status at 540 is PAUSED, used during 540..600 is 0.
        # RESUME at 600 -> runs 600..660 (60 min).
        stream1 = [
            "540,T,OPEN,P1",
            "540,T,PAUSE",
            "600,T,RESUME",
            "660,T,CLOSE",
        ]
        expected1 = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("ties_open_then_pause", stream1, expected1)

        # PAUSE then OPEN at 540 -> PAUSE ignored (NOT_OPENED), OPEN makes it RUNNING.
        # Runs 540..660 (120 min).
        stream2 = [
            "540,T,PAUSE",
            "540,T,OPEN,P1",
            "660,T,CLOSE",
        ]
        expected2 = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 120, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("ties_pause_then_open", stream2, expected2)

    @test("completely_out_of_order_stream")
    def _():
        # Events given in reverse chronological order
        stream = [
            "700,T,CLOSE",
            "650,T,RESUME",
            "600,T,PAUSE",
            "540,T,OPEN,P1",
        ]
        # Runs [540, 600) = 60 min, [650, 700) = 50 min. Total = 110 min.
        expected = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 110, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("completely_out_of_order", stream, expected)

    # -------------------------------------------------------------------------
    # Definition of "Now"
    # -------------------------------------------------------------------------
    @test("now_determined_by_invalid_transition_on_other_ticket")
    def _():
        # T1 opened at 540, stays RUNNING.
        # T2 has invalid transition at 900 (never opened, CLOSE ignored).
        # 'now' is 900. T2 is NOT in output. T1 runs 540..900 = 360 min.
        # T1 breaches at 781.
        stream = [
            "540,T1,OPEN,P1",
            "900,T2,CLOSE",
        ]
        expected = [
            {"ticket_id": "T1", "priority": "P1", "used_minutes": 360, "breached": True, "breached_at": 781, "status": "running"}
        ]
        run_case("now_invalid_transition", stream, expected)

    @test("holiday_does_not_affect_now")
    def _():
        # T1 opens at 540, closes at 600.
        # HOLIDAY at minute 999999.
        # 'now' must be 600, NOT 999999!
        stream = [
            "540,T1,OPEN,P1",
            "600,T1,CLOSE",
            "999999,*,HOLIDAY",
        ]
        expected = [
            {"ticket_id": "T1", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("holiday_does_not_affect_now", stream, expected)

    # -------------------------------------------------------------------------
    # Holiday Calendar Features
    # -------------------------------------------------------------------------
    @test("holiday_on_active_day_and_duplicate_holidays")
    def _():
        # Monday (day 0) declared holiday twice.
        # Tuesday (day 1, minute 1440) is NOT holiday.
        # Ticket runs Mon 540 to Tue 10:00 (2040).
        # Mon contributes 0 min. Tue contributes 60 min (1980..2040).
        stream = [
            "0,*,HOLIDAY",
            "1000,*,HOLIDAY",
            "540,T,OPEN,P1",
            "2040,T,CLOSE",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("holiday_active_day", stream, expected)

    @test("holiday_declared_at_end_of_stream")
    def _():
        # Day 0 is holiday, declared after all ticket lines.
        stream = [
            "540,T,OPEN,P1",
            "1020,T,CLOSE",
            "10,*,HOLIDAY",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "closed"}
        ]
        run_case("holiday_declared_at_end", stream, expected)

    # -------------------------------------------------------------------------
    # Non-Business Hours & Weekends
    # -------------------------------------------------------------------------
    @test("ticket_active_across_weekend")
    def _():
        # Friday 15:00 (6660) to Monday 12:00 (10800).
        # Friday business ends at 6780 (120 min).
        # Weekend: 0 min.
        # Monday business starts at 10620. 10620 to 10800 = 180 min.
        # Total used: 120 + 180 = 300 min.
        # Under P1 (limit 240), needs 121 min on Monday to breach.
        # Monday 09:00 (10620) + 121 = 10741.
        stream = [
            "6660,T,OPEN,P1",
            "10800,T,CLOSE",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 300, "breached": True, "breached_at": 10741, "status": "closed"}
        ]
        run_case("ticket_across_weekend", stream, expected)

    @test("ticket_opened_during_weekend")
    def _():
        # Saturday 10:00 (minute 7800). Ticket opens and pauses at 7900.
        # Used = 0 business minutes.
        stream = [
            "7800,T,OPEN,P1",
            "7900,T,PAUSE",
        ]
        expected = [
            {"ticket_id": "T", "priority": "P1", "used_minutes": 0, "breached": False, "breached_at": None, "status": "paused"}
        ]
        run_case("ticket_opened_during_weekend", stream, expected)

    # -------------------------------------------------------------------------
    # Output Sorting & Case-Sensitivity
    # -------------------------------------------------------------------------
    @test("output_sorting_and_case_sensitivity")
    def _():
        # Code-point order: "A" < "T1" < "T10" < "T2" < "a"
        stream = [
            "540,T10,OPEN,P1",
            "540,T2,OPEN,P2",
            "540,T1,OPEN,P3",
            "540,a,OPEN,P4",
            "540,A,OPEN,P1",
            "600,T10,CLOSE",
            "600,T2,CLOSE",
            "600,T1,CLOSE",
            "600,a,CLOSE",
            "600,A,CLOSE",
        ]
        expected = [
            {"ticket_id": "A", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T1", "priority": "P3", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T10", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T2", "priority": "P2", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "a", "priority": "P4", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
        ]
        run_case("output_sorting", stream, expected)

    # -------------------------------------------------------------------------
    # Scalability & Large Minute Values (up to 1,000,000,000)
    # -------------------------------------------------------------------------
    @test("large_minute_values_instant_computation")
    def _():
        # Minute 500,000,220:
        # 500000220 // 1440 = 347222 days. 347222 % 7 = 3 (Thursday).
        # 347222 * 1440 = 499999680.
        # 500000220 - 499999680 = 540 (09:00).
        # 500000520 - 499999680 = 840 (14:00, 300 business minutes).
        # P1 limit = 240. Breaches at 500000220 + 241 = 500000461.
        # HOLIDAY declared at 1,000,000,000.
        stream = [
            "500000220,BIG,OPEN,P1",
            "500000520,BIG,CLOSE",
            "1000000000,*,HOLIDAY",
        ]
        expected = [
            {"ticket_id": "BIG", "priority": "P1", "used_minutes": 300, "breached": True, "breached_at": 500000461, "status": "closed"}
        ]
        run_case("large_minute_values", stream, expected)

    # -------------------------------------------------------------------------
    # Run all tests
    # -------------------------------------------------------------------------
    passed = 0
    failed = 0
    for name, fn in tests:
        try:
            fn()
            passed += 1
            print(f"[PASS] {name}")
        except Exception as e:
            failed += 1
            print(f"[FAIL] {name}: {e}")

    total = passed + failed
    print(f"\nSummary: {passed}/{total} tests passed ({failed} failed).")
    if failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()