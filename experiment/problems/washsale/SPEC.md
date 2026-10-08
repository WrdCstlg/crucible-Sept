# Problem 12: Tax lots with wash sales

Implement `def compute_gains(trades, identical)` in Python, using only the standard library.

A simplified model of share-lot accounting with a wash-sale rule. It deliberately differs from real tax law in places:
follow this text only. Money is integer cents. Every `//` below is floor division of non-negative integers.

## Input

- `trades`: a list of dicts, each meant to have the keys `"date"`, `"side"`, `"symbol"`, `"qty"` and `"amount"`.
  `amount` is the total for the whole trade: what was paid for a BUY, what was received for a SELL.
- `identical`: a list of lists of non-empty strings. Symbols listed together are **identical**. The relation is
  transitive: lists that share a symbol merge into one **group** (`[["A", "B"], ["B", "C"]]` makes A, B and C one
  group). A symbol that appears in no list is a group by itself. Symbols are compared exactly (case-sensitive).

## 1. Validation and processing order

A trade is **invalid** if a key is missing (extra keys are ignored) or if:
- `date` is not a string of exactly 10 characters `YYYY-MM-DD`, ASCII digits only, forming a real Gregorian date with
  year 1900–2099;
- `side` is not exactly `"BUY"` or `"SELL"`;
- `symbol` is not a non-empty string;
- `qty` is not an int ≥ 1, or `amount` is not an int ≥ 0 (a `bool` or a `float` is never an int here).

Invalid trades are **rejected** and have no effect. The valid trades are processed one at a time in **processing
order**: by date, then by input index. When a valid SELL is reached, it is also **rejected** (no effect) if its `qty`
exceeds the shares of **that same symbol** currently held (bought earlier in processing order and not yet sold).
Shares of other symbols in the group do not count for this check.

## 2. Lots and pieces

Every valid BUY creates a **lot**, identified by the BUY's input index; its **acquisition date** is the BUY's date.
All lots exist from the very start, so a sale can adjust a lot whose BUY comes later (section 4). A lot's shares are
held, and can be sold, only from its BUY onwards in processing order.

A lot is an ordered list of **pieces**. A piece has a qty, a basis (cents) and a number of **carried days** (≥ 0).
A new lot has a single **fresh** piece: the BUY's qty, basis = its amount, carried days 0. Wash sales (section 4)
turn fresh shares into **replacement** pieces. A lot's pieces are always kept in this order: its replacement pieces in the
order they were created, then its fresh piece. Pieces are never merged, and a piece with 0 shares is gone. A piece's
**holding start** is the lot's acquisition date minus the piece's carried days.

**Split rule.** Taking k shares out of a piece of q shares with basis B: the taken shares get basis `B * k // q`; the
piece keeps q − k shares and basis `B - B * k // q`.

## 3. Selling

A valid, accepted SELL of k shares of symbol X takes shares from X's held lots in FIFO order (acquisition date, then
input index), and within a lot from its pieces in order, splitting a piece by the split rule when only part of it is
needed. Each piece (or part of a piece) taken is one **row**; the order in which rows are taken is the **draw order**.

**Proceeds.** The SELL's amount is spread over its rows in draw order: with R cents and Q shares not yet allocated
(at first R = amount and Q = k), a row of n shares gets proceeds `R * n // Q`, and then R and Q drop by those
amounts (so the last row gets whatever is left).

For each row, gain = proceeds − basis. A row with gain < 0 is a **loss row**, with loss L = −gain. A row's
**holding days** = sale date − its piece's holding start, in days.

## 4. Wash sales

After all rows of the sale have been taken, its loss rows are handled one at a time, in draw order. For a loss row
of n shares with loss L, sale date t, symbol X:

1. **Candidates** are lots that meet all of these at this moment:
   - the lot's symbol is in X's group (X itself included);
   - its acquisition date is between t − 30 and t + 30 (calendar days, both ends included); the lot may be bought
     before or after the sale;
   - it has fresh shares (its fresh piece is not empty; for a lot bought earlier, shares sold or already used as
     replacement are not fresh);
   - this SELL took **no** shares from it in any row. A lot this sale draws from is never a candidate for this sale,
     not even its unsold shares.
2. Visit candidates by acquisition date, then input index. From each take c = min(shares still needed, its fresh
   qty), until n shares are found or the candidates run out. Let r be the number found. If r = 0, the row disallows
   nothing; stop.
3. **Disallowed** D = `L * r // n`.
4. Spread D over the chunks found, in visit order, by the same running rule as proceeds: with R = D and Q = r at
   first, a chunk of c shares gets `R * c // Q`, then R and Q drop by those amounts.
5. For each chunk (c shares of lot P, with share d of D): take c shares out of P's fresh piece by the split rule.
   They become a new replacement piece of P with basis = (their split basis) + d and carried days = the loss row's
   holding days. It goes after P's existing replacement pieces, before its fresh piece.

Step 5 happens even when D is 0. Replacement pieces are never candidates (a share is used as replacement at most
once), but they can be sold, and a loss on them is again a loss row (wash sales chain). Rows with gain ≥ 0 have
D = 0 and use no candidate shares.

## 5. Term

A row is `"LONG"` if the sale date is later than the first anniversary of its piece's holding start, otherwise
`"SHORT"`. The first anniversary of a date is the same month and day one year later, except that the anniversary of
February 29 is March 1 of the next year. Long wash chains can push a holding start very far back, even before year
1, so work with day numbers: a holding start more than 366 days before the sale date is always `"LONG"`.

## Output

```python
{"realized": [{"sale": i, "lot": j, "qty": n, "proceeds": p, "basis": b, "gain": p - b,
               "disallowed": D, "term": "SHORT" or "LONG"}, ...],
 "open_lots": [{"lot": j, "qty": n, "basis": b, "carried_days": c}, ...],
 "rejected": [...],
 "totals": {"short_term": ..., "long_term": ..., "disallowed": ...}}
```

- `realized`: one entry per row, sorted by the SELL's **input index** `i` (not processing order), then draw order.
- `open_lots`: every piece still held after all trades, ordered by lot (acquisition date, then input index), then by
  piece order within the lot.
- `rejected`: input indices of invalid trades and rejected SELLs, ascending.
- `totals`: `short_term` is the sum of gain + disallowed over `"SHORT"` rows, `long_term` the same over `"LONG"` rows,
  and `disallowed` the sum of all D.

All numbers are ints. `realized`, `open_lots` and `rejected` may be empty.

## Size

Up to 200 000 trades and 2 000 symbols; qty up to 10^9, amount up to 10^12. The whole call must finish within a few
seconds in CPython. Windows can hold thousands of lots with no fresh shares left, so a loss row must not rescan its
window (let alone every lot) from the start; wash chains can be 100 000 sales long.

## Examples

Example 1 (a repurchase after the loss replaces part of it):

```python
compute_gains([{"date": "2024-01-10", "side": "BUY", "symbol": "XYZ", "qty": 10, "amount": 1000},
               {"date": "2024-03-01", "side": "SELL", "symbol": "XYZ", "qty": 10, "amount": 700},
               {"date": "2024-03-20", "side": "BUY", "symbol": "XYZ", "qty": 4, "amount": 360}], [])
# loss 300 on 10 shares, 4 replaced: D = 300 * 4 // 10 = 120; holding days 2024-01-10 -> 2024-03-01 = 51
# -> {"realized": [{"sale": 1, "lot": 0, "qty": 10, "proceeds": 700, "basis": 1000, "gain": -300,
#                   "disallowed": 120, "term": "SHORT"}],
#     "open_lots": [{"lot": 2, "qty": 4, "basis": 480, "carried_days": 51}],
#     "rejected": [], "totals": {"short_term": -180, "long_term": 0, "disallowed": 120}}
```

Example 2 (earlier purchases of an identical symbol count; one sale, two loss rows):

```python
compute_gains([{"date": "2024-01-02", "side": "BUY", "symbol": "AAA", "qty": 6, "amount": 600},
               {"date": "2024-01-03", "side": "BUY", "symbol": "AAA", "qty": 4, "amount": 500},
               {"date": "2024-02-10", "side": "BUY", "symbol": "BBB", "qty": 3, "amount": 270},
               {"date": "2024-02-20", "side": "SELL", "symbol": "AAA", "qty": 8, "amount": 640},
               {"date": "2024-03-05", "side": "BUY", "symbol": "AAA", "qty": 10, "amount": 800}],
              [["AAA", "BBB"]])
# row 1 (lot 0) takes 3 shares of lot 2 and 3 of lot 4 (D 120 -> 60 + 60); row 2 (lot 1) takes 2 more of lot 4
# -> {"realized": [{"sale": 3, "lot": 0, "qty": 6, "proceeds": 480, "basis": 600, "gain": -120,
#                   "disallowed": 120, "term": "SHORT"},
#                  {"sale": 3, "lot": 1, "qty": 2, "proceeds": 160, "basis": 250, "gain": -90,
#                   "disallowed": 90, "term": "SHORT"}],
#     "open_lots": [{"lot": 1, "qty": 2, "basis": 250, "carried_days": 0},
#                   {"lot": 2, "qty": 3, "basis": 330, "carried_days": 49},
#                   {"lot": 4, "qty": 3, "basis": 300, "carried_days": 49},
#                   {"lot": 4, "qty": 2, "basis": 250, "carried_days": 48},
#                   {"lot": 4, "qty": 5, "basis": 400, "carried_days": 0}],
#     "rejected": [], "totals": {"short_term": 0, "long_term": 0, "disallowed": 210}}
```

Example 3 (a chain: the replacement is itself sold at a loss; carried days make it long-term):

```python
compute_gains([{"date": "2022-05-10", "side": "BUY", "symbol": "QQ", "qty": 5, "amount": 500},
               {"date": "2023-06-01", "side": "SELL", "symbol": "QQ", "qty": 5, "amount": 400},
               {"date": "2023-06-15", "side": "BUY", "symbol": "QQ", "qty": 5, "amount": 450},
               {"date": "2023-07-01", "side": "SELL", "symbol": "QQ", "qty": 5, "amount": 500},
               {"date": "2023-07-20", "side": "BUY", "symbol": "QQ", "qty": 2, "amount": 180}], [])
# lot 2 gets basis 550, carried 387 (holding start 2022-05-24); its sale loses 50, and 50 * 2 // 5 = 20 moves to lot 4
# -> {"realized": [{"sale": 1, "lot": 0, "qty": 5, "proceeds": 400, "basis": 500, "gain": -100,
#                   "disallowed": 100, "term": "LONG"},
#                  {"sale": 3, "lot": 2, "qty": 5, "proceeds": 500, "basis": 550, "gain": -50,
#                   "disallowed": 20, "term": "LONG"}],
#     "open_lots": [{"lot": 4, "qty": 2, "basis": 200, "carried_days": 403}],
#     "rejected": [], "totals": {"short_term": 0, "long_term": -30, "disallowed": 120}}
```

Example 4 (input out of date order; invalid trades and an oversized sale are rejected):

```python
compute_gains([{"date": "2024-05-02", "side": "SELL", "symbol": "ZZ", "qty": 3, "amount": 330},
               {"date": "2024-05-01", "side": "BUY", "symbol": "ZZ", "qty": 5, "amount": 500},
               {"date": "2024-05-03", "side": "SELL", "symbol": "ZZ", "qty": 3, "amount": 270},
               {"date": "2024-02-30", "side": "BUY", "symbol": "ZZ", "qty": 1, "amount": 100},
               {"date": "2024-05-04", "side": "buy", "symbol": "ZZ", "qty": 1, "amount": 100},
               {"date": "2024-05-04", "side": "BUY", "symbol": "ZZ", "qty": 0, "amount": 0},
               {"date": "2024-05-05", "side": "SELL", "symbol": "ZZ", "qty": 2, "amount": 150}], [])
# -> {"realized": [{"sale": 0, "lot": 1, "qty": 3, "proceeds": 330, "basis": 300, "gain": 30,
#                   "disallowed": 0, "term": "SHORT"},
#                  {"sale": 6, "lot": 1, "qty": 2, "proceeds": 150, "basis": 200, "gain": -50,
#                   "disallowed": 0, "term": "SHORT"}],
#     "open_lots": [], "rejected": [2, 3, 4, 5], "totals": {"short_term": -20, "long_term": 0, "disallowed": 0}}
```
