"""Cases for Problem 9. Stdlib only (copied into the sandbox: stress inputs are generated there).

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

    def chance(self, num, den):
        return self.below(den) < num


def cat(**items):
    """cat(a=(price, category), ...)"""
    return {k: {"price": p, "category": c} for k, (p, c) in items.items()}


def cart(*pairs):
    return [{"sku": s, "qty": q} for s, q in pairs]


def pct(pid, category, percent, min_qty, priority, **kw):
    return dict(id=pid, type="percent", category=category, percent=percent, min_qty=min_qty, priority=priority, **kw)


def bxgy(pid, skus, buy, get, priority, **kw):
    return dict(id=pid, type="bxgy", skus=skus, buy=buy, get=get, priority=priority, **kw)


def bundle(pid, skus, price, priority, **kw):
    return dict(id=pid, type="bundle", skus=skus, price=price, priority=priority, **kw)


def thr(pid, min_subtotal, amount_off, priority, **kw):
    return dict(id=pid, type="threshold", min_subtotal=min_subtotal, amount_off=amount_off, priority=priority, **kw)


def out(lines, applied):
    return {"lines": lines, "applied": applied, "total": sum(lines)}


def case(cid, title, catalog, items, promos, expected=None):
    c = {"id": cid, "title": title, "args": [catalog, items, promos]}
    if expected is not None:
        c["spec_expected"] = expected
    return c


MEAL = cat(burger=(650, "food"), fries=(300, "food"), soda=(250, "drink"))


def public():
    return [
        case("P1", "order matters", cat(tea=(450, "drink"), mug=(1200, "home")), cart(("tea", 3), ("mug", 1)),
             [pct("D10", "drink", 10, 3, 1), thr("T5", 2500, 500, 2)], out([1086, 964], ["T5"])),
        case("P2", "buy 2 get 1", cat(a=(500, "x"), b=(300, "x"), c=(300, "x")), cart(("a", 2), ("b", 1), ("c", 2)),
             [bxgy("B21", ["a", "b", "c"], 2, 1, 1)], out([1000, 0, 600], ["B21"])),
        case("P3", "bundle allocation", MEAL, cart(("burger", 2), ("fries", 1), ("soda", 2)),
             [bundle("MEAL", ["burger", "fries", "soda"], 900, 1)], out([1138, 225, 437], ["MEAL"])),
        case("P4", "group conflict, tie by id", cat(x=(1000, "c")), cart(("x", 1)),
             [pct("B", "c", 10, 1, 1, group="g"), thr("A", 0, 100, 1, group="g")], out([900], ["A"])),
    ]


def hand():
    return [
        case("H01", "percent floors per unit", cat(p=(999, "c")), cart(("p", 2)), [pct("P15", "c", 15, 2, 1)],
             out([1700], ["P15"])),
        case("H02", "percent skips claimed units", cat(a=(1000, "c"), b=(1000, "c")), cart(("a", 1), ("b", 1)),
             [bundle("BND", ["a", "b"], 1500, 1), pct("PC", "c", 50, 1, 2)], out([500, 500], ["PC"])),
        case("H03", "bxgy: last claimed units are free, ties by unit order",
             cat(x=(400, "k"), y=(400, "k"), z=(100, "k")), cart(("z", 1), ("x", 2), ("y", 2), ("z", 1)),
             [bxgy("B", ["x", "y", "z"], 1, 1, 1)], out([0, 800, 400, 0], ["B"])),
        case("H04", "bxgy leaves a remainder for a later percent", cat(s=(1000, "shoe")), cart(("s", 3)),
             [bxgy("B", ["s"], 1, 1, 1), pct("P", "shoe", 20, 1, 2)], out([1800], ["B", "P"])),
        case("H05", "threshold allocation with a zero-price unit", cat(a=(0, "c"), b=(333, "c")),
             cart(("a", 1), ("b", 3)), [thr("T", 999, 100, 1)], out([0, 899], ["T"])),
        case("H06", "threshold capped at the subtotal", cat(a=(150, "c")), cart(("a", 2)), [thr("T", 300, 1000, 1)],
             out([0], ["T"])),
        case("H07", "exclusive promotion stands alone", cat(a=(1000, "c")), cart(("a", 2)),
             [pct("X", "c", 30, 1, 1, exclusive=True), pct("Y", "c", 20, 1, 1), thr("Z", 0, 300, 2)],
             out([1300], ["Y", "Z"])),
        case("H08", "fewer promotions beat the id order", cat(a=(1000, "c")), cart(("a", 1)),
             [thr("A", 0, 50, 1), thr("B", 0, 50, 2), thr("C", 1000, 100, 3)], out([900], ["C"])),
        case("H09", "ids compare by code point", cat(a=(500, "c")), cart(("a", 1)),
             [thr("b", 0, 100, 1, group="g"), pct("B", "c", 20, 1, 1, group="g")], out([400], ["B"])),
        case("H10", "applied by priority, not by id", cat(a=(1000, "c")), cart(("a", 1)),
             [pct("Z1", "c", 50, 1, 1), thr("A1", 600, 200, 2)], out([500], ["Z1"])),
        case("H11", "equal priority applied by id", cat(a=(1000, "c")), cart(("a", 1)),
             [pct("b2", "c", 50, 1, 1), thr("a2", 600, 200, 1)], out([400], ["a2", "b2"])),
        case("H12", "bundle repeats while units remain", cat(a=(600, "c"), b=(400, "c")),
             cart(("a", 1), ("b", 1), ("a", 1), ("b", 1)), [bundle("M", ["a", "b"], 900, 1)],
             out([540, 360, 540, 360], ["M"])),
        case("H13", "bundle allocation ties by unit order, not sku order", MEAL,
             cart(("soda", 1), ("burger", 1), ("fries", 1)), [bundle("MEAL", ["burger", "fries", "soda"], 900, 1)],
             out([188, 487, 225], ["MEAL"])),
        case("H14", "no promotions", cat(a=(100, "c")), cart(("a", 3)), [], out([300], [])),
        case("H15", "buy 2 get 2 with a partial group", cat(a=(300, "k"), b=(200, "k"), c=(100, "k")),
             cart(("a", 1), ("b", 2), ("c", 2)), [bxgy("B22", ["a", "b", "c"], 2, 2, 1)],
             out([300, 200, 100], ["B22"])),
        case("H16", "group conflict with an ungrouped promotion", cat(a=(1000, "c")), cart(("a", 1)),
             [thr("G1", 0, 100, 1, group="g"), thr("G2", 0, 200, 1, group="g"), pct("N", "c", 10, 1, 0)],
             out([700], ["N", "G2"])),
        case("H17", "threshold after bxgy: free units get no share", cat(a=(500, "k")), cart(("a", 2)),
             [bxgy("B", ["a"], 1, 1, 1), thr("T", 400, 100, 2)], out([400], ["B", "T"])),
        case("H18", "min_qty counts units across lines", cat(a=(250, "c")), cart(("a", 1), ("a", 3)),
             [pct("P", "c", 10, 4, 1)], out([225, 675], ["P"])),
        case("H19", "100 percent", cat(a=(199, "c")), cart(("a", 2)), [pct("F", "c", 100, 2, 1)], out([0], ["F"])),
        case("H20", "bundle stops when it would not lower the price", cat(a=(400, "c1"), b=(400, "c2")),
             cart(("a", 1), ("b", 1)), [bundle("M", ["a", "b"], 800, 1), pct("P", "c1", 50, 1, 2, group="g"),
                                        thr("T", 0, 1, 3, group="g")],
             out([200, 400], ["P"])),
    ]


# ── Random cases ────────────────────────────────────────────────────────────
PRICES = [0, 99, 100, 150, 199, 250, 333, 400, 499, 500, 999, 1200, 1999]
CATS = ["a", "b", "c"]
IDS = ["A", "B", "a", "b", "Z9", "x1", "AB", "A1", "b0", "M", "m", "Q7"]


def rand_promo(r, pid, skus):
    kind = r.pick(["percent", "percent", "bxgy", "bxgy", "bundle", "threshold", "threshold"])
    extra = {}
    if r.chance(1, 3):
        extra["group"] = r.pick(["g1", "g2"])
    if r.chance(1, 12):
        extra["exclusive"] = True
    prio = r.below(4)
    if kind == "percent":
        return pct(pid, r.pick(CATS), r.pick([5, 10, 15, 25, 33, 50, 100]), 1 + r.below(4), prio, **extra)
    if kind == "bxgy":
        k = 1 + r.below(len(skus))
        chosen = []
        for _ in range(k):
            s = r.pick(skus)
            if s not in chosen:
                chosen.append(s)
        return bxgy(pid, chosen, 1 + r.below(3), 1 + r.below(2), prio, **extra)
    if kind == "bundle":
        chosen = []
        while len(chosen) < 2 or (len(chosen) < len(skus) and r.chance(1, 3)):
            s = r.pick(skus)
            if s not in chosen:
                chosen.append(s)
        return bundle(pid, chosen, r.pick([0, 199, 500, 750, 900, 1000, 1500]), prio, **extra)
    return thr(pid, r.pick([0, 500, 1000, 2000, 5000]), r.pick([1, 50, 100, 333, 1000, 10000]), prio, **extra)


def rand_case(r, n_skus, n_lines, max_qty, n_promos):
    skus = ["s" + str(i) for i in range(n_skus)]
    catalog = {s: {"price": r.pick(PRICES), "category": r.pick(CATS)} for s in skus}
    items = [{"sku": r.pick(skus), "qty": 1 + r.below(max_qty)} for _ in range(n_lines)]
    ids = []
    while len(ids) < n_promos:
        pid = r.pick(IDS) if len(ids) < len(IDS) // 2 else "P" + str(len(ids))
        if pid not in ids:
            ids.append(pid)
    promos = [rand_promo(r, pid, skus) for pid in ids]
    return [catalog, items, promos]


def random_cases():
    res = []
    for i in range(100):
        r = SplitMix(55000 + i)
        args = rand_case(r, 2 + r.below(4), 1 + r.below(6), 5, r.below(7))
        res.append({"id": f"R{i + 1:03d}", "title": "random cart", "args": args})
    return res


def hidden():
    return hand() + random_cases()


def stress():
    return [{"id": f"S{k}", "title": "10 promotions, ~200 units", "seed": 777 + k} for k in (1, 2, 3)]


def stress_args(c):
    r = SplitMix(c["seed"])
    while True:
        args = rand_case(r, 6, 20, 19, 10)
        if 150 <= sum(item["qty"] for item in args[1]) <= 200:
            return args
