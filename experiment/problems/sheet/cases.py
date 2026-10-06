"""Cases for Problem 8. Stdlib only (copied into the sandbox: stress inputs are generated there).

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


def E(code):
    return {"error": code}


def case(cid, title, cells, expected=None):
    c = {"id": cid, "title": title, "args": [cells]}
    if expected is not None:
        c["spec_expected"] = expected
    return c


def public():
    return [
        case("P1", "precedence and errors", {"A1": "5", "A2": "=-A1^2", "A3": "=2^3^2", "A4": "=A1/0"},
             {"A1": 5, "A2": 25, "A3": 64, "A4": E("#DIV/0!")}),
        case("P2", "comparisons and coercions",
             {"A1": "abc", "A2": '=A1="ABC"', "A3": '=1<"0"', "A4": '="3"+TRUE', "A5": "=A1+1"},
             {"A1": "abc", "A2": True, "A3": True, "A4": 4, "A5": E("#VALUE!")}),
        case("P3", "aggregates and ROUND",
             {"A1": "1", "A2": "x", "A3": "TRUE", "A4": "=SUM(A1:A3)", "A5": '=SUM(A1,"2",TRUE)',
              "A6": "=AVERAGE(B1:B3)", "A7": "=ROUND(2.675,2)"},
             {"A1": 1, "A2": "x", "A3": True, "A4": 1, "A5": 4, "A6": E("#DIV/0!"), "A7": 2.68}),
        case("P4", "static cycles", {"A1": "=IF(TRUE,1,B1)", "B1": "=A1+1", "C1": "=IFERROR(B1,7)", "D1": '=E1&"!"'},
             {"A1": E("#CYCLE!"), "B1": E("#CYCLE!"), "C1": 7, "D1": "!"}),
    ]


def hand():
    return [
        case("H01", "unary minus binds tighter than ^", {"A1": "=-2^2", "A2": "=2^-1", "A3": "=-(2^2)", "A4": "=2*-3^2"},
             {"A1": 4, "A2": 0.5, "A3": -4, "A4": 18}),
        case("H02", "left associativity",
             {"A1": "=2^3^2", "A2": "=10-4-3", "A3": "=64/4/2", "A4": "=1=1=TRUE", "A5": "=1<2<3"},
             {"A1": 64, "A2": 3, "A3": 8, "A4": True, "A5": False}),
        case("H03", "& sits between comparison and +", {"A1": "=1+2&3", "A2": "=1&2+3", "A3": '="a"&1="A1"'},
             {"A1": "33", "A2": "15", "A3": True}),
        case("H04", "string to number uses the literal rule",
             {"A1": '=" 1"+1', "A2": '="1.5"*2', "A3": '="-0.5"+0', "A4": '="1e3"+0', "A5": '="+1"+0'},
             {"A1": E("#VALUE!"), "A2": 3, "A3": -0.5, "A4": E("#VALUE!"), "A5": E("#VALUE!")}),
        case("H05", "raw literal parsing",
             {"A1": "007", "A2": "-3.25", "A3": "1.", "A4": ".5", "A5": "true", "A6": "TRUE", "A7": "", "A8": " 1",
              "A9": "-0"},
             {"A1": 7, "A2": -3.25, "A3": "1.", "A4": ".5", "A5": "true", "A6": True, "A7": None, "A8": " 1",
              "A9": 0}),
        case("H06", "empty formula values stay empty",
             {"A1": "=B1", "A2": '=A1&"x"', "A3": "=B1=0", "A4": '=B1=""', "A5": "=B1=FALSE", "A6": "=B1=C1",
              "A7": "=A1+1", "A8": "=-B1"},
             {"A1": 0, "A2": "x", "A3": True, "A4": True, "A5": True, "A6": True, "A7": 1, "A8": 0}),
        case("H07", "cross-type ordering",
             {"A1": '="a"<1', "A2": '=TRUE>"z"', "A3": '="10"<"9"', "A4": "=0.1+0.2=0.3", "A5": '="B">"a"',
              "A6": "=FALSE<TRUE", "A7": '=1="1"'},
             {"A1": False, "A2": True, "A3": True, "A4": True, "A5": True, "A6": True, "A7": False}),
        case("H08", "error order: operand errors before conversion",
             {"A1": '="a"+1/0', "A2": '=1/0+"a"', "A3": "=(1/0)&X1", "A4": '="a"+"b"', "A5": "=AA1+1/0",
              "A6": "=1/0=1/0"},
             {"A1": E("#DIV/0!"), "A2": E("#DIV/0!"), "A3": E("#DIV/0!"), "A4": E("#VALUE!"), "A5": E("#REF!"),
              "A6": E("#DIV/0!")}),
        case("H09", "power edge cases",
             {"A1": "=0^0", "A2": "=0^-1", "A3": "=(-8)^(1/3)", "A4": "=(-2)^3", "A5": "=10^400", "A6": "=2^0.5"},
             {"A1": E("#NUM!"), "A2": E("#DIV/0!"), "A3": E("#NUM!"), "A4": -8, "A5": E("#NUM!"),
              "A6": 1.414213562}),
        case("H10", "overflow is #NUM!", {"A1": "=10^300*10^10", "A2": "=SUM(A3,A3)", "A3": "=10^308*1.5"},
             {"A1": E("#NUM!"), "A2": E("#NUM!"), "A3": int(1.5e308)}),
        case("H11", "aggregate argument kinds",
             {"A1": "1", "A2": "x", "A3": "TRUE", "A4": "", "A5": '=SUM(A1:A4,"3")', "A6": "=SUM((A2))",
              "A7": '=COUNT(A1:A4,"3",TRUE,"x",1/0)', "A8": "=MAX(B1:B5)", "A9": "=MIN(A1:A3,-2)",
              "B9": "=AVERAGE(A1:A4,5)"},
             {"A1": 1, "A2": "x", "A3": True, "A4": None, "A5": 4, "A6": E("#VALUE!"), "A7": 3, "A8": 0, "A9": -2,
              "B9": 3}),
        case("H12", "AND / OR",
             {"A1": '=AND(TRUE,1,"true")', "A2": "=OR(B1:B3)", "A3": "=AND(C1:C2)", "C1": "1", "C2": "abc",
              "A4": "=OR(FALSE,1/0,TRUE)", "A5": '=AND("x")', "A6": '=NOT("FALSE")', "A7": "=OR(C1:C2,FALSE)"},
             {"A1": True, "A2": E("#VALUE!"), "A3": True, "C1": 1, "C2": "abc", "A4": E("#DIV/0!"),
              "A5": E("#VALUE!"), "A6": True, "A7": True}),
        case("H13", "IF evaluates only the chosen branch",
             {"A1": '=IF(1,"y",1/0)', "A2": "=IF(0,1/0)", "A3": '=IF("x",1,2)', "A4": "=IF(B1:B2,1,2)",
              "A5": "=IF(TRUE,B9)", "A6": '=IFERROR(1/0,"caught")', "A7": "=IFERROR(B1:B2,5)",
              "A8": '=IF("TRUE",1,2)'},
             {"A1": "y", "A2": False, "A3": E("#VALUE!"), "A4": E("#VALUE!"), "A5": 0, "A6": "caught", "A7": 5,
              "A8": 1}),
        case("H14", "names, references and function names",
             {"A1": "=foo", "A2": "=FOO(1/0)", "A3": "=AA1", "A4": "=A0", "A5": "=A01", "A6": "=A1000", "A7": "=b2",
              "B2": "5", "A8": "=sum(b2,1)", "A9": "=SUM1(2)", "B1": "=TRUE()"},
             {"A1": E("#NAME?"), "A2": E("#NAME?"), "A3": E("#REF!"), "A4": E("#REF!"), "A5": E("#REF!"),
              "A6": E("#REF!"), "A7": 5, "B2": 5, "A8": 6, "A9": E("#NAME?"), "B1": E("#NAME?")}),
        case("H15", "grammar errors",
             {"A1": "=", "A2": "=SUM(1,)", "A3": "=1 2", "A4": "=IF(1)", "A5": "=NOT(1,2)", "A6": "=(1",
              "A7": '="abc', "A8": "=1.", "A9": "=.5", "B1": "=A1 :B2", "B2": "=SUM()", "B3": "=1+\t2",
              "B4": "=FOO()", "B5": "=A1:B"},
             {"A1": E("#PARSE!"), "A2": E("#PARSE!"), "A3": E("#PARSE!"), "A4": E("#PARSE!"), "A5": E("#PARSE!"),
              "A6": E("#PARSE!"), "A7": E("#PARSE!"), "A8": E("#PARSE!"), "A9": E("#PARSE!"), "B1": E("#PARSE!"),
              "B2": E("#PARSE!"), "B3": E("#PARSE!"), "B4": E("#NAME?"), "B5": E("#PARSE!")}),
        case("H16", "static cycles in every form",
             {"A1": "=A1", "B1": "=IF(FALSE,B2,1)", "B2": "=B1", "C1": "=FOO(C2)", "C2": "=C1",
              "D1": '=IFERROR(B1,"cyc")', "D2": "=B1+1", "E1": "=SUM(E2:E3)", "E3": "=E1", "F1": "=1+", "F2": "=F1"},
             {"A1": E("#CYCLE!"), "B1": E("#CYCLE!"), "B2": E("#CYCLE!"), "C1": E("#CYCLE!"), "C2": E("#CYCLE!"),
              "D1": "cyc", "D2": E("#CYCLE!"), "E1": E("#CYCLE!"), "E3": E("#CYCLE!"), "F1": E("#PARSE!"),
              "F2": E("#PARSE!")}),
        case("H17", "range containing its own cell", {"A1": "=SUM(A1:A3)", "A2": "1"},
             {"A1": E("#CYCLE!"), "A2": 1}),
        case("H18", "text conversion of numbers",
             {"A1": "=CONCAT(B1:C2,1/4,TRUE)", "B1": "a", "C1": "=1/3", "B2": "", "C2": "=2*0.5", "A2": "=LEN(1/3)",
              "A3": '=LEN("h\u00e9llo")', "A4": '=0.1+0.2&""', "A5": '=1/3*3&""', "A6": '="say ""hi"""'},
             {"A1": "a0.33333333310.25TRUE", "B1": "a", "C1": 0.333333333, "B2": None, "C2": 1, "A2": 11, "A3": 5,
              "A4": "0.3", "A5": "1", "A6": 'say "hi"'}),
        case("H19", "ROUND halves away from zero on the repr decimal",
             {"A1": "=ROUND(2.5,0)", "A2": "=ROUND(-2.5,0)", "A3": "=ROUND(1234.5678,-2)", "A4": "=ROUND(1.005,2)",
              "A5": "=ROUND(2.675,2.9)", "A6": '=ROUND("7.45",1)', "A7": "=ROUND(-0.4,0)", "A8": "=ROUND(5,-1)"},
             {"A1": 3, "A2": -3, "A3": 1200, "A4": 1.01, "A5": 2.68, "A6": 7.5, "A7": 0, "A8": 10}),
        case("H20", "SUM adds left to right",
             {"A1": "=SUM(10000000000000000,1,-10000000000000000)", "A2": "=SUM(0.1,0.2,0.3)=0.6"},
             {"A1": 0, "A2": True}),
        case("H21", "ranges are row-major, corners in any order",
             {"A1": "=CONCAT(C2:B1)", "B1": "1", "C1": "2", "B2": "3", "C2": "4"},
             {"A1": "1234", "B1": 1, "C1": 2, "B2": 3, "C2": 4}),
        case("H22", "invalid and misused ranges",
             {"A1": "=SUM(A2:AA3)", "A2": "1", "A3": "=COUNT(B1:B0,1)", "A4": "=B1:B2", "A5": '=+"abc"',
              "A6": "=+B1:B2"},
             {"A1": E("#REF!"), "A2": 1, "A3": 1, "A4": E("#VALUE!"), "A5": "abc", "A6": E("#VALUE!")}),
        case("H23", "case-insensitive names, spaces before (",
             {"A1": "=sum (a2:a3)", "A2": "2", "A3": "3", "A4": "=true", "A5": "=tRuE+1"},
             {"A1": 5, "A2": 2, "A3": 3, "A4": True, "A5": 2}),
        case("H24", "IFERROR catches #PARSE!", {"A1": "=1+", "A2": '=IFERROR(A1,"p")', "A3": "=ISBLANK(A9)"},
             {"A1": E("#PARSE!"), "A2": "p", "A3": E("#NAME?")}),
        case("H25", "empty string comparisons", {"A1": '=""=B5', "A2": '=""<0', "A3": '=""=FALSE'},
             {"A1": True, "A2": False, "A3": False}),
        case("H26", "boolean conversion", {"A1": "=NOT(0)", "A2": '=NOT("0")', "A3": "=NOT(B1)", "A4": '=NOT("False")'},
             {"A1": True, "A2": E("#VALUE!"), "A3": True, "A4": True}),
        case("H27", "single REF is a range argument, (+REF) is not",
             {"A1": "TRUE", "A2": "5", "A3": "=MAX(A1:A2)", "A4": "=MAX(A1)", "A5": "=MAX(+A1)"},
             {"A1": True, "A2": 5, "A3": 5, "A4": 0, "A5": 1}),
        case("H28", "spaces and nesting", {"A1": "= ( 1 + 2 ) * 3 ", "A2": "=((((((((((1))))))))))"},
             {"A1": 9, "A2": 1}),
        case("H29", "number formatting",
             {"A1": '=1/0.1&""', "A2": '=2^60&""', "A3": '=0.000000001&""', "A4": '=0.0000000001&""',
              "A5": '=-0.5&""', "A6": "=1/3"},
             {"A1": "10", "A2": "1152921504606846976", "A3": "1e-09", "A4": "0", "A5": "-0.5", "A6": 0.333333333}),
        case("H30", "COUNT of direct arguments", {"A1": '=COUNT("1","-2.5","1e2","",B1,FALSE)'}, {"A1": 3}),
        case("H31", "comparison operators", {"A1": "=2<>2", "A2": "=2<=2", "A3": '="b">="B"', "A4": "=3>2"},
             {"A1": False, "A2": True, "A3": True, "A4": True}),
        case("H32", "string-to-boolean ignores ASCII case only", {"A1": '=AND("TrUe")', "A2": '=OR("yes")'},
             {"A1": True, "A2": E("#VALUE!")}),
        case("H33", "AND / OR do not short-circuit", {"A1": "=AND(FALSE,1/0)", "A2": "=OR(TRUE,NOT(\"x\"))"},
             {"A1": E("#DIV/0!"), "A2": E("#VALUE!")}),
        case("H34", "more associativity, row-major and invalid-range checks",
             {"A1": "=2^2^3", "A2": "=CONCAT(A3:B4)", "A3": "p", "B3": "q", "A4": "r", "B4": "s",
              "A5": "=SUM(B1:B0)"},
             {"A1": 64, "A2": "pqrs", "A3": "p", "B3": "q", "A4": "r", "B4": "s", "A5": E("#REF!")}),
    ]


# ── Random sheets ───────────────────────────────────────────────────────────
NUMS = ["0", "1", "2", "3", "10", "0.5", "2.25", "007", "100", "0.1"]
STRS = ['""', '"a"', '"B"', '"1"', '"-2.5"', '"TRUE"', '"x y"', '"true"']
FUNCS = ["SUM", "MIN", "MAX", "AVERAGE", "COUNT", "AND", "OR", "CONCAT", "NOT", "IF", "IFERROR", "LEN", "ROUND",
         "FOO"]
OPS = ["+", "-", "*", "/", "^", "&", "=", "<>", "<", ">", "<=", ">="]


def rand_ref(r, cols, rows):
    ref = r.pick(cols) + str(1 + r.below(rows))
    return ref.lower() if r.chance(1, 10) else ref


def rand_expr(r, depth, cols, rows):
    roll = r.below(12) if depth > 0 else r.below(5)
    if roll == 0:
        return r.pick(NUMS)
    if roll == 1:
        return r.pick(STRS)
    if roll == 2:
        return r.pick(["TRUE", "FALSE", "true", "foo", "AA1", "A0"]) if r.chance(1, 4) else rand_ref(r, cols, rows)
    if roll in (3, 4):
        return rand_ref(r, cols, rows)
    if roll in (5, 6, 7):
        return rand_expr(r, depth - 1, cols, rows) + r.pick(OPS) + rand_expr(r, depth - 1, cols, rows)
    if roll == 8:
        return r.pick(["-", "+"]) + rand_expr(r, depth - 1, cols, rows)
    if roll == 9:
        return "(" + rand_expr(r, depth - 1, cols, rows) + ")"
    name = r.pick(FUNCS)
    arity = {"NOT": 1, "LEN": 1, "IFERROR": 2, "ROUND": 2, "IF": 2 + r.below(2)}.get(name, 1 + r.below(3))
    args = []
    for _ in range(arity):
        if name in ("SUM", "MIN", "MAX", "AVERAGE", "COUNT", "AND", "OR", "CONCAT") and r.chance(1, 3):
            a, b = rand_ref(r, cols, rows), rand_ref(r, cols, rows)
            args.append(f"{a}:{b}")
        else:
            args.append(rand_expr(r, depth - 1, cols, rows))
    return name + "(" + ",".join(args) + ")"


def rand_sheet(r, cols, rows, density_num=3, density_den=4):
    cells = {}
    for c in cols:
        for row in range(1, rows + 1):
            if not r.chance(density_num, density_den):
                continue
            roll = r.below(10)
            if roll < 2:
                raw = r.pick(NUMS + ["-3", "x", "TRUE", "FALSE", "", "abc", "1."])
            else:
                raw = "=" + rand_expr(r, 3, cols, rows)
                if r.chance(1, 30):
                    raw = raw + r.pick(["+", ")", ",1", " 2"])
            cells[f"{c}{row}"] = raw
    return cells


def random_cases():
    out = []
    for i in range(90):
        r = SplitMix(31000 + i)
        cols = ["A", "B", "C", "D"][: 2 + r.below(3)]
        out.append(case(f"R{i + 1:02d}", "random sheet", rand_sheet(r, cols, 3 + r.below(4))))
    return out


def hidden():
    return hand() + random_cases()


# ── Stress (generated inside the sandbox) ───────────────────────────────────
COLS = [chr(c) for c in range(ord("A"), ord("Z") + 1)]


def stress():
    return [
        {"id": "S1", "title": "reference chain of 20000 cells", "kind": "chain", "n": 20000},
        {"id": "S2", "title": "prefix sums, a 999-cell cycle ring and readers", "kind": "sums"},
        {"id": "S3", "title": "random sheet of ~6000 cells", "kind": "random", "seed": 4242},
    ]


def stress_args(c):
    cells = {}
    if c["kind"] == "chain":
        keys = [f"{col}{row}" for col in COLS for row in range(1, 1000)][: c["n"]]
        # A1 needs A2, which needs A3, ...: evaluation in sorted, insertion or natural order starts at the deep end
        for key, nxt in zip(keys, keys[1:]):
            cells[key] = f"={nxt}+1"
        cells[keys[-1]] = "1"
    elif c["kind"] == "sums":
        for row in range(1, 1000):
            cells[f"A{row}"] = str((row * 37) % 101)
            cells[f"B{row}"] = f"=SUM(A1:A{row})"
            cells[f"C{row}"] = f"=B{row}-B{row - 1}" if row > 1 else "=B1"
            cells[f"D{row}"] = f"=D{row % 999 + 1}+1"
            cells[f"E{row}"] = f"=IFERROR(D{row},{row})+COUNT(A{row}:C{row})"
    else:
        r = SplitMix(c["seed"])
        cells = rand_sheet(r, COLS[:12], 500, 1, 1)
    return [cells]
