# Problem 6: Order book matching engine

Implement `def run_book(commands)` in Python, using only the standard library.

`commands` is a list of strings. Process them in list order; line numbers below are 0-based list indices.

## Parsing

Trim each line, split it on commas, and trim every field. A line is **well-formed** only if it matches one of these
shapes exactly (field count included):

| Command | Fields |
|---|---|
| `LIMIT` | `LIMIT,<owner>,<id>,<side>,<price>,<qty>` optionally followed by one flag field: `IOC`, `FOK`, `POST` or `ICE=<display>` |
| `MARKET` | `MARKET,<owner>,<id>,<side>,<qty>` |
| `STOP` | `STOP,<owner>,<id>,<side>,<trigger>,<qty>` |
| `CANCEL` | `CANCEL,<id>` |
| `AMEND` | `AMEND,<id>,<price>,<qty>` |

- Command names and flags are uppercase and case-sensitive.
- `<owner>` and `<id>` are non-empty and contain only ASCII letters, digits and `_`. IDs are case-sensitive.
- `<side>` is `B` (buy) or `S` (sell).
- `<price>`, `<qty>`, `<trigger>` and `<display>` consist only of ASCII digits (leading zeros allowed), are read as
  base-10 integers and must be at least 1.
- For `ICE=<display>`, `<display>` must be **less than** `<qty>`.

Anything else is **malformed**: it changes nothing and is reported as a reject with reason `"malformed"`.

## IDs

Every well-formed `LIMIT`, `MARKET` or `STOP` line **consumes** its ID unless it is rejected as a duplicate. A later
`LIMIT`, `MARKET` or `STOP` with an already consumed ID is rejected with reason `"duplicate_id"` and has no other
effect. This holds even if the earlier order is gone (filled, cancelled or rejected for another reason).

## The book

Resting orders are buy or sell limit orders. Each has an owner, an ID, a side, a price, a **visible** quantity and a
**hidden** quantity (hidden is 0 except for icebergs). Orders at the same price on the same side form a **level**,
queued in **time priority**: an order joins the back of its level when it starts resting, and again whenever it
loses priority (below).

## Matching

An incoming buy may trade with resting sells whose price is at most its limit (any price for a market order).
An incoming sell may trade with resting buys whose price is at least its limit. Repeat while the incoming order has
quantity left and a tradable resting order exists:

1. Take the **best** resting order on the opposite side: lowest-priced sell or highest-priced buy, and within that
   price the front of the level.
2. **Self-trade prevention:** if it has the same owner as the incoming order, cancel that resting order entirely
   (visible and hidden), append its ID to `stp_cancelled`, and go back to step 1. No trade happens.
3. Otherwise trade `min(incoming remaining, resting visible)` at the **resting order's price**. The incoming
   order's quantity and the resting order's visible quantity both drop by that amount.
4. **Iceberg refresh:** if the resting order's visible quantity is now 0 and its hidden quantity is not, move
   `min(display, hidden)` from hidden to visible and move the order to the **back** of its level.
   A resting order with nothing visible and nothing hidden is removed.

The incoming order's own quantity is always its full remaining quantity, including for an incoming iceberg.

Every trade is reported as
`{"seq": n, "price": p, "qty": q, "buy": <buy order id>, "sell": <sell order id>, "aggressor": "B" or "S"}`, where
`seq` counts trades from 1 and `aggressor` is the incoming order's side. The **last price** is the price of the most
recent trade (none before the first trade).

## Order types

- **`LIMIT`, no flag:** match, then any remainder rests at its price.
- **`IOC`:** match; any remainder is cancelled. No reject, even if nothing traded.
- **`FOK`:** first add up the visible plus hidden quantity of every resting opposite order it could trade with by
  price **and** whose owner differs from its own. If that total is less than its quantity, reject it with
  `"fok_unfilled"`: nothing else happens (no trades, no self-trade cancels). Otherwise it matches normally.
- **`POST` (post-only):** if any resting opposite order is tradable by price, whatever its owner, reject it with
  `"post_would_cross"` and change nothing. Otherwise it rests.
- **`ICE=<display>` (iceberg):** matches with its full quantity. Any remainder `r` rests with visible `min(display, r)`
  and hidden `r - visible`.
- **`MARKET`:** match at any price; any remainder is cancelled. If it traded nothing at all, reject it with
  `"no_liquidity"`.
- **`STOP`:** accepted into the stop list (it does not rest in the book and cannot trade until triggered).

## Stops

A buy stop is **triggered** when a last price exists and last price `>=` its trigger; a sell stop when last price
`<=` its trigger. After each line has been fully processed (and after any triggered stop has executed), repeat:
take the untriggered stop with the **earliest line number** whose condition holds under the current last price; if
there is none, stop; otherwise remove it from the stop list and execute it as a `MARKET` order with the same owner,
ID, side and quantity (a triggered stop that trades nothing is rejected with `"no_liquidity"`, reported at the
`STOP` line's number). A stop whose condition holds when it is accepted triggers right away.

## `CANCEL` and `AMEND`

- **`CANCEL,<id>`** removes a resting order (all of it) or an untriggered stop. Otherwise reject `"unknown_id"`.
- **`AMEND,<id>,<price>,<qty>`** applies only to a resting order; otherwise (including a stop) reject `"unknown_id"`.
  `<qty>` is the new **total** remaining quantity (visible plus hidden).
  - Same price and the same total: nothing changes.
  - Same price and a smaller total: reduce in place and **keep** time priority. Take the reduction from hidden first,
    then from visible.
  - Any other change (new price, or a larger total): if the order was posted with `POST` and the new price would be
    tradable against any resting opposite order (any owner, not counting itself), reject `"post_would_cross"` and
    change nothing. Otherwise remove the order and enter it again as a new incoming order with the same owner, ID,
    side and flag (`POST`, `ICE=<display>` or none), the new price and `<qty>`: it matches, and any remainder joins
    the back of its new level. This does not consume or check its ID again.

## Output

Return a dict with exactly these keys:

- `"trades"`: list of trade dicts in the order they happened.
- `"rejects"`: list of `{"line": i, "reason": r}` in the order they happened.
- `"stp_cancelled"`: list of resting order IDs cancelled by self-trade prevention, in order.
- `"bids"`: buy levels, highest price first; `"asks"`: sell levels, lowest price first. Each level is
  `[price, [[id, visible, hidden], ...]]` with orders in time priority. Empty levels are omitted.
- `"stops"`: untriggered stops in line order, each `[id, side, trigger, qty]`.
- `"last_price"`: an `int`, or `None` if no trade happened.

All numbers are `int`. Every list is a `list` (not a tuple or generator).

## Performance

Up to 200,000 lines, prices and quantities up to 1,000,000,000. Each call must finish within 10 seconds in CPython on
a typical laptop; scanning a whole side of the book for every command will not.

## Examples

Example 1 (price-time priority, trade at the resting price, remainder rests):

```
LIMIT,u1,a1,S,101,5
LIMIT,u2,a2,S,100,5
LIMIT,u3,b1,B,101,7
```

```
{"trades": [{"seq": 1, "price": 100, "qty": 5, "buy": "b1", "sell": "a2", "aggressor": "B"},
            {"seq": 2, "price": 101, "qty": 2, "buy": "b1", "sell": "a1", "aggressor": "B"}],
 "rejects": [], "stp_cancelled": [], "bids": [], "asks": [[101, [["a1", 3, 0]]]], "stops": [], "last_price": 101}
```

Example 2 (an iceberg refresh goes to the back of its level):

```
LIMIT,u1,i1,S,100,10,ICE=4
LIMIT,u2,s2,S,100,3
MARKET,u3,m1,B,6
```

```
{"trades": [{"seq": 1, "price": 100, "qty": 4, "buy": "m1", "sell": "i1", "aggressor": "B"},
            {"seq": 2, "price": 100, "qty": 2, "buy": "m1", "sell": "s2", "aggressor": "B"}],
 "rejects": [], "stp_cancelled": [], "bids": [], "asks": [[100, [["s2", 1, 0], ["i1", 4, 2]]]], "stops": [],
 "last_price": 100}
```

Example 3 (self-trade prevention, then a reject for a duplicate ID and a malformed line):

```
LIMIT,u1,s1,S,100,5
LIMIT,u2,s2,S,100,5
LIMIT,u1,b1,B,100,3
LIMIT,u9,s1,S,99,1
limit,u9,x,S,99,1
```

```
{"trades": [{"seq": 1, "price": 100, "qty": 3, "buy": "b1", "sell": "s2", "aggressor": "B"}],
 "rejects": [{"line": 3, "reason": "duplicate_id"}, {"line": 4, "reason": "malformed"}], "stp_cancelled": ["s1"],
 "bids": [], "asks": [[100, [["s2", 2, 0]]]], "stops": [], "last_price": 100}
```

Example 4 (a stop triggers, and its market order cascades into a second stop):

```
LIMIT,u1,a1,S,100,1
LIMIT,u1,a2,S,105,1
LIMIT,u1,a3,S,110,1
STOP,u2,t1,B,100,1
STOP,u3,t2,B,105,1
LIMIT,u4,b1,B,100,1
```

```
{"trades": [{"seq": 1, "price": 100, "qty": 1, "buy": "b1", "sell": "a1", "aggressor": "B"},
            {"seq": 2, "price": 105, "qty": 1, "buy": "t1", "sell": "a2", "aggressor": "B"},
            {"seq": 3, "price": 110, "qty": 1, "buy": "t2", "sell": "a3", "aggressor": "B"}],
 "rejects": [], "stp_cancelled": [], "bids": [], "asks": [], "stops": [], "last_price": 110}
```
