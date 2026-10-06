# Problem 9: Cart pricing with stacked promotions

Implement `def price_cart(catalog, cart, promotions)` in Python, using only the standard library. All money is in
integer cents; never use floating point for money.

- `catalog`: dict sku → `{"price": int ≥ 0, "category": str}`.
- `cart`: list of lines `{"sku": str, "qty": int ≥ 1}`. Every sku is in the catalog; a sku may appear on several
  lines.
- `promotions`: list of promotion dicts (see **Promotions**), each with a unique string `"id"`, a `"type"`, an int
  `"priority"`, an optional string `"group"` and an optional boolean `"exclusive"` (default false).

Inputs are always valid. There are at most 10 promotions and at most 200 units in the cart.

## Units

Expand the cart into **units**: line i with quantity q gives q units. **Unit order** is by line index, then by
position within the line. Every unit has a **current price** (initially its catalog price) and a **claimed** flag
(initially false).

**Allocation** of an amount A ≥ 0 over some units with weights w (their current prices, total W > 0, A ≤ W): each
unit gets `floor(A * w / W)`; the R cents still missing go one each to the R units with the largest remainder
`(A * w) mod W`, ties broken by unit order.

## Promotions

Applying a promotion changes current prices and claimed flags as follows.

- `"percent"`, fields `"category"`, `"percent"` (1–100), `"min_qty"` (≥ 1). The eligible units are the
  **unclaimed** units whose catalog category equals `"category"`. If there are at least `"min_qty"` of them, each
  eligible unit's price is reduced by `floor(price * percent / 100)`. Claimed flags do not change.
- `"bxgy"`, fields `"skus"` (list), `"buy"` X ≥ 1, `"get"` Y ≥ 1. The eligible units are the unclaimed units whose
  sku is in `"skus"`. Let g = (number eligible) // (X + Y). Sort the eligible units by current price, highest
  first, ties by unit order. The first g·(X + Y) of them become claimed, and the **last** g·Y of those claimed
  units get price 0.
- `"bundle"`, fields `"skus"` (list of 2 or more distinct skus), `"price"` P ≥ 0. Repeat: for every sku in
  `"skus"`, pick its unclaimed unit with the highest current price (ties by unit order). Stop if some sku has no
  unclaimed unit, or if the picked units' current prices sum to P or less. Otherwise claim the picked units and
  replace their prices by an **allocation** of P over them (weights: their current prices).
- `"threshold"`, fields `"min_subtotal"`, `"amount_off"`. Let S be the sum of all current prices. If S > 0 and
  S ≥ `"min_subtotal"`, allocate D = min(`"amount_off"`, S) over **all** units (weights: current prices) and
  subtract each unit's share from its price. Claimed flags do not change.

## Choosing promotions

A **selection** is a subset of the promotions such that no two have the same `"group"` (promotions without a group
never conflict) and, if it contains a promotion with `"exclusive": true`, it contains nothing else. The empty
selection is allowed.

To price a selection, start from fresh units and apply its promotions one at a time in order of `"priority"`
(lowest first), ties by id in code-point order. A promotion whose condition is not met simply changes nothing.

The answer is the selection with the **lowest total** (sum of all current prices). Ties: the selection with fewer
promotions; then the one whose ids, sorted in code-point order, form the smaller list (compared element by element
in code-point order; a proper prefix is smaller).

## Output

`{"lines": [cents for each cart line, in cart order], "applied": [ids of the chosen selection in application
order], "total": cents}`, where a line's cents are the sum of its units' final prices.

## Examples

Example 1 (order matters: after the 10% the subtotal is below the threshold, so the threshold alone wins):

```python
catalog = {"tea": {"price": 450, "category": "drink"}, "mug": {"price": 1200, "category": "home"}}
cart = [{"sku": "tea", "qty": 3}, {"sku": "mug", "qty": 1}]
promotions = [
    {"id": "D10", "type": "percent", "category": "drink", "percent": 10, "min_qty": 3, "priority": 1},
    {"id": "T5", "type": "threshold", "min_subtotal": 2500, "amount_off": 500, "priority": 2},
]
# T5 alone: 500 allocated over 450, 450, 450, 1200 -> 88, 88, 88, 236 (the mug has the largest remainder)
# -> {"lines": [1086, 964], "applied": ["T5"], "total": 2050}
```

Example 2 (buy 2 get 1: the cheapest of the claimed units are free):

```python
catalog = {"a": {"price": 500, "category": "x"}, "b": {"price": 300, "category": "x"},
           "c": {"price": 300, "category": "x"}}
cart = [{"sku": "a", "qty": 2}, {"sku": "b", "qty": 1}, {"sku": "c", "qty": 2}]
promotions = [{"id": "B21", "type": "bxgy", "skus": ["a", "b", "c"], "buy": 2, "get": 1, "priority": 1}]
# -> {"lines": [1000, 0, 600], "applied": ["B21"], "total": 1600}
```

Example 3 (bundle price allocated by largest remainder; the remainder tie goes to the earlier unit):

```python
catalog = {"burger": {"price": 650, "category": "food"}, "fries": {"price": 300, "category": "food"},
           "soda": {"price": 250, "category": "drink"}}
cart = [{"sku": "burger", "qty": 2}, {"sku": "fries", "qty": 1}, {"sku": "soda", "qty": 2}]
promotions = [{"id": "MEAL", "type": "bundle", "skus": ["burger", "fries", "soda"], "price": 900, "priority": 1}]
# -> {"lines": [1138, 225, 437], "applied": ["MEAL"], "total": 1800}
```

Example 4 (same group: only one may apply; equal totals are broken by id):

```python
catalog = {"x": {"price": 1000, "category": "c"}}
cart = [{"sku": "x", "qty": 1}]
promotions = [
    {"id": "B", "type": "percent", "category": "c", "percent": 10, "min_qty": 1, "priority": 1, "group": "g"},
    {"id": "A", "type": "threshold", "min_subtotal": 0, "amount_off": 100, "priority": 1, "group": "g"},
]
# -> {"lines": [900], "applied": ["A"], "total": 900}
```
