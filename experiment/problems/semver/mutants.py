"""Planted misreadings of SPEC.md for Problem 7. Each must be caught by at least one non-public case."""

MUTANTS = {
    "M01 caret ignores the 0.x rule": [
        ("""    for i, value in enumerate(comps):
        if value != 0:
            return bump(comps, i)
    return bump(comps, len(comps) - 1)""",
         """    return bump(comps, 0)"""),
    ],
    "M02 prereleases admitted freely": [
        ("        if v[3] and not any(w[3] and w[:3] == v[:3] for _, w in cs):",
         "        if False:"),
    ],
    "M03 prerelease opt-in ignores M.m.p": [
        ("if v[3] and not any(w[3] and w[:3] == v[:3] for _, w in cs):",
         "if v[3] and not any(w[3] for _, w in cs):"),
    ],
    "M04 numeric prerelease ids compared as strings": [
        ("    if na and nb:\n        x, y = int(a), int(b)", "    if na and nb:\n        x, y = a, b"),
    ],
    "M05 space after an operator accepted": [
        ("    tokens = [t for t in text.split(\" \") if t != \"\"]",
         "    import re\n    text = re.sub(r'(>=|<=|>|<|=|~|\\^) +', r'\\1', text)\n"
         "    tokens = [t for t in text.split(\" \") if t != \"\"]"),
    ],
    "M06 any whitespace splits tokens": [
        ("    tokens = [t for t in text.split(\" \") if t != \"\"]", "    tokens = text.split()"),
    ],
    "M07 packages resolved in first-seen order": [
        ("        pending = sorted(n for n in names if n not in selected)",
         "        order = list(root)\n"
         "        for _, _, deps in selected.values():\n"
         "            order += list(deps)\n"
         "        pending = [n for n in dict.fromkeys(order) if n not in selected]"),
    ],
    "M08 candidates tried lowest first": [
        ("            if c:\n                return -c", "            if c:\n                return c"),
    ],
    "M09 leading zeros accepted": [
        ("(s == \"0\" or s[0] != \"0\")", "True"),
    ],
    "M10 >partial read as >low": [
        ("    if op == \">\":\n        return [(\">=\", nxt(comps))]", "    if op == \">\":\n        return [(\">\", low(comps, pre))]"),
    ],
    "M11 <=partial read as <=low": [
        ("    if op == \"<=\":\n        return [(\"<\", nxt(comps))]", "    if op == \"<=\":\n        return [(\"<=\", low(comps, pre))]"),
    ],
    "M12 hyphen partial upper bound inclusive of low": [
        ("        elif b_comps:\n            out.append((\"<\", nxt(b_comps)))",
         "        elif b_comps:\n            out.append((\"<=\", low(b_comps, b_pre)))"),
    ],
    "M13 invalid set only drops that set": [
        ("        return [set_comparators(part) for part in text.split(\"||\")]\n    except Invalid:\n        return None",
         "        pass\n    except Invalid:\n        return None\n"
         "    out = []\n"
         "    for part in text.split(\"||\"):\n"
         "        try:\n"
         "            out.append(set_comparators(part))\n"
         "        except Invalid:\n"
         "            out.append(NOTHING)\n"
         "    return out"),
    ],
    "M14 equal precedence: smaller string first": [
        ("            return (a[1] < b[1]) - (a[1] > b[1])", "            return (a[1] > b[1]) - (a[1] < b[1])"),
    ],
    "M15 no re-check of already selected packages": [
        ("            if consistent() and search():", "            if search():"),
    ],
    "M16 build metadata counts in precedence": [
        ("    return (int(parts[0]), int(parts[1]), int(parts[2]), tuple(pre) if pre else ())",
         "    return (int(parts[0]), int(parts[1]), int(parts[2]), tuple(pre) if pre else (), build or \"\")"),
        ("    for i in range(3):\n        if v[i] != w[i]:\n            return -1 if v[i] < w[i] else 1\n    pv, pw = v[3], w[3]\n    if not pv and not pw:\n        return 0",
         "    for i in range(3):\n        if v[i] != w[i]:\n            return -1 if v[i] < w[i] else 1\n    pv, pw = v[3], w[3]\n    if not pv and not pw:\n"
         "        bv, bw = (v[4] if len(v) > 4 else \"\"), (w[4] if len(w) > 4 else \"\")\n"
         "        return (bv > bw) - (bv < bw)"),
    ],
    "M17 caret all-zero bumps patch": [
        ("            return bump(comps, i)\n    return bump(comps, len(comps) - 1)",
         "            return bump(comps, i)\n    return bump(comps + [0] * (3 - len(comps)), 2)"),
    ],
    "M18 tilde full version bumps major": [
        ("            return [(\">=\", v), (\"<\", bump(comps, 1))]", "            return [(\">=\", v), (\"<\", bump(comps, 0))]"),
    ],
}
