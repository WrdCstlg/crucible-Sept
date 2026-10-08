def split_lines(text: str) -> list[str]:
    if not text:
        return []
    parts = text.split("\n")
    lines = [p + "\n" for p in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def myers_diff(A: list[int], B: list[int]) -> list[tuple[int, int]]:
    N = len(A)
    M = len(B)

    V_history: list[list[int]] = []

    # Step d = 0
    x = 0
    y = 0
    while x < N and y < M and A[x] == B[y]:
        x += 1
        y += 1
    V_history.append([x])

    if x == N and y == M:
        d_final = 0
        k_final = 0
    else:
        d_final = -1
        k_final = 0
        max_d = N + M
        for d in range(1, max_d + 1):
            V_prev = V_history[d - 1]
            V_curr = [0] * (d + 1)
            found = False

            # idx = 0, k = -d
            x = V_prev[0]
            y = x + d
            while x < N and y < M and A[x] == B[y]:
                x += 1
                y += 1
            V_curr[0] = x
            if x == N and y == M:
                d_final = d
                k_final = -d
                found = True

            if not found:
                for idx in range(1, d):
                    x_down = V_prev[idx]
                    x_right = V_prev[idx - 1] + 1
                    x = x_down if x_down >= x_right else x_right
                    y = x - (2 * idx - d)
                    while x < N and y < M and A[x] == B[y]:
                        x += 1
                        y += 1
                    V_curr[idx] = x
                    if x == N and y == M:
                        d_final = d
                        k_final = 2 * idx - d
                        found = True
                        break

            if not found:
                # idx = d, k = d
                x = V_prev[d - 1] + 1
                y = x - d
                while x < N and y < M and A[x] == B[y]:
                    x += 1
                    y += 1
                V_curr[d] = x
                if x == N and y == M:
                    d_final = d
                    k_final = d
                    found = True

            V_history.append(V_curr)
            if found:
                break

    # Backtracking to reconstruct matches
    matched: list[tuple[int, int]] = []
    curr_d = d_final
    curr_k = k_final

    while curr_d > 0:
        idx = (curr_k + curr_d) // 2
        if curr_d == d_final:
            x_end = N
        else:
            x_end = V_history[curr_d][idx]

        V_prev = V_history[curr_d - 1]
        if curr_k == -curr_d:
            prev_k = curr_k + 1
            x_start = V_prev[0]
        elif curr_k == curr_d:
            prev_k = curr_k - 1
            x_start = V_prev[curr_d - 1] + 1
        else:
            x_down = V_prev[idx]
            x_right = V_prev[idx - 1] + 1
            if x_down >= x_right:
                prev_k = curr_k + 1
                x_start = x_down
            else:
                prev_k = curr_k - 1
                x_start = x_right

        for x_val in range(x_start, x_end):
            matched.append((x_val, x_val - curr_k))

        curr_d -= 1
        curr_k = prev_k

    x_end = V_history[0][0]
    for x_val in range(0, x_end):
        matched.append((x_val, x_val))

    matched.reverse()
    return matched


def format_conflict_part(part: list[str]) -> str:
    if not part:
        return ""
    text = "".join(part)
    if not text.endswith("\n"):
        text += "\n"
    return text


def format_conflict_block(o: list[str], b: list[str], t: list[str]) -> str:
    return (
        "<<<<<<< ours\n"
        + format_conflict_part(o)
        + "||||||| base\n"
        + format_conflict_part(b)
        + "=======\n"
        + format_conflict_part(t)
        + ">>>>>>> theirs\n"
    )


def merge(base: str, ours: str, theirs: str) -> dict:
    base_lines = split_lines(base)
    ours_lines = split_lines(ours)
    theirs_lines = split_lines(theirs)

    # Map lines to integer IDs for fast diff comparison
    line_to_id: dict[str, int] = {}

    def to_ids(lines: list[str]) -> list[int]:
        res = []
        for line in lines:
            lid = line_to_id.get(line)
            if lid is None:
                lid = len(line_to_id)
                line_to_id[line] = lid
            res.append(lid)
        return res

    base_ids = to_ids(base_lines)
    ours_ids = to_ids(ours_lines)
    theirs_ids = to_ids(theirs_lines)

    # Compute diffs: base vs ours, base vs theirs
    ours_diff = myers_diff(base_ids, ours_ids)
    theirs_diff = myers_diff(base_ids, theirs_ids)

    match_ours = {x: y for x, y in ours_diff}
    match_theirs = {x: y for x, y in theirs_diff}

    # Identify stable lines: base lines matched in both diffs
    s_indices: list[int] = []
    o_indices: list[int] = []
    t_indices: list[int] = []

    for x in range(len(base_lines)):
        if x in match_ours and x in match_theirs:
            s_indices.append(x)
            o_indices.append(match_ours[x])
            t_indices.append(match_theirs[x])

    r = len(s_indices)
    S = [-1] + s_indices + [len(base_lines)]
    O = [-1] + o_indices + [len(ours_lines)]
    T = [-1] + t_indices + [len(theirs_lines)]

    output_parts: list[str] = []
    conflicts = 0

    for j in range(r + 1):
        b_part = base_lines[S[j] + 1 : S[j + 1]]
        o_part = ours_lines[O[j] + 1 : O[j + 1]]
        t_part = theirs_lines[T[j] + 1 : T[j + 1]]

        # A chunk whose three parts are all empty is skipped
        if b_part or o_part or t_part:
            if o_part == b_part:
                output_parts.extend(t_part)
            elif t_part == b_part:
                output_parts.extend(o_part)
            elif o_part == t_part:
                output_parts.extend(o_part)
            else:
                conflicts += 1
                output_parts.append(format_conflict_block(o_part, b_part, t_part))

        if j < r:
            output_parts.append(base_lines[s_indices[j]])

    merged_text = "".join(output_parts)
    return {
        "text": merged_text,
        "conflicts": conflicts,
        "clean": conflicts == 0,
    }