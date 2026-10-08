def split_lines(text: str) -> list[str]:
    if not text:
        return []
    parts = text.split("\n")
    lines = [p + "\n" for p in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def myers_diff(A: list[int], B: list[int], N: int, M: int) -> list[tuple[int, int]]:
    x = 0
    y = 0
    while x < N and y < M and A[x] == B[y]:
        x += 1
        y += 1

    if x == N and y == M:
        return [(i, i) for i in range(x)]

    history: list[dict[int, int]] = [{0: x}]
    final_d = 0
    final_k = 0
    stop = False

    for d in range(1, N + M + 1):
        V_curr: dict[int, int] = {}
        V_prev = history[d - 1]
        for k in range(-d, d + 1, 2):
            if k == -d:
                prev_k = k + 1
                start_x = V_prev[prev_k]
            elif k == d:
                prev_k = k - 1
                start_x = V_prev[prev_k] + 1
            else:
                x_down = V_prev[k + 1]
                x_right = V_prev[k - 1] + 1
                if x_down >= x_right:
                    prev_k = k + 1
                    start_x = x_down
                else:
                    prev_k = k - 1
                    start_x = x_right

            x = start_x
            y = x - k
            while x < N and y < M and A[x] == B[y]:
                x += 1
                y += 1

            V_curr[k] = x
            if x == N and y == M:
                final_d = d
                final_k = k
                stop = True
                break

        history.append(V_curr)
        if stop:
            break

    all_matches: list[list[tuple[int, int]]] = []
    curr_k = final_k
    for d in range(final_d, 0, -1):
        V_prev = history[d - 1]
        if curr_k == -d:
            prev_k = curr_k + 1
            start_x = V_prev[prev_k]
        elif curr_k == d:
            prev_k = curr_k - 1
            start_x = V_prev[prev_k] + 1
        else:
            x_down = V_prev[curr_k + 1]
            x_right = V_prev[curr_k - 1] + 1
            if x_down >= x_right:
                prev_k = curr_k + 1
                start_x = x_down
            else:
                prev_k = curr_k - 1
                start_x = x_right

        end_x = history[d][curr_k]
        all_matches.append([(xi, xi - curr_k) for xi in range(start_x, end_x)])
        curr_k = prev_k

    end_x = history[0][0]
    all_matches.append([(xi, xi) for xi in range(0, end_x)])

    matches: list[tuple[int, int]] = []
    for step in reversed(all_matches):
        matches.extend(step)

    return matches


def format_conflict_part(part_lines: list[str]) -> str:
    if not part_lines:
        return ""
    text = "".join(part_lines)
    if not text.endswith("\n"):
        text += "\n"
    return text


def merge(base: str, ours: str, theirs: str) -> dict[str, object]:
    base_lines = split_lines(base)
    ours_lines = split_lines(ours)
    theirs_lines = split_lines(theirs)

    line_to_id: dict[str, int] = {}

    def to_ids(lines: list[str]) -> list[int]:
        ids: list[int] = []
        for line in lines:
            val = line_to_id.get(line)
            if val is None:
                val = len(line_to_id)
                line_to_id[line] = val
            ids.append(val)
        return ids

    base_ids = to_ids(base_lines)
    ours_ids = to_ids(ours_lines)
    theirs_ids = to_ids(theirs_lines)

    matches_ours = myers_diff(base_ids, ours_ids, len(base_ids), len(ours_ids))
    matches_theirs = myers_diff(base_ids, theirs_ids, len(base_ids), len(theirs_ids))

    base_to_ours = dict(matches_ours)
    base_to_theirs = dict(matches_theirs)

    stable_base = [
        i
        for i in range(len(base_lines))
        if i in base_to_ours and i in base_to_theirs
    ]

    r = len(stable_base)
    s = [-1] + stable_base + [len(base_lines)]
    o = [-1] + [base_to_ours[i] for i in stable_base] + [len(ours_lines)]
    t = [-1] + [base_to_theirs[i] for i in stable_base] + [len(theirs_lines)]

    out: list[str] = []
    conflicts = 0

    for j in range(1, r + 2):
        b_part = base_lines[s[j - 1] + 1 : s[j]]
        o_part = ours_lines[o[j - 1] + 1 : o[j]]
        t_part = theirs_lines[t[j - 1] + 1 : t[j]]

        if not (not b_part and not o_part and not t_part):
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
                    + format_conflict_part(o_part)
                    + "||||||| base\n"
                    + format_conflict_part(b_part)
                    + "=======\n"
                    + format_conflict_part(t_part)
                    + ">>>>>>> theirs\n"
                )
                out.append(block)

        if j <= r:
            out.append(base_lines[s[j]])

    merged_text = "".join(out)
    return {
        "text": merged_text,
        "conflicts": conflicts,
        "clean": conflicts == 0,
    }