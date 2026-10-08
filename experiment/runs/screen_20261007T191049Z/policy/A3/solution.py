import collections
import decimal
import re

# Set high precision for decimal comparisons to avoid precision loss on large numbers.
decimal.getcontext().prec = 5000

# ASCII number specification: optional '-', 1+ digits, optional ('.' and 1+ digits).
NUMBER_RE = re.compile(r'^-?[0-9]+(?:\.[0-9]+)?\Z')

# ASCII-only lowercase translation table.
ASCII_LOWER_TABLE = str.maketrans(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
    "abcdefghijklmnopqrstuvwxyz"
)

# Base operators
ALL_BASES = {
    "StringEquals", "StringNotEquals",
    "StringLike", "StringNotLike",
    "NumericEquals", "NumericNotEquals",
    "NumericLessThan", "NumericLessThanEquals",
    "NumericGreaterThan", "NumericGreaterThanEquals",
    "Bool", "Null"
}

NEGATED_BASES = {"StringNotEquals", "StringNotLike", "NumericNotEquals"}

VALID_STMT_KEYS = {
    "sid", "effect", "principals", "actions", "not_actions",
    "resources", "not_resources", "conditions", "set"
}

# Wildcard token sentinels
STAR = object()
ANY = object()


def match_tokens(tokens, s: str) -> bool:
    """Matches a sequence of tokens (STAR, ANY, or 1-char literal str) against s."""
    n_tokens = len(tokens)
    n_s = len(s)

    if n_tokens == 1 and tokens[0] is STAR:
        return True

    s_idx = 0
    p_idx = 0
    star_idx = -1
    s_tmp = -1

    while s_idx < n_s:
        if p_idx < n_tokens:
            tok = tokens[p_idx]
            if tok is ANY or tok == s[s_idx]:
                s_idx += 1
                p_idx += 1
                continue
            elif tok is STAR:
                if p_idx == n_tokens - 1:
                    return True
                star_idx = p_idx
                s_tmp = s_idx
                p_idx += 1
                continue
        if star_idx != -1:
            p_idx = star_idx + 1
            s_tmp += 1
            s_idx = s_tmp
        else:
            return False

    while p_idx < n_tokens and tokens[p_idx] is STAR:
        p_idx += 1
    return p_idx == n_tokens


def compile_simple_pattern(pat: str):
    """Compiles a pattern without references into (type, data).
    Types: 1 = match all ('*'), 2 = exact string, 3 = wildcard tokens."""
    if pat == "*":
        return (1, None)
    if "*" not in pat and "?" not in pat:
        return (2, pat)
    tokens = []
    for c in pat:
        if c == '*':
            if not tokens or tokens[-1] is not STAR:
                tokens.append(STAR)
        elif c == '?':
            tokens.append(ANY)
        else:
            tokens.append(c)
    return (3, tokens)


def pattern_matches(compiled, s: str) -> bool:
    """Tests if a compiled simple pattern matches string s."""
    ptype = compiled[0]
    if ptype == 1:
        return True
    if ptype == 2:
        return compiled[1] == s
    return match_tokens(compiled[1], s)


def parse_operator(op: str):
    """Validates and parses an operator string into (prefix, base, if_exists)."""
    if op == "Null":
        return ("", "Null", False)

    prefix = ""
    rest = op
    if rest.startswith("ForAnyValue:"):
        prefix = "ForAnyValue:"
        rest = rest[12:]
    elif rest.startswith("ForAllValues:"):
        prefix = "ForAllValues:"
        rest = rest[13:]

    if_exists = False
    if rest.endswith("IfExists"):
        if_exists = True
        rest = rest[:-8]

    if rest in ALL_BASES and rest != "Null":
        return (prefix, rest, if_exists)
    return None


def parse_resource_pattern(pat: str):
    """Validates and parses a resource pattern with references into pieces."""
    pieces = []
    i = 0
    n = len(pat)
    while i < n:
        if pat[i:i + 2] == "${":
            close_idx = pat.find("}", i + 2)
            if close_idx == -1:
                return None
            ref_text = pat[i + 2:close_idx]
            if ref_text == "principal":
                pieces.append(('REF_PRINCIPAL',))
            elif ref_text.startswith("tag:") and len(ref_text) > 4:
                pieces.append(('REF_TAG', ref_text[4:]))
            elif ref_text in ("*", "?", "$"):
                pieces.append(('REF_CHAR', ref_text))
            else:
                return None
            i = close_idx + 1
        else:
            c = pat[i]
            if c == '*':
                pieces.append(('STAR',))
            elif c == '?':
                pieces.append(('ANY',))
            else:
                if pieces and pieces[-1][0] == 'LITERAL':
                    pieces[-1] = ('LITERAL', pieces[-1][1] + c)
                else:
                    pieces.append(('LITERAL', c))
            i += 1
    return pieces


def validate_statement(stmt):
    """Validates a policy statement dict and precompiles its parts.
    Returns statement representation or None if malformed."""
    if not isinstance(stmt, dict):
        return None

    if not set(stmt.keys()).issubset(VALID_STMT_KEYS):
        return None

    sid = stmt.get("sid")
    if not isinstance(sid, str) or len(sid) == 0:
        return None

    effect = stmt.get("effect")
    if effect not in ("Allow", "Deny"):
        return None

    has_set_key = "set" in stmt
    set_val = stmt.get("set")
    if has_set_key and set_val is not None:
        if not isinstance(set_val, str) or len(set_val) == 0:
            return None
        is_boundary = True
    else:
        is_boundary = False

    if is_boundary:
        if "principals" in stmt:
            return None
        principals_compiled = None
    else:
        if "principals" not in stmt:
            return None
        principals_val = stmt["principals"]
        if not isinstance(principals_val, list) or len(principals_val) == 0:
            return None
        if not all(isinstance(p, str) for p in principals_val):
            return None
        principals_compiled = [compile_simple_pattern(p) for p in principals_val]

    has_actions = "actions" in stmt
    has_not_actions = "not_actions" in stmt
    if has_actions == has_not_actions:
        return None
    actions_list = stmt["actions"] if has_actions else stmt["not_actions"]
    if not isinstance(actions_list, list) or len(actions_list) == 0:
        return None
    if not all(isinstance(a, str) for a in actions_list):
        return None
    actions_compiled = [
        compile_simple_pattern(a.translate(ASCII_LOWER_TABLE))
        for a in actions_list
    ]

    has_resources = "resources" in stmt
    has_not_resources = "not_resources" in stmt
    if has_resources == has_not_resources:
        return None
    resources_list = stmt["resources"] if has_resources else stmt["not_resources"]
    if not isinstance(resources_list, list) or len(resources_list) == 0:
        return None
    if not all(isinstance(r, str) for r in resources_list):
        return None

    parsed_resources = []
    for r in resources_list:
        parsed = parse_resource_pattern(r)
        if parsed is None:
            return None
        parsed_resources.append(parsed)

    parsed_conditions = []
    if "conditions" in stmt:
        cond_dict = stmt["conditions"]
        if not isinstance(cond_dict, dict):
            return None
        for op_str, ctx_map in cond_dict.items():
            if not isinstance(op_str, str):
                return None
            op_parsed = parse_operator(op_str)
            if op_parsed is None:
                return None
            prefix, base, if_exists = op_parsed
            if not isinstance(ctx_map, dict):
                return None
            for ctx_key, policy_val in ctx_map.items():
                if not isinstance(ctx_key, str):
                    return None
                if isinstance(policy_val, str):
                    val_list = [policy_val]
                elif isinstance(policy_val, list):
                    if len(policy_val) == 0 or not all(isinstance(x, str) for x in policy_val):
                        return None
                    val_list = policy_val
                else:
                    return None

                # Base validation and precompilation
                val_data = None
                if base.startswith("Numeric"):
                    v_decs = []
                    for x in val_list:
                        if not NUMBER_RE.match(x):
                            return None
                        v_decs.append(decimal.Decimal(x))
                    val_data = {
                        "decs": v_decs,
                        "set": set(v_decs),
                        "min": min(v_decs),
                        "max": max(v_decs)
                    }
                elif base in ("Bool", "Null"):
                    for x in val_list:
                        if x not in ("true", "false"):
                            return None
                    val_data = set(val_list)
                elif base in ("StringEquals", "StringNotEquals"):
                    val_data = set(val_list)
                elif base in ("StringLike", "StringNotLike"):
                    val_data = [compile_simple_pattern(v) for v in val_list]

                parsed_conditions.append({
                    "prefix": prefix,
                    "base": base,
                    "if_exists": if_exists,
                    "key": ctx_key,
                    "vals": val_list,
                    "data": val_data
                })

    return {
        "sid": sid,
        "effect": effect,
        "is_boundary": is_boundary,
        "set": set_val if is_boundary else None,
        "principals_compiled": principals_compiled,
        "is_not_actions": has_not_actions,
        "actions_compiled": actions_compiled,
        "is_not_resources": has_not_resources,
        "parsed_resources": parsed_resources,
        "conditions": parsed_conditions
    }


def resolve_resource_pattern(pieces, principal_id: str, tags: dict):
    """Resolves a parsed resource pattern against a principal and their tags.
    Returns compiled pattern or None if a referenced tag is missing."""
    tokens = []
    for piece in pieces:
        p_type = piece[0]
        if p_type == 'STAR':
            if not tokens or tokens[-1] is not STAR:
                tokens.append(STAR)
        elif p_type == 'ANY':
            tokens.append(ANY)
        elif p_type == 'LITERAL':
            tokens.extend(piece[1])
        elif p_type == 'REF_CHAR':
            tokens.append(piece[1])
        elif p_type == 'REF_PRINCIPAL':
            tokens.extend(principal_id)
        elif p_type == 'REF_TAG':
            tag_key = piece[1]
            if tag_key not in tags:
                return None
            tokens.extend(tags[tag_key])

    if tokens == [STAR]:
        return (1, None)
    if not any(t is STAR or t is ANY for t in tokens):
        return (2, "".join(tokens))
    return (3, tokens)


def evaluate_single_condition(cond, context: dict) -> bool:
    """Evaluates a single condition against the request context."""
    prefix = cond["prefix"]
    base = cond["base"]
    if_exists = cond["if_exists"]
    k = cond["key"]

    if base == "Null":
        present = k in context
        val_set = cond["data"]
        return ("true" in val_set and not present) or ("false" in val_set and present)

    if k not in context:
        if if_exists:
            return True
        if prefix == "ForAllValues:":
            return True
        if prefix == "ForAnyValue:":
            return False
        return base in NEGATED_BASES

    raw_val = context[k]
    r_list = raw_val if isinstance(raw_val, list) else [raw_val]

    def passes(r: str) -> bool:
        if base == "StringEquals":
            return r in cond["data"]
        if base == "StringNotEquals":
            return r not in cond["data"]
        if base == "StringLike":
            return any(pattern_matches(pat, r) for pat in cond["data"])
        if base == "StringNotLike":
            return not any(pattern_matches(pat, r) for pat in cond["data"])
        if base == "Bool":
            return r in cond["data"]

        # Numeric bases
        if not NUMBER_RE.match(r):
            return False
        r_dec = decimal.Decimal(r)
        d = cond["data"]
        if base == "NumericEquals":
            return r_dec in d["set"]
        if base == "NumericNotEquals":
            return r_dec not in d["set"]
        if base == "NumericLessThan":
            return r_dec < d["max"]
        if base == "NumericLessThanEquals":
            return r_dec <= d["max"]
        if base == "NumericGreaterThan":
            return r_dec > d["min"]
        if base == "NumericGreaterThanEquals":
            return r_dec >= d["min"]
        return False

    if prefix == "ForAllValues:":
        return all(passes(r) for r in r_list)
    return any(passes(r) for r in r_list)


def authorize(principals, policies, requests):
    # 1. Parse and filter well-formed policies
    valid_stmts = []
    needed_tag_keys = set()
    for p in policies:
        stmt = validate_statement(p)
        if stmt is not None:
            valid_stmts.append(stmt)
            for pieces in stmt["parsed_resources"]:
                for piece in pieces:
                    if piece[0] == 'REF_TAG':
                        needed_tag_keys.add(piece[1])

    # 2. Principal information cache: P -> principal info tuple
    principal_cache = {}

    def get_principal_info(p_id: str):
        if p_id in principal_cache:
            return principal_cache[p_id]

        # BFS from p_id along role edges
        visited = {p_id: 0}
        queue = collections.deque([p_id])
        while queue:
            curr = queue.popleft()
            curr_dist = visited[curr]
            p_data = principals.get(curr)
            if p_data:
                for child in p_data.get("inherits", []):
                    child_data = principals.get(child)
                    if child_data and child_data.get("kind") == "role":
                        if child not in visited:
                            visited[child] = curr_dist + 1
                            queue.append(child)

        # Boundary sets
        boundary_sets = set()
        for m in visited:
            b = principals[m].get("boundary")
            if b is not None:
                boundary_sets.add(b)

        # Tags
        tags = {}
        for k in needed_tag_keys:
            best = None
            for m, dist in visited.items():
                m_tags = principals[m].get("tags", {})
                if k in m_tags:
                    cand = (dist, m, m_tags[k])
                    if best is None or cand < best:
                        best = cand
            if best is not None:
                tags[k] = best[2]

        identity_set = set(visited.keys())

        # Precompute which identity statements match Condition 1 for this principal
        matched_identity_stmts = set()
        for idx, stmt in enumerate(valid_stmts):
            if not stmt["is_boundary"]:
                for compiled_pat in stmt["principals_compiled"]:
                    ptype = compiled_pat[0]
                    if ptype == 1:
                        matched_identity_stmts.add(idx)
                        break
                    elif ptype == 2:
                        if compiled_pat[1] in identity_set:
                            matched_identity_stmts.add(idx)
                            break
                    else:
                        if any(pattern_matches(compiled_pat, m) for m in identity_set):
                            matched_identity_stmts.add(idx)
                            break

        # Precompute resolved resource patterns for this principal
        resolved_resources = []
        for stmt in valid_stmts:
            stmt_pats = []
            for pieces in stmt["parsed_resources"]:
                res_pat = resolve_resource_pattern(pieces, p_id, tags)
                stmt_pats.append(res_pat)
            resolved_resources.append(stmt_pats)

        info = (
            boundary_sets,
            matched_identity_stmts,
            resolved_resources
        )
        principal_cache[p_id] = info
        return info

    results = []

    # 3. Evaluate each request
    for req in requests:
        p_id = req["principal"]
        if p_id not in principals:
            results.append({
                "decision": "DENY",
                "reason": "unknown_principal",
                "statements": []
            })
            continue

        boundary_sets, matched_id_stmts, resolved_res = get_principal_info(p_id)

        act = req["action"].translate(ASCII_LOWER_TABLE)
        res = req["resource"]
        ctx = req.get("context", {})

        # Test statement matches for this request
        matched_identity_denies = []
        matched_identity_allows = []
        matched_boundary_allows = collections.defaultdict(list)
        matched_boundary_denies = collections.defaultdict(list)

        for idx, stmt in enumerate(valid_stmts):
            # Condition 1: principals pattern matches identity set
            if stmt["is_boundary"]:
                b_set = stmt["set"]
                if b_set not in boundary_sets:
                    continue
            else:
                if idx not in matched_id_stmts:
                    continue

            # Condition 2: action matches
            act_match = any(pattern_matches(cp, act) for cp in stmt["actions_compiled"])
            if stmt["is_not_actions"]:
                if act_match:
                    continue
            else:
                if not act_match:
                    continue

            # Condition 3: resource matches
            res_pats = resolved_res[idx]
            res_match = False
            for pat in res_pats:
                if pat is not None and pattern_matches(pat, res):
                    res_match = True
                    break
            if stmt["is_not_resources"]:
                if res_match:
                    continue
            else:
                if not res_match:
                    continue

            # Condition 4: conditions hold
            conds_pass = True
            for cond in stmt["conditions"]:
                if not evaluate_single_condition(cond, ctx):
                    conds_pass = False
                    break
            if not conds_pass:
                continue

            # Statement matches!
            sid = stmt["sid"]
            if stmt["is_boundary"]:
                b_set = stmt["set"]
                if stmt["effect"] == "Allow":
                    matched_boundary_allows[b_set].append(sid)
                else:
                    matched_boundary_denies[b_set].append(sid)
            else:
                if stmt["effect"] == "Deny":
                    matched_identity_denies.append(sid)
                else:
                    matched_identity_allows.append(sid)

        # Decision rules in order:
        # Rule 2: Explicit deny
        if matched_identity_denies:
            results.append({
                "decision": "DENY",
                "reason": "explicit_deny",
                "statements": sorted(set(matched_identity_denies))
            })
            continue

        # Rule 3: Boundary sets containment check
        outside_boundary = False
        all_boundary_denies = []
        for b_set in boundary_sets:
            b_allows = matched_boundary_allows[b_set]
            b_denies = matched_boundary_denies[b_set]
            all_boundary_denies.extend(b_denies)
            if not (len(b_allows) > 0 and len(b_denies) == 0):
                outside_boundary = True

        if outside_boundary:
            results.append({
                "decision": "DENY",
                "reason": "outside_boundary",
                "statements": sorted(set(all_boundary_denies))
            })
            continue

        # Rule 4: Allowed
        if matched_identity_allows:
            all_allows = list(matched_identity_allows)
            for b_set in boundary_sets:
                all_allows.extend(matched_boundary_allows[b_set])
            results.append({
                "decision": "ALLOW",
                "reason": "allowed",
                "statements": sorted(set(all_allows))
            })
            continue

        # Rule 5: Implicit deny
        results.append({
            "decision": "DENY",
            "reason": "implicit_deny",
            "statements": []
        })

    return results