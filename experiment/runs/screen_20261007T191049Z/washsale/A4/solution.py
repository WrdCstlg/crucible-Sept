from collections import deque
from datetime import date


class Piece:
    __slots__ = ("qty", "basis", "carried_days")

    def __init__(self, qty, basis, carried_days):
        self.qty = qty
        self.basis = basis
        self.carried_days = carried_days


class Lot:
    __slots__ = (
        "id",
        "symbol",
        "acq_ord",
        "replacement_pieces",
        "fresh_piece",
        "fresh_qty",
        "total_qty",
        "node",
    )

    def __init__(self, lot_id, symbol, acq_ord, qty, basis):
        self.id = lot_id
        self.symbol = symbol
        self.acq_ord = acq_ord
        self.replacement_pieces = deque()
        self.fresh_piece = Piece(qty, basis, 0)
        self.fresh_qty = qty
        self.total_qty = qty
        self.node = None


class Node:
    __slots__ = ("lot", "group_id", "prev", "next")

    def __init__(self, lot, group_id):
        self.lot = lot
        self.group_id = group_id
        self.prev = None
        self.next = None


def parse_and_validate_date(s):
    if not (isinstance(s, str) and len(s) == 10 and s[4] == "-" and s[7] == "-"):
        return None
    y_s, m_s, d_s = s[:4], s[5:7], s[8:]
    if not (
        y_s.isascii()
        and y_s.isdigit()
        and m_s.isascii()
        and m_s.isdigit()
        and d_s.isascii()
        and d_s.isdigit()
    ):
        return None
    y, m, d = int(y_s), int(m_s), int(d_s)
    if not (1900 <= y <= 2099):
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


def compute_gains(trades, identical):
    rejected = []
    valid_trades = []

    # 1. Trade validation
    for i, t in enumerate(trades):
        if not isinstance(t, dict):
            rejected.append(i)
            continue

        if not (
            "date" in t
            and "side" in t
            and "symbol" in t
            and "qty" in t
            and "amount" in t
        ):
            rejected.append(i)
            continue

        dt = parse_and_validate_date(t["date"])
        if dt is None:
            rejected.append(i)
            continue

        side = t["side"]
        if side not in ("BUY", "SELL"):
            rejected.append(i)
            continue

        symbol = t["symbol"]
        if not (isinstance(symbol, str) and len(symbol) > 0):
            rejected.append(i)
            continue

        qty = t["qty"]
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            rejected.append(i)
            continue

        amount = t["amount"]
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
            rejected.append(i)
            continue

        valid_trades.append(
            {
                "index": i,
                "date_dt": dt,
                "date_ord": dt.toordinal(),
                "side": side,
                "symbol": symbol,
                "qty": qty,
                "amount": amount,
            }
        )

    # Union-Find for identical symbols
    parent = {}

    def find(x):
        path = []
        curr = x
        while curr in parent and parent[curr] != curr:
            path.append(curr)
            curr = parent[curr]
        for node in path:
            parent[node] = curr
        return curr

    def union(x, y):
        rx = find(x)
        ry = find(y)
        if rx != ry:
            parent[rx] = ry

    for group in identical:
        if not group:
            continue
        first = group[0]
        if first not in parent:
            parent[first] = first
        for s in group[1:]:
            if s not in parent:
                parent[s] = s
            union(first, s)

    # Assign integer group IDs
    group_ids = {}

    def get_group_id(sym):
        rep = find(sym)
        if rep not in group_ids:
            group_ids[rep] = len(group_ids)
        return group_ids[rep]

    # Pre-create all lots from valid BUYs
    all_lots = {}
    group_lots = {}

    for t in valid_trades:
        if t["side"] == "BUY":
            lot_id = t["index"]
            lot = Lot(
                lot_id,
                t["symbol"],
                t["date_ord"],
                t["qty"],
                t["amount"],
            )
            all_lots[lot_id] = lot
            gid = get_group_id(t["symbol"])
            if gid not in group_lots:
                group_lots[gid] = []
            group_lots[gid].append(lot)

    # Sort lots in each group by (acq_ord, lot_id) and build doubly linked lists
    group_head = {}

    def unlink(node):
        if node.lot.node is None:
            return
        gid = node.group_id
        if node.prev is not None:
            node.prev.next = node.next
        else:
            group_head[gid] = node.next
        if node.next is not None:
            node.next.prev = node.prev
        node.prev = None
        node.next = None
        node.lot.node = None

    for gid, lots in group_lots.items():
        lots.sort(key=lambda l: (l.acq_ord, l.id))
        head = None
        tail = None
        for lot in lots:
            node = Node(lot, gid)
            lot.node = node
            if head is None:
                head = node
                tail = node
            else:
                tail.next = node
                node.prev = tail
                tail = node
        group_head[gid] = head

    def advance_head(gid, min_acq_ord):
        head = group_head.get(gid)
        while head is not None and head.lot.acq_ord < min_acq_ord:
            next_node = head.next
            unlink(head)
            head = next_node

    # Processing order: date_ord ascending, then input index ascending
    valid_trades.sort(key=lambda t: (t["date_ord"], t["index"]))

    currently_held = {}
    held_lots = {}
    realized_rows = []

    for t in valid_trades:
        sym = t["symbol"]
        if t["side"] == "BUY":
            lot = all_lots[t["index"]]
            if sym not in held_lots:
                held_lots[sym] = deque()
                currently_held[sym] = 0
            held_lots[sym].append(lot)
            currently_held[sym] += t["qty"]
        else:
            # SELL trade
            current_shares = currently_held.get(sym, 0)
            if t["qty"] > current_shares:
                rejected.append(t["index"])
                continue

            currently_held[sym] -= t["qty"]
            remaining_sell_qty = t["qty"]
            drawn_lots = set()
            sale_rows = []

            # 3. Selling: draw shares from held lots in FIFO order
            while remaining_sell_qty > 0:
                lot = held_lots[sym][0]
                drawn_lots.add(lot.id)
                while remaining_sell_qty > 0 and lot.total_qty > 0:
                    if lot.replacement_pieces:
                        piece = lot.replacement_pieces[0]
                        take = min(remaining_sell_qty, piece.qty)
                        split_basis = piece.basis * take // piece.qty
                        piece.basis -= split_basis
                        piece.qty -= take
                        lot.total_qty -= take
                        c_days = piece.carried_days
                        if piece.qty == 0:
                            lot.replacement_pieces.popleft()
                        sale_rows.append(
                            {
                                "lot": lot,
                                "qty": take,
                                "basis": split_basis,
                                "carried_days": c_days,
                            }
                        )
                        remaining_sell_qty -= take
                    else:
                        piece = lot.fresh_piece
                        take = min(remaining_sell_qty, piece.qty)
                        split_basis = piece.basis * take // piece.qty
                        piece.basis -= split_basis
                        piece.qty -= take
                        lot.total_qty -= take
                        lot.fresh_qty = piece.qty
                        c_days = 0
                        if piece.qty == 0:
                            lot.fresh_piece = None
                            lot.fresh_qty = 0
                            if lot.node is not None:
                                unlink(lot.node)
                        sale_rows.append(
                            {
                                "lot": lot,
                                "qty": take,
                                "basis": split_basis,
                                "carried_days": c_days,
                            }
                        )
                        remaining_sell_qty -= take

                if lot.total_qty == 0:
                    held_lots[sym].popleft()

            # Proceeds allocation
            R = t["amount"]
            Q = t["qty"]
            for row in sale_rows:
                n = row["qty"]
                p = R * n // Q
                R -= p
                Q -= n
                row["proceeds"] = p
                row["gain"] = p - row["basis"]

                # Holding days and Term
                holding_start_ord = row["lot"].acq_ord - row["carried_days"]
                holding_days = t["date_ord"] - holding_start_ord
                row["holding_days"] = holding_days

                if holding_days > 366:
                    row["term"] = "LONG"
                else:
                    hs_date = date.fromordinal(holding_start_ord)
                    if hs_date.month == 2 and hs_date.day == 29:
                        anniv = date(hs_date.year + 1, 3, 1)
                    else:
                        anniv = date(hs_date.year + 1, hs_date.month, hs_date.day)
                    row["term"] = "LONG" if t["date_dt"] > anniv else "SHORT"

            # 4. Wash sales
            gid = get_group_id(sym)
            min_acq_ord = t["date_ord"] - 30
            max_acq_ord = t["date_ord"] + 30
            advance_head(gid, min_acq_ord)

            for row in sale_rows:
                gain = row["gain"]
                if gain >= 0:
                    row["disallowed"] = 0
                    continue

                loss = -gain
                n = row["qty"]
                row_holding_days = row["holding_days"]

                # Step 2: Candidates search
                chunks = []
                needed = n
                curr = group_head.get(gid)
                while (
                    curr is not None
                    and curr.lot.acq_ord <= max_acq_ord
                    and needed > 0
                ):
                    if curr.lot.id in drawn_lots:
                        curr = curr.next
                        continue
                    c = min(needed, curr.lot.fresh_qty)
                    chunks.append((curr.lot, c))
                    needed -= c
                    curr = curr.next

                r = n - needed
                if r == 0:
                    row["disallowed"] = 0
                    continue

                D = loss * r // n
                row["disallowed"] = D

                # Steps 4 & 5: Allocate D and create replacement pieces
                R_d = D
                Q_d = r
                for cand_lot, c in chunks:
                    d = R_d * c // Q_d
                    R_d -= d
                    Q_d -= c

                    fp = cand_lot.fresh_piece
                    split_basis = fp.basis * c // fp.qty
                    fp.qty -= c
                    fp.basis -= split_basis
                    cand_lot.fresh_qty = fp.qty
                    if fp.qty == 0:
                        cand_lot.fresh_piece = None
                        cand_lot.fresh_qty = 0
                        if cand_lot.node is not None:
                            unlink(cand_lot.node)

                    rep = Piece(c, split_basis + d, row_holding_days)
                    cand_lot.replacement_pieces.append(rep)

            # Record realized rows for output
            for draw_idx, row in enumerate(sale_rows):
                realized_rows.append(
                    (
                        t["index"],
                        draw_idx,
                        {
                            "sale": t["index"],
                            "lot": row["lot"].id,
                            "qty": row["qty"],
                            "proceeds": row["proceeds"],
                            "basis": row["basis"],
                            "gain": row["gain"],
                            "disallowed": row["disallowed"],
                            "term": row["term"],
                        },
                    )
                )

    # Sort realized entries: by SELL input index, then draw order
    realized_rows.sort(key=lambda item: (item[0], item[1]))
    realized_output = [item[2] for item in realized_rows]

    # Collect open lots: ordered by lot (acq_ord, input index), then piece order
    open_lots = []
    sorted_lots = sorted(all_lots.values(), key=lambda l: (l.acq_ord, l.id))
    for lot in sorted_lots:
        for p in lot.replacement_pieces:
            open_lots.append(
                {
                    "lot": lot.id,
                    "qty": p.qty,
                    "basis": p.basis,
                    "carried_days": p.carried_days,
                }
            )
        if lot.fresh_piece is not None and lot.fresh_piece.qty > 0:
            open_lots.append(
                {
                    "lot": lot.id,
                    "qty": lot.fresh_piece.qty,
                    "basis": lot.fresh_piece.basis,
                    "carried_days": lot.fresh_piece.carried_days,
                }
            )

    rejected.sort()

    short_term_total = sum(
        r["gain"] + r["disallowed"]
        for r in realized_output
        if r["term"] == "SHORT"
    )
    long_term_total = sum(
        r["gain"] + r["disallowed"]
        for r in realized_output
        if r["term"] == "LONG"
    )
    disallowed_total = sum(r["disallowed"] for r in realized_output)

    return {
        "realized": realized_output,
        "open_lots": open_lots,
        "rejected": rejected,
        "totals": {
            "short_term": short_term_total,
            "long_term": long_term_total,
            "disallowed": disallowed_total,
        },
    }