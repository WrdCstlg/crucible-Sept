"""Reference for Problem 18 (three-way text merge). Stdlib only.

Lines keep their "\n"; the diff is Myers' forward greedy procedure exactly as SPEC.md states it (ties go to the
insertion, i.e. the down move); the merge is diff3 over base lines matched by both diffs.
"""

MARK_OURS = "<<<<<<< ours\n"
MARK_BASE = "||||||| base\n"
MARK_SEP = "=======\n"
MARK_THEIRS = ">>>>>>> theirs\n"


def split_lines(text):
    """Split at "\n" only; every line keeps its "\n"; a last line without one is still a line; "" has no lines."""
    parts = text.split("\n")
    lines = [p + "\n" for p in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def goes_down(prev, i, d):
    """Step d, diagonal k = 2*i - d. prev[j] is V[2*j - (d-1)] from step d-1, so V[k-1] = prev[i-1], V[k+1] = prev[i].
    Down (insertion, from k+1) reaches x = V[k+1]; right (deletion, from k-1) reaches V[k-1] + 1. Down wins ties."""
    return i == 0 or (i != d and prev[i - 1] < prev[i])


def myers_matches(a, b):
    """match[x] = index in b matched with a[x], or -1 when a[x] is deleted."""
    n, m = len(a), len(b)
    trace = []          # trace[d] = the V values step d reads (those of step d-1; for d = 0 the seed V[1] = 0)
    prev = [0]
    found = -1
    for d in range(n + m + 1):          # the procedure always stops by step n + m
        cur = [0] * (d + 1)
        for i in range(d + 1):
            k = 2 * i - d
            if goes_down(prev, i, d):
                x = prev[i]
            else:
                x = prev[i - 1] + 1
            y = x - k
            while x < n and y < m and a[x] == b[y]:
                x += 1
                y += 1
            cur[i] = x
            if x >= n and y >= m:
                found = i
                break
        trace.append(prev)
        if found >= 0:
            break
        prev = cur

    match = [-1] * n
    i, x_end = found, n
    while True:
        back = trace[d]
        k = 2 * i - d
        if goes_down(back, i, d):
            x_start, pi = back[i], i
        else:
            x_start, pi = back[i - 1] + 1, i - 1
        for x in range(x_start, x_end):
            match[x] = x - k
        if d == 0:
            break
        x_end = back[pi]
        i = pi
        d -= 1
    return match


def section(lines):
    """A part written inside a conflict block: a last line without "\n" gets one."""
    if lines and not lines[-1].endswith("\n"):
        return lines[:-1] + [lines[-1] + "\n"]
    return lines


def merge(base, ours, theirs):
    b, o, t = split_lines(base), split_lines(ours), split_lines(theirs)
    mo = myers_matches(b, o)
    mt = myers_matches(b, t)
    out = []
    conflicts = 0
    pb = po = pt = 0                      # where the current chunk starts in base, ours, theirs
    for i in range(len(b) + 1):
        if i < len(b):
            if mo[i] < 0 or mt[i] < 0:
                continue                  # not stable: part of the current chunk
            jo, jt = mo[i], mt[i]
        else:
            jo, jt = len(o), len(t)       # end of all three texts
        bs, os_, ts = b[pb:i], o[po:jo], t[pt:jt]
        if bs or os_ or ts:
            if os_ == bs:
                out.extend(ts)
            elif ts == bs:
                out.extend(os_)
            elif os_ == ts:
                out.extend(os_)
            else:
                conflicts += 1
                out.append(MARK_OURS)
                out.extend(section(os_))
                out.append(MARK_BASE)
                out.extend(section(bs))
                out.append(MARK_SEP)
                out.extend(section(ts))
                out.append(MARK_THEIRS)
        if i < len(b):
            out.append(b[i])
        pb, po, pt = i + 1, jo + 1, jt + 1
    text = "".join(out)
    return {"text": text, "conflicts": conflicts, "clean": conflicts == 0}
