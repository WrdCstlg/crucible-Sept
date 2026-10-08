"""Cases for Problem 18 (three-way text merge). Stdlib only (copied into the sandbox like every cases.py).

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


O, B, S, T = "<<<<<<< ours\n", "||||||| base\n", "=======\n", ">>>>>>> theirs\n"


def block(ours, base, theirs):
    """A conflict block written out from its three parts (each part given already newline-terminated)."""
    return O + ours + B + base + S + theirs + T


def case(cid, title, base, ours, theirs, text=None, conflicts=None):
    c = {"id": cid, "title": title, "args": [base, ours, theirs]}
    if text is not None:
        c["spec_expected"] = {"text": text, "conflicts": conflicts, "clean": conflicts == 0}
    return c


def public():
    return [
        case("P1", "edits separated by a stable line; one-sided insertion",
             "def f():\n    return 1\n\ndef g():\n    return 2\n",
             "def f():\n    return 10\n\ndef g():\n    return 2\n",
             "def f():\n    return 1\n\ndef g():\n    log()\n    return 2\n",
             "def f():\n    return 10\n\ndef g():\n    log()\n    return 2\n", 0),
        case("P2", "conflict block; same change on both sides once",
             "a\nb\nc\nd\ne\n", "a\nB\nc\nD\ne\n", "a\nX\nc\nD\ne\n",
             "a\n<<<<<<< ours\nB\n||||||| base\nb\n=======\nX\n>>>>>>> theirs\nc\nD\ne\n", 1),
        case("P3", "adding the final newline changes the last line",
             "x = 1\ny = 2", "x = 1\ny = 3", "x = 1\ny = 2\n",
             "x = 1\n<<<<<<< ours\ny = 3\n||||||| base\ny = 2\n=======\ny = 2\n>>>>>>> theirs\n", 1),
        case("P4", "the diff decides what is stable (tie goes down)",
             "a\nb\n", "b\na\n", "a\nb\nc\n",
             "b\n<<<<<<< ours\na\n||||||| base\n=======\nc\n>>>>>>> theirs\n", 1),
    ]


def hand():
    return [
        case("H01", "adjacent edits to different lines conflict",
             "1\n2\n3\n4\n", "1\nX\n3\n4\n", "1\n2\nY\n4\n",
             "1\n" + block("X\n3\n", "2\n3\n", "2\nY\n") + "4\n", 1),
        case("H02", "edits with one stable line between them merge",
             "1\n2\n3\n4\n5\n", "1\nX\n3\n4\n5\n", "1\n2\n3\nY\n5\n",
             "1\nX\n3\nY\n5\n", 0),
        case("H03", "identical change on both sides is written once",
             "a\nb\nc\n", "a\nB\nc\n", "a\nB\nc\n",
             "a\nB\nc\n", 0),
        case("H04", "different insertions at the same place conflict; empty base part keeps its marker",
             "a\nb\n", "a\nx\nb\n", "a\ny\nb\n",
             "a\n" + block("x\n", "", "y\n") + "b\n", 1),
        case("H05", "identical insertion at the same place is written once",
             "a\n", "a\nz\n", "a\nz\n",
             "a\nz\n", 0),
        # base->ours keeps only line 0 ("b\n" != "b\r\n"); base->theirs keeps only line 1: no stable line at all.
        case("H06", "CRLF and LF lines are different lines",
             "a\r\nb\r\n", "a\r\nb\n", "a\nb\r\n",
             block("a\r\nb\n", "a\r\nb\r\n", "a\nb\r\n"), 1),
        # Two lines each ("p\rq\n", "r\n"): ours edits line 1, theirs edits line 0 -> adjacent -> conflict.
        case("H07", "a lone CR does not end a line",
             "p\rq\nr\n", "p\rq\nR\n", "P\rq\nr\n",
             block("p\rq\nR\n", "p\rq\nr\n", "P\rq\nr\n"), 1),
        # One line each; ours and theirs both change it, differently.
        case("H08", "U+2028 and U+0085 do not end a line",
             "a\u2028m\x85c\n", "A\u2028m\x85c\n", "a\u2028m\x85C\n",
             block("A\u2028m\x85c\n", "a\u2028m\x85c\n", "a\u2028m\x85C\n"), 1),
        # Stable "m\n"; chunk 1 only theirs changed, chunk 2 ("y" -> "y\n") only ours changed.
        case("H09", "one side adds the final newline, the other edits elsewhere",
             "x\nm\ny", "x\nm\ny\n", "X\nm\ny",
             "X\nm\ny\n", 0),
        case("H10", "one side removes the final newline; result ends without one",
             "a\nb\nc\n", "a\nb\nc", "A\nb\nc\n",
             "A\nb\nc", 0),
        case("H11", "conflict on newline-less last lines: every part terminated",
             "k\nv1", "k\nv2", "k\nv3",
             "k\n" + block("v2\n", "v1\n", "v3\n"), 1),
        case("H12", "empty base, both sides create different text",
             "", "x", "y\n",
             block("x\n", "", "y\n"), 1),
        case("H13", "three empty texts", "", "", "", "", 0),
        case("H14", "both sides delete everything", "a\nb\n", "", "", "", 0),
        case("H15", "delete versus modify conflicts with an empty ours part",
             "a\nb\nc\n", "a\nc\n", "a\nB\nc\n",
             "a\n" + block("", "b\n", "B\n") + "c\n", 1),
        # base->theirs: insertion of "=======\n" at the top (down at step 1, then two diagonal moves).
        case("H16", "marker-like input lines are ordinary text in a clean merge",
             "<<<<<<< ours\nx\n", "<<<<<<< ours\nx\ny\n", "=======\n<<<<<<< ours\nx\n",
             "=======\n<<<<<<< ours\nx\ny\n", 0),
        # base->ours for [a,b,c] vs [c,b,a]: step 2 k=2 snakes (2,0)->(3,1); the path ends at step 4 via k=1 and k=2,
        # so only c is matched (base 2 <-> ours 0). Stable: c. Chunk 1: theirs kept a,b -> take ours (nothing).
        case("H17", "reversed lines: the diff keeps the last base line",
             "a\nb\nc\n", "c\nb\na\n", "a\nb\nc\nd\n",
             "c\n" + block("b\na\n", "", "d\n"), 1),
        # base->ours [x,x,q] vs [x,q]: step 0 matches the first x; step 1 k=1 goes right (deletes base line 1) and
        # matches q. Base line 1 is not stable, base line 2 is not stable (theirs changed q) -> one chunk.
        case("H18", "the greedy diff keeps the first of two equal lines",
             "x\nx\nq\n", "x\nq\n", "x\nx\nQ\n",
             "x\n" + block("q\n", "x\nq\n", "x\nQ\n"), 1),
        case("H19", "two conflict blocks are counted separately",
             "1\n2\n3\n", "A\n2\nC\n", "a\n2\nc\n",
             block("A\n", "1\n", "a\n") + "2\n" + block("C\n", "3\n", "c\n"), 2),
        case("H20", "an insertion just before a line the other side edits conflicts",
             "a\nb\nc\n", "a\nN\nb\nc\n", "a\nB\nc\n",
             "a\n" + block("N\nb\n", "b\n", "B\n") + "c\n", 1),
        case("H21", "unchanged ours: theirs taken whole, deletions included",
             "a\nb\nc\nd\n", "a\nb\nc\nd\n", "b\nd\ne\n",
             "b\nd\ne\n", 0),
        case("H22", "lines common to both sides stay inside the block",
             "a\nb\nc\n", "a\nX\nY\nc\n", "a\nX\nZ\nc\n",
             "a\n" + block("X\nY\n", "b\n", "X\nZ\n") + "c\n", 1),
        case("H23", "a marker-like line inside a conflict does not add a conflict",
             "m\n", "<<<<<<< ours\n", "t\n",
             block("<<<<<<< ours\n", "m\n", "t\n"), 1),
        # base ["\n"]; ours has no lines; theirs ["\n","\n"] keeps base line 0 as its first line. Not stable.
        case("H24", "an empty text has no lines; a lone newline is one line",
             "\n", "", "\n\n",
             block("", "\n", "\n\n"), 1),
        case("H25", "only theirs adds a newline-less line to an empty base",
             "", "", "t", "t", 0),
        # base->ours [a,b,c] vs [b,a,c]: tie at step 2, k=0 (x_down = x_right = 2) goes down, so b and c are matched
        # and a is deleted. Theirs changed b, so only c is stable.
        case("H26", "swap: the tie keeps the second line, not the first",
             "a\nb\nc\n", "b\na\nc\n", "a\nB\nc\n",
             block("b\na\n", "a\nb\n", "a\nB\n") + "c\n", 1),
        # "b" (base, theirs) != "b\n" (ours): base->ours matches only a, base->theirs only b. No stable line.
        case("H27", "appending after a newline-less last line changes it",
             "a\nb", "a\nb\nc\n", "A\nb",
             block("a\nb\nc\n", "a\nb\n", "A\nb\n"), 1),
        case("H28", "one side appends a newline-less line; the result keeps it that way",
             "a\nb\nc\n", "a\nB\nc\n", "a\nb\nc\nd",
             "a\nB\nc\nd", 0),
    ]


# ── Generated cases ─────────────────────────────────────────────────────────
def edit(r, lines, n_ops, pool):
    """Apply n_ops random small edits (replace, insert, delete, move) to a copy of lines."""
    out = list(lines)
    for _ in range(n_ops):
        op = r.below(4)
        p = r.below(len(out) + 1)
        if op == 0 and p < len(out):
            out[p] = r.pick(pool)
        elif op == 1 or not out:
            out[p:p] = [r.pick(pool) for _ in range(1 + r.below(2))]
        elif op == 2 and p < len(out):
            del out[p:p + 1 + r.below(2)]
        elif p < len(out):
            ln = out.pop(p)
            q = r.below(len(out) + 1)
            out.insert(q, ln)
    return out


def text_of(lines, drop_final_newline=False):
    s = "".join(lines)
    if drop_final_newline and s.endswith("\n"):
        s = s[:-1]
    return s


def gen_ties(r):
    """Tiny alphabets: many equally short diffs, so only the exact procedure gives the expected matches."""
    alpha = ["a\n", "b\n", "c\n", "d\n"][:2 + r.below(3)]
    base = [r.pick(alpha) for _ in range(2 + r.below(8))]
    ours = edit(r, base, 1 + r.below(3), alpha)
    theirs = edit(r, base, 1 + r.below(3), alpha)
    return [text_of(base), text_of(ours), text_of(theirs)]


def gen_structure(r):
    """Distinct lines; the two sides edit at the same spot, adjacent spots, one line apart, or identically."""
    n = 6 + r.below(12)
    base = [f"L{i}\n" for i in range(n)]
    ours, theirs = list(base), list(base)
    for _ in range(1 + r.below(3)):
        p = r.below(n - 2)
        rel = r.pick([0, 0, 1, 1, 2, 3])
        kind_o, kind_t = r.below(3), r.below(3)
        same = r.chance(1, 4)

        def apply(lst, pos, kind, tag):
            if pos >= len(lst) or lst[pos] is None:
                return
            if kind == 0:
                lst[pos] = f"{lst[pos][:-1]}{tag}\n"
            elif kind == 1:
                lst.insert(pos, f"new{tag}{pos}\n")
            else:
                lst[pos] = None                       # marked for deletion
        apply(ours, p, kind_o, "o" if not same else "s")
        if same:
            apply(theirs, p, kind_o, "s")
        else:
            apply(theirs, p + rel, kind_t, "t")
    return [text_of(base), text_of([x for x in ours if x is not None]),
            text_of([x for x in theirs if x is not None])]


EOL_POOL = ["a\n", "a\r\n", "b\n", "b\r\n", "c\rd\n", "e\x0cf\n", "g\x85h\n", "i\u2028j\n", "\n", "\r\n", "k\n"]


def gen_moves(r):
    """One side moves lines around in a tiny alphabet (many equally short diffs), the other edits."""
    alpha = ["a\n", "b\n", "c\n"][:2 + r.below(2)]
    base = [r.pick(alpha) for _ in range(4 + r.below(7))]
    ours = list(base)
    for _ in range(1 + r.below(2)):
        p, q = r.below(len(ours)), r.below(len(ours))
        ln = ours.pop(p)
        ours.insert(q, ln)
    theirs = edit(r, base, 1 + r.below(3), alpha + ["Z\n"])
    if r.chance(1, 2):
        ours, theirs = theirs, ours
    return [text_of(base), text_of(ours), text_of(theirs)]


def gen_swaps(r):
    """One side moves a line down by one or two places; the other edits, inserts or deletes right there."""
    alpha = ["a\n", "b\n", "c\n", "d\n"][:2 + r.below(3)]
    base = [r.pick(alpha) for _ in range(3 + r.below(6))]
    ours = list(base)
    p = r.below(len(base) - 1)
    span = 1 + r.below(2)
    q = min(len(base), p + 1 + span)
    ln = ours.pop(p)
    ours.insert(q - 1, ln)
    theirs = list(base)
    t = max(0, min(len(base) - 1, p + r.below(span + 2) - 1))
    k = r.below(3)
    if k == 0:
        theirs[t] = "Z\n"
    elif k == 1:
        theirs.insert(t + r.below(2), "Z\n")
    else:
        del theirs[t]
    if r.chance(1, 2):
        ours, theirs = theirs, ours
    return [text_of(base), text_of(ours), text_of(theirs)]


SEPS = ["\r", "\x0c", "\x85", "\u2028", "\x0b", "\x1c", "\x1e", "\u2029"]


def gen_separators(r):
    """Lines holding other line-separator characters; the sides edit different pieces of the same line."""
    n = 1 + r.below(4)
    base = [f"p{i}{r.pick(SEPS)}m{i}{r.pick(SEPS)}q{i}\n" for i in range(n)]
    ours, theirs = list(base), list(base)
    i = r.below(n)
    j = i if r.chance(2, 3) else r.below(n)
    ours[i] = ours[i].replace("p", "P")
    theirs[j] = theirs[j].replace("q", "Q")
    if r.chance(1, 4):
        theirs[j] = theirs[j].replace("m", "M")
    if r.chance(1, 3):
        theirs, ours = ours, theirs
    return [text_of(base), text_of(ours), text_of(theirs)]


def gen_crlf(r):
    """CRLF text where one side turns a line into LF and the other edits the same or a nearby line."""
    n = 2 + r.below(5)
    base = [f"l{i}\r\n" for i in range(n)]
    ours, theirs = list(base), list(base)
    i = r.below(n)
    ours[i] = ours[i].replace("\r\n", "\n")
    j = min(n - 1, i + r.pick([0, 1, 1, 2]))
    theirs[j] = f"L{j}\r\n" if r.chance(1, 2) else theirs[j].replace("\r\n", "\n")
    if r.chance(1, 3):
        ours, theirs = theirs, ours
    return [text_of(base), text_of(ours), text_of(theirs)]


def gen_eol(r):
    """Line-ending traps: CRLF vs LF, lone CR and other separators inside lines, missing final newlines, empties."""
    base = [r.pick(EOL_POOL) for _ in range(1 + r.below(6))]
    ours = edit(r, base, 1 + r.below(2), EOL_POOL)
    theirs = edit(r, base, 1 + r.below(2), EOL_POOL)
    texts = []
    for lines in (base, ours, theirs):
        texts.append(text_of(lines, drop_final_newline=r.chance(2, 5)))
    if r.chance(1, 8):
        texts[r.below(3)] = ""
    return texts


MARKERS = ["<<<<<<< ours\n", "||||||| base\n", "=======\n", ">>>>>>> theirs\n"]


def gen_markers(r):
    """Marker-like lines in the inputs: ours inserts one, theirs replaces a line by one or appends one."""
    base = [r.pick(MARKERS + ["x\n", "y\n", "z\n"]) for _ in range(2 + r.below(5))]
    ours, theirs = list(base), list(base)
    ours.insert(r.below(len(base) + 1), r.pick(MARKERS))
    if r.chance(1, 2):
        theirs[r.below(len(base))] = r.pick(MARKERS)
    else:
        theirs.append(r.pick(MARKERS))
    return [text_of(base), text_of(ours), text_of(theirs)]


CODE = ["\n", "}\n", "{\n", "    return x;\n", "    i += 1;\n", "else\n"]


def code_lines(r, n, dup_pct=30):
    return [r.pick(CODE) if r.below(100) < dup_pct else f"    v{r.below(60)} = f({r.below(9)});\n" for _ in range(n)]


def gen_code(r):
    """Medium code-like files with repeated lines and scattered edits."""
    base = code_lines(r, 20 + r.below(50))
    pool = CODE + [f"    w{i} = g();\n" for i in range(6)]
    ours = edit(r, base, 2 + r.below(6), pool)
    theirs = edit(r, base, 2 + r.below(6), pool)
    if r.chance(1, 5):
        theirs = list(ours) if r.chance(1, 2) else theirs
    return [text_of(base, r.chance(1, 6)), text_of(ours, r.chance(1, 6)), text_of(theirs, r.chance(1, 6))]


def random_cases():
    gens = [("tiny alphabet (diff ties)", gen_ties, 36),
            ("moved lines in a tiny alphabet", gen_moves, 10),
            ("a line moved next to the other side's edit", gen_swaps, 20),
            ("edits at the same or nearby spots", gen_structure, 30),
            ("line endings, missing final newlines, empty texts", gen_eol, 24),
            ("other separator characters inside lines", gen_separators, 8),
            ("CRLF versus LF", gen_crlf, 8),
            ("marker-like lines", gen_markers, 12),
            ("code-like file", gen_code, 14)]
    res, n = [], 0
    for title, gen, count in gens:
        for i in range(count):
            n += 1
            r = SplitMix(180000 + n * 7919)
            res.append({"id": f"R{n:03d}", "title": title, "args": gen(r)})
    return res


def hidden():
    return hand() + random_cases()


# ── Stress ──────────────────────────────────────────────────────────────────
def stress():
    return [{"id": "S1", "title": "50 000 code-like lines, scattered edits on both sides", "seed": 1801,
             "n": 50000, "sites": 70},
            {"id": "S2", "title": "long common prefix and suffix around a busy middle", "seed": 1802,
             "n": 50000, "sites": 60},
            {"id": "S3", "title": "40 000 lines, over half of them repeated lines", "seed": 1803,
             "n": 40000, "sites": 60}]


def scatter(r, base, positions, pool, tag):
    """Apply one small edit at each position (descending, so earlier positions stay valid)."""
    out = list(base)
    for p in sorted(positions, reverse=True):
        kind = r.below(4)
        if kind == 0:
            out[p] = f"    {tag}{p} = h();\n"
        elif kind == 1:
            out[p:p] = [r.pick(pool) for _ in range(1 + r.below(2))]
        elif kind == 2:
            del out[p:p + 1 + r.below(2)]
        else:
            out[p:p + 1] = [r.pick(pool), f"    {tag}{p} = k();\n"]
    return out


def stress_args(case):
    r = SplitMix(case["seed"])
    n, sites = case["n"], case["sites"]
    pool = CODE + ["    x = y;\n", "    // note\n"]
    if case["id"] == "S1":
        base = code_lines(r, n)
        lo, hi = 0, n - 5
    elif case["id"] == "S2":
        base = code_lines(r, n)
        lo, hi = n // 2 - 1000, n // 2 + 1000
        # the busy middle repeats the lines around it, so the edges of the middle are ambiguous
        base[lo - 3:lo] = base[hi:hi + 3]
    else:
        base = code_lines(r, n, dup_pct=55)
        lo, hi = 0, n - 5
    pos_o = sorted({lo + r.below(hi - lo) for _ in range(sites)})
    pos_t = []
    for p in pos_o:
        k = r.below(4)
        if k == 0:
            pos_t.append(p)                                   # same spot
        elif k == 1:
            pos_t.append(min(hi - 1, p + 1 + r.below(2)))      # adjacent or one line apart
    pos_t += [lo + r.below(hi - lo) for _ in range(sites - len(pos_t))]
    pos_t = sorted(set(pos_t))
    ours = scatter(r, base, pos_o, pool, "o")
    theirs = "".join(scatter(r, base, pos_t, pool, "t"))
    if case["id"] == "S1":
        theirs = theirs[:-1]                                  # theirs also drops the final newline
    return ["".join(base), "".join(ours), theirs]
