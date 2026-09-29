import solution
import sys


def assert_equal(actual, expected, msg=""):
    assert actual == expected, (
        f"Assertion failed: {msg}\n"
        f"Expected:\n  {expected}\n"
        f"Actual:\n  {actual}"
    )


def validate_types_and_schema(results):
    assert isinstance(results, list), f"Expected list, got {type(results)}"
    for idx, item in enumerate(results):
        assert isinstance(item, dict), f"Item {idx} is not a dict: {type(item)}"
        expected_keys = {"ticket_id", "used_ms", "breached", "status"}
        assert set(item.keys()) == expected_keys, (
            f"Item {idx} has invalid keys: {set(item.keys())} != {expected_keys}"
        )
        assert isinstance(item["ticket_id"], str), (
            f"Item {idx} ticket_id is not str: {type(item['ticket_id'])}"
        )
        assert type(item["used_ms"]) is int, (
            f"Item {idx} used_ms is not int: {type(item['used_ms'])}"
        )
        assert type(item["breached"]) is bool, (
            f"Item {idx} breached is not bool: {type(item['breached'])}"
        )
        assert item["status"] in ("open", "closed"), (
            f"Item {idx} status is invalid: {item['status']}"
        )


def main():
    test_count = 0
    passed_count = 0

    def run_case(name, stream, expected):
        nonlocal test_count, passed_count
        test_count += 1
        try:
            actual = solution.compute_sla(stream)
            validate_types_and_schema(actual)
            assert_equal(actual, expected, f"Test '{name}' failed")
            passed_count += 1
            print(f"PASS: {name}")
        except Exception as e:
            print(f"FAIL: {name} - {e}")
            raise

    try:
        # 1. Empty & Non-Event Streams
        run_case("Empty stream", [], [])

        run_case(
            "Stream with only malformed lines",
            [
                "",
                "   ",
                "\t\n",
                "100",
                "100,T1",
                "100,T1,OPEN,EXTRA",
                "-100,T1,OPEN",
                "+100,T1,OPEN",
                "100.5,T1,OPEN",
                "abc,T1,OPEN",
                "100,,OPEN",
                "100,   ,OPEN",
                "100,T1,open",
                "100,T1,Open",
                "100,T1,PENDING",
            ],
            [],
        )

        run_case(
            "Stream with only events on NOT_OPENED tickets",
            [
                "100,T1,PAUSE",
                "200,T1,RESUME",
                "300,T1,CLOSE",
                "400,T1,REOPEN",
            ],
            [],
        )

        # 2. Complete State-Transition Matrix (5 Events x 4 States = 20 cells)
        # State: NOT_OPENED
        run_case(
            "Matrix: NOT_OPENED + OPEN -> to RUNNING, used=0",
            ["100,T,OPEN"],
            [{"ticket_id": "T", "used_ms": 0, "breached": False, "status": "open"}],
        )
        run_case(
            "Matrix: NOT_OPENED + PAUSE -> ignored",
            ["100,T,PAUSE"],
            [],
        )
        run_case(
            "Matrix: NOT_OPENED + RESUME -> ignored",
            ["100,T,RESUME"],
            [],
        )
        run_case(
            "Matrix: NOT_OPENED + CLOSE -> ignored",
            ["100,T,CLOSE"],
            [],
        )
        run_case(
            "Matrix: NOT_OPENED + REOPEN -> ignored",
            ["100,T,REOPEN"],
            [],
        )

        # State: RUNNING
        run_case(
            "Matrix: RUNNING + OPEN -> ignored",
            [
                "100,T,OPEN",
                "200,T,OPEN",  # ignored, clock continues from 100
                "500,T,CLOSE",
            ],
            [{"ticket_id": "T", "used_ms": 400, "breached": False, "status": "closed"}],
        )
        run_case(
            "Matrix: RUNNING + PAUSE -> to PAUSED",
            [
                "100,T,OPEN",
                "300,T,PAUSE",
                "600,DUMMY,PAUSE",  # advances 'now' to 600; T is paused so stops at 300
            ],
            [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "open"}],
        )
        run_case(
            "Matrix: RUNNING + RESUME -> ignored",
            [
                "100,T,OPEN",
                "200,T,RESUME",  # ignored, stays RUNNING
                "500,T,CLOSE",
            ],
            [{"ticket_id": "T", "used_ms": 400, "breached": False, "status": "closed"}],
        )
        run_case(
            "Matrix: RUNNING + CLOSE -> to CLOSED",
            [
                "100,T,OPEN",
                "400,T,CLOSE",
            ],
            [{"ticket_id": "T", "used_ms": 300, "breached": False, "status": "closed"}],
        )
        run_case(
            "Matrix: RUNNING + REOPEN -> ignored",
            [
                "100,T,OPEN",
                "200,T,REOPEN",  # ignored, stays RUNNING
                "500,T,CLOSE",
            ],
            [{"ticket_id": "T", "used_ms": 400, "breached": False, "status": "closed"}],
        )

        # State: PAUSED
        run_case(
            "Matrix: PAUSED + OPEN -> ignored",
            [
                "100,T,OPEN",
                "200,T,PAUSE",
                "300,T,OPEN",  # ignored, remains PAUSED
                "400,T,RESUME",
                "600,T,CLOSE",
            ],
            # used: (200 - 100) + (600 - 400) = 100 + 200 = 300
            [{"ticket_id": "T", "used_ms": 300, "breached": False, "status": "closed"}],
        )
        run_case(
            "Matrix: PAUSED + PAUSE -> ignored",
            [
                "100,T,OPEN",
                "200,T,PAUSE",
                "300,T,PAUSE",  # ignored
                "400,T,RESUME",
                "600,T,CLOSE",
            ],
            [{"ticket_id": "T", "used_ms": 300, "breached": False, "status": "closed"}],
        )
        run_case(
            "Matrix: PAUSED + RESUME -> to RUNNING",
            [
                "100,T,OPEN",
                "200,T,PAUSE",
                "400,T,RESUME",
                "500,T,CLOSE",
            ],
            # used: (200 - 100) + (500 - 400) = 100 + 100 = 200
            [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}],
        )
        run_case(
            "Matrix: PAUSED + CLOSE -> to CLOSED",
            [
                "100,T,OPEN",
                "200,T,PAUSE",
                "500,T,CLOSE",  # time between 200 and 500 does NOT count
            ],
            [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}],
        )
        run_case(
            "Matrix: PAUSED + REOPEN -> ignored",
            [
                "100,T,OPEN",
                "200,T,PAUSE",
                "300,T,REOPEN",  # ignored, remains PAUSED
                "400,T,RESUME",
                "600,T,CLOSE",
            ],
            [{"ticket_id": "T", "used_ms": 300, "breached": False, "status": "closed"}],
        )

        # State: CLOSED
        run_case(
            "Matrix: CLOSED + OPEN -> to RUNNING, used time resets to 0",
            [
                "100,T,OPEN",
                "300,T,CLOSE",  # used = 200
                "500,T,OPEN",   # resets used time to 0!
                "700,T,CLOSE",  # used = 200
            ],
            [{"ticket_id": "T", "used_ms": 200, "breached": False, "status": "closed"}],
        )
        run_case(
            "Matrix: CLOSED + PAUSE -> ignored",
            [
                "100,T,OPEN",
                "300,T,CLOSE",  # used = 200
                "400,T,PAUSE",  # ignored
                "500,T,REOPEN", # continues from 200
                "700,T,CLOSE",  # used = 200 + 200 = 400
            ],
            [{"ticket_id": "T", "used_ms": 400, "breached": False, "status": "closed"}],
        )
        run_case(
            "Matrix: CLOSED + RESUME -> ignored",
            [
                "100,T,OPEN",
                "300,T,CLOSE",  # used = 200
                "400,T,RESUME", # ignored
                "500,T,REOPEN", # continues from 200
                "700,T,CLOSE",  # used = 200 + 200 = 400
            ],
            [{"ticket_id": "T", "used_ms": 400, "breached": False, "status": "closed"}],
        )
        run_case(
            "Matrix: CLOSED + CLOSE -> ignored",
            [
                "100,T,OPEN",
                "300,T,CLOSE",  # used = 200
                "400,T,CLOSE",  # ignored
                "500,T,REOPEN", # continues from 200
                "700,T,CLOSE",  # used = 200 + 200 = 400
            ],
            [{"ticket_id": "T", "used_ms": 400, "breached": False, "status": "closed"}],
        )
        run_case(
            "Matrix: CLOSED + REOPEN -> to RUNNING, used time continues",
            [
                "100,T,OPEN",
                "300,T,CLOSE",  # used = 200
                "500,T,REOPEN", # continues from 200
                "800,T,CLOSE",  # used = 200 + 300 = 500
            ],
            [{"ticket_id": "T", "used_ms": 500, "breached": False, "status": "closed"}],
        )

        # 3. Exact SLA Boundary (14,400,000 ms limit)
        LIMIT = 14_400_000
        run_case(
            "SLA Boundary: exactly LIMIT - 1 ms (closed)",
            [
                "0,T,OPEN",
                f"{LIMIT - 1},T,CLOSE",
            ],
            [{"ticket_id": "T", "used_ms": LIMIT - 1, "breached": False, "status": "closed"}],
        )
        run_case(
            "SLA Boundary: exactly LIMIT ms does not breach (closed)",
            [
                "0,T,OPEN",
                f"{LIMIT},T,CLOSE",
            ],
            [{"ticket_id": "T", "used_ms": LIMIT, "breached": False, "status": "closed"}],
        )
        run_case(
            "SLA Boundary: exactly LIMIT + 1 ms breaches (closed)",
            [
                "0,T,OPEN",
                f"{LIMIT + 1},T,CLOSE",
            ],
            [{"ticket_id": "T", "used_ms": LIMIT + 1, "breached": True, "status": "closed"}],
        )

        run_case(
            "SLA Boundary: exactly LIMIT ms does not breach (open at now)",
            [
                "0,T,OPEN",
                f"{LIMIT},DUMMY,PAUSE",  # defines 'now' as LIMIT
            ],
            [{"ticket_id": "T", "used_ms": LIMIT, "breached": False, "status": "open"}],
        )
        run_case(
            "SLA Boundary: exactly LIMIT + 1 ms breaches (open at now)",
            [
                "0,T,OPEN",
                f"{LIMIT + 1},DUMMY,PAUSE",  # defines 'now' as LIMIT + 1
            ],
            [{"ticket_id": "T", "used_ms": LIMIT + 1, "breached": True, "status": "open"}],
        )

        # 4. Definition of "Now"
        run_case(
            "Now: ignored well-formed event advances now, malformed event does not",
            [
                "100,T1,OPEN",
                "500,T2,PAUSE",            # well-formed line on NOT_OPENED ticket advances now to 500
                "999999,T3,INVALID_EVENT", # malformed line does NOT advance now
            ],
            # T1 was RUNNING from 100 to 500 -> used_ms = 400
            # T2 never had valid OPEN -> omitted
            # T3 malformed -> omitted
            [{"ticket_id": "T1", "used_ms": 400, "breached": False, "status": "open"}],
        )

        # 5. Ties and Stable Sort Order
        run_case(
            "Ties: OPEN then CLOSE at same timestamp",
            [
                "100,T,OPEN",
                "100,T,CLOSE",
            ],
            [{"ticket_id": "T", "used_ms": 0, "breached": False, "status": "closed"}],
        )
        run_case(
            "Ties: CLOSE then OPEN at same timestamp (CLOSE ignored)",
            [
                "100,T,CLOSE",  # ignored because NOT_OPENED
                "100,T,OPEN",   # becomes RUNNING
            ],
            [{"ticket_id": "T", "used_ms": 0, "breached": False, "status": "open"}],
        )
        run_case(
            "Ties: CLOSE then REOPEN at same timestamp vs REOPEN then CLOSE",
            [
                # Stream out of order, tie-breaking maintains stream order
                "500,T,CLOSE",
                "100,T,OPEN",
                "300,T,CLOSE",
                "300,T,REOPEN",
            ],
            # At 100: OPEN -> RUNNING
            # At 300: CLOSE -> CLOSED (used: 200)
            # At 300: REOPEN -> RUNNING (used continues from 200)
            # At 500: CLOSE -> CLOSED (used: 200 + 200 = 400)
            [{"ticket_id": "T", "used_ms": 400, "breached": False, "status": "closed"}],
        )
        run_case(
            "Ties: REOPEN then CLOSE at same timestamp",
            [
                "100,T,OPEN",
                "200,T,CLOSE",  # used = 100
                "300,T,REOPEN", # to RUNNING
                "300,T,CLOSE",  # to CLOSED (used stays 100)
            ],
            [{"ticket_id": "T", "used_ms": 100, "breached": False, "status": "closed"}],
        )
        run_case(
            "Ties: OPEN then PAUSE at same timestamp",
            [
                "100,T,OPEN",
                "100,T,PAUSE",
                "200,DUMMY,PAUSE",  # now = 200
            ],
            [{"ticket_id": "T", "used_ms": 0, "breached": False, "status": "open"}],
        )

        # 6. Out-of-Order Events
        run_case(
            "Out of order events: reversed order",
            [
                "500,T,CLOSE",
                "400,T,RESUME",
                "300,T,PAUSE",
                "100,T,OPEN",
            ],
            # Sorted:
            # 100: OPEN -> RUNNING
            # 300: PAUSE -> PAUSED (used: 200)
            # 400: RESUME -> RUNNING
            # 500: CLOSE -> CLOSED (used: 200 + 100 = 300)
            [{"ticket_id": "T", "used_ms": 300, "breached": False, "status": "closed"}],
        )

        # 7. Whitespace Trimming & Leading Zero Timestamps
        run_case(
            "Whitespace trimming & leading zero timestamps",
            [
                "  000100  ,  A  ,  OPEN  ",
                "\t 000350 \t, A ,\t PAUSE \t",
                " 000500 , A , CLOSE ",
            ],
            # used: 350 - 100 = 250, closed at 500 with no extra used time
            [{"ticket_id": "A", "used_ms": 250, "breached": False, "status": "closed"}],
        )

        # 8. Output Ordering and Case Sensitivity
        run_case(
            "Output sorting: Python default string order and case sensitivity",
            [
                "100,t1,OPEN",
                "100,T2,OPEN",
                "100,T10,OPEN",
                "100,A,OPEN",
                "100,a,OPEN",
                "100,1,OPEN",
            ],
            # Python code point order: "1" < "A" < "T10" < "T2" < "a" < "t1"
            [
                {"ticket_id": "1", "used_ms": 0, "breached": False, "status": "open"},
                {"ticket_id": "A", "used_ms": 0, "breached": False, "status": "open"},
                {"ticket_id": "T10", "used_ms": 0, "breached": False, "status": "open"},
                {"ticket_id": "T2", "used_ms": 0, "breached": False, "status": "open"},
                {"ticket_id": "a", "used_ms": 0, "breached": False, "status": "open"},
                {"ticket_id": "t1", "used_ms": 0, "breached": False, "status": "open"},
            ],
        )

        # 9. Complex lifecycle with OPEN reset vs REOPEN continuation
        run_case(
            "Complex ticket lifecycle with reset and continuation",
            [
                "0,M,OPEN",        # RUNNING, used = 0
                "1000,M,PAUSE",    # PAUSED, used = 1000
                "2000,M,RESUME",   # RUNNING, used = 1000
                "3000,M,CLOSE",    # CLOSED, used = 2000
                "4000,M,REOPEN",   # RUNNING, used continues from 2000
                "5000,M,CLOSE",    # CLOSED, used = 3000
                "6000,M,OPEN",     # RUNNING, used RESETS to 0!
                "7000,M,PAUSE",    # PAUSED, used = 1000
                "8000,M,CLOSE",    # CLOSED, used = 1000
                "9000,M,REOPEN",   # RUNNING, used continues from 1000
                "10000,DUMMY,OPEN",# now = 10000; M is RUNNING from 9000 to 10000 (+1000)
            ],
            [
                {"ticket_id": "DUMMY", "used_ms": 0, "breached": False, "status": "open"},
                {"ticket_id": "M", "used_ms": 2000, "breached": False, "status": "open"},
            ],
        )

        # 10. Multi-ticket SLA Breach Comparison
        run_case(
            "Multi-ticket SLA breach edge comparison",
            [
                "0,T_BELOW,OPEN",
                f"{LIMIT - 1},T_BELOW,CLOSE",
                "0,T_EXACT,OPEN",
                f"{LIMIT},T_EXACT,CLOSE",
                "0,T_ABOVE,OPEN",
                f"{LIMIT + 1},T_ABOVE,CLOSE",
            ],
            [
                {"ticket_id": "T_ABOVE", "used_ms": LIMIT + 1, "breached": True, "status": "closed"},
                {"ticket_id": "T_BELOW", "used_ms": LIMIT - 1, "breached": False, "status": "closed"},
                {"ticket_id": "T_EXACT", "used_ms": LIMIT, "breached": False, "status": "closed"},
            ],
        )

        print(f"\nAll {passed_count}/{test_count} tests passed successfully.")
        sys.exit(0)

    except AssertionError as e:
        print(f"\nTest suite failed on test {test_count}: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected error during testing: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()