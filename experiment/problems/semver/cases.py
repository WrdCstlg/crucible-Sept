"""Cases for Problem 7. Stdlib only (copied into the sandbox like every cases.py).

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


POOL = ["0.0.3", "0.0.4", "0.1.0", "0.2.3", "0.2.9", "0.3.0", "1.0.0", "1.2.0", "1.2.3-beta.1", "1.2.3-beta.7",
        "1.2.3", "1.2.4-alpha", "1.2.9", "1.3.0-rc.1", "1.3.0", "1.9.9", "2.0.0-0", "2.0.0", "2.1.0", "3.0.0"]


def ok(**packages):
    return {"ok": True, "packages": packages}


FAIL = {"ok": False, "packages": {}}


def probe(cid, title, rng, versions, expected):
    """One package 'a' with the given versions; the root range picks the highest match (or nothing)."""
    return {"id": cid, "title": title, "args": [{"a": {v: {} for v in versions}}, {"a": rng}],
            "spec_expected": ok(a=expected) if expected else FAIL}


def public():
    reg2 = {"a": {"1.0.0": {}, "1.1.0-beta.2": {}, "1.1.0-beta.10": {}}}
    return [
        {"id": "P1", "title": "caret on 0.x", "args": [{"a": {"0.2.1": {}, "0.2.9": {}, "0.3.0": {}}}, {"a": "^0.2.1"}],
         "spec_expected": ok(a="0.2.9")},
        {"id": "P2a", "title": "prerelease excluded", "args": [reg2, {"a": ">=1.0.0"}], "spec_expected": ok(a="1.0.0")},
        {"id": "P2b", "title": "prerelease opt-in", "args": [reg2, {"a": ">=1.1.0-beta.1"}],
         "spec_expected": ok(a="1.1.0-beta.10")},
        {"id": "P3", "title": "backtracking", "args": [
            {"app": {"2.0.0": {"lib": "^2.0.0"}, "1.0.0": {"lib": "^1.0.0"}},
             "lib": {"1.4.0": {}, "2.1.0": {}},
             "util": {"1.0.0": {"lib": "<2"}}},
            {"app": "*", "util": "1.x"}],
         "spec_expected": ok(app="1.0.0", lib="1.4.0", util="1.0.0")},
        {"id": "P4", "title": "space after operator is invalid", "args": [{"a": {"1.0.0": {}}}, {"a": ">= 1.0.0"}],
         "spec_expected": FAIL},
    ]


def hand():
    cases = [
        probe("H01", "caret 0.2.3", "^0.2.3", POOL, "0.2.9"),
        probe("H02", "caret 0.0.3", "^0.0.3", POOL, "0.0.3"),
        probe("H03", "caret 0.0 (all zero: bump last present)", "^0.0", POOL, "0.0.4"),
        probe("H04", "caret 0", "^0", POOL, "0.3.0"),
        probe("H05", "caret 1.2.3 excludes prereleases", "^1.2.3", POOL, "1.9.9"),
        probe("H06", "tilde full", "~1.2.3", POOL, "1.2.9"),
        probe("H07", "tilde major only", "~1", POOL, "1.9.9"),
        probe("H08", "greater-than partial means >=next", ">1.2", ["1.2.0", "1.2.9"], None),
        probe("H09", "<= partial means <next", "<=1.2", ["1.2.9", "1.3.0"], "1.2.9"),
        probe("H10", "< partial means <low", "<1.2", ["1.1.9", "1.2.0"], "1.1.9"),
        probe("H11", "bare partial", "1.2", POOL, "1.2.9"),
        probe("H12", "capital X wildcard", "1.2.X", POOL, "1.2.9"),
        probe("H13", "component after wildcard is invalid", "1.x.3", POOL, None),
        probe("H14", "one invalid set invalidates the whole range", ">=1.0.0 || ~>1.2", POOL, None),
        probe("H15", "v prefix is invalid", "v1.0.0", POOL, None),
        probe("H16", "hyphen with partial upper bound", "1.0.0 - 1.2", POOL, "1.2.9"),
        probe("H17", "hyphen with prerelease lower bound",
              "1.2.3-beta.1 - 1.2.3", ["1.2.3-beta.1", "1.2.3-beta.7", "1.2.4-alpha", "1.2.0"], "1.2.3-beta.7"),
        probe("H18", "prerelease opt-in is per M.m.p", ">=1.2.3-beta.1",
              ["1.2.3-beta.1", "1.2.3-beta.7", "1.2.4-alpha"], "1.2.3-beta.7"),
        probe("H19", "< full version excludes its prereleases", "<2.0.0", ["1.9.9", "2.0.0-0"], "1.9.9"),
        probe("H20", "< prerelease admits a lower prerelease", "<2.0.0-1", ["1.9.9", "2.0.0-0"], "2.0.0-0"),
        probe("H21", "numeric identifiers sort below alphanumeric", ">=1.0.0-0",
              ["1.0.0-alpha", "1.0.0-1", "1.0.0-10", "1.0.0-9"], "1.0.0-alpha"),
        probe("H22", "more identifiers is greater; numeric below alpha", ">=1.0.0-a",
              ["1.0.0-a", "1.0.0-a.1", "1.0.0-a.b"], "1.0.0-a.b"),
        probe("H23", "build ignored; tie broken by greater string", "=1.0.0",
              ["1.0.0+b", "1.0.0+a", "1.0.0", "0.9.0"], "1.0.0+b"),
        probe("H24", "invalid registry versions ignored", "*",
              ["01.0.0", "1.0", "1.0.0-01", "1.0.0-", "1.0.0+", "0.5.0", "0.6.0+build.01",
               "1.0.0-beta+exp.sha.5114f85", "1.2.3.4", "\uff12.0.0", "1.0.0-be_ta"], "0.6.0+build.01"),
        probe("H25", "tab is not whitespace", "1.0.0\t|| 2.0.0", POOL, None),
        probe("H26", "empty range means *", "", ["1.0.0", "2.0.0-rc.1"], "1.0.0"),
        probe("H27", ">* matches nothing but another set can", ">* || 1.0.0", POOL, "1.0.0"),
        probe("H28", "<* matches nothing", "<*", POOL, None),
        probe("H29", "hyphen with wildcard lower bound", "* - 1.2.3", POOL, "1.2.3"),
        probe("H30", "operator on a hyphen endpoint is invalid", ">=1.0.0 - 2.0.0", POOL, None),
        probe("H31", "stray dash token is invalid", "1.0.0 -2.0.0", POOL, None),
        probe("H32", "tilde with prerelease", "~1.2.3-beta.1",
              ["1.2.3-beta.1", "1.2.3-rc.1", "1.2.4-alpha"], "1.2.3-rc.1"),
        probe("H33", "leading zero in a range prerelease is invalid", "1.2.3-beta.01", POOL, None),
        probe("H34", "build metadata in a range is invalid", "1.2.3+b", POOL, None),
        probe("H35", "union of sets", ">=0.1.0 <0.3.0 || ^2", POOL, "2.1.0"),
        probe("H36", "=partial", "=1.2", POOL, "1.2.9"),
        probe("H37", "exact prerelease", "1.2.3-beta.7", POOL, "1.2.3-beta.7"),
        probe("H38", "caret with prerelease admits same M.m.p only", "^1.2.3-beta.1",
              ["1.2.3-beta.7", "1.3.0-rc.1", "1.2.2"], "1.2.3-beta.7"),
        probe("H39", "> full version excludes other prereleases", ">1.2.3", ["1.2.3", "1.2.4-alpha"], None),
        probe("H40", "x alone excludes prereleases", "x", ["0.1.0", "0.2.0-rc"], "0.1.0"),
        probe("H41", "four components is invalid", "1.2.3.4", POOL, None),
        probe("H42", "star wildcards", "1.*.*", POOL, "1.9.9"),
        probe("H43", "caret 0.0.x", "^0.0.x", POOL, "0.0.4"),
        probe("H44", "caret 0.0.0", "^0.0.0", ["0.0.0", "0.0.1"], "0.0.0"),
        probe("H45", "ASCII order: uppercase sorts first", ">=1.2.3-Beta", ["1.2.3-Beta", "1.2.3-alpha"],
              "1.2.3-alpha"),
        probe("H46", "<= prerelease", "<=1.2.3-beta.7", ["1.2.3-beta.1", "1.2.3-beta.7", "1.2.3-beta.8", "1.2.2"],
              "1.2.3-beta.7"),
        probe("H47", "single pipe is invalid", "1.0.0 | 2.0.0", POOL, None),
        probe("H48", "== is invalid", "==1.0.0", POOL, None),
        probe("H49", "numeric prerelease ids compare numerically", ">=1.0.0-rc.1",
              ["1.0.0-rc.2", "1.0.0-rc.11", "1.0.0-rc.9"], "1.0.0-rc.11"),
        probe("H50", "space after tilde is invalid", "~ 1.2", POOL, None),
        probe("H51", "tie on prerelease broken by greater string", "=1.0.0-rc.1",
              ["1.0.0-rc.1+a", "1.0.0-rc.1+z", "1.0.0-rc.1"], "1.0.0-rc.1+z"),
    ]
    cases += [
        {"id": "H60", "title": "self-dependency forces backtrack",
         "args": [{"a": {"2.0.0": {"a": "^1"}, "1.5.0": {"a": "^1"}}}, {"a": "*"}], "spec_expected": ok(a="1.5.0")},
        {"id": "H61", "title": "smallest name is resolved first",
         "args": [{"z": {"2.0.0": {"a": "1"}, "1.0.0": {}}, "a": {"2.0.0": {}, "1.0.0": {}}}, {"z": "*", "a": "*"}],
         "spec_expected": ok(a="2.0.0", z="1.0.0")},
        {"id": "H62", "title": "chronological backtracking two levels deep",
         "args": [{"a": {"2.0.0": {"b": "*", "c": "*"}, "1.0.0": {}},
                   "b": {"2.0.0": {"d": "2"}, "1.0.0": {"d": "1"}},
                   "c": {"1.0.0": {"d": "3"}},
                   "d": {"1.0.0": {}, "2.0.0": {}, "3.0.0": {}}}, {"a": "*"}],
         "spec_expected": ok(a="1.0.0")},
        {"id": "H63", "title": "missing package has no candidates",
         "args": [{"a": {"1.0.0": {"ghost": "*"}, "0.9.0": {}}}, {"a": "*"}], "spec_expected": ok(a="0.9.0")},
        {"id": "H64", "title": "new requirement re-checks an already selected package",
         "args": [{"a": {"2.0.0": {}, "1.0.0": {}}, "b": {"1.0.0": {"a": "<2"}}}, {"a": "*", "b": "*"}],
         "spec_expected": ok(a="1.0.0", b="1.0.0")},
        {"id": "H65", "title": "empty root", "args": [{"a": {"1.0.0": {}}}, {}], "spec_expected": ok()},
        {"id": "H66", "title": "invalid dependency range blocks", "args": [{"a": {"1.0.0": {"b": "~>1"}},
                                                                        "b": {"1.0.0": {}}}, {"a": "*"}],
         "spec_expected": FAIL},
        {"id": "H67", "title": "unrequired packages are not selected",
         "args": [{"a": {"1.0.0": {}}, "b": {"1.0.0": {}}}, {"a": "1"}], "spec_expected": ok(a="1.0.0")},
        {"id": "H68", "title": "equal-precedence candidates tried by string order",
         "args": [{"a": {"1.0.0+a": {"c": "1"}, "1.0.0+b": {"c": "2"}}, "c": {"1.0.0": {}}}, {"a": "1.0.0"}],
         "spec_expected": ok(a="1.0.0+a", c="1.0.0")},
        {"id": "H69", "title": "empty registry", "args": [{}, {"a": "*"}], "spec_expected": FAIL},
        {"id": "H70", "title": "backtracking drops packages selected deeper",
         "args": [{"a": {"2.0.0": {"b": "1", "x": "*"}, "1.0.0": {"b": "2"}},
                   "b": {"1.0.0": {"c": "9"}, "2.0.0": {}},
                   "c": {"1.0.0": {}}, "x": {"1.0.0": {}}}, {"a": "*"}],
         "spec_expected": ok(a="1.0.0", b="2.0.0")},
        {"id": "H71", "title": "smallest name first, not dependency order",
         "args": [{"c": {"1.0.0": {"z": "*", "b": "*"}}, "z": {"2.0.0": {"b": "1"}, "1.0.0": {}},
                   "b": {"2.0.0": {}, "1.0.0": {}}}, {"c": "*"}],
         "spec_expected": ok(b="2.0.0", c="1.0.0", z="1.0.0")},
    ]
    return cases


# ── Random cases ────────────────────────────────────────────────────────────
VERSION_POOL = ["0.0.1", "0.0.2", "0.1.0", "0.1.5", "0.2.0", "1.0.0", "1.0.1", "1.1.0", "1.2.0", "1.2.3-alpha",
                "1.2.3-beta.2", "1.2.3-beta.10", "1.2.3", "1.5.0", "2.0.0-rc.1", "2.0.0", "2.1.3", "2.2.0",
                "3.0.0", "1.0.0+build", "01.2.0", "1.2", "1.0.0-x.7.z.92"]
WILD = ["x", "X", "*"]


def rand_partial(r, allow_pre=True):
    k = r.below(4)
    comps = [str(r.below(3)) for _ in range(k)]
    if k < 3 and r.chance(1, 2):
        comps += [r.pick(WILD)] * r.below(3 - k + 1)
    text = ".".join(comps) if comps else r.pick(WILD)
    if k == 3 and allow_pre and r.chance(1, 4):
        text += "-" + r.pick(["alpha", "beta.2", "rc.1", "0", "beta.10"])
    return text


INVALID_TOKENS = ["==1.0.0", ">= 1", "v1.2.3", "1.x.3", "01.0.0", "1.2.3+b", "~>1.2", "1.2-beta", "-", "1.2.3.4",
                  "1.2.3-01", "=>1.0.0"]


def rand_set(r):
    if r.chance(1, 6):
        return f"{rand_partial(r)} - {rand_partial(r)}"
    items = []
    for _ in range(1 + r.below(2)):
        if r.chance(1, 25):
            items.append(r.pick(INVALID_TOKENS))
        else:
            items.append(r.pick(["", "", "=", ">=", ">", "<", "<=", "~", "^", "^"]) + rand_partial(r))
    return " ".join(items)


def rand_range(r):
    sets = [rand_set(r) for _ in range(1 + (r.below(4) == 0))]
    return " || ".join(sets)


LOOSE = ["*", "^1", "^0.1", ">=1", "<2", "1.x", "~1.2", ">=0.1.0 <2.0.0", "^2", "0.x || 2.x", ">=1.2.3-alpha",
         "1.0.0 - 2", "^1.2.3-beta.2", "<=1.2", ">0.1", "", "x"]


def dep_range(r):
    return rand_range(r) if r.chance(1, 3) else r.pick(LOOSE)


def rand_registry(r, names):
    reg = {}
    for n in names:
        versions = []
        for _ in range(5 + r.below(6)):
            v = r.pick(VERSION_POOL)
            if v not in versions:
                versions.append(v)
        table = {}
        for v in versions:
            deps = {}
            for _ in range(r.below(3)):
                target = r.pick(names)
                if target == n and not r.chance(1, 5):
                    continue
                deps[target] = dep_range(r)
            table[v] = deps
        reg[n] = table
    if r.chance(1, 10):
        reg.pop(r.pick(names), None)
    return reg


def random_cases():
    out = []
    for i in range(40):
        r = SplitMix(7000 + i)
        versions = []
        for _ in range(8 + r.below(10)):
            v = r.pick(VERSION_POOL)
            if v not in versions:
                versions.append(v)
        out.append({"id": f"RP{i + 1:02d}", "title": "random range probe",
                    "args": [{"a": {v: {} for v in versions}}, {"a": rand_range(r)}]})
    for i in range(70):
        r = SplitMix(9100 + i)
        names = ["a", "b", "c", "d", "e", "f"][: 3 + r.below(4)]
        reg = rand_registry(r, names)
        root = {}
        for _ in range(1 + r.below(3)):
            root[r.pick(names)] = rand_range(r) if r.chance(1, 5) else r.pick(LOOSE)
        out.append({"id": f"RR{i + 1:02d}", "title": "random registry", "args": [reg, root]})
    return out


def hidden():
    return hand() + random_cases()


def stress():
    return []


def stress_args(case):
    raise ValueError("Problem 7 has no stress cases")
