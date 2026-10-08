"""Cases for Problem 17 (ignore-file matcher). Stdlib only (copied into the sandbox like every cases.py).

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


def case(cid, title, files, rules, ignored=None, dirs=None, invalid=None):
    c = {"id": cid, "title": title, "args": [files, rules]}
    if ignored is not None:
        c["spec_expected"] = {"ignored": ignored, "ignored_dirs": dirs, "invalid": invalid}
    return c


def public():
    return [
        case("P1", "comments, negation, last match wins, directory-only at any depth, invalid path",
             ["a.log", "src/b.log", "src/keep.log", "build/out.txt", "src/build", "docs/build/x.md", "a//b", "README"],
             {"": ["# logs", "*.log", "!keep.log", "build/", ""]},
             ["a.log", "build/out.txt", "docs/build/x.md", "src/b.log"], ["build", "docs/build"], ["a//b"]),
        case("P2", "anchoring relative to the ignore file; deeper ignore file wins",
             ["out/a.txt", "src/out/b.txt", "src/gen/c.txt", "src/lib/gen/d.txt", "src/e.txt"],
             {"": ["/out", "*.txt"], "src": ["!*.txt", "/gen/"]},
             ["out/a.txt", "src/gen/c.txt"], ["out", "src/gen"], []),
        case("P3", "an excluded directory cannot be re-included",
             ["logs/a.log", "logs/keep/b.log", "notes/c.txt"],
             {"": ["logs/", "!logs/keep/", "!logs/keep/b.log"], "logs/keep": ["!*"]},
             ["logs/a.log", "logs/keep/b.log"], ["logs"], []),
        case("P4", "escapes, trailing spaces, ?, a range, a path that is also a directory",
             ["#notes", "a ", "a", "x1", "x/y", "x", "data/v2", "data/vX"],
             {"": ["\\#notes", "a\\ ", "data/v[0-9]", "?1   "]},
             ["#notes", "a ", "data/v2", "x1"], [], ["x"]),
    ]


def hand():
    return [
        # build/ is excluded at the root, so the negations inside build/'s own ignore file change nothing.
        case("H01", "parent exclusion beats negations in the excluded directory's own ignore file",
             ["build/a.o", "build/keep.txt", "src/a.o"],
             {"": ["build/", "*.o"], "build": ["!keep.txt", "!*.o"]},
             ["build/a.o", "build/keep.txt", "src/a.o"], ["build"], []),
        # out/** needs at least one segment after out, so out itself is not excluded and out/keep can be re-included;
        # out/sub is excluded (by out/**), so !out/sub/b cannot help.
        case("H02", "trailing /** matches inside the directory but not the directory itself",
             ["out/a", "out/sub/b", "out/keep"],
             {"": ["out/**", "!out/keep", "!out/sub/b"]},
             ["out/a", "out/sub/b"], ["out/sub"], []),
        case("H03", "leading **/ and middle /**/ match zero or more directories",
             ["foo", "a/foo", "a/b/foo", "x/y", "x/m/n/y", "xy"],
             {"": ["**/foo", "x/**/y"]},
             ["a/b/foo", "a/foo", "foo", "x/m/n/y", "x/y"], [], []),
        case("H04", "a middle slash anchors; * does not cross /",
             ["doc/a.txt", "src/doc/b.txt", "doc/sub/c.txt"],
             {"": ["doc/*.txt"]},
             ["doc/a.txt"], [], []),
        # tmp/ -> directory-only "tmp" with no slash left: unanchored, so it matches src/tmp too; lib/tmp is a file.
        case("H05", "a trailing slash alone does not anchor; directory-only skips files",
             ["tmp/a", "src/tmp/b", "lib/tmp"],
             {"": ["tmp/"]},
             ["src/tmp/b", "tmp/a"], ["src/tmp", "tmp"], []),
        case("H06", "the deepest ignore file with a match decides",
             ["a/x.log", "a/b/y.log", "c/z.log"],
             {"": ["*.log", "!*.log"], "a": ["*.log"], "a/b": ["!y.log"]},
             ["a/x.log"], [], []),
        case("H07", "last matching line wins, including re-ignoring after a negation",
             ["a.txt", "ab.txt", "b.txt", "abc.txt"],
             {"": ["*.txt", "!a*.txt", "ab.txt"]},
             ["ab.txt", "b.txt"], [], []),
        # "d\\\\   " is d, backslash, backslash, three spaces: the pair \\ is kept, the plain spaces go -> name d\.
        case("H08", "trailing spaces: escaped kept, plain removed; leading spaces and tabs kept",
             ["a", "a ", "b", " b", "c\t", "c", "d\\"],
             {"": ["a\\ ", " b", "c\t", "d\\\\   "]},
             [" b", "a ", "c\t", "d\\"], [], []),
        # "#a" is a comment; " #c" is not; \!d is the name !d; !!f negates the name !f.
        case("H09", "comments, escaped # and !, double !",
             ["#a", "#b", " #c", "!d", "e", "!f", "f"],
             {"": ["#a", "\\#b", " #c", "\\!d", "e", "!e", "*f", "!!f"]},
             [" #c", "!d", "#b", "f"], [], []),
        # [c-a] is an empty range, so [c-a]3 matches nothing; [a-] is {a, -}; [!]a] is anything but ] and a.
        case("H10", "bracket expressions: ^ negates, ] first is a member, reversed range, - at the end",
             ["a1", "b1", "^1", "]2", "a2", "a3", "b3", "c3", "-4", "a4", "b4", "]5", "a5", "b5"],
             {"": ["[^a]1", "[]]2", "[c-a]3", "[a-]4", "[!]a]5"]},
             ["-4", "]2", "^1", "a4", "b1", "b5"], [], []),
        # a[b, c\, [ and d[] all match nothing; \[ is the name [ and d\[] is the name d[].
        case("H11", "an unclosed [ or a dangling \\ makes the rule match nothing",
             ["a[b", "ab", "c", "c\\", "[", "d[]", "d]"],
             {"": ["a[b", "c\\", "[", "d[]", "\\[", "d\\[]"]},
             ["[", "d[]"], [], []),
        case("H12", "directory-only never matches a file; negated directory-only re-includes directories only",
             ["data", "x/data/y", "z/data"],
             {"": ["data", "!data/"]},
             ["data", "z/data"], [], []),
        # /gen in src's ignore file means src/gen only; src/x/gen is untouched. Root a.tmp: no root rules.
        case("H13", "rules of a subdirectory: unanchored at any depth below it, anchored to it",
             ["a.tmp", "src/a.tmp", "src/x/b.tmp", "src/gen/c", "src/x/gen/d", "gen/e"],
             {"src": ["*.tmp", "/gen"]},
             ["src/a.tmp", "src/gen/c", "src/x/b.tmp"], ["src/gen"], []),
        # ?.md needs exactly 4 characters, so .md (3) does not match.
        case("H14", "* matches a leading dot; ? is exactly one character; case-sensitive",
             [".env", "a.env", "ab.md", "b.md", ".md", "readme", "README"],
             {"": ["*.env", "?.md", "README"]},
             [".env", "README", "a.env", "b.md"], [], []),
        # Paths a, v and v/w are also directories -> invalid, but still directories; v/ excludes v.
        case("H15", "invalid paths: empty, . and .. segments, slashes, paths that are directories, duplicates",
             ["a/b", "a", "a/b", "./x", "x/.", "y/../z", "", "/r", "s/", "t//u", "v", "v/w/q", "v/w"],
             {"": ["v/"]},
             ["v/w/q"], ["v"], ["", "./x", "/r", "a", "s/", "t//u", "v", "v/w", "x/.", "y/../z"]),
        # *** is a whole segment of stars -> globstar; q**r is just q*r (one segment).
        case("H16", "*** is a globstar; ** inside a segment is a plain *",
             ["x", "d/e/x", "p/qr", "p/qzzr", "p/q/r", "p/qq/zr"],
             {"": ["***/x", "p/q**r"]},
             ["d/e/x", "p/qr", "p/qzzr", "x"], [], []),
        # a/x/b/y matches a/**/b/** (the last ** takes y), a/x/b and a/b do not (nothing left for the last **).
        case("H17", "globstars around a middle segment; the last globstar needs one segment",
             ["a/b/c", "a/b/keep", "a/x/b/y/z", "a/q/b2"],
             {"": ["a/**/b/**", "!a/b/keep"]},
             ["a/b/c", "a/x/b/y/z"], ["a/x/b/y"], []),
        # x's own ignore file does not apply to x; f is a file and nowhere is not a directory, so their files apply
        # to nothing.
        case("H18", "an ignore file applies only below its directory; keys that are not directories do nothing",
             ["f", "x/a", "x/y/b"],
             {"x": ["*"], "f": ["*"], "nowhere": ["*"], "": ["!*"]},
             ["x/a", "x/y/b"], ["x/y"], []),
        case("H19", "ignored_dirs lists only the topmost excluded directories",
             ["a/b/c/f", "b/c/d/g", "b/h"],
             {"": ["a/", "b/c/", "b/c/d/"]},
             ["a/b/c/f", "b/c/d/g"], ["a", "b/c"], []),
        case("H20", "re-including a directory, then excluding inside it (the /* !/foo idiom)",
             ["x", "y/z", "foo/a", "foo/bar/b", "foo/baz/c"],
             {"": ["/*", "!/foo", "/foo/*", "!/foo/bar"]},
             ["foo/a", "foo/baz/c", "x", "y/z"], ["foo/baz", "y"], []),
        # "!" and "/" become empty and are skipped; "!//x" and "!x//" have an empty segment and match nothing.
        case("H21", "lines that become empty; empty pattern segments match nothing",
             ["x", "y"],
             {"": ["*", "!", "/", "!//x", "!x//"]},
             ["x", "y"], [], []),
        # [\]]x is the set {]} then x; [\!]y is the set {!} then y (the ! is escaped, so not a negation).
        case("H22", "escapes outside and inside bracket expressions",
             ["*", "a", "]x", "\\x", "a?", "ab", "!y", "\\y"],
             {"": ["\\*", "[\\]]x", "a\\?", "[\\!]y"]},
             ["!y", "*", "]x", "a?"], [], []),
        case("H23", "leading / and **/ in a subdirectory's ignore file are relative to that subdirectory",
             ["lib/a.c", "lib/sub/b.c", "a.c", "lib/x/c.h", "lib/y/x/d.h", "x/e.h"],
             {"lib": ["/*.c", "**/x/*.h"]},
             ["lib/a.c", "lib/x/c.h", "lib/y/x/d.h"], [], []),
        # a/keep: a's ignore file says keep/ -> excluded although the root says !keep/.
        # keep: root k*/ then !keep/ -> not excluded. kx and a/kx: k*/ -> excluded.
        case("H24", "deeper ignore file decides for directories too",
             ["a/keep/1", "keep/2", "kx/3", "a/kx/4"],
             {"": ["k*/", "!keep/"], "a": ["keep/"]},
             ["a/keep/1", "a/kx/4", "kx/3"], ["a/keep", "a/kx", "kx"], []),
        # é (233) is inside [à-ÿ] (224..255); É (201) is not.
        case("H25", "characters are code points; ranges compare code points",
             ["café", "cafe", "cafés", "éx", "Éx"],
             {"": ["caf?", "[à-ÿ]x"]},
             ["cafe", "café", "éx"], [], []),
        # Unanchored ** is a plain *: every name. !**/ re-includes every directory, so none is excluded.
        case("H26", "unanchored ** is a plain *; all files ignored but no directory excluded",
             ["a/b", "c", "d/e/f"],
             {"": ["**", "!**/"]},
             ["a/b", "c", "d/e/f"], [], []),
        case("H27", "case-sensitive directory names; duplicates reported once",
             ["Build/x", "build/y", "build/y"],
             {"": ["build/"]},
             ["build/y"], ["build"], []),
        # "dir/  " -> dir/ (directory-only dir); "dir\\ /" -> directory-only name "dir " (escaped space kept).
        case("H28", "trailing spaces before and after a trailing slash",
             ["dir/a", "dir /b", "x/dir"],
             {"": ["dir/  ", "dir\\ /"]},
             ["dir /b", "dir/a"], ["dir", "dir "], []),
    ]


# ── Generated cases ─────────────────────────────────────────────────────────
def dirs_of(files):
    out = set()
    for f in files:
        if f == "" or f.startswith("/"):
            continue
        p = f.split("/")
        for k in range(1, len(p)):
            out.add("/".join(p[:k]))
    return sorted(out)


GEN_DIRS = ["a", "b", "src", "lib", "build", "Build", "docs", "keep", "out", "x y", ".cache", "logs", "sub"]
GEN_LEAVES = ["a", "b", "ab", "ba", "a.txt", "b.txt", "a.log", "main.o", "keep.txt", "build", ".env", "x y", "foo ",
              "#x", "!x", "[a]", "a*", "a\\b", "README", "readme", "aa", "c", "-", "]", "^"]
GEN_BAD = ["", "/", "a//b", "/a", "a/", "a/./b", "./a", "a/..", "..", ".", "src//x", "b/../c"]
GEN_TEMPLATES = [
    "{n}", "{n}", "/{n}", "{n}/", "/{n}/", "!{n}", "!{n}/", "!/{n}", "{d}/{n}", "/{d}/{n}", "{d}/*", "{d}/**",
    "{d}/**/", "!{d}/**", "**/{n}", "**/{d}/{n}", "{d}/**/{n}", "*.txt", "*.log", "!*.txt", "?", "??", "a*", "*a",
    "[ab]*", "[!a]*", "[^a]*", "[]a]", "[a-c]", "[c-a]*", "[a", "a[b", "\\#x", "#x", "\\!x", "!x", "\\[a]",
    "{n}   ", "{n}\\ ", " {n}", "{n}\t", "***/{n}", "{d}/***", "{d}**", "**", "/**", "*", "!*/", "!**/", "{n}\\",
    "{d}//{n}", "**/**", ".*", "*/{n}", "/*/{n}", "!{d}/", "{d}/", "/{d}", "!/{d}/{n}", "{d}/*/", "*/", "[!]]",
    "[a-]", "[\\]]", "{N}", "!{N}", "{d}/{N}", "[A-Z]*", "*[!.]*", "\\{n}", "!!x", "\\\\", "{n}/**/", "**/{d}/",
    "{d}/**/{d2}", "/{d}/**/*.txt", "*.*", "a?", "?.txt", "!?", "{n}  \\ ", "{d}/?*", "{d}/*.txt", "{d}/*.log",
    "!{d}/*.txt", "{d}/**/{n}", "!{d}/**/{n}",
]


def gen_rules(r, files, templates, nfiles, nlines):
    dirs = dirs_of(files)
    names = sorted({seg for f in files for seg in f.split("/") if seg}) or ["a"]
    dnames = sorted({d.split("/")[-1] for d in dirs}) or ["a"]
    rules = {}
    bases = [""] + dirs
    for _ in range(nfiles):
        base = "" if r.chance(1, 2) or len(bases) == 1 else r.pick(bases)
        if r.chance(1, 12):
            base = r.pick(["nowhere", "a/b/c/d", "zz"])
        lines = rules.setdefault(base, [])
        for _ in range(1 + r.below(nlines)):
            n = r.pick(names)
            line = r.pick(templates).replace("{n}", n).replace("{N}", n.swapcase())
            lines.append(line.replace("{d}", r.pick(dnames)).replace("{d2}", r.pick(dnames)))
        if r.chance(1, 5):
            lines.append("")
        if r.chance(1, 6):
            lines.append("# comment")
    return rules


def family_general(seed):
    r = SplitMix(seed)
    files = []
    for _ in range(4 + r.below(10)):
        depth = r.pick([1, 1, 2, 2, 3, 3, 4])
        files.append("/".join([r.pick(GEN_DIRS) for _ in range(depth - 1)] + [r.pick(GEN_LEAVES)]))
    if r.chance(1, 3):
        files.append(r.pick(GEN_BAD))
    if r.chance(1, 4):
        f = r.pick(files)
        if "/" in f:
            files.append(f[:f.rfind("/")])       # a path that is also a directory
    if r.chance(1, 4):
        files.append(r.pick(files))             # duplicate
    return files, gen_rules(r, files, GEN_TEMPLATES, 1 + r.below(3), 5)


PREC_DIRS = ["a", "b", "keep", "build", "logs", "x"]
PREC_LEAVES = ["x.log", "y.txt", "keep.txt", "a", "b", "z.o", "keep", "build"]
PREC_TEMPLATES = [
    "{d}/", "!{d}/", "{d}", "!{d}", "/{d}", "/{d}/", "!/{d}/{n}", "{d}/*", "!{d}/*", "{d}/**", "!{d}/**",
    "!{d}/**/{n}", "**/{d}/", "!**/{d}", "*.log", "!*.log", "!{n}", "{n}", "!*", "*", "!**/{n}", "{d}/{d2}/",
    "!{d}/{d2}", "/{d}/**/{n}", "*/", "!*/", "{d}/**/", "!{d}/{n}", "{d}/{n}", "**/{n}", "/*", "!/{d}",
    "{d}/*.log", "!{d}/*.txt", "/{d}/*.o", "{d}/**/{n}", "!{d}/**/{d2}/", "{d}/{d2}/*",
]


def family_precedence(seed):
    r = SplitMix(seed)
    files = []
    for _ in range(6 + r.below(10)):
        depth = r.pick([1, 2, 2, 3, 3, 4, 4, 5])
        files.append("/".join([r.pick(PREC_DIRS) for _ in range(depth - 1)] + [r.pick(PREC_LEAVES)]))
    files = [f for f in files if f not in dirs_of(files)] if r.chance(3, 4) else files
    rules = gen_rules(r, files, PREC_TEMPLATES, 2 + r.below(3), 5)
    dirs = dirs_of(files)
    if dirs:                                     # always at least one subdirectory ignore file
        sub = r.pick(dirs)
        rules.setdefault(sub, []).extend(r.pick(PREC_TEMPLATES).replace("{n}", r.pick(PREC_LEAVES))
                                         .replace("{d}", r.pick(PREC_DIRS)).replace("{d2}", r.pick(PREC_DIRS))
                                         for _ in range(1 + r.below(3)))
    return files, rules


GLOB_DIRS = ["a", "b", "c"]
GLOB_LEAVES = ["x.log", "y", "keep", "y", "x.log", "a", "b"]
GLOB_TEMPLATES = [
    "**/{n}", "{d}/**", "{d}/**/", "{d}/**/{n}", "**/{d}/**", "/**/{n}", "**/{d}/{n}", "{d}/**/{d2}/**",
    "!{d}/**/{n}", "!**/{d}/", "{d}/***", "***/{n}", "**/**/{n}", "{d}/**/**/{n}", "{d}/*/{n}", "*/{d}/**",
    "{d}/**/*.log", "!{d}/**", "{d}/{d2}/**", "/**", "!/**/", "**", "{d}**", "**{n}", "!{n}", "!keep", "{d}/*",
    "!{d}/{d2}/", "{d}/**/{d2}", "**/{d}/{d2}/", "!**/keep", "{d}/*.log", "!{d}/*/", "{d}/?", "{d}/*/*.log",
    "{d}/[xy]*", "{d}/**/{n}", "{d}/*",
]


def expand(r, line):
    """A path that a GLOB_TEMPLATES rule nearly or exactly matches: globstars become 0-2 directories, star segments
    concrete names; sometimes one extra segment is inserted before the last, or the last is dropped."""
    body = line.lstrip("!").strip("/")
    out = []
    for seg in body.split("/"):
        if seg in ("**", "***"):
            out += [r.pick(GLOB_DIRS) for _ in range(r.pick([0, 0, 1, 2]))]
        elif seg == "*":
            out.append(r.pick(GLOB_DIRS + ["y"]))
        elif "*" in seg or "?" in seg or "[" in seg:
            out.append(r.pick(["x.log", "y", "z.log", "xy"]))
        else:
            out.append(seg)
    if not out:
        out = [r.pick(GLOB_LEAVES)]
    k = r.below(4)
    if k == 0 and len(out) >= 1:
        out.insert(len(out) - 1, r.pick(GLOB_DIRS))         # one segment too many
    elif k == 1 and len(out) >= 2:
        out.pop()                                           # the directory itself
    if out[-1] in GLOB_DIRS or r.chance(1, 3):
        out.append(r.pick(GLOB_LEAVES[:5]))                 # make it a file inside
    return "/".join(out)


def family_globstar(seed):
    """Anchored rules with globstars and stars; most files are built from the rules as exact or near matches."""
    r = SplitMix(seed)
    lines = [r.pick(GLOB_TEMPLATES).replace("{n}", r.pick(GLOB_LEAVES)).replace("{d}", r.pick(GLOB_DIRS))
             .replace("{d2}", r.pick(GLOB_DIRS)) for _ in range(2 + r.below(4))]
    files = [expand(r, line) for line in lines for _ in range(2 + r.below(3))]
    for _ in range(2 + r.below(4)):
        depth = r.pick([1, 2, 2, 3, 4])
        files.append("/".join([r.pick(GLOB_DIRS) for _ in range(depth - 1)] + [r.pick(GLOB_LEAVES)]))
    dirs = dirs_of(files)
    files = [f for f in files if f not in dirs]
    if r.chance(1, 4) and dirs:                              # sometimes the rules live in a subdirectory
        base = r.pick(dirs)
        files = files + [base + "/" + f for f in files[:6]]
        return files, {base: lines}
    return files, {"": lines}


SYN_NAMES = ["#x", "!x", " x", "x ", "x\t", "a\\b", "[a]", "]", "^", "-", "a-b", "*", "?", "é", "É", "x.y",
             ".x", "ab", "b", "a", "Ab", "aB", "]x", "^x", "!", "a b", "x  ", "c", "[", "a[b", "\\", "[a", "x[",
             "[]", "[!]", "[^]", "bx", "zx", "y", "ax"]
SYN_LINES = [
    "\\#x", "#x", "\\!x", "!x", "\\ x", " x", "x\\ ", "x ", "x\\  ", "x\t", "a\\\\b", "a\\b", "\\[a]", "[a]",
    "[[]a]", "[]]", "[]x]", "[!]]x", "[^]]x", "[\\]]x", "[]-a]", "[a-]", "[-a]", "[^a]*", "[!a]*", "[a-c]*",
    "[c-a]*", "[a", "a\\", "*\\", "\\*", "\\?", "?", "??", "?x", "[É-é]", "[à-ÿ]*", "*.*", ".*",
    "*", "!*", "a?b", "a*b", "[[:alpha:]]", "[a-c-e]", "x[", "\\", "\\\\", " ", "\\ ", "!\\ x", "x\\ \\ ", "[!a-b]",
    "[^-]", "[]-]", "[\\-]", "a[]-b]b", "*[!x]", "[x-x]", "\\\\*", "!\\#x", "[!]", "[]", "[^]", "!a*", "!?",
    "[ -!]x", "\\x  ", "x\\\\ ", "!x ", "a[!b-]b", "[z-a]*", "[!c-a]", "[b-a]x", "[y-a]", "x\\ ", "\\ x ",
    "x\\\t", "[a-a]",
]


def literal_readings(line):
    """Names a misreading of this line would match: the raw text, without backslashes, stripped."""
    body = line[1:] if line.startswith("!") else line
    out = []
    for name in (body, body.replace("\\", ""), body.rstrip(), body.strip()):
        if name and name not in (".", "..") and name not in out:
            out.append(name)
    return out


def family_syntax(seed):
    r = SplitMix(seed)
    names = {r.pick(SYN_NAMES) if r.chance(3, 4) else r.pick(["d", "e"]) + "/" + r.pick(SYN_NAMES)
             for _ in range(12 + r.below(14))}
    rules = {"": [r.pick(SYN_LINES) for _ in range(2 + r.below(6))]}
    if r.chance(1, 3):
        rules["d"] = [r.pick(SYN_LINES) for _ in range(1 + r.below(4))]
    for base, lines in sorted(rules.items()):
        for line in lines:
            for name in literal_readings(line):
                if r.chance(2, 3):
                    names.add(name if base == "" else base + "/" + name)
    return sorted(names), rules


def random_cases():
    families = [(family_general, 17000, 40, "random tree and rules"),
                (family_precedence, 27000, 35, "random precedence and exclusion"),
                (family_syntax, 37000, 35, "random pattern syntax"),
                (family_globstar, 47000, 25, "random globstar rules")]
    res = []
    for fam, base, count, title in families:
        for i in range(count):
            f, rl = fam(base + i)
            res.append({"id": f"R{len(res) + 1:03d}", "title": title, "args": [f, rl]})
    return res


def hidden():
    return hand() + random_cases()


# ── Stress cases (built inside the sandbox) ─────────────────────────────────
DIR_POOL = ["s", "l", "p", "c", "u", "t", "d", "a", "m", "w", "k", "v", "e", "r", "z"]
HOT_DIRS = ["build", "cache", "gen", "tmp", "dist", "obj", "local", "vendor1", "node_modules", "coverage"]
EXTS = ["py", "pyc", "c", "o", "h", "txt", "md", "log", "tmp", "bak", "out", "json", "js", "min.js", "csv", "cache",
        "swp", "pyo", "cfg"]
STEMS = ["main", "util", "test", "data", "x", "keep", "important", "notes", "Temp", "temp", "secret", "conf", "f"]
ROOT_LINES = ["# generated", "*.tmp", "*.bak", "!important*.bak", "/dist/", "**/cache/", "build-*/", "*.py[co]",
              "!keep*.pyc", "**/gen/**/*.out", "x[0-9][0-9]9.log", "/vendor*/", "*.sw?", "node_modules/",
              "**/tmp/", "coverage/", "*.o", "!s*/**/*.o", "", "*.min.*", "!*.min.md", "# end"]
SUB_LINES = ["*.log", "!keep*.log", "/local/", "secret*", "*.cache", "obj/", "/*.min.js", "data/**/*.csv", "[Tt]emp*",
             "!*.md", "build/", "/gen/", "*.json", "!conf*.json", "**/x1*", "notes[!0-9]*"]


def stress_big_tree(case):
    """~80 000 files about 28 levels deep on average, ~1 900 ignore files; few directories are excluded, so every
    file is evaluated. Re-evaluating every ancestor directory for every file is ~30x the work."""
    r = SplitMix(case["seed"])
    dirs, seen = [], set()
    while len(dirs) < case["dirs"]:
        if not dirs or r.chance(1, 150):
            parent, depth = "", 0
        else:
            if r.chance(4, 5):
                parent, depth = dirs[len(dirs) - 1 - r.below(min(len(dirs), 12))]
            else:
                parent, depth = dirs[r.below(len(dirs))]
            if depth >= case["max_depth"]:
                parent, depth = dirs[r.below(len(dirs))]
                if depth >= case["max_depth"]:
                    parent, depth = "", 0
        name = r.pick(DIR_POOL) + str(r.below(30))
        path = name if not parent else parent + "/" + name
        if path not in seen:
            seen.add(path)
            dirs.append((path, depth + 1))
    hot = [dirs[r.below(len(dirs))][0] + "/" + r.pick(HOT_DIRS) for _ in range(case["hot_dirs"])]
    files = []
    for k in range(case["files"]):
        if r.chance(1, 25):
            d = r.pick(hot)
        else:
            d = max(dirs[r.below(len(dirs))], dirs[r.below(len(dirs))], key=lambda x: x[1])[0]
        files.append(f"{d}/{r.pick(STEMS)}{k}.{r.pick(EXTS)}")
    rules = {"": list(ROOT_LINES)}
    for _ in range(case["rule_files"]):
        rules[dirs[r.below(len(dirs))][0]] = [r.pick(SUB_LINES) for _ in range(2 + r.below(3))]
    return [files, rules]


def stress_deep_chains(case):
    """Directory chains thousands of levels deep with a file every few levels: recursion one call per level
    overflows, and per-file work that grows with depth x depth does not finish."""
    r = SplitMix(case["seed"])
    files = []
    rules = {"": ["*.tmp", "!keep*.tmp", "/c0/n/n/x/", "q/n/b/", "/c1/m/*.log", "[0-9]*.bak", "*a*a*a*a*b",
                  "!f7*", "end/", "z/"]}
    for c, depth in enumerate(case["depths"]):
        path = f"c{c}"
        for lvl in range(depth):
            path = path + "/" + ("n" if r.chance(15, 16) else r.pick(["m", "q", "b"]))
            if lvl % case["file_every"] == 0:
                files.append(f"{path}/f{r.below(10)}{r.pick(['.tmp', '.log', '.bak', '.c', ''])}")
            if lvl % case["rule_every"] == case["rule_every"] - 1:
                rules[path] = [r.pick(["*.c", "!f1*", "/n/q/", "f[2-4]*", "!*.log", "n/end/"]) for _ in range(3)]
        files.append(f"{path}/z/last.c")
        files.append(f"{path}/end/last.c")
        files.append(f"{path}/f.c")
    return [files, rules]


def stress_pathological(case):
    """Many-star rules against long names and many-globstar rules against deep paths: a backtracking matcher
    (including a plain translation to re) takes exponential time; a linear or DP matcher is instant."""
    r = SplitMix(case["seed"])
    files = []
    rules = {"": ["*a*a*a*a*a*a*a*b", "*a?a*a*a*a*a*[!a]b", "a*a*a*a*a*a*a*a*c*", "*a*a*a*a*a*a*a*a*a*a*z",
                  "**/*a*a*a*a*a*a*b/**", "!*aaaa*aaaa*aaaa*aaaa*d", "*[ab]*[ab]*[ab]*[ab]*[ab]*[ab]*e",
                  "**/a/**/a/**/a/**/a/**/a/**/b", "a/**/a/**/a/**/a/**/a/**/a/**/c",
                  "**/a*/**/a*/**/a*/**/a*/**/a*/**/x", "*.tmp"]}
    for k in range(case["long_names"]):
        body = "".join("a" if r.chance(15, 16) else r.pick(["b", "c", "d"]) for _ in range(40 + r.below(160)))
        files.append(f"d{r.below(20)}/{body}{r.pick(['', 'x', 'yy', 'c', 'q'])}")
    for k in range(case["deep_paths"]):
        segs = ["a" if r.chance(7, 8) else r.pick(["b", "ab", "aa"]) for _ in range(20 + r.below(40))]
        files.append("/".join(segs) + f"/leaf{k}")
    for k in range(case["plain"]):
        files.append(f"p{r.below(50)}/f{k}.{r.pick(['tmp', 'txt', 'c'])}")
    return [files, rules]


def stress():
    return [
        {"id": "S1", "title": "60 000 files ~28 levels deep under ~1 600 ignore files", "kind": "big_tree", "seed": 1,
         "dirs": 4000, "files": 60000, "rule_files": 2000, "max_depth": 70, "hot_dirs": 300},
        {"id": "S2", "title": "directory chains 2 900, 1 600 and 1 100 levels deep", "kind": "deep_chains", "seed": 2,
         "depths": [2900, 1600, 1100], "rule_every": 400, "file_every": 4},
        {"id": "S3", "title": "many-star and many-globstar rules against long names and deep paths",
         "kind": "pathological", "seed": 3, "long_names": 700, "deep_paths": 300, "plain": 5000},
    ]


def stress_args(case):
    build = {"big_tree": stress_big_tree, "deep_chains": stress_deep_chains, "pathological": stress_pathological}
    return build[case["kind"]](case)
