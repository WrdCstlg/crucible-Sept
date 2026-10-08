def _split_lines(text: str) -> list[str]:
    """Split text into lines at '\\n' only, preserving line endings."""
    if not text:
        return []
    lines = []
    start = 0
    pos = text.find("\n")
    while pos != -1:
        lines.append(text[start : pos + 1])
        start = pos + 1
        pos = text.find("\n", start)
    if start < len(text):
        lines.append(text[start:])
    return lines


def _myers_diff(A: list[str], B: list[str]) -> list[tuple[int, int]]:
    """Compute Myers' greedy diff of A against B according to Section 2 specification.

    Returns the list of matches (x, y) where A[x] is matched with B[y].
    """
    N = len(A)
    M = len(B)

    # history will store V at each step d.
    # V_prev maps diagonal number k to x value.
    history = []
    V_prev = {1: 0}

    found = False
    final_d = 0
    final_k = 0

    max_d = N + M
    for d in range(max_d + 1):
        V_curr = {}
        for k in range(-d, d + 1, 2):
            if k == -d:
                x = V_prev[k + 1]
            elif k == d:
                x = V_prev[k - 1] + 1
            else:
                x_down = V_prev[k + 1]
                x_right = V_prev[k - 1] + 1
                if x_down >= x_right:
                    x = x_down
                else:
                    x = x_right

            y = x - k
            while 0 <= x < N and 0 <= y < M and A[x] == B[y]:
                x += 1
                y += 1

            V_curr[k] = x
            if x == N and y == M:
                final_d = d
                final_k = k
                found = True
                break

        history.append(V_curr)
        V_prev = V_curr
        if found:
            break

    # Backtrack along the chosen diff path to collect matches
    snakes = []
    curr_d = final_d
    curr_k = final_k

    while curr_d > 0:
        x_end = history[curr_d][curr_k]
        if curr_k == -curr_d:
            prev_k = curr_k + 1
            x_start = history[curr_d - 1][prev_k]
        elif curr_k == curr_d:
            prev_k = curr_k - 1
            x_start = history[curr_d - 1][prev_k] + 1
        else:
            x_down = history[curr_d - 1][curr_k + 1]
            x_right = history[curr_d - 1][curr_k - 1] + 1
            if x_down >= x_right:
                prev_k = curr_k + 1
                x_start = x_down
            else:
                prev_k = curr_k - 1
                x_start = x_right

        snakes.append([(x, x - curr_k) for x in range(x_start, x_end)])
        curr_k = prev_k
        curr_d -= 1

    # Step 0 diagonal moves from (0, 0)
    x_end = history[0][0]
    snakes.append([(x, x) for x in range(0, x_end)])

    snakes.reverse()
    matches = [m for snake in snakes for m in snake]
    return matches


def _format_conflict_part(lines: list[str]) -> str:
    """Format a part inside a conflict block, ensuring a final '\\n' if non-empty."""
    if not lines:
        return ""
    text = "".join(lines)
    if not text.endswith("\n"):
        text += "\n"
    return text


def merge(base: str, ours: str, theirs: str) -> dict:
    # 1. Split texts into lines and intern line strings for speed and memory efficiency
    raw_base = _split_lines(base)
    raw_ours = _split_lines(ours)
    raw_theirs = _split_lines(theirs)

    pool: dict[str, str] = {}
    base_lines = [pool.setdefault(line, line) for line in raw_base]
    ours_lines = [pool.setdefault(line, line) for line in raw_ours]
    theirs_lines = [pool.setdefault(line, line) for line in raw_theirs]

    # 2. Diff base against ours and base against theirs
    diff_ours = _myers_diff(base_lines, ours_lines)
    diff_theirs = _myers_diff(base_lines, theirs_lines)

    ours_map = dict(diff_ours)
    theirs_map = dict(diff_theirs)

    # 3. Find stable base lines and their partners
    stable_base = []
    stable_ours = []
    stable_theirs = []

    for b_idx in range(len(base_lines)):
        if b_idx in ours_map and b_idx in theirs_map:
            stable_base.append(b_idx)
            stable_ours.append(ours_map[b_idx])
            stable_theirs.append(theirs_map[b_idx])

    r = len(stable_base)
    s = [-1] + stable_base + [len(base_lines)]
    o = [-1] + stable_ours + [len(ours_lines)]
    t = [-1] + stable_theirs + [len(theirs_lines)]

    # 4. Form and resolve chunks
    output_pieces: list[str] = []
    conflicts = 0

    for j in range(1, r + 2):
        b_part = base_lines[s[j - 1] + 1 : s[j]]
        o_part = ours_lines[o[j - 1] + 1 : o[j]]
        t_part = theirs_lines[t[j - 1] + 1 : t[j]]

        # A chunk whose three parts are all empty is skipped
        if b_part or o_part or t_part:
            if o_part == b_part:
                output_pieces.extend(t_part)
            elif t_part == b_part:
                output_pieces.extend(o_part)
            elif o_part == t_part:
                output_pieces.extend(o_part)
            else:
                conflicts += 1
                output_pieces.append("<<<<<<< ours\n")
                output_pieces.append(_format_conflict_part(o_part))
                output_pieces.append("||||||| base\n")
                output_pieces.append(_format_conflict_part(b_part))
                output_pieces.append("=======\n")
                output_pieces.append(_format_conflict_part(t_part))
                output_pieces.append(">>>>>>> theirs\n")

        # Stable line s_j is written once between chunk j and chunk j+1
        if j <= r:
            output_pieces.append(base_lines[s[j]])

    merged_text = "".join(output_pieces)
    return {
        "text": merged_text,
        "conflicts": conflicts,
        "clean": conflicts == 0,
    }