# Problem 11: Access-policy evaluator

Implement `def authorize(principals, policies, requests)` in Python, using only the standard library.

Decide, for each request, whether a principal may perform an action on a resource, given allow/deny statements, role
inheritance and permission boundaries. The rules are inspired by cloud IAM systems but are self-contained: where they
differ from any real system, follow this text.

## Inputs and output

The inputs always have these shapes; only statements can be malformed (see "Statements").

- `principals`: dict id → `{"kind": "user" or "role", "inherits": [ids], "boundary": a non-empty str or None,
  "tags": {str: str}}`.
- `policies`: list of statement dicts.
- `requests`: list of `{"principal": str, "action": str, "resource": str, "context": {str: str or list of str}}`.

Return a list with one result per request, in request order:
`{"decision": "ALLOW" or "DENY", "reason": str, "statements": [sids]}`.

Strings are compared and sorted by Unicode code point (Python's default `str` order). Nothing is trimmed or
normalised unless a rule says so.

## Identity set, distance, tags, boundaries

An **edge** goes from principal X to Y when Y is listed in X's `inherits`, Y is a key of `principals`, and Y's kind is
`"role"`. Entries naming an unknown id or a user are ignored. The **identity set** of P is P plus every principal
reachable from P along edges (edges may form cycles). A member's **distance** is the number of edges on a shortest
path from P; P has distance 0.

The **tag** k of P: among the members whose `tags` contain key k, take the one with the smallest distance, then the
smallest id; the tag is that member's value for k. (So P's own tag always wins.) If no member has key k, the tag is
**missing**. An empty-string value is present.

The **boundary sets** of P are the distinct non-None `boundary` values of all members of its identity set (roles
included, not only P).

## Statements

A statement is **well-formed** iff all of the following hold. A malformed statement is ignored completely: it never
matches and is never listed.

1. Every key is one of `sid`, `effect`, `principals`, `actions`, `not_actions`, `resources`, `not_resources`,
   `conditions`, `set`.
2. `sid` is a non-empty str. Sids need not be unique.
3. `effect` is exactly `"Allow"` or `"Deny"`.
4. `set` is absent or None (an **identity statement**), or a non-empty str (a **boundary statement** of that set).
5. An identity statement has `principals`: a non-empty list of str. A boundary statement has no `principals` key.
6. Exactly one of `actions` and `not_actions` is present, and its value is a non-empty list of str. The same holds for
   `resources` and `not_resources`, and every resource pattern must be valid (see "Resource patterns").
7. `conditions` is absent, or a dict whose keys are valid operators (see "Conditions") and whose values are dicts
   (possibly empty) mapping a context key (str) to a policy value: a str or a non-empty list of str. If the base starts
   with `Numeric`, every str in the policy value must be a number; if the base is `Bool` or `Null`, every str must be
   `"true"` or `"false"`.

"List" means a Python `list`: a bare str where a list is required is malformed.

## Patterns

A pattern must match the whole string. `*` matches any run of characters, including the empty run; `?` matches exactly
one character; every other character matches only itself. Nothing else is special (`[`, `]`, `\` are ordinary), and
`*` and `?` match `/` and `:` like any other character.

| Patterns in | are matched against | case | references |
|---|---|---|---|
| `principals` | each id of the identity set (any id may match) | sensitive | no |
| `actions`, `not_actions` | the request `action` | insensitive for ASCII letters only: `A`–`Z` equal `a`–`z`; no other character is folded | no |
| `resources`, `not_resources` | the request `resource` | sensitive | yes |
| `StringLike`, `StringNotLike` values | context values | sensitive | no |

Where references are "no", `$`, `{` and `}` are ordinary characters.

### Resource patterns

Read left to right. A `$` immediately followed by `{` opens a reference, which ends at the first `}` after it. The text
between the braces must be one of:

| Reference | Stands for |
|---|---|
| `principal` | the request's `principal` id |
| `tag:` followed by a non-empty key k | tag k of the request principal |
| `*`, `?` or `$` | that single character, literally |

Any other text between the braces, or a `${` with no later `}`, makes the pattern invalid (and its statement
malformed). Text that a reference stands for is literal: a `*` or `?` inside a substituted id or tag value matches only
itself. If a referenced tag is missing, that pattern **matches nothing** for the request.

## Conditions

An operator is an optional prefix `ForAnyValue:` or `ForAllValues:`, then a base, then an optional suffix `IfExists`,
case-sensitive. The bases are `StringEquals`, `StringNotEquals`, `StringLike`, `StringNotLike`, `NumericEquals`,
`NumericNotEquals`, `NumericLessThan`, `NumericLessThanEquals`, `NumericGreaterThan`, `NumericGreaterThanEquals`,
`Bool` and `Null`. `Null` takes no prefix and no suffix. Any other operator string is invalid. The **negated** bases
are `StringNotEquals`, `StringNotLike` and `NumericNotEquals`.

A **number** is ASCII only: an optional `-`, one or more digits `0`–`9`, then optionally a `.` and one or more digits.
Nothing else is a number (no `+`, spaces, exponents, `_`, `inf`). Numbers compare exactly as decimals: `"2.50"` equals
`"2.5"`, `"-0"` equals `"0"`, and large integers never lose precision.

For one key under one operator, with policy values V (a single str means a one-element list), a request str r
**passes** when:

| Base | r passes when |
|---|---|
| `StringEquals` / `StringNotEquals` | r equals some v / r equals no v |
| `StringLike` / `StringNotLike` | r matches some pattern v / r matches no v |
| `NumericEquals`, `NumericLessThan`, `NumericLessThanEquals`, `NumericGreaterThan`, `NumericGreaterThanEquals` | r is a number and r =, <, ≤, >, ≥ (respectively) some v |
| `NumericNotEquals` | r is a number and r differs from every v |
| `Bool` | r equals some v (only exact `"true"` / `"false"` can pass) |

For every base except `Null`, whether the key is true depends on whether it is in `context`:

- **Present**: let R be its value if that is a list (possibly empty), or a one-element list if it is a str.
  `ForAllValues:` is true iff every r in R passes (true when R is empty); `ForAnyValue:` and no prefix are true iff
  some r in R passes (false when R is empty). `IfExists` changes nothing.
- **Absent**: with `IfExists` the key is true. Otherwise `ForAllValues:` is true, `ForAnyValue:` is false, and with no
  prefix it is true for a negated base and false for any other base.

`Null` looks only at presence: value `"true"` is satisfied when the key is absent, `"false"` when it is present (an
empty list is present); with several values, the key is true if any is satisfied.

A statement's conditions hold iff every key under every operator is true; an empty `conditions` dict, or an operator
with an empty dict, imposes nothing. Context keys are case-sensitive.

## Matching

A well-formed statement **matches** a request when all of these hold:

1. (Identity statements only.) Some `principals` pattern matches some id in the identity set.
2. With `actions`, some pattern matches the action; with `not_actions`, no pattern matches it.
3. With `resources`, some pattern matches the resource; with `not_resources`, no pattern matches it (a pattern that
   matches nothing excludes nothing).
4. Its conditions hold.

## Decision

For each request, the first rule that applies decides. Sids in `statements` are sorted, without duplicates.

1. The principal is not a key of `principals`: `DENY`, `"unknown_principal"`, `[]`.
2. Some identity statement with effect Deny matches: `DENY`, `"explicit_deny"`, the sids of the matching identity Deny
   statements.
3. Some boundary set of the principal does not contain the request: `DENY`, `"outside_boundary"`, the sids of the
   matching Deny statements of all its boundary sets. Set b consists of the well-formed boundary statements whose `set`
   equals b, and it contains the request iff one of its Allow statements matches and none of its Deny statements
   matches (so a set with no statements contains nothing).
4. Some identity Allow statement matches: `ALLOW`, `"allowed"`, the sids of the matching identity Allow statements
   together with the matching Allow statements of the principal's boundary sets.
5. Otherwise: `DENY`, `"implicit_deny"`, `[]`.

Boundary statements never allow or deny anything on their own; they only limit, in rule 3.

## Size

Up to 50 000 principals and 400 000 `inherits` entries; inheritance chains up to 50 000 roles deep, so an identity set
can hold tens of thousands of roles; up to 100 statements; up to 20 000 requests, often hundreds from the same
principal; strings up to 1 000 characters; patterns with dozens of `*`. The whole call must finish within a few
seconds in CPython.

## Examples

Example 1 (inheritance with a cycle and an unknown id, case-insensitive actions, explicit and implicit deny):

```python
principals = {"alice": {"kind": "user", "inherits": ["dev", "ghost"], "boundary": None, "tags": {}},
              "dev": {"kind": "role", "inherits": ["base"], "boundary": None, "tags": {}},
              "base": {"kind": "role", "inherits": ["dev"], "boundary": None, "tags": {}}}
policies = [{"sid": "read", "effect": "Allow", "principals": ["base"], "actions": ["s3:Get*"],
             "resources": ["arn:s3:*"]},
            {"sid": "no-secret", "effect": "Deny", "principals": ["dev"], "actions": ["s3:*"],
             "resources": ["arn:s3:secret/*"]}]
requests = [{"principal": "alice", "action": "S3:getObject", "resource": "arn:s3:pub/a.txt", "context": {}},
            {"principal": "alice", "action": "s3:GetObject", "resource": "arn:s3:secret/k", "context": {}},
            {"principal": "alice", "action": "s3:PutObject", "resource": "arn:s3:pub/a.txt", "context": {}},
            {"principal": "bob", "action": "s3:GetObject", "resource": "arn:s3:pub/a.txt", "context": {}}]
authorize(principals, policies, requests)
# -> [{"decision": "ALLOW", "reason": "allowed", "statements": ["read"]},
#     {"decision": "DENY", "reason": "explicit_deny", "statements": ["no-secret"]},
#     {"decision": "DENY", "reason": "implicit_deny", "statements": []},
#     {"decision": "DENY", "reason": "unknown_principal", "statements": []}]
```

Example 2 (references: `${principal}`, a tag inherited from a role, the literal `${*}`):

```python
principals = {"u1": {"kind": "user", "inherits": ["eng"], "boundary": None, "tags": {}},
              "u2": {"kind": "user", "inherits": [], "boundary": None, "tags": {"team": "ops"}},
              "eng": {"kind": "role", "inherits": [], "boundary": None, "tags": {"team": "core"}}}
policies = [{"sid": "home", "effect": "Allow", "principals": ["u?"], "actions": ["fs:*"],
             "resources": ["home/${principal}/*"]},
            {"sid": "team", "effect": "Allow", "principals": ["*"], "actions": ["fs:Read"],
             "resources": ["team/${tag:team}/${*}"]}]
requests = [{"principal": "u1", "action": "fs:Write", "resource": "home/u1/notes", "context": {}},
            {"principal": "u1", "action": "fs:Write", "resource": "home/u2/notes", "context": {}},
            {"principal": "u1", "action": "fs:Read", "resource": "team/core/*", "context": {}},
            {"principal": "u2", "action": "fs:Read", "resource": "team/ops/x", "context": {}}]
authorize(principals, policies, requests)
# -> [{"decision": "ALLOW", "reason": "allowed", "statements": ["home"]},
#     {"decision": "DENY", "reason": "implicit_deny", "statements": []},
#     {"decision": "ALLOW", "reason": "allowed", "statements": ["team"]},
#     {"decision": "DENY", "reason": "implicit_deny", "statements": []}]
```

Example 3 (conditions: Bool, numbers, several values for one key, a multi-valued key):

```python
principals = {"ann": {"kind": "user", "inherits": [], "boundary": None, "tags": {}}}
policies = [{"sid": "q", "effect": "Allow", "principals": ["ann"], "actions": ["db:Query"], "resources": ["*"],
             "conditions": {"Bool": {"mfa": "true"}, "NumericLessThan": {"rows": ["100", "1000.5"]}}},
            {"sid": "lbl", "effect": "Deny", "principals": ["*"], "actions": ["db:*"], "resources": ["*"],
             "conditions": {"ForAnyValue:StringLike": {"labels": ["secret*", "pii"]}}}]
requests = [{"principal": "ann", "action": "db:Query", "resource": "t1", "context": {"mfa": "true", "rows": "999"}},
            {"principal": "ann", "action": "db:Query", "resource": "t1", "context": {"mfa": "true", "rows": "1e3"}},
            {"principal": "ann", "action": "db:Query", "resource": "t1",
             "context": {"mfa": "true", "rows": "5", "labels": ["public", "secret-x"]}},
            {"principal": "ann", "action": "db:Query", "resource": "t1",
             "context": {"mfa": "true", "rows": "0100", "labels": []}}]
authorize(principals, policies, requests)
# -> [{"decision": "ALLOW", "reason": "allowed", "statements": ["q"]},
#     {"decision": "DENY", "reason": "implicit_deny", "statements": []},
#     {"decision": "DENY", "reason": "explicit_deny", "statements": ["lbl"]},
#     {"decision": "ALLOW", "reason": "allowed", "statements": ["q"]}]
```

Example 4 (a permission boundary limits an inherited allow):

```python
principals = {"carl": {"kind": "user", "inherits": ["admin"], "boundary": "limits", "tags": {}},
              "admin": {"kind": "role", "inherits": [], "boundary": None, "tags": {}}}
policies = [{"sid": "all", "effect": "Allow", "principals": ["admin"], "actions": ["*"], "resources": ["arn:*"]},
            {"sid": "lim-s3", "set": "limits", "effect": "Allow", "actions": ["s3:*"], "resources": ["*"]},
            {"sid": "lim-del", "set": "limits", "effect": "Deny", "actions": ["s3:Delete*"], "resources": ["*"]}]
requests = [{"principal": "carl", "action": "s3:GetObject", "resource": "arn:s3:b/k", "context": {}},
            {"principal": "carl", "action": "ec2:RunInstances", "resource": "arn:ec2:i-1", "context": {}},
            {"principal": "carl", "action": "s3:DeleteObject", "resource": "arn:s3:b/k", "context": {}},
            {"principal": "carl", "action": "s3:GetObject", "resource": "local/k", "context": {}}]
authorize(principals, policies, requests)
# -> [{"decision": "ALLOW", "reason": "allowed", "statements": ["all", "lim-s3"]},
#     {"decision": "DENY", "reason": "outside_boundary", "statements": []},
#     {"decision": "DENY", "reason": "outside_boundary", "statements": ["lim-del"]},
#     {"decision": "DENY", "reason": "implicit_deny", "statements": []}]
```
