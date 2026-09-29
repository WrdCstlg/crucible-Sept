import solution
import sys
import traceback

def check_sla(name, stream, expected):
    res = solution.compute_sla(stream)
    assert isinstance(res, list), f"[{name}] Expected list, got {type(res)}"
    for i, d in enumerate(res):
        assert isinstance(d, dict), f"[{name}] Element {i} is not a dict: {type(d)}"
        assert set(d.keys()) == {"ticket_id", "used_ms", "breached", "status"}, (
            f"[{name}] Element {i} keys mismatch: {set(d.keys())}"
        )
        assert isinstance(d["ticket_id"], str), f"[{name}] ticket_id not str: {type(d['ticket_id'])}"
        assert type(d["used_ms"]) is int, f"[{name}] used_ms not int: {type(d['used_ms'])}"
        assert type(d["breached"]) is bool, f"[{name}] breached not bool: {type(d['breached'])}"
        assert d["status"] in ("open", "closed"), f"[{name}] status invalid: {d['status']}"
    assert res == expected, f"[{name}] Result mismatch:\nExpected: {expected}\nGot:      {res}"


def test_example():
    stream = [
        "100,A,OPEN",
        "400,A,CLOSE",
    ]
    expected = [
        {"ticket_id": "A", "used_ms": 300, "breached": False, "status": "closed"}
    ]
    check_sla("test_example", stream, expected)


def test_empty_stream():
    check_sla("test_empty_stream", [], [])


def test_malformed_lines_only():
    stream = [
        "",
        "   ",
        "\t\n",
        "100",
        "100,A",
        "100,A,OPEN,extra",
        ",100,A,OPEN",
        "100,A,OPEN,",
        "-100,A,OPEN",
        "+100,A,OPEN",
        "100.5,A,OPEN",
        "1e4,A,OPEN",
        "0x64,A,OPEN",
        "10 0,A,OPEN",
        "100,,OPEN",
        "100,   ,OPEN",
        "100,A,",
        "100,A,   ",
        "100,A,open",
        "100,A,Open",
        "100,A,PAUSED",
        "100,A,RESUMED",
        "100,A,CLOSED",
        "100,A,RE-OPEN",
        "100,A,INVALID",
        "١٢٣,A,OPEN",
        "²³,A,OPEN",
    ]
    check_sla("test_malformed_lines_only", stream, [])


def test_malformed_lines_do_not_affect_now():
    stream = [
        "100,A,OPEN",
        "999999999,A,INVALID_EVENT",
        "888888888,,OPEN",
        "777777777,A",
        "666666666,A,OPEN,EXTRA",
        "555555555,A,open",
        "444444444,-10,OPEN",
    ]
    # 'now' must remain 100. A is RUNNING: used_ms = 100 - 100 = 0.
    expected = [
        {"ticket_id": "A", "used_ms": 0, "breached": False, "status": "open"}
    ]
    check_sla("test_malformed_lines_do_not_affect_now", stream, expected)


def test_state_table_not_opened():
    # 1. NOT_OPENED + OPEN -> to RUNNING, used time starts at 0
    stream1 = ["100,T01,OPEN", "200,OTHER,OPEN"]
    expected1 = [
        {"ticket_id": "OTHER", "used_ms": 0, "breached": False, "status": "open"},
        {"ticket_id": "T01", "used_ms": 100, "breached": False, "status": "open"},
    ]
    check_sla("test_not_opened_open", stream1, expected1)

    # 2. NOT_OPENED + PAUSE -> ignored
    check_sla("test_not_opened_pause", ["100,T,PAUSE"], [])

    # 3. NOT_OPENED + RESUME -> ignored
    check_sla("test_not_opened_resume", ["100,T,RESUME"], [])

    # 4. NOT_OPENED + CLOSE -> ignored
    check_sla("test_not_opened_close", ["100,T,CLOSE"], [])

    # 5. NOT_OPENED + REOPEN -> ignored
    check_sla("test_not_opened_reopen", ["100,T,REOPEN"], [])

    # Sequence of all invalid transitions from NOT_OPENED
    stream_all_ignored = [
        "100,X,PAUSE",
        "200,X,RESUME",
        "300,X,CLOSE",
        "400,X,REOPEN",
    ]
    check_sla("test_not_opened_all_ignored", stream_all_ignored, [])


def test_state_table_running():
    # 6. RUNNING + OPEN -> ignored (stays RUNNING, accumulates from original start)
    stream_open = ["100,T,OPEN", "200,T,OPEN", "300,T,CLOSE"]
    expected_open = [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    check_sla("test_running_open", stream_open, expected_open)

    # 7. RUNNING + PAUSE -> to PAUSED
    stream_pause = ["100,T,OPEN", "200,T,PAUSE", "500,OTHER,OPEN"]
    expected_pause = [
        {"ticket_id": "OTHER", "used_ms": 0, "breached": False, "status": "open"},
        {"ticket_id": "T", "used_ms": 100, "breached": False, "status": "open"},
    ]
    check_sla("test_running_pause", stream_pause, expected_pause)

    # 8. RUNNING + RESUME -> ignored
    stream_resume = ["100,T,OPEN", "200,T,RESUME", "300,T,CLOSE"]
    expected_resume = [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    check_sla("test_running_resume", stream_resume, expected_resume)

    # 9. RUNNING + CLOSE -> to CLOSED
    stream_close = ["100,T,OPEN", "300,T,CLOSE"]
    expected_close = [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    check_sla("test_running_close", stream_close, expected_close)

    # 10. RUNNING + REOPEN -> ignored
    stream_reopen = ["100,T,OPEN", "200,T,REOPEN", "300,T,CLOSE"]
    expected_reopen = [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    check_sla("test_running_reopen", stream_reopen, expected_reopen)


def test_state_table_paused():
    # 11. PAUSED + OPEN -> ignored
    stream_open = ["100,T,OPEN", "200,T,PAUSE", "300,T,OPEN", "400,T,CLOSE"]
    expected_open = [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    check_sla("test_paused_open", stream_open, expected_open)

    # 12. PAUSED + PAUSE -> ignored
    stream_pause = ["100,T,OPEN", "200,T,PAUSE", "300,T,PAUSE", "400,T,RESUME", "500,T,CLOSE"]
    expected_pause = [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    check_sla("test_paused_pause", stream_pause, expected_pause)

    # 13. PAUSED + RESUME -> to RUNNING
    stream_resume = ["100,T,OPEN", "200,T,PAUSE", "300,T,RESUME", "400,T,CLOSE"]
    expected_resume = [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    check_sla("test_paused_resume", stream_resume, expected_resume)

    # 14. PAUSED + CLOSE -> to CLOSED (stretch between PAUSE and CLOSE does not count)
    stream_close = ["100,T,OPEN", "200,T,PAUSE", "400,T,CLOSE"]
    expected_close = [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    check_sla("test_paused_close", stream_close, expected_close)

    # 15. PAUSED + REOPEN -> ignored
    stream_reopen = ["100,T,OPEN", "200,T,PAUSE", "300,T,REOPEN", "400,T,RESUME", "500,T,CLOSE"]
    expected_reopen = [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    check_sla("test_paused_reopen", stream_reopen, expected_reopen)


def test_state_table_closed():
    # 16. CLOSED + OPEN -> to RUNNING, used time resets to 0
    stream_open = ["100,T,OPEN", "200,T,CLOSE", "300,T,OPEN", "400,T,CLOSE"]
    expected_open = [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    check_sla("test_closed_open", stream_open, expected_open)

    # 17. CLOSED + PAUSE -> ignored
    stream_pause = ["100,T,OPEN", "200,T,CLOSE", "300,T,PAUSE", "500,OTHER,OPEN"]
    expected_pause = [
        {"ticket_id": "OTHER", "used_ms": 0, "breached": False, "status": "open"},
        {"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"},
    ]
    check_sla("test_closed_pause", stream_pause, expected_pause)

    # 18. CLOSED + RESUME -> ignored
    stream_resume = ["100,T,OPEN", "200,T,CLOSE", "300,T,RESUME", "500,OTHER,OPEN"]
    expected_resume = [
        {"ticket_id": "OTHER", "used_ms": 0, "breached": False, "status": "open"},
        {"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"},
    ]
    check_sla("test_closed_resume", stream_resume, expected_resume)

    # 19. CLOSED + CLOSE -> ignored
    stream_close = ["100,T,OPEN", "200,T,CLOSE", "300,T,CLOSE"]
    expected_close = [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    check_sla("test_closed_close", stream_close, expected_close)

    # 20. CLOSED + REOPEN -> to RUNNING, used time continues from its total
    stream_reopen = ["100,T,OPEN", "200,T,CLOSE", "300,T,REOPEN", "400,T,CLOSE"]
    expected_reopen = [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    check_sla("test_closed_reopen", stream_reopen, expected_reopen)


def test_closed_open_vs_reopen_at_stream_end():
    # Ticket reset by OPEN and still RUNNING at end of stream
    stream_open = ["100,T,OPEN", "200,T,CLOSE", "300,T,OPEN", "500,OTHER,OPEN"]
    expected_open = [
        {"ticket_id": "OTHER", "used_ms": 0, "breached": False, "status": "open"},
        {"ticket_id": "T", "used_ms": 200, "breached": False, "status": "open"},
    ]
    check_sla("test_closed_open_stream_end", stream_open, expected_open)

    # Ticket continued by REOPEN and still RUNNING at end of stream
    stream_reopen = ["100,T,OPEN", "200,T,CLOSE", "300,T,REOPEN", "500,OTHER,OPEN"]
    expected_reopen = [
        {"ticket_id": "OTHER", "used_ms": 0, "breached": False, "status": "open"},
        {"ticket_id": "T", "used_ms": 300, "breached": False, "status": "open"},
    ]
    check_sla("test_closed_reopen_stream_end", stream_reopen, expected_reopen)


def test_sla_boundaries():
    # SLA limit: 14,400,000 ms. Breached only if used_ms > 14,400,000.

    # 1. Exactly 14,400,000 ms (CLOSED) -> breached: False
    s1 = ["0,SLA,OPEN", "14400000,SLA,CLOSE"]
    e1 = [{"ticket_id": "SLA", "used_ms": 14400000, "breached": False, "status": "closed"}]
    check_sla("test_sla_exact_closed", s1, e1)

    # 2. 14,399,999 ms (CLOSED) -> breached: False
    s2 = ["0,SLA,OPEN", "14399999,SLA,CLOSE"]
    e2 = [{"ticket_id": "SLA", "used_ms": 14399999, "breached": False, "status": "closed"}]
    check_sla("test_sla_minus_one_closed", s2, e2)

    # 3. 14,400,001 ms (CLOSED) -> breached: True
    s3 = ["0,SLA,OPEN", "14400001,SLA,CLOSE"]
    e3 = [{"ticket_id": "SLA", "used_ms": 14400001, "breached": True, "status": "closed"}]
    check_sla("test_sla_plus_one_closed", s3, e3)

    # 4. Exactly 14,400,000 ms (RUNNING) -> breached: False
    s4 = ["0,SLA,OPEN", "14400000,OTHER,OPEN"]
    e4 = [
        {"ticket_id": "OTHER", "used_ms": 0, "breached": False, "status": "open"},
        {"ticket_id": "SLA", "used_ms": 14400000, "breached": False, "status": "open"},
    ]
    check_sla("test_sla_exact_running", s4, e4)

    # 5. 14,400,001 ms (RUNNING) -> breached: True
    s5 = ["0,SLA,OPEN", "14400001,OTHER,OPEN"]
    e5 = [
        {"ticket_id": "OTHER", "used_ms": 0, "breached": False, "status": "open"},
        {"ticket_id": "SLA", "used_ms": 14400001, "breached": True, "status": "open"},
    ]
    check_sla("test_sla_plus_one_running", s5, e5)

    # 6. Exactly 14,400,000 ms (PAUSED) -> breached: False
    s6 = ["0,SLA,OPEN", "14400000,SLA,PAUSE", "20000000,OTHER,OPEN"]
    e6 = [
        {"ticket_id": "OTHER", "used_ms": 0, "breached": False, "status": "open"},
        {"ticket_id": "SLA", "used_ms": 14400000, "breached": False, "status": "open"},
    ]
    check_sla("test_sla_exact_paused", s6, e6)

    # 7. 14,400,001 ms (PAUSED) -> breached: True
    s7 = ["0,SLA,OPEN", "14400001,SLA,PAUSE", "20000000,OTHER,OPEN"]
    e7 = [
        {"ticket_id": "OTHER", "used_ms": 0, "breached": False, "status": "open"},
        {"ticket_id": "SLA", "used_ms": 14400001, "breached": True, "status": "open"},
    ]
    check_sla("test_sla_plus_one_paused", s7, e7)

    # 8. Accumulation across pause to exactly 14,400,000 ms
    s8 = ["0,SLA,OPEN", "7000000,SLA,PAUSE", "8000000,SLA,RESUME", "15400000,SLA,CLOSE"]
    e8 = [{"ticket_id": "SLA", "used_ms": 14400000, "breached": False, "status": "closed"}]
    check_sla("test_sla_multi_segment_exact", s8, e8)

    # 9. Accumulation across pause to 14,400,001 ms
    s9 = ["0,SLA,OPEN", "7000000,SLA,PAUSE", "8000000,SLA,RESUME", "15400001,SLA,CLOSE"]
    e9 = [{"ticket_id": "SLA", "used_ms": 14400001, "breached": True, "status": "closed"}]
    check_sla("test_sla_multi_segment_breach", s9, e9)


def test_sla_breach_reset_and_reopen():
    # A ticket that breached earlier, is closed, then reset with OPEN
    stream_reset = [
        "0,T,OPEN",
        "15000000,T,CLOSE",
        "16000000,T,OPEN",
        "16000100,T,CLOSE",
    ]
    expected_reset = [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    check_sla("test_sla_breach_reset", stream_reset, expected_reset)

    # A ticket that was closed below SLA, then REOPENed and breaches
    stream_reopen = [
        "0,T,OPEN",
        "10000000,T,CLOSE",
        "11000000,T,REOPEN",
        "16000001,T,CLOSE",
    ]
    # used = 10,000,000 + (16,000,001 - 11,000,000) = 15,000,001
    expected_reopen = [{"ticket_id": "T", "used_ms": 15000001, "breached": True, "status": "closed"}]
    check_sla("test_sla_reopen_breach", stream_reopen, expected_reopen)


def test_ties_and_stability():
    # 1. Same timestamp: CLOSE then OPEN
    s1 = ["100,T,OPEN", "200,T,CLOSE", "200,T,OPEN"]
    # At 200: CLOSE -> CLOSED (used = 100). OPEN -> RUNNING (used resets to 0).
    # Stream ends at now = 200. T is RUNNING, used = 0 + (200 - 200) = 0.
    e1 = [{"ticket_id": "T", "used_ms": 0, "breached": False, "status": "open"}]
    check_sla("test_tie_close_then_open", s1, e1)

    # 2. Same timestamp: OPEN then CLOSE
    s2 = ["100,T,OPEN", "100,T,CLOSE"]
    e2 = [{"ticket_id": "T", "used_ms": 0, "breached": False, "status": "closed"}]
    check_sla("test_tie_open_then_close", s2, e2)

    # 3. Same timestamp: PAUSE then RESUME
    s3 = ["100,T,OPEN", "200,T,PAUSE", "200,T,RESUME", "300,T,CLOSE"]
    # At 200: PAUSE (used = 100), RESUME (RUNNING from 200). At 300: CLOSE (used = 100 + 100 = 200)
    e3 = [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}]
    check_sla("test_tie_pause_then_resume", s3, e3)

    # 4. Same timestamp: RESUME then PAUSE
    s4 = ["100,T,OPEN", "200,T,RESUME", "200,T,PAUSE", "300,T,CLOSE"]
    # At 200: RESUME on RUNNING is ignored. PAUSE -> PAUSED (used = 100).
    # At 300: CLOSE on PAUSED -> CLOSED (used remains 100).
    e4 = [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    check_sla("test_tie_resume_then_pause", s4, e4)

    # 5. Multiple transitions at timestamp 0
    s5 = ["0,T,OPEN", "0,T,PAUSE", "0,T,RESUME", "0,T,CLOSE"]
    e5 = [{"ticket_id": "T", "used_ms": 0, "breached": False, "status": "closed"}]
    check_sla("test_tie_all_at_zero", s5, e5)


def test_out_of_order_events():
    # 1. Fully reversed order stream
    stream_reversed = [
        "500,T,CLOSE",
        "400,T,RESUME",
        "300,T,PAUSE",
        "200,T,REOPEN",
        "150,T,CLOSE",
        "100,T,OPEN",
    ]
    # Sorted:
    # 100: OPEN -> RUNNING
    # 150: CLOSE -> CLOSED (used = 50)
    # 200: REOPEN -> RUNNING (start = 200, used = 50)
    # 300: PAUSE -> PAUSED (used = 50 + 100 = 150)
    # 400: RESUME -> RUNNING (start = 400, used = 150)
    # 500: CLOSE -> CLOSED (used = 150 + 100 = 250)
    expected_reversed = [{"ticket_id": "T", "used_ms": 250, "breached": False, "status": "closed"}]
    check_sla("test_out_of_order_reversed", stream_reversed, expected_reversed)

    # 2. Out-of-order with ties requiring stable sort
    stream_ties = [
        "200,T,CLOSE",   # arrives first among 200s
        "100,T,OPEN",
        "200,T,REOPEN",  # arrives second among 200s
    ]
    # Sorted by ts stably:
    # 100: OPEN -> RUNNING
    # 200: CLOSE -> CLOSED (used = 100)
    # 200: REOPEN -> RUNNING (start = 200, used = 100)
    # now = 200. T is RUNNING: used = 100 + (200 - 200) = 100, status = "open"
    expected_ties = [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "open"}]
    check_sla("test_out_of_order_ties", stream_ties, expected_ties)

    # 3. Interleaved out-of-order multiple tickets
    stream_multi = [
        "500,A,CLOSE",
        "100,B,OPEN",
        "100,A,OPEN",
        "300,B,PAUSE",
        "250,A,PAUSE",
        "400,B,CLOSE",
        "350,A,RESUME",
    ]
    # A: 100 OPEN, 250 PAUSE (150ms), 350 RESUME, 500 CLOSE (150ms) -> used = 300
    # B: 100 OPEN, 300 PAUSE (200ms), 400 CLOSE (0ms) -> used = 200
    expected_multi = [
        {"ticket_id": "A", "used_ms": 300, "breached": False, "status": "closed"},
        {"ticket_id": "B", "used_ms": 200, "breached": False, "status": "closed"},
    ]
    check_sla("test_out_of_order_multi", stream_multi, expected_multi)


def test_now_definition():
    # 1. Ignored event on unopened ticket defines 'now'
    s1 = ["100,A,OPEN", "200,A,CLOSE", "1000,UNOPENED,CLOSE"]
    # UNOPENED is well-formed so now = 1000. UNOPENED omitted because never valid OPEN.
    e1 = [{"ticket_id": "A", "used_ms": 100, "breached": False, "status": "closed"}]
    check_sla("test_now_ignored_unopened_closed", s1, e1)

    # 2. Ignored event on unopened ticket extends running ticket
    s2 = ["100,A,OPEN", "1000,UNOPENED,RESUME"]
    # A runs from 100 to 1000 -> used = 900
    e2 = [{"ticket_id": "A", "used_ms": 900, "breached": False, "status": "open"}]
    check_sla("test_now_ignored_unopened_running", s2, e2)

    # 3. Ignored event on running ticket defines 'now'
    s3 = ["100,A,OPEN", "1000,A,RESUME"]
    # RESUME ignored, now = 1000. A runs from 100 to 1000 -> used = 900
    e3 = [{"ticket_id": "A", "used_ms": 900, "breached": False, "status": "open"}]
    check_sla("test_now_ignored_on_running", s3, e3)


def test_output_ordering_codepoint():
    # Spec: "sorted by ticket_id ascending in Python's default string order (code-point order, so 'T10' sorts before 'T2')"
    tickets = ["T10", "T2", "T1", "t1", "t2", "10", "2", "A", "a"]
    stream = []
    for tid in tickets:
        stream.append(f"100,{tid},OPEN")
        stream.append(f"200,{tid},CLOSE")

    # Code points: '1'(49), '2'(50), 'A'(65), 'T'(84), 'a'(97), 't'(116)
    # "10" < "2" < "A" < "T1" < "T10" < "T2" < "a" < "t1" < "t2"
    expected_order = sorted(tickets)
    expected = [
        {"ticket_id": tid, "used_ms": 100, "breached": False, "status": "closed"}
        for tid in expected_order
    ]
    check_sla("test_output_ordering_codepoint", stream, expected)


def test_whitespace_and_formatting():
    # Surrounding whitespace and leading zeros in timestamp
    stream1 = [
        "  000100  ,  T1  ,  OPEN  ",
        "\t000250\t,\tT1\t,\tCLOSE\t",
    ]
    expected1 = [{"ticket_id": "T1", "used_ms": 150, "breached": False, "status": "closed"}]
    check_sla("test_whitespace_leading_zeros", stream1, expected1)

    # Ticket ID with internal spaces and special characters
    stream2 = [
        "  100  ,  Ticket #42 - Special  ,  OPEN  ",
        "  300  ,  Ticket #42 - Special  ,  CLOSE  ",
    ]
    expected2 = [{"ticket_id": "Ticket #42 - Special", "used_ms": 200, "breached": False, "status": "closed"}]
    check_sla("test_special_ticket_id", stream2, expected2)

    # Timestamp 0 with leading zeros
    stream3 = [
        "0000,T,OPEN",
        "00100,T,CLOSE",
    ]
    expected3 = [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}]
    check_sla("test_timestamp_zero_zeros", stream3, expected3)


def test_complex_multi_ticket_lifecycle():
    stream = [
        # T1: multiple transitions, reset by OPEN at 800
        "100,T1,OPEN",
        "200,T1,PAUSE",    # used = 100
        "300,T1,RESUME",
        "400,T1,CLOSE",    # used = 200
        "500,T1,REOPEN",
        "600,T1,PAUSE",    # used = 300
        "700,T1,CLOSE",    # used = 300
        "800,T1,OPEN",     # resets to 0!
        "900,T1,CLOSE",    # used = 100

        # T2: paused at stream end
        "150,T2,OPEN",
        "350,T2,PAUSE",    # used = 200, paused at 350. now=14400005

        # T3: running at stream end
        "50,T3,OPEN",
        "250,T3,PAUSE",    # used = 200
        "450,T3,RESUME",   # runs from 450 to 14400005 -> 14399555 ms. total = 14399755

        # T4: never validly opened
        "100,T4,PAUSE",
        "200,T4,RESUME",
        "300,T4,CLOSE",
        "400,T4,REOPEN",
        "850,T4,open",     # malformed

        # T5: breaches SLA
        "0,T5,OPEN",
        "14400005,T5,CLOSE", # used = 14400005 > 14400000 -> breached!
    ]

    expected = [
        {"ticket_id": "T1", "used_ms": 100, "breached": False, "status": "closed"},
        {"ticket_id": "T2", "used_ms": 200, "breached": False, "status": "open"},
        {"ticket_id": "T3", "used_ms": 14399755, "breached": False, "status": "open"},
        {"ticket_id": "T5", "used_ms": 14400005, "breached": True, "status": "closed"},
    ]
    check_sla("test_complex_lifecycle", stream, expected)


def main():
    tests = [
        test_example,
        test_empty_stream,
        test_malformed_lines_only,
        test_malformed_lines_do_not_affect_now,
        test_state_table_not_opened,
        test_state_table_running,
        test_state_table_paused,
        test_state_table_closed,
        test_closed_open_vs_reopen_at_stream_end,
        test_sla_boundaries,
        test_sla_breach_reset_and_reopen,
        test_ties_and_stability,
        test_out_of_order_events,
        test_now_definition,
        test_output_ordering_codepoint,
        test_whitespace_and_formatting,
        test_complex_multi_ticket_lifecycle,
    ]

    passed = 0
    failed = 0

    print(f"Running {len(tests)} test suites for support-ticket SLA clock...")

    for test in tests:
        test_name = test.__name__
        try:
            test()
            passed += 1
            print(f"  [PASS] {test_name}")
        except Exception as e:
            failed += 1
            print(f"  [FAIL] {test_name}: {e}")
            traceback.print_exc()

    print(f"\nSummary: {passed} passed, {failed} failed out of {len(tests)} test suites.")

    if failed == 0:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()