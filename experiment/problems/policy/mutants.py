"""Planted misreadings of SPEC.md for Problem 11. Each must be caught by at least one non-public case."""

MUTANTS = {
    "M01 unknown principal evaluated with an identity set of its own id": [
        ("        if pid not in principals:\n            out.append(result(\"DENY\", \"unknown_principal\", []))\n"
         "            continue\n",
         "        if pid not in principals:\n            principals = dict(principals)\n"
         "            principals[pid] = {\"kind\": \"user\", \"inherits\": [], \"boundary\": None, \"tags\": {}}\n"
         "            wildcard_hits.clear()\n"),
    ],
    "M02 inheriting a user is followed": [
        ("                    if principals[y][\"kind\"] != \"role\":\n                        continue\n", ""),
    ],
    "M03 only the principal's own boundary counts": [
        ("            bsets = sorted({principals[m][\"boundary\"] for m in members if principals[m][\"boundary\"] is not None})",
         "            bsets = [principals[pid][\"boundary\"]] if principals[pid][\"boundary\"] is not None else []"),
    ],
    "M04 a boundary set without statements imposes nothing": [
        ("            for st in boundary_stmts.get(b, []):",
         "            if b not in boundary_stmts:\n                continue\n            for st in boundary_stmts.get(b, []):"),
    ],
    "M05 ForAllValues needs at least one value": [
        ("        if prefix == \"ForAllValues:\":\n            return True\n",
         "        if prefix == \"ForAllValues:\":\n            return False\n"),
        ("        return all(passes(base, values, r) for r in vals)",
         "        return bool(vals) and all(passes(base, values, r) for r in vals)"),
    ],
    "M06 unknown statement keys are tolerated": [
        ("    if type(st) is not dict or not set(st) <= STATEMENT_KEYS:", "    if type(st) is not dict:"),
    ],
    "M07 plain negated operator is false for a missing key": [
        ("        return base in NEGATED", "        return False"),
    ],
    "M08 IfExists ignored": [
        ("        if if_exists:\n            return True\n", ""),
    ],
    "M09 plain operator on a list needs every value": [
        ("    return any(passes(base, values, r) for r in vals)",
         "    if prefix == \"ForAnyValue:\":\n        return any(passes(base, values, r) for r in vals)\n"
         "    return bool(vals) and all(passes(base, values, r) for r in vals)"),
    ],
    "M10 full Unicode lowercasing of actions": [
        ("    return s.translate(ASCII_FOLD)", "    return s.lower()"),
    ],
    "M11 fnmatch semantics ([...] is a character class)": [
        ("    __slots__ = (\"segs\",)", "    __slots__ = (\"segs\", \"text\")"),
        ("        self.segs = [(re.compile(\"\".join(s), re.S), len(s)) for s in segs]",
         "        self.segs = [(re.compile(\"\".join(s), re.S), len(s)) for s in segs]\n"
         "        self.text = \"\".join(\"*\" if k == STAR else \"?\" if k == ONE else ch for k, ch in tokens)"),
        ("    def match(self, s):\n        segs = self.segs\n",
         "    def match(self, s):\n        import fnmatch\n        return fnmatch.fnmatchcase(s, self.text)\n\n"
         "    def unused(self, s):\n        segs = self.segs\n"),
    ],
    "M12 number grammar not enforced (anything Fraction parses)": [
        ("    if NUMBER.fullmatch(s) is None:\n        return None\n    return Fraction(s)",
         "    try:\n        return Fraction(s)\n    except (ValueError, ZeroDivisionError):\n        return None"),
    ],
    "M13 numbers compared as floats": [
        ("    return Fraction(s)", "    return float(s)"),
    ],
    "M14 a missing tag is substituted as the empty string": [
        ("                        if value is None:\n                            toks = None\n                            break\n",
         "                        if value is None:\n                            value = \"\"\n"),
    ],
    "M15 substituted text keeps its wildcards": [
        ("                        toks.extend((LIT, ch) for ch in pid)", "                        toks.extend(plain_tokens(pid))"),
        ("                        toks.extend((LIT, ch) for ch in value)",
         "                        toks.extend(plain_tokens(value))"),
    ],
    "M16 tag ties broken by inheritance order, not smallest id": [
        ("                    if best is None or cand < best:", "                    if best is None or cand[0] < best[0]:"),
    ],
    "M17 a missing-tag pattern in not_resources excludes everything": [
        ("        hit = any(g is not None and g.match(resource) for g in resource_globs(st, pid))",
         "        hit = any(st[\"not_resources\"] if g is None else g.match(resource) for g in resource_globs(st, pid))"),
    ],
    "M18 a matching boundary Deny is an explicit deny": [
        ("        if outside:\n            out.append(result(\"DENY\", \"outside_boundary\", b_deny))",
         "        if b_deny:\n            out.append(result(\"DENY\", \"explicit_deny\", b_deny))\n"
         "        elif outside:\n            out.append(result(\"DENY\", \"outside_boundary\", b_deny))"),
    ],
    "M19 Null inverted (\"true\" means the key is present)": [
        ("        return any((v == \"true\") != present for v in values)",
         "        return any((v == \"true\") == present for v in values)"),
    ],
    "M20 recursive identity traversal (overflows on deep chains)": [
        ("            dist = {pid: 0}\n            queue = deque([pid])\n            while queue:\n"
         "                x = queue.popleft()\n                for y in principals[x][\"inherits\"]:\n"
         "                    if y in dist or y not in principals:\n                        continue\n"
         "                    if principals[y][\"kind\"] != \"role\":\n                        continue\n"
         "                    dist[y] = dist[x] + 1\n                    queue.append(y)\n",
         "            dist = {}\n\n            def visit(x, d):\n                if x in dist and dist[x] <= d:\n"
         "                    return\n                dist[x] = d\n                for y in principals[x][\"inherits\"]:\n"
         "                    if y in principals and principals[y][\"kind\"] == \"role\":\n"
         "                        visit(y, d + 1)\n            visit(pid, 0)\n"),
    ],
}
