"""Cases for Problem 6. Stdlib only: this file is copied into the sandbox to generate stress inputs there.

Cases with "spec_expected" were worked out by hand from SPEC.md; the build fails if the reference disagrees.
"""


class SplitMix:
    """Version-independent PRNG (the sandbox and the host may run different Python versions)."""

    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFFFFFFFFFF

    def next(self):
        self.s = (self.s + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.s
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    def below(self, n):
        return self.next() % n

    def pick(self, seq):
        return seq[self.below(len(seq))]


def _empty(**kw):
    out = {"trades": [], "rejects": [], "stp_cancelled": [], "bids": [], "asks": [], "stops": [], "last_price": None}
    out.update(kw)
    return out


def _t(seq, price, qty, buy, sell, aggr):
    return {"seq": seq, "price": price, "qty": qty, "buy": buy, "sell": sell, "aggressor": aggr}


def public():
    return [
        {"id": "P1", "title": "price-time priority", "args": [["LIMIT,u1,a1,S,101,5", "LIMIT,u2,a2,S,100,5",
                                                              "LIMIT,u3,b1,B,101,7"]],
         "spec_expected": _empty(trades=[_t(1, 100, 5, "b1", "a2", "B"), _t(2, 101, 2, "b1", "a1", "B")],
                                 asks=[[101, [["a1", 3, 0]]]], last_price=101)},
        {"id": "P2", "title": "iceberg refresh to back", "args": [["LIMIT,u1,i1,S,100,10,ICE=4", "LIMIT,u2,s2,S,100,3",
                                                                   "MARKET,u3,m1,B,6"]],
         "spec_expected": _empty(trades=[_t(1, 100, 4, "m1", "i1", "B"), _t(2, 100, 2, "m1", "s2", "B")],
                                 asks=[[100, [["s2", 1, 0], ["i1", 4, 2]]]], last_price=100)},
        {"id": "P3", "title": "STP, duplicate, malformed", "args": [["LIMIT,u1,s1,S,100,5", "LIMIT,u2,s2,S,100,5",
                                                                     "LIMIT,u1,b1,B,100,3", "LIMIT,u9,s1,S,99,1",
                                                                     "limit,u9,x,S,99,1"]],
         "spec_expected": _empty(trades=[_t(1, 100, 3, "b1", "s2", "B")],
                                 rejects=[{"line": 3, "reason": "duplicate_id"}, {"line": 4, "reason": "malformed"}],
                                 stp_cancelled=["s1"], asks=[[100, [["s2", 2, 0]]]], last_price=100)},
        {"id": "P4", "title": "stop cascade", "args": [["LIMIT,u1,a1,S,100,1", "LIMIT,u1,a2,S,105,1",
                                                        "LIMIT,u1,a3,S,110,1", "STOP,u2,t1,B,100,1",
                                                        "STOP,u3,t2,B,105,1", "LIMIT,u4,b1,B,100,1"]],
         "spec_expected": _empty(trades=[_t(1, 100, 1, "b1", "a1", "B"), _t(2, 105, 1, "t1", "a2", "B"),
                                         _t(3, 110, 1, "t2", "a3", "B")], last_price=110)},
    ]


def _hand():
    m = "malformed"
    return [
        ("H01", "non-ASCII digits are malformed", ["LIMIT,u1,a,S,\u0661\u0660\u0660,5"],
         _empty(rejects=[{"line": 0, "reason": m}])),
        ("H02", "spaces and leading zeros", [" LIMIT , u1 , a , S , 0100 , 005 "],
         _empty(asks=[[100, [["a", 5, 0]]]])),
        ("H03", "zero quantity is malformed", ["LIMIT,u1,a,S,100,0", "LIMIT,u1,b,S,000,3"],
         _empty(rejects=[{"line": 0, "reason": m}, {"line": 1, "reason": m}])),
        ("H04", "iceberg display must be below qty", ["LIMIT,u1,a,S,100,5,ICE=5", "LIMIT,u1,b,S,100,5,ICE=0"],
         _empty(rejects=[{"line": 0, "reason": m}, {"line": 1, "reason": m}])),
        ("H05", "FOK counts hidden, excludes own orders", ["LIMIT,u1,i,S,100,10,ICE=2", "LIMIT,u2,o,S,100,5",
                                                            "LIMIT,u2,f,B,100,12,FOK"],
         _empty(rejects=[{"line": 2, "reason": "fok_unfilled"}], asks=[[100, [["i", 2, 8], ["o", 5, 0]]]])),
        ("H06", "FOK fills past a self-trade cancel", ["LIMIT,u2,o,S,100,5", "LIMIT,u1,a,S,100,3",
                                                        "LIMIT,u2,f,B,100,3,FOK"],
         _empty(trades=[_t(1, 100, 3, "f", "a", "B")], stp_cancelled=["o"], last_price=100)),
        ("H07", "POST rejects even against own order", ["LIMIT,u1,a,S,100,5", "LIMIT,u1,p,B,100,1,POST"],
         _empty(rejects=[{"line": 1, "reason": "post_would_cross"}], asks=[[100, [["a", 5, 0]]]])),
        ("H08", "amend down keeps priority", ["LIMIT,u1,a,S,100,5", "LIMIT,u2,b,S,100,5", "AMEND,a,100,2",
                                               "MARKET,u3,m,B,3"],
         _empty(trades=[_t(1, 100, 2, "m", "a", "B"), _t(2, 100, 1, "m", "b", "B")], asks=[[100, [["b", 4, 0]]]],
                last_price=100)),
        ("H09", "amend up loses priority", ["LIMIT,u1,a,S,100,5", "LIMIT,u2,b,S,100,5", "AMEND,a,100,6",
                                             "MARKET,u3,m,B,3"],
         _empty(trades=[_t(1, 100, 3, "m", "b", "B")], asks=[[100, [["b", 2, 0], ["a", 6, 0]]]], last_price=100)),
        ("H10", "market with no liquidity", ["MARKET,u1,m,B,5"],
         _empty(rejects=[{"line": 0, "reason": "no_liquidity"}])),
        ("H11", "IDs stay consumed after cancel", ["LIMIT,u1,a,S,100,5", "CANCEL,a", "LIMIT,u1,a,S,100,5",
                                                    "CANCEL,a"],
         _empty(rejects=[{"line": 2, "reason": "duplicate_id"}, {"line": 3, "reason": "unknown_id"}])),
        ("H12", "stop triggers on acceptance", ["LIMIT,u1,a,S,100,1", "LIMIT,u2,b,B,100,1", "LIMIT,u1,c,S,101,2",
                                                 "STOP,u3,t,B,99,1"],
         _empty(trades=[_t(1, 100, 1, "b", "a", "B"), _t(2, 101, 1, "t", "c", "B")], asks=[[101, [["c", 1, 0]]]],
                last_price=101)),
        ("H13", "earliest-line stop first; empty-book stop rejected", ["STOP,u1,s1,S,100,1", "STOP,u2,b1,B,90,1",
                                                                        "LIMIT,u3,x,B,95,5", "LIMIT,u4,y,S,95,1"],
         _empty(trades=[_t(1, 95, 1, "x", "y", "S"), _t(2, 95, 1, "x", "s1", "S")],
                rejects=[{"line": 1, "reason": "no_liquidity"}], bids=[[95, [["x", 3, 0]]]], last_price=95)),
        ("H14", "market that only self-trades", ["LIMIT,u1,a,S,100,2", "MARKET,u1,m,B,2"],
         _empty(rejects=[{"line": 1, "reason": "no_liquidity"}], stp_cancelled=["a"])),
        ("H15", "post-only amend that would cross", ["LIMIT,u1,p,B,99,5,POST", "LIMIT,u2,a,S,100,5", "AMEND,p,100,5"],
         _empty(rejects=[{"line": 2, "reason": "post_would_cross"}], bids=[[99, [["p", 5, 0]]]],
                asks=[[100, [["a", 5, 0]]]])),
        ("H16", "crossing amend trades", ["LIMIT,u1,p,B,99,5", "LIMIT,u2,a,S,100,3", "AMEND,p,100,5"],
         _empty(trades=[_t(1, 100, 3, "p", "a", "B")], bids=[[100, [["p", 2, 0]]]], last_price=100)),
        ("H17", "incoming iceberg uses full quantity", ["LIMIT,u1,a,S,100,7", "LIMIT,u2,i,B,100,10,ICE=3"],
         _empty(trades=[_t(1, 100, 7, "i", "a", "B")], bids=[[100, [["i", 3, 0]]]], last_price=100)),
        ("H18", "amend down takes hidden first", ["LIMIT,u1,i,S,100,10,ICE=4", "AMEND,i,100,5"],
         _empty(asks=[[100, [["i", 4, 1]]]])),
        ("H19", "cancel a stop", ["STOP,u1,t,B,100,1", "CANCEL,t", "AMEND,t,100,1"],
         _empty(rejects=[{"line": 2, "reason": "unknown_id"}])),
        ("H20", "amend cannot touch a stop", ["STOP,u1,t,B,100,1", "AMEND,t,101,1"],
         _empty(rejects=[{"line": 1, "reason": "unknown_id"}], stops=[["t", "B", 100, 1]])),
        ("H21", "trailing comma is malformed", ["LIMIT,u1,a,S,100,5,"],
         _empty(rejects=[{"line": 0, "reason": m}])),
        ("H22", "IOC with nothing to hit", ["LIMIT,u1,i,B,100,5,IOC"], _empty()),
        ("H23", "one aggressor refreshes an iceberg twice", ["LIMIT,u1,i,S,100,10,ICE=3", "MARKET,u2,m,B,8"],
         _empty(trades=[_t(1, 100, 3, "m", "i", "B"), _t(2, 100, 3, "m", "i", "B"), _t(3, 100, 2, "m", "i", "B")],
                asks=[[100, [["i", 1, 1]]]], last_price=100)),
        ("H24", "stop waits for a first trade", ["STOP,u1,s,S,100,1"], _empty(stops=[["s", "S", 100, 1]])),
        ("H25", "best bid first for an incoming sell", ["LIMIT,u1,b1,B,99,1", "LIMIT,u1,b2,B,101,1",
                                                         "LIMIT,u1,b3,B,100,1", "LIMIT,u2,s,S,98,2"],
         _empty(trades=[_t(1, 101, 1, "b2", "s", "S"), _t(2, 100, 1, "b3", "s", "S")], bids=[[99, [["b1", 1, 0]]]],
                last_price=100)),
        ("H26", "lowercase side and flag are malformed", ["LIMIT,u1,a,s,100,5", "LIMIT,u1,b,S,100,5,ioc",
                                                          "LIMIT,u-1,c,S,100,5"],
         _empty(rejects=[{"line": 0, "reason": m}, {"line": 1, "reason": m}, {"line": 2, "reason": m}])),
        ("H27", "same price, same total: no change", ["LIMIT,u1,a,S,100,5", "LIMIT,u2,b,S,100,5", "AMEND,a,100,5",
                                                       "MARKET,u3,m,B,1"],
         _empty(trades=[_t(1, 100, 1, "m", "a", "B")], asks=[[100, [["a", 4, 0], ["b", 5, 0]]]], last_price=100)),
    ]


def _random_lines(rng, n):
    owners = ["u1", "u2", "u3", "u4"]
    lines, ids = [], []
    for k in range(n):
        r = rng.below(100)
        oid = f"o{k}" if rng.below(12) else (rng.pick(ids) if ids else "o0")
        side = rng.pick("BS")
        price = 95 + rng.below(11)
        qty = 1 + rng.below(9)
        owner = rng.pick(owners)
        if r < 40:
            flag = rng.pick(["", "", "", ",IOC", ",FOK", ",POST", f",ICE={1 + rng.below(3)}"])
            lines.append(f"LIMIT,{owner},{oid},{side},{price},{qty}{flag}")
        elif r < 50:
            lines.append(f"MARKET,{owner},{oid},{side},{qty}")
        elif r < 60:
            lines.append(f"STOP,{owner},{oid},{side},{price},{qty}")
        elif r < 72:
            lines.append(f"CANCEL,{rng.pick(ids) if ids else 'zz'}")
        elif r < 88:
            lines.append(f"AMEND,{rng.pick(ids) if ids else 'zz'},{price},{qty}")
        else:
            lines.append(rng.pick(["", "LIMIT,u1", "MARKET,u1,x,B,0", "CANCEL,", "AMEND,o1,100", "STOP,u1,s,X,1,1",
                                   "LIMIT,u1,q,B,100,5,ICE=9", "  ", "LIMIT,u1,q,B,1e2,5"]))
        ids.append(oid)
    return lines


def hidden():
    out = [{"id": i, "title": t, "args": [lines], "spec_expected": exp} for i, t, lines, exp in _hand()]
    rng = SplitMix(6006)
    for k in range(90):
        out.append({"id": f"R{k + 1:02d}", "title": "random mixed session", "args": [_random_lines(rng, 8 + rng.below(40))]})
    return out


def stress():
    return [{"id": "S1", "title": "200k mixed commands", "seed": 61, "n": 200000, "band": 2000},
            {"id": "S2", "title": "deep book swept by market orders", "seed": 62, "n": 150000, "band": 60000},
            {"id": "S3", "title": "icebergs, amends and stops", "seed": 63, "n": 120000, "band": 300}]


def stress_args(case):
    rng = SplitMix(case["seed"])
    n, band = case["n"], case["band"]
    lines, live = [], []
    for k in range(n):
        r = rng.below(1000)
        owner = f"w{rng.below(50)}"
        side = "B" if rng.below(2) else "S"
        mid = 1_000_000
        price = mid + rng.below(band) - band // 2 + (band // 8 if side == "S" else -band // 8)
        qty = 1 + rng.below(500)
        if r < 600:
            flag = ""
            f = rng.below(20)
            if f == 0:
                flag = ",IOC"
            elif f == 1:
                flag = ",POST"
            elif f < 5 and qty > 1:
                flag = f",ICE={1 + rng.below(qty - 1)}"
            elif f == 5:
                flag = ",FOK"
            lines.append(f"LIMIT,{owner},L{k},{side},{price},{qty}{flag}")
            live.append(f"L{k}")
        elif r < 640:
            lines.append(f"MARKET,{owner},M{k},{side},{qty * (20 if case['id'] == 'S2' else 1)}")
        elif r < 660:
            lines.append(f"STOP,{owner},T{k},{side},{price},{qty}")
            live.append(f"T{k}")
        elif r < 850 and live:
            lines.append(f"CANCEL,{live[rng.below(len(live))]}")
        elif live:
            tgt = live[rng.below(len(live))]
            lines.append(f"AMEND,{tgt},{price if rng.below(2) else mid},{qty}")
        else:
            lines.append("CANCEL,none")
    return [lines]
