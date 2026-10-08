import bisect
import datetime
import re

RUN_RE = re.compile(r"[A-Za-z0-9_\-\.]+")
JOINER_RE = re.compile(r"[\-_\.]")
DIGIT_RUN_RE = re.compile(r"\d+")


def _clean_digit_run(m):
    s = m.group().lstrip("0")
    return s if s else "0"


def _extract_tokens(text):
    tokens = []
    for m in RUN_RE.finditer(text):
        run = m.group()
        s = JOINER_RE.sub("", run)
        if not s:
            continue
        s = s.upper()
        s = DIGIT_RUN_RE.sub(_clean_digit_run, s)
        tokens.append(s)
    return tokens


def _is_ascii_digits(s):
    return all("0" <= c <= "9" for c in s)


def _parse_date(s):
    if not isinstance(s, str) or len(s) != 10 or s[4] != "-" or s[7] != "-":
        return None
    y_str, m_str, d_str = s[:4], s[5:7], s[8:10]
    if (
        not _is_ascii_digits(y_str)
        or not _is_ascii_digits(m_str)
        or not _is_ascii_digits(d_str)
    ):
        return None
    y, m, d = int(y_str), int(m_str), int(d_str)
    if y < 1 or y > 9999:
        return None
    try:
        dt = datetime.date(y, m, d)
        return dt.toordinal()
    except ValueError:
        return None


def _validate_ledger_record(r):
    if not isinstance(r, dict):
        return False, None
    for k in ("id", "date", "amount", "ref", "party"):
        if k not in r:
            return False, None
    r_id = r["id"]
    if not isinstance(r_id, str) or len(r_id) == 0:
        return False, None
    ord_date = _parse_date(r["date"])
    if ord_date is None:
        return False, None
    r_amount = r["amount"]
    if type(r_amount) is not int or r_amount == 0:
        return False, None
    if not isinstance(r["ref"], str) or not isinstance(r["party"], str):
        return False, None
    return True, ord_date


def _validate_bank_record(r):
    if not isinstance(r, dict):
        return False, None
    for k in ("id", "date", "amount", "text"):
        if k not in r:
            return False, None
    r_id = r["id"]
    if not isinstance(r_id, str) or len(r_id) == 0:
        return False, None
    ord_date = _parse_date(r["date"])
    if ord_date is None:
        return False, None
    r_amount = r["amount"]
    if type(r_amount) is not int or r_amount == 0:
        return False, None
    if not isinstance(r["text"], str):
        return False, None
    return True, ord_date


class _LedgerEntry:
    __slots__ = ("idx", "id", "date", "ord", "amount", "ref", "party", "key")

    def __init__(self, idx, id_, date, ord_val, amount, ref, party, key):
        self.idx = idx
        self.id = id_
        self.date = date
        self.ord = ord_val
        self.amount = amount
        self.ref = ref
        self.party = party
        self.key = key


class _BankLine:
    __slots__ = ("idx", "id", "date", "ord", "amount", "text", "tokens")

    def __init__(self, idx, id_, date, ord_val, amount, text, tokens):
        self.idx = idx
        self.id = id_
        self.date = date
        self.ord = ord_val
        self.amount = amount
        self.text = text
        self.tokens = tokens


def reconcile(ledger, bank, params):
    W = params["days"]
    F = params["fee_cents"]

    # 1. Validation
    invalid_ledger = []
    valid_ledger_candidates = []
    ledger_id_counts = {}
    for idx, r in enumerate(ledger):
        ok, ord_d = _validate_ledger_record(r)
        if ok:
            valid_ledger_candidates.append((idx, r, ord_d))
            rid = r["id"]
            ledger_id_counts[rid] = ledger_id_counts.get(rid, 0) + 1
        else:
            invalid_ledger.append(idx)

    valid_entries = []
    for idx, r, ord_d in valid_ledger_candidates:
        if ledger_id_counts[r["id"]] > 1:
            invalid_ledger.append(idx)
        else:
            tokens = _extract_tokens(r["ref"])
            key = tokens[0] if len(tokens) == 1 else None
            entry = _LedgerEntry(
                idx, r["id"], r["date"], ord_d, r["amount"], r["ref"], r["party"], key
            )
            valid_entries.append(entry)
    invalid_ledger.sort()

    invalid_bank = []
    valid_bank_candidates = []
    bank_id_counts = {}
    for idx, r in enumerate(bank):
        ok, ord_d = _validate_bank_record(r)
        if ok:
            valid_bank_candidates.append((idx, r, ord_d))
            bid = r["id"]
            bank_id_counts[bid] = bank_id_counts.get(bid, 0) + 1
        else:
            invalid_bank.append(idx)

    valid_lines = []
    for idx, r, ord_d in valid_bank_candidates:
        if bank_id_counts[r["id"]] > 1:
            invalid_bank.append(idx)
        else:
            tokens = set(_extract_tokens(r["text"]))
            line = _BankLine(
                idx, r["id"], r["date"], ord_d, r["amount"], r["text"], tokens
            )
            valid_lines.append(line)
    invalid_bank.sort()

    matched_entries = set()
    matched_lines = set()
    matches = []

    # Pre-index bank lines for Pass 1 and Pass 4
    lines_by_token_amount = {}
    lines_by_token = {}
    for b in valid_lines:
        for t in b.tokens:
            lines_by_token.setdefault(t, []).append(b)
            lines_by_token_amount.setdefault((t, b.amount), []).append(b)

    for lst in lines_by_token.values():
        lst.sort(key=lambda x: x.ord)
    for lst in lines_by_token_amount.values():
        lst.sort(key=lambda x: x.ord)

    # -------------------------------------------------------------
    # Pass 1: "ref"
    # -------------------------------------------------------------
    pass1_candidates = []
    for e in valid_entries:
        if e.key is None:
            continue
        lines_list = lines_by_token_amount.get((e.key, e.amount))
        if not lines_list:
            continue
        line_dates = [b.ord for b in lines_list]
        start_idx = bisect.bisect_left(line_dates, e.ord - W)
        end_idx = bisect.bisect_right(line_dates, e.ord + W)
        for i in range(start_idx, end_idx):
            b = lines_list[i]
            delta = abs(e.ord - b.ord)
            key = (delta, e.date, e.id, b.id)
            pass1_candidates.append((key, e, b))

    pass1_candidates.sort(key=lambda x: x[0])
    for key, e, b in pass1_candidates:
        if e.id not in matched_entries and b.id not in matched_lines:
            matched_entries.add(e.id)
            matched_lines.add(b.id)
            matches.append(
                {"type": "ref", "ledger": [e.id], "bank": [b.id], "difference": 0}
            )

    # -------------------------------------------------------------
    # Pass 2: "amount"
    # -------------------------------------------------------------
    entries_by_amount = {}
    for e in valid_entries:
        if e.id not in matched_entries:
            entries_by_amount.setdefault(e.amount, []).append(e)

    lines_by_amount = {}
    for b in valid_lines:
        if b.id not in matched_lines:
            lines_by_amount.setdefault(b.amount, []).append(b)

    pass2_matched_pairs = []
    for amt, elist in entries_by_amount.items():
        blist = lines_by_amount.get(amt)
        if not blist:
            continue
        blist_sorted = sorted(blist, key=lambda x: x.ord)
        b_dates = [b.ord for b in blist_sorted]
        amt_candidates = []
        for e in elist:
            start_idx = bisect.bisect_left(b_dates, e.ord - W)
            end_idx = bisect.bisect_right(b_dates, e.ord + W)
            for i in range(start_idx, end_idx):
                b = blist_sorted[i]
                delta = abs(e.ord - b.ord)
                key = (delta, e.date, e.id, b.id)
                amt_candidates.append((key, e, b))

        amt_candidates.sort(key=lambda x: x[0])
        amt_matched_entries = set()
        amt_matched_lines = set()
        for key, e, b in amt_candidates:
            if e.id not in amt_matched_entries and b.id not in amt_matched_lines:
                amt_matched_entries.add(e.id)
                amt_matched_lines.add(b.id)
                pass2_matched_pairs.append((key, e.id, b.id))

    pass2_matched_pairs.sort(key=lambda x: x[0])
    for key, e_id, b_id in pass2_matched_pairs:
        matched_entries.add(e_id)
        matched_lines.add(b_id)
        matches.append(
            {"type": "amount", "ledger": [e_id], "bank": [b_id], "difference": 0}
        )

    # -------------------------------------------------------------
    # Pass 3: "multi_ledger"
    # -------------------------------------------------------------
    unmatched_lines_pass3 = [b for b in valid_lines if b.id not in matched_lines]
    unmatched_lines_pass3.sort(key=lambda x: (x.date, x.id))

    entries_sorted_by_date = sorted(valid_entries, key=lambda x: x.ord)
    entry_ord_list = [e.ord for e in entries_sorted_by_date]

    for b in unmatched_lines_pass3:
        if b.id in matched_lines:
            continue
        idx_start = bisect.bisect_left(entry_ord_list, b.ord - W)
        idx_end = bisect.bisect_right(entry_ord_list, b.ord + W)

        party_groups = {}
        for idx in range(idx_start, idx_end):
            e = entries_sorted_by_date[idx]
            if e.party and e.id not in matched_entries:
                party_groups.setdefault(e.party, []).append(e)

        # (a) Fewest entries: 2 entries beats 3 entries
        best_2 = None
        for p, cands in party_groups.items():
            n = len(cands)
            if n < 2:
                continue
            for i in range(n):
                e1 = cands[i]
                for j in range(i + 1, n):
                    e2 = cands[j]
                    if e1.amount + e2.amount == b.amount:
                        sum_delta = abs(e1.ord - b.ord) + abs(e2.ord - b.ord)
                        sorted_ids = [e1.id, e2.id]
                        if sorted_ids[0] > sorted_ids[1]:
                            sorted_ids[0], sorted_ids[1] = sorted_ids[1], sorted_ids[0]
                        score = (sum_delta, sorted_ids)
                        if best_2 is None or score < best_2[0]:
                            best_2 = (score, (e1, e2))

        if best_2 is not None:
            group = best_2[1]
            for e in group:
                matched_entries.add(e.id)
            matched_lines.add(b.id)
            matches.append(
                {
                    "type": "multi_ledger",
                    "ledger": best_2[0][1],
                    "bank": [b.id],
                    "difference": 0,
                }
            )
            continue

        best_3 = None
        for p, cands in party_groups.items():
            n = len(cands)
            if n < 3:
                continue
            for i in range(n):
                e1 = cands[i]
                for j in range(i + 1, n):
                    e2 = cands[j]
                    target = b.amount - (e1.amount + e2.amount)
                    for k in range(j + 1, n):
                        e3 = cands[k]
                        if e3.amount == target:
                            sum_delta = (
                                abs(e1.ord - b.ord)
                                + abs(e2.ord - b.ord)
                                + abs(e3.ord - b.ord)
                            )
                            sorted_ids = sorted([e1.id, e2.id, e3.id])
                            score = (sum_delta, sorted_ids)
                            if best_3 is None or score < best_3[0]:
                                best_3 = (score, (e1, e2, e3))

        if best_3 is not None:
            group = best_3[1]
            for e in group:
                matched_entries.add(e.id)
            matched_lines.add(b.id)
            matches.append(
                {
                    "type": "multi_ledger",
                    "ledger": best_3[0][1],
                    "bank": [b.id],
                    "difference": 0,
                }
            )

    # -------------------------------------------------------------
    # Pass 4: "multi_bank"
    # -------------------------------------------------------------
    unmatched_entries_pass4 = [
        e for e in valid_entries if e.id not in matched_entries
    ]
    unmatched_entries_pass4.sort(key=lambda x: (x.date, x.id))

    for e in unmatched_entries_pass4:
        if e.id in matched_entries or e.key is None:
            continue
        token_lines = lines_by_token.get(e.key)
        if not token_lines:
            continue
        t_dates = [b.ord for b in token_lines]
        idx_start = bisect.bisect_left(t_dates, e.ord - W)
        idx_end = bisect.bisect_right(t_dates, e.ord + W)

        cands = [
            token_lines[i]
            for i in range(idx_start, idx_end)
            if token_lines[i].id not in matched_lines
        ]

        best_2 = None
        n = len(cands)
        if n >= 2:
            for i in range(n):
                b1 = cands[i]
                for j in range(i + 1, n):
                    b2 = cands[j]
                    if b1.amount + b2.amount == e.amount:
                        sum_delta = abs(b1.ord - e.ord) + abs(b2.ord - e.ord)
                        sorted_ids = [b1.id, b2.id]
                        if sorted_ids[0] > sorted_ids[1]:
                            sorted_ids[0], sorted_ids[1] = sorted_ids[1], sorted_ids[0]
                        score = (sum_delta, sorted_ids)
                        if best_2 is None or score < best_2[0]:
                            best_2 = (score, (b1, b2))

        if best_2 is not None:
            group = best_2[1]
            matched_entries.add(e.id)
            for b in group:
                matched_lines.add(b.id)
            matches.append(
                {
                    "type": "multi_bank",
                    "ledger": [e.id],
                    "bank": best_2[0][1],
                    "difference": 0,
                }
            )
            continue

        best_3 = None
        if n >= 3:
            for i in range(n):
                b1 = cands[i]
                for j in range(i + 1, n):
                    b2 = cands[j]
                    target = e.amount - (b1.amount + b2.amount)
                    for k in range(j + 1, n):
                        b3 = cands[k]
                        if b3.amount == target:
                            sum_delta = (
                                abs(b1.ord - e.ord)
                                + abs(b2.ord - e.ord)
                                + abs(b3.ord - e.ord)
                            )
                            sorted_ids = sorted([b1.id, b2.id, b3.id])
                            score = (sum_delta, sorted_ids)
                            if best_3 is None or score < best_3[0]:
                                best_3 = (score, (b1, b2, b3))

        if best_3 is not None:
            group = best_3[1]
            matched_entries.add(e.id)
            for b in group:
                matched_lines.add(b.id)
            matches.append(
                {
                    "type": "multi_bank",
                    "ledger": [e.id],
                    "bank": best_3[0][1],
                    "difference": 0,
                }
            )

    # -------------------------------------------------------------
    # Pass 5: "fee"
    # -------------------------------------------------------------
    if F > 0:
        rem_entries = [e for e in valid_entries if e.id not in matched_entries]
        rem_lines = [b for b in valid_lines if b.id not in matched_lines]

        day_lines_map = {}
        for b in rem_lines:
            day_lines_map.setdefault(b.ord, []).append(b)

        unique_line_days = sorted(day_lines_map.keys())
        day_amounts_map = {}
        for d in unique_line_days:
            day_lines_map[d].sort(key=lambda x: x.amount)
            day_amounts_map[d] = [b.amount for b in day_lines_map[d]]

        pass5_candidates = []
        for e in rem_entries:
            if e.amount > 0:
                low = max(1, e.amount - F)
                high = e.amount - 1
            else:
                low = e.amount - F
                high = e.amount - 1
            if low > high:
                continue

            d_start = bisect.bisect_left(unique_line_days, e.ord - W)
            d_end = bisect.bisect_right(unique_line_days, e.ord + W)

            for d_idx in range(d_start, d_end):
                d = unique_line_days[d_idx]
                amt_list = day_amounts_map[d]
                idx_low = bisect.bisect_left(amt_list, low)
                idx_high = bisect.bisect_right(amt_list, high)
                lines_d = day_lines_map[d]
                delta = abs(e.ord - d)
                for b_idx in range(idx_low, idx_high):
                    b = lines_d[b_idx]
                    fee = e.amount - b.amount
                    key = (delta, fee, e.date, e.id, b.id)
                    pass5_candidates.append((key, e, b))

        pass5_candidates.sort(key=lambda x: x[0])
        for key, e, b in pass5_candidates:
            if e.id not in matched_entries and b.id not in matched_lines:
                matched_entries.add(e.id)
                matched_lines.add(b.id)
                fee = key[1]
                matches.append(
                    {
                        "type": "fee",
                        "ledger": [e.id],
                        "bank": [b.id],
                        "difference": -fee,
                    }
                )

    unmatched_ledger = [
        e.id for e in valid_entries if e.id not in matched_entries
    ]
    unmatched_bank = [b.id for b in valid_lines if b.id not in matched_lines]

    return {
        "matches": matches,
        "unmatched_ledger": unmatched_ledger,
        "unmatched_bank": unmatched_bank,
        "invalid": {"ledger": invalid_ledger, "bank": invalid_bank},
    }