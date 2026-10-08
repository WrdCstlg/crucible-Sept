"""Cases for Problem 12 (tax lots with wash sales). Stdlib only (copied into the sandbox like every cases.py).

Cases with "spec_expected" were worked out by hand from SPEC.md; the build fails if the reference disagrees.
Date differences quoted in comments were checked with datetime only (never with the reference).
"""
from datetime import date


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


# ── Helpers (expected values are written out by hand; gain is proceeds - basis by definition) ──
def T(d, side, sym, qty, amount):
    return {"date": d, "side": side, "symbol": sym, "qty": qty, "amount": amount}


def B(d, sym, qty, amount):
    return T(d, "BUY", sym, qty, amount)


def S(d, sym, qty, amount):
    return T(d, "SELL", sym, qty, amount)


def row(sale, lot, qty, proceeds, basis, disallowed, term):
    return {"sale": sale, "lot": lot, "qty": qty, "proceeds": proceeds, "basis": basis, "gain": proceeds - basis,
            "disallowed": disallowed, "term": term}


def piece(lot, qty, basis, carried):
    return {"lot": lot, "qty": qty, "basis": basis, "carried_days": carried}


def result(realized, open_lots, rejected, short, long_, disallowed):
    return {"realized": realized, "open_lots": open_lots, "rejected": rejected,
            "totals": {"short_term": short, "long_term": long_, "disallowed": disallowed}}


def case(cid, title, trades, identical, expected=None):
    c = {"id": cid, "title": title, "args": [trades, identical]}
    if expected is not None:
        c["spec_expected"] = expected
    return c


SH, LG = "SHORT", "LONG"


def public():
    return [
        case("P1", "a repurchase after the loss replaces part of it",
             [B("2024-01-10", "XYZ", 10, 1000), S("2024-03-01", "XYZ", 10, 700), B("2024-03-20", "XYZ", 4, 360)], [],
             result([row(1, 0, 10, 700, 1000, 120, SH)], [piece(2, 4, 480, 51)], [], -180, 0, 120)),
        case("P2", "earlier purchases of an identical symbol count; two loss rows",
             [B("2024-01-02", "AAA", 6, 600), B("2024-01-03", "AAA", 4, 500), B("2024-02-10", "BBB", 3, 270),
              S("2024-02-20", "AAA", 8, 640), B("2024-03-05", "AAA", 10, 800)], [["AAA", "BBB"]],
             result([row(3, 0, 6, 480, 600, 120, SH), row(3, 1, 2, 160, 250, 90, SH)],
                    [piece(1, 2, 250, 0), piece(2, 3, 330, 49), piece(4, 3, 300, 49), piece(4, 2, 250, 48),
                     piece(4, 5, 400, 0)], [], 0, 0, 210)),
        case("P3", "a chain; carried days make the replacement long-term",
             [B("2022-05-10", "QQ", 5, 500), S("2023-06-01", "QQ", 5, 400), B("2023-06-15", "QQ", 5, 450),
              S("2023-07-01", "QQ", 5, 500), B("2023-07-20", "QQ", 2, 180)], [],
             result([row(1, 0, 5, 400, 500, 100, LG), row(3, 2, 5, 500, 550, 20, LG)], [piece(4, 2, 200, 403)], [],
                    0, -30, 120)),
        case("P4", "unsorted input; invalid trades and an oversized sale are rejected",
             [S("2024-05-02", "ZZ", 3, 330), B("2024-05-01", "ZZ", 5, 500), S("2024-05-03", "ZZ", 3, 270),
              B("2024-02-30", "ZZ", 1, 100), T("2024-05-04", "buy", "ZZ", 1, 100), B("2024-05-04", "ZZ", 0, 0),
              S("2024-05-05", "ZZ", 2, 150)], [],
             result([row(0, 1, 3, 330, 300, 0, SH), row(6, 1, 2, 150, 200, 0, SH)], [], [2, 3, 4, 5], -20, 0, 0)),
    ]


def hand():
    return [
        # Lot 0 is 61 days old (outside the window). Window of 2024-07-01 is [06-01, 07-31]: lot 2 (07-31) is in,
        # lot 3 (08-01) is out. r = 2 of 5, D = 100*2//5 = 40. Carried = 07-01 - 05-01 = 61.
        case("H01", "window: a purchase exactly 30 days after the sale counts, 31 days does not",
             [B("2024-05-01", "A", 10, 1000), S("2024-07-01", "A", 5, 400), B("2024-07-31", "A", 2, 200),
              B("2024-08-01", "A", 3, 300)], [],
             result([row(1, 0, 5, 400, 500, 40, SH)],
                    [piece(0, 5, 500, 0), piece(2, 2, 240, 61), piece(3, 3, 300, 0)], [], -60, 0, 40)),
        # Window of 2023-03-31 is [03-01, 04-30]: lot 1 (02-28, 31 days back) is out, lot 2 (03-01) is in.
        # D = 200*2//4 = 100; carried = 03-31 - 01-01 = 89.
        case("H02", "window: an earlier purchase exactly 30 days before the sale counts, 31 days does not",
             [B("2023-01-01", "B", 4, 400), B("2023-02-28", "B", 1, 100), B("2023-03-01", "B", 2, 200),
              S("2023-03-31", "B", 4, 200)], [],
             result([row(3, 0, 4, 200, 400, 100, SH)], [piece(1, 1, 100, 0), piece(2, 2, 300, 89)], [],
                    -100, 0, 100)),
        # Lot 0 is in the window but this sale draws from it, so its 6 unsold shares never count. Only lot 2:
        # r = 3 of 4, D = 100*3//4 = 75, carried 14.
        case("H03", "the unsold remainder of a lot the loss sale draws from is never a replacement",
             [B("2024-04-01", "C", 10, 1000), S("2024-04-15", "C", 4, 300), B("2024-05-10", "C", 3, 330)], [],
             result([row(1, 0, 4, 300, 400, 75, SH)], [piece(0, 6, 600, 0), piece(2, 3, 405, 14)], [],
                    -25, 0, 75)),
        # A~B and B~C merge, so C replaces the A loss; "a" is a different symbol (case-sensitive). Carried 27.
        case("H04", "identical lists merge transitively; symbols are case-sensitive",
             [B("2024-01-05", "A", 2, 200), S("2024-02-01", "A", 2, 100), B("2024-02-05", "a", 1, 100),
              B("2024-02-10", "C", 2, 150)], [["A", "B"], ["B", "C"]],
             result([row(1, 0, 2, 100, 200, 100, SH)], [piece(2, 1, 100, 0), piece(3, 2, 250, 27)], [], 0, 0, 100)),
        # Proceeds 400 -> 200 + 200. Row lot 0 gains 100 (uses nothing); row lot 1 loses 100 and takes 2 of lot 3's
        # 3 shares: split basis 300*2//3 = 200, + D 100. Carried = 03-10 - 03-02 = 8.
        case("H05", "loss is per row: a gain row beside a loss row uses no replacement shares",
             [B("2024-03-01", "G", 2, 100), B("2024-03-02", "G", 2, 300), S("2024-03-10", "G", 4, 400),
              B("2024-03-20", "G", 3, 300)], [],
             result([row(2, 0, 2, 200, 100, 0, SH), row(2, 1, 2, 200, 300, 100, SH)],
                    [piece(3, 2, 300, 8), piece(3, 1, 100, 0)], [], 100, 0, 100)),
        # L = 7, n = 3, r = 2: D = 14//3 = 4 (not 5).
        case("H06", "disallowed is L * r // n, rounded down",
             [B("2024-01-02", "H", 3, 307), S("2024-01-20", "H", 3, 300), B("2024-01-25", "H", 2, 200)], [],
             result([row(1, 0, 3, 300, 307, 4, SH)], [piece(2, 2, 204, 18)], [], -3, 0, 4)),
        # D = 2 over four 1-share chunks: 2*1//4 = 0, 2*1//3 = 0, 2*1//2 = 1, then 1 -> 0, 0, 1, 1.
        case("H07", "D is spread over the chunks by the running floor rule",
             [B("2024-02-01", "K", 4, 402), S("2024-02-05", "K", 4, 400), B("2024-02-06", "K", 1, 100),
              B("2024-02-07", "K", 1, 100), B("2024-02-08", "K", 1, 100), B("2024-02-09", "K", 1, 100)], [],
             result([row(1, 0, 4, 400, 402, 2, SH)],
                    [piece(2, 1, 100, 4), piece(3, 1, 100, 4), piece(4, 1, 101, 4), piece(5, 1, 101, 4)], [],
                    0, 0, 2)),
        # Proceeds 6 over four 1-share rows: 6//4 = 1, 5//3 = 1, 4//2 = 2, 2 -> 1, 1, 2, 2. Rows 0 and 1 lose 1
        # each; row 0 takes lot 5 (D 1, carried 8), row 1 finds nothing; rows with gain 0 are not loss rows.
        case("H08", "proceeds are spread over rows by the running floor rule",
             [B("2024-01-02", "P", 1, 2), B("2024-01-02", "P", 1, 2), B("2024-01-02", "P", 1, 2),
              B("2024-01-02", "P", 1, 2), S("2024-01-10", "P", 4, 6), B("2024-01-15", "P", 1, 5)], [],
             result([row(4, 0, 1, 1, 2, 1, SH), row(4, 1, 1, 1, 2, 0, SH), row(4, 2, 1, 2, 2, 0, SH),
                     row(4, 3, 1, 2, 2, 0, SH)], [piece(5, 1, 6, 8)], [], -1, 0, 1)),
        case("H09", "term: sold on the first anniversary is short, the day after is long",
             [B("2022-06-15", "T", 2, 200), S("2023-06-15", "T", 1, 150), S("2023-06-16", "T", 1, 160)], [],
             result([row(1, 0, 1, 150, 100, 0, SH), row(2, 0, 1, 160, 100, 0, LG)], [], [], 50, 60, 0)),
        # Anniversary of 2024-02-29 is 2025-03-01: sales on 02-28 and 03-01 are short, 03-02 is long.
        case("H10", "February 29 acquisition: the anniversary is March 1",
             [B("2024-02-29", "F", 3, 300), S("2025-02-28", "F", 1, 120), S("2025-03-01", "F", 1, 130),
              S("2025-03-02", "F", 1, 140)], [],
             result([row(1, 0, 1, 120, 100, 0, SH), row(2, 0, 1, 130, 100, 0, SH), row(3, 0, 1, 140, 100, 0, LG)],
                    [], [], 50, 40, 0)),
        # 2023-03-01 -> 2024-03-01 is 366 days but not later than the anniversary. W is not identical to Y.
        case("H11", "more than one year is not more than 365 days",
             [B("2023-03-01", "Y", 1, 100), S("2024-03-01", "Y", 1, 90), B("2024-03-01", "W", 1, 100)], [],
             result([row(1, 0, 1, 90, 100, 0, SH)], [piece(2, 1, 100, 0)], [], -10, 0, 0)),
        # Sale 1: holding days 2023-01-01 -> 10-01 = 273, lot 2 gets basis 1050, carried 273, start 2023-01-20.
        # Sale 3 on 2024-01-25 is after 2024-01-20: LONG. Holding days 370 -> lot 4 carried 370, basis 990 + 50.
        case("H12", "a chain carries holding days until the replacement is long-term",
             [B("2023-01-01", "C", 1, 1000), S("2023-10-01", "C", 1, 900), B("2023-10-20", "C", 1, 950),
              S("2024-01-25", "C", 1, 1000), B("2024-02-20", "C", 1, 990)], [],
             result([row(1, 0, 1, 900, 1000, 100, SH), row(3, 2, 1, 1000, 1050, 50, LG)], [piece(4, 1, 1040, 370)],
                    [], 0, 0, 150)),
        # Processing order: 0, 1, 3 (05-10), 2 (05-20), 4. Sale 3 takes lot 1 (N, held, earliest) -> basis 250,
        # carried 9 (start 04-23). Sale 2 sells that piece: holding days 27, takes 2 of lot 4: 200 + 150.
        # Rows are listed by sale input index: sale 2 before sale 3.
        case("H13", "two loss sales compete; the earlier one in processing order takes the shares first",
             [B("2024-05-01", "M", 2, 200), B("2024-05-02", "N", 2, 200), S("2024-05-20", "N", 2, 100),
              S("2024-05-10", "M", 2, 150), B("2024-05-25", "M", 3, 300)], [["M", "N"]],
             result([row(2, 1, 2, 100, 250, 150, SH), row(3, 0, 2, 150, 200, 50, SH)],
                    [piece(4, 2, 350, 27), piece(4, 1, 100, 0)], [], 0, 0, 200)),
        # Trade 1 comes before the same-day BUY 2, so only 2 shares are held: rejected. Sale 3 holds 3 shares and
        # takes lot 0; lots 2 (before it) and 4 (after it, same day) both replace: D 50 -> 25 + 25, carried 9.
        case("H14", "same-day trades follow input index",
             [B("2024-07-01", "S", 2, 200), S("2024-07-10", "S", 3, 240), B("2024-07-10", "S", 1, 100),
              S("2024-07-10", "S", 2, 150), B("2024-07-10", "S", 1, 80)], [],
             result([row(3, 0, 2, 150, 200, 50, SH)], [piece(2, 1, 125, 9), piece(4, 1, 105, 9)], [1], 0, 0, 50)),
        case("H15", "validation: bools, floats, non-ASCII digits, year range, missing keys",
             [B("2024-01-02", "V", True, 100), B("2024-01-02", "V", 2, 100.0), B("２024-01-02", "V", 1, 1),
              B("1899-12-31", "V", 1, 1), B("2024-01-02", "", 1, 1),
              {"date": "2024-01-02", "side": "BUY", "symbol": "V", "qty": 1}, B("2024-1-02", "V", 1, 1),
              {"date": "2024-01-02", "side": "BUY", "symbol": "V", "qty": 2, "amount": 0, "note": "gift"},
              S("2024-01-03", "V", 1, -5), S("2024-01-03", "V", 1, 7), B("2099-12-31", "V", 1, 5),
              B("2024-01-02 ", "V", 1, 1), B("2024-01-02", 7, 1, 1), T("2024-01-03", "SELL ", "V", 1, 1)], [],
             result([row(9, 7, 1, 7, 0, 0, SH)], [piece(7, 1, 0, 0), piece(10, 1, 5, 0)],
                    [0, 1, 2, 3, 4, 5, 6, 8, 11, 12, 13], 7, 0, 0)),
        # Only 1 Q held when trade 2 arrives (P shares do not count). Sale 3's loss is replaced by the held P lot.
        case("H16", "the oversell check is per symbol, not per group",
             [B("2024-03-01", "P", 5, 500), B("2024-03-02", "Q", 1, 100), S("2024-03-03", "Q", 2, 150),
              S("2024-03-04", "Q", 1, 80)], [["P", "Q"]],
             result([row(3, 1, 1, 80, 100, 20, SH)], [piece(0, 1, 120, 2), piece(0, 4, 400, 0)], [2], 0, 0, 20)),
        # After sale 2, lot 1 = [replacement (1, 140, 13), fresh (3, 300)]. Sale 3 takes the replacement piece
        # first, then 1 fresh share (300*1//3 = 100). Proceeds 300 -> 150 + 150.
        case("H17", "within a lot, replacement pieces are sold before the fresh piece",
             [B("2024-01-02", "R", 1, 100), B("2024-01-10", "R", 4, 400), S("2024-01-15", "R", 1, 60),
              S("2024-03-01", "R", 2, 300)], [],
             result([row(2, 0, 1, 60, 100, 40, SH), row(3, 1, 1, 150, 140, 0, SH), row(3, 1, 1, 150, 100, 0, SH)],
                    [piece(1, 2, 200, 0)], [], 60, 0, 40)),
        # Lot 1 (F) is sold out, so it offers nothing. Lot 3 (held, bought before the sale) comes first, then
        # lot 5 (after). D 100 -> 50 + 50; carried = 05-10 - 04-01 = 39.
        case("H18", "earliest purchase first; a still-held earlier purchase counts, a sold-out one does not",
             [B("2024-04-01", "E", 2, 200), B("2024-04-20", "F", 2, 180), S("2024-04-22", "F", 2, 200),
              B("2024-04-25", "F", 1, 100), S("2024-05-10", "E", 2, 100), B("2024-05-12", "E", 3, 270)],
             [["E", "F"]],
             result([row(2, 1, 2, 200, 180, 0, SH), row(4, 0, 2, 100, 200, 100, SH)],
                    [piece(3, 1, 150, 39), piece(5, 1, 140, 39), piece(5, 2, 180, 0)], [], 20, 0, 100)),
        # Sale 1 (window [07-06, 09-04], lot 4 is outside): L = 1, r = 1, n = 3 -> D = 0, but lot 2's share still
        # becomes a replacement (carried 4, start 08-02). Sale 3 sells it on 09-01: holding days 30, replaced by
        # lot 4 (09-20): 200*1//2 = 100, + 50.
        case("H19", "a loss with D = 0 still uses up the replacement shares and carries days",
             [B("2024-08-01", "Z", 3, 300), S("2024-08-05", "Z", 3, 299), B("2024-08-06", "Z", 1, 100),
              S("2024-09-01", "Z", 1, 50), B("2024-09-20", "Z", 2, 200)], [],
             result([row(1, 0, 3, 299, 300, 0, SH), row(3, 2, 1, 50, 100, 50, SH)],
                    [piece(4, 1, 150, 30), piece(4, 1, 100, 0)], [], -1, 0, 50)),
        # Sale 2 leaves lot 1 with fresh (2, 220). Sale 4 (V) loses 100 on 4: lot 0 is sold out, lot 1 gives 2,
        # lot 5 gives 1: r = 3, D = 75 -> 50 + 25. Carried = 09-20 - 09-15 = 5.
        case("H20", "a partly sold earlier purchase offers only its remaining fresh shares",
             [B("2024-09-01", "U", 4, 400), B("2024-09-10", "U", 3, 330), S("2024-09-12", "U", 5, 600),
              B("2024-09-15", "V", 4, 400), S("2024-09-20", "V", 4, 300), B("2024-10-01", "U", 1, 90)],
             [["U", "V"]],
             result([row(2, 0, 4, 480, 400, 0, SH), row(2, 1, 1, 120, 110, 0, SH), row(4, 3, 4, 300, 400, 75, SH)],
                    [piece(1, 2, 270, 5), piece(5, 1, 115, 5)], [], 65, 0, 75)),
        # Sale 2 draws lot 0 (2 shares, proceeds 200) and lot 1 (1 share, basis 100, proceeds 100). Lot 1 is
        # excluded for row 1 even though the row's own lot is lot 0: only lot 3 helps, r = 1 of 2, D = 50.
        # Carried = 03-01 - 02-01 = 29 (leap February).
        case("H21", "every lot the sale draws from is excluded, not just the loss row's own lot",
             [B("2024-02-01", "W", 2, 300), B("2024-02-20", "W", 4, 400), S("2024-03-01", "W", 3, 300),
              B("2024-03-15", "W", 1, 120)], [],
             result([row(2, 0, 2, 200, 300, 50, SH), row(2, 1, 1, 100, 100, 0, SH)],
                    [piece(1, 3, 300, 0), piece(3, 1, 170, 29)], [], -50, 0, 50)),
        # Basis 100 over 3 shares: 100//3 = 33 (keeps 67), 67//2 = 33 (keeps 34), then 34.
        case("H22", "the split rule leaves the remainder with the piece",
             [B("2024-01-02", "X", 3, 100), S("2024-01-03", "X", 1, 40), S("2024-01-04", "X", 1, 40),
              S("2024-01-05", "X", 1, 40)], [],
             result([row(1, 0, 1, 40, 33, 0, SH), row(2, 0, 1, 40, 33, 0, SH), row(3, 0, 1, 40, 34, 0, SH)], [], [],
                    20, 0, 0)),
        case("H23", "no trades", [], [["A", "B"]], result([], [], [], 0, 0, 0)),
        # Sale 1 adjusts lot 2 before it is bought: 330*2//3 = 220 + 40, carried 9 (start 05-11). Sale 3 sells
        # one share of that replacement piece first: 260*1//2 = 130.
        case("H24", "a later purchase is adjusted before it is bought; its replacement piece is sold first",
             [B("2024-05-01", "J", 2, 200), S("2024-05-10", "J", 2, 160), B("2024-05-20", "J", 3, 330),
              S("2024-06-30", "J", 1, 150)], [],
             result([row(1, 0, 2, 160, 200, 40, SH), row(3, 2, 1, 150, 130, 0, SH)],
                    [piece(2, 1, 130, 9), piece(2, 1, 110, 0)], [], 20, 0, 40)),
        # Holding days 02-20 -> 03-01 = 10, so lot 2's replacement piece starts 2024-03-10 - 10 = 2024-02-29:
        # anniversary 2025-03-01, sale on 2025-03-01 is SHORT. The fresh share (start 2024-03-10) sold on
        # 2025-03-11 is LONG.
        case("H25", "a carried holding start can land on February 29",
             [B("2024-02-20", "L", 1, 100), S("2024-03-01", "L", 1, 90), B("2024-03-10", "L", 2, 200),
              S("2025-03-01", "L", 1, 150), S("2025-03-11", "L", 1, 160)], [],
             result([row(1, 0, 1, 90, 100, 10, SH), row(3, 2, 1, 150, 110, 0, SH), row(4, 2, 1, 160, 100, 0, LG)],
                    [], [], 40, 60, 10)),
        # Lot 1 (L) becomes all replacement on 06-10 (carried 7). Sale 4 then finds no fresh shares in the group.
        case("H26", "replacement shares are never candidates again",
             [B("2024-06-03", "K", 2, 200), B("2024-06-04", "L", 2, 200), S("2024-06-10", "K", 2, 150),
              B("2024-06-12", "K", 2, 160), S("2024-06-15", "K", 2, 100)], [["K", "L"]],
             result([row(2, 0, 2, 150, 200, 50, SH), row(4, 3, 2, 100, 160, 0, SH)], [piece(1, 2, 250, 7)], [],
                    -60, 0, 50)),
        # Gain exactly 0 is not a loss: lot 2 stays fresh (carried 0).
        case("H27", "a row with gain 0 is not a loss row",
             [B("2024-10-01", "N", 2, 200), S("2024-10-05", "N", 2, 200), B("2024-10-10", "N", 1, 90)], [],
             result([row(1, 0, 2, 200, 200, 0, SH)], [piece(2, 1, 90, 0)], [], 0, 0, 0)),
    ]


# ── Generated cases: small, dense windows, groups, partial lots, leap days, anniversaries ─────────────────
SYMS = ["AA", "BB", "CC", "DD"]
BASES = ["2023-12-20", "2024-02-10", "2023-02-15", "2022-12-01", "2024-12-20", "2023-06-01"]
STEPS = [0, 0, 0, 0, 1, 1, 2, 3, 5, 8, 13, 20, 29, 30, 30, 31, 40, 61]
LONG_STEPS = [300, 334, 335, 364, 365, 366, 367]
GROUPINGS = [[], [["AA", "BB"]], [["AA", "BB"], ["BB", "CC"]], [["AA"], ["BB", "CC", "DD"]],
             [["AA", "BB", "CC", "DD"]], [["CC", "AA"], ["DD", "aa"]], [["BB", "zz"], ["zz", "AA"]]]
BAD = [
    {"date": "2024-02-30", "side": "BUY", "symbol": "AA", "qty": 1, "amount": 100},
    {"date": "2024-03-01", "side": "BUY", "symbol": "AA", "qty": True, "amount": 100},
    {"date": "2024-03-01", "side": "SELL", "symbol": "AA", "qty": 1, "amount": 99.0},
    {"date": "2024-03-01", "side": "Buy", "symbol": "AA", "qty": 1, "amount": 100},
    {"date": "1899-12-31", "side": "BUY", "symbol": "AA", "qty": 1, "amount": 100},
    {"date": "2024-03-01", "side": "BUY", "symbol": "AA", "qty": -2, "amount": 100},
    {"date": "2024-03-01", "side": "BUY", "symbol": "AA", "amount": 100},
    {"date": "20240301", "side": "BUY", "symbol": "AA", "qty": 1, "amount": 100},
]


def iso(ordinal):
    return date.fromordinal(ordinal).isoformat()


def random_trades(r, n, syms, base, long_jumps):
    d = date.fromisoformat(base).toordinal()
    trades, held = [], {}
    price = {s: 60 + r.below(80) for s in syms}
    for _ in range(n):
        if long_jumps and r.chance(1, 6):
            d += r.pick(LONG_STEPS)
        else:
            d += r.pick(STEPS)
        sym = r.pick(syms)
        price[sym] = max(1, price[sym] + r.below(41) - 20)
        h = held.get(sym, 0)
        if h > 0 and r.chance(11, 20):
            qty = 1 + r.below(h + (2 if r.chance(1, 6) else 0))
            if qty <= h:
                held[sym] = h - qty
            side = "SELL"
        else:
            qty = 1 + r.below(9)
            held[sym] = h + qty
            side = "BUY"
        amount = max(0, qty * price[sym] + r.below(9) - 4)
        trades.append(T(iso(d), side, sym, qty, amount))
    return trades


def random_cases():
    res = []
    for i in range(100):
        r = SplitMix(120000 + i)
        syms = SYMS[:1 + r.below(4)]
        if r.chance(1, 8):
            syms = syms + ["aa"]
        identical = [list(g) for g in r.pick(GROUPINGS)]
        trades = random_trades(r, 5 + r.below(16), syms, r.pick(BASES), r.chance(1, 3))
        if r.chance(1, 4):
            trades.insert(r.below(len(trades) + 1), dict(r.pick(BAD)))
        if r.chance(1, 3):                          # disorder the input a little (dates decide the order)
            for _ in range(1 + r.below(4)):
                a, b = r.below(len(trades)), r.below(len(trades))
                trades[a], trades[b] = trades[b], trades[a]
        res.append({"id": f"R{i + 1:03d}", "title": "random trades", "args": [trades, identical]})
    return res


def hidden():
    return hand() + random_cases()


# ── Stress: built inside the sandbox from metadata ─────────────────────────────────────────────────────────
def stress():
    return [{"id": "S1", "title": "crowded windows: 196 000 trades in one identical group", "seed": 1201,
             "days": 1400, "per_day": 140, "symbols": 8},
            {"id": "S2", "title": "a 99 999-link wash chain whose holding start drifts before year 1", "seed": 1202,
             "n": 100000},
            {"id": "S3", "title": "200 000 shuffled trades, 600 symbols in many groups, some invalid", "seed": 1203,
             "n": 200000, "symbols": 600}]


def stress_args(case):
    r = SplitMix(case["seed"])
    if case["id"] == "S1":
        syms = [f"G{k}" for k in range(case["symbols"])]
        held = {s: 0 for s in syms}
        d0 = date(2001, 1, 1).toordinal()
        price, trades = 10000, []
        for day in range(case["days"]):
            ds = iso(d0 + day)
            price = max(1000, price + r.below(201) - 100)
            for _ in range(case["per_day"]):
                s = syms[r.below(len(syms))]
                h = held[s]
                if h > 0 and (h > 12 or r.chance(1, 2)):
                    q = 1 + r.below(min(h, 4))
                    held[s] = h - q
                    trades.append(T(ds, "SELL", s, q, q * (price + r.below(401) - 200)))
                else:
                    q = 1 + r.below(4)
                    held[s] = h + q
                    trades.append(T(ds, "BUY", s, q, q * (price + r.below(401) - 200)))
        return [trades, [syms]]
    if case["id"] == "S2":
        n = case["n"]
        trades = [B("2000-01-03", "C" if k % 2 == 0 else "D", 1, 1000) for k in range(n)]
        trades += [S("2000-02-02", "C" if k % 2 == 0 else "D", 1, 1) for k in range(n - 1)]
        return [trades, [["C", "D"]]]
    n, nsym = case["n"], case["symbols"]
    syms = [f"S{k:03d}" for k in range(nsym)]
    identical = [[syms[k], syms[k + 1]] for k in range(0, nsym - 1, 3)] + \
                [[syms[k + 1], syms[k + 2]] for k in range(0, nsym - 2, 6)]
    held = {s: 0 for s in syms}
    price = {s: 2000 + r.below(8000) for s in syms}
    d = date(2000, 1, 1).toordinal()
    trades = []
    while len(trades) < n:
        if r.chance(1, 40):
            d += 1 + r.below(3)
        s = syms[r.below(nsym)]
        price[s] = max(100, price[s] + r.below(301) - 150)
        h = held[s]
        if h > 0 and r.chance(1, 2):
            q = 1 + r.below(h)
            held[s] = h - q
            trades.append(T(iso(d), "SELL", s, q, q * price[s]))
        else:
            q = 1 + r.below(50)
            held[s] = h + q
            trades.append(T(iso(d), "BUY", s, q, q * price[s] + r.below(100)))
        if r.chance(1, 500) and len(trades) < n:
            trades.append(dict(BAD[r.below(len(BAD))]))
    for i in range(len(trades) - 1, 0, -1):         # shuffle: processing order comes from the dates alone
        j = r.below(i + 1)
        trades[i], trades[j] = trades[j], trades[i]
    return [trades, identical]
