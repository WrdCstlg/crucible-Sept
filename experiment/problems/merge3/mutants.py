"""Planted misreadings of SPEC.md for Problem 18. Each must be caught by at least one non-public case."""

CALLS = "    mo = myers_matches(b, o)\n    mt = myers_matches(b, t)\n"
BRANCH_SAME = "            elif os_ == ts:\n                out.extend(os_)\n"
BASE_PART = "                out.append(MARK_BASE)\n                out.extend(section(bs))\n"

PATCH_MERGE = '''def patch_merge(bs, os_, ts):
    """Patch-style: two edits in one chunk merge unless their base ranges overlap (touching is fine)."""
    lb = len(bs)

    def common_prefix(xs):
        n = 0
        while n < min(lb, len(xs)) and xs[n] == bs[n]:
            n += 1
        return n

    def common_suffix(xs):
        n = 0
        while n < min(lb, len(xs)) and xs[len(xs) - 1 - n] == bs[lb - 1 - n]:
            n += 1
        return n

    so, st, po_, pt_ = common_suffix(os_), common_suffix(ts), common_prefix(os_), common_prefix(ts)
    if lb - so <= pt_:
        return os_[:len(os_) - so] + bs[lb - so:pt_] + ts[pt_:]
    if lb - st <= po_:
        return ts[:len(ts) - st] + bs[lb - st:po_] + os_[po_:]
    return None


def merge(base, ours, theirs):
'''

SUFFIX_TRIM = '''def myers_matches(a, b):
    s = 0
    while s < len(a) and s < len(b) and a[len(a) - 1 - s] == b[len(b) - 1 - s]:
        s += 1
    match = _myers(a[:len(a) - s], b[:len(b) - s])
    return match + [len(b) - s + j for j in range(s)]


def _myers(a, b):
'''

MUTANTS = {
    "M01 diff ties go to the deletion (right) move": [
        ("    return i == 0 or (i != d and prev[i - 1] < prev[i])",
         "    return i == 0 or (i != d and prev[i - 1] + 1 < prev[i])"),
    ],
    "M02 common suffix removed before diffing": [
        ("def myers_matches(a, b):\n", SUFFIX_TRIM),
    ],
    "M03 str.splitlines used (CR, FF, U+0085, U+2028 end lines)": [
        ("    parts = text.split(\"\\n\")\n    lines = [p + \"\\n\" for p in parts[:-1]]\n    if parts[-1]:\n"
         "        lines.append(parts[-1])\n    return lines",
         "    return text.splitlines(keepends=True)"),
    ],
    "M04 lines compared without their newline": [
        (CALLS, "    kb, ko, kt = ([s.rstrip(\"\\n\") for s in x] for x in (b, o, t))\n"
                "    mo = myers_matches(kb, ko)\n    mt = myers_matches(kb, kt)\n"),
    ],
    "M05 edits in one chunk merge unless they overlap (patch style)": [
        ("def merge(base, ours, theirs):\n", PATCH_MERGE),
        (BRANCH_SAME, BRANCH_SAME + "            elif patch_merge(bs, os_, ts) is not None:\n"
                                   "                out.extend(patch_merge(bs, os_, ts))\n"),
    ],
    "M06 identical changes on both sides reported as a conflict": [
        (BRANCH_SAME, ""),
    ],
    "M07 conflict block without the base part (two-way style)": [
        (BASE_PART, ""),
    ],
    "M08 newline-less last line not terminated inside a block": [
        ("    if lines and not lines[-1].endswith(\"\\n\"):", "    if False:"),
    ],
    "M09 conflicts counted from marker lines in the text": [
        ("    return {\"text\": text, \"conflicts\": conflicts, \"clean\": conflicts == 0}",
         "    conflicts = sum(1 for ln in split_lines(text) if ln == MARK_OURS)\n"
         "    return {\"text\": text, \"conflicts\": conflicts, \"clean\": conflicts == 0}"),
    ],
    "M10 no chunk after the last stable line": [
        ("    for i in range(len(b) + 1):", "    for i in range(len(b)):"),
    ],
    "M11 different insertions at the same place both kept, ours first": [
        (BRANCH_SAME, BRANCH_SAME + "            elif not bs:\n                out.extend(os_ + ts)\n"),
    ],
    "M12 base marker and part omitted when the base part is empty": [
        (BASE_PART, "                if bs:\n                    out.append(MARK_BASE)\n"
                    "                    out.extend(section(bs))\n"),
    ],
    "M13 an empty text is one empty line": [
        ("    if parts[-1]:", "    if parts[-1] or len(parts) == 1:"),
    ],
    "M14 merged text forced to end with a newline": [
        ("    text = \"\".join(out)\n",
         "    text = \"\".join(out)\n    if text and not text.endswith(\"\\n\"):\n        text += \"\\n\"\n"),
    ],
    "M15 clean decided by searching the text for a marker": [
        ("\"clean\": conflicts == 0}", "\"clean\": MARK_OURS not in text}"),
    ],
    "M16 CRLF and LF lines compared as equal": [
        (CALLS, "    kb, ko, kt = ([s[:-2] + \"\\n\" if s.endswith(\"\\r\\n\") else s for s in x] for x in (b, o, t))\n"
                "    mo = myers_matches(kb, ko)\n    mt = myers_matches(kb, kt)\n"),
    ],
    "M17 diff tie test forgets the +1 of the right move": [
        ("    return i == 0 or (i != d and prev[i - 1] < prev[i])",
         "    return i == 0 or (i != d and prev[i - 1] <= prev[i])"),
    ],
    "M18 both sides deleting the same lines is a conflict (same change needs new text)": [
        ("            elif os_ == ts:\n", "            elif os_ == ts and os_:\n"),
    ],
}
