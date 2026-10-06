# Problem 8: Spreadsheet formula evaluator

Implement `def evaluate(cells)` in Python, using only the standard library.

`cells` is a dict: cell reference → raw string. Every key is a valid reference: one uppercase ASCII letter `A`–`Z`
followed by a row number 1–999 written without leading zeros (`A1`, `Z999`). Return a dict with **the same keys**
mapping each cell to its value (see **Output**). Cells not in `cells` are **missing**; a missing cell behaves as an
empty cell.

**Size.** There may be up to 26 × 999 cells, and chains of references may be thousands of cells long (your
evaluator must not hit Python's recursion limit on them). Every raw string is at most 300 characters and every
formula nests parentheses at most 30 deep. The whole sheet must evaluate within a few seconds.

## Raw strings

- A raw string starting with `=` is a **formula** (the rest of the string, see **Formulas**).
- Otherwise, a raw string that is a **number literal** is a number. A number literal is an optional `-`, then one or
  more ASCII digits, then optionally `.` followed by one or more ASCII digits (`7`, `007`, `-3.25`; not `+1`, `1.`,
  `.5`, `1e3` or ` 1`).
- Otherwise, exactly `TRUE` or `FALSE` (uppercase) is a boolean.
- Otherwise, the empty string is **empty**.
- Otherwise the raw string is a string value, exactly as written.

## Values

A value is a number (Python `float` arithmetic throughout), a string, a boolean, **empty**, or an **error**: one of
`#DIV/0!`, `#VALUE!`, `#REF!`, `#NAME?`, `#NUM!`, `#CYCLE!`, `#PARSE!`.

**Coercions.** When an operation needs a certain type, the value is converted as follows. Converting an error gives
that error.

| from | to number | to text | to boolean |
|---|---|---|---|
| number x | x | `fmt(x)` (below) | x ≠ 0 |
| string s | the number if s is a number literal, else `#VALUE!` | s | `TRUE` if s is `true` ignoring ASCII case, `FALSE` if `false` ignoring ASCII case, else `#VALUE!` |
| boolean | 1 or 0 | `TRUE` or `FALSE` | itself |
| empty | 0 | `""` | FALSE |

`fmt(x)`: let r = `round(x, 9)` (Python's built-in `round`). If r is integral, the decimal digits of `int(r)` (with
`-` if negative; `-0` is written `0`); otherwise `repr(r)`.

## Formulas

Spaces (U+0020) may appear between tokens; any other character outside a string literal that is not part of a token
is a grammar error. Grammar, from lowest to highest precedence (all binary operators are **left-associative**):

```
formula    := expr
expr       := concat (("=" | "<>" | "<=" | ">=" | "<" | ">") concat)*
concat     := additive ("&" additive)*
additive   := term (("+" | "-") term)*
term       := power (("*" | "/") power)*
power      := unary ("^" unary)*
unary      := ("-" | "+") unary | primary
primary    := NUMBER | STRING | BOOLEAN | REF | RANGE | NAME "(" [expr ("," expr)*] ")" | NAME | "(" expr ")"
```

So unary minus binds **tighter** than `^` (`-2^2` is 4) and `2^3^2` is 64.

- NUMBER: one or more digits, optionally `.` and one or more digits (no sign; the sign is a unary operator).
- STRING: `"` … `"`, where `""` inside stands for one `"`.
- A **word** is one or more ASCII letters followed by zero or more ASCII digits (the longest such run).
  - A word followed (after optional spaces) by `(` is a function call; its NAME is the whole word in uppercase
    (`sum(` is `SUM`; `SUM1(` is the unknown function `SUM1`).
  - Otherwise a word that is `TRUE` or `FALSE` ignoring ASCII case is a BOOLEAN.
  - Otherwise a word containing digits is a **reference token**: a valid REF if it is one letter (either case)
    and a row 1–999 without leading zeros; any other reference token (`AA1`, `A0`, `A01`, `A1000`) evaluates to
    `#REF!`.
  - Otherwise (letters only) it is a bare NAME, which evaluates to `#NAME?`.
- RANGE: a reference token, `:`, and another reference token, with no spaces anywhere in between. It is the
  rectangle between the two corners, in either order. If either side is not a valid REF, the range evaluates to
  `#REF!` (wherever it is used). Any other `:` is a grammar error.
- Function call arguments are separated by `,`. `F()` has zero arguments.

A formula that does not match this grammar (including leftover text, `=` alone, an empty argument like `SUM(1,)`,
or a known function called with the wrong number of arguments, see the table) has the value `#PARSE!`. An unknown
function name evaluates to `#NAME?` (its arguments are not evaluated).

## Evaluation

A REF evaluates to the value of that cell (a missing cell is empty). A formula whose value is empty (for example
`=B7` with B7 missing) stays empty when other formulas read it; only the **Output** shows it as `0`.

**Operators.** Evaluate the left operand, then the right one. If the left value is an error, the result is that
error; otherwise if the right value is an error, that error. A valid RANGE used anywhere except directly as an
argument of an aggregate function (below) evaluates to `#VALUE!`.

- `+ - * /`: convert left, then right, to number (the first conversion error wins); `x / 0` is `#DIV/0!`.
- `^`: convert both to number. `0 ^ 0` is `#NUM!`; `0 ^` a negative number is `#DIV/0!`; a negative base with a
  non-integral exponent is `#NUM!`.
- Any arithmetic result (of an operator, `SUM`, `AVERAGE` or `ROUND`) that is not finite (or raises
  `OverflowError`) is `#NUM!`.
- Unary `-` converts to number and negates. Unary `+` returns its operand **unchanged** (no conversion).
- `&` converts left, then right, to text and concatenates.
- Comparisons: an empty operand is first replaced by `0` if the other operand is a number, `""` if it is a string,
  `FALSE` if it is a boolean, and two empties are equal. Then values of different types are ordered
  **number < string < boolean** (so they are never equal); two numbers compare after `round(·, 9)`; two strings
  compare after mapping ASCII `A`–`Z` to lowercase, by code point; `FALSE < TRUE`. The result is a boolean.

**Functions.** "Arg values" below means: for an argument that is a RANGE or a single REF, the values of its cells in
row-major order (row by row from the top, columns `A`→`Z` within a row); for any other argument, the single value
of the expression. Arguments are processed left to right and the **first** error met is the result (except where
noted).

| Function | Arity | Behaviour |
|---|---|---|
| `SUM`, `MIN`, `MAX`, `AVERAGE` | ≥ 1 | From a RANGE/REF argument: numbers are used; strings, booleans and empties are skipped; errors propagate. Any other argument is converted to number (errors propagate). SUM adds left to right starting from 0. MIN/MAX of no numbers is 0. AVERAGE of no numbers is `#DIV/0!`. |
| `COUNT` | ≥ 1 | Counts numbers in RANGE/REF arguments; any other argument counts 1 if its value is a number, a boolean or a string that is a number literal. Errors are **ignored**, never propagated. |
| `AND`, `OR` | ≥ 1 | All arguments are evaluated. From a RANGE/REF argument: booleans are used, numbers are converted to boolean, strings and empties are skipped; errors propagate. Any other argument is converted to boolean. If no value was used, `#VALUE!`. |
| `NOT` | 1 | Convert to boolean and negate. |
| `IF` | 2 or 3 | Convert the first argument to boolean (an error propagates). Then evaluate and return **only** the chosen branch; a missing third argument gives `FALSE`. |
| `IFERROR` | 2 | If the first argument's value is an error, evaluate and return the second; otherwise return the first. |
| `CONCAT` | ≥ 1 | Every arg value (RANGE/REF arguments included, row-major) converted to text and concatenated. |
| `LEN` | 1 | Number of code points of the text conversion. |
| `ROUND` | 2 | Convert x, then n, to number; truncate n toward zero to an integer, then clamp it to −15…15. Take the decimal number written by `repr(x)` and round it to n decimal places (n may be negative), halves **away from zero**; the result is a number. (`ROUND(2.675, 2)` is 2.68.) |

Only the aggregate functions (`SUM`, `MIN`, `MAX`, `AVERAGE`, `COUNT`, `AND`, `OR`, `CONCAT`) accept a RANGE
argument; a RANGE argument to any other function evaluates to `#VALUE!`. A single REF argument is a RANGE/REF
argument only for these aggregate functions; elsewhere it is an ordinary expression.

## Cycles

Before evaluating, build the **reference graph**: a formula cell has an edge to every cell named by a valid REF or
inside a valid RANGE **anywhere** in its formula, including branches that would not be evaluated and arguments of
unknown functions. A formula with value `#PARSE!` has no edges. Every cell that lies on a directed cycle (including
a cell that references itself) has the value `#CYCLE!`; its formula is not evaluated. Other cells that read a cycle
cell simply see the `#CYCLE!` value (which `IFERROR` can catch).

## Output

For each key of `cells`: a number is output as `round(x, 9)`, as an `int` if that is integral (`-0.0` becomes `0`)
and otherwise as a `float`; a string as `str`; a boolean as `bool`; an empty literal cell as `None`; a **formula**
whose value is empty (for example `=B7` with B7 missing) as `0`; an error as `{"error": "#DIV/0!"}` (and so on).

## Examples

Example 1 (precedence and errors):

```python
evaluate({"A1": "5", "A2": "=-A1^2", "A3": "=2^3^2", "A4": "=A1/0"})
# -> {"A1": 5, "A2": 25, "A3": 64, "A4": {"error": "#DIV/0!"}}
```

Example 2 (comparisons and coercions):

```python
evaluate({"A1": "abc", "A2": "=A1=\"ABC\"", "A3": "=1<\"0\"", "A4": "=\"3\"+TRUE", "A5": "=A1+1"})
# -> {"A1": "abc", "A2": True, "A3": True, "A4": 4, "A5": {"error": "#VALUE!"}}
```

Example 3 (aggregates skip text in ranges but convert direct arguments; ROUND halves away from zero):

```python
evaluate({"A1": "1", "A2": "x", "A3": "TRUE", "A4": "=SUM(A1:A3)", "A5": "=SUM(A1,\"2\",TRUE)",
          "A6": "=AVERAGE(B1:B3)", "A7": "=ROUND(2.675,2)"})
# -> {"A1": 1, "A2": "x", "A3": True, "A4": 1, "A5": 4, "A6": {"error": "#DIV/0!"}, "A7": 2.68}
```

Example 4 (cycles are static; IFERROR catches a cycle value read from outside the cycle):

```python
evaluate({"A1": "=IF(TRUE,1,B1)", "B1": "=A1+1", "C1": "=IFERROR(B1,7)", "D1": "=E1&\"!\""})
# -> {"A1": {"error": "#CYCLE!"}, "B1": {"error": "#CYCLE!"}, "C1": 7, "D1": "!"}
```
