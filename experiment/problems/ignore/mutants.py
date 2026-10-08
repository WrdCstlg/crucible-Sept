"""Planted misreadings of SPEC.md for Problem 17. Each must be caught by at least one non-public case."""

MUTANTS = {
    "M01 a negation can re-include a path under an excluded directory": [
        ("                return not r.negated\n    return False",
         "                return not r.negated\n    return None"),
        ("        if p_excl:\n            excl = True\n        else:\n            excl = decide(segs, True, p_chain)\n"
         "            if excl:\n                top_dirs.append(d)",
         "        v = decide(segs, True, p_chain)\n        excl = p_excl if v is None else v\n"
         "        if excl and not p_excl:\n            top_dirs.append(d)"),
        ("        if p_excl or decide(segs, False, p_chain):",
         "        v = decide(segs, False, p_chain)\n        if (p_excl if v is None else v):"),
    ],
    "M02 trailing /** also matches the directory itself": [
        ("    hi = n - len(r.tail) - (1 if r.trailing else 0)", "    hi = n - len(r.tail)"),
    ],
    "M03 the shallower ignore file wins over the deeper one": [
        ("    for depth, compiled in reversed(chain):", "    for depth, compiled in chain:"),
    ],
    "M04 the first matching line wins instead of the last": [
        ("        for r in reversed(compiled):", "        for r in compiled:"),
    ],
    "M05 only a leading slash anchors (a middle slash floats)": [
        ("    anchored = \"/\" in line\n",
         "    anchored = \"/\" in line\n    floating = anchored and not line.startswith(\"/\")\n"),
        ("    parts = line.split(\"/\")\n",
         "    parts = line.split(\"/\")\n    if floating:\n        parts = [\"**\"] + parts\n"),
    ],
    "M06 a directory-only rule also matches files": [
        ("    if r.dir_only and not is_dir:\n        return False\n", ""),
    ],
    "M07 a trailing slash also anchors the rule": [
        ("    anchored = \"/\" in line\n", "    anchored = \"/\" in line or dir_only\n"),
    ],
    "M08 [^x] is not a negation (fnmatch style)": [
        ("    if j < n and part[j] in \"!^\":", "    if j < n and part[j] == \"!\":"),
    ],
    "M09 an unclosed [ is a literal [ (fnmatch style)": [
        ("            if got is None:\n                return None\n            toks.append(got[0])",
         "            if got is None:\n                toks.append((\"c\", \"[\"))\n                i += 1\n"
         "                continue\n            toks.append(got[0])"),
    ],
    "M10 a ] right after [ closes the bracket expression": [
        ("        if c == \"]\" and not first:", "        if c == \"]\":"),
    ],
    "M11 lines are rstripped (escaped spaces and tabs removed too)": [
        ("    line = strip_trailing_spaces(line)", "    line = line.rstrip()"),
    ],
    "M12 a backslash outside brackets is a literal character": [
        ('        if c == "\\\\":\n            if i + 1 >= n:\n                return None\n'
         '            toks.append(("c", part[i + 1]))\n            i += 2\n        elif c == "?":',
         '        if c == "?":'),
    ],
    "M13 a middle /**/ needs at least one directory": [
        ("    if lo > hi:\n", "    if lo > hi or (r.head and r.tail and lo == hi):\n"),
    ],
    "M14 * in an anchored rule can cross a slash": [
        ("        if n - off != len(r.fixed):\n            return False\n",
         "        if n - off < len(r.fixed):\n            return False\n        if n - off > len(r.fixed):\n"
         "            k = len(r.fixed)\n            return chunk_at(r.fixed[:-1], segs, off) and "
         "bool(r.fixed[-1](\"/\".join(segs[off + k - 1:])))\n"),
    ],
    "M15 a path that is also a directory is kept as a file": [
        ("    for p in list(valid):\n        if p in dirs:\n            invalid.add(p)\n            del valid[p]\n", ""),
    ],
    "M16 . and .. segments are accepted": [
        ("        if s == \"\" or s == \".\" or s == \"..\":", "        if s == \"\":"),
    ],
    "M17 ignored_dirs lists every excluded directory": [
        ("        if p_excl:\n            excl = True\n", "        if p_excl:\n            excl = True\n            top_dirs.append(d)\n"),
    ],
    "M18 a reversed range is read as the forward range": [
        ("    items += [re.escape(lo) + \"-\" + re.escape(hi) for lo, hi in ranges if lo <= hi]",
         "    items += [re.escape(min(lo, hi)) + \"-\" + re.escape(max(lo, hi)) for lo, hi in ranges]"),
    ],
    "M19 case-insensitive matching": [
        ("    return re.compile(rx, re.DOTALL).fullmatch", "    return re.compile(rx, re.DOTALL | re.IGNORECASE).fullmatch"),
        ("        return text.__eq__", "        return re.compile(re.escape(text), re.DOTALL | re.IGNORECASE).fullmatch"),
    ],
    "M20 anchored rules in a subdirectory's ignore file are relative to the root": [
        ("            if rule_matches(r, segs, depth, is_dir):", "            if rule_matches(r, segs, 0, is_dir):"),
    ],
}
