import solution
import sys
import traceback

def assert_ticket_equal(actual, expected, context=""):
    """Validates schema, types, and values for a ticket dict."""
    prefix = f"[{context}] " if context else ""
    assert isinstance(actual, dict), f"{prefix}Expected dict, got {type(actual)}"
    expected_keys = {"ticket_id", "used_ms", "breached", "status"}
    assert set(actual.keys()) == expected_keys, (
        f"{prefix}Keys mismatch: expected {expected_keys}, got {set(actual.keys())}"
    )

    # Validate types strictly (bool is a subclass of int in Python, so check explicitly)
    assert isinstance(actual["ticket_id"], str), (
        f"{prefix}ticket_id must be str, got {type(actual['ticket_id'])}"
    )
    assert isinstance(actual["used_ms"], int) and not isinstance(actual["used_ms"], bool), (
        f"{prefix}used_ms must be int, got {type(actual['used_ms'])}"
    )
    assert isinstance(actual["breached"], bool), (
        f"{prefix}breached must be bool, got {type(actual['breached'])}"
    )
    assert isinstance(actual["status"], str), (
        f"{prefix}status must be str, got {type(actual['status'])}"
    )

    assert actual["ticket_id"] == expected["ticket_id"], (
        f"{prefix}ticket_id: expected {expected['ticket_id']!r}, got {actual['ticket_id']!r}"
    )
    assert actual["used_ms"] == expected["used_ms"], (
        f"{prefix}ticket {expected['ticket_id']} used_ms: expected {expected['used_ms']}, got {actual['used_ms']}"
    )
    assert actual["breached"] == expected["breached"], (
        f"{prefix}ticket {expected['ticket_id']} breached: expected {expected['breached']}, got {actual['breached']}"
    )
    assert actual["status"] == expected["status"], (
        f"{prefix}ticket {expected['ticket_id']} status: expected {expected['status']!r}, got {actual['status']!r}"
    )

def assert_results_equal(actual_list, expected_list, context=""):
    """Validates the entire return list and strict string ordering."""
    prefix = f"[{context}] " if context else ""
    assert isinstance(actual_list, list), f"{prefix}Expected list, got {type(actual_list)}"
    assert len(actual_list) == len(expected_list), (
        f"{prefix}Expected {len(expected_list)} tickets, got {len(actual_list)}.\n"
        f"Actual: {actual_list}\nExpected: {expected_list}"
    )

    # Check ascending string order of ticket_id
    ticket_ids = [t.get("ticket_id") for t in actual_list if isinstance(t, dict)]
    assert ticket_ids == sorted(ticket_ids), (
        f"{prefix}Results are not sorted by ticket_id ascending (string order): {ticket_ids}"
    )

    for i, (act, exp) in enumerate(zip(actual_list, expected_list)):
        assert_ticket_equal(act, exp, context=f"{context} item #{i}")


# ==============================================================================
# TEST SUITE
# ==============================================================================

def test_empty_and_no_open_streams():
    """Empty streams, malformed-only streams, and unopened tickets should return []."""
    # 1. Pure empty
    assert solution.compute_sla([]) == []

    # 2. Malformed lines only
    stream = [
        "",
        "   ",
        "\t\r\n",
        "corrupted_line_without_commas",
        "100,only_two_fields",
        "100,t1,OPEN,extra,fourth_field",
        "abc,t1,OPEN",
        "-50,t1,OPEN",
    ]
    assert solution.compute_sla(stream) == []

    # 3. Validly formatted lines but no ticket ever has a valid OPEN
    stream = [
        "100, t_ghost, PAUSE",
        "200, t_ghost, RESUME",
        "300, t_ghost, CLOSE",
        "400, t_ghost, REOPEN",
        "500, t_other, CLOSE",
    ]
    assert solution.compute_sla(stream) == []


def test_state_machine_20_cells():
    """
    Exhaustively tests all 20 cells of the state-transition table:
      States: UNOPENED (S0), RUNNING (S1), PAUSED (S2), CLOSED (S3)
      Events: OPEN, PAUSE, RESUME, CLOSE, REOPEN
    """
    stream = [
        # --- Anchor to fix 'now' at 1000 ---
        "0, z_anchor, OPEN",
        "1000, z_anchor, CLOSE",

        # --- S0 (UNOPENED) ---
        # 1. OPEN (Valid -> S1)
        "100, s0_open, OPEN",  # Still running at now=1000: used = 900
        # 2-5. Invalid before first valid OPEN -> all omitted
        "100, s0_pause, PAUSE",
        "100, s0_resume, RESUME",
        "100, s0_close, CLOSE",
        "100, s0_reopen, REOPEN",

        # --- S1 (RUNNING) ---
        # 6. OPEN (Invalid -> ignored)
        "100, s1_open, OPEN",
        "200, s1_open, OPEN",  # Ignored: already open
        "300, s1_open, CLOSE", # Used: 300 - 100 = 200
        # 7. PAUSE (Valid -> S2): tested below in S2 transitions
        # 8. RESUME (Invalid -> ignored)
        "100, s1_resume, OPEN",
        "200, s1_resume, RESUME",  # Ignored: clock running
        "300, s1_resume, CLOSE",   # Used: 300 - 100 = 200
        # 9. CLOSE (Valid -> S3): tested above in s1_open, s1_resume
        # 10. REOPEN (Invalid -> ignored)
        "100, s1_reopen, OPEN",
        "200, s1_reopen, REOPEN",  # Ignored: not closed
        "300, s1_reopen, CLOSE",   # Used: 300 - 100 = 200

        # --- S2 (PAUSED) ---
        # 11. OPEN (Invalid -> ignored)
        "100, s2_open, OPEN",
        "200, s2_open, PAUSE",
        "250, s2_open, OPEN",    # Ignored: already open
        "300, s2_open, RESUME",
        "400, s2_open, CLOSE",   # Used: (200-100) + (400-300) = 100 + 100 = 200
        # 12. PAUSE (Invalid -> ignored)
        "100, s2_pause, OPEN",
        "200, s2_pause, PAUSE",
        "250, s2_pause, PAUSE",  # Ignored: already paused
        "300, s2_pause, RESUME",
        "400, s2_pause, CLOSE",  # Used: (200-100) + (400-300) = 200
        # 13. RESUME (Valid -> S1): tested in s2_open / s2_pause
        # 14. CLOSE (Valid -> S3 from paused; mid-pause stretch ignored)
        "100, s2_close, OPEN",
        "200, s2_close, PAUSE",
        "400, s2_close, CLOSE",  # Used: 200 - 100 = 100
        # 15. REOPEN (Invalid -> ignored)
        "100, s2_reopen, OPEN",
        "200, s2_reopen, PAUSE",
        "250, s2_reopen, REOPEN", # Ignored: not closed
        "300, s2_reopen, RESUME",
        "400, s2_reopen, CLOSE",  # Used: (200-100) + (400-300) = 200

        # --- S3 (CLOSED) ---
        # 16. OPEN (Invalid -> ignored; ticket already had first valid OPEN, REOPEN needed)
        "100, s3_open, OPEN",
        "200, s3_open, CLOSE",
        "300, s3_open, OPEN",    # Ignored: cannot OPEN closed ticket
        # Used: 200 - 100 = 100, status: closed
        # 17. PAUSE (Invalid -> ignored)
        "100, s3_pause, OPEN",
        "200, s3_pause, CLOSE",
        "300, s3_pause, PAUSE",  # Ignored: cannot pause closed ticket
        # Used: 200 - 100 = 100, status: closed
        # 18. RESUME (Invalid -> ignored)
        "100, s3_resume, OPEN",
        "200, s3_resume, CLOSE",
        "300, s3_resume, RESUME", # Ignored: cannot resume closed ticket
        # Used: 200 - 100 = 100, status: closed
        # 19. CLOSE (Invalid -> ignored)
        "100, s3_close, OPEN",
        "200, s3_close, CLOSE",
        "300, s3_close, CLOSE",  # Ignored: CLOSE when already closed
        # Used: 200 - 100 = 100, status: closed
        # 20. REOPEN (Valid -> S1)
        "100, s3_reopen, OPEN",
        "200, s3_reopen, CLOSE",
        "300, s3_reopen, REOPEN",
        "450, s3_reopen, CLOSE", # Used: (200-100) + (450-300) = 100 + 150 = 250
    ]

    expected = [
        {"ticket_id": "s0_open",   "used_ms": 900, "breached": False, "status": "open"},
        {"ticket_id": "s1_open",   "used_ms": 200, "breached": False, "status": "closed"},
        {"ticket_id": "s1_reopen", "used_ms": 200, "breached": False, "status": "closed"},
        {"ticket_id": "s1_resume", "used_ms": 200, "breached": False, "status": "closed"},
        {"ticket_id": "s2_close",  "used_ms": 100, "breached": False, "status": "closed"},
        {"ticket_id": "s2_open",   "used_ms": 200, "breached": False, "status": "closed"},
        {"ticket_id": "s2_pause",  "used_ms": 200, "breached": False, "status": "closed"},
        {"ticket_id": "s2_reopen", "used_ms": 200, "breached": False, "status": "closed"},
        {"ticket_id": "s3_close",  "used_ms": 100, "breached": False, "status": "closed"},
        {"ticket_id": "s3_open",   "used_ms": 100, "breached": False, "status": "closed"},
        {"ticket_id": "s3_pause",  "used_ms": 100, "breached": False, "status": "closed"},
        {"ticket_id": "s3_reopen", "used_ms": 250, "breached": False, "status": "closed"},
        {"ticket_id": "s3_resume", "used_ms": 100, "breached": False, "status": "closed"},
        {"ticket_id": "z_anchor",  "used_ms": 1000, "breached": False, "status": "closed"},
    ]
    actual = solution.compute_sla(stream)
    assert_results_equal(actual, expected, "test_state_machine_20_cells")


def test_exact_sla_boundary():
    """
    SLA limit is strictly 14,400,000 ms.
    A ticket breaches iff used_ms > 14,400,000.
    14,400,000 does NOT breach; 14,400,001 DOES breach.
    """
    SLA_LIMIT = 14_400_000

    stream = [
        # Anchor setting now to 30,000,000
        "0, z_anchor, OPEN",
        "30000000, z_anchor, CLOSE",

        # 1. Closed exactly at boundary: 14,399,999 ms -> NOT breached
        f"0, t_closed_under, OPEN",
        f"{SLA_LIMIT - 1}, t_closed_under, CLOSE",

        # 2. Closed exactly at 14,400,000 ms -> NOT breached
        f"0, t_closed_exact, OPEN",
        f"{SLA_LIMIT}, t_closed_exact, CLOSE",

        # 3. Closed at 14,400,001 ms -> BREACHED
        f"0, t_closed_over, OPEN",
        f"{SLA_LIMIT + 1}, t_closed_over, CLOSE",

        # 4. Open and paused with exactly 14,400,000 ms -> NOT breached, status open
        "0, t_paused_exact, OPEN",
        f"{SLA_LIMIT}, t_paused_exact, PAUSE",

        # 5. Open and paused with 14,400,001 ms -> BREACHED, status open
        "0, t_paused_over, OPEN",
        f"{SLA_LIMIT + 1}, t_paused_over, PAUSE",

        # 6. Reopened ticket accumulating exactly 14,400,000 ms over multiple spans
        # Span 1: 0 to 4,400,000 = 4,400,000 ms
        "0, t_reopen_exact, OPEN",
        "4400000, t_reopen_exact, CLOSE",
        # Span 2: 5,000,000 to 15,000,000 = 10,000,000 ms -> Total: 14,400,000 ms
        "5000000, t_reopen_exact, REOPEN",
        "15000000, t_reopen_exact, CLOSE",

        # 7. Reopened ticket accumulating 14,400,001 ms
        "0, t_reopen_over, OPEN",
        "4400000, t_reopen_over, CLOSE",
        "5000000, t_reopen_over, REOPEN",
        "15000001, t_reopen_over, CLOSE",  # 4.4M + 10.000001M = 14,400,001
    ]

    expected = [
        {"ticket_id": "t_closed_exact",  "used_ms": 14400000, "breached": False, "status": "closed"},
        {"ticket_id": "t_closed_over",   "used_ms": 14400001, "breached": True,  "status": "closed"},
        {"ticket_id": "t_closed_under",  "used_ms": 14399999, "breached": False, "status": "closed"},
        {"ticket_id": "t_paused_exact",  "used_ms": 14400000, "breached": False, "status": "open"},
        {"ticket_id": "t_paused_over",   "used_ms": 14400001, "breached": True,  "status": "open"},
        {"ticket_id": "t_reopen_exact",  "used_ms": 14400000, "breached": False, "status": "closed"},
        {"ticket_id": "t_reopen_over",   "used_ms": 14400001, "breached": True,  "status": "closed"},
        {"ticket_id": "z_anchor",        "used_ms": 30000000, "breached": True,  "status": "closed"},
    ]
    actual = solution.compute_sla(stream)
    assert_results_equal(actual, expected, "test_exact_sla_boundary")


def test_open_ticket_boundary_with_now():
    """Validates that tickets still running count up to 'now', hitting exact SLA boundaries."""
    # now will be 14,400,000
    stream1 = [
        "0, t_exact, OPEN",          # Running 0..14400000 = 14400000 ms -> NOT breached
        "1, t_under, OPEN",          # Running 1..14400000 = 14399999 ms -> NOT breached
        "14400000, t_anchor, OPEN",  # Sets now = 14400000; running 14.4M..14.4M = 0 ms
        "14400000, t_anchor, CLOSE",
    ]
    expected1 = [
        {"ticket_id": "t_anchor", "used_ms": 0,        "breached": False, "status": "closed"},
        {"ticket_id": "t_exact",  "used_ms": 14400000, "breached": False, "status": "open"},
        {"ticket_id": "t_under",  "used_ms": 14399999, "breached": False, "status": "open"},
    ]
    assert_results_equal(solution.compute_sla(stream1), expected1, "test_open_ticket_boundary_with_now - exact")

    # now will be 14,400,001
    stream2 = [
        "0, t_over, OPEN",           # Running 0..14400001 = 14400001 ms -> BREACHED
        "14400001, t_anchor, OPEN",
        "14400001, t_anchor, CLOSE",
    ]
    expected2 = [
        {"ticket_id": "t_anchor", "used_ms": 0,        "breached": False, "status": "closed"},
        {"ticket_id": "t_over",   "used_ms": 14400001, "breached": True,  "status": "open"},
    ]
    assert_results_equal(solution.compute_sla(stream2), expected2, "test_open_ticket_boundary_with_now - over")


def test_definition_of_now_including_invalid_lines():
    """
    'Now' is defined as the maximum timestamp_ms appearing anywhere in the stream
    (including lines that are otherwise invalid).
    """
    stream = [
        "0, t_valid, OPEN",
        # These lines are semantically invalid, but their timestamps MUST update 'now'
        "50000000, t_ghost, PAUSE",          # Ticket never opened -> invalid event
        "75000000, t_ghost2, CLOSE",         # Ticket never opened -> invalid event
        "100000000, t_valid, OPEN",          # Already open -> invalid event
        "60000000, t_ghost3, REOPEN",        # Never closed -> invalid event
    ]
    # now = 100,000,000.
    # t_valid opened at 0 and was never closed or paused.
    # Clock runs up to now (100,000,000 ms).
    # Ghosts had no valid OPEN -> omitted entirely!
    expected = [
        {"ticket_id": "t_valid", "used_ms": 100000000, "breached": True, "status": "open"}
    ]
    actual = solution.compute_sla(stream)
    assert_results_equal(actual, expected, "test_definition_of_now_including_invalid_lines")


def test_ties_and_stable_sort_order():
    """
    Events with the same timestamp_ms must preserve their original arrival order (stable sort).
    Ties between different event types have critical semantic consequences.
    """
    stream = [
        # Anchor setting now = 5000
        "0, z_anchor, OPEN",
        "5000, z_anchor, CLOSE",

        # Pair 1: OPEN followed by CLOSE at t=1000
        "1000, t1_open_close, OPEN",
        "1000, t1_open_close, CLOSE",

        # Pair 2: CLOSE followed by OPEN at t=1000
        # CLOSE is invalid (before OPEN) and ignored; OPEN opens ticket at 1000
        "1000, t2_close_open, CLOSE",
        "1000, t2_close_open, OPEN",

        # Pair 3: OPEN followed by PAUSE at t=1000
        # Opens at 1000, then pauses at 1000 -> remains paused (used = 0, status: open)
        "1000, t3_open_pause, OPEN",
        "1000, t3_open_pause, PAUSE",

        # Pair 4: PAUSE followed by OPEN at t=1000
        # PAUSE before OPEN is ignored; OPEN opens ticket -> runs up to now (5000)
        "1000, t4_pause_open, PAUSE",
        "1000, t4_pause_open, OPEN",

        # Pair 5: Ticket already open. At t=2000: CLOSE followed by REOPEN
        "500, t5_close_reopen, OPEN",
        "2000, t5_close_reopen, CLOSE",   # Used so far: 2000 - 500 = 1500
        "2000, t5_close_reopen, REOPEN",  # Clock restarts from 2000; runs to 5000 (3000 ms)

        # Pair 6: Ticket already open. At t=2000: REOPEN followed by CLOSE
        "500, t6_reopen_close, OPEN",
        "2000, t6_reopen_close, REOPEN",  # Invalid (not closed) -> ignored
        "2000, t6_reopen_close, CLOSE",   # Closes at 2000; used: 2000 - 500 = 1500, status: closed
    ]

    expected = [
        {"ticket_id": "t1_open_close",   "used_ms": 0,    "breached": False, "status": "closed"},
        {"ticket_id": "t2_close_open",   "used_ms": 4000, "breached": False, "status": "open"},
        {"ticket_id": "t3_open_pause",   "used_ms": 0,    "breached": False, "status": "open"},
        {"ticket_id": "t4_pause_open",   "used_ms": 4000, "breached": False, "status": "open"},
        {"ticket_id": "t5_close_reopen", "used_ms": 4500, "breached": False, "status": "open"},
        {"ticket_id": "t6_reopen_close", "used_ms": 1500, "breached": False, "status": "closed"},
        {"ticket_id": "z_anchor",        "used_ms": 5000, "breached": False, "status": "closed"},
    ]
    actual = solution.compute_sla(stream)
    assert_results_equal(actual, expected, "test_ties_and_stable_sort_order")


def test_out_of_order_events():
    """Events arrive completely reversed and interleaved across tickets."""
    stream = [
        "10000, t1, CLOSE",
        "1000,  t2, OPEN",
        "6000,  t1, RESUME",
        "4000,  t1, PAUSE",
        "7000,  t2, CLOSE",
        "0,     t1, OPEN",
        "3000,  t2, PAUSE",
        "5000,  t2, RESUME",
    ]
    # Hand trace chronological order:
    # 0:     t1 OPEN
    # 1000:  t2 OPEN
    # 3000:  t2 PAUSE   -> t2 used: 2000
    # 4000:  t1 PAUSE   -> t1 used: 4000
    # 5000:  t2 RESUME  -> t2 clock restarts
    # 6000:  t1 RESUME  -> t1 clock restarts
    # 7000:  t2 CLOSE   -> t2 used: 2000 + (7000 - 5000) = 4000
    # 10000: t1 CLOSE   -> t1 used: 4000 + (10000 - 6000) = 8000

    expected = [
        {"ticket_id": "t1", "used_ms": 8000, "breached": False, "status": "closed"},
        {"ticket_id": "t2", "used_ms": 4000, "breached": False, "status": "closed"},
    ]
    actual = solution.compute_sla(stream)
    assert_results_equal(actual, expected, "test_out_of_order_events")


def test_malformed_lines_and_whitespace():
    """
    Whitespace around fields is ignored.
    Empty or malformed lines are skipped without breaking processing.
    """
    stream = [
        "",
        "   \t  ",
        "\n",
        "corrupted line",
        "1000, missing_event",
        "1000, t_bad, OPEN, too, many, fields",
        "NaN, t_bad, OPEN",
        "-100, t_bad, OPEN",
        "12.34, t_bad, OPEN",
        "   500   ,   t_ws   ,   OPEN   ",
        "invalid_timestamp, t_ws, PAUSE",
        "   1500  ,   t_ws   ,   PAUSE  ",
        "random junk",
        "   2500  ,   t_ws   ,   RESUME ",
        "   4000  ,   t_ws   ,   CLOSE  ",
    ]
    # t_ws used: (1500 - 500) + (4000 - 2500) = 1000 + 1500 = 2500.
    # t_bad has no valid lines -> omitted.
    expected = [
        {"ticket_id": "t_ws", "used_ms": 2500, "breached": False, "status": "closed"}
    ]
    actual = solution.compute_sla(stream)
    assert_results_equal(actual, expected, "test_malformed_lines_and_whitespace")


def test_output_ordering_string_comparison():
    """
    Output must be sorted by ticket_id ascending (string order, not numeric).
    For example: '10' < '2' in string order.
    """
    stream = [
        "0, 10,  OPEN",  "10, 10,  CLOSE",
        "0, 2,   OPEN",  "10, 2,   CLOSE",
        "0, 1,   OPEN",  "10, 1,   CLOSE",
        "0, 02,  OPEN",  "10, 02,  CLOSE",
        "0, 100, OPEN",  "10, 100, CLOSE",
        "0, A,   OPEN",  "10, A,   CLOSE",
        "0, a,   OPEN",  "10, a,   CLOSE",
        "0, _,   OPEN",  "10, _,   CLOSE",
    ]
    # Lexicographical sort of IDs:
    # ASCII: '02' (48), '1' (49), '10' (49), '100' (49), '2' (50), 'A' (65), '_' (95), 'a' (97)
    expected_ids = sorted(["10", "2", "1", "02", "100", "A", "a", "_"])
    assert expected_ids == ["02", "1", "10", "100", "2", "A", "_", "a"]

    expected = [
        {"ticket_id": tid, "used_ms": 10, "breached": False, "status": "closed"}
        for tid in expected_ids
    ]
    actual = solution.compute_sla(stream)
    assert_results_equal(actual, expected, "test_output_ordering_string_comparison")


def test_complex_lifecycle():
    """A realistic lifecycle with multiple pauses, resumes, closes, and reopens."""
    stream = [
        "1000,  t_life, OPEN",
        "3000,  t_life, PAUSE",    # Used: 2000
        "5000,  t_life, RESUME",
        "8000,  t_life, PAUSE",    # Used: 2000 + 3000 = 5000
        "10000, t_life, CLOSE",    # Closed mid-pause; 8000..10000 does not count; used: 5000
        "12000, t_life, REOPEN",   # Reopened; continues from 5000
        "17000, t_life, PAUSE",    # Used: 5000 + 5000 = 10000
        "20000, t_life, RESUME",
        "22000, t_life, CLOSE",    # Used: 10000 + 2000 = 12000
        "25000, t_life, REOPEN",   # Clock starts running from 25000
        # Another ticket pushes 'now' to 35000
        "30000, other, OPEN",
        "35000, other, CLOSE",
    ]
    # At now=35000, t_life is still open and running from 25000:
    # Additional used: 35000 - 25000 = 10000.
    # Total used: 12000 + 10000 = 22000. Status: open, breached: False.
    expected = [
        {"ticket_id": "other",  "used_ms": 5000,  "breached": False, "status": "closed"},
        {"ticket_id": "t_life", "used_ms": 22000, "breached": False, "status": "open"},
    ]
    actual = solution.compute_sla(stream)
    assert_results_equal(actual, expected, "test_complex_lifecycle")


# ==============================================================================
# MAIN RUNNER
# ==============================================================================

def main():
    test_functions = [
        test_empty_and_no_open_streams,
        test_state_machine_20_cells,
        test_exact_sla_boundary,
        test_open_ticket_boundary_with_now,
        test_definition_of_now_including_invalid_lines,
        test_ties_and_stable_sort_order,
        test_out_of_order_events,
        test_malformed_lines_and_whitespace,
        test_output_ordering_string_comparison,
        test_complex_lifecycle,
    ]

    passed = 0
    failed = 0

    print("=" * 70)
    print("Running adversarial test suite for Problem 4: Support-ticket SLA clock")
    print("=" * 70)

    for test_fn in test_functions:
        name = test_fn.__name__
        try:
            test_fn()
            print(f" [PASS] {name}")
            passed += 1
        except Exception as e:
            print(f" [FAIL] {name}: {e}")
            traceback.print_exc(file=sys.stdout)
            failed += 1

    print("-" * 70)
    print(f"Summary: {passed} passed, {failed} failed out of {len(test_functions)} tests.")

    if failed == 0:
        print("All adversarial tests PASSED.")
        sys.exit(0)
    else:
        print("Some tests FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    main()