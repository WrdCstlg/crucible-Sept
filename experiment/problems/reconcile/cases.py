"""Cases for Problem 14 (bank reconciliation). Stdlib only (copied into the sandbox like every cases.py).

Cases with "spec_expected" were worked out by hand from SPEC.md; the build fails if the reference disagrees.
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


def E(i, d, amount, ref="", party=""):
    return {"id": i, "date": d, "amount": amount, "ref": ref, "party": party}


def Bk(i, d, amount, text=""):
    return {"id": i, "date": d, "amount": amount, "text": text}


def M(kind, ledger, bank, difference=0):
    return {"type": kind, "ledger": ledger, "bank": bank, "difference": difference}


def case(cid, title, ledger, bank, days, fee, matches=None, ul=None, ub=None, il=(), ib=()):
    c = {"id": cid, "title": title, "args": [ledger, bank, {"days": days, "fee_cents": fee}]}
    if matches is not None:
        c["spec_expected"] = {"matches": matches, "unmatched_ledger": ul, "unmatched_bank": ub,
                              "invalid": {"ledger": list(il), "bank": list(ib)}}
    return c


def public():
    return [
        case("P1", "key normalisation, ref match, amount matches across a leap day",
             [E("L1", "2024-01-30", 12500, "INV-0042", "Acme"), E("L2", "2024-02-01", 12500, "INV-0043", "Acme"),
              E("L3", "2024-02-27", -4999, "", "Telco")],
             [Bk("B1", "2024-02-01", 12500, "SEPA CR ACME LTD inv42"), Bk("B2", "2024-02-02", 12500, "ACME PAYMENT"),
              Bk("B3", "2024-03-01", -4999, "DD TELCO 0043")], 3, 0,
             [M("ref", ["L1"], ["B1"]), M("amount", ["L2"], ["B2"]), M("amount", ["L3"], ["B3"])], [], []),
        case("P2", "multi_ledger and multi_bank",
             [E("L1", "2024-03-04", 30000, "PO-7", "Beta"), E("L2", "2024-03-05", 12000, "PO-8", "Beta"),
              E("L3", "2024-03-06", 8000, "PO-9", "Beta"), E("L4", "2024-03-06", 8000, "PO-10", "Gamma"),
              E("L5", "2024-03-10", 50000, "C-551", "Delta")],
             [Bk("B1", "2024-03-06", 20000, "BETA GROUP"), Bk("B2", "2024-03-09", 20000, "DELTA C551 PART 1"),
              Bk("B3", "2024-03-12", 30000, "DELTA C-551 PART 2")], 2, 0,
             [M("multi_ledger", ["L2", "L3"], ["B1"]), M("multi_bank", ["L5"], ["B2", "B3"])], ["L1", "L4"], []),
        case("P3", "fee matches across a year end",
             [E("L1", "2024-12-30", 10000, "", "Kappa"), E("L2", "2024-12-31", 10000, "", "Kappa"),
              E("L3", "2025-01-02", 5000, "", "Kappa")],
             [Bk("B1", "2025-01-02", 9980, "KAPPA"), Bk("B2", "2025-01-03", 9990, "KAPPA"),
              Bk("B3", "2025-01-02", 4940, "KAPPA")], 5, 50,
             [M("fee", ["L2"], ["B1"], -20), M("fee", ["L1"], ["B2"], -10)], ["L3"], ["B3"]),
        case("P4", "invalid records; a ref match beats a closer amount match",
             [E("L1", "2024-03-01", 900, "INV-5", "Zed"), E("L2", "2024-02-30", 900, "INV-6", "Zed"),
              E("L3", "2024-03-02", 0, "INV-7", "Zed")],
             [Bk("B1", "2024-03-01", 900, "STRIPE PAYOUT"), Bk("B2", "2024-03-03", 900, "Zed inv5"),
              Bk("B3", "2024-03-02", 850, "INV-5"), Bk("B4", "2024-03-02", "850", "x"),
              {"id": "B5", "date": "2024-03-02", "text": "y"}], 3, 100,
             [M("ref", ["L1"], ["B2"])], [], ["B1", "B3"], [1, 2], [3, 4]),
    ]


def hand():
    d = "2024-06-10"
    return [
        # Only a4 (2000 is a leap year) and a7 (2024 is) are valid dates.
        case("H01", "strict dates: format, leap years, year 0, non-ASCII digits",
             [E("a0", "2024-3-05", 1), E("a1", "20240305", 2), E("a2", "2024-03-05 ", 3), E("a3", "1900-02-29", 4),
              E("a4", "2000-02-29", 5), E("a5", "0000-01-01", 6), E("a6", "2023-02-29", 7),
              E("a7", "2024-02-29", 8), E("a8", "٢٠٢٤-03-05", 9), E("a9", "2024-13-01", 10),
              E("a10", "2024-04-31", 11), E("a11", 20240305, 12)],
             [], 0, 0, [], ["a4", "a7"], [], [0, 1, 2, 3, 5, 6, 8, 9, 10, 11], []),
        # Valid: ledger 3 (L3, -5) and 11 (L11, 5, extra key ignored); bank 3 (B3, -5) and 4 (B4, 5).
        # Pass 2 keys (0, 05-01, L3, B3) then (1, 05-01, L11, B4).
        case("H02", "amount and field types; extra keys ignored",
             [E("x0", "2024-05-01", True), E("x1", "2024-05-01", 100.0), E("x2", "2024-05-01", 0),
              E("L3", "2024-05-01", -5), E("x4", "2024-05-01", "5"), E("x5", "2024-05-01", 5, None),
              E("x6", "2024-05-01", 5, "", 5), {"id": "x7", "date": "2024-05-01", "amount": 5, "ref": ""},
              ["L8", "2024-05-01", 5, "", ""], E("", "2024-05-01", 5), E(7, "2024-05-01", 5),
              {"id": "L11", "date": "2024-05-01", "amount": 5, "ref": "", "party": "", "memo": "x"}],
             [Bk("y0", "2024-05-01", False), Bk("y1", "2024-05-01", 5, None), {"id": "y2", "date": "2024-05-01",
                                                                               "amount": 5},
              Bk("B3", "2024-05-01", -5), Bk("B4", "2024-05-02", 5)], 1, 0,
             [M("amount", ["L3"], ["B3"]), M("amount", ["L11"], ["B4"])], [], [],
             [0, 1, 2, 4, 5, 6, 7, 8, 9, 10], [0, 1, 2]),
        # Ledger D,D both invalid; E at 3 has a bad date so it does not make E at 2 a duplicate. Bank F,F invalid.
        # Ledger X and bank X may share an id: they match in pass 2. Bank D has no ledger partner left.
        case("H03", "duplicate ids: every copy invalid, only records passing other checks count, lists separate",
             [E("D", "2024-01-10", 100), E("D", "2024-01-10", 200), E("E", "2024-01-10", 300),
              E("E", "bad", 300), E("X", "2024-01-10", 400)],
             [Bk("X", "2024-01-10", 400), Bk("D", "2024-01-10", 100), Bk("F", "2024-01-10", 300),
              Bk("F", "2024-01-10", 300)], 0, 0,
             [M("amount", ["X"], ["X"])], ["E"], ["D"], [0, 1, 3], [2, 3]),
        # Keys: K1 INV-0012 -> INV12; K2 inv_12x007 -> INV12X7; K3 1-007 -> 1007; K4 12; K5 A0B; K6 000 -> 0.
        # Line tokens: C1 PAYMENT INV12 OK; C2 REF INV12X7; C3 17; C4 INV12; C5 A0B; C6 NO 0.
        # Pass 1 (all Δ 0, same date, by entry id): K1, K2, K5, K6. K3 and K4 fall to pass 2.
        case("H04", "tokens: joiners deleted before zeros are stripped, zeros per digit run, whole tokens",
             [E("K1", d, 111, "INV-0012"), E("K2", d, 222, "inv_12x007"), E("K3", d, 333, "1-007"),
              E("K4", d, 444, "12"), E("K5", d, 555, "A0B"), E("K6", d, 666, "000")],
             [Bk("C1", d, 111, "PAYMENT INV12 OK"), Bk("C2", d, 222, "ref:INV12X7."), Bk("C3", d, 333, "17"),
              Bk("C4", d, 444, "INV12"), Bk("C5", d, 555, "a0b"), Bk("C6", d, 666, "No. 00")], 5, 0,
             [M("ref", ["K1"], ["C1"]), M("ref", ["K2"], ["C2"]), M("ref", ["K5"], ["C5"]), M("ref", ["K6"], ["C6"]),
              M("amount", ["K3"], ["C3"]), M("amount", ["K4"], ["C4"])], [], []),
        # M1 "INV 77" has two tokens -> no key. M2 key INV77; N2 "PAYÉINV77" splits at É -> PAY, INV77.
        # M3 "INV٣" -> the Arabic-Indic digit is a separator -> key INV, carried by N3.
        case("H05", "non-ASCII characters separate; a two-token ref has no key",
             [E("M1", d, 100, "INV 77"), E("M2", d, 200, "INV77"), E("M3", d, 300, "INV٣")],
             [Bk("N1", d, 100, "INV 77"), Bk("N2", d, 200, "PAYÉINV77"), Bk("N3", d, 300, "INV")], 0, 0,
             [M("ref", ["M2"], ["N2"]), M("ref", ["M3"], ["N3"]), M("amount", ["M1"], ["N1"])], [], []),
        # Pass 1 candidates: R1-S1 Δ1, R1-S2 Δ1, R2-S1 Δ1, R2-S2 Δ3. Keys (1, 03-01, R2, S1) first -> R2-S1,
        # then (1, 03-03, R1, S1) blocked, (1, 03-03, R1, S2) taken.
        case("H06", "pass 1 greedy key: entry date before entry id",
             [E("R1", "2024-03-03", 500, "X1"), E("R2", "2024-03-01", 500, "X-1")],
             [Bk("S1", "2024-03-02", 500, "X1"), Bk("S2", "2024-03-04", 500, "x1")], 3, 0,
             [M("ref", ["R2"], ["S1"]), M("ref", ["R1"], ["S2"])], [], []),
        # Candidates: A1-Z1 Δ1, A2-Z1 Δ0, A2-Z2 Δ3 (A1-Z2 is Δ4 > 3). Greedy takes A2-Z1 first; A1 and Z2 are left.
        case("H07", "pass 2 takes the global smallest key, not each entry's nearest line",
             [E("A1", "2024-01-01", 1000), E("A2", "2024-01-02", 1000)],
             [Bk("Z1", "2024-01-02", 1000), Bk("Z2", "2024-01-05", 1000)], 3, 0,
             [M("amount", ["A2"], ["Z1"])], ["A1"], ["Z2"]),
        # Δ: E1/F1 2 (year end), E2/F2 2 (Feb 29 2024), E3/F3 2 (2023 has no Feb 29), E4/F4 3 > 2,
        # E5/F5 2, E6/F6 1 (2100 is not a leap year). 2100-02-29 is invalid.
        case("H08", "day distance across month, year and leap-day boundaries; window is inclusive",
             [E("E1", "2023-12-30", 700), E("E2", "2024-02-28", 800), E("E3", "2023-02-28", 900),
              E("E4", "2024-01-30", 1100), E("E5", "2024-04-30", 1200), E("E6", "2100-02-28", 1300),
              E("E7", "2100-02-29", 1300)],
             [Bk("F1", "2024-01-01", 700), Bk("F2", "2024-03-01", 800), Bk("F3", "2023-03-02", 900),
              Bk("F4", "2024-02-02", 1100), Bk("F5", "2024-05-02", 1200), Bk("F6", "2100-03-01", 1300)], 2, 0,
             [M("amount", ["E6"], ["F6"]), M("amount", ["E3"], ["F3"]), M("amount", ["E1"], ["F1"]),
              M("amount", ["E2"], ["F2"]), M("amount", ["E5"], ["F5"])], ["E4"], ["F4"], [6], []),
        # "L10" < "L9" and "B10" < "B9" as strings.
        case("H09", "ids compare as strings: L10 before L9",
             [E("L9", "2024-05-05", 250), E("L10", "2024-05-05", 250), E("Q", "2024-05-06", 300)],
             [Bk("B9", "2024-05-06", 300), Bk("B", "2024-05-05", 250), Bk("B10", "2024-05-06", 300)], 0, 0,
             [M("amount", ["L10"], ["B"]), M("amount", ["Q"], ["B10"])], ["L9"], ["B9"]),
        # Party P pairs summing to 600: b+d (Δ 0+3) and d+e (Δ 3+3); triple a+b+c has Δ 0 but 3 entries.
        # a+f is 600 with Δ 0 but parties P and p differ; g+h is 600 with Δ 0 but the party is empty.
        case("H10", "multi_ledger: fewest entries first; party compared exactly; empty party never groups",
             [E("a", "2024-07-10", 100, "", "P"), E("b", "2024-07-10", 200, "", "P"), E("c", "2024-07-10", 300, "", "P"),
              E("d", "2024-07-07", 400, "", "P"), E("e", "2024-07-13", 200, "", "P"), E("f", "2024-07-10", 500, "", "p"),
              E("g", "2024-07-10", 300, "", ""), E("h", "2024-07-10", 300, "", "")],
             [Bk("X1", "2024-07-10", 600, "TRANSFER")], 3, 0,
             [M("multi_ledger", ["b", "d"], ["X1"])], ["a", "c", "e", "f", "g", "h"], []),
        # Pairs: e9+e10 = 1500-500 (Δ0) and e2+e3 (Δ0). Tie on Δ; ["e10","e9"] < ["e2","e3"] since "1" < "2".
        case("H11", "multi_ledger: mixed signs allowed; Δ tie broken by sorted id list (string order)",
             [E("e2", "2024-08-01", 700, "", "Q"), E("e9", "2024-08-01", 1500, "", "Q"),
              E("e3", "2024-08-01", 300, "", "Q"), E("e10", "2024-08-01", -500, "", "Q")],
             [Bk("Y", "2024-08-01", 1000, "CUSTOMER Q")], 2, 0,
             [M("multi_ledger", ["e10", "e9"], ["Y"])], ["e2", "e3"], []),
        # Lines are processed V1 (09-11) then V2 (09-12). V1 takes u1+u2 = 350; V2 = 500 needs u1, already used.
        case("H12", "multi_ledger: lines processed in (date, id) order, entries used up as it goes",
             [E("u1", "2024-09-10", 100, "", "R"), E("u2", "2024-09-10", 250, "", "R"),
              E("u3", "2024-09-10", 400, "", "R")],
             [Bk("V2", "2024-09-12", 500), Bk("V1", "2024-09-11", 350)], 5, 0,
             [M("multi_ledger", ["u1", "u2"], ["V1"])], ["u3"], ["V2"]),
        # Window 1 around 10-15: s1, s2, s3, s5 (s4 is 2 days away). No pair makes 900; s1+s2+s3 does,
        # although s1 and s2 are 2 days apart from each other. s4+s5 = 900 but s4 is outside the window.
        case("H13", "multi_ledger: a triple when no pair fits; each entry within the window of the line",
             [E("s1", "2024-10-14", 300, "", "S"), E("s2", "2024-10-16", 300, "", "S"),
              E("s3", "2024-10-15", 300, "", "S"), E("s4", "2024-10-13", 450, "", "S"),
              E("s5", "2024-10-15", 450, "", "S")],
             [Bk("T", "2024-10-15", 900)], 1, 0,
             [M("multi_ledger", ["s1", "s2", "s3"], ["T"])], ["s4", "s5"], []),
        # G1 key ORD55, carried by h1..h5 (h2 "Ord-0055" -> ORD55). Pairs to 1000: h1+h2 (Δ2), h2+h5 (Δ1);
        # triples h3+h4+h5 (Δ0) lose on size. G2 "ORD/56" gives two tokens -> no key -> skipped.
        case("H14", "multi_bank: fewest lines, then Δ; an entry whose ref has two tokens is skipped",
             [E("G1", "2024-11-20", 1000, "ord-55"), E("G2", "2024-11-20", 1000, "ORD/56")],
             [Bk("h1", "2024-11-19", 400, "ORD55 part"), Bk("h2", "2024-11-21", 600, "Ord-0055"),
              Bk("h3", "2024-11-20", 300, "ORD55"), Bk("h4", "2024-11-20", 300, "ORD55"),
              Bk("h5", "2024-11-20", 400, "ORD55"), Bk("h6", "2024-11-20", 600, "ORD56"),
              Bk("h7", "2024-11-20", 400, "ORD56")], 1, 0,
             [M("multi_bank", ["G1"], ["h2", "h5"])], ["G2"], ["h1", "h3", "h4", "h6", "h7"]),
        # Entries processed J2 (04-02) then J1 (04-03). J2: m1+m2 (Δ0) beats m3+m4 (Δ4). J1: m3+m4 = 700-200.
        # (Processing J1 first would give J1 m1+m2 by the id tie-break and J2 m3+m4.)
        case("H15", "multi_bank: entries processed in (date, id) order; lines of mixed sign",
             [E("J1", "2024-04-03", 500, "k-9"), E("J2", "2024-04-02", 500, "K9")],
             [Bk("m1", "2024-04-02", 200, "K9"), Bk("m2", "2024-04-02", 300, "K9"), Bk("m3", "2024-04-04", 700, "K9"),
              Bk("m4", "2024-04-04", -200, "K9")], 2, 0,
             [M("multi_bank", ["J2"], ["m1", "m2"]), M("multi_bank", ["J1"], ["m3", "m4"])], [], []),
        # P1 -10000 / Q1 -10025: fee 25. P2 -20000 / Q2 -19975: fee -25, no. P3 5000 / Q3 4970: fee 30 = F.
        # P3 / Q5: fee 31 > F. P4 20 / Q4 -5: fee 25 but the signs differ.
        case("H16", "fee: sign-aware (a payment's bank line is more negative), fee = F allowed, same sign",
             [E("P1", "2024-06-01", -10000), E("P2", "2024-06-01", -20000), E("P3", "2024-06-01", 5000),
              E("P4", "2024-06-01", 20)],
             [Bk("Q1", "2024-06-01", -10025), Bk("Q2", "2024-06-01", -19975), Bk("Q3", "2024-06-01", 4970),
              Bk("Q4", "2024-06-01", -5), Bk("Q5", "2024-06-01", 4969)], 1, 30,
             [M("fee", ["P1"], ["Q1"], -25), M("fee", ["P3"], ["Q3"], -30)], ["P2", "P4"], ["Q2", "Q4", "Q5"]),
        # Δ: N1 (02-27) to 03-01 is 3 in 2024, N2 (02-28) is 2. Keys (2,10,N2,O2) (2,50,N2,O1) (3,10,N1,O2)
        # (3,50,N1,O1): N2-O2, then N1-O1.
        case("H17", "fee key: the smaller fee wins a Δ tie before ids are looked at",
             [E("N1", "2024-02-27", 1000), E("N2", "2024-02-28", 1000)],
             [Bk("O1", "2024-03-01", 950), Bk("O2", "2024-03-01", 990)], 3, 100,
             [M("fee", ["N2"], ["O2"], -10), M("fee", ["N1"], ["O1"], -50)], [], []),
        # Pass 3 runs before pass 4 and 5: F1 = E1+E2 (party P) uses E1, so F2+F3 (carrying Q1) and the fee
        # line F4 (E1 - 20) find nothing.
        case("H18", "pass order: multi_ledger before multi_bank and fee",
             [E("E1", "2024-05-10", 1000, "Q1", "P"), E("E2", "2024-05-10", 500, "", "P")],
             [Bk("F1", "2024-05-10", 1500, "misc"), Bk("F2", "2024-05-10", 600, "Q1"),
              Bk("F3", "2024-05-10", 400, "Q1"), Bk("F4", "2024-05-10", 980, "x")], 0, 100,
             [M("multi_ledger", ["E1", "E2"], ["F1"])], [], ["F2", "F3", "F4"]),
        # T1 carries INV1 and INV2: keys (0, 01-05, I1, T1), (1, 01-04, I2, T1) -> I1-T1; I2 then takes T2 by
        # amount (Δ2). I3/T3 carry the same key and amount but are 9 days apart: no match at all.
        case("H19", "a line carrying two keys; pass 1 respects the window",
             [E("I1", "2024-01-05", 300, "INV-1"), E("I2", "2024-01-04", 300, "INV-2"),
              E("I3", "2024-01-01", 700, "INV-3")],
             [Bk("T1", "2024-01-05", 300, "INV1 INV2"), Bk("T2", "2024-01-06", 300, "PAY"),
              Bk("T3", "2024-01-10", 700, "inv3")], 2, 0,
             [M("ref", ["I1"], ["T1"]), M("amount", ["I2"], ["T2"])], ["I3"], ["T3"]),
        case("H20", "W = 0 means the same day; F = 0 means no fee matches",
             [E("a", "2024-03-31", 1000), E("b", "2024-03-31", 2000)],
             [Bk("c", "2024-03-31", 999), Bk("d", "2024-04-01", 2000)], 0, 0,
             [], ["a", "b"], ["c", "d"]),
        # Party Z: a1 (Δ0) + a2 (Δ2) = 900; party Y: b1 (Δ1, Jan 31) + b2 (Δ1) = 900; party C triple Δ0.
        # Pairs tie at Δ2; ["a1","a2"] < ["b1","b2"] (party names play no part).
        case("H21", "multi_ledger: best group across parties; Δ tie broken by ids, not by party",
             [E("b1", "2024-01-31", 450, "", "Y"), E("b2", "2024-02-02", 450, "", "Y"),
              E("a1", "2024-02-01", 400, "", "Z"), E("a2", "2024-02-03", 500, "", "Z"),
              E("c1", "2024-02-01", 300, "", "C"), E("c2", "2024-02-01", 300, "", "C"),
              E("c3", "2024-02-01", 300, "", "C")],
             [Bk("M", "2024-02-01", 900)], 2, 0,
             [M("multi_ledger", ["a1", "a2"], ["M"])], ["b1", "b2", "c1", "c2", "c3"], []),
        # Key R2. n9+n10 (Δ 1+1) and n2+n3 (Δ 1+1) both make 1000; ["n10","n9"] < ["n2","n3"].
        case("H22", "multi_bank: Δ tie broken by sorted line ids in string order; across a year end",
             [E("K", "2024-12-31", 1000, "R-2")],
             [Bk("n9", "2025-01-01", 600, "r2"), Bk("n2", "2024-12-30", 300, "R2"), Bk("n10", "2024-12-30", 400, "R2"),
              Bk("n3", "2025-01-01", 700, "R-2")], 1, 0,
             [M("multi_bank", ["K"], ["n10", "n9"])], [], ["n2", "n3"]),
        # U1 A-000-1 -> A0001 -> A1 (V1 A1). U2 B.10.05 -> B1005, not V2's B105. U3 "  0042  " -> 42 (V3 NO, 42).
        # U4 x_ -> X (V4 X- -> X). U5 "--" gives no token -> no key. Pass 1: U1, U3, U4; pass 2: U2, U5.
        case("H23", "tokens: zero runs after joiner removal, padding, trailing joiners, empty runs",
             [E("U1", d, 100, "A-000-1"), E("U2", d, 200, "B.10.05"), E("U3", d, 300, "  0042  "),
              E("U4", d, 400, "x_"), E("U5", d, 500, "--")],
             [Bk("V1", d, 100, "A1"), Bk("V2", d, 200, "B105"), Bk("V3", d, 300, "No:42"), Bk("V4", d, 400, "X-"),
              Bk("V5", d, 500, "--")], 0, 0,
             [M("ref", ["U1"], ["V1"]), M("ref", ["U3"], ["V3"]), M("ref", ["U4"], ["V4"]),
              M("amount", ["U2"], ["V2"]), M("amount", ["U5"], ["V5"])], [], []),
        # Keys (1, 03-03, B, G1) < (1, 03-05, A, G1); then C: (1, 03-10, C, H1) < (1, 03-10, C, H2) although H2's
        # date is earlier (the key has no line date).
        case("H24", "pass 2 key: entry date before entry id; line id, not line date, breaks the last tie",
             [E("A", "2024-03-05", 100), E("B", "2024-03-03", 100), E("C", "2024-03-10", 200)],
             [Bk("G1", "2024-03-04", 100), Bk("H2", "2024-03-09", 200), Bk("H1", "2024-03-11", 200)], 1, 0,
             [M("amount", ["B"], ["G1"]), M("amount", ["C"], ["H1"])], ["A"], ["H2"]),
        # Pass 2: W1 (5000) = Y1 (Δ1). Pass 3, lines in (date, id) order: Y2 (03-02) then Y3 (03-03).
        # Y2 = 700: w2+w3 (party T, Δ 0+1). Y3 = 700: w4+w5 (Δ 0+0). Pass 5: w6 (-300) with Y4 (-310): fee 10.
        case("H25", "all five passes in one statement",
             [E("w1", "2024-03-01", 5000, "S-1", "T"), E("w2", "2024-03-02", 400, "", "T"),
              E("w3", "2024-03-03", 300, "", "T"), E("w4", "2024-03-03", 350, "", "T"),
              E("w5", "2024-03-03", 350, "", "T"), E("w6", "2024-03-04", -300, "S-6", "T"),
              E("w7", "2024-03-04", 900, "S-7", "")],
             [Bk("Y1", "2024-03-02", 5000, "s1"), Bk("Y3", "2024-03-03", 700, "T"), Bk("Y2", "2024-03-02", 700, "T"),
              Bk("Y4", "2024-03-05", -310, "FEE"), Bk("Y5", "2024-03-04", 450, "S7"), Bk("Y6", "2024-03-05", 450, "S7")],
             1, 20,
             [M("ref", ["w1"], ["Y1"]), M("multi_ledger", ["w2", "w3"], ["Y2"]),
              M("multi_ledger", ["w4", "w5"], ["Y3"]), M("multi_bank", ["w7"], ["Y5", "Y6"]),
              M("fee", ["w6"], ["Y4"], -10)], [], []),
    ]


# ── Generated cases ─────────────────────────────────────────────────────────
def iso(ordinal):
    return date.fromordinal(ordinal).isoformat()


BASES = [date(2023, 12, 27).toordinal(), date(2024, 2, 25).toordinal(), date(2023, 2, 25).toordinal(),
         date(2024, 12, 28).toordinal(), date(2100, 2, 25).toordinal(), date(2024, 4, 28).toordinal()]
PARTIES = ["Acme", "Acme", "Acme", "ACME", "Beta", "Beta", "", "Acme "]
POOL = [100, 200, 300, 400, 500, 250, 150, 1000, -100, -200, -300]
PREFIXES = ["INV", "INV", "PO", "C", ""]
WORDS = ["SEPA", "CR", "TRF", "PAYMENT", "THANKS", "DD", "CARD", "REF", "ACME", "BETA", "TO", "FROM"]
BAD_DATES = ["2024-02-30", "2023-02-29", "2024-1-05", "20240105", " 2024-01-05", "2024-01-05T", "1900-02-29",
             "2024-00-10", "0000-01-01", "٢024-01-05", "2024/01/05", None]
BAD_AMOUNTS = [0, True, False, 100.0, "100", None]


def ref_variant(r, p, n):
    v = r.below(10)
    if v == 0:
        return f"{p}-{n:04d}"
    if v == 1:
        return f"{p}{n}"
    if v == 2:
        return f"{p.lower()}_{n:03d}"
    if v == 3:
        return f"{p} {n}"               # two tokens unless p is empty
    if v == 4:
        return f"{p}.{n}."
    if v == 5:
        return f"#{p}{n}"
    if v == 6:
        return f"{p}-0-{n}"             # joiners go first: INV-0-7 -> INV07 -> INV7
    if v == 7:
        return f"{p}{n}é"          # the accented letter is a separator
    if v == 8:
        return f"{p}/{n}"               # two tokens unless p is empty
    return f" {p}-{n:02d} "


def text_variant(r, p, n):
    v = r.below(12)
    w = r.pick(WORDS)
    if v == 0:
        return f"{w} {p}{n}"
    if v == 1:
        return f"{p}-{n:05d} {w}"
    if v == 2:
        return f"{w}:{p.lower()}{n}"
    if v == 3:
        return f"{p}{n}0"               # a different token
    if v == 4:
        return f"{p} {n}"
    if v == 5:
        return f"{w}É{p}{n}"       # the accented letter splits the run
    if v == 6:
        return f"X{p}{n}"               # a different token
    if v == 7:
        return f"{n}"
    if v == 8:
        return f"{p}_{n:02d}{w}"        # glued to a word: a different token
    if v == 9:
        return f"{w} {p}{n} {p}{n + 1}"
    if v == 10:
        return f"{p}.0{n}/{w}"
    return f"{p}{n}٣"              # a non-ASCII digit is a separator


def make_records(r, rows, prefix, ledger):
    """rows: [day, amount, ref_or_text(, party)] -> shuffled records with ids, a few corrupted or duplicated."""
    for i in range(len(rows) - 1, 0, -1):
        j = r.below(i + 1)
        rows[i], rows[j] = rows[j], rows[i]
    recs = []
    for k, row in enumerate(rows):
        rec = {"id": f"{prefix}{k + 1}", "date": iso(row[0]), "amount": row[1]}
        if ledger:
            rec["ref"], rec["party"] = row[2], row[3]
        else:
            rec["text"] = row[2]
        recs.append(rec)
    if recs and r.chance(1, 3):
        for _ in range(1 + r.below(2)):
            k = r.below(len(recs))
            rec = recs[k]
            what = r.below(6)
            if what == 0:
                rec["date"] = r.pick(BAD_DATES)
            elif what == 1:
                rec["amount"] = r.pick(BAD_AMOUNTS)
            elif what == 2:
                recs[k] = {key: v for key, v in rec.items() if key != "amount"}
            elif what == 3:
                rec["ref" if ledger else "text"] = r.pick([None, 7, ["x"]])
            elif what == 4:
                rec["id"] = r.pick(["", 12, None])
            else:
                rec["date"] = r.pick(["2024-02-29", "2000-02-29", "2023-03-01"])   # valid, unusual
    if len(recs) >= 2 and r.chance(1, 4):
        a, b = r.below(len(recs)), r.below(len(recs))
        if a != b:
            recs[b]["id"] = recs[a]["id"]
    if recs and r.chance(1, 10):
        recs.insert(r.below(len(recs) + 1), r.pick([None, "L0", ["L0", "2024-01-01", 5], {"id": "Z"}]))
    return recs


def random_case(r, cid, events):
    W = r.pick([0, 1, 1, 2, 2, 3])
    F = r.pick([0, 5, 25, 25, 100])
    base = r.pick(BASES)
    led, bk = [], []

    def day():
        return base + r.below(8)

    def near(o):
        return o + r.below(2 * W + 3) - (W + 1)

    def amt():
        if r.chance(2, 3):
            return r.pick(POOL)
        return (1 + r.below(2000)) * (-1 if r.chance(1, 4) else 1)

    for _ in range(events):
        kind = r.below(8)
        o = day()
        if kind == 0:                                   # reference
            p, n = r.pick(PREFIXES), 1 + r.below(12)
            a = amt()
            led.append([o, a, ref_variant(r, p, n), r.pick(PARTIES)])
            bk.append([near(o), a if r.chance(4, 5) else a - 1 - r.below(F + 1), text_variant(r, p, n)])
        elif kind == 1:                                 # exact amount, sometimes contended
            a = amt()
            led.append([o, a, r.pick(["", "", "INV-1"]), r.pick(PARTIES)])
            for _ in range(1 + r.below(2)):
                bk.append([near(o), a, r.pick(WORDS)])
        elif kind == 2:                                 # one line, several entries
            party = r.pick(PARTIES)
            total = 0
            for _ in range(2 + r.below(3)):
                a = amt()
                total += a
                led.append([near(o), a, r.pick(["", "", "PO-3"]), party if r.chance(5, 6) else r.pick(PARTIES)])
            if total == 0:
                total = 7
            bk.append([o, total if r.chance(4, 5) else total - 1 - r.below(F + 1), r.pick(WORDS)])
        elif kind == 3:                                 # several lines, one entry
            p, n = r.pick(PREFIXES), 1 + r.below(12)
            total = 0
            for _ in range(2 + r.below(3)):
                a = amt()
                total += a
                bk.append([near(o), a, text_variant(r, p, n) if r.chance(3, 4) else f"{p}{n}"])
            if total == 0:
                total = 9
            led.append([o, total if r.chance(5, 6) else total + 1, ref_variant(r, p, n), r.pick(PARTIES)])
        elif kind == 4:                                 # fee, sometimes in the wrong direction or too big
            a = amt()
            fee = r.pick([1, F, F + 1, 1 + r.below(F + 1)]) if F else r.pick([1, 2])
            b = a + fee if r.chance(1, 4) else a - fee
            led.append([o, a, "", r.pick(PARTIES)])
            bk.append([near(o), b if b != 0 else 3, r.pick(WORDS)])
        elif kind == 5:
            led.append([day(), amt(), r.pick(["", "INV-1", "PO 3", "C-0007"]), r.pick(PARTIES)])
        else:
            bk.append([day(), amt(), r.pick(WORDS + ["INV1", "C7", "po3"])])
    return {"id": cid, "title": f"generated statement ({events} events)",
            "args": [make_records(r, led, "L", True), make_records(r, bk, "B", False), {"days": W, "fee_cents": F}]}


def group_case(r, cid):
    """Pairs and triples competing for the same line (or the same entry): size, Δ, id and party tie-breaks."""
    W = r.pick([1, 1, 2, 3])
    F = r.pick([0, 0, 25])
    base = r.pick(BASES)
    parties = ["Acme", "Beta", "acme", ""]
    led, bk = [], []

    def near(o):
        return o + r.below(2 * W + 1) - W

    def far(o):
        return o + (W + 1) * (1 if r.chance(1, 2) else -1)

    def split(total):
        a = r.pick([100, 200, 300, 400, 500, 700, 1100, -100])
        x, y = r.pick([100, 200, 300, -200]), r.pick([100, 200, 300, 400])
        z = total - x - y
        return [a, total - a or 50], [x, y, z or 50]

    for _ in range(2 + r.below(3)):
        o = base + r.below(6)
        total = r.pick([600, 900, 1000, 1200, -300])
        pair, triple = split(total)
        if r.chance(1, 2):                              # one line, groups of entries
            party = r.pick(parties[:3])
            for k, a in enumerate(pair + triple):
                when = far(o) if k == 1 and r.chance(1, 6) else near(o)
                led.append([when, a, "", party if r.chance(5, 6) else r.pick(parties)])
            bk.append([o, total, r.pick(WORDS)])
            if r.chance(1, 3):
                bk.append([near(o), total, r.pick(WORDS)])
        else:                                           # one entry, groups of lines carrying its key
            p, n = r.pick(PREFIXES), 1 + r.below(6)
            for k, a in enumerate(pair + triple):
                when = far(o) if k == 1 and r.chance(1, 6) else near(o)
                bk.append([when, a, text_variant(r, p, n) if r.chance(1, 4) else f"{p}{n}"])
            led.append([o, total, ref_variant(r, p, n) if r.chance(1, 3) else f"{p}-{n}", r.pick(parties)])
            if r.chance(1, 3):
                led.append([near(o), total, f"{p}{n}", r.pick(parties)])
    return {"id": cid, "title": "competing groups", "args": [make_records(r, led, "L", True),
                                                             make_records(r, bk, "B", False),
                                                             {"days": W, "fee_cents": F}]}


def random_cases():
    res = []
    for i in range(120):
        r = SplitMix(140000 + i)
        events = 3 + r.below(6) if i < 90 else 14 + r.below(12)
        res.append(random_case(r, f"R{i + 1:03d}", events))
    for i in range(30):
        res.append(group_case(SplitMix(150000 + i), f"R{i + 121:03d}"))
    return res


def hidden():
    return hand() + random_cases()


# ── Stress ──────────────────────────────────────────────────────────────────
FATES = {   # percent: ref, amount, multi_ledger, multi_bank, fee, entry only, line only
    "mixed": (30, 25, 10, 7, 10, 9, 9),
    "leftover": (3, 7, 35, 22, 23, 5, 5),
    "crowded": (25, 40, 8, 5, 10, 6, 6),
}
CROWD = [k * 500 for k in range(1, 31)] + [-k * 700 for k in range(1, 11)]
STRESS_WORDS = ["SEPA", "CR", "TRF", "PAYMENT", "THANKS", "DD", "CARD", "POS", "GIRO", "WIRE"]


def stress():
    return [{"id": "S1", "title": "20 000 a side, every pass", "seed": 1401, "n": 20000, "days": 4, "fee": 300,
             "mode": "mixed"},
            {"id": "S2", "title": "20 000 entries, most records left for passes 3-5", "seed": 1402, "n": 20000,
             "days": 6, "fee": 2500, "mode": "leftover"},
            {"id": "S3", "title": "crowded amounts and shared keys", "seed": 1403, "n": 20000, "days": 10,
             "fee": 100, "mode": "crowded"}]


def stress_args(case):
    r = SplitMix(case["seed"])
    n, W, F, mode = case["n"], case["days"], case["fee"], case["mode"]
    base, span = date(2023, 10, 1).toordinal(), 900
    cuts = []
    acc = 0
    for share in FATES[mode]:
        acc += share
        cuts.append(acc)
    led, bk = [], []
    seq = 0

    def amount():
        if mode == "crowded" and r.chance(4, 5):
            return CROWD[r.below(len(CROWD))]
        a = 100 + r.below(500000)
        return -a if r.chance(1, 5) else a

    def jitter():
        if r.chance(19, 20):
            return r.below(2 * W + 1) - W
        return (W + 1 + r.below(5)) * (1 if r.chance(1, 2) else -1)

    def words(k):
        return " ".join(STRESS_WORDS[r.below(len(STRESS_WORDS))] for _ in range(k))

    while len(led) < n:
        f = r.below(100)
        o = base + r.below(span)
        pk = r.below(600)
        party = f"Party {pk}"
        seq += 1
        if f < cuts[0]:
            a = amount()
            if mode == "crowded":
                ref, text = f"CT-{pk:04d}", f"{words(2)} ct{pk}"
            else:
                v = r.below(3)
                ref = f"INV-{seq:06d}" if v == 0 else f"inv{seq}" if v == 1 else f"INV_{seq:07d}"
                v = r.below(3)
                text = (f"{words(2)} INV{seq}" if v == 0 else f"REF:inv-{seq:06d} {words(1)}" if v == 1
                        else f"{words(1)}/INV{seq}")
            led.append([o, a, ref, party])
            bk.append([o + jitter(), a, text])
        elif f < cuts[1]:
            a = amount()
            led.append([o, a, "", party])
            bk.append([o + jitter(), a, words(3)])
        elif f < cuts[2]:
            total = 0
            for _ in range(3 if r.chance(3, 10) else 2):
                a = amount()
                total += a
                led.append([o + r.below(2 * W + 1) - W, a, "", party])
            if total == 0:
                led[-1][1] += 1
                total = 1
            bk.append([o, total, f"{words(1)} PARTY {pk}"])
        elif f < cuts[3]:
            total = 0
            for _ in range(3 if r.chance(3, 10) else 2):
                a = amount()
                total += a
                bk.append([o + r.below(2 * W + 1) - W, a, f"{words(1)} SPL-{seq:06d}"])
            if total == 0:
                bk[-1][1] += 1
                total = 1
            led.append([o, total, f"spl{seq}", party])
        elif f < cuts[4]:
            a = amount()
            if 0 < a <= F:
                a += F
            led.append([o, a, "", party])
            bk.append([o + jitter(), a - 1 - r.below(F), words(2)])
        elif f < cuts[5]:
            led.append([o, amount(), f"INV-{seq:06d}" if r.chance(1, 2) else "", party])
        else:
            bk.append([o, amount(), words(3)])
    ledger, bank = [], []
    for rows, out, prefix in ((led, ledger, "L"), (bk, bank, "B")):
        for k, row in enumerate(rows):
            rec = {"id": f"{prefix}{k}", "date": iso(row[0]), "amount": row[1]}
            if prefix == "L":
                rec["ref"], rec["party"] = row[2], row[3]
            else:
                rec["text"] = row[2]
            out.append(rec)
        for i in range(len(out) - 1, 0, -1):
            j = r.below(i + 1)
            out[i], out[j] = out[j], out[i]
        for _ in range(len(out) // 400):
            rec = out[r.below(len(out))]
            what = r.below(4)
            if what == 0:
                rec["date"] = r.pick(BAD_DATES)
            elif what == 1:
                rec["amount"] = r.pick(BAD_AMOUNTS)
            elif what == 2:
                rec["id"] = out[r.below(len(out))]["id"]
            else:
                rec["date"] = "2024-02-29"
    return [ledger, bank, {"days": W, "fee_cents": F}]
