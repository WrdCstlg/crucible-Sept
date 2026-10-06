"""Reference for Problem 9 (cart pricing with stacked promotions). Stdlib only; integer cents throughout."""
from itertools import combinations


def allocate(amount, weights):
    """Largest-remainder allocation of `amount` over `weights` (sum > 0, amount <= sum). Ties by position."""
    total = sum(weights)
    shares = [amount * w // total for w in weights]
    missing = amount - sum(shares)
    order = sorted(range(len(weights)), key=lambda i: (-(amount * weights[i] % total), i))
    for i in order[:missing]:
        shares[i] += 1
    return shares


def apply(promo, units, catalog):
    """units: list of dicts {line, sku, price, claimed} in unit order. Mutates in place."""
    kind = promo["type"]
    if kind == "percent":
        eligible = [u for u in units if not u["claimed"] and catalog[u["sku"]]["category"] == promo["category"]]
        if len(eligible) >= promo["min_qty"]:
            for u in eligible:
                u["price"] -= u["price"] * promo["percent"] // 100
    elif kind == "bxgy":
        skus = set(promo["skus"])
        eligible = [(i, u) for i, u in enumerate(units) if not u["claimed"] and u["sku"] in skus]
        size = promo["buy"] + promo["get"]
        groups = len(eligible) // size
        if groups:
            eligible.sort(key=lambda iu: (-iu[1]["price"], iu[0]))
            claimed = eligible[: groups * size]
            for _, u in claimed:
                u["claimed"] = True
            for _, u in claimed[len(claimed) - groups * promo["get"]:]:
                u["price"] = 0
    elif kind == "bundle":
        # unclaimed prices do not change while this bundle is applied, so each sku's queue can be sorted once:
        # highest current price first, ties by unit order
        queues = {}
        for sku in promo["skus"]:
            q = [i for i, u in enumerate(units) if not u["claimed"] and u["sku"] == sku]
            q.sort(key=lambda i: (-units[i]["price"], i))
            queues[sku] = q
        pos = 0
        while True:
            if any(pos >= len(queues[sku]) for sku in promo["skus"]):
                return
            picked = [queues[sku][pos] for sku in promo["skus"]]
            current = [units[i]["price"] for i in picked]
            if sum(current) <= promo["price"]:
                return
            # allocation ties are broken by unit order, not by the order of skus in the promotion
            order = sorted(range(len(picked)), key=lambda k: picked[k])
            shares = allocate(promo["price"], [current[k] for k in order])
            for k, share in zip(order, shares):
                units[picked[k]]["price"] = share
                units[picked[k]]["claimed"] = True
            pos += 1
    elif kind == "threshold":
        subtotal = sum(u["price"] for u in units)
        if subtotal > 0 and subtotal >= promo["min_subtotal"]:
            shares = allocate(min(promo["amount_off"], subtotal), [u["price"] for u in units])
            for u, share in zip(units, shares):
                u["price"] -= share
    else:
        raise ValueError(f"unknown promotion type {kind!r}")


def valid_selection(sel):
    if len(sel) > 1 and any(p.get("exclusive", False) for p in sel):
        return False
    groups = [p["group"] for p in sel if p.get("group") is not None]
    return len(groups) == len(set(groups))


def price_selection(catalog, cart, sel):
    units = []
    for line, item in enumerate(cart):
        for _ in range(item["qty"]):
            units.append({"line": line, "sku": item["sku"], "price": catalog[item["sku"]]["price"],
                          "claimed": False})
    ordered = sorted(sel, key=lambda p: (p["priority"], p["id"]))
    for p in ordered:
        apply(p, units, catalog)
    lines = [0] * len(cart)
    for u in units:
        lines[u["line"]] += u["price"]
    return lines, [p["id"] for p in ordered]


def price_cart(catalog, cart, promotions):
    best = None
    for size in range(len(promotions) + 1):
        for sel in combinations(promotions, size):
            if not valid_selection(sel):
                continue
            lines, applied = price_selection(catalog, cart, sel)
            key = (sum(lines), len(sel), sorted(p["id"] for p in sel))
            if best is None or key < best[0]:
                best = (key, lines, applied)
    _, lines, applied = best
    return {"lines": lines, "applied": applied, "total": sum(lines)}
