# Problem 14: Bank reconciliation

Implement `def reconcile(ledger, bank, params)` in Python, using only the standard library. Money is integer cents.

Match the entries of a company's ledger against the lines of its bank statement.

- `ledger`: list of dicts `{"id": str, "date": "YYYY-MM-DD", "amount": int, "ref": str, "party": str}`.
- `bank`: list of dicts `{"id": str, "date": "YYYY-MM-DD", "amount": int, "text": str}`.
- `params`: `{"days": W, "fee_cents": F}`, ints with 0 ≤ W ≤ 31 and 0 ≤ F ≤ 10000. It is always well-formed.

A positive amount is money received, a negative amount money paid out, in both lists. Do not modify the inputs.

## 1. Validation

A record (ledger entry or bank line) is **invalid** if any of these holds:

1. It is not a dict, or it lacks one of its keys: `id`, `date`, `amount`, and also `ref` and `party` (ledger) or
   `text` (bank). Extra keys are ignored.
2. `id` is not a non-empty str.
3. `date` is not a str of exactly 10 characters `YYYY-MM-DD`, where `Y`, `M` and `D` are ASCII digits `0`–`9`,
   naming a real date with year 0001–9999 in the Gregorian calendar, applied to all years (no gap in 1582). So
   `2024-3-05`, `20240305` and `2024-03-05 ` are invalid. Leap years are those divisible by 4, except century years
   not divisible by 400 (`2000-02-29` is valid, `1900-02-29` is not).
4. `amount` is not an int, or is 0. `True` and `False` do not count as ints here, and neither does `100.0`.
5. `ref` or `party` (ledger), or `text` (bank), is not a str.
6. **Duplicate id.** Among the records of one list that pass checks 1–5, if two or more carry the same `id`, every
   one of them is invalid (not only the later ones). The two lists are separate: a ledger entry and a bank line may
   share an id.

Invalid records take no further part. From here on, an **entry** is a valid ledger record and a **line** is a valid
bank record.

## 2. Definitions

**Day distance.** Δ(x, y) is the absolute number of days between the dates of x and y: `2023-12-30` to
`2024-01-02` is 3, `2024-02-28` to `2024-03-01` is 2. An entry and a line are **within the window** if Δ ≤ W
(W = 0 means the same day).

**Id order.** Ids compare as strings, character by character by Unicode code point, a proper prefix before the longer
string (Python's `<` on `str`). So `"L10"` comes before `"L9"`. "(date, id) order" means ascending date, ties broken
by ascending id. A **sorted id list** is a list of ids in ascending id order.

**Tokens.** A *word character* is an ASCII letter (`A`–`Z`, `a`–`z`), an ASCII digit (`0`–`9`), or one of the three
*joiners* `-`, `_` and `.`. Every other character is a separator: space, tab, `#`, `:`, `/`, `,`, and every non-ASCII
character, including non-ASCII letters and digits. Each maximal run of word characters in a string gives at most one
token, made by these steps in order:

1. delete every joiner;
2. change lowercase letters to uppercase;
3. in every maximal run of digits, delete the leading zeros, but keep a single `0` if the run is all zeros.

A run that is empty after step 1 gives no token. Examples: `inv-00123` gives `INV123`; `INV_0012x007` gives
`INV12X7`; `1-007` gives `1007` (the joiner is gone before zeros are stripped); `000` gives `0`; `PO#77` gives `PO`
and `77`; `--` gives nothing.

The **tokens of a line** are the tokens of its `text`. An entry's **key** is the token of its `ref` if `ref` gives
exactly one token; if it gives none or several (`"INV 123"`), the entry has no key. A line **carries** a key if the
key equals one of its tokens. Only whole tokens count: key `INV12` is not carried by a line whose token is
`INV123`, and key `12` is not carried by `INV12`.

## 3. Matching

Five passes run in the order below. A pass sees only the entries and lines that no earlier pass matched, and no
record is ever matched twice.

**Pair passes (1, 2 and 5).** Each of these passes defines candidate pairs (one entry, one line) and a key for each
pair. Repeatedly take the candidate pair with the smallest key whose entry and line are both still unmatched, and
match them. Stop when no such pair is left. Keys are tuples compared element by element: numbers numerically, dates
chronologically, ids in id order.

1. **`"ref"`.** Candidate: the entry has a key, the line carries it, the two amounts are equal, and they are within
   the window. Key: (Δ, entry date, entry id, line id).
2. **`"amount"`.** Candidate: the two amounts are equal and they are within the window. Key: as in pass 1.
3. **`"multi_ledger"`** (one line settles several entries). Take the lines still unmatched in (date, id) order, one
   at a time. For a line b, a **candidate group** is a set of 2 or 3 entries, all unmatched at that moment, that
   - all have the same `party`, which is not the empty string (compared exactly: `"Acme"` and `"ACME"` differ),
   - are each within the window of b, and
   - have amounts summing to b's amount (entries of different signs may be combined).

   If b has candidate groups, match b with the best one, chosen by: (a) fewest entries; then (b) the smallest sum of
   Δ(entry, b) over the group; then (c) the smallest sorted id list, comparing the lists element by element.
   Otherwise b stays unmatched. Then go on to the next line.
4. **`"multi_bank"`** (several lines settle one entry). The same with the roles swapped. Take the entries still
   unmatched in (date, id) order, one at a time; an entry without a key is skipped. For an entry e, a candidate group
   is a set of 2 or 3 lines, all unmatched at that moment, that each carry e's key, are each within the window of e,
   and have amounts summing to e's amount. Choose the best group by rules (a)–(c) of pass 3, using Δ(line, e) and
   the lines' ids.
5. **`"fee"`** (the bank kept a fee). For an entry and a line, fee = entry amount − line amount. Candidate: the two
   amounts have the same sign, 1 ≤ fee ≤ F, and they are within the window. The fee always lowers the bank amount,
   whatever the sign: entry `10000` with line `9975` is a fee of 25, and so is entry `-10000` with line `-10025`
   (more money left the account), but entry `-10000` with line `-9975` is not a candidate. Key: (Δ, fee, entry
   date, entry id, line id).

## 4. Output

```python
{"matches": [{"type": t, "ledger": [entry ids], "bank": [line ids], "difference": d}, ...],
 "unmatched_ledger": [entry ids], "unmatched_bank": [line ids],
 "invalid": {"ledger": [positions], "bank": [positions]}}
```

- `type` is the pass name in quotes above. `ledger` and `bank` are sorted id lists. `difference` is (sum of the
  match's line amounts) − (sum of its entry amounts): 0, except −fee for a `"fee"` match.
- `matches` are grouped by pass, 1 to 5. Within passes 1, 2 and 5 they appear in the order they were taken
  (ascending key); within passes 3 and 4 in processing order.
- `unmatched_ledger` and `unmatched_bank` list the ids of the entries and lines in no match, in input order.
- `invalid` lists the 0-based positions of the invalid records in each input list, ascending.

## Size

Each list has up to 20 000 records; `ref` and `text` are at most 100 characters. In every test, no line has more than
30 entries of one party within its window, and no entry has more than 30 lines carrying its key within its window.
The whole call must finish within a few seconds in CPython on a typical laptop. Comparing every entry with every
line, or scanning a whole list once per record, is far too slow at this size.

## Examples

Example 1 (key normalisation, a reference match, exact-amount matches across a leap day):

```python
reconcile(
    [{"id": "L1", "date": "2024-01-30", "amount": 12500, "ref": "INV-0042", "party": "Acme"},
     {"id": "L2", "date": "2024-02-01", "amount": 12500, "ref": "INV-0043", "party": "Acme"},
     {"id": "L3", "date": "2024-02-27", "amount": -4999, "ref": "", "party": "Telco"}],
    [{"id": "B1", "date": "2024-02-01", "amount": 12500, "text": "SEPA CR ACME LTD inv42"},
     {"id": "B2", "date": "2024-02-02", "amount": 12500, "text": "ACME PAYMENT"},
     {"id": "B3", "date": "2024-03-01", "amount": -4999, "text": "DD TELCO 0043"}],
    {"days": 3, "fee_cents": 0})
# L1's key is INV42, carried by B1. L2's key INV43 is not carried by B3 (its token is 43). L3 has no key.
# -> {"matches": [{"type": "ref", "ledger": ["L1"], "bank": ["B1"], "difference": 0},
#                 {"type": "amount", "ledger": ["L2"], "bank": ["B2"], "difference": 0},
#                 {"type": "amount", "ledger": ["L3"], "bank": ["B3"], "difference": 0}],
#     "unmatched_ledger": [], "unmatched_bank": [], "invalid": {"ledger": [], "bank": []}}
```

Example 2 (one line settles two entries of one party; two lines carrying a key settle one entry):

```python
reconcile(
    [{"id": "L1", "date": "2024-03-04", "amount": 30000, "ref": "PO-7", "party": "Beta"},
     {"id": "L2", "date": "2024-03-05", "amount": 12000, "ref": "PO-8", "party": "Beta"},
     {"id": "L3", "date": "2024-03-06", "amount": 8000, "ref": "PO-9", "party": "Beta"},
     {"id": "L4", "date": "2024-03-06", "amount": 8000, "ref": "PO-10", "party": "Gamma"},
     {"id": "L5", "date": "2024-03-10", "amount": 50000, "ref": "C-551", "party": "Delta"}],
    [{"id": "B1", "date": "2024-03-06", "amount": 20000, "text": "BETA GROUP"},
     {"id": "B2", "date": "2024-03-09", "amount": 20000, "text": "DELTA C551 PART 1"},
     {"id": "B3", "date": "2024-03-12", "amount": 30000, "text": "DELTA C-551 PART 2"}],
    {"days": 2, "fee_cents": 0})
# L2 + L4 also make 20000, but their parties differ. L1 and B3 are 8 days apart.
# -> {"matches": [{"type": "multi_ledger", "ledger": ["L2", "L3"], "bank": ["B1"], "difference": 0},
#                 {"type": "multi_bank", "ledger": ["L5"], "bank": ["B2", "B3"], "difference": 0}],
#     "unmatched_ledger": ["L1", "L4"], "unmatched_bank": [], "invalid": {"ledger": [], "bank": []}}
```

Example 3 (fee matches across a year end; Δ decides before the fee does):

```python
reconcile(
    [{"id": "L1", "date": "2024-12-30", "amount": 10000, "ref": "", "party": "Kappa"},
     {"id": "L2", "date": "2024-12-31", "amount": 10000, "ref": "", "party": "Kappa"},
     {"id": "L3", "date": "2025-01-02", "amount": 5000, "ref": "", "party": "Kappa"}],
    [{"id": "B1", "date": "2025-01-02", "amount": 9980, "text": "KAPPA"},
     {"id": "B2", "date": "2025-01-03", "amount": 9990, "text": "KAPPA"},
     {"id": "B3", "date": "2025-01-02", "amount": 4940, "text": "KAPPA"}],
    {"days": 5, "fee_cents": 50})
# Candidate keys, smallest first: (2, 20, 2024-12-31, L2, B1), (3, 10, 2024-12-31, L2, B2),
# (3, 20, 2024-12-30, L1, B1), (4, 10, 2024-12-30, L1, B2). L3 with B3 would be a fee of 60 > 50.
# -> {"matches": [{"type": "fee", "ledger": ["L2"], "bank": ["B1"], "difference": -20},
#                 {"type": "fee", "ledger": ["L1"], "bank": ["B2"], "difference": -10}],
#     "unmatched_ledger": ["L3"], "unmatched_bank": ["B3"], "invalid": {"ledger": [], "bank": []}}
```

Example 4 (invalid records; a reference match beats a closer exact-amount line):

```python
reconcile(
    [{"id": "L1", "date": "2024-03-01", "amount": 900, "ref": "INV-5", "party": "Zed"},
     {"id": "L2", "date": "2024-02-30", "amount": 900, "ref": "INV-6", "party": "Zed"},
     {"id": "L3", "date": "2024-03-02", "amount": 0, "ref": "INV-7", "party": "Zed"}],
    [{"id": "B1", "date": "2024-03-01", "amount": 900, "text": "STRIPE PAYOUT"},
     {"id": "B2", "date": "2024-03-03", "amount": 900, "text": "Zed inv5"},
     {"id": "B3", "date": "2024-03-02", "amount": 850, "text": "INV-5"},
     {"id": "B4", "date": "2024-03-02", "amount": "850", "text": "x"},
     {"id": "B5", "date": "2024-03-02", "text": "y"}],
    {"days": 3, "fee_cents": 100})
# B3 carries INV5 but its amount differs, and it is not a fee match because L1 is already matched.
# -> {"matches": [{"type": "ref", "ledger": ["L1"], "bank": ["B2"], "difference": 0}],
#     "unmatched_ledger": [], "unmatched_bank": ["B1", "B3"], "invalid": {"ledger": [1, 2], "bank": [3, 4]}}
```
