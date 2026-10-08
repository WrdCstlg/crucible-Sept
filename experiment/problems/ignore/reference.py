"""Reference for Problem 17 (ignore-file matcher). Stdlib only.

Structure:
  * paths are validated, and the directory set is built by walking each path upward until a known directory;
  * every ignore-file line is compiled once into a Rule (segment matchers + flags);
  * directories are evaluated once each, parents first (sorted order puts a prefix before its extensions), and each
    keeps the chain of ignore files that apply below it, so a file costs one rule evaluation, not one per ancestor;
  * a pattern segment compiles to a plain string or to a regex that is linear-time: every star but the last becomes
    an atomic lazy group, which is exact for glob chunks of fixed width (the leftmost placement is always optimal).
"""
import re

GLOB = "GLOBSTAR"


# ── Paths ────────────────────────────────────────────────────────────────────
def split_valid(path):
    """Segments of a syntactically valid path, or None."""
    segs = path.split("/")
    for s in segs:
        if s == "" or s == "." or s == "..":
            return None
    return segs


# ── Ignore-file lines ────────────────────────────────────────────────────────
def strip_trailing_spaces(line):
    keep = 0                       # length of the prefix that must be kept
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c == "\\":              # an escape pair is always kept (even when its second half is a space)
            i += 2
            keep = min(i, n)
        elif c == " ":
            i += 1
        else:
            i += 1
            keep = i
    return line[:keep]


def parse_class(part, i):
    """Bracket expression starting at part[i] == '['. Returns (token, next index) or None if unclosed/bad."""
    n = len(part)
    j = i + 1
    neg = False
    if j < n and part[j] in "!^":
        neg = True
        j += 1
    chars, ranges = [], []
    first = True
    while True:
        if j >= n:
            return None
        c = part[j]
        if c == "]" and not first:
            return ("[", neg, chars, ranges), j + 1
        first = False
        if c == "\\":
            if j + 1 >= n:
                return None
            lo = part[j + 1]
            j += 2
        else:
            lo = c
            j += 1
        if j + 1 < n and part[j] == "-" and part[j + 1] != "]":
            k = j + 1
            if part[k] == "\\":
                if k + 1 >= n:
                    return None
                hi = part[k + 1]
                j = k + 2
            else:
                hi = part[k]
                j = k + 1
            ranges.append((lo, hi))
        else:
            chars.append(lo)


def tokenize(part):
    """Tokens of one pattern segment, or None if the segment (and so the rule) matches nothing."""
    toks = []
    i, n = 0, len(part)
    while i < n:
        c = part[i]
        if c == "\\":
            if i + 1 >= n:
                return None
            toks.append(("c", part[i + 1]))
            i += 2
        elif c == "?":
            toks.append(("?",))
            i += 1
        elif c == "*":
            toks.append(("*",))
            i += 1
        elif c == "[":
            got = parse_class(part, i)
            if got is None:
                return None
            toks.append(got[0])
            i = got[1]
        else:
            toks.append(("c", c))
            i += 1
    return toks


def class_rx(neg, chars, ranges):
    items = [re.escape(c) for c in chars]
    items += [re.escape(lo) + "-" + re.escape(hi) for lo, hi in ranges if lo <= hi]
    if not items:
        return "." if neg else "(?!)"
    return "[" + ("^" if neg else "") + "".join(items) + "]"


def token_rx(t):
    if t[0] == "c":
        return re.escape(t[1])
    if t[0] == "?":
        return "."
    return class_rx(t[1], t[2], t[3])


def compile_segment(part):
    """A callable name -> bool for one ordinary pattern segment, or None if it matches nothing."""
    if part == "":
        return None
    toks = tokenize(part)
    if toks is None:
        return None
    if all(t[0] == "c" for t in toks):
        text = "".join(t[1] for t in toks)
        return text.__eq__
    chunks = [[]]                  # fixed-width chunks separated by runs of stars
    for t in toks:
        if t[0] == "*":
            if chunks[-1] or len(chunks) == 1:
                chunks.append([])
        else:
            chunks[-1].append(token_rx(t))
    if len(chunks) == 1:
        rx = "".join(chunks[0])
    else:
        rx = "".join(chunks[0])
        rx += "".join("(?>.*?" + "".join(c) + ")" for c in chunks[1:-1])
        rx += ".*" + "".join(chunks[-1])
    return re.compile(rx, re.DOTALL).fullmatch


class Rule:
    __slots__ = ("negated", "dir_only", "anchored", "one", "fixed", "head", "mids", "tail", "trailing")


def compile_line(line):
    if line.startswith("#"):
        return None
    line = strip_trailing_spaces(line)
    if not line:
        return None
    negated = line.startswith("!")
    if negated:
        line = line[1:]
    dir_only = line.endswith("/")
    if dir_only:
        line = line[:-1]
    anchored = "/" in line
    if line.startswith("/"):
        line = line[1:]
    if not line:
        return None
    r = Rule()
    r.negated, r.dir_only, r.anchored = negated, dir_only, anchored
    r.one = r.fixed = r.head = r.mids = r.tail = None
    r.trailing = False
    parts = line.split("/")
    segs = []
    for part in parts:
        if anchored and len(part) >= 2 and part == "*" * len(part):
            segs.append(GLOB)
        else:
            m = compile_segment(part)
            if m is None:
                return None
            segs.append(m)
    if not anchored:
        r.one = segs[0]
    elif GLOB not in segs:
        r.fixed = segs
    else:
        chunks = [[]]
        for s in segs:
            if s is GLOB:
                chunks.append([])
            else:
                chunks[-1].append(s)
        r.head, r.mids, r.tail = chunks[0], chunks[1:-1], chunks[-1]
        r.trailing = segs[-1] is GLOB
    return r


def compile_file(lines):
    out = []
    for line in lines:
        r = compile_line(line)
        if r is not None:
            out.append(r)
    return out


# ── Matching ─────────────────────────────────────────────────────────────────
def chunk_at(chunk, segs, s):
    for t, m in enumerate(chunk):
        if not m(segs[s + t]):
            return False
    return True


def rule_matches(r, segs, off, is_dir):
    """Does rule r (from the ignore file at depth off) match the path with these segments?"""
    if r.dir_only and not is_dir:
        return False
    if r.one is not None:
        return bool(r.one(segs[-1]))
    n = len(segs)
    if r.fixed is not None:
        if n - off != len(r.fixed):
            return False
        return chunk_at(r.fixed, segs, off)
    lo = off + len(r.head)
    hi = n - len(r.tail) - (1 if r.trailing else 0)
    if lo > hi:
        return False
    if not chunk_at(r.head, segs, off) or not chunk_at(r.tail, segs, n - len(r.tail)):
        return False
    pos = lo
    for chunk in r.mids:
        size = len(chunk)
        while pos + size <= hi and not chunk_at(chunk, segs, pos):
            pos += 1
        if pos + size > hi:
            return False
        pos += size
    return True


def decide(segs, is_dir, chain):
    """True if the rules say ignore. chain: ((depth, rules), ...) root first."""
    for depth, compiled in reversed(chain):
        for r in reversed(compiled):
            if rule_matches(r, segs, depth, is_dir):
                return not r.negated
    return False


# ── Entry point ──────────────────────────────────────────────────────────────
def ignored(files, rules):
    invalid = set()
    valid = {}
    for p in files:
        if p in valid or p in invalid:
            continue
        segs = split_valid(p)
        if segs is None:
            invalid.add(p)
        else:
            valid[p] = segs

    dirs = set()
    for p in valid:
        i = p.rfind("/")
        while i > 0:
            d = p[:i]
            if d in dirs:
                break
            dirs.add(d)
            i = p.rfind("/", 0, i)
    for p in list(valid):
        if p in dirs:
            invalid.add(p)
            del valid[p]

    compiled = {}
    for base, lines in rules.items():
        if base == "" or base in dirs:
            compiled[base] = compile_file(lines)

    root_chain = ((0, compiled[""]),) if "" in compiled else ()
    state = {"": (False, root_chain)}
    top_dirs = []
    for d in sorted(dirs):
        i = d.rfind("/")
        parent = d[:i] if i > 0 else ""
        p_excl, p_chain = state[parent]
        segs = d.split("/")
        if p_excl:
            excl = True
        else:
            excl = decide(segs, True, p_chain)
            if excl:
                top_dirs.append(d)
        chain = p_chain + ((len(segs), compiled[d]),) if d in compiled else p_chain
        state[d] = (excl, chain)

    out = []
    for f, segs in valid.items():
        i = f.rfind("/")
        p_excl, p_chain = state[f[:i] if i > 0 else ""]
        if p_excl or decide(segs, False, p_chain):
            out.append(f)
    return {"ignored": sorted(out), "ignored_dirs": sorted(top_dirs), "invalid": sorted(invalid)}
