"""Planted misreadings of SPEC.md for Problem 14. Each must be caught by at least one non-public case."""

MUTANTS = {
    "M01 pass 2 gives each entry, in input order, its nearest free line": [
        ("    take_pairs(\"amount\", cands)",
         "    for c in sorted(cands, key=lambda c: (c[4], c[0], c[3])):\n"
         "        if not l_used[c[4]] and not b_used[c[5]]:\n"
         "            record(\"amount\", [c[4]], [c[5]])"),
    ],
    "M02 window is exclusive (days < W)": [
        ("                if dd <= W:\n                    cands.append((dd, e[1], e[0], b[0], li, bi))",
         "                if dd < W:\n                    cands.append((dd, e[1], e[0], b[0], li, bi))"),
        ("for bi in lst[bisect_left(days, e[1] - W):bisect_right(days, e[1] + W)]:",
         "for bi in lst[bisect_left(days, e[1] - W + 1):bisect_right(days, e[1] + W - 1)]:"),
        ("                if dd <= W:\n                    cands.append((dd, e[2] - amount",
         "                if dd < W:\n                    cands.append((dd, e[2] - amount"),
    ],
    "M03 key ties broken by input position instead of id order": [
        ("            cands.append((abs(b[1] - e[1]), e[1], e[0], b[0], li, bi))",
         "            cands.append((abs(b[1] - e[1]), e[1], li, bi, li, bi))"),
    ],
    "M04 reference found as a substring of a token, not a whole token": [
        ("        for bi in carriers.get(e[3], ()):\n            b = B[bi]\n            if b[2] == e[2]:",
         "        for bi in range(len(B)):\n            b = B[bi]\n            if b[2] == e[2] and any(e[3] in t for t in b[3]):"),
    ],
    "M05 leading zeros stripped only at the start of the token": [
        ("            out.append(DIGIT_RUN.sub(_no_leading_zeros, t))", "            out.append(t.lstrip(\"0\") or \"0\")"),
    ],
    "M06 zeros stripped before the joiners are deleted": [
        ("        t = run.translate(JOINERS).upper()\n        if t:\n            out.append(DIGIT_RUN.sub(_no_leading_zeros, t))",
         "        t = DIGIT_RUN.sub(_no_leading_zeros, run).translate(JOINERS).upper()\n        if t:\n"
         "            out.append(t)"),
    ],
    "M07 non-ASCII letters and digits count as word characters": [
        ("WORD_RUN = re.compile(r\"[A-Za-z0-9._-]+\")", "WORD_RUN = re.compile(r\"[\\w.-]+\")"),
    ],
    "M08 a ref with several tokens is joined into one key": [
        ("    return toks[0] if len(toks) == 1 else None", "    return \"\".join(toks) if toks else None"),
    ],
    "M09 tokens are case-sensitive": [
        ("        t = run.translate(JOINERS).upper()", "        t = run.translate(JOINERS)"),
    ],
    "M10 groups chosen by smallest day distance before fewest members": [
        ("    if best is not None:\n        return best[2]\n    n = len(members)", "    n = len(members)"),
        ("cand = (len(g), sum(m[0] for m in g), sorted(m[1] for m in g), g)",
         "cand = (sum(m[0] for m in g), len(g), sorted(m[1] for m in g), g)"),
    ],
    "M11 multi_ledger processes lines in input order": [
        ("    for bi in sorted((bi for bi in range(len(B)) if not b_used[bi]), key=lambda bi: (B[bi][1], B[bi][0])):",
         "    for bi in [bi for bi in range(len(B)) if not b_used[bi]]:"),
    ],
    "M12 parties compared ignoring case and surrounding spaces": [
        ("                parties.setdefault(e[4], []).append(", "                parties.setdefault(e[4].strip().lower(), []).append("),
    ],
    "M13 entries with an empty party may form groups": [
        ("if not l_used[li] and L[li][4] != \"\"), key=lambda li: L[li][1])",
         "if not l_used[li]), key=lambda li: L[li][1])"),
    ],
    "M14 fee lowers the magnitude for payments too (|bank| = |ledger| - fee)": [
        ("            if e[2] > 0:\n                lo = max(lo, 1)",
         "            if e[2] < 0:\n                lo, hi = e[2] + 1, min(e[2] + F, -1)\n"
         "            if e[2] > 0:\n                lo = max(lo, 1)"),
        ("cands.append((dd, e[2] - amount, e[1], e[0], b[0], li, bi))",
         "cands.append((dd, abs(e[2] - amount), e[1], e[0], b[0], li, bi))"),
    ],
    "M15 fee pass key leaves out the fee": [
        ("cands.append((dd, e[2] - amount, e[1], e[0], b[0], li, bi))", "cands.append((dd, e[1], e[0], b[0], li, bi))"),
    ],
    "M16 difference is ledger minus bank": [
        ("\"difference\": sum(B[bi][2] for bi in bis) - sum(L[li][2] for li in lis)",
         "\"difference\": sum(L[li][2] for li in lis) - sum(B[bi][2] for bi in bis)"),
    ],
    "M17 duplicate ids: the first copy stays valid": [
        ("    for i, r, day in passed:\n        if count[r[\"id\"]] > 1:\n            bad.append(i)\n        else:\n"
         "            good.append((i, r, day))",
         "    seen = set()\n    for i, r, day in passed:\n        if r[\"id\"] in seen:\n            bad.append(i)\n"
         "        else:\n            seen.add(r[\"id\"])\n            good.append((i, r, day))"),
    ],
    "M18 a bool is accepted as an int amount": [
        ("        if type(r[\"amount\"]) is not int or r[\"amount\"] == 0:",
         "        if not isinstance(r[\"amount\"], int) or r[\"amount\"] == 0:"),
    ],
    "M19 dates parsed leniently with strptime": [
        ("from datetime import date\n", "from datetime import date, datetime\n"),
        ("    if type(s) is not str or len(s) != 10 or s[4] != \"-\" or s[7] != \"-\":\n        return None\n"
         "    y, m, d = s[0:4], s[5:7], s[8:10]\n    if not all(c in DIGITS for c in y + m + d):\n        return None\n"
         "    try:\n        return date(int(y), int(m), int(d)).toordinal()\n    except ValueError:",
         "    try:\n        return datetime.strptime(s, \"%Y-%m-%d\").toordinal()\n    except (TypeError, ValueError):"),
    ],
    "M20 groups only combine amounts with the same sign as the target": [
        ("    by_amount = {}\n    for pos, m in enumerate(members):",
         "    members = [m for m in members if (m[2] > 0) == (target > 0)]\n    by_amount = {}\n"
         "    for pos, m in enumerate(members):"),
    ],
}
