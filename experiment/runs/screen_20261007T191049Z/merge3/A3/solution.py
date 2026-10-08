def _split_lines(text: str) -> list[str]:
    """Split text into lines at '\\n' only, keeping '\\n'. The last line may lack one."""
    if not text:
        return []
    lines = []
    start = 0
    length = len(text)
    while start < length:
        idx = text.find("\n", start)
        if idx == -1:
            lines.append(text[start:])
            break
        lines.append(text[start : idx + 1])
        start = idx + 1
    return lines


def _myers_diff(A: list[str], B: list[str]) -> list[tuple[int, int]]:
    """Compute the Myers greedy diff path matches between A and B."""
    N = len(A)
    M = len(B)

    # history[d] maps k to x reached at step d
    history: list[dict[int, int]] = []
    V_prev = {1: 0}

    found = False
    final_d = 0
    final_k = 0
    final_x = 0

    max_d = N + M
    for d in range(max_d + 1):
        V_curr: dict[int, int] = {}
        for k in range(-d, d + 1, 2):
            if k == -d:
                start_x = V_prev[k + 1]
            elif k == d:
                start_x = V_prev[k - 1] + 1
            else:
                x_down = V_prev[k + 1]
                x_right = V_prev[k - 1] + 1
                if x_down >= x_right:
                    start_x = x_down
                else:
                    start_x = x_right

            x = start_x
            y = x - k
            limit = N if N < M + k else M + k
            while x < limit and A[x] == B[y]:
                x += 1
                y += 1

            V_curr[k] = x
            if x == N and y == M:
                final_d = d
                final_k = k
                final_x = x
                found = True
                history.append(V_curr)
                break

        if found:
            break
        history.append(V_curr)
        V_prev = V_curr

    # Backtrack to reconstruct the matched diagonal moves
    all_blocks: list[list[tuple[int, int]]] = []
    curr_x = final_x
    curr_k = final_k

    for d in range(final_d, 0, -1):
        V_p = history[d - 1]
        k = curr_k
        if k == -d:
            k_prev = k + 1
            start_x = V_p[k + 1]
        elif k == d:
            k_prev = k - 1
            start_x = V_p[k - 1] + 1
        else:
            x_down = V_p[k + 1]
            x_right = V_p[k - 1] + 1
            if x_down >= x_right:
                k_prev = k + 1
                start_x = x_down
            else:
                k_prev = k - 1
                start_x = x_right

        step_matches = [(x_m, x_m - k) for x_m in range(start_x, curr_x)]
        all_blocks.append(step_matches)

        curr_x = V_p[k_prev]
        curr_k = k_prev

    # At step 0, diagonal moves from (0, 0)
    all_blocks.append([(x_m, x_m) for x_m in range(0, curr_x)])

    all_blocks.reverse()
    matches = [m for block in all_blocks for m in block]
    return matches


def _format_conflict_part(part_lines: list[str]) -> str:
    """Format a part inside a conflict block, ensuring its last line ends with '\\n'."""
    if not part_lines:
        return ""
    last = part_lines[-1]
    if not last.endswith("\n"):
        return "".join(part_lines[:-1]) + last + "\n"
    return "".join(part_lines)


def merge(base: str, ours: str, theirs: str) -> dict:
    # Intern line strings to accelerate comparisons and reduce memory usage
    line_pool: dict[str, str] = {}

    def intern(line: str) -> str:
        return line_pool.setdefault(line, line)

    base_lines = [intern(line) for line in _split_lines(base)]
    ours_lines = [intern(line) for line in _split_lines(ours)]
    theirs_lines = [intern(line) for line in _split_lines(theirs)]

    # Diff base against ours, and base against theirs
    matches_ours = _myers_diff(base_lines, ours_lines)
    matches_theirs = _myers_diff(base_lines, theirs_lines)

    ours_map = dict(matches_ours)
    theirs_map = dict(matches_theirs)

    # 1. Identify stable base lines (matched in both diffs)
    stable_s: list[int] = []
    stable_o: list[int] = []
    stable_t: list[int] = []
    for x in range(len(base_lines)):
        if x in ours_map and x in theirs_map:
            stable_s.append(x)
            stable_o.append(ours_map[x])
            stable_t.append(theirs_map[x])

    # 2. Stable lines cut texts into r + 1 chunks
    r = len(stable_s)
    s_cuts = [-1] + stable_s + [len(base_lines)]
    o_cuts = [-1] + stable_o + [len(ours_lines)]
    t_cuts = [-1] + stable_t + [len(theirs_lines)]

    out: list[str] = []
    conflicts = 0

    # 3. Write in order: chunk 1, s_1, chunk 2, s_2, ..., s_r, chunk r+1
    for j in range(r + 1):
        b_part = base_lines[s_cuts[j] + 1 : s_cuts[j + 1]]
        o_part = ours_lines[o_cuts[j] + 1 : o_cuts[j + 1]]
        t_part = theirs_lines[t_cuts[j] + 1 : t_cuts[j + 1]]

        # 4. Resolve chunk
        if o_part == b_part:
            out.extend(t_part)
        elif t_part == b_part:
            out.extend(o_part)
        elif o_part == t_part:
            out.extend(o_part)
        else:
            conflicts += 1
            block = (
                "<<<<<<< ours\n"
                + _format_conflict_part(o_part)
                + "||||||| base\n"
                + _format_conflict_part(b_part)
                + "=======\n"
                + _format_conflict_part(t_part)
                + ">>>>>>> theirs\n"
            )
            out.append(block)

        # Write stable line between chunks
        if j < r:
            out.append(base_lines[stable_s[j]])

    merged_text = "".join(out)
    return {
        "text": merged_text,
        "conflicts": conflicts,
        "clean": conflicts == 0,
    }