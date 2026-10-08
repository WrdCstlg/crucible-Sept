"""Cases for Problem 11 (access-policy evaluator). Stdlib only (copied into the sandbox like every cases.py).

Cases with "spec_expected" were worked out by hand from SPEC.md; the build fails if the reference disagrees.
"""


class SplitMix:
    """Version-independent PRNG (the sandbox and the host may run different Python versions)."""

    def __init__(self, seed):
        self.s = seed & 0xFFFFFFFFFFFFFFFF

    def next(self):
        self.s = (self.s + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = self.s
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        return z ^ (z >> 31)

    def below(self, n):
        return self.next() % n

    def pick(self, seq):
        return seq[self.below(len(seq))]

    def chance(self, num, den):
        return self.below(den) < num


# ── Builders ────────────────────────────────────────────────────────────────
def U(inherits=(), boundary=None, tags=None):
    return {"kind": "user", "inherits": list(inherits), "boundary": boundary, "tags": dict(tags or {})}


def R(inherits=(), boundary=None, tags=None):
    return {"kind": "role", "inherits": list(inherits), "boundary": boundary, "tags": dict(tags or {})}


def S(sid, effect, principals, actions, resources, **extra):
    st = {"sid": sid, "effect": effect, "principals": principals, "actions": actions, "resources": resources}
    st.update(extra)
    return st


def B(sid, bset, effect, actions, resources, **extra):
    st = {"sid": sid, "set": bset, "effect": effect, "actions": actions, "resources": resources}
    st.update(extra)
    return st


def Q(principal, action, resource, context=None):
    return {"principal": principal, "action": action, "resource": resource,
            "context": {} if context is None else context}


def ALLOW(*sids):
    return {"decision": "ALLOW", "reason": "allowed", "statements": list(sids)}


def DENY(reason, *sids):
    return {"decision": "DENY", "reason": reason, "statements": list(sids)}


IMPLICIT = DENY("implicit_deny")
UNKNOWN = DENY("unknown_principal")
OUTSIDE = DENY("outside_boundary")


def EXPLICIT(*sids):
    return DENY("explicit_deny", *sids)


def case(cid, title, principals, policies, requests, expected=None):
    c = {"id": cid, "title": title, "args": [principals, policies, requests]}
    if expected is not None:
        assert len(expected) == len(requests), cid
        c["spec_expected"] = expected
    return c


# ── Public examples (identical to SPEC.md) ──────────────────────────────────
def public():
    p1 = {"alice": U(["dev", "ghost"]), "dev": R(["base"]), "base": R(["dev"])}
    s1 = [S("read", "Allow", ["base"], ["s3:Get*"], ["arn:s3:*"]),
          S("no-secret", "Deny", ["dev"], ["s3:*"], ["arn:s3:secret/*"])]
    q1 = [Q("alice", "S3:getObject", "arn:s3:pub/a.txt"), Q("alice", "s3:GetObject", "arn:s3:secret/k"),
          Q("alice", "s3:PutObject", "arn:s3:pub/a.txt"), Q("bob", "s3:GetObject", "arn:s3:pub/a.txt")]
    p2 = {"u1": U(["eng"]), "u2": U(tags={"team": "ops"}), "eng": R(tags={"team": "core"})}
    s2 = [S("home", "Allow", ["u?"], ["fs:*"], ["home/${principal}/*"]),
          S("team", "Allow", ["*"], ["fs:Read"], ["team/${tag:team}/${*}"])]
    q2 = [Q("u1", "fs:Write", "home/u1/notes"), Q("u1", "fs:Write", "home/u2/notes"),
          Q("u1", "fs:Read", "team/core/*"), Q("u2", "fs:Read", "team/ops/x")]
    p3 = {"ann": U()}
    s3 = [S("q", "Allow", ["ann"], ["db:Query"], ["*"],
            conditions={"Bool": {"mfa": "true"}, "NumericLessThan": {"rows": ["100", "1000.5"]}}),
          S("lbl", "Deny", ["*"], ["db:*"], ["*"],
            conditions={"ForAnyValue:StringLike": {"labels": ["secret*", "pii"]}})]
    q3 = [Q("ann", "db:Query", "t1", {"mfa": "true", "rows": "999"}),
          Q("ann", "db:Query", "t1", {"mfa": "true", "rows": "1e3"}),
          Q("ann", "db:Query", "t1", {"mfa": "true", "rows": "5", "labels": ["public", "secret-x"]}),
          Q("ann", "db:Query", "t1", {"mfa": "true", "rows": "0100", "labels": []})]
    p4 = {"carl": U(["admin"], boundary="limits"), "admin": R()}
    s4 = [S("all", "Allow", ["admin"], ["*"], ["arn:*"]),
          B("lim-s3", "limits", "Allow", ["s3:*"], ["*"]),
          B("lim-del", "limits", "Deny", ["s3:Delete*"], ["*"])]
    q4 = [Q("carl", "s3:GetObject", "arn:s3:b/k"), Q("carl", "ec2:RunInstances", "arn:ec2:i-1"),
          Q("carl", "s3:DeleteObject", "arn:s3:b/k"), Q("carl", "s3:GetObject", "local/k")]
    return [
        case("P1", "inheritance with a cycle, case-insensitive actions, explicit and implicit deny", p1, s1, q1,
             [ALLOW("read"), EXPLICIT("no-secret"), IMPLICIT, UNKNOWN]),
        case("P2", "references: principal, inherited tag, literal star", p2, s2, q2,
             [ALLOW("home"), IMPLICIT, ALLOW("team"), IMPLICIT]),
        case("P3", "conditions: Bool, numbers, several values, multi-valued key", p3, s3, q3,
             [ALLOW("q"), IMPLICIT, EXPLICIT("lbl"), ALLOW("q")]),
        case("P4", "a permission boundary limits an inherited allow", p4, s4, q4,
             [ALLOW("all", "lim-s3"), OUTSIDE, DENY("outside_boundary", "lim-del"), IMPLICIT]),
    ]


# ── Hand cases ──────────────────────────────────────────────────────────────
def hand():
    cs = []

    cs.append(case(
        "H01", "unknown principal is denied even by a wildcard allow (ids are case-sensitive)",
        {"u": U()}, [S("any", "Allow", ["*"], ["*"], ["*"])],
        [Q("x", "a", "r"), Q("u", "a", "r"), Q("U", "a", "r")],
        [UNKNOWN, ALLOW("any"), UNKNOWN]))

    # u1 -> u2 is ignored (u2 is a user) and "nope" is unknown, so u1's identity set is {u1, r1}.
    cs.append(case(
        "H02", "inherits naming a user or an unknown id is ignored",
        {"u1": U(["u2", "nope", "r1"]), "u2": U(["r2"]), "r1": R(), "r2": R()},
        [S("via-u2", "Allow", ["u2"], ["x:*"], ["*"]), S("via-r2", "Allow", ["r2"], ["y:*"], ["*"]),
         S("via-r1", "Allow", ["r1"], ["z:*"], ["*"])],
        [Q("u1", "x:a", "r"), Q("u1", "y:a", "r"), Q("u1", "z:a", "r"), Q("u2", "y:a", "r")],
        [IMPLICIT, IMPLICIT, ALLOW("via-r1"), ALLOW("via-r2")]))

    cs.append(case(
        "H03", "cycles and self-loops in inheritance; a role can make requests",
        {"a": R(["b", "a"]), "b": R(["c"]), "c": R(["a"]), "u": U(["c"])},
        [S("pa", "Allow", ["a"], ["s:*"], ["*"]), S("pb", "Deny", ["b"], ["s:Del*"], ["*"])],
        [Q("u", "s:Get", "r"), Q("u", "s:Delete", "r"), Q("b", "s:Get", "r"), Q("c", "s:DELETE", "r")],
        [ALLOW("pa"), EXPLICIT("pb"), ALLOW("pa"), EXPLICIT("pb")]))

    # Distances from u: rz 1, ry 1, deep 2. Tag t: rz and ry tie at distance 1 -> smallest id "ry" -> "Y".
    # From rz: rz itself (distance 0) has t = "Z". Tag own of u is u's own "" (present).
    cs.append(case(
        "H04", "tag resolution: own tag first, then smallest distance, then smallest id; empty value is present",
        {"u": U(["rz", "ry"], tags={"own": ""}), "rz": R(["deep"], tags={"t": "Z"}),
         "ry": R(tags={"t": "Y", "own": "role"}), "deep": R(tags={"d": "D", "t": "deep"})},
        [S("t", "Allow", ["*"], ["get"], ["t/${tag:t}"]), S("own", "Allow", ["u"], ["get"], ["o/${tag:own}x"]),
         S("d", "Allow", ["u"], ["get"], ["d/${tag:d}"])],
        [Q("u", "get", "t/Y"), Q("u", "get", "t/Z"), Q("rz", "get", "t/Z"), Q("u", "get", "o/x"),
         Q("u", "get", "o/rolex"), Q("u", "get", "d/D")],
        [ALLOW("t"), IMPLICIT, ALLOW("t"), ALLOW("own"), IMPLICIT, ALLOW("d")]))

    # u has no env tag: "env/${tag:env}/*" matches nothing, so as a not_resources pattern it excludes nothing and
    # the Deny applies to every write by u, including env//a (a missing tag is not an empty string).
    cs.append(case(
        "H05", "a missing tag matches nothing; in not_resources it therefore excludes nothing",
        {"u": U(), "v": U(tags={"env": "prod"})},
        [S("allow-all", "Allow", ["*"], ["*"], ["*"]),
         {"sid": "guard", "effect": "Deny", "principals": ["*"], "actions": ["write"],
          "not_resources": ["env/${tag:env}/*"]},
         S("own-env", "Allow", ["*"], ["read"], ["env/${tag:env}/*", "pub/*"])],
        [Q("u", "write", "env/prod/a"), Q("v", "write", "env/prod/a"), Q("v", "write", "env/dev/a"),
         Q("u", "read", "pub/x"), Q("u", "read", "env//a"), Q("u", "write", "env//a")],
        [EXPLICIT("guard"), ALLOW("allow-all"), EXPLICIT("guard"), ALLOW("allow-all", "own-env"),
         ALLOW("allow-all"), EXPLICIT("guard")]))

    cs.append(case(
        "H06", "substituted text is literal: * and ? inside an id or tag value match only themselves",
        {"dev*": U(tags={"p": "a?c"}), "x": U(tags={"p": "*"})},
        [S("home", "Allow", ["*"], ["get"], ["home/${principal}/f"]),
         S("tagp", "Allow", ["*"], ["get"], ["t/${tag:p}"])],
        [Q("dev*", "get", "home/dev*/f"), Q("dev*", "get", "home/devops/f"), Q("dev*", "get", "t/abc"),
         Q("dev*", "get", "t/a?c"), Q("x", "get", "t/anything"), Q("x", "get", "t/*")],
        [ALLOW("home"), IMPLICIT, IMPLICIT, ALLOW("tagp"), IMPLICIT, ALLOW("tagp")]))

    # "a${*}b${?}c${$}d$e{f}" is the literal text a*b?c$d$e{f} ("$e" is not a reference; "{f}" is plain text).
    # "x*${$}{y}" is: x, any run, then the literal text ${y}.
    cs.append(case(
        "H07", "escapes ${*} ${?} ${$}; a $ not followed by { and a bare { are ordinary",
        {"u": U()},
        [S("esc", "Allow", ["u"], ["get"], ["a${*}b${?}c${$}d$e{f}"]),
         S("wild", "Allow", ["u"], ["put"], ["x*${$}{y}"])],
        [Q("u", "get", "a*b?c$d$e{f}"), Q("u", "get", "aXbYc$d$e{f}"), Q("u", "put", "xyz${y}"),
         Q("u", "put", "x${y")],
        [ALLOW("esc"), IMPLICIT, ALLOW("wild"), IMPLICIT]))

    # bad1..bad5 are malformed. good-dollar's pattern is the literal text r/$tag:t} ("$t" opens nothing).
    # In actions, ${principal} is ordinary text; actions fold ASCII case, so ${PRINCIPAL} matches it.
    cs.append(case(
        "H08", "invalid references make the statement malformed; actions have no references",
        {"u": U(tags={"t": "1"})},
        [S("ok", "Allow", ["u"], ["get"], ["r/*"]),
         S("bad1", "Allow", ["u"], ["get"], ["r/${Principal}"]),
         S("bad2", "Deny", ["u"], ["get"], ["r/${tag:}"]),
         S("bad3", "Deny", ["u"], ["get"], ["r/*", "r/${tag:t"]),
         S("bad4", "Deny", ["u"], ["get"], ["${}"]),
         S("bad5", "Deny", ["u"], ["get"], ["r/${ principal}"]),
         S("good-dollar", "Allow", ["u"], ["get"], ["r/$tag:t}"]),
         S("act", "Allow", ["u"], ["${principal}"], ["*"])],
        [Q("u", "get", "r/u"), Q("u", "get", "r/$tag:t}"), Q("u", "u", "z"), Q("u", "${PRINCIPAL}", "z")],
        [ALLOW("ok"), ALLOW("good-dollar", "ok"), IMPLICIT, ALLOW("act")]))

    cs.append(case(
        "H09", "[ and ] are ordinary; * crosses / and :; ? is exactly one character",
        {"u": U()},
        [S("br", "Allow", ["u"], ["get"], ["log[1-3]/*"]), S("q", "Allow", ["u"], ["put"], ["a?c"]),
         S("cross", "Allow", ["u"], ["del"], ["arn:*:x"])],
        [Q("u", "get", "log2/a"), Q("u", "get", "log[1-3]/a/b:c"), Q("u", "put", "ac"), Q("u", "put", "a/c"),
         Q("u", "put", "abbc"), Q("u", "del", "arn:a/b:c:x"), Q("u", "del", "arn:x")],
        [IMPLICIT, ALLOW("br"), IMPLICIT, ALLOW("q"), IMPLICIT, ALLOW("cross"), IMPLICIT]))

    # The Kelvin sign U+212A is not an ASCII letter, so it is not folded and never equals "k".
    # "ß" (sharp s) is not folded either, so it never equals "ss".
    cs.append(case(
        "H10", "action case folding is ASCII-only; resources and principal ids are case-sensitive",
        {"u": U(), "U2": U()},
        [S("kelvin", "Allow", ["u"], ["KMS:Encrypt"], ["*"]),
         S("plain", "Allow", ["u"], ["kms:Decrypt"], ["Key/*"]),
         S("caps", "Allow", ["u2"], ["*"], ["*"]),
         S("ss", "Allow", ["u"], ["s3:straße"], ["*"])],
        [Q("u", "kms:encrypt", "k"), Q("u", "KMS:ENCRYPT", "k"), Q("u", "KMS:DECRYPT", "Key/1"),
         Q("u", "kms:decrypt", "key/1"), Q("U2", "x", "y"), Q("u", "S3:STRASSE", "x"),
         Q("u", "S3:STRAßE", "x")],
        [IMPLICIT, ALLOW("kelvin"), ALLOW("plain"), IMPLICIT, IMPLICIT, IMPLICIT, ALLOW("ss")]))

    good = {"sid": "good", "effect": "Allow", "principals": ["u"], "actions": ["get"], "resources": ["r"],
            "set": None}
    cs.append(case(
        "H11", "malformed statements: effect case, bare strings, empty or doubled lists, unknown keys",
        {"u": U()},
        [{"sid": "e1", "effect": "allow", "principals": ["u"], "actions": ["get"], "resources": ["r"]},
         {"sid": "e2", "effect": "Allow", "principals": "u", "actions": ["get"], "resources": ["r"]},
         {"sid": "e3", "effect": "Allow", "principals": ["u"], "actions": "get", "resources": ["r"]},
         {"sid": "e4", "effect": "Allow", "principals": ["u"], "actions": ["get"], "not_actions": ["x"],
          "resources": ["r"]},
         {"sid": "e5", "effect": "Allow", "principals": ["u"], "resources": ["r"]},
         {"sid": "e6", "effect": "Allow", "principals": ["u"], "actions": ["get"], "resources": ["r"],
          "Condition": {}},
         {"sid": "e7", "effect": "Allow", "principals": ["u"], "actions": ["get"], "resources": []},
         {"sid": "", "effect": "Allow", "principals": ["u"], "actions": ["get"], "resources": ["r"]},
         {"sid": "e9", "effect": "Allow", "principals": ["u"], "actions": ["get", 5], "resources": ["r"]},
         {"sid": "d1", "effect": "DENY", "principals": ["u"], "actions": ["get"], "resources": ["r"]},
         {"sid": "d2", "effect": "Deny", "principals": ["u"], "actions": ["get"], "resources": ["r"],
          "conditions": None},
         {"sid": "d3", "effect": "Deny", "principals": ["u"], "actions": ["get"], "resources": "r"},
         {"sid": "d4", "effect": "Deny", "principals": [], "actions": ["get"], "resources": ["r"]},
         good],
        [Q("u", "get", "r")],
        [ALLOW("good")]))

    # Only id and b-put are well-formed; B therefore contains only "put" requests.
    cs.append(case(
        "H12", "malformed statements: principals in a boundary statement, missing in an identity one, bad set",
        {"u": U(boundary="B")},
        [S("id", "Allow", ["u"], ["*"], ["*"]),
         {"sid": "b-with-principals", "set": "B", "effect": "Allow", "principals": ["u"], "actions": ["get"],
          "resources": ["*"]},
         {"sid": "b-empty", "set": "", "effect": "Allow", "actions": ["*"], "resources": ["*"]},
         {"sid": "id-noprin", "effect": "Allow", "actions": ["*"], "resources": ["*"]},
         B("b-put", "B", "Allow", ["put"], ["*"]),
         {"sid": "b-num", "set": 7, "effect": "Allow", "actions": ["*"], "resources": ["*"]}],
        [Q("u", "get", "x"), Q("u", "put", "x")],
        [OUTSIDE, ALLOW("b-put", "id")]))

    cs.append(case(
        "H13", "a role's boundary applies to everyone who inherits it; a set with no statements contains nothing",
        {"u": U(["r"]), "r": R(boundary="RB"), "v": U(["r2"]), "r2": R(boundary="EMPTY"), "w": U()},
        [S("all", "Allow", ["*"], ["*"], ["*"]), B("rb", "RB", "Allow", ["read"], ["*"])],
        [Q("u", "read", "x"), Q("u", "write", "x"), Q("r", "write", "x"), Q("v", "read", "x"),
         Q("w", "write", "x")],
        [ALLOW("all", "rb"), OUTSIDE, OUTSIDE, OUTSIDE, ALLOW("all")]))

    cs.append(case(
        "H14", "identity deny beats the boundary; boundary denies are listed only under outside_boundary",
        {"u": U(boundary="B")},
        [S("allow", "Allow", ["u"], ["*"], ["*"]), S("deny-x", "Deny", ["u"], ["x:*"], ["*"]),
         B("b-all", "B", "Allow", ["*"], ["*"]), B("b-deny", "B", "Deny", ["x:*", "y:*"], ["*"]),
         B("b-deny2", "B", "Deny", ["y:Del*"], ["*"])],
        [Q("u", "x:Get", "r"), Q("u", "y:Delete", "r"), Q("u", "z:Get", "r")],
        [EXPLICIT("deny-x"), DENY("outside_boundary", "b-deny", "b-deny2"), ALLOW("allow", "b-all")]))

    # Boundary sets of u: {B1 (u and r2), B2 (r1)}. Sorted by code point: "Z-allow" < "b1" < "b2".
    cs.append(case(
        "H15", "every boundary set must contain the request; duplicate sids are listed once",
        {"u": U(["r1", "r2"], boundary="B1"), "r1": R(boundary="B2"), "r2": R(boundary="B1")},
        [S("Z-allow", "Allow", ["r2"], ["*"], ["*"]),
         B("b1", "B1", "Allow", ["s3:*", "ec2:*"], ["*"]),
         B("b2", "B2", "Allow", ["s3:*"], ["*"]),
         B("b2", "B2", "Allow", ["s3:Get*"], ["*"])],
        [Q("u", "s3:GetObject", "k"), Q("u", "ec2:Run", "k"), Q("u", "s3:Put", "k")],
        [ALLOW("Z-allow", "b1", "b2"), OUTSIDE, ALLOW("Z-allow", "b1", "b2")]))

    cs.append(case(
        "H16", "plain negated operator: true for a missing key, false for an empty list, any-value for lists",
        {"u": U()},
        [S("allow", "Allow", ["u"], ["*"], ["*"]),
         S("not-corp", "Deny", ["u"], ["*"], ["*"], conditions={"StringNotEquals": {"net": "corp"}})],
        [Q("u", "a", "r", {}), Q("u", "a", "r", {"net": "corp"}), Q("u", "a", "r", {"net": "home"}),
         Q("u", "a", "r", {"net": []}), Q("u", "a", "r", {"net": ["corp", "home"]}),
         Q("u", "a", "r", {"NET": "corp"})],
        [EXPLICIT("not-corp"), ALLOW("allow"), EXPLICIT("not-corp"), ALLOW("allow"), EXPLICIT("not-corp"),
         EXPLICIT("not-corp")]))

    cs.append(case(
        "H17", "ForAllValues is true for a missing key or an empty list; ForAnyValue is false for both",
        {"u": U()},
        [S("all-ok", "Allow", ["u"], ["a"], ["*"], conditions={"ForAllValues:StringEquals": {"tags": ["x", "y"]}}),
         S("any-ok", "Allow", ["u"], ["b"], ["*"], conditions={"ForAnyValue:StringEquals": {"tags": ["x", "y"]}})],
        [Q("u", "a", "r", {}), Q("u", "a", "r", {"tags": []}), Q("u", "a", "r", {"tags": ["x", "z"]}),
         Q("u", "a", "r", {"tags": "y"}), Q("u", "b", "r", {}), Q("u", "b", "r", {"tags": []}),
         Q("u", "b", "r", {"tags": ["z", "y"]})],
        [ALLOW("all-ok"), ALLOW("all-ok"), IMPLICIT, ALLOW("all-ok"), IMPLICIT, IMPLICIT, ALLOW("any-ok")]))

    # neg-ie with n = "abc": present, not a number, so it does not pass -> false -> no deny.
    cs.append(case(
        "H18", "IfExists is true for a missing key and changes nothing for a present one",
        {"u": U()},
        [S("ie", "Allow", ["u"], ["a"], ["*"], conditions={"StringEqualsIfExists": {"region": ["eu", "us"]}}),
         S("any-ie", "Allow", ["u"], ["b"], ["*"], conditions={"ForAnyValue:StringLikeIfExists": {"zone": "eu-*"}}),
         S("neg-ie", "Deny", ["u"], ["c"], ["*"], conditions={"NumericNotEqualsIfExists": {"n": "5"}}),
         S("c-allow", "Allow", ["u"], ["c"], ["*"])],
        [Q("u", "a", "r", {}), Q("u", "a", "r", {"region": "ap"}), Q("u", "a", "r", {"region": ["ap", "eu"]}),
         Q("u", "b", "r", {"zone": []}), Q("u", "b", "r", {}), Q("u", "c", "r", {}),
         Q("u", "c", "r", {"n": "5.0"}), Q("u", "c", "r", {"n": "abc"})],
        [ALLOW("ie"), IMPLICIT, ALLOW("ie"), IMPLICIT, ALLOW("any-ie"), EXPLICIT("neg-ie"), ALLOW("c-allow"),
         ALLOW("c-allow")]))

    cs.append(case(
        "H19", "keys and operators combine with AND, values with OR; an empty operator dict imposes nothing",
        {"u": U()},
        [S("and", "Allow", ["u"], ["a"], ["*"],
           conditions={"StringEquals": {"k1": "x", "k2": ["p", "q"]}, "StringLike": {"k3": "img-*"}}),
         S("empty", "Allow", ["u"], ["b"], ["*"], conditions={"StringEquals": {}, "Bool": {}})],
        [Q("u", "a", "r", {"k1": "x", "k2": "q", "k3": "img-1"}),
         Q("u", "a", "r", {"k1": ["y", "x"], "k2": ["r", "p"], "k3": ["doc", "img-"]}),
         Q("u", "a", "r", {"k1": "x", "k2": "q"}),
         Q("u", "a", "r", {"k1": "x", "k2": "Q", "k3": "img-1"}),
         Q("u", "b", "r", {})],
        [ALLOW("and"), ALLOW("and"), IMPLICIT, IMPLICIT, ALLOW("empty")]))

    nums = ["9", "+5", " 5", "5.", ".5", "1e0", "٥", "5\n", "-007.50", "1_0", "10", "9.999999999999999999999"]
    cs.append(case(
        "H20", "numbers: strict ASCII grammar, exact comparison",
        {"u": U()},
        [S("lt", "Allow", ["u"], ["a"], ["*"], conditions={"NumericLessThan": {"n": "10"}})],
        [Q("u", "a", "r", {"n": v}) for v in nums],
        [ALLOW("lt"), IMPLICIT, IMPLICIT, IMPLICIT, IMPLICIT, IMPLICIT, IMPLICIT, IMPLICIT, ALLOW("lt"), IMPLICIT,
         IMPLICIT, ALLOW("lt")]))

    # 9007199254740992 and ...993 differ exactly (as floats they would be equal). "bad" has "2e1": malformed.
    cs.append(case(
        "H21", "numbers compare exactly; NumericNotEquals on a non-number is false; a bad policy number",
        {"u": U()},
        [S("eq", "Allow", ["u"], ["a"], ["*"], conditions={"NumericEquals": {"id": "9007199254740993"}}),
         S("ne", "Allow", ["u"], ["b"], ["*"], conditions={"NumericNotEquals": {"n": ["1", "2.0"]}}),
         S("bad", "Allow", ["u"], ["c", "a", "b"], ["*"], conditions={"NumericGreaterThan": {"n": ["1", "2e1"]}}),
         S("ge", "Allow", ["u"], ["c"], ["*"],
           conditions={"NumericGreaterThanEquals": {"n": "-0"}, "NumericLessThanEquals": {"n": "0.0"}})],
        [Q("u", "a", "r", {"id": "9007199254740992"}), Q("u", "a", "r", {"id": "9007199254740993.000"}),
         Q("u", "b", "r", {"n": "3"}), Q("u", "b", "r", {"n": "2"}), Q("u", "b", "r", {"n": "two"}),
         Q("u", "b", "r", {}), Q("u", "c", "r", {"n": "0"}), Q("u", "c", "r", {"n": "-0.000"}),
         Q("u", "c", "r", {"n": "0.001"})],
        [IMPLICIT, ALLOW("eq"), ALLOW("ne"), IMPLICIT, IMPLICIT, ALLOW("ne"), ALLOW("ge"), ALLOW("ge"), IMPLICIT]))

    cs.append(case(
        "H22", "Bool is exact; Null tests presence (true = absent); Null takes no prefix or suffix",
        {"u": U()},
        [S("mfa", "Allow", ["u"], ["a"], ["*"], conditions={"Bool": {"mfa": "true"}}),
         S("bad-bool", "Allow", ["u"], ["a", "b", "c"], ["*"], conditions={"Bool": {"mfa": "True"}}),
         S("no-src", "Allow", ["u"], ["b"], ["*"], conditions={"Null": {"src": "true"}}),
         S("has-src", "Allow", ["u"], ["c"], ["*"], conditions={"Null": {"src": "false"}}),
         S("bad-null", "Allow", ["u"], ["a", "b", "c"], ["*"], conditions={"NullIfExists": {"src": "true"}}),
         S("bad-null2", "Allow", ["u"], ["a", "b", "c"], ["*"], conditions={"ForAnyValue:Null": {"src": "false"}})],
        [Q("u", "a", "r", {"mfa": "true"}), Q("u", "a", "r", {"mfa": "True"}),
         Q("u", "a", "r", {"mfa": ["false", "true"]}), Q("u", "b", "r", {}), Q("u", "b", "r", {"src": "x"}),
         Q("u", "c", "r", {"src": []}), Q("u", "c", "r", {})],
        [ALLOW("mfa"), IMPLICIT, ALLOW("mfa"), ALLOW("no-src"), IMPLICIT, ALLOW("has-src"), IMPLICIT]))

    cs.append(case(
        "H23", "operator names: prefix plus suffix is valid; wrong case, doubled parts and bad values are not",
        {"u": U()},
        [S("o1", "Allow", ["u"], ["a1"], ["*"], conditions={"ForAllValues:StringLikeIfExists": {"k": "x*"}}),
         S("o2", "Allow", ["u"], ["a2"], ["*"], conditions={"StringEqualsIfExistsIfExists": {"k": "x"}}),
         S("o3", "Allow", ["u"], ["a3"], ["*"], conditions={"forAnyValue:StringEquals": {"k": "x"}}),
         S("o4", "Allow", ["u"], ["a4"], ["*"], conditions={"ForAnyValue:ForAllValues:StringEquals": {"k": "x"}}),
         S("o5", "Allow", ["u"], ["a5"], ["*"], conditions={"StringNotEquals": {"k": []}}),
         S("o6", "Allow", ["u"], ["a6"], ["*"], conditions={"StringNotEquals": {"k": 1}}),
         S("o7", "Allow", ["u"], ["a7"], ["*"], conditions={"StringEquals": "x"}),
         S("o8", "Allow", ["u"], ["a8"], ["*"], conditions={"NumericLessThanEqualsIfExists": {"k": "3"}})],
        [Q("u", "a1", "r", {"k": ["x1", "y"]}), Q("u", "a1", "r", {"k": ["x1", "x"]}),
         Q("u", "a2", "r", {"k": "x"}), Q("u", "a3", "r", {"k": "x"}), Q("u", "a4", "r", {"k": "x"}),
         Q("u", "a5", "r", {"k": "x"}), Q("u", "a6", "r", {"k": "x"}), Q("u", "a7", "r", {"k": "x"}),
         Q("u", "a8", "r", {}), Q("u", "a8", "r", {"k": "3.5"})],
        [IMPLICIT, ALLOW("o1"), IMPLICIT, IMPLICIT, IMPLICIT, IMPLICIT, IMPLICIT, IMPLICIT, ALLOW("o8"), IMPLICIT]))

    cs.append(case(
        "H24", "not_actions and not_resources",
        {"u": U()},
        [{"sid": "na", "effect": "Allow", "principals": ["u"], "not_actions": ["iam:*", "s3:Delete*"],
          "resources": ["*"]},
         {"sid": "nr", "effect": "Deny", "principals": ["u"], "actions": ["s3:*"],
          "not_resources": ["arn:s3:pub/*", "arn:s3:tmp/?"]}],
        [Q("u", "s3:GetObject", "arn:s3:pub/x"), Q("u", "s3:GetObject", "arn:s3:priv/x"),
         Q("u", "IAM:CreateUser", "x"), Q("u", "s3:deleteBucket", "arn:s3:tmp/a"),
         Q("u", "ec2:Run", "arn:s3:tmp/ab")],
        [ALLOW("na"), EXPLICIT("nr"), IMPLICIT, IMPLICIT, ALLOW("na")]))

    cs.append(case(
        "H25", "principal patterns match any member of the identity set, wildcards included",
        {"alice": U(["team-a", "team-b"]), "team-a": R(), "team-b": R(["ops-x"]), "ops-x": R(), "bob": U()},
        [S("teams", "Allow", ["team-?"], ["read"], ["*"]),
         S("ops", "Allow", ["ops-*", "nobody"], ["write"], ["*"]),
         S("exact", "Allow", ["team"], ["exec"], ["*"])],
        [Q("alice", "read", "r"), Q("alice", "write", "r"), Q("alice", "exec", "r"), Q("bob", "read", "r"),
         Q("ops-x", "write", "r")],
        [ALLOW("teams"), ALLOW("ops"), IMPLICIT, IMPLICIT, ALLOW("ops")]))

    # Code-point order: "B" (0x42) < "_x" (0x5F) < "b" (0x62) < "é" (0xE9).
    cs.append(case(
        "H26", "allowed lists every matching identity allow, without duplicates, in code-point order",
        {"u": U()},
        [S("b", "Allow", ["u"], ["*"], ["*"]), S("B", "Allow", ["u"], ["get"], ["*"]),
         S("b", "Allow", ["u"], ["g*"], ["*"]), S("_x", "Allow", ["u"], ["*"], ["r*"]),
         S("é", "Allow", ["u"], ["*"], ["*"]), S("never", "Allow", ["u"], ["put"], ["*"])],
        [Q("u", "get", "r1"), Q("u", "list", "z")],
        [ALLOW("B", "_x", "b", "é"), ALLOW("b", "é")]))

    cs.append(case(
        "H27", "explicit_deny lists every matching identity deny, whatever the statement order",
        {"u": U(["r"]), "r": R()},
        [S("d2", "Deny", ["r"], ["*"], ["secret/*"]), S("a", "Allow", ["u"], ["*"], ["*"]),
         S("d1", "Deny", ["u"], ["get"], ["*"])],
        [Q("u", "get", "secret/1"), Q("u", "put", "secret/1"), Q("u", "put", "pub")],
        [EXPLICIT("d1", "d2"), EXPLICIT("d2"), ALLOW("a")]))

    # u's own tag proj = "p1" wins over r's "p9"; r requesting on its own has proj = "p9" and boundary B.
    cs.append(case(
        "H28", "boundary statements have no principals and resolve references for the request principal",
        {"u": U(["r"], tags={"proj": "p1"}), "r": R(boundary="B", tags={"proj": "p9"})},
        [S("all", "Allow", ["*"], ["*"], ["*"]),
         B("b-own", "B", "Allow", ["*"], ["proj/${tag:proj}/*", "home/${principal}"])],
        [Q("u", "get", "proj/p1/x"), Q("u", "get", "proj/p9/x"), Q("r", "get", "proj/p9/x"),
         Q("u", "get", "home/u"), Q("u", "get", "home/r")],
        [ALLOW("all", "b-own"), OUTSIDE, ALLOW("all", "b-own"), ALLOW("all", "b-own"), OUTSIDE]))

    cs.append(case(
        "H29", "glob edge cases: empty pattern, doubled stars, overlapping literal segments",
        {"u": U()},
        [S("empty", "Allow", ["u"], ["e"], [""]), S("stars", "Allow", ["u"], ["s"], ["a**b*?"]),
         S("ends", "Allow", ["u"], ["t"], ["*ab*ab*"])],
        [Q("u", "e", ""), Q("u", "e", "x"), Q("u", "s", "ab"), Q("u", "s", "abc"), Q("u", "s", "aXbYZ"),
         Q("u", "t", "abab"), Q("u", "t", "aba"), Q("u", "t", "xaby")],
        [ALLOW("empty"), IMPLICIT, IMPLICIT, ALLOW("stars"), ALLOW("stars"), ALLOW("ends"), IMPLICIT, IMPLICIT]))

    # Condition values never contain references, and [a] is ordinary text there too.
    cs.append(case(
        "H30", "StringLike / StringNotLike: no references, [ is ordinary, negated base on a missing key",
        {"u": U()},
        [S("like", "Allow", ["u"], ["a"], ["*"], conditions={"StringLike": {"path": "/home/${principal}/*"}}),
         S("b-allow", "Allow", ["u"], ["b"], ["*"]),
         S("notlike", "Deny", ["u"], ["b"], ["*"], conditions={"StringNotLike": {"f": ["*.txt", "[a]*"]}})],
        [Q("u", "a", "r", {"path": "/home/u/x"}), Q("u", "a", "r", {"path": "/home/${principal}/x"}),
         Q("u", "b", "r", {"f": "x.txt"}), Q("u", "b", "r", {"f": "a.doc"}), Q("u", "b", "r", {"f": "[a].doc"}),
         Q("u", "b", "r", {})],
        [IMPLICIT, ALLOW("like"), ALLOW("b-allow"), EXPLICIT("notlike"), ALLOW("b-allow"), EXPLICIT("notlike")]))

    return cs


# ── Generated cases: small universes dense in traps ─────────────────────────
USERS = ["u0", "u1", "u2", "dev*"]
ROLES = ["r0", "r1", "r2", "r3", "r4", "a?"]
TAG_KEYS = ["team", "env"]
TAG_VALUES = ["core", "ops", "", "a*", "x?y", "core"]
PRINCIPAL_PATTERNS = ["u0", "u1", "u?", "r0", "r1", "r2", "r3", "r4", "r*", "*", "a?", "dev*", "U0", "zz", "?0",
                      "*", "r*", "u?", "dev*"]
ACTION_PATTERNS = ["s3:Get*", "s3:*", "S3:GET?BJECT", "s3:get?bject", "*", "iam:*", "Kms:*", "kms:*",
                   "s3:Delete*", "ec2:Run*", "*:list*", "s3:*Object", "sqs:*"]
ACTIONS = ["s3:GetObject", "S3:getobject", "s3:DeleteObject", "s3:PutObject", "iam:CreateUser", "kms:Encrypt",
           "KMS:Encrypt", "ec2:RunInstances", "s3:ListBucket", "sqs:List", "s3:Get0bject"]
RESOURCE_PATTERNS = ["*", "arn:s3:*", "arn:s3:pub/*", "home/${principal}/*", "team/${tag:team}/*", "env/${tag:env}",
                     "log[1]/*", "arn:s3:??/*", "a${*}b", "x${$}y", "proj/${tag:team}${?}", "home/*/${tag:env}",
                     "team/*", "*/${principal}", "env/*", "home/u?/*"]
RESOURCES = ["arn:s3:pub/a", "arn:s3:ab/c", "arn:s3:abc/d", "home/u0/x", "home/u1/x", "home/dev*/x",
             "home/devops/x", "team/core/1", "team/ops/1", "team//1", "team/a*/1", "team/ab/1", "env/", "env/core",
             "env/ops", "log[1]/x", "log1/x", "a*b", "aXb", "x$y", "proj/core?", "proj/corex", "home/u0/ops",
             "home/r1/core", "env/a*", "env/aXb", "x/u0", "x/r1", "home/u2/", "team/x?y/2"]
GOOD_CONDS = [
    {"StringEquals": {"net": "corp"}},
    {"StringNotEquals": {"net": ["corp", "vpn"]}},
    {"StringLike": {"path": "/home/*"}},
    {"StringNotLike": {"path": ["*.tmp", "[x]*"]}},
    {"ForAllValues:StringEquals": {"labels": ["a", "b"]}},
    {"ForAnyValue:StringEquals": {"labels": ["b", "c"]}},
    {"ForAnyValue:StringNotEquals": {"labels": "a"}},
    {"ForAllValues:StringNotLike": {"labels": "secret*"}},
    {"StringEqualsIfExists": {"net": "corp"}},
    {"ForAnyValue:StringLikeIfExists": {"labels": "a*"}},
    {"NumericLessThan": {"n": "10"}},
    {"NumericGreaterThanEquals": {"n": ["-1.5", "100"]}},
    {"NumericNotEquals": {"n": "5"}},
    {"NumericEquals": {"n": "9007199254740993"}},
    {"NumericLessThanEqualsIfExists": {"n": "0"}},
    {"ForAllValues:NumericLessThan": {"n": "10"}},
    {"Bool": {"mfa": "true"}},
    {"BoolIfExists": {"mfa": "false"}},
    {"Null": {"mfa": "true"}},
    {"Null": {"labels": "false"}},
    {"StringNotLikeIfExists": {"net": "c*"}},
    {"ForAnyValue:NumericGreaterThan": {"n": "9"}},
    {"StringEquals": {"labels": "a"}},
    {"StringNotEquals": {"labels": ["a", "c"]}},
    {"NumericLessThan": {"n": "9007199254740993"}},
    {"NumericGreaterThan": {"n": "9.9999999999999999999"}},
]
BAD_CONDS = [{"Bool": {"mfa": "True"}}, {"NumericLessThan": {"n": "1e1"}}, {"StringNotEquals": {"net": []}},
             {"stringEquals": {"net": "corp"}}, {"NullIfExists": {"mfa": "true"}}, {"StringNotEquals": {"net": 5}},
             {"ForAnyValue:Null": {"mfa": "true"}}, {"NumericNotEquals": {"n": "+5"}}, {"StringEquals": "corp"},
             {"ForAllValues:StringEqualsIfExistsIfExists": {"net": "corp"}}]
# For each pattern, request strings that match it or nearly do, so generated requests hit the traps.
ACTION_EXAMPLES = {
    "s3:Get*": ["s3:GetObject", "S3:getobject", "s3:Get", "s3:PutObject"],
    "s3:*": ["s3:PutObject", "S3:x", "s3", "s4:x"],
    "S3:GET?BJECT": ["s3:getobject", "s3:Get0bject", "s3:GetBJECT"],
    "s3:get?bject": ["S3:GETOBJECT", "s3:getbject", "s3:get/bject"],
    "*": ["anything", ""],
    "iam:*": ["iam:CreateUser", "IAM:x", "iam"],
    "Kms:*": ["KMS:Encrypt", "kms:Encrypt", "Kms:x"],
    "kms:*": ["kms:Encrypt", "KMS:Decrypt", "KMS:Encrypt"],
    "s3:Delete*": ["s3:DeleteObject", "s3:deletebucket", "s3:Delet"],
    "ec2:Run*": ["ec2:RunInstances", "EC2:run", "ec2:Ru"],
    "*:list*": ["sqs:List", "s3:ListBucket", "list", "x:LIST"],
    "s3:*Object": ["s3:GetObject", "s3:Object", "s3:GetObjects"],
    "sqs:*": ["sqs:Send", "SQS:", "sqs"],
}
RESOURCE_EXAMPLES = {
    "*": ["", "x"],
    "arn:s3:*": ["arn:s3:", "arn:s3:pub/a", "arn:S3:x"],
    "arn:s3:pub/*": ["arn:s3:pub/a", "arn:s3:pub", "arn:s3:pub/"],
    "home/${principal}/*": ["home/u0/x", "home/u1/", "home/dev*/x", "home/devops/x", "home/r1/a", "home/a?/q",
                            "home/ab/q"],
    "team/${tag:team}/*": ["team/core/1", "team/ops/1", "team//1", "team/a*/1", "team/ab/1", "team/x?y/2",
                           "team/xzy/2"],
    "env/${tag:env}": ["env/", "env/core", "env/ops", "env/a*", "env/aXb", "env/x?y"],
    "log[1]/*": ["log[1]/x", "log1/x"],
    "arn:s3:??/*": ["arn:s3:ab/c", "arn:s3:abc/d", "arn:s3:a/c"],
    "a${*}b": ["a*b", "aXb"],
    "x${$}y": ["x$y", "x${$}y"],
    "proj/${tag:team}${?}": ["proj/core?", "proj/corex", "proj/?", "proj/ops?"],
    "home/*/${tag:env}": ["home/u0/ops", "home/r1/core", "home/x/", "home/a/b/core"],
    "team/*": ["team/x", "team"],
    "*/${principal}": ["x/u0", "x/r1", "/u1", "a/b/dev*"],
    "env/*": ["env/x", "env"],
    "home/u?/*": ["home/u0/x", "home/u12/x"],
}
CTX_VALUES = {
    "net": ["corp", "vpn", "home", ["corp"], ["home", "corp"], [], "Corp"],
    "path": ["/home/x", "/tmp/a.tmp", "[x]y", "x", ["/home/a", "/b"], [], "xy"],
    "labels": ["a", ["a", "b"], ["b", "c"], [], ["secret-1"], ["a", "secret"], "c"],
    "n": ["5", "9", "10", "-0", "+5", "1e1", "9007199254740992", "9007199254740993", "-1.50", " 5", "05.0",
          "٥", ["1", "20"], [], "abc", "100.0", "9.5"],
    "mfa": ["true", "false", "True", ["true"], [], "1"],
}


def random_principals(r):
    ids = USERS[:2 + r.below(3)] + ROLES[:3 + r.below(4)]
    principals = {}
    for pid in ids:
        kind = "user" if pid in USERS else "role"
        inherits = []
        for _ in range(r.below(3)):
            inherits.append(r.pick(ROLES[:5] + ["ghost", "u1", "a?"]))
        tags = {}
        for k in TAG_KEYS:
            if r.chance(2, 7):
                tags[k] = r.pick(TAG_VALUES)
        boundary = r.pick(["B1", "B2", "B0"]) if r.chance(1, 8) else None
        principals[pid] = {"kind": kind, "inherits": inherits, "boundary": boundary, "tags": tags}
    return principals


def maybe_malform(r, st):
    k = r.below(12)
    if k == 0:
        st["effect"] = st["effect"].lower()
    elif k == 1:
        st["actions" if "actions" in st else "not_actions"] = r.pick(ACTION_PATTERNS)
    elif k == 2:
        st["Condition"] = {}
    elif k == 3:
        if "set" in st:
            st["principals"] = ["*"]
        else:
            st.pop("principals")
    elif k == 4:
        st["not_resources" if "resources" in st else "resources"] = ["*"]
    elif k == 5:
        st["resources" if "resources" in st else "not_resources"] = [r.pick(["r/${Principal}", "r/${tag:}",
                                                                           "x${", "${ tag:team}", "${}"])]
    elif k == 6:
        st["conditions"] = dict(r.pick(BAD_CONDS))
    elif k == 7:
        st["sid"] = ""
    elif k == 8:
        st["set"] = ""
    else:
        st["actions" if "actions" in st else "not_actions"] = []
    return st


def random_statement(r, idx, boundary):
    effect = "Deny" if r.chance(1, 3) else "Allow"
    st = {"sid": r.pick(["s", "S", "t", "_", "s"]) + str(idx % 7)}
    st["effect"] = effect
    if boundary:
        st["set"] = r.pick(["B1", "B1", "B2"])
    else:
        st["principals"] = [r.pick(PRINCIPAL_PATTERNS) for _ in range(1 + r.below(2))]
    acts = [r.pick(ACTION_PATTERNS) for _ in range(1 + r.below(2))]
    st["not_actions" if r.chance(1, 8) else "actions"] = acts
    ress = [r.pick(RESOURCE_PATTERNS) for _ in range(1 + r.below(2))]
    st["not_resources" if r.chance(1, 7) else "resources"] = ress
    if r.chance(1, 3):
        conds = {}
        for _ in range(1 + r.below(2)):
            c = r.pick(GOOD_CONDS)
            for op, body in c.items():
                conds.setdefault(op, {}).update(body)
        st["conditions"] = conds
    if effect == "Deny" and "conditions" not in st and r.chance(1, 2):
        st["conditions"] = dict(r.pick(GOOD_CONDS))
    if r.chance(1, 9):
        maybe_malform(r, st)
    return st


def random_context(r):
    ctx = {}
    for k in ("net", "path", "labels", "n", "mfa"):
        if r.chance(1, 2):
            v = r.pick(CTX_VALUES[k])
            ctx[k] = list(v) if type(v) is list else v
    return ctx


def pattern_list(st, a, b):
    v = st.get(a, st.get(b))
    return v if type(v) is list and v and all(type(x) is str for x in v) else []


def random_request(r, ids, policies):
    """Usually aimed at one statement: an action and a resource that match its patterns or nearly do."""
    pid = r.pick(ids) if r.chance(14, 15) else r.pick(["ghost", "U0", "r9"])
    action, resource = r.pick(ACTIONS), r.pick(RESOURCES)
    if policies and r.chance(3, 4):
        st = r.pick(policies)
        named = [p for p in pattern_list(st, "principals", "principals") if p in ids]
        if named and r.chance(1, 2) and pid in ids:
            pid = r.pick(named)
        acts = [p for p in pattern_list(st, "actions", "not_actions") if p in ACTION_EXAMPLES]
        ress = [p for p in pattern_list(st, "resources", "not_resources") if p in RESOURCE_EXAMPLES]
        # the first example of each pattern matches it (references permitting); the others are near misses
        if acts and r.chance(4, 5):
            ex = ACTION_EXAMPLES[r.pick(acts)]
            action = ex[0] if r.chance(1, 2) else r.pick(ex)
        if ress and r.chance(4, 5):
            ex = RESOURCE_EXAMPLES[r.pick(ress)]
            resource = ex[0] if r.chance(1, 2) else r.pick(ex)
    return Q(pid, action, resource, random_context(r))


def random_cases():
    res = []
    for i in range(100):
        r = SplitMix(1100 + i)
        principals = random_principals(r)
        n_id = 3 + r.below(6)
        policies = [random_statement(r, j, False) for j in range(n_id)]
        policies += [random_statement(r, n_id + j, True) for j in range(r.below(4))]
        # shuffle (Fisher-Yates with the version-independent PRNG)
        for j in range(len(policies) - 1, 0, -1):
            k = r.below(j + 1)
            policies[j], policies[k] = policies[k], policies[j]
        requests = [random_request(r, list(principals), policies) for _ in range(10 + r.below(8))]
        res.append({"id": f"R{i + 1:03d}", "title": "random policy universe", "args": [principals, policies, requests]})
    return res


def hidden():
    return hand() + random_cases()


# ── Stress ──────────────────────────────────────────────────────────────────
def stress():
    return [{"id": "S1", "title": "dozens of stars against long resources and context values", "seed": 111,
             "requests": 120, "statements": 12, "min_len": 150, "max_len": 600},
            {"id": "S2", "title": "inheritance chain 50 000 roles deep, with a cycle", "seed": 112,
             "depth": 50000, "requests": 60},
            {"id": "S3", "title": "20 000 requests from 60 users over dense role clusters", "seed": 113,
             "clusters": 40, "cluster_size": 150, "degree": 60, "users": 60, "requests": 20000}]


def stress_glob(case):
    r = SplitMix(case["seed"])
    n_st = case["statements"]
    principals = {f"u{i}": U(["dev"], tags={"team": "a" * (1 + i % 3)}) for i in range(20)}
    principals["dev"] = R()
    policies = []
    for j in range(n_st):
        stars = 12 + r.below(20)
        body = "".join(r.pick(["*a", "*a", "*aa", "*?a", "*a?"]) for _ in range(stars))
        res = "data/" + body + "*b"
        st = S(f"g{j:02d}", "Deny" if j % 4 == 3 else "Allow", ["dev", "u*"], [f"svc{j}:*"], [res])
        if j % 3 == 0:
            st["conditions"] = {"StringLike": {"path": "".join(r.pick(["a*", "a*?", "aa*"]) for _ in range(stars))
                                               + "z"}}
        if j % 5 == 1:
            st["resources"].append("data/${tag:team}" + "*a" * stars + "*b")
        policies.append(st)
    policies.append(S("wide", "Allow", ["*"], ["svc*:Op"], ["data/*a*a*a*a*a*a*a*a*a*a*a*c"]))
    requests = []
    for k in range(case["requests"]):
        length = case["min_len"] + r.below(case["max_len"] - case["min_len"])
        tail = r.pick(["b", "c", "ab", "ba", "c", "c"])
        res = "data/" + "a" * length + tail
        ctx = {"path": "a" * (length // 2) + r.pick(["z", "y", "az"])} if r.chance(2, 3) else {}
        requests.append(Q(f"u{r.below(20)}", f"svc{r.below(n_st)}:Op", res, ctx))
    return [principals, policies, requests]


def stress_chain(case):
    r = SplitMix(case["seed"])
    depth = case["depth"]
    principals = {}
    for i in range(depth):
        inherits = [f"r{i + 1}" if i + 1 < depth else "r0"]
        if i % 997 == 0:
            inherits += [f"ghost{i}", "u0"]
        tags = {}
        if i == depth - 10:
            tags = {"team": "far"}
        elif i == depth - 5:
            tags = {"team": "farther", "env": "deep"}
        elif i == 30000:
            tags = {"env": "mid"}
        principals[f"r{i}"] = R(inherits, boundary="B" if i == depth - 1 else None, tags=tags)
    principals["u0"] = U(["r0"])
    principals["u1"] = U([f"r{depth // 2}"], tags={"env": "own"})
    principals["u2"] = U(["r1", "r2", "r3"])
    policies = [
        S("deep", "Allow", [f"r{depth - 1}"], ["s3:*"], ["proj/${tag:team}/*"]),
        S("wild", "Allow", [f"r{depth // 10}?"], ["ec2:*"], ["*"]),
        S("env", "Allow", ["r*"], ["sqs:*"], ["env/${tag:env}"]),
        S("deny", "Deny", ["r12345"], ["s3:Delete*"], ["*"]),
        B("b", "B", "Allow", ["s3:*", "ec2:Describe*", "sqs:*"], ["*"]),
        B("b-deny", "B", "Deny", ["s3:*"], ["proj/far/secret*"]),
    ]
    pairs = [("s3:GetObject", "proj/far/x"), ("s3:GetObject", "proj/farther/x"), ("s3:DeleteObject", "proj/far/x"),
             ("s3:GetObject", "proj/far/secret1"), ("ec2:DescribeInstances", "i-1"), ("ec2:RunInstances", "i-1"),
             ("sqs:Send", "env/mid"), ("sqs:Send", "env/deep"), ("sqs:Send", "env/own"), ("s3:GetObject", "env/x")]
    who = ["u0", "u1", "u2", f"r{depth - 3}", "r40000", "r12345"]
    requests = []
    for _ in range(case["requests"]):
        action, resource = r.pick(pairs)
        requests.append(Q(r.pick(who), action, resource))
    return [principals, policies, requests]


def stress_graph(case):
    """Dense clusters of roles (every role inherits many roles of its own cluster, and a few inherit shared "core"
    roles), so each user's identity set is a few hundred roles reached through thousands of edges."""
    r = SplitMix(case["seed"])
    n_clusters, size, degree, n_users = case["clusters"], case["cluster_size"], case["degree"], case["users"]
    principals = {}
    for i in range(20):
        inherits = [f"core{r.below(20)}" for _ in range(3)]
        tags = {"team": r.pick(["core", "ops"])} if i % 4 == 0 else {}
        principals[f"core{i}"] = R(inherits, tags=tags)
    for c in range(n_clusters):
        for i in range(size):
            inherits = [f"c{c}-{r.below(size)}" for _ in range(degree)]
            if i % 25 == 0:
                inherits.append(f"core{r.below(20)}")
            if r.chance(1, 40):
                inherits.append(r.pick(["nobody", f"user{r.below(n_users)}"]))
            tags = {}
            if r.chance(1, 30):
                tags["team"] = r.pick(["data", "web", "ops"])
            if r.chance(1, 60):
                tags["env"] = r.pick(["prod", "dev"])
            boundary = r.pick(["B1", "B2"]) if c % 5 == 0 and i == 7 else None
            principals[f"c{c}-{i}"] = R(inherits, boundary=boundary, tags=tags)
    for i in range(n_users):
        tags = {"team": "solo"} if i % 7 == 0 else {}
        inherits = [f"c{r.below(n_clusters)}-{r.below(size)}"]
        if i % 3 == 0:
            inherits.append(f"c{r.below(n_clusters)}-{r.below(size)}")
        principals[f"user{i}"] = U(inherits, tags=tags)
    acts = ["s3:Get*", "s3:Put*", "s3:*", "ec2:*", "iam:*", "*", "sqs:Send*", "kms:*"]
    policies = []
    for j in range(60):
        kind = j % 6
        if kind == 0:
            pats = ["*"]
        elif kind in (1, 2):
            pats = [f"core{r.below(20)}"]
        elif kind == 3:
            pats = [f"user{r.below(n_users)}", f"user{r.below(n_users)}"]
        else:
            pats = [f"c{r.below(n_clusters)}-{r.below(size)}" for _ in range(1 + r.below(3))]
        deny = j % 7 == 6
        st = S(f"p{j:02d}", "Deny" if deny else "Allow", pats, [r.pick(["iam:*", "kms:*", "s3:Put*"] if deny else acts)],
               [r.pick(["*", "arn:s3:${tag:team}/*", "home/${principal}/*", "arn:*:data/*", "arn:s3:core/*"])])
        if deny or kind == 0 or j % 4 == 1:
            st["conditions"] = dict(r.pick(GOOD_CONDS))
        policies.append(st)
    policies.append(B("bb1", "B1", "Allow", ["s3:*", "sqs:*"], ["*"]))
    policies.append(B("bb2", "B2", "Allow", ["*"], ["arn:*"]))
    policies.append(B("bb2d", "B2", "Deny", ["iam:*"], ["*"]))
    actions = ["s3:GetObject", "s3:PutObject", "ec2:Run", "iam:CreateUser", "sqs:SendMessage", "kms:Decrypt"]
    resources = ["arn:s3:core/k", "arn:s3:ops/k", "arn:s3:solo/k", "arn:ec2:data/i", "home/user3/x", "local/x",
                 "arn:s3:data/k"]
    requests = []
    for k in range(case["requests"]):
        pid = f"user{r.below(n_users)}"
        requests.append(Q(pid, r.pick(actions), r.pick(resources), random_context(r)))
    return [principals, policies, requests]


def stress_args(case):
    if case["id"] == "S1":
        return stress_glob(case)
    if case["id"] == "S2":
        return stress_chain(case)
    return stress_graph(case)
