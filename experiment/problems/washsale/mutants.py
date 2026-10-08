"""Planted misreadings of SPEC.md for Problem 12. Each must be caught by at least one non-public case."""

FRESH_FIRST = (
    "            if need and lot.fq:\n"
    "                k = min(need, lot.fq)\n"
    "                b = split(lot.fb, lot.fq, k)\n"
    "                lot.fq -= k\n"
    "                lot.fb -= b\n"
    "                pieces.append((lot, k, b, 0))\n"
    "                need -= k\n"
    "                if lot.fq == 0:\n"
    "                    win.exhaust(lot.pos)\n"
)

MUTANTS = {
    "M01 window end exclusive (a purchase 30 days after does not count)": [
        ("        while need and i < len(lots) and lots[i].day <= day + WINDOW:",
         "        while need and i < len(lots) and lots[i].day < day + WINDOW:"),
    ],
    "M02 no look-back: only purchases on or after the sale date replace": [
        ("        while self.lo < len(lots) and lots[self.lo].day < day - WINDOW:",
         "        while self.lo < len(lots) and lots[self.lo].day < day:"),
    ],
    "M03 unsold shares of a lot the sale draws from count as replacement": [
        ("            if lot.idx not in drawn:", "            if True:"),
    ],
    "M04 only the loss row's own lot is excluded": [
        ("day - start, drawn)", "day - start, {lot.idx})"),
    ],
    "M05 identical lists not merged transitively (last list wins)": [
        ("            parent.setdefault(s, s)", "            parent[s] = s"),
    ],
    "M06 a row with gain 0 counts as a loss row": [
        ("            if basis > proceeds:", "            if basis >= proceeds:"),
    ],
    "M07 disallowed rounded half up": [
        ("        disallowed = loss * r // n", "        disallowed = (2 * loss * r + n) // (2 * n)"),
    ],
    "M08 D spread: each chunk floors on its own, the last takes the rest": [
        ("            d = split(left_d, left_r, c)", "            d = split(disallowed, r, c) if left_r > c else left_d"),
    ],
    "M09 proceeds spread: each row floors on its own, the last takes the rest": [
        ("            proceeds = split(left_amount, left_qty, k)",
         "            proceeds = split(amount, qty, k) if left_qty > k else left_amount"),
    ],
    "M10 long-term means more than 365 days": [
        ('    return "LONG" if sale > anniversary.toordinal() else "SHORT"',
         '    return "LONG" if sale - start > 365 else "SHORT"'),
    ],
    "M11 anniversary of February 29 is February 28": [
        ("        anniversary = date(s.year + 1, 3, 1)", "        anniversary = date(s.year + 1, 2, 28)"),
    ],
    "M12 term from the acquisition date, ignoring carried days": [
        ('"term": term(start, day)', '"term": term(lot.day, day)'),
    ],
    "M13 carried days omit the sold piece's own carried days": [
        ("basis - proceeds, day - start", "basis - proceeds, day - lot.day"),
    ],
    "M14 same-day BUYs processed before SELLs": [
        ("    valid.sort(key=lambda v: (v[0], v[1]))", '    valid.sort(key=lambda v: (v[0], v[2] != "BUY", v[1]))'),
    ],
    "M15 fresh piece sold before replacement pieces": [
        ("            while need and lot.repl:\n", FRESH_FIRST + "            while need and lot.repl:\n"),
    ],
    "M16 a loss with D = 0 uses no replacement shares": [
        ("        if r == 0:\n            return 0", "        if r == 0 or loss * r // n == 0:\n            return 0"),
    ],
    "M17 bools accepted as quantities and amounts": [
        ("    if type(qty) is not int or qty < 1 or type(amount) is not int or amount < 0:",
         "    if not isinstance(qty, int) or qty < 1 or not isinstance(amount, int) or amount < 0:"),
    ],
    "M18 realized rows left in processing order": [
        ('    rows.sort(key=lambda r: r["sale"])', "    rows = rows"),
    ],
    "M19 split rule rounds the taken basis up": [
        ("                b = split(lot.fb, lot.fq, k)", "                b = lot.fb - split(lot.fb, lot.fq, lot.fq - k)"),
    ],
    "M20 holding starts converted to dates (no day-number shortcut)": [
        ('    if sale - start > 366:\n        return "LONG"\n', ""),
    ],
}
