from datetime import date
from collections import deque


def compute_gains(trades, identical):
    # --- 1. Union-Find for Identical Symbols ---
    parent = {}

    def find(u):
        path = []
        while parent.get(u, u) != u:
            path.append(u)
            u = parent[u]
        for node in path:
            parent[node] = u
        return u

    def union(u, v):
        ru = find(u)
        rv = find(v)
        if ru != rv:
            parent[ru] = rv

    for group in identical:
        if not group:
            continue
        first = group[0]
        if first not in parent:
            parent[first] = first
        for other in group[1:]:
            union(first, other)

    def get_group(sym):
        if sym not in parent:
            parent[sym] = sym
        return find(sym)

    # --- 2. Date Validation & Parsing Helper ---
    date_cache = {}

    def parse_date(s):
        if s in date_cache:
            return date_cache[s]
        if not isinstance(s, str) or len(s) != 10:
            date_cache[s] = None
            return None
        if s[4] != "-" or s[7] != "-":
            date_cache[s] = None
            return None
        y_str = s[:4]
        m_str = s[5:7]
        d_str = s[8:10]
        for c in y_str:
            if c < "0" or c > "9":
                date_cache[s] = None
                return None
        for c in m_str:
            if c < "0" or c > "9":
                date_cache[s] = None
                return None
        for c in d_str:
            if c < "0" or c > "9":
                date_cache[s] = None
                return None
        y = int(y_str)
        if not (1900 <= y <= 2099):
            date_cache[s] = None
            return None
        m = int(m_str)
        d = int(d_str)
        try:
            dt = date(y, m, d)
            ord_val = dt.toordinal()
            date_cache[s] = ord_val
            return ord_val
        except ValueError:
            date_cache[s] = None
            return None

    # --- 3. Input Validation ---
    rejected_indices = []
    valid_trades = []

    required_keys = ("date", "side", "symbol", "qty", "amount")
    for idx, trade in enumerate(trades):
        if not all(k in trade for k in required_keys):
            rejected_indices.append(idx)
            continue

        d_str = trade["date"]
        d_ord = parse_date(d_str)
        if d_ord is None:
            rejected_indices.append(idx)
            continue

        side = trade["side"]
        if side != "BUY" and side != "SELL":
            rejected_indices.append(idx)
            continue

        sym = trade["symbol"]
        if not isinstance(sym, str) or len(sym) == 0:
            rejected_indices.append(idx)
            continue

        qty = trade["qty"]
        if type(qty) is not int or qty < 1:
            rejected_indices.append(idx)
            continue

        amt = trade["amount"]
        if type(amt) is not int or amt < 0:
            rejected_indices.append(idx)
            continue

        valid_trades.append({
            "idx": idx,
            "date_ord": d_ord,
            "side": side,
            "symbol": sym,
            "qty": qty,
            "amount": amt,
        })

    # --- 4. Lots and Doubly Linked List for Wash Sale Candidates ---
    class Piece:
        __slots__ = ("qty", "basis", "carried_days")

        def __init__(self, qty, basis, carried_days):
            self.qty = qty
            self.basis = basis
            self.carried_days = carried_days

    class Lot:
        __slots__ = (
            "lot_id",
            "symbol",
            "group_id",
            "acq_date",
            "replacements",
            "fresh_piece",
            "fresh_qty",
            "node",
        )

        def __init__(self, lot_id, symbol, group_id, acq_date, qty, amount):
            self.lot_id = lot_id
            self.symbol = symbol
            self.group_id = group_id
            self.acq_date = acq_date
            self.replacements = deque()
            self.fresh_piece = Piece(qty, amount, 0)
            self.fresh_qty = qty
            self.node = None

    class Node:
        __slots__ = ("lot", "prev", "next")

        def __init__(self, lot):
            self.lot = lot
            self.prev = None
            self.next = None

    class GroupList:
        __slots__ = ("head", "tail")

        def __init__(self):
            self.head = None
            self.tail = None

        def append(self, node):
            if self.tail is None:
                self.head = node
                self.tail = node
            else:
                self.tail.next = node
                node.prev = self.tail
                self.tail = node

        def unlink(self, node):
            if node.prev is None and node.next is None and self.head is not node:
                return
            if node.prev is not None:
                node.prev.next = node.next
            else:
                self.head = node.next
            if node.next is not None:
                node.next.prev = node.prev
            else:
                self.tail = node.prev
            node.prev = None
            node.next = None

    lots_by_id = {}
    group_lists = {}
    all_lots_list = []

    # All lots exist from the very start.
    # We sort BUYs by (date_ord, input_index) to populate group lists in proper order.
    valid_buys = [t for t in valid_trades if t["side"] == "BUY"]
    valid_buys.sort(key=lambda t: (t["date_ord"], t["idx"]))

    for t in valid_buys:
        grp = get_group(t["symbol"])
        lot = Lot(t["idx"], t["symbol"], grp, t["date_ord"], t["qty"], t["amount"])
        node = Node(lot)
        lot.node = node
        lots_by_id[t["idx"]] = lot
        all_lots_list.append(lot)
        if grp not in group_lists:
            group_lists[grp] = GroupList()
        group_lists[grp].append(node)

    # --- 5. Processing Order Execution ---
    # Process valid trades by date, then input index
    valid_trades.sort(key=lambda t: (t["date_ord"], t["idx"]))

    held_shares = {}
    held_lots = {}
    realized_by_sale = {}

    def is_long_term(sale_date_ord, holding_days):
        if holding_days > 366:
            return True
        start_date = date.fromordinal(sale_date_ord - holding_days)
        sale_dt = date.fromordinal(sale_date_ord)
        if start_date.month == 2 and start_date.day == 29:
            anniv = date(start_date.year + 1, 3, 1)
        else:
            anniv = date(start_date.year + 1, start_date.month, start_date.day)
        return sale_dt > anniv

    for trade in valid_trades:
        sym = trade["symbol"]
        idx = trade["idx"]
        t_ord = trade["date_ord"]
        qty = trade["qty"]
        side = trade["side"]

        if side == "BUY":
            lot = lots_by_id[idx]
            held_shares[sym] = held_shares.get(sym, 0) + qty
            if sym not in held_lots:
                held_lots[sym] = deque()
            held_lots[sym].append(lot)

        elif side == "SELL":
            curr_held = held_shares.get(sym, 0)
            if qty > curr_held:
                rejected_indices.append(idx)
                continue

            held_shares[sym] = curr_held - qty
            amt = trade["amount"]
            shares_to_sell = qty

            drawn_rows = []
            drawn_lot_ids = set()

            # Take shares from X's held lots in FIFO order
            while shares_to_sell > 0:
                lot = held_lots[sym][0]
                drawn_lot_ids.add(lot.lot_id)

                while shares_to_sell > 0:
                    if lot.replacements:
                        piece = lot.replacements[0]
                        is_fresh = False
                    elif lot.fresh_piece is not None:
                        piece = lot.fresh_piece
                        is_fresh = True
                    else:
                        break

                    if piece.qty <= shares_to_sell:
                        n = piece.qty
                        b = piece.basis
                        c_days = piece.carried_days
                        shares_to_sell -= n
                        drawn_rows.append((lot, n, b, c_days))
                        if is_fresh:
                            lot.fresh_piece = None
                            lot.fresh_qty = 0
                            if lot.node is not None:
                                group_lists[lot.group_id].unlink(lot.node)
                                lot.node = None
                        else:
                            lot.replacements.popleft()
                    else:
                        n = shares_to_sell
                        taken_basis = piece.basis * n // piece.qty
                        piece.basis -= taken_basis
                        piece.qty -= n
                        c_days = piece.carried_days
                        shares_to_sell = 0
                        drawn_rows.append((lot, n, taken_basis, c_days))
                        if is_fresh:
                            lot.fresh_qty -= n
                        break

                if not lot.replacements and lot.fresh_piece is None:
                    held_lots[sym].popleft()

            # Proceeds allocation
            R = amt
            Q = qty
            sale_realized_rows = []
            loss_rows = []

            for row_idx, (lot, n, b, c_days) in enumerate(drawn_rows):
                proceeds = R * n // Q
                R -= proceeds
                Q -= n
                gain = proceeds - b
                holding_days = t_ord - lot.acq_date + c_days
                term = "LONG" if is_long_term(t_ord, holding_days) else "SHORT"

                row_dict = {
                    "sale": idx,
                    "lot": lot.lot_id,
                    "qty": n,
                    "proceeds": proceeds,
                    "basis": b,
                    "gain": gain,
                    "disallowed": 0,
                    "term": term,
                }
                sale_realized_rows.append(row_dict)

                if gain < 0:
                    loss_rows.append((row_dict, n, -gain, holding_days))

            # Wash sales handling for loss rows
            grp = get_group(sym)
            g_list = group_lists.get(grp)

            if g_list is not None and loss_rows:
                # Prune lots whose acquisition date is strictly earlier than t - 30
                min_acq = t_ord - 30
                max_acq = t_ord + 30
                while g_list.head is not None and g_list.head.lot.acq_date < min_acq:
                    g_list.unlink(g_list.head)

                for row_dict, n, L, row_holding_days in loss_rows:
                    chunks = []
                    shares_needed = n
                    curr = g_list.head

                    while curr is not None and shares_needed > 0:
                        cand_lot = curr.lot
                        if cand_lot.acq_date > max_acq:
                            break
                        if cand_lot.lot_id in drawn_lot_ids:
                            curr = curr.next
                            continue

                        c = min(shares_needed, cand_lot.fresh_qty)
                        chunks.append((cand_lot, curr, c))
                        shares_needed -= c
                        curr = curr.next

                    r = n - shares_needed
                    if r == 0:
                        continue

                    D = L * r // n
                    row_dict["disallowed"] = D

                    # Spread D over chunks
                    RD = D
                    QD = r
                    for cand_lot, node, c in chunks:
                        d = RD * c // QD
                        RD -= d
                        QD -= c

                        fresh_piece = cand_lot.fresh_piece
                        split_basis = fresh_piece.basis * c // fresh_piece.qty
                        fresh_piece.basis -= split_basis
                        fresh_piece.qty -= c
                        cand_lot.fresh_qty -= c

                        repl_piece = Piece(c, split_basis + d, row_holding_days)
                        cand_lot.replacements.append(repl_piece)

                        if fresh_piece.qty == 0:
                            cand_lot.fresh_piece = None
                            g_list.unlink(node)

            realized_by_sale[idx] = sale_realized_rows

    # --- 6. Prepare Final Output ---
    realized = []
    for sell_idx in sorted(realized_by_sale.keys()):
        realized.extend(realized_by_sale[sell_idx])

    open_lots = []
    for lot in all_lots_list:
        for piece in lot.replacements:
            if piece.qty > 0:
                open_lots.append({
                    "lot": lot.lot_id,
                    "qty": piece.qty,
                    "basis": piece.basis,
                    "carried_days": piece.carried_days,
                })
        if lot.fresh_piece is not None and lot.fresh_piece.qty > 0:
            open_lots.append({
                "lot": lot.lot_id,
                "qty": lot.fresh_piece.qty,
                "basis": lot.fresh_piece.basis,
                "carried_days": lot.fresh_piece.carried_days,
            })

    rejected_indices.sort()

    short_term_sum = 0
    long_term_sum = 0
    disallowed_sum = 0
    for row in realized:
        d = row["disallowed"]
        disallowed_sum += d
        net = row["gain"] + d
        if row["term"] == "SHORT":
            short_term_sum += net
        else:
            long_term_sum += net

    return {
        "realized": realized,
        "open_lots": open_lots,
        "rejected": rejected_indices,
        "totals": {
            "short_term": short_term_sum,
            "long_term": long_term_sum,
            "disallowed": disallowed_sum,
        },
    }