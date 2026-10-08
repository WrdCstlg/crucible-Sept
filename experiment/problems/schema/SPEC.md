# Problem 16: Data-schema validator

Implement `def validate(schema, instance)` in Python, using only the standard library.

This schema language resembles JSON Schema but differs from it in several places; only the rules below count.

## Values and conventions

`schema` and `instance` are built from `dict` (str keys), `list`, `str`, `int`, `float` (always finite), `bool` and
`None`. The root `schema` is a dict or a bool. Do not modify the arguments.

- **Type names.** A value matches `"null"` if it is None, `"boolean"` if it is a bool, `"object"` if a dict, `"array"`
  if a list, `"string"` if a str, `"number"` if an int or float but **not a bool**, and `"integer"` if it is an int
  that is not a bool **or a float whose value is an integer** (`1.0`, `-3.0`, `-0.0` and `1e300` are integers, `1.5`
  is not; `True` is neither a number nor an integer). A value is *a number* when it matches `"number"`.
- **Numbers** compare by exact mathematical value: `10**20 + 1` is greater than `1e20`. Never convert an int to float.
- **Equality** (used by `enum`, `const`, `uniqueItems`): null equals null; a bool equals only the same bool; a number
  equals a number with the same value (`1` equals `1.0`, but `True` never equals `1` and `False` never equals `0`);
  strings are equal if their code points are; arrays if they have the same length and equal elements in the same
  order; objects if they have the same set of keys and equal values under each key.
- **Pointers.** Locations are written as JSON pointers: `""` is the whole document and each step down appends `"/"`
  and a token. An object key becomes a token by replacing every `~` with `~0` and then every `/` with `~1`; an array
  index becomes its decimal digits. Instance locations (`path`) and schema locations (`schema_path`) are both written
  this way. Below, `S/kw` means location S followed by the token kw.

## Step 1: check the schema

A *schema* is a dict or a bool. Starting with the root at location `""`, collect the **subschema locations**: in
every one that holds a dict, look at each key that is a keyword of the table below. If its value is not well-formed,
that keyword is a **problem**. Otherwise these values become subschema locations too, and are checked the same way:

- `properties`, `patternProperties`, `$defs`: each value, at `S/kw/<token of its key>`;
- `prefixItems`, `allOf`, `anyOf`, `oneOf`: each element, at `S/kw/<index>`;
- `additionalProperties`, `items`, `not`, `if`, `then`, `else`: the value, at `S/kw`.

Nothing inside a malformed value becomes a subschema location. A key missing from the table is not a keyword: ignore
it and never look inside its value, even where other schema languages define it (`contains`, `format`,
`minProperties`, `additionalItems`, `definitions`, `$id`, ...). `const` and `enum` hold data, not schemas.

| keyword | well-formed value |
|---|---|
| `type` | a type name, or a non-empty list of distinct type names (the seven above) |
| `enum` | a list (possibly empty) |
| `const` | any value |
| `properties`, `$defs` | a dict whose values are all schemas |
| `patternProperties` | a dict whose values are all schemas and whose keys all compile with `re.compile` |
| `additionalProperties`, `items`, `not`, `if`, `then`, `else` | a schema |
| `prefixItems`, `allOf`, `anyOf`, `oneOf` | a non-empty list of schemas |
| `required` | a list of strings (possibly empty, repeats allowed) |
| `minItems`, `maxItems`, `minLength`, `maxLength` | an int ≥ 0 that is not a bool (`2.0` is malformed, unlike JSON Schema) |
| `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum` | a number |
| `multipleOf` | a number > 0 |
| `uniqueItems` | a bool |
| `pattern` | a str that compiles with `re.compile` |
| `$ref` | a str that resolves (below) |

**Resolving `$ref`**, once all subschema locations are known: the value resolves if it is `"#"` followed by the exact
location string of a subschema location. `"#"` is the root; `"#/$defs/a~1b"` is the `$defs` entry with key `a/b`.
The match is on strings, with no decoding of any kind (unlike JSON Schema), so `"#/allOf/01"`, `"#/properties"` (a
dict of schemas, not a schema) and anything not starting with `#` resolve to nothing.

**Cycles.** The *in-place links* of a dict subschema lead to these subschema locations: each element of its `allOf`,
`anyOf` and `oneOf`; its `not`, `if`, `then` and `else` (whenever present, even `then` without `if`); and the target
of its resolved `$ref`. A resolved `$ref` in the dict at location L is **cyclic** if its target is L or can reach L by
following in-place links. Every cyclic `$ref` is a problem.

If there is any problem (malformed keyword, `$ref` that does not resolve, cyclic `$ref`), return one record per
problem, `{"path": None, "keyword": kw, "schema_path": "S/kw"}`, sorted by `schema_path`, without looking at the
instance.

## Step 2: validate

Applying the subschema at location S to the value x at instance location p produces a set of **errors**, each
`{"path": ..., "keyword": ..., "schema_path": ...}`. S *accepts* x if it produces no errors.

- `true` produces nothing. `false` produces one error: path p, keyword `"false"`, schema_path S.
- A dict: (1) if it has `type` and x matches none of its names, the only error is a `type` error and **no other
  keyword of this dict is evaluated** (unlike JSON Schema); (2) otherwise every keyword is evaluated and the dict
  produces the union of their errors. A keyword whose "applies to" column does not fit x does nothing.

An *own error* has path p, the keyword's name, and schema_path `S/kw`.

| keyword | applies to | errors |
|---|---|---|
| `type` | any | own error if x matches none of the names |
| `enum` / `const` | any | own error unless x equals some element / equals the value |
| `minimum`, `maximum` | number | own error if x < value / x > value |
| `exclusiveMinimum`, `exclusiveMaximum` | number | own error if x ≤ value / x ≥ value |
| `multipleOf` | number | own error unless x ÷ value is an integer (zero and negatives count; exactly, see below) |
| `minLength`, `maxLength` | string | own error if the number of code points is below / above the value |
| `pattern` | string | own error if `re.search(value, x)` is None (unanchored) |
| `minItems`, `maxItems` | array | own error if the length is below / above the value |
| `uniqueItems` | array | if true: one own error if two elements at different indices are equal |
| `prefixItems` | array | value[i] applied to x[i] at p/i, for each index i < len(value) that x has |
| `items` | array | the value applied to x[i] at p/i, for each i ≥ len(this dict's prefixItems) (0 if absent) |
| `required` | object | one own error if any listed name is not a key of x |
| `properties` | object | each key k of x that is also a key of the value: value[k] applied to x[k] at p/k |
| `patternProperties` | object | for each key k of x and each pattern with `re.search(pattern, k)` not None: that pattern's schema applied to x[k] at p/k |
| `additionalProperties` | object | each key k of x that is neither a key of this dict's `properties` nor matched by a pattern of this dict's `patternProperties`: the value applied to x[k] at p/k |
| `allOf` | any | the errors of every element |
| `anyOf` | any | one own error if no element accepts x |
| `oneOf` | any | one own error unless exactly one element accepts x |
| `not` | any | one own error if the value accepts x |
| `if` | any | if `if` accepts x: the errors of `then` (if present), otherwise those of `else` (if present) |
| `$ref` | any | the errors of the target applied to x at p; sibling keywords are still evaluated |

`then`, `else` and `$defs` do nothing by themselves. `additionalProperties: false` gives one `"false"` error per
extra key, at p/k. Errors produced inside the elements of `anyOf` and `oneOf`, the value of `not` and the `if`
schema only decide acceptance; they never appear in the result. An error keeps the `schema_path` of its own keyword
in the schema document however it was reached: through a `$ref` it lies inside the target (for example
`/$defs/pos/minimum`), never on a route like `/$ref/...`.

**multipleOf, exactly.** Read every number as an exact decimal: an int is itself, and a float is the decimal number
that `repr()` prints (so `0.1` is exactly 1/10, and `0.3` is a multiple of `0.1`). Then divide exactly, for example
with `fractions.Fraction(repr(x))`.

**Result.** Apply the root schema to the instance at `""`. Remove duplicate errors (same path, keyword and
schema_path), and sort by path, then schema_path, then keyword. All sorting in this problem compares strings with
Python's `<` (code-point order, so `"/10"` sorts before `"/9"` and `"/B"` before `"/a"`). A valid instance gives `[]`.

## Size

The instance has at most 200 000 values and is up to 20 000 containers deep; an array has at most 50 000 elements.
The schema has at most 60 000 subschema locations and nests at most 50 containers deep, but a chain of in-place links
can pass through tens of thousands of them. Values compared for equality nest at most 50 deep. These depths are far
beyond Python's default recursion limit. The whole call must finish within a few seconds.

## Examples

Example 1 (object keywords; extra keys meet the `false` schema; code-point order):

```python
schema = {"type": "object", "required": ["id", "name"],
          "properties": {"id": {"type": "integer", "minimum": 1}, "name": {"type": "string", "minLength": 2}},
          "additionalProperties": False}
validate(schema, {"id": 0, "name": "x", "zip": 1, "Age": 3})
# -> [{"path": "/Age", "keyword": "false", "schema_path": "/additionalProperties"},
#     {"path": "/id", "keyword": "minimum", "schema_path": "/properties/id/minimum"},
#     {"path": "/name", "keyword": "minLength", "schema_path": "/properties/name/minLength"},
#     {"path": "/zip", "keyword": "false", "schema_path": "/additionalProperties"}]
```

Example 2 (recursion through `$ref`; errors located inside the target; a `$ref` sibling still counts):

```python
schema = {"$defs": {"node": {"type": "object",
                             "properties": {"v": {"type": "integer"},
                                            "kids": {"items": {"$ref": "#/$defs/node"}}}}},
          "$ref": "#/$defs/node", "required": ["v"]}
validate(schema, {"kids": [{"v": 1}, {"v": "2", "kids": [3]}]})
# -> [{"path": "", "keyword": "required", "schema_path": "/required"},
#     {"path": "/kids/1/kids/0", "keyword": "type", "schema_path": "/$defs/node/type"},
#     {"path": "/kids/1/v", "keyword": "type", "schema_path": "/$defs/node/properties/v/type"}]
```

Example 3 (combinators report one error at the keyword; `if` picks `then`):

```python
schema = {"properties": {"a": {"anyOf": [{"type": "string"}, {"minimum": 10}]},
                         "b": {"oneOf": [{"type": "number"}, {"multipleOf": 2}]},
                         "c": {"not": {"enum": [None, 0]}},
                         "d": {"if": {"type": "string"}, "then": {"maxLength": 3}, "else": {"const": 5}}}}
validate(schema, {"a": 3, "b": 4, "c": 0.0, "d": "long"})
# -> [{"path": "/a", "keyword": "anyOf", "schema_path": "/properties/a/anyOf"},
#     {"path": "/b", "keyword": "oneOf", "schema_path": "/properties/b/oneOf"},
#     {"path": "/c", "keyword": "not", "schema_path": "/properties/c/not"},
#     {"path": "/d", "keyword": "maxLength", "schema_path": "/properties/d/then/maxLength"}]
```

Example 4 (schema problems; the `$ref` under `properties` is not in place; `contains` is ignored):

```python
schema = {"$defs": {"a": {"allOf": [{"$ref": "#/$defs/b"}]},
                    "b": {"anyOf": [{"$ref": "#/$defs/a"}, {"type": "null"}]},
                    "c": {"properties": {"next": {"$ref": "#/$defs/c"}}}},
          "properties": {"x": {"$ref": "#/$defs/d"}, "y": {"minLength": -1}},
          "contains": {"$ref": "#/nowhere"}}
validate(schema, 1)
# -> [{"path": None, "keyword": "$ref", "schema_path": "/$defs/a/allOf/0/$ref"},
#     {"path": None, "keyword": "$ref", "schema_path": "/$defs/b/anyOf/0/$ref"},
#     {"path": None, "keyword": "$ref", "schema_path": "/properties/x/$ref"},
#     {"path": None, "keyword": "minLength", "schema_path": "/properties/y/minLength"}]
```
