"""Planted misreadings of SPEC.md for Problem 9. Each must be caught by at least one non-public case."""

MUTANTS = {
    "M01 percent rounds instead of floors": [
        ("                u[\"price\"] -= u[\"price\"] * promo[\"percent\"] // 100",
         "                u[\"price\"] -= (u[\"price\"] * promo[\"percent\"] + 50) // 100"),
    ],
    "M02 percent applies to claimed units": [
        ("        eligible = [u for u in units if not u[\"claimed\"] and catalog[u[\"sku\"]][\"category\"] == promo[\"category\"]]",
         "        eligible = [u for u in units if catalog[u[\"sku\"]][\"category\"] == promo[\"category\"]]"),
    ],
    "M03 bxgy frees the cheapest eligible units overall": [
        ("            for _, u in claimed[len(claimed) - groups * promo[\"get\"]:]:\n                u[\"price\"] = 0",
         "            for _, u in sorted(eligible, key=lambda iu: (iu[1][\"price\"], iu[0]))[: groups * promo[\"get\"]]:\n"
         "                u[\"price\"] = 0"),
    ],
    "M04 bxgy claims only the free units": [
        ("            for _, u in claimed:\n                u[\"claimed\"] = True",
         "            for _, u in claimed[len(claimed) - groups * promo[\"get\"]:]:\n                u[\"claimed\"] = True"),
    ],
    "M05 allocation remainder ties by last unit": [
        ("    order = sorted(range(len(weights)), key=lambda i: (-(amount * weights[i] % total), i))",
         "    order = sorted(range(len(weights)), key=lambda i: (-(amount * weights[i] % total), -i))"),
    ],
    "M06 allocation remainder to the largest weight": [
        ("    order = sorted(range(len(weights)), key=lambda i: (-(amount * weights[i] % total), i))",
         "    order = sorted(range(len(weights)), key=lambda i: (-weights[i], i))"),
    ],
    "M07 bundle allocation ties by sku order": [
        ("            order = sorted(range(len(picked)), key=lambda k: picked[k])",
         "            order = list(range(len(picked)))"),
    ],
    "M08 bundle applied once only": [
        ("            pos += 1", "            return"),
    ],
    "M09 threshold uses strict >": [
        ("        if subtotal > 0 and subtotal >= promo[\"min_subtotal\"]:",
         "        if subtotal > 0 and subtotal > promo[\"min_subtotal\"]:"),
    ],
    "M10 threshold not capped at the subtotal": [
        ("            shares = allocate(min(promo[\"amount_off\"], subtotal), [u[\"price\"] for u in units])\n"
         "            for u, share in zip(units, shares):\n                u[\"price\"] -= share",
         "            amount = promo[\"amount_off\"]\n"
         "            shares = [amount * u[\"price\"] // subtotal for u in units]\n"
         "            for u, share in zip(units, shares):\n                u[\"price\"] = max(0, u[\"price\"] - share)"),
    ],
    "M11 exclusive flag ignored": [
        ("    if len(sel) > 1 and any(p.get(\"exclusive\", False) for p in sel):\n        return False\n", ""),
    ],
    "M12 groups ignored": [
        ("    return len(groups) == len(set(groups))", "    return True"),
    ],
    "M13 applied in input order": [
        ("    ordered = sorted(sel, key=lambda p: (p[\"priority\"], p[\"id\"]))", "    ordered = list(sel)"),
    ],
    "M14 priority ties broken by input order": [
        ("    ordered = sorted(sel, key=lambda p: (p[\"priority\"], p[\"id\"]))",
         "    ordered = sorted(sel, key=lambda p: p[\"priority\"])"),
    ],
    "M15 ties prefer the smaller id list before fewer promotions": [
        ("            key = (sum(lines), len(sel), sorted(p[\"id\"] for p in sel))",
         "            key = (sum(lines), sorted(p[\"id\"] for p in sel), len(sel))"),
    ],
    "M16 greedy: add promotions in priority order while the total drops": [
        ("    best = None\n    for size in range(len(promotions) + 1):\n        for sel in combinations(promotions, size):\n"
         "            if not valid_selection(sel):\n                continue\n",
         "    best = None\n    chosen = []\n    for p in sorted(promotions, key=lambda p: (p[\"priority\"], p[\"id\"])):\n"
         "        if valid_selection(chosen + [p]) and sum(price_selection(catalog, cart, chosen + [p])[0]) < \\\n"
         "                sum(price_selection(catalog, cart, chosen)[0]):\n            chosen.append(p)\n"
         "    for sel in [tuple(chosen)]:\n        if True:\n"),
    ],
    "M17 min_qty counted per line": [
        ("        if len(eligible) >= promo[\"min_qty\"]:",
         "        per_line = {}\n        for u in eligible:\n            per_line[u[\"line\"]] = per_line.get(u[\"line\"], 0) + 1\n"
         "        if eligible and max(per_line.values()) >= promo[\"min_qty\"]:"),
    ],
    "M18 bxgy groups sorted cheapest first": [
        ("            eligible.sort(key=lambda iu: (-iu[1][\"price\"], iu[0]))",
         "            eligible.sort(key=lambda iu: (iu[1][\"price\"], iu[0]))"),
    ],
}
