def parse_pattern_segment(seg: str):
    """
    Parses a single pattern segment according to Section 3.
    Returns a PatternSegment instance, or None if the segment matches nothing.
    """
    if len(seg) == 0:
        return None

    # Check for unpaired backslash at the end of the segment
    i = 0
    m = len(seg)
    while i < m:
        if seg[i] == '\\':
            if i + 1 == m:
                return None
            i += 2
        else:
            i += 1

    tokens = []
    i = 0
    while i < m:
        c = seg[i]
        if c == '\\':
            tokens.append(('lit', seg[i + 1]))
            i += 2
        elif c == '?':
            tokens.append(('any',))
            i += 1
        elif c == '*':
            if not (tokens and tokens[-1][0] == 'star'):
                tokens.append(('star',))
            i += 1
        elif c == '[':
            curr = i + 1
            negated = False
            if curr < m and seg[curr] in ('!', '^'):
                negated = True
                curr += 1

            first_member = True
            ranges = []
            chars = set()
            closed = False

            while curr < m:
                if seg[curr] == ']' and not first_member:
                    closed = True
                    curr += 1
                    break

                first_member = False

                if seg[curr] == '\\':
                    if curr + 1 >= m:
                        return None
                    m_char = seg[curr + 1]
                    curr += 2
                else:
                    m_char = seg[curr]
                    curr += 1

                if curr < m and seg[curr] == '-':
                    if curr + 1 >= m:
                        return None
                    if seg[curr + 1] == ']':
                        chars.add(m_char)
                    elif seg[curr + 1] == '\\':
                        if curr + 2 >= m:
                            return None
                        hi_char = seg[curr + 2]
                        lo_code = ord(m_char)
                        hi_code = ord(hi_char)
                        if lo_code <= hi_code:
                            ranges.append((lo_code, hi_code))
                        curr += 3
                    else:
                        hi_char = seg[curr + 1]
                        lo_code = ord(m_char)
                        hi_code = ord(hi_char)
                        if lo_code <= hi_code:
                            ranges.append((lo_code, hi_code))
                        curr += 2
                else:
                    chars.add(m_char)

            if not closed:
                return None

            tokens.append(('bracket', chars, ranges, negated))
            i = curr
        else:
            tokens.append(('lit', c))
            i += 1

    return PatternSegment(seg, tokens)


class PatternSegment:
    def __init__(self, raw: str, tokens: list):
        self.raw = raw
        self.tokens = tokens
        self.L = len(tokens)

        self.is_all_star = (len(tokens) == 1 and tokens[0][0] == 'star')
        self.is_literal = all(t[0] == 'lit' for t in tokens)
        if self.is_literal:
            self.literal_str = "".join(t[1] for t in tokens)
        else:
            self.literal_str = None

        self.is_suffix = (len(tokens) >= 2 and tokens[0][0] == 'star'
                          and all(t[0] == 'lit' for t in tokens[1:]))
        if self.is_suffix:
            self.suffix_str = "".join(t[1] for t in tokens[1:])
        else:
            self.suffix_str = None

        self.is_prefix = (len(tokens) >= 2 and tokens[-1][0] == 'star'
                          and all(t[0] == 'lit' for t in tokens[:-1]))
        if self.is_prefix:
            self.prefix_str = "".join(t[1] for t in tokens[:-1])
        else:
            self.prefix_str = None

    def matches(self, name: str) -> bool:
        if self.is_all_star:
            return True
        if self.is_literal:
            return name == self.literal_str
        if self.is_suffix:
            return name.endswith(self.suffix_str)
        if self.is_prefix:
            return name.startswith(self.prefix_str)

        tokens = self.tokens
        L = self.L

        def advance_stars(states):
            res = set(states)
            for s in list(states):
                while s < L and tokens[s][0] == 'star':
                    s += 1
                    res.add(s)
            return res

        states = advance_stars({0})
        for c in name:
            next_states = set()
            for s in states:
                if s < L:
                    tok = tokens[s]
                    kind = tok[0]
                    if kind == 'star':
                        next_states.add(s)
                    elif kind == 'lit':
                        if c == tok[1]:
                            next_states.add(s + 1)
                    elif kind == 'any':
                        next_states.add(s + 1)
                    elif kind == 'bracket':
                        code = ord(c)
                        in_set = (c in tok[1]) or any(lo <= code <= hi for lo, hi in tok[2])
                        matched = (not in_set) if tok[3] else in_set
                        if matched:
                            next_states.add(s + 1)
            if not next_states:
                return False
            states = advance_stars(next_states)

        return L in states


class Rule:
    def __init__(self, negated: bool, dir_only: bool, anchored: bool, segments: list, has_globstar: bool):
        self.negated = negated
        self.dir_only = dir_only
        self.anchored = anchored
        self.segments = segments
        self.has_globstar = has_globstar
        self.single_segment = segments[0][1] if not anchored else None


def parse_rule(line: str):
    """
    Parses a single ignore-file line according to Section 2.
    Returns a Rule instance, or None if skipped/invalid.
    """
    # 1. Comment
    if line.startswith('#'):
        return None

    # 2. Remove unescaped trailing spaces
    n = len(line)
    escaped = [False] * n
    i = 0
    while i < n:
        if line[i] == '\\' and i + 1 < n:
            escaped[i + 1] = True
            i += 2
        else:
            i += 1

    end = n
    while end > 0 and line[end - 1] == ' ' and not escaped[end - 1]:
        end -= 1
    line = line[:end]

    # 3. Empty
    if not line:
        return None

    # 4. Negated
    negated = False
    if line.startswith('!'):
        negated = True
        line = line[1:]

    # 5. Directory-only
    dir_only = False
    if line.endswith('/'):
        dir_only = True
        line = line[:-1]

    # 6. Anchored
    anchored = False
    if '/' in line:
        anchored = True
        if line.startswith('/'):
            line = line[1:]

    # 7. Empty check and split
    if not line:
        return None

    raw_segments = line.split('/')
    parsed_segs = []
    has_globstar = False

    for seg in raw_segments:
        is_globstar = anchored and len(seg) >= 2 and all(c == '*' for c in seg)
        if is_globstar:
            has_globstar = True
            parsed_segs.append((True, None))
        else:
            matcher = parse_pattern_segment(seg)
            if matcher is None:
                return None
            parsed_segs.append((False, matcher))

    return Rule(negated, dir_only, anchored, parsed_segs, has_globstar)


def match_globstar(segments: list, rel: list) -> bool:
    N = len(rel)
    M = len(segments)

    match_states = [False] * (N + 1)
    match_states[0] = True

    for j in range(M):
        is_globstar, matcher = segments[j]
        if is_globstar:
            is_last = (j == M - 1)
            first_i = -1
            for i in range(N + 1):
                if match_states[i]:
                    first_i = i
                    break
            if first_i == -1:
                return False
            new_states = [False] * (N + 1)
            start_i = first_i + 1 if is_last else first_i
            for i in range(start_i, N + 1):
                new_states[i] = True
            match_states = new_states
        else:
            new_states = [False] * (N + 1)
            for i in range(N):
                if match_states[i] and matcher.matches(rel[i]):
                    new_states[i + 1] = True
            match_states = new_states

        if not any(match_states):
            return False

    return match_states[N]


def evaluate_decision(path: str, is_dir: bool, applicable_dirs: list, parsed_rules: dict) -> bool:
    idx = path.rfind('/')
    last_seg = path[idx + 1:] if idx != -1 else path

    for B in applicable_dirs:
        rules_in_B = parsed_rules[B]
        rel_cached = None

        for r in reversed(rules_in_B):
            if r.dir_only and not is_dir:
                continue

            if not r.anchored:
                if r.single_segment.matches(last_seg):
                    return not r.negated
            else:
                if rel_cached is None:
                    if B == "":
                        rel_cached = path.split('/')
                    else:
                        rel_cached = path[len(B) + 1:].split('/')

                if not r.has_globstar:
                    if len(rel_cached) == len(r.segments):
                        if all(seg_tuple[1].matches(name) for seg_tuple, name in zip(r.segments, rel_cached)):
                            return not r.negated
                else:
                    if match_globstar(r.segments, rel_cached):
                        return not r.negated

    return False


def ignored(files, rules):
    # Step 1: Paths and validation
    invalid_paths = set()
    passed_step1 = {}

    for p in set(files):
        if not p or p.startswith('/') or p.endswith('/') or '//' in p:
            invalid_paths.add(p)
            continue
        segs = p.split('/')
        if any(s == '.' or s == '..' for s in segs):
            invalid_paths.add(p)
            continue
        passed_step1[p] = segs

    # Step 2: Directories
    all_dirs = set()
    for segs in passed_step1.values():
        if len(segs) > 1:
            cur = "/".join(segs[:-1])
            while cur and cur not in all_dirs:
                all_dirs.add(cur)
                idx = cur.rfind('/')
                cur = cur[:idx] if idx != -1 else ""

    # Steps 3 and 4: Valid files vs paths that are also directories
    valid_files = []
    for p, segs in passed_step1.items():
        if p in all_dirs:
            invalid_paths.add(p)
        else:
            valid_files.append((p, segs))

    # Parse ignore files that apply to valid directories or the root
    parsed_rules = {}
    for d, lines in rules.items():
        if d != "" and d not in all_dirs:
            continue
        rule_list = []
        for line in lines:
            r = parse_rule(line)
            if r is not None:
                rule_list.append(r)
        if rule_list:
            parsed_rules[d] = rule_list

    # Top-down order of directories
    sorted_dirs = sorted(all_dirs, key=lambda d: d.count('/'))

    ancestor_rules = {"": [""] if "" in parsed_rules else []}
    for d in sorted_dirs:
        idx = d.rfind('/')
        parent = d[:idx] if idx != -1 else ""
        parent_rules = ancestor_rules[parent]
        ancestor_rules[d] = ([d] if d in parsed_rules else []) + parent_rules

    # Evaluate directories (parents first)
    excluded_dirs = set()
    ignored_dirs = []

    for d in sorted_dirs:
        idx = d.rfind('/')
        parent = d[:idx] if idx != -1 else ""
        if parent in excluded_dirs:
            excluded_dirs.add(d)
            continue

        applicable_dirs = ancestor_rules[parent]
        if applicable_dirs and evaluate_decision(d, True, applicable_dirs, parsed_rules):
            excluded_dirs.add(d)
            ignored_dirs.append(d)

    # Evaluate files
    ignored_files = []
    for p, segs in valid_files:
        idx = p.rfind('/')
        parent = p[:idx] if idx != -1 else ""
        if parent in excluded_dirs:
            ignored_files.append(p)
            continue

        applicable_dirs = ancestor_rules[parent]
        if applicable_dirs and evaluate_decision(p, False, applicable_dirs, parsed_rules):
            ignored_files.append(p)

    return {
        "ignored": sorted(ignored_files),
        "ignored_dirs": sorted(ignored_dirs),
        "invalid": sorted(invalid_paths),
    }