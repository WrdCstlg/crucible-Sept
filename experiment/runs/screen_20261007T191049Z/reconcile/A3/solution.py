import bisect
import collections
import datetime
import re


def _is_valid_date(date_str):
    if not isinstance(date_str, str) or len(date_str) != 10:
        return False
    if date_str[4] != '-' or date_str[7] != '-':
        return False
    for c in date_str[:4] + date_str[5:7] + date_str[8:]:
        if c not in '0123456789':
            return False
    y = int(date_str[:4])
    m = int(date_str[5:7])
    d = int(date_str[8:])
    if not (1 <= y <= 9999):
        return False
    try:
        datetime.date(y, m, d)
    except ValueError:
        return False
    return True


def _tokenize(s):
    runs = re.findall(r'[A-Za-z0-9._\-]+', s)
    tokens = []
    for run in runs:
        run = run.replace('-', '').replace('_', '').replace('.', '')
        if not run:
            continue
        run = run.upper()
        run = re.sub(r'[0-9]+', lambda m: m.group(0).lstrip('0') or '0', run)
        tokens.append(run)
    return tokens


def _validate_ledger_record(rec):
    if not isinstance(rec, dict):
        return False
    if not ('id' in rec and 'date' in rec and 'amount' in rec and 'ref' in rec and 'party' in rec):
        return False
    rec_id = rec['id']
    if not isinstance(rec_id, str) or len(rec_id) == 0:
        return False
    if not _is_valid_date(rec['date']):
        return False
    amt = rec['amount']
    if type(amt) is not int or amt == 0:
        return False
    if not isinstance(rec['ref'], str) or not isinstance(rec['party'], str):
        return False
    return True


def _validate_bank_record(rec):
    if not isinstance(rec, dict):
        return False
    if not ('id' in rec and 'date' in rec and 'amount' in rec and 'text' in rec):
        return False
    rec_id = rec['id']
    if not isinstance(rec_id, str) or len(rec_id) == 0:
        return False
    if not _is_valid_date(rec['date']):
        return False
    amt = rec['amount']
    if type(amt) is not int or amt == 0:
        return False
    if not isinstance(rec['text'], str):
        return False
    return True


class _Entry:
    __slots__ = ('idx', 'id', 'date_str', 'date_ord', 'amount', 'ref', 'party', 'key', 'matched')

    def __init__(self, idx, rec):
        self.idx = idx
        self.id = rec['id']
        self.date_str = rec['date']
        self.date_ord = datetime.date(
            int(rec['date'][:4]), int(rec['date'][5:7]), int(rec['date'][8:])
        ).toordinal()
        self.amount = rec['amount']
        self.ref = rec['ref']
        self.party = rec['party']
        tokens = _tokenize(self.ref)
        self.key = tokens[0] if len(tokens) == 1 else None
        self.matched = False


class _Line:
    __slots__ = ('idx', 'id', 'date_str', 'date_ord', 'amount', 'text', 'tokens_set', 'matched')

    def __init__(self, idx, rec):
        self.idx = idx
        self.id = rec['id']
        self.date_str = rec['date']
        self.date_ord = datetime.date(
            int(rec['date'][:4]), int(rec['date'][5:7]), int(rec['date'][8:])
        ).toordinal()
        self.amount = rec['amount']
        self.text = rec['text']
        self.tokens_set = set(_tokenize(self.text))
        self.matched = False


def reconcile(ledger, bank, params):
    w = params['days']
    fee_limit = params['fee_cents']

    # --- 1. Validation ---
    ledger_invalid_positions = []
    ledger_valid_temp = []
    for i, rec in enumerate(ledger):
        if _validate_ledger_record(rec):
            ledger_valid_temp.append((i, rec))
        else:
            ledger_invalid_positions.append(i)

    id_counts_ledger = collections.Counter(rec['id'] for _, rec in ledger_valid_temp)
    valid_entries = []
    for i, rec in ledger_valid_temp:
        if id_counts_ledger[rec['id']] > 1:
            ledger_invalid_positions.append(i)
        else:
            valid_entries.append(_Entry(i, rec))
    ledger_invalid_positions.sort()

    bank_invalid_positions = []
    bank_valid_temp = []
    for i, rec in enumerate(bank):
        if _validate_bank_record(rec):
            bank_valid_temp.append((i, rec))
        else:
            bank_invalid_positions.append(i)

    id_counts_bank = collections.Counter(rec['id'] for _, rec in bank_valid_temp)
    valid_lines = []
    for i, rec in bank_valid_temp:
        if id_counts_bank[rec['id']] > 1:
            bank_invalid_positions.append(i)
        else:
            valid_lines.append(_Line(i, rec))
    bank_invalid_positions.sort()

    # Pre-index lines by token for passes 1 and 4
    lines_by_token = collections.defaultdict(list)
    for line in valid_lines:
        for t in line.tokens_set:
            lines_by_token[t].append(line)

    matches_pass1 = []
    matches_pass2 = []
    matches_pass3 = []
    matches_pass4 = []
    matches_pass5 = []

    # --- Pass 1: "ref" ---
    entries_by_key_amount = collections.defaultdict(list)
    for e in valid_entries:
        if e.key is not None:
            entries_by_key_amount[(e.key, e.amount)].append(e)

    pass1_candidates = []
    for line in valid_lines:
        for token in line.tokens_set:
            matching_entries = entries_by_key_amount.get((token, line.amount))
            if matching_entries:
                for e in matching_entries:
                    delta = abs(e.date_ord - line.date_ord)
                    if delta <= w:
                        key = (delta, e.date_ord, e.id, line.id)
                        pass1_candidates.append((key, e, line))

    pass1_candidates.sort(key=lambda c: c[0])
    for _, e, line in pass1_candidates:
        if not e.matched and not line.matched:
            e.matched = True
            line.matched = True
            matches_pass1.append({
                "type": "ref",
                "ledger": [e.id],
                "bank": [line.id],
                "difference": 0
            })

    # --- Pass 2: "amount" ---
    unmatched_entries_by_amount = collections.defaultdict(list)
    for e in valid_entries:
        if not e.matched:
            unmatched_entries_by_amount[e.amount].append(e)

    unmatched_lines_by_amount = collections.defaultdict(list)
    for line in valid_lines:
        if not line.matched:
            unmatched_lines_by_amount[line.amount].append(line)

    pass2_matched_items = []
    for amt, elist in unmatched_entries_by_amount.items():
        llist = unmatched_lines_by_amount.get(amt)
        if not llist:
            continue
        amt_candidates = []
        if len(llist) > 10:
            llist.sort(key=lambda l: l.date_ord)
            ldates = [l.date_ord for l in llist]
            for e in elist:
                i_start = bisect.bisect_left(ldates, e.date_ord - w)
                i_end = bisect.bisect_right(ldates, e.date_ord + w)
                for line in llist[i_start:i_end]:
                    delta = abs(e.date_ord - line.date_ord)
                    amt_candidates.append(((delta, e.date_ord, e.id, line.id), e, line))
        else:
            for e in elist:
                for line in llist:
                    delta = abs(e.date_ord - line.date_ord)
                    if delta <= w:
                        amt_candidates.append(((delta, e.date_ord, e.id, line.id), e, line))

        amt_candidates.sort(key=lambda c: c[0])
        for key, e, line in amt_candidates:
            if not e.matched and not line.matched:
                e.matched = True
                line.matched = True
                pass2_matched_items.append((key, {
                    "type": "amount",
                    "ledger": [e.id],
                    "bank": [line.id],
                    "difference": 0
                }))

    pass2_matched_items.sort(key=lambda item: item[0])
    matches_pass2 = [item[1] for item in pass2_matched_items]

    # --- Pass 3: "multi_ledger" ---
    unmatched_lines_p3 = [l for l in valid_lines if not l.matched]
    unmatched_lines_p3.sort(key=lambda l: (l.date_ord, l.id))

    unmatched_entries_p3 = [e for e in valid_entries if not e.matched and e.party != ""]
    unmatched_entries_p3.sort(key=lambda e: e.date_ord)

    window_party_entries = collections.defaultdict(set)
    eligible_parties = set()
    left_idx = 0
    right_idx = 0
    n_p3_entries = len(unmatched_entries_p3)

    for line in unmatched_lines_p3:
        while right_idx < n_p3_entries and unmatched_entries_p3[right_idx].date_ord <= line.date_ord + w:
            entry = unmatched_entries_p3[right_idx]
            if not entry.matched:
                p_set = window_party_entries[entry.party]
                p_set.add(entry)
                if len(p_set) == 2:
                    eligible_parties.add(entry.party)
            right_idx += 1

        while left_idx < right_idx and unmatched_entries_p3[left_idx].date_ord < line.date_ord - w:
            entry = unmatched_entries_p3[left_idx]
            p_set = window_party_entries[entry.party]
            if entry in p_set:
                p_set.remove(entry)
                if len(p_set) < 2:
                    eligible_parties.discard(entry.party)
            left_idx += 1

        best_2 = None
        best_2_key = None
        for party in eligible_parties:
            elist = list(window_party_entries[party])
            amounts = [e.amount for e in elist]
            pos = any(a > 0 for a in amounts)
            neg = any(a < 0 for a in amounts)
            if not pos and line.amount >= 0:
                continue
            if not neg and line.amount <= 0:
                continue

            n_elist = len(elist)
            for i in range(n_elist):
                e1 = elist[i]
                for j in range(i + 1, n_elist):
                    e2 = elist[j]
                    if e1.amount + e2.amount == line.amount:
                        delta_sum = abs(e1.date_ord - line.date_ord) + abs(e2.date_ord - line.date_ord)
                        sorted_ids = sorted([e1.id, e2.id])
                        cand_key = (delta_sum, sorted_ids)
                        if best_2_key is None or cand_key < best_2_key:
                            best_2_key = cand_key
                            best_2 = (e1, e2)

        if best_2 is not None:
            e1, e2 = best_2
            e1.matched = True
            e2.matched = True
            line.matched = True
            for me in (e1, e2):
                p_set = window_party_entries[me.party]
                if me in p_set:
                    p_set.remove(me)
                    if len(p_set) < 2:
                        eligible_parties.discard(me.party)
            matches_pass3.append({
                "type": "multi_ledger",
                "ledger": sorted([e1.id, e2.id]),
                "bank": [line.id],
                "difference": 0
            })
            continue

        best_3 = None
        best_3_key = None
        for party in eligible_parties:
            elist = list(window_party_entries[party])
            if len(elist) < 3:
                continue
            amounts = [e.amount for e in elist]
            pos = any(a > 0 for a in amounts)
            neg = any(a < 0 for a in amounts)
            if not pos and line.amount >= 0:
                continue
            if not neg and line.amount <= 0:
                continue

            n_elist = len(elist)
            for i in range(n_elist):
                e1 = elist[i]
                for j in range(i + 1, n_elist):
                    e2 = elist[j]
                    for k in range(j + 1, n_elist):
                        e3 = elist[k]
                        if e1.amount + e2.amount + e3.amount == line.amount:
                            delta_sum = (
                                abs(e1.date_ord - line.date_ord)
                                + abs(e2.date_ord - line.date_ord)
                                + abs(e3.date_ord - line.date_ord)
                            )
                            sorted_ids = sorted([e1.id, e2.id, e3.id])
                            cand_key = (delta_sum, sorted_ids)
                            if best_3_key is None or cand_key < best_3_key:
                                best_3_key = cand_key
                                best_3 = (e1, e2, e3)

        if best_3 is not None:
            e1, e2, e3 = best_3
            e1.matched = True
            e2.matched = True
            e3.matched = True
            line.matched = True
            for me in (e1, e2, e3):
                p_set = window_party_entries[me.party]
                if me in p_set:
                    p_set.remove(me)
                    if len(p_set) < 2:
                        eligible_parties.discard(me.party)
            matches_pass3.append({
                "type": "multi_ledger",
                "ledger": sorted([e1.id, e2.id, e3.id]),
                "bank": [line.id],
                "difference": 0
            })

    # --- Pass 4: "multi_bank" ---
    unmatched_entries_p4 = [e for e in valid_entries if not e.matched and e.key is not None]
    unmatched_entries_p4.sort(key=lambda e: (e.date_ord, e.id))

    for entry in unmatched_entries_p4:
        cand_lines = [
            l for l in lines_by_token.get(entry.key, [])
            if not l.matched and abs(l.date_ord - entry.date_ord) <= w
        ]
        if len(cand_lines) < 2:
            continue

        amounts = [l.amount for l in cand_lines]
        pos = any(a > 0 for a in amounts)
        neg = any(a < 0 for a in amounts)
        if not pos and entry.amount >= 0:
            continue
        if not neg and entry.amount <= 0:
            continue

        n_cand = len(cand_lines)
        best_2 = None
        best_2_key = None
        for i in range(n_cand):
            l1 = cand_lines[i]
            for j in range(i + 1, n_cand):
                l2 = cand_lines[j]
                if l1.amount + l2.amount == entry.amount:
                    delta_sum = abs(l1.date_ord - entry.date_ord) + abs(l2.date_ord - entry.date_ord)
                    sorted_ids = sorted([l1.id, l2.id])
                    cand_key = (delta_sum, sorted_ids)
                    if best_2_key is None or cand_key < best_2_key:
                        best_2_key = cand_key
                        best_2 = (l1, l2)

        if best_2 is not None:
            l1, l2 = best_2
            l1.matched = True
            l2.matched = True
            entry.matched = True
            matches_pass4.append({
                "type": "multi_bank",
                "ledger": [entry.id],
                "bank": sorted([l1.id, l2.id]),
                "difference": 0
            })
            continue

        if n_cand >= 3:
            best_3 = None
            best_3_key = None
            for i in range(n_cand):
                l1 = cand_lines[i]
                for j in range(i + 1, n_cand):
                    l2 = cand_lines[j]
                    for k in range(j + 1, n_cand):
                        l3 = cand_lines[k]
                        if l1.amount + l2.amount + l3.amount == entry.amount:
                            delta_sum = (
                                abs(l1.date_ord - entry.date_ord)
                                + abs(l2.date_ord - entry.date_ord)
                                + abs(l3.date_ord - entry.date_ord)
                            )
                            sorted_ids = sorted([l1.id, l2.id, l3.id])
                            cand_key = (delta_sum, sorted_ids)
                            if best_3_key is None or cand_key < best_3_key:
                                best_3_key = cand_key
                                best_3 = (l1, l2, l3)

            if best_3 is not None:
                l1, l2, l3 = best_3
                l1.matched = True
                l2.matched = True
                l3.matched = True
                entry.matched = True
                matches_pass4.append({
                    "type": "multi_bank",
                    "ledger": [entry.id],
                    "bank": sorted([l1.id, l2.id, l3.id]),
                    "difference": 0
                })

    # --- Pass 5: "fee" ---
    if fee_limit > 0:
        pos_entries = [e for e in valid_entries if not e.matched and e.amount > 0]
        neg_entries = [e for e in valid_entries if not e.matched and e.amount < 0]
        pos_lines = [l for l in valid_lines if not l.matched and l.amount > 0]
        neg_lines = [l for l in valid_lines if not l.matched and l.amount < 0]

        pass5_candidates = []

        if pos_entries and pos_lines:
            pos_lines.sort(key=lambda l: l.amount)
            pos_line_amounts = [l.amount for l in pos_lines]
            for e in pos_entries:
                i_start = bisect.bisect_left(pos_line_amounts, e.amount - fee_limit)
                i_end = bisect.bisect_right(pos_line_amounts, e.amount - 1)
                for line in pos_lines[i_start:i_end]:
                    delta = abs(e.date_ord - line.date_ord)
                    if delta <= w:
                        fee = e.amount - line.amount
                        key = (delta, fee, e.date_ord, e.id, line.id)
                        pass5_candidates.append((key, e, line, fee))

        if neg_entries and neg_lines:
            neg_lines.sort(key=lambda l: l.amount)
            neg_line_amounts = [l.amount for l in neg_lines]
            for e in neg_entries:
                i_start = bisect.bisect_left(neg_line_amounts, e.amount - fee_limit)
                i_end = bisect.bisect_right(neg_line_amounts, e.amount - 1)
                for line in neg_lines[i_start:i_end]:
                    delta = abs(e.date_ord - line.date_ord)
                    if delta <= w:
                        fee = e.amount - line.amount
                        key = (delta, fee, e.date_ord, e.id, line.id)
                        pass5_candidates.append((key, e, line, fee))

        pass5_candidates.sort(key=lambda c: c[0])
        for _, e, line, fee in pass5_candidates:
            if not e.matched and not line.matched:
                e.matched = True
                line.matched = True
                matches_pass5.append({
                    "type": "fee",
                    "ledger": [e.id],
                    "bank": [line.id],
                    "difference": -fee
                })

    # --- Output ---
    all_matches = matches_pass1 + matches_pass2 + matches_pass3 + matches_pass4 + matches_pass5
    unmatched_ledger = [e.id for e in valid_entries if not e.matched]
    unmatched_bank = [l.id for l in valid_lines if not l.matched]

    return {
        "matches": all_matches,
        "unmatched_ledger": unmatched_ledger,
        "unmatched_bank": unmatched_bank,
        "invalid": {
            "ledger": ledger_invalid_positions,
            "bank": bank_invalid_positions
        }
    }