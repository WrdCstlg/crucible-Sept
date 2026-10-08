import bisect
import collections
import datetime
import re

WORD_RUN_RE = re.compile(r"[A-Za-z0-9_.-]+")
DIGIT_RUN_RE = re.compile(r"[0-9]+")


def _normalize_digits(m):
    s = m.group(0).lstrip("0")
    return s if s else "0"


def _extract_tokens(text):
    tokens = []
    for match in WORD_RUN_RE.finditer(text):
        run = match.group(0)
        # Step 1: delete every joiner
        run = run.replace("-", "").replace("_", "").replace(".", "")
        if not run:
            continue
        # Step 2: change lowercase letters to uppercase
        run = run.upper()
        # Step 3: delete leading zeros in every maximal run of digits
        run = DIGIT_RUN_RE.sub(_normalize_digits, run)
        tokens.append(run)
    return tokens


def _parse_date(d):
    if not isinstance(d, str) or len(d) != 10:
        return None
    if d[4] != "-" or d[7] != "-":
        return None
    y_str = d[:4]
    m_str = d[5:7]
    d_str = d[8:]
    for c in y_str:
        if not ("0" <= c <= "9"):
            return None
    for c in m_str:
        if not ("0" <= c <= "9"):
            return None
    for c in d_str:
        if not ("0" <= c <= "9"):
            return None
    y = int(y_str)
    m = int(m_str)
    day = int(d_str)
    if y < 1 or y > 9999:
        return None
    try:
        return datetime.date(y, m, day)
    except ValueError:
        return None


def _validate_ledger_record(rec):
    if not isinstance(rec, dict):
        return False, None, None, None
    for k in ("id", "date", "amount", "ref", "party"):
        if k not in rec:
            return False, None, None, None
    rec_id = rec["id"]
    if not isinstance(rec_id, str) or len(rec_id) == 0:
        return False, None, None, None
    date_val = _parse_date(rec["date"])
    if date_val is None:
        return False, None, None, None
    amount = rec["amount"]
    if type(amount) is not int or amount == 0:
        return False, None, None, None
    if not isinstance(rec["ref"], str) or not isinstance(rec["party"], str):
        return False, None, None, None
    return True, rec_id, date_val, amount


def _validate_bank_record(rec):
    if not isinstance(rec, dict):
        return False, None, None, None
    for k in ("id", "date", "amount", "text"):
        if k not in rec:
            return False, None, None, None
    rec_id = rec["id"]
    if not isinstance(rec_id, str) or len(rec_id) == 0:
        return False, None, None, None
    date_val = _parse_date(rec["date"])
    if date_val is None:
        return False, None, None, None
    amount = rec["amount"]
    if type(amount) is not int or amount == 0:
        return False, None, None, None
    if not isinstance(rec["text"], str):
        return False, None, None, None
    return True, rec_id, date_val, amount


class _LedgerEntry:
    __slots__ = (
        "idx",
        "id",
        "date_str",
        "date_obj",
        "ordinal",
        "amount",
        "ref",
        "party",
        "key",
    )

    def __init__(self, idx, rec_id, date_str, date_obj, amount, ref, party, key):
        self.idx = idx
        self.id = rec_id
        self.date_str = date_str
        self.date_obj = date_obj
        self.ordinal = date_obj.toordinal()
        self.amount = amount
        self.ref = ref
        self.party = party
        self.key = key


class _BankLine:
    __slots__ = (
        "idx",
        "id",
        "date_str",
        "date_obj",
        "ordinal",
        "amount",
        "text",
        "tokens",
    )

    def __init__(self, idx, rec_id, date_str, date_obj, amount, text, tokens):
        self.idx = idx
        self.id = rec_id
        self.date_str = date_str
        self.date_obj = date_obj
        self.ordinal = date_obj.toordinal()
        self.amount = amount
        self.text = text
        self.tokens = tokens


def reconcile(ledger, bank, params):
    w_days = params["days"]
    f_cents = params["fee_cents"]

    # 1. Validation: Ledger
    invalid_ledger = []
    valid_ledger_candidates = []
    ledger_id_counts = collections.defaultdict(int)

    for idx, rec in enumerate(ledger):
        ok, rec_id, date_val, amount = _validate_ledger_record(rec)
        if ok:
            valid_ledger_candidates.append((idx, rec, rec_id, date_val, amount))
            ledger_id_counts[rec_id] += 1
        else:
            invalid_ledger.append(idx)

    valid_ledger = []
    for idx, rec, rec_id, date_val, amount in valid_ledger_candidates:
        if ledger_id_counts[rec_id] > 1:
            invalid_ledger.append(idx)
        else:
            tokens = _extract_tokens(rec["ref"])
            key = tokens[0] if len(tokens) == 1 else None
            entry = _LedgerEntry(
                idx, rec_id, rec["date"], date_val, amount, rec["ref"], rec["party"], key
            )
            valid_ledger.append(entry)

    invalid_ledger.sort()

    # 1. Validation: Bank
    invalid_bank = []
    valid_bank_candidates = []
    bank_id_counts = collections.defaultdict(int)

    for idx, rec in enumerate(bank):
        ok, rec_id, date_val, amount = _validate_bank_record(rec)
        if ok:
            valid_bank_candidates.append((idx, rec, rec_id, date_val, amount))
            bank_id_counts[rec_id] += 1
        else:
            invalid_bank.append(idx)

    valid_bank = []
    for idx, rec, rec_id, date_val, amount in valid_bank_candidates:
        if bank_id_counts[rec_id] > 1:
            invalid_bank.append(idx)
        else:
            tokens_set = set(_extract_tokens(rec["text"]))
            line = _BankLine(
                idx, rec_id, rec["date"], date_val, amount, rec["text"], tokens_set
            )
            valid_bank.append(line)

    invalid_bank.sort()

    matched_ledger = set()
    matched_bank = set()

    # Pre-index bank lines by token sorted by ordinal
    lines_by_token = collections.defaultdict(list)
    for line in valid_bank:
        for tok in line.tokens:
            lines_by_token[tok].append(line)
    for tok in lines_by_token:
        lines_by_token[tok].sort(key=lambda l: l.ordinal)

    # -------------------------------------------------------------
    # Pass 1: "ref"
    # -------------------------------------------------------------
    matches_1 = []
    candidates_1 = []
    for e in valid_ledger:
        if e.key is None:
            continue
        tok_lines = lines_by_token.get(e.key)
        if not tok_lines:
            continue
        # Binary search for lines within window
        i_start = bisect.bisect_left(tok_lines, e.ordinal - w_days, key=lambda l: l.ordinal)
        i_end = bisect.bisect_right(tok_lines, e.ordinal + w_days, key=lambda l: l.ordinal)
        for k in range(i_start, i_end):
            l = tok_lines[k]
            if l.amount == e.amount:
                delta = abs(e.ordinal - l.ordinal)
                candidates_1.append((delta, e.date_str, e.id, l.id, e, l))

    candidates_1.sort(key=lambda x: (x[0], x[1], x[2], x[3]))
    for delta, e_date, e_id, l_id, e, l in candidates_1:
        if e_id not in matched_ledger and l_id not in matched_bank:
            matched_ledger.add(e_id)
            matched_bank.add(l_id)
            matches_1.append({
                "type": "ref",
                "ledger": [e_id],
                "bank": [l_id],
                "difference": 0,
            })

    # -------------------------------------------------------------
    # Pass 2: "amount"
    # -------------------------------------------------------------
    matches_2 = []
    rem_entries_2 = [e for e in valid_ledger if e.id not in matched_ledger]
    rem_entries_2.sort(key=lambda e: (e.date_str, e.id))

    lines_by_amt_date_2 = collections.defaultdict(list)
    for l in valid_bank:
        if l.id not in matched_bank:
            lines_by_amt_date_2[(l.amount, l.ordinal)].append(l)

    for k in lines_by_amt_date_2:
        lines_by_amt_date_2[k].sort(key=lambda l: l.id)

    ptr_2 = {k: 0 for k in lines_by_amt_date_2}

    def get_next_line_2(amt, ord_val):
        key = (amt, ord_val)
        lines = lines_by_amt_date_2.get(key)
        if not lines:
            return None
        p = ptr_2[key]
        while p < len(lines):
            l = lines[p]
            if l.id not in matched_bank:
                ptr_2[key] = p
                return l
            p += 1
        ptr_2[key] = p
        return None

    for delta in range(w_days + 1):
        for e in rem_entries_2:
            if e.id in matched_ledger:
                continue
            cand1 = get_next_line_2(e.amount, e.ordinal - delta)
            cand2 = get_next_line_2(e.amount, e.ordinal + delta) if delta > 0 else None
            best_line = None
            if cand1 is not None and cand2 is not None:
                best_line = cand1 if cand1.id < cand2.id else cand2
            elif cand1 is not None:
                best_line = cand1
            elif cand2 is not None:
                best_line = cand2

            if best_line is not None:
                matched_ledger.add(e.id)
                matched_bank.add(best_line.id)
                matches_2.append({
                    "type": "amount",
                    "ledger": [e.id],
                    "bank": [best_line.id],
                    "difference": 0,
                })

    # -------------------------------------------------------------
    # Pass 3: "multi_ledger"
    # -------------------------------------------------------------
    matches_3 = []
    unmatched_bank_3 = [l for l in valid_bank if l.id not in matched_bank]
    unmatched_bank_3.sort(key=lambda l: (l.date_str, l.id))

    entries_by_day_3 = collections.defaultdict(list)
    for e in valid_ledger:
        entries_by_day_3[e.ordinal].append(e)

    for b_line in unmatched_bank_3:
        if b_line.id in matched_bank:
            continue

        parties_entries = collections.defaultdict(list)
        for day in range(b_line.ordinal - w_days, b_line.ordinal + w_days + 1):
            for e in entries_by_day_3.get(day, ()):
                if e.id not in matched_ledger and e.party != "":
                    parties_entries[e.party].append(e)

        best_group_2 = None
        for party, p_entries in parties_entries.items():
            n = len(p_entries)
            if n < 2:
                continue
            for i in range(n):
                for j in range(i + 1, n):
                    if p_entries[i].amount + p_entries[j].amount == b_line.amount:
                        delta_sum = (
                            abs(p_entries[i].ordinal - b_line.ordinal)
                            + abs(p_entries[j].ordinal - b_line.ordinal)
                        )
                        s_ids = (
                            [p_entries[i].id, p_entries[j].id]
                            if p_entries[i].id < p_entries[j].id
                            else [p_entries[j].id, p_entries[i].id]
                        )
                        score = (2, delta_sum, s_ids)
                        if best_group_2 is None or score < best_group_2[0]:
                            best_group_2 = (score, [p_entries[i], p_entries[j]])

        if best_group_2 is not None:
            matched_bank.add(b_line.id)
            for e in best_group_2[1]:
                matched_ledger.add(e.id)
            matches_3.append({
                "type": "multi_ledger",
                "ledger": best_group_2[0][2],
                "bank": [b_line.id],
                "difference": 0,
            })
            continue

        # Check 3-entry groups only if no 2-entry group exists
        best_group_3 = None
        for party, p_entries in parties_entries.items():
            n = len(p_entries)
            if n < 3:
                continue
            for i in range(n):
                for j in range(i + 1, n):
                    for m in range(j + 1, n):
                        if (
                            p_entries[i].amount + p_entries[j].amount + p_entries[m].amount
                            == b_line.amount
                        ):
                            delta_sum = (
                                abs(p_entries[i].ordinal - b_line.ordinal)
                                + abs(p_entries[j].ordinal - b_line.ordinal)
                                + abs(p_entries[m].ordinal - b_line.ordinal)
                            )
                            s_ids = sorted([
                                p_entries[i].id,
                                p_entries[j].id,
                                p_entries[m].id,
                            ])
                            score = (3, delta_sum, s_ids)
                            if best_group_3 is None or score < best_group_3[0]:
                                best_group_3 = (
                                    score,
                                    [p_entries[i], p_entries[j], p_entries[m]],
                                )

        if best_group_3 is not None:
            matched_bank.add(b_line.id)
            for e in best_group_3[1]:
                matched_ledger.add(e.id)
            matches_3.append({
                "type": "multi_ledger",
                "ledger": best_group_3[0][2],
                "bank": [b_line.id],
                "difference": 0,
            })

    # -------------------------------------------------------------
    # Pass 4: "multi_bank"
    # -------------------------------------------------------------
    matches_4 = []
    unmatched_ledger_4 = [
        e for e in valid_ledger if e.id not in matched_ledger and e.key is not None
    ]
    unmatched_ledger_4.sort(key=lambda e: (e.date_str, e.id))

    for entry in unmatched_ledger_4:
        if entry.id in matched_ledger:
            continue

        tok_lines = lines_by_token.get(entry.key, [])
        i_start = bisect.bisect_left(
            tok_lines, entry.ordinal - w_days, key=lambda l: l.ordinal
        )
        i_end = bisect.bisect_right(
            tok_lines, entry.ordinal + w_days, key=lambda l: l.ordinal
        )

        cand_lines = [
            tok_lines[k]
            for k in range(i_start, i_end)
            if tok_lines[k].id not in matched_bank
        ]
        n = len(cand_lines)
        if n < 2:
            continue

        best_group_2 = None
        for i in range(n):
            for j in range(i + 1, n):
                if cand_lines[i].amount + cand_lines[j].amount == entry.amount:
                    delta_sum = (
                        abs(cand_lines[i].ordinal - entry.ordinal)
                        + abs(cand_lines[j].ordinal - entry.ordinal)
                    )
                    s_ids = (
                        [cand_lines[i].id, cand_lines[j].id]
                        if cand_lines[i].id < cand_lines[j].id
                        else [cand_lines[j].id, cand_lines[i].id]
                    )
                    score = (2, delta_sum, s_ids)
                    if best_group_2 is None or score < best_group_2[0]:
                        best_group_2 = (score, [cand_lines[i], cand_lines[j]])

        if best_group_2 is not None:
            matched_ledger.add(entry.id)
            for l in best_group_2[1]:
                matched_bank.add(l.id)
            matches_4.append({
                "type": "multi_bank",
                "ledger": [entry.id],
                "bank": best_group_2[0][2],
                "difference": 0,
            })
            continue

        best_group_3 = None
        if n >= 3:
            for i in range(n):
                for j in range(i + 1, n):
                    for m in range(j + 1, n):
                        if (
                            cand_lines[i].amount
                            + cand_lines[j].amount
                            + cand_lines[m].amount
                            == entry.amount
                        ):
                            delta_sum = (
                                abs(cand_lines[i].ordinal - entry.ordinal)
                                + abs(cand_lines[j].ordinal - entry.ordinal)
                                + abs(cand_lines[m].ordinal - entry.ordinal)
                            )
                            s_ids = sorted([
                                cand_lines[i].id,
                                cand_lines[j].id,
                                cand_lines[m].id,
                            ])
                            score = (3, delta_sum, s_ids)
                            if best_group_3 is None or score < best_group_3[0]:
                                best_group_3 = (
                                    score,
                                    [cand_lines[i], cand_lines[j], cand_lines[m]],
                                )

        if best_group_3 is not None:
            matched_ledger.add(entry.id)
            for l in best_group_3[1]:
                matched_bank.add(l.id)
            matches_4.append({
                "type": "multi_bank",
                "ledger": [entry.id],
                "bank": best_group_3[0][2],
                "difference": 0,
            })

    # -------------------------------------------------------------
    # Pass 5: "fee"
    # -------------------------------------------------------------
    matches_5 = []
    if f_cents > 0:
        rem_entries_5 = [e for e in valid_ledger if e.id not in matched_ledger]
        rem_lines_5 = [l for l in valid_bank if l.id not in matched_bank]

        lines_by_day_5 = collections.defaultdict(list)
        for l in rem_lines_5:
            lines_by_day_5[l.ordinal].append(l)
        for day in lines_by_day_5:
            lines_by_day_5[day].sort(key=lambda l: l.amount)

        candidates_5 = []
        for e in rem_entries_5:
            low_amt = e.amount - f_cents
            high_amt = e.amount - 1
            if e.amount > 0:
                low_amt = max(low_amt, 1)
            else:
                high_amt = min(high_amt, -1)
            if low_amt > high_amt:
                continue

            for day in range(e.ordinal - w_days, e.ordinal + w_days + 1):
                day_lines = lines_by_day_5.get(day)
                if not day_lines:
                    continue
                i_start = bisect.bisect_left(day_lines, low_amt, key=lambda l: l.amount)
                i_end = bisect.bisect_right(day_lines, high_amt, key=lambda l: l.amount)
                for k in range(i_start, i_end):
                    l = day_lines[k]
                    fee = e.amount - l.amount
                    delta = abs(e.ordinal - l.ordinal)
                    candidates_5.append((delta, fee, e.date_str, e.id, l.id, e, l))

        candidates_5.sort(key=lambda x: (x[0], x[1], x[2], x[3], x[4]))
        for delta, fee, e_date, e_id, l_id, e, l in candidates_5:
            if e_id not in matched_ledger and l_id not in matched_bank:
                matched_ledger.add(e_id)
                matched_bank.add(l_id)
                matches_5.append({
                    "type": "fee",
                    "ledger": [e_id],
                    "bank": [l_id],
                    "difference": -fee,
                })

    all_matches = matches_1 + matches_2 + matches_3 + matches_4 + matches_5
    unmatched_ledger_final = [
        e.id for e in valid_ledger if e.id not in matched_ledger
    ]
    unmatched_bank_final = [
        l.id for l in valid_bank if l.id not in matched_bank
    ]

    return {
        "matches": all_matches,
        "unmatched_ledger": unmatched_ledger_final,
        "unmatched_bank": unmatched_bank_final,
        "invalid": {
            "ledger": invalid_ledger,
            "bank": invalid_bank,
        },
    }