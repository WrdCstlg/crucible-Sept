import string

ASCII_DIGITS = set("0123456789")
IDENT_CHARS = set(string.ascii_letters + string.digits + "-")
OPERATORS = (">=", "<=", ">", "<", "=", "~", "^")


def is_valid_int(s: str) -> bool:
    if not s or not all(c in ASCII_DIGITS for c in s):
        return False
    if len(s) > 1 and s.startswith("0"):
        return False
    return True


def is_wildcard(s: str) -> bool:
    return s in ("*", "x", "X")


class Version:
    def __init__(self, major, minor, patch, prerelease_str=None, build_str=None, raw=None):
        self.major = major
        self.minor = minor
        self.patch = patch
        self.prerelease_str = prerelease_str
        self.build_str = build_str
        self.raw = raw if raw is not None else self._to_str()

        if prerelease_str is None:
            pre_key = (1, ())
        else:
            parts = prerelease_str.split(".")
            parsed_ids = []
            for p in parts:
                if all(c in ASCII_DIGITS for c in p):
                    parsed_ids.append((0, int(p)))
                else:
                    parsed_ids.append((1, p))
            pre_key = (0, tuple(parsed_ids))

        self.prec_key = (major, minor, patch, pre_key[0], pre_key[1])

    def _to_str(self):
        s = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease_str is not None:
            s += f"-{self.prerelease_str}"
        if self.build_str is not None:
            s += f"+{self.build_str}"
        return s


def parse_registry_version(s: str):
    if not isinstance(s, str) or not s:
        return None

    plus_parts = s.split("+", 1)
    if len(plus_parts) == 2:
        rest, build_str = plus_parts
        if not build_str:
            return None
        b_parts = build_str.split(".")
        for bp in b_parts:
            if not bp or not all(c in IDENT_CHARS for c in bp):
                return None
    else:
        rest = s
        build_str = None

    dash_parts = rest.split("-", 1)
    if len(dash_parts) == 2:
        rest, pre_str = dash_parts
        if not pre_str:
            return None
        p_parts = pre_str.split(".")
        for pp in p_parts:
            if not pp or not all(c in IDENT_CHARS for c in pp):
                return None
            if all(c in ASCII_DIGITS for c in pp):
                if len(pp) > 1 and pp.startswith("0"):
                    return None
    else:
        pre_str = None

    dot_parts = rest.split(".")
    if len(dot_parts) != 3:
        return None
    for dp in dot_parts:
        if not is_valid_int(dp):
            return None

    return Version(int(dot_parts[0]), int(dot_parts[1]), int(dot_parts[2]), pre_str, build_str, raw=s)


class PartialVersion:
    def __init__(self, k, components, prerelease_str=None):
        self.k = k
        self.components = components
        self.prerelease_str = prerelease_str

    @property
    def low(self):
        if self.k == 1:
            return Version(self.components[0], 0, 0, None)
        elif self.k == 2:
            return Version(self.components[0], self.components[1], 0, None)
        elif self.k == 3:
            return Version(self.components[0], self.components[1], self.components[2], self.prerelease_str)
        return None

    @property
    def next(self):
        if self.k == 1:
            return Version(self.components[0] + 1, 0, 0, None)
        elif self.k == 2:
            return Version(self.components[0], self.components[1] + 1, 0, None)
        return None

    @property
    def U(self):
        idx = None
        for i in range(self.k):
            if self.components[i] > 0:
                idx = i
                break
        if idx is None:
            idx = self.k - 1

        u = [0, 0, 0]
        for i in range(idx):
            u[i] = self.components[i]
        u[idx] = self.components[idx] + 1
        return Version(u[0], u[1], u[2], None)


def parse_partial_version(s: str):
    if not s or "+" in s:
        return None

    if "-" in s:
        main_part, pre_str = s.split("-", 1)
        if not pre_str:
            return None
        p_parts = pre_str.split(".")
        for pp in p_parts:
            if not pp or not all(c in IDENT_CHARS for c in pp):
                return None
            if all(c in ASCII_DIGITS for c in pp):
                if len(pp) > 1 and pp.startswith("0"):
                    return None
    else:
        main_part = s
        pre_str = None

    if main_part in ("*", "x", "X"):
        if pre_str is not None:
            return None
        return PartialVersion(0, [], None)

    dot_parts = main_part.split(".")
    if len(dot_parts) == 1:
        if not is_valid_int(dot_parts[0]) or pre_str is not None:
            return None
        return PartialVersion(1, [int(dot_parts[0])], None)
    elif len(dot_parts) == 2:
        if not is_valid_int(dot_parts[0]) or pre_str is not None:
            return None
        if is_valid_int(dot_parts[1]):
            return PartialVersion(2, [int(dot_parts[0]), int(dot_parts[1])], None)
        elif is_wildcard(dot_parts[1]):
            return PartialVersion(1, [int(dot_parts[0])], None)
        else:
            return None
    elif len(dot_parts) == 3:
        if not is_valid_int(dot_parts[0]):
            return None
        if is_valid_int(dot_parts[1]):
            if is_valid_int(dot_parts[2]):
                return PartialVersion(3, [int(dot_parts[0]), int(dot_parts[1]), int(dot_parts[2])], pre_str)
            elif is_wildcard(dot_parts[2]):
                if pre_str is not None:
                    return None
                return PartialVersion(2, [int(dot_parts[0]), int(dot_parts[1])], None)
            else:
                return None
        elif is_wildcard(dot_parts[1]):
            if is_wildcard(dot_parts[2]):
                if pre_str is not None:
                    return None
                return PartialVersion(1, [int(dot_parts[0])], None)
            else:
                return None
        else:
            return None
    else:
        return None


class ComparatorSet:
    def __init__(self, comparators=None, unsatisfiable=False):
        self.comparators = comparators if comparators is not None else []
        self.unsatisfiable = unsatisfiable

    def matches(self, cand: Version) -> bool:
        if self.unsatisfiable:
            return False

        for op, ver in self.comparators:
            if op == "=":
                if cand.prec_key != ver.prec_key:
                    return False
            elif op == ">=":
                if cand.prec_key < ver.prec_key:
                    return False
            elif op == "<=":
                if cand.prec_key > ver.prec_key:
                    return False
            elif op == ">":
                if cand.prec_key <= ver.prec_key:
                    return False
            elif op == "<":
                if cand.prec_key >= ver.prec_key:
                    return False

        if cand.prerelease_str is not None:
            cand_mmp = (cand.major, cand.minor, cand.patch)
            has_matching_pre = False
            for _, ver in self.comparators:
                if ver.prerelease_str is not None and (ver.major, ver.minor, ver.patch) == cand_mmp:
                    has_matching_pre = True
                    break
            if not has_matching_pre:
                return False

        return True


def parse_comparator_set(set_str: str):
    s = set_str.strip(" ")
    if not s:
        return ComparatorSet(comparators=[], unsatisfiable=False)

    tokens = [t for t in s.split(" ") if t != ""]

    if len(tokens) == 3 and tokens[1] == "-":
        t0, t2 = tokens[0], tokens[2]
        for op in OPERATORS:
            if t0.startswith(op) or t2.startswith(op):
                return None

        pv_a = parse_partial_version(t0)
        pv_b = parse_partial_version(t2)
        if pv_a is None or pv_b is None:
            return None

        comps = []
        if pv_a.k >= 1:
            comps.append((">=", pv_a.low))

        if pv_b.k == 3:
            comps.append(("<=", pv_b.low))
        elif pv_b.k in (1, 2):
            comps.append(("<", pv_b.next))

        return ComparatorSet(comparators=comps, unsatisfiable=False)

    if "-" in tokens:
        return None

    comps = []
    unsatisfiable = False

    for token in tokens:
        if token.startswith((">=", "<=")):
            matched_op = token[:2]
            rem = token[2:]
        elif token.startswith((">", "<", "=", "~", "^")):
            matched_op = token[:1]
            rem = token[1:]
        else:
            matched_op = ""
            rem = token

        if not rem:
            return None

        pv = parse_partial_version(rem)
        if pv is None:
            return None

        k = pv.k
        if matched_op in ("", "="):
            if k == 0:
                pass
            elif k in (1, 2):
                comps.append((">=", pv.low))
                comps.append(("<", pv.next))
            elif k == 3:
                comps.append(("=", pv.low))
        elif matched_op == ">=":
            if k == 0:
                pass
            elif k in (1, 2, 3):
                comps.append((">=", pv.low))
        elif matched_op == ">":
            if k == 0:
                unsatisfiable = True
            elif k in (1, 2):
                comps.append((">=", pv.next))
            elif k == 3:
                comps.append((">", pv.low))
        elif matched_op == "<":
            if k == 0:
                unsatisfiable = True
            elif k in (1, 2, 3):
                comps.append(("<", pv.low))
        elif matched_op == "<=":
            if k == 0:
                pass
            elif k in (1, 2):
                comps.append(("<", pv.next))
            elif k == 3:
                comps.append(("<=", pv.low))
        elif matched_op == "~":
            if k == 0:
                pass
            elif k in (1, 2):
                comps.append((">=", pv.low))
                comps.append(("<", pv.next))
            elif k == 3:
                comps.append((">=", pv.low))
                upper = Version(pv.components[0], pv.components[1] + 1, 0, None)
                comps.append(("<", upper))
        elif matched_op == "^":
            if k == 0:
                pass
            elif k in (1, 2, 3):
                comps.append((">=", pv.low))
                comps.append(("<", pv.U))

    return ComparatorSet(comparators=comps, unsatisfiable=unsatisfiable)


class ParsedRange:
    def __init__(self, sets=None, is_valid=True):
        self.sets = sets if sets is not None else []
        self.is_valid = is_valid

    def matches(self, cand: Version) -> bool:
        if not self.is_valid:
            return False
        return any(cset.matches(cand) for cset in self.sets)


def parse_range(range_str: str) -> ParsedRange:
    if not isinstance(range_str, str):
        return ParsedRange(is_valid=False)

    set_strings = range_str.split("||")
    csets = []
    for s_str in set_strings:
        cset = parse_comparator_set(s_str)
        if cset is None:
            return ParsedRange(is_valid=False)
        csets.append(cset)

    return ParsedRange(sets=csets, is_valid=True)


def resolve(registry, root):
    range_cache = {}

    def get_parsed_range(r_str):
        if r_str not in range_cache:
            range_cache[r_str] = parse_range(r_str)
        return range_cache[r_str]

    valid_registry = {}
    for pkg, versions in registry.items():
        pkg_vers = {}
        for ver_str in versions:
            v_obj = parse_registry_version(ver_str)
            if v_obj is not None:
                pkg_vers[ver_str] = v_obj
        valid_registry[pkg] = pkg_vers

    def ver_satisfies(v_obj, r_str):
        pr = get_parsed_range(r_str)
        return pr.matches(v_obj)

    def get_requirements(pkg, selected):
        reqs = []
        if pkg in root:
            reqs.append(root[pkg])
        for s_pkg, s_ver in selected.items():
            deps = registry.get(s_pkg, {}).get(s_ver, {})
            if pkg in deps:
                reqs.append(deps[pkg])
        return reqs

    def dfs(selected):
        req_pkgs = set(root.keys())
        for s_pkg, s_ver in selected.items():
            deps = registry.get(s_pkg, {}).get(s_ver, {})
            req_pkgs.update(deps.keys())

        unresolved = [p for p in req_pkgs if p not in selected]

        if not unresolved:
            return dict(selected)

        P = min(unresolved)

        if P not in valid_registry:
            return None

        p_reqs = get_requirements(P, selected)
        p_valid_vers = valid_registry[P].values()

        candidates = []
        for v_obj in p_valid_vers:
            if all(ver_satisfies(v_obj, r) for r in p_reqs):
                candidates.append(v_obj)

        candidates.sort(key=lambda v: (v.prec_key, v.raw), reverse=True)

        for cand in candidates:
            selected[P] = cand.raw

            check_passed = True
            for q in selected:
                q_ver = valid_registry[q][selected[q]]
                q_reqs = get_requirements(q, selected)
                if not all(ver_satisfies(q_ver, r) for r in q_reqs):
                    check_passed = False
                    break

            if check_passed:
                res = dfs(selected)
                if res is not None:
                    return res

            del selected[P]

        return None

    solution = dfs({})
    if solution is not None:
        return {"ok": True, "packages": solution}
    else:
        return {"ok": False, "packages": {}}