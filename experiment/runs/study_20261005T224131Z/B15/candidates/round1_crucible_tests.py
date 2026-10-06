import sys
import solution


def check_result(test_name, actual, expected):
    if not isinstance(actual, list):
        return False, f"Expected list, got {type(actual).__name__}"
    if len(actual) != len(expected):
        return (
            False,
            f"Expected {len(expected)} items, got {len(actual)}.\n"
            f"Expected: {expected}\nActual:   {actual}",
        )
    expected_keys = {
        "ticket_id",
        "priority",
        "used_minutes",
        "breached",
        "breached_at",
        "status",
    }
    for i, (act, exp) in enumerate(zip(actual, expected)):
        if not isinstance(act, dict):
            return False, f"Item {i} is not a dict: {act!r}"
        if set(act.keys()) != expected_keys:
            return (
                False,
                f"Item {i} keys mismatch. Expected {expected_keys}, got {set(act.keys())}",
            )
        for key in expected_keys:
            act_val = act[key]
            exp_val = exp[key]
            if act_val != exp_val or type(act_val) is not type(exp_val):
                return (
                    False,
                    f"Item {i} ({exp.get('ticket_id', 'unknown')}) field '{key}' mismatch:\n"
                    f"  Expected: {exp_val!r} (type {type(exp_val).__name__})\n"
                    f"  Actual:   {act_val!r} (type {type(act_val).__name__})",
                )
    return True, "OK"


def run_tests():
    tests = []

    # -------------------------------------------------------------------------
    # Spec Examples
    # -------------------------------------------------------------------------
    def test_spec_example_1():
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
        return stream, expected

    tests.append(("Spec Example 1 (Basic SLA)", test_spec_example_1))

    def test_spec_example_2():
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
        return stream, expected

    tests.append(("Spec Example 2 (Business hours across weekend)", test_spec_example_2))

    def test_spec_example_3():
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
        return stream, expected

    tests.append(("Spec Example 3 (Breach minute calculation)", test_spec_example_3))

    def test_spec_example_4():
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
        return stream, expected

    tests.append(("Spec Example 4 (Holiday and malformed line handling)", test_spec_example_4))

    # -------------------------------------------------------------------------
    # Empty & Malformed Streams
    # -------------------------------------------------------------------------
    def test_empty_stream():
        return [], []

    tests.append(("Empty stream returns []", test_empty_stream))

    def test_only_whitespace_lines():
        stream = ["", "   ", "\t  \r\n", " \n "]
        return stream, []

    tests.append(("Whitespace-only stream returns []", test_only_whitespace_lines))

    def test_only_holiday_lines():
        stream = ["0,*,HOLIDAY", "1440,*,HOLIDAY", "2880,*,HOLIDAY"]
        return stream, []

    tests.append(("Only holiday lines in stream returns []", test_only_holiday_lines))

    def test_malformed_variations():
        stream = [
            "-10,A,OPEN,P1",
            "+540,A,OPEN,P1",
            "540.0,A,OPEN,P1",
            "abc,A,OPEN,P1",
            "540,,OPEN,P1",
            "540,*,OPEN,P1",
            "540,A,HOLIDAY",
            "540,*,HOLIDAY,EXTRA",
            "540,*,CLOSE",
            "540,A,INVALID,P1",
            "540,A,open,P1",
            "540,A,OPEN,p1",
            "540,A,OPEN,P5",
            "540,A,OPEN,P0",
            "540,A,OPEN",
            "540,A,OPEN,P1,EXTRA",
            "540,A,PRIORITY",
            "540,A,PRIORITY,P1,EXTRA",
            "540,A,PAUSE,EXTRA",
            "540,A,RESUME,EXTRA",
            "540,A,CLOSE,EXTRA",
            "540,A,REOPEN,EXTRA",
            "540,A,OPEN,P1",
            "600,A,CLOSE",
        ]
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
        return stream, expected

    tests.append(("Malformed record filtering", test_malformed_variations))

    def test_leading_zeros_and_zero_minute():
        stream = [
            "00000, T_ZERO , OPEN , P1 ",
            "000540, T_ZERO , PAUSE ",
            "000600, T_ZERO , CLOSE ",
        ]
        expected = [
            {
                "ticket_id": "T_ZERO",
                "priority": "P1",
                "used_minutes": 0,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ]
        return stream, expected

    tests.append(("Leading zeros and minute 0", test_leading_zeros_and_zero_minute))

    # -------------------------------------------------------------------------
    # Definition of 'now'
    # -------------------------------------------------------------------------
    def test_now_includes_ignored_ticket_events():
        stream = [
            "540,T_VALID,OPEN,P1",
            "600,T_VALID,PAUSE",
            "800,T_NEVER_OPEN,PAUSE",
        ]
        expected = [
            {
                "ticket_id": "T_VALID",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ]
        return stream, expected

    tests.append(("Now includes ignored ticket events", test_now_includes_ignored_ticket_events))

    def test_now_ignores_holiday_lines():
        stream = [
            "540,T1,OPEN,P1",
            "600,T1,PAUSE",
            "1000000,*,HOLIDAY",
        ]
        expected = [
            {
                "ticket_id": "T1",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            }
        ]
        return stream, expected

    tests.append(("Now is never affected by HOLIDAY records", test_now_ignores_holiday_lines))

    # -------------------------------------------------------------------------
    # Out of order & Stable sort ties
    # -------------------------------------------------------------------------
    def test_out_of_order_stream():
        stream = [
            "700, T1, CLOSE",
            "600, T1, RESUME",
            "570, T1, PAUSE",
            "540, T1, OPEN, P1",
        ]
        expected = [
            {
                "ticket_id": "T1",
                "priority": "P1",
                "used_minutes": 130,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ]
        return stream, expected

    tests.append(("Out-of-order ticket event sorting", test_out_of_order_stream))

    def test_stable_sort_same_minute():
        stream = [
            "600, T_SAME, CLOSE",
            "540, T_SAME, PAUSE",
            "540, T_SAME, OPEN, P1",
        ]
        expected = [
            {
                "ticket_id": "T_SAME",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ]
        return stream, expected

    tests.append(("Stable sort for events at same minute", test_stable_sort_same_minute))

    # -------------------------------------------------------------------------
    # State Transitions Exhaustive Coverage
    # -------------------------------------------------------------------------
    def test_state_transitions_not_opened():
        stream = [
            "540, T_NO1, PRIORITY, P1",
            "540, T_NO2, PAUSE",
            "540, T_NO3, RESUME",
            "540, T_NO4, CLOSE",
            "540, T_NO5, REOPEN",
            "600, T_OK, OPEN, P1",
            "660, T_OK, CLOSE",
        ]
        expected = [
            {
                "ticket_id": "T_OK",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            }
        ]
        return stream, expected

    tests.append(("Transitions from NOT_OPENED", test_state_transitions_not_opened))

    def test_state_transitions_running():
        stream = [
            "540, T_RUN_OPEN, OPEN, P1",
            "560, T_RUN_OPEN, OPEN, P2",
            "600, T_RUN_OPEN, CLOSE",
            "540, T_RUN_PRIO, OPEN, P1",
            "560, T_RUN_PRIO, PRIORITY, P2",
            "600, T_RUN_PRIO, CLOSE",
            "540, T_RUN_REOPEN, OPEN, P1",
            "560, T_RUN_REOPEN, REOPEN",
            "600, T_RUN_REOPEN, CLOSE",
            "540, T_RUN_RESUME, OPEN, P1",
            "560, T_RUN_RESUME, RESUME",
            "600, T_RUN_RESUME, CLOSE",
        ]
        expected = [
            {
                "ticket_id": "T_RUN_OPEN",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T_RUN_PRIO",
                "priority": "P2",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T_RUN_REOPEN",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T_RUN_RESUME",
                "priority": "P1",
                "used_minutes": 60,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
        ]
        return stream, expected

    tests.append(("Transitions from RUNNING", test_state_transitions_running))

    def test_state_transitions_paused():
        stream = [
            "540, T_PAUSE_CLOSE, OPEN, P1",
            "560, T_PAUSE_CLOSE, PAUSE",
            "620, T_PAUSE_CLOSE, CLOSE",
            "540, T_PAUSE_OPEN, OPEN, P1",
            "560, T_PAUSE_OPEN, PAUSE",
            "580, T_PAUSE_OPEN, OPEN, P2",
            "600, T_PAUSE_OPEN, RESUME",
            "620, T_PAUSE_OPEN, CLOSE",
            "540, T_PAUSE_PAUSE, OPEN, P1",
            "560, T_PAUSE_PAUSE, PAUSE",
            "580, T_PAUSE_PAUSE, PAUSE",
            "600, T_PAUSE_PAUSE, RESUME",
            "620, T_PAUSE_PAUSE, CLOSE",
            "540, T_PAUSE_PRIO, OPEN, P1",
            "560, T_PAUSE_PRIO, PAUSE",
            "580, T_PAUSE_PRIO, PRIORITY, P3",
            "600, T_PAUSE_PRIO, RESUME",
            "620, T_PAUSE_PRIO, CLOSE",
            "540, T_PAUSE_REOPEN, OPEN, P1",
            "560, T_PAUSE_REOPEN, PAUSE",
            "580, T_PAUSE_REOPEN, REOPEN",
            "600, T_PAUSE_REOPEN, RESUME",
            "620, T_PAUSE_REOPEN, CLOSE",
        ]
        expected = [
            {
                "ticket_id": "T_PAUSE_CLOSE",
                "priority": "P1",
                "used_minutes": 20,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T_PAUSE_OPEN",
                "priority": "P1",
                "used_minutes": 40,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T_PAUSE_PAUSE",
                "priority": "P1",
                "used_minutes": 40,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T_PAUSE_PRIO",
                "priority": "P3",
                "used_minutes": 40,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T_PAUSE_REOPEN",
                "priority": "P1",
                "used_minutes": 40,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
        ]
        return stream, expected

    tests.append(("Transitions from PAUSED", test_state_transitions_paused))

    def test_state_transitions_closed():
        stream = [
            "540, T_CLOSED_IGN, OPEN, P1",
            "600, T_CLOSED_IGN, CLOSE",
            "620, T_CLOSED_IGN, PRIORITY, P4",
            "630, T_CLOSED_IGN, PAUSE",
            "640, T_CLOSED_IGN, RESUME",
            "650, T_CLOSED_IGN, CLOSE",
            "700, T_CLOSED_IGN, REOPEN",
            "730, T_CLOSED_IGN, CLOSE",
            "540, T_CLOSED_OPEN, OPEN, P1",
            "800, T_CLOSED_OPEN, CLOSE",
            "850, T_CLOSED_OPEN, OPEN, P2",
            "900, T_CLOSED_OPEN, CLOSE",
            "540, T_CLOSED_REOPEN, OPEN, P1",
            "800, T_CLOSED_REOPEN, CLOSE",
            "850, T_CLOSED_REOPEN, REOPEN",
            "900, T_CLOSED_REOPEN, CLOSE",
        ]
        expected = [
            {
                "ticket_id": "T_CLOSED_IGN",
                "priority": "P1",
                "used_minutes": 90,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T_CLOSED_OPEN",
                "priority": "P2",
                "used_minutes": 50,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            },
            {
                "ticket_id": "T_CLOSED_REOPEN",
                "priority": "P1",
                "used_minutes": 310,
                "breached": True,
                "breached_at": 781,
                "status": "closed",
            },
        ]
        return stream, expected

    tests.append(("Transitions from CLOSED", test_state_transitions_closed))

    # -------------------------------------------------------------------------
    # SLA Boundary: Exact limit vs Limit + 1
    # -------------------------------------------------------------------------
    def test_exact_sla_boundary_and_breach():
        stream = [
            "540, T_EXACT, OPEN, P1",
            "780, T_EXACT, PAUSE",
            "540, T_OVER, OPEN, P1",
            "781, T_OVER, PAUSE",
        ]
        expected = [
            {
                "ticket_id": "T_EXACT",
                "priority": "P1",
                "used_minutes": 240,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
            {
                "ticket_id": "T_OVER",
                "priority": "P1",
                "used_minutes": 241,
                "breached": True,
                "breached_at": 781,
                "status": "paused",
            },
        ]
        return stream, expected

    tests.append(("Exact SLA boundary (240 no breach vs 241 breach)", test_exact_sla_boundary_and_breach))

    # -------------------------------------------------------------------------
    # Priority Changes and Sticky Breach
    # -------------------------------------------------------------------------
    def test_priority_raise_exact_breach_minute():
        stream = [
            "540, T_PREVENT, OPEN, P1",
            "781, T_PREVENT, PRIORITY, P2",
            "800, T_PREVENT, PAUSE",
            "540, T_TOO_LATE, OPEN, P1",
            "782, T_TOO_LATE, PRIORITY, P2",
            "800, T_TOO_LATE, PAUSE",
        ]
        expected = [
            {
                "ticket_id": "T_PREVENT",
                "priority": "P2",
                "used_minutes": 260,
                "breached": False,
                "breached_at": None,
                "status": "paused",
            },
            {
                "ticket_id": "T_TOO_LATE",
                "priority": "P2",
                "used_minutes": 260,
                "breached": True,
                "breached_at": 781,
                "status": "paused",
            },
        ]
        return stream, expected

    tests.append(("Priority raise at exact breach minute vs 1 minute late", test_priority_raise_exact_breach_minute))

    def test_priority_drop_causes_immediate_breach():
        stream = [
            "540, T_DROP_PAUSED, OPEN, P2",
            "790, T_DROP_PAUSED, PAUSE",
            "850, T_DROP_PAUSED, PRIORITY, P1",
            "540, T_DROP_WEEKEND, OPEN, P2",
            "800, T_DROP_WEEKEND, PAUSE",
            "7250, T_DROP_WEEKEND, PRIORITY, P1",
            "7300, T_DROP_WEEKEND, CLOSE",
        ]
        expected = [
            {
                "ticket_id": "T_DROP_PAUSED",
                "priority": "P1",
                "used_minutes": 250,
                "breached": True,
                "breached_at": 850,
                "status": "paused",
            },
            {
                "ticket_id": "T_DROP_WEEKEND",
                "priority": "P1",
                "used_minutes": 260,
                "breached": True,
                "breached_at": 7250,
                "status": "closed",
            },
        ]
        return stream, expected

    tests.append(("Priority drop triggers immediate breach (paused & weekend)", test_priority_drop_causes_immediate_breach))

    # -------------------------------------------------------------------------
    # Multi-day and Multi-Priority Limits (P2, P3, P4)
    # -------------------------------------------------------------------------
    def test_multi_day_priorities():
        stream = [
            # P2: 480 limit. Monday 09:00 (540) to Tuesday 10:00 (2040).
            # Mon 540-1020: 480 min. Tue 1980-1981: 481 min -> breaches at 1981!
            "540, T_P2, OPEN, P2",
            "2040, T_P2, CLOSE",
            # P3: 1440 limit (3 days: Mon, Tue, Wed = 480 * 3 = 1440).
            # Thu 09:00 (4860) to 09:01 (4861) reaches 1441 -> breaches at 4861!
            "540, T_P3, OPEN, P3",
            "4920, T_P3, CLOSE",
            # P4: 2400 limit (5 days: Mon-Fri = 480 * 5 = 2400).
            # Next Mon 09:00 (10620) to 09:01 (10621) reaches 2401 -> breaches at 10621!
            "540, T_P4, OPEN, P4",
            "10650, T_P4, CLOSE",
        ]
        expected = [
            {
                "ticket_id": "T_P2",
                "priority": "P2",
                "used_minutes": 540,
                "breached": True,
                "breached_at": 1981,
                "status": "closed",
            },
            {
                "ticket_id": "T_P3",
                "priority": "P3",
                "used_minutes": 1500,
                "breached": True,
                "breached_at": 4861,
                "status": "closed",
            },
            {
                "ticket_id": "T_P4",
                "priority": "P4",
                "used_minutes": 2430,
                "breached": True,
                "breached_at": 10621,
                "status": "closed",
            },
        ]
        return stream, expected

    tests.append(("Multi-day SLA breaches for P2, P3, P4", test_multi_day_priorities))

    # -------------------------------------------------------------------------
    # Holiday Calendar: Deduplication and Spans
    # -------------------------------------------------------------------------
    def test_holiday_spans_and_dedup():
        stream = [
            "4860, T_HOL, OPEN, P2",
            "6000, *, HOLIDAY",
            "6500, *, HOLIDAY",
            "10680, T_HOL, CLOSE",
        ]
        expected = [
            {
                "ticket_id": "T_HOL",
                "priority": "P2",
                "used_minutes": 540,
                "breached": True,
                "breached_at": 10621,
                "status": "closed",
            }
        ]
        return stream, expected

    tests.append(("Holiday deduplication and multi-day spanning", test_holiday_spans_and_dedup))

    # -------------------------------------------------------------------------
    # Output Ordering & Code-Point Verification
    # -------------------------------------------------------------------------
    def test_code_point_sorting_and_types():
        stream = [
            "540, t1, OPEN, P1",
            "600, t1, CLOSE",
            "540, T2, OPEN, P1",
            "600, T2, CLOSE",
            "540, 1, OPEN, P1",
            "600, 1, CLOSE",
            "540, T10, OPEN, P1",
            "600, T10, CLOSE",
            "540, b, OPEN, P1",
            "600, b, CLOSE",
            "540, A, OPEN, P1",
            "600, A, CLOSE",
        ]
        expected = [
            {"ticket_id": "1", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "A", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T10", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "T2", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "b", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
            {"ticket_id": "t1", "priority": "P1", "used_minutes": 60, "breached": False, "breached_at": None, "status": "closed"},
        ]
        return stream, expected

    tests.append(("Code-point sorting order of ticket_ids", test_code_point_sorting_and_types))

    # -------------------------------------------------------------------------
    # Ticket Running Past Business Hours into Night
    # -------------------------------------------------------------------------
    def test_ticket_running_past_business_hours():
        stream = [
            "540, T_NIGHT, OPEN, P1",
            "1050, T_OTHER, PAUSE",
        ]
        expected = [
            {
                "ticket_id": "T_NIGHT",
                "priority": "P1",
                "used_minutes": 480,
                "breached": True,
                "breached_at": 781,
                "status": "running",
            }
        ]
        return stream, expected

    tests.append(("Ticket running past business hours evaluated at 'now'", test_ticket_running_past_business_hours))

    # -------------------------------------------------------------------------
    # Performance with Minutes up to 1,000,000,000
    # -------------------------------------------------------------------------
    def test_large_minutes_performance():
        stream = [
            "1000000000, T_BIG, OPEN, P2",
            "1000000800, *, HOLIDAY",
            "1000003000, T_BIG, CLOSE",
        ]
        expected = [
            {
                "ticket_id": "T_BIG",
                "priority": "P2",
                "used_minutes": 600,
                "breached": True,
                "breached_at": 1000002881,
                "status": "closed",
            }
        ]
        return stream, expected

    tests.append(("Large minute values (~1 billion) without timeout", test_large_minutes_performance))

    # -------------------------------------------------------------------------
    # High-Volume Event Batch
    # -------------------------------------------------------------------------
    def test_high_volume_batch():
        stream = []
        expected = []
        for d in range(20):
            stream.append(f"{d * 1440 + 100}, *, HOLIDAY")

        for i in range(100):
            t_id = f"T_{i:03d}"
            open_min = 28800 + i * 20
            prio_min = open_min + 2
            pause_min = open_min + 4
            resume_min = open_min + 6
            close_min = open_min + 8
            stream.extend([
                f"{open_min}, {t_id}, OPEN, P1",
                f"{prio_min}, {t_id}, PRIORITY, P2",
                f"{pause_min}, {t_id}, PAUSE",
                f"{resume_min}, {t_id}, RESUME",
                f"{close_min}, {t_id}, CLOSE",
            ])
            expected.append({
                "ticket_id": t_id,
                "priority": "P2",
                "used_minutes": 6,
                "breached": False,
                "breached_at": None,
                "status": "closed",
            })
        expected.sort(key=lambda x: x["ticket_id"])
        return stream, expected

    tests.append(("High-volume batch (100 tickets, 500 events, 20 holidays)", test_high_volume_batch))

    # -------------------------------------------------------------------------
    # Execution
    # -------------------------------------------------------------------------
    passed_count = 0
    failed_count = 0

    print("======================================================================")
    print("RUNNING ADVERSARIAL SLA CLOCK TEST SUITE")
    print("======================================================================")

    for idx, (name, test_func) in enumerate(tests, 1):
        try:
            stream, expected = test_func()
            actual = solution.compute_sla(stream)
            success, msg = check_result(name, actual, expected)
            if success:
                print(f"[{idx:02d}/{len(tests):02d}] PASS: {name}")
                passed_count += 1
            else:
                print(f"[{idx:02d}/{len(tests):02d}] FAIL: {name}")
                print(f"       Reason: {msg}")
                failed_count += 1
        except Exception as e:
            print(f"[{idx:02d}/{len(tests):02d}] CRASH: {name}")
            print(f"       Exception: {type(e).__name__}: {e}")
            failed_count += 1

    print("======================================================================")
    print(f"SUMMARY: {passed_count} passed, {failed_count} failed out of {len(tests)} tests.")
    print("======================================================================")

    if failed_count == 0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    run_tests()