import sys

# Increase recursion depth just in case, though traversal is iterative.
sys.setrecursionlimit(20000)


class BracketMatcher:
    __slots__ = ('negated', 'singles', 'ranges')

    def __init__(self, negated, singles, ranges):
        self.negated = negated
        self.singles = singles  # set of chars
        self.ranges = ranges    # list of (lo_code, hi_code)

    def matches(self, ch):
        code = ord(ch)
        in_set = (ch in self.singles) or any(lo <= code <= hi for lo, hi in self.ranges)
        return not in_set if self.negated else in_set


class PatternSegment:
    __slots__ = ('exact_str', 'has_wildcard', 'has_star', 'tokens', 'fixed_len')

    def matches(self, name):
        if self.exact_str is not None:
            return name == self.exact_str
        if not self.has_star:
            if len(name) != self.fixed_len:
                return False
            for t, ch in zip(self.tokens, name):
                k = t[0]
                if k == 'L':
                    if t[1] != ch:
                        return False
                elif k == '?':
                    continue
                elif k == 'B':
                    if not t[1].matches(ch):
                        return False
            return True
        return match_wildcard(self.tokens, name)


def match_wildcard(tokens, name):
    K = len(tokens)
    dp = 1
    # Epsilon closure for initial dp
    i = 0
    while i < K and tokens[i][0] == '*':
        dp |= (1 << (i + 1))
        i += 1

    for ch in name:
        if not dp:
            return False
        new_dp = 0
        for i in range(K):
            if (dp >> i) & 1:
                t = tokens[i]
                k = t[0]
                if k == '*':
                    new_dp |= (1 << i)
                elif k == 'L':
                    if t[1] == ch:
                        new_dp |= (1 << (i + 1))
                elif k == '?':
                    new_dp |= (1 << (i + 1))
                elif k == 'B':
                    if t[1].matches(ch):
                        new_dp |= (1 << (i + 1))

        for i in range(K):
            if ((new_dp >> i) & 1) and tokens[i][0] == '*':
                new_dp |= (1 << (i + 1))

        dp = new_dp

    return bool((dp >> K) & 1)


def parse_pattern_segment(raw_seg):
    if not raw_seg:
        return None  # empty segment -> invalid

    n = len(raw_seg)
    tokens = []
    i = 0
    has_star = False
    has_wildcard = False

    while i < n:
        c = raw_seg[i]
        if c == '\\':
            if i + 1 >= n:
                return None  # unpaired \ at end of segment -> invalid
            tokens.append(('L', raw_seg[i + 1]))
            i += 2
        elif c == '*':
            has_star = True
            has_wildcard = True
            if not tokens or tokens[-1][0] != '*':
                tokens.append(('*',))
            i += 1
        elif c == '?':
            has_wildcard = True
            tokens.append(('?',))
            i += 1
        elif c == '[':
            has_wildcard = True
            start_i = i + 1
            if start_i >= n:
                return None  # unclosed '[' -> invalid

            negated = False
            curr = start_i
            if raw_seg[curr] in ('!', '^'):
                negated = True
                curr += 1
                if curr >= n:
                    return None  # unclosed

            singles = set()
            ranges = []
            first_member = True
            closed = False

            while curr < n:
                if raw_seg[curr] == ']' and not first_member:
                    closed = True
                    curr += 1
                    break

                # Read member
                if raw_seg[curr] == '\\':
                    if curr + 1 >= n:
                        return None  # unpaired \ inside bracket -> invalid
                    lo_char = raw_seg[curr + 1]
                    next_curr = curr + 2
                else:
                    lo_char = raw_seg[curr]
                    next_curr = curr + 1

                first_member = False
                curr = next_curr

                # Check for range: '-' followed by char other than ']'
                if curr < n and raw_seg[curr] == '-':
                    after_dash = curr + 1
                    if after_dash < n:
                        if raw_seg[after_dash] == ']':
                            # '-' is followed by ']' -> '-' is plain member
                            singles.add(lo_char)
                            # curr remains at '-', next iteration reads '-'
                        else:
                            # forms range
                            if raw_seg[after_dash] == '\\':
                                if after_dash + 1 >= n:
                                    return None
                                hi_char = raw_seg[after_dash + 1]
                                curr = after_dash + 2
                            else:
                                hi_char = raw_seg[after_dash]
                                curr = after_dash + 1
                            lo_code = ord(lo_char)
                            hi_code = ord(hi_char)
                            if lo_code <= hi_code:
                                ranges.append((lo_code, hi_code))
                    else:
                        singles.add(lo_char)
                else:
                    singles.add(lo_char)

            if not closed:
                return None  # unclosed '[' -> invalid

            bm = BracketMatcher(negated, singles, ranges)
            tokens.append(('B', bm))
            i = curr
        else:
            tokens.append(('L', c))
            i += 1

    ps = PatternSegment()
    ps.tokens = tokens
    ps.has_wildcard = has_wildcard
    ps.has_star = has_star
    if not has_wildcard:
        ps.exact_str = ''.join(t[1] for t in tokens)
    else:
        ps.exact_str = None
        if not has_star:
            ps.fixed_len = len(tokens)
        else:
            ps.fixed_len = -1
    return ps


def parse_line(raw_line):
    # Step 1: comment
    if raw_line.startswith('#'):
        return None

    # Step 2: remove trailing spaces respecting escapes
    tokens = []
    i = 0
    n = len(raw_line)
    while i < n:
        if raw_line[i] == '\\' and i + 1 < n:
            tokens.append((True, raw_line[i:i + 2]))
            i += 2
        else:
            tokens.append((False, raw_line[i]))
            i += 1

    while tokens and tokens[-1] == (False, ' '):
        tokens.pop()

    line = ''.join(t[1] for t in tokens)

    # Step 3: if empty, skip
    if not line:
        return None

    # Step 4: negation
    negated = False
    if line.startswith('!'):
        negated = True
        line = line[1:]

    # Step 5: directory-only
    dir_only = False
    if line.endswith('/'):
        dir_only = True
        line = line[:-1]

    # Step 6: anchoring
    anchored = '/' in line
    if anchored and line.startswith('/'):
        line = line[1:]

    # Step 7: if now empty, skip
    if not line:
        return None

    raw_segments = line.split('/')
    return negated, dir_only, anchored, raw_segments


class Rule:
    __slots__ = (
        'negated', 'dir_only', 'anchored', 'has_globstar',
        'seg_pattern',       # for unanchored rules
        'seg_patterns',      # for anchored non-globstar
        'num_segs',
        'prefix', 'suffix', 'blocks', 'block_remaining_lens',
        'last_is_globstar', 'min_len'
    )


def parse_rules_for_dir(lines):
    parsed_rules = []
    for line in lines:
        parsed = parse_line(line)
        if parsed is None:
            continue
        negated, dir_only, anchored, raw_segments = parsed

        # A globstar is a pattern segment of an anchored rule that consists only of '*' (>= 2)
        is_globstar_seg = [
            anchored and len(s) >= 2 and all(c == '*' for c in s)
            for s in raw_segments
        ]

        # Collapse adjacent globstars
        if anchored and any(is_globstar_seg):
            collapsed_raw = []
            collapsed_is_gs = []
            for s, is_gs in zip(raw_segments, is_globstar_seg):
                if is_gs and collapsed_is_gs and collapsed_is_gs[-1]:
                    continue
                collapsed_raw.append(s)
                collapsed_is_gs.append(is_gs)
            raw_segments = collapsed_raw
            is_globstar_seg = collapsed_is_gs

        seg_patterns = []
        rule_invalid = False
        for s, is_gs in zip(raw_segments, is_globstar_seg):
            if is_gs:
                seg_patterns.append(None)
            else:
                ps = parse_pattern_segment(s)
                if ps is None:
                    rule_invalid = True
                    break
                seg_patterns.append(ps)

        if rule_invalid:
            continue

        rule = Rule()
        rule.negated = negated
        rule.dir_only = dir_only
        rule.anchored = anchored

        if not anchored:
            rule.has_globstar = False
            rule.seg_pattern = seg_patterns[0]
        else:
            has_gs = any(is_globstar_seg)
            rule.has_globstar = has_gs
            if not has_gs:
                rule.seg_patterns = seg_patterns
                rule.num_segs = len(seg_patterns)
            else:
                gs_indices = [idx for idx, val in enumerate(is_globstar_seg) if val]
                first_gs = gs_indices[0]
                last_gs = gs_indices[-1]

                rule.prefix = seg_patterns[:first_gs]
                rule.suffix = seg_patterns[last_gs + 1:]
                rule.last_is_globstar = (last_gs == len(seg_patterns) - 1)

                blocks = []
                curr_block = []
                for p, is_gs in zip(seg_patterns[first_gs + 1:last_gs], is_globstar_seg[first_gs + 1:last_gs]):
                    if is_gs:
                        if curr_block:
                            blocks.append(curr_block)
                            curr_block = []
                    else:
                        curr_block.append(p)
                if curr_block:
                    blocks.append(curr_block)

                rule.blocks = blocks

                rem = []
                tot = sum(len(b) for b in blocks)
                curr_sum = 0
                for b in blocks:
                    curr_sum += len(b)
                    rem.append(tot - curr_sum)
                rule.block_remaining_lens = rem

                rule.min_len = (
                    len(rule.prefix) + len(rule.suffix) +
                    tot + (1 if rule.last_is_globstar else 0)
                )

        parsed_rules.append(rule)

    return parsed_rules


def match_globstar(rule, rel, rel_len):
    if rel_len < rule.min_len:
        return False

    prefix = rule.prefix
    prefix_len = len(prefix)
    for i in range(prefix_len):
        if not prefix[i].matches(rel[i]):
            return False

    suffix = rule.suffix
    suffix_len = len(suffix)
    for i in range(suffix_len):
        if not suffix[i].matches(rel[rel_len - suffix_len + i]):
            return False

    end_pos = rel_len - suffix_len - (1 if rule.last_is_globstar else 0)
    pos = prefix_len

    blocks = rule.blocks
    block_remaining = rule.block_remaining_lens
    for b_idx in range(len(blocks)):
        block = blocks[b_idx]
        b_len = len(block)
        limit = end_pos - b_len - block_remaining[b_idx]
        found = False
        for j in range(pos, limit + 1):
            if all(block[k].matches(rel[j + k]) for k in range(b_len)):
                pos = j + b_len
                found = True
                break
        if not found:
            return False

    return True


def decide(path_segs, is_dir, ancestor_stack):
    last_seg = path_segs[-1]
    # Check ancestors from deepest to root
    for i in range(len(ancestor_stack) - 1, -1, -1):
        _, b_len, b_rules = ancestor_stack[i]
        rel = path_segs[b_len:]
        rel_len = len(rel)
        for rule in reversed(b_rules):
            if rule.dir_only and not is_dir:
                continue
            if not rule.anchored:
                if rule.seg_pattern.matches(last_seg):
                    return not rule.negated
            elif not rule.has_globstar:
                if rel_len == rule.num_segs:
                    if all(rule.seg_patterns[k].matches(rel[k]) for k in range(rel_len)):
                        return not rule.negated
            else:
                if match_globstar(rule, rel, rel_len):
                    return not rule.negated
    return False


class DirNode:
    __slots__ = ('name', 'path', 'path_segs', 'children', 'files', 'rules')

    def __init__(self, name, path, path_segs):
        self.name = name
        self.path = path
        self.path_segs = path_segs
        self.children = {}  # seg -> DirNode
        self.files = []     # list of (seg, full_path, path_segs)
        self.rules = None


def ignored(files, rules):
    invalid_set = set()
    valid_paths = set()
    path_segments = {}

    for p in files:
        segs = p.split('/')
        if any(s in ('', '.', '..') for s in segs):
            invalid_set.add(p)
        else:
            valid_paths.add(p)
            if p not in path_segments:
                path_segments[p] = segs

    # Step 2: directories
    directory_set = set()
    for p in valid_paths:
        segs = path_segments[p]
        for k in range(1, len(segs)):
            directory_set.add('/'.join(segs[:k]))

    # Step 3 & 4: files and invalid directories
    file_paths = set()
    for p in valid_paths:
        if p in directory_set:
            invalid_set.add(p)
        else:
            file_paths.add(p)

    # Build directory tree
    root = DirNode("", "", [])
    nodes = {"": root}

    sorted_dirs = sorted(directory_set, key=lambda d: d.count('/'))
    for d in sorted_dirs:
        idx = d.rfind('/')
        if idx == -1:
            parent_path = ""
            seg = d
        else:
            parent_path = d[:idx]
            seg = d[idx + 1:]
        parent_node = nodes[parent_path]
        node = DirNode(seg, d, parent_node.path_segs + [seg])
        parent_node.children[seg] = node
        nodes[d] = node

    # Assign parsed rules to directory nodes
    for d_path, r_lines in rules.items():
        if d_path in nodes:
            parsed = parse_rules_for_dir(r_lines)
            if parsed:
                nodes[d_path].rules = parsed

    # Assign files to their parent directories
    for f in file_paths:
        idx = f.rfind('/')
        if idx == -1:
            parent_path = ""
            seg = f
        else:
            parent_path = f[:idx]
            seg = f[idx + 1:]
        parent_node = nodes[parent_path]
        parent_node.files.append((seg, f, path_segments[f]))

    ignored_files = []
    ignored_dirs = []

    def collect_all_files(start_node):
        s = [start_node]
        while s:
            curr = s.pop()
            for _, f_path, _ in curr.files:
                ignored_files.append(f_path)
            for child in curr.children.values():
                s.append(child)

    # Traverse directory tree iteratively
    ancestor_stack = []
    if root.rules:
        ancestor_stack.append(("", 0, root.rules))

    # DFS stack holds: (node, child_keys, next_child_idx)
    root_child_keys = list(root.children.keys())
    dfs_stack = [(root, root_child_keys, 0)]

    # Process files in root
    for _, f_path, f_segs in root.files:
        if decide(f_segs, False, ancestor_stack):
            ignored_files.append(f_path)

    while dfs_stack:
        curr_node, child_keys, idx = dfs_stack[-1]
        if idx < len(child_keys):
            dfs_stack[-1] = (curr_node, child_keys, idx + 1)
            child = curr_node.children[child_keys[idx]]

            # Decide whether child directory is excluded
            if decide(child.path_segs, True, ancestor_stack):
                ignored_dirs.append(child.path)
                collect_all_files(child)
            else:
                # Directory is included: push rules and enter
                if child.rules:
                    ancestor_stack.append((child.path, len(child.path_segs), child.rules))

                # Decide files immediately in child
                for _, f_path, f_segs in child.files:
                    if decide(f_segs, False, ancestor_stack):
                        ignored_files.append(f_path)

                dfs_stack.append((child, list(child.children.keys()), 0))
        else:
            # Done with curr_node
            dfs_stack.pop()
            if curr_node is not root and curr_node.rules:
                ancestor_stack.pop()

    return {
        "ignored": sorted(set(ignored_files)),
        "ignored_dirs": sorted(set(ignored_dirs)),
        "invalid": sorted(invalid_set)
    }