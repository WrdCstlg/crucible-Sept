"""Cases for Problem 16. Stdlib only (copied into the sandbox like every cases.py).

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


def E(path, keyword, schema_path):
    return {"path": path, "keyword": keyword, "schema_path": schema_path}


def PB(keyword, schema_path):
    return {"path": None, "keyword": keyword, "schema_path": schema_path}


def case(cid, title, schema, instance, expected=None):
    c = {"id": cid, "title": title, "args": [schema, instance]}
    if expected is not None:
        c["spec_expected"] = expected
    return c


def public():
    return [
        case("P1", "object keywords, false schema for extra keys, code-point order",
             {"type": "object", "required": ["id", "name"],
              "properties": {"id": {"type": "integer", "minimum": 1}, "name": {"type": "string", "minLength": 2}},
              "additionalProperties": False},
             {"id": 0, "name": "x", "zip": 1, "Age": 3},
             [E("/Age", "false", "/additionalProperties"), E("/id", "minimum", "/properties/id/minimum"),
              E("/name", "minLength", "/properties/name/minLength"), E("/zip", "false", "/additionalProperties")]),
        case("P2", "recursion through $ref, schema_path inside the target, $ref sibling",
             {"$defs": {"node": {"type": "object",
                                 "properties": {"v": {"type": "integer"},
                                                "kids": {"items": {"$ref": "#/$defs/node"}}}}},
              "$ref": "#/$defs/node", "required": ["v"]},
             {"kids": [{"v": 1}, {"v": "2", "kids": [3]}]},
             [E("", "required", "/required"), E("/kids/1/kids/0", "type", "/$defs/node/type"),
              E("/kids/1/v", "type", "/$defs/node/properties/v/type")]),
        case("P3", "combinators report one error; if picks then",
             {"properties": {"a": {"anyOf": [{"type": "string"}, {"minimum": 10}]},
                             "b": {"oneOf": [{"type": "number"}, {"multipleOf": 2}]},
                             "c": {"not": {"enum": [None, 0]}},
                             "d": {"if": {"type": "string"}, "then": {"maxLength": 3}, "else": {"const": 5}}}},
             {"a": 3, "b": 4, "c": 0.0, "d": "long"},
             [E("/a", "anyOf", "/properties/a/anyOf"), E("/b", "oneOf", "/properties/b/oneOf"),
              E("/c", "not", "/properties/c/not"), E("/d", "maxLength", "/properties/d/then/maxLength")]),
        case("P4", "schema problems: cycle, unresolvable $ref, malformed value",
             {"$defs": {"a": {"allOf": [{"$ref": "#/$defs/b"}]},
                        "b": {"anyOf": [{"$ref": "#/$defs/a"}, {"type": "null"}]},
                        "c": {"properties": {"next": {"$ref": "#/$defs/c"}}}},
              "properties": {"x": {"$ref": "#/$defs/d"}, "y": {"minLength": -1}},
              "contains": {"$ref": "#/nowhere"}},
             1,
             [PB("$ref", "/$defs/a/allOf/0/$ref"), PB("$ref", "/$defs/b/anyOf/0/$ref"),
              PB("$ref", "/properties/x/$ref"), PB("minLength", "/properties/y/minLength")]),
    ]


def hand():
    return [
        # a: 1.0 is a whole float -> integer. b: True is not an integer. c: False is not a number. d: 1.5 no.
        # e: None matches "null". f: -0.0 is whole -> integer. g: 0 is not a bool.
        case("H01", "type names: bool is not a number, whole floats are integers",
             {"properties": {"a": {"type": "integer"}, "b": {"type": "integer"}, "c": {"type": "number"},
                             "d": {"type": "integer"}, "e": {"type": ["number", "null"]}, "f": {"type": "integer"},
                             "g": {"type": "boolean"}}},
             {"a": 1.0, "b": True, "c": False, "d": 1.5, "e": None, "f": -0.0, "g": 0},
             [E("/b", "type", "/properties/b/type"), E("/c", "type", "/properties/c/type"),
              E("/d", "type", "/properties/d/type"), E("/g", "type", "/properties/g/type")]),
        # a: True != 1. b: 1 == 1.0. c: nested 1.0/2.0 equal 1/2. d: order matters. e: empty enum never matches.
        # f: 0 != False. g: null == null. h: {"p": -0.0} equals {"p": 0}.
        case("H02", "enum and const use JSON equality",
             {"properties": {"a": {"const": 1}, "b": {"enum": [1.0, "x"]}, "c": {"const": {"k": [1, {"m": 2}]}},
                             "d": {"const": [1, 2]}, "e": {"enum": []}, "f": {"const": False},
                             "g": {"const": None}, "h": {"enum": [[True], {"p": 0}]}}},
             {"a": True, "b": 1, "c": {"k": [1.0, {"m": 2.0}]}, "d": [2, 1], "e": 0, "f": 0, "g": None,
              "h": {"p": -0.0}},
             [E("/a", "const", "/properties/a/const"), E("/d", "const", "/properties/d/const"),
              E("/e", "enum", "/properties/e/enum"), E("/f", "const", "/properties/f/const")]),
        # a: 1 vs True distinct. b: 1 == 1.0 dup. c: [1] vs [True] distinct. d: same keys, 2 == 2.0 dup.
        # e: all distinct. f: 0 == -0.0 dup. g: uniqueItems false. h: a string is not an array.
        case("H03", "uniqueItems uses JSON equality",
             {"properties": {"a": {"uniqueItems": True}, "b": {"uniqueItems": True}, "c": {"uniqueItems": True},
                             "d": {"uniqueItems": True}, "e": {"uniqueItems": True}, "f": {"uniqueItems": True},
                             "g": {"uniqueItems": False}, "h": {"uniqueItems": True}}},
             {"a": [1, True], "b": [1, 1.0], "c": [[1], [True]], "d": [{"a": 1, "b": 2}, {"b": 2.0, "a": 1}],
              "e": [0, False, None, "", [], {}], "f": [0, -0.0], "g": [1, 1], "h": "aa"},
             [E("/b", "uniqueItems", "/properties/b/uniqueItems"), E("/d", "uniqueItems", "/properties/d/uniqueItems"),
              E("/f", "uniqueItems", "/properties/f/uniqueItems")]),
        # a: 0.3/0.1 = 3. b: 0.35/0.1 = 3.5. c: 1.15/0.01 = 115. d: 9.0/3 = 3. e: True is not a number.
        # f: 0.00123/0.00001 = 123. g: 7.5/2.5 = 3. h: 6/2.5 = 2.4. i: 10/0.1 = 100.
        case("H04", "multipleOf is exact on the decimal that repr prints",
             {"properties": {"a": {"multipleOf": 0.1}, "b": {"multipleOf": 0.1}, "c": {"multipleOf": 0.01},
                             "d": {"multipleOf": 3}, "e": {"multipleOf": 3}, "f": {"multipleOf": 1e-05},
                             "g": {"multipleOf": 2.5}, "h": {"multipleOf": 2.5}, "i": {"multipleOf": 0.1}}},
             {"a": 0.3, "b": 0.35, "c": 1.15, "d": 9.0, "e": True, "f": 0.00123, "g": 7.5, "h": 6, "i": 10},
             [E("/b", "multipleOf", "/properties/b/multipleOf"), E("/h", "multipleOf", "/properties/h/multipleOf")]),
        # a: 5 >= 5 ok. b: 5.0 <= 5 fails. c: 5.5 <= 5.5 ok. d: 5.5 >= 5.5 fails. e: 10**20+1 > 1e20 exactly.
        # f: False is not a number. g: -0.0 >= 0 fails. h: a string is not a number.
        case("H05", "bounds: inclusive vs exclusive, exact big numbers, bools skipped",
             {"properties": {"a": {"minimum": 5}, "b": {"exclusiveMinimum": 5}, "c": {"maximum": 5.5},
                             "d": {"exclusiveMaximum": 5.5}, "e": {"maximum": 1e20}, "f": {"minimum": 1},
                             "g": {"exclusiveMaximum": 0}, "h": {"minimum": 0}}},
             {"a": 5, "b": 5.0, "c": 5.5, "d": 5.5, "e": 10 ** 20 + 1, "f": False, "g": -0.0, "h": "7"},
             [E("/b", "exclusiveMinimum", "/properties/b/exclusiveMinimum"),
              E("/d", "exclusiveMaximum", "/properties/d/exclusiveMaximum"), E("/e", "maximum", "/properties/e/maximum"),
              E("/g", "exclusiveMaximum", "/properties/g/exclusiveMaximum")]),
        # a: 5 code points. b: one code point. c: search finds "bb". d: "^a" fails on "ba". e: not a string.
        # f: "^$" matches "". g: length 0 < 1.
        case("H06", "string keywords: code points, unanchored pattern",
             {"properties": {"a": {"minLength": 5}, "b": {"maxLength": 1}, "c": {"pattern": "b+"},
                             "d": {"pattern": "^a"}, "e": {"maxLength": 2, "pattern": "x"}, "f": {"pattern": "^$"},
                             "g": {"minLength": 1}}},
             {"a": "h\u00e9llo", "b": "\U0001F600", "c": "abbc", "d": "ba", "e": 12345, "f": "", "g": ""},
             [E("/d", "pattern", "/properties/d/pattern"), E("/g", "minLength", "/properties/g/minLength")]),
        # x-a: matches ^x- (5 not a string). my_num_2: matches "num" (2.5 not integer). foo: additional -> false.
        # x-num: matches both; "s" is a string but not an integer.
        case("H07", "patternProperties: unanchored, several apply; additionalProperties false",
             {"properties": {"id": {"type": "integer"}},
              "patternProperties": {"^x-": {"type": "string"}, "num": {"type": "integer"}},
              "additionalProperties": False},
             {"id": 1, "x-a": 5, "my_num_2": 2.5, "foo": 1, "x-num": "s"},
             [E("/foo", "false", "/additionalProperties"), E("/my_num_2", "type", "/patternProperties/num/type"),
              E("/x-a", "type", "/patternProperties/^x-/type"), E("/x-num", "type", "/patternProperties/num/type")]),
        # Only the root dict's own properties ({"b"}) exclude keys; "a" from allOf does not.
        case("H08", "additionalProperties looks only at its own dict",
             {"allOf": [{"properties": {"a": {}}}], "properties": {"b": {}},
              "additionalProperties": {"type": "string"}},
             {"a": 1, "b": 2, "c": "ok", "d": 4},
             [E("/a", "type", "/additionalProperties/type"), E("/d", "type", "/additionalProperties/type")]),
        # 0 ok; 1 "b" not integer; 2 True ok; 3: 1 not boolean (items); 4 ok; length 5 > 4.
        case("H09", "prefixItems, items after the prefix, maxItems",
             {"prefixItems": [{"type": "string"}, {"type": "integer"}], "items": {"type": "boolean"},
              "minItems": 2, "maxItems": 4},
             ["a", "b", True, 1, False],
             [E("", "maxItems", "/maxItems"), E("/1", "type", "/prefixItems/1/type"), E("/3", "type", "/items/type")]),
        # p: only index 0 exists (prefix 0 fails), items starts at 3 (none), length 1 < 2.
        # q: no prefixItems, items applies from index 0: -1 and -2 fail.
        case("H10", "array shorter than prefixItems; items without prefix",
             {"properties": {"p": {"prefixItems": [{"type": "string"}, {"type": "string"}, False], "items": False,
                                   "minItems": 2},
                             "q": {"items": {"minimum": 0}}}},
             {"p": [1], "q": [-1, 0, -2]},
             [E("/p", "minItems", "/properties/p/minItems"), E("/p/0", "type", "/properties/p/prefixItems/0/type"),
              E("/q/0", "minimum", "/properties/q/items/minimum"), E("/q/2", "minimum", "/properties/q/items/minimum")]),
        # b and c missing -> one required error at the object. l is an array -> required does nothing.
        case("H11", "required: one error at the object; ignored for non-objects",
             {"required": ["a", "b", "c"], "properties": {"a": {"type": "string"}, "l": {"required": ["z"]}}},
             {"a": 1, "l": [1]},
             [E("", "required", "/required"), E("/a", "type", "/properties/a/type")]),
        # p: type fails -> only the type error from /properties/p, but the enum in the root's allOf is another dict.
        # q: no type -> both minLength and enum. r: type fails -> allOf and not are not evaluated.
        case("H12", "a type failure stops only the other keywords of its own dict",
             {"properties": {"p": {"type": "string", "minLength": 5, "enum": ["zz"]},
                             "q": {"minLength": 5, "enum": ["zz"]},
                             "r": {"type": "number", "allOf": [{"type": "string"}], "not": {}}},
              "allOf": [{"properties": {"p": {"enum": ["zz"]}}}]},
             {"p": 7, "q": "abc", "r": "s"},
             [E("/p", "enum", "/allOf/0/properties/p/enum"), E("/p", "type", "/properties/p/type"),
              E("/q", "enum", "/properties/q/enum"), E("/q", "minLength", "/properties/q/minLength"),
              E("/r", "type", "/properties/r/type")]),
        # a: neither branch. b: both accept 3. c: none accepts 1. d: 2.0 is an integer -> not fails.
        # e: maximum accepts -> fine. f: exactly one (-3 integer, below 0). g: not false always passes.
        case("H13", "anyOf/oneOf/not: one error, members' errors hidden",
             {"properties": {"a": {"anyOf": [{"type": "string"}, {"minimum": 10}]},
                             "b": {"oneOf": [{"type": "integer"}, {"minimum": 0}]},
                             "c": {"oneOf": [{"type": "string"}, {"type": "null"}]},
                             "d": {"not": {"type": "integer"}},
                             "e": {"anyOf": [{"type": "string"}, {"maximum": 10}]},
                             "f": {"oneOf": [{"type": "integer"}, {"minimum": 0}]},
                             "g": {"not": False}}},
             {"a": 5, "b": 3, "c": 1, "d": 2.0, "e": 5, "f": -3, "g": 1},
             [E("/a", "anyOf", "/properties/a/anyOf"), E("/b", "oneOf", "/properties/b/oneOf"),
              E("/c", "oneOf", "/properties/c/oneOf"), E("/d", "not", "/properties/d/not")]),
        # a: if fails, nothing else. b: no if -> then/else ignored. c: if fails, no else. d: if fails -> else false.
        # e: if true -> then maximum 0 fails for 1.
        case("H14", "if/then/else: if's errors hidden; then/else need if",
             {"properties": {"a": {"if": {"type": "string"}},
                             "b": {"then": {"type": "string"}, "else": {"type": "string"}},
                             "c": {"if": {"minimum": 5}, "then": {"multipleOf": 2}},
                             "d": {"if": {"minimum": 5}, "then": {"multipleOf": 2}, "else": False},
                             "e": {"if": True, "then": {"maximum": 0}, "else": False}}},
             {"a": 1, "b": 1, "c": 3, "d": 3, "e": 1},
             [E("/d", "false", "/properties/d/else"), E("/e", "maximum", "/properties/e/then/maximum")]),
        # The array itself: if accepts (nothing applies to arrays), then's required ignores arrays. Items use "#"
        # (not in place, so no cycle): 0 is a circle without r; 1 is not a circle and lacks w; 2 fine; 3 not object.
        case("H15", "if chooses per instance; recursion to the root",
             {"if": {"properties": {"kind": {"const": "circle"}}, "required": ["kind"]},
              "then": {"required": ["r"]}, "else": {"required": ["w"]}, "items": {"$ref": "#"}},
             [{"kind": "circle", "w": 1}, {"kind": "square"}, {"kind": "circle", "r": 2}, 5],
             [E("/0", "required", "/then/required"), E("/1", "required", "/else/required")]),
        # a: pos accepts 11, sibling maximum fails. b: the same error twice through allOf -> kept once.
        # c: type fails, so the $ref is not followed.
        case("H16", "$ref siblings evaluated; errors located in the target; duplicates removed",
             {"$defs": {"pos": {"type": "number", "minimum": 0}},
              "properties": {"a": {"$ref": "#/$defs/pos", "maximum": 10},
                             "b": {"allOf": [{"$ref": "#/$defs/pos"}, {"$ref": "#/$defs/pos"}]},
                             "c": {"$ref": "#/$defs/pos", "type": "string"}}},
             {"a": 11, "b": -1, "c": 4},
             [E("/a", "maximum", "/properties/a/maximum"), E("/b", "minimum", "/$defs/pos/minimum"),
              E("/c", "type", "/properties/c/type")]),
        case("H17", "root false schema", False, {"a": 1}, [E("", "false", "")]),
        # n meets false; y meets true; items does not apply to an object.
        case("H18", "boolean subschemas", {"properties": {"n": False, "y": True}, "items": False},
             {"n": None, "y": 1}, [E("/n", "false", "/properties/n")]),
        # Key "a/b" -> token a~1b; "m~n" -> m~0n; "~z" -> ~0z and matches "^~" whose $ref names key "x/y";
        # "#/$defs/t~01" names key "t~1". Paths sort a < m < q < ~.
        case("H19", "pointer escaping in paths, schema paths and $ref",
             {"properties": {"a/b": {"type": "string"}, "m~n": {"type": "string"}, "q": {"$ref": "#/$defs/t~01"}},
              "$defs": {"x/y": {"type": "integer"}, "t~1": {"minimum": 3}},
              "patternProperties": {"^~": {"$ref": "#/$defs/x~1y"}}},
             {"a/b": 1, "m~n": 2, "~z": "s", "q": 1},
             [E("/a~1b", "type", "/properties/a~1b/type"), E("/m~0n", "type", "/properties/m~0n/type"),
              E("/q", "minimum", "/$defs/t~01/minimum"), E("/~0z", "type", "/$defs/x~1y/type")]),
        # One problem per malformed keyword; contains/format ignored; const holds data, so its {"$ref": 5} is
        # never examined.
        case("H20", "malformed keyword values; unknown keys ignored",
             {"properties": {"a": {"type": "int"}, "b": {"minLength": 2.0}, "c": {"required": "a"},
                             "d": {"exclusiveMinimum": True}, "e": {"multipleOf": 0}, "f": {"allOf": []},
                             "g": {"items": [{"type": "string"}]}, "h": {"pattern": "("}, "i": {"uniqueItems": 1},
                             "j": {"contains": 5, "format": 7, "type": ["string", "string"]},
                             "k": {"maxItems": True}, "l": {"enum": "x", "const": {"$ref": 5}}}},
             "anything",
             [PB("type", "/properties/a/type"), PB("minLength", "/properties/b/minLength"),
              PB("required", "/properties/c/required"), PB("exclusiveMinimum", "/properties/d/exclusiveMinimum"),
              PB("multipleOf", "/properties/e/multipleOf"), PB("allOf", "/properties/f/allOf"),
              PB("items", "/properties/g/items"), PB("pattern", "/properties/h/pattern"),
              PB("uniqueItems", "/properties/i/uniqueItems"), PB("type", "/properties/j/type"),
              PB("maxItems", "/properties/k/maxItems"), PB("enum", "/properties/l/enum")]),
        # p1-p4 resolve ("#", a $defs entry, an allOf element, a nested items); none of them is in place.
        # p5: definitions is not a keyword. p6: a dict of schemas. p7: 01 != 0/1. p8, p9: not "#" + location.
        # q1: no location /$defs/a/b. q2: not a string. q3: "/" is no location.
        case("H21", "$ref resolution is an exact match on subschema locations",
             {"definitions": {"a": {}}, "$defs": {"a": {"items": {"type": "string"}}},
              "allOf": [{"type": ["object", "array"]}, {"minProperties": 1}],
              "properties": {"p1": {"$ref": "#"}, "p2": {"$ref": "#/$defs/a"}, "p3": {"$ref": "#/allOf/1"},
                             "p4": {"$ref": "#/$defs/a/items"}, "p5": {"$ref": "#/definitions/a"},
                             "p6": {"$ref": "#/properties"}, "p7": {"$ref": "#/allOf/01"}, "p8": {"$ref": "#a"},
                             "p9": {"$ref": "other.json#/$defs/a"}, "q1": {"$ref": "#/$defs/a/b"},
                             "q2": {"$ref": 5}, "q3": {"$ref": "#/"}}},
             {},
             [PB("$ref", "/properties/p5/$ref"), PB("$ref", "/properties/p6/$ref"), PB("$ref", "/properties/p7/$ref"),
              PB("$ref", "/properties/p8/$ref"), PB("$ref", "/properties/p9/$ref"), PB("$ref", "/properties/q1/$ref"),
              PB("$ref", "/properties/q2/$ref"), PB("$ref", "/properties/q3/$ref")]),
        # a <-> b through allOf/oneOf: both refs cyclic. c -> a: a never reaches c. d: properties is not in place.
        # e: not -> e. f: then counts without if. g/items -> g -> g/else -> h -> h/if -> g/items: all three refs
        # (g/items, g/else, h/if) are on that cycle. Root -> c: nothing reaches the root.
        case("H22", "cycles: every $ref whose target leads back to it in place",
             {"$defs": {"a": {"allOf": [{"$ref": "#/$defs/b"}]},
                        "b": {"oneOf": [{"type": "null"}, {"$ref": "#/$defs/a"}]},
                        "c": {"$ref": "#/$defs/a"},
                        "d": {"properties": {"x": {"$ref": "#/$defs/d"}}},
                        "e": {"not": {"$ref": "#/$defs/e"}},
                        "f": {"then": {"$ref": "#/$defs/f"}},
                        "g": {"items": {"$ref": "#/$defs/g"}, "else": {"$ref": "#/$defs/h"}},
                        "h": {"if": {"$ref": "#/$defs/g/items"}}},
              "$ref": "#/$defs/c"},
             None,
             [PB("$ref", "/$defs/a/allOf/0/$ref"), PB("$ref", "/$defs/b/oneOf/1/$ref"), PB("$ref", "/$defs/e/not/$ref"),
              PB("$ref", "/$defs/f/then/$ref"), PB("$ref", "/$defs/g/else/$ref"), PB("$ref", "/$defs/g/items/$ref"),
              PB("$ref", "/$defs/h/if/$ref")]),
        case("H23", "a $ref to the root, at the root, is a cycle", {"$ref": "#"}, [1, 2],
             [PB("$ref", "/$ref")]),
        # loop is never used but is still cyclic. properties is malformed (b: 3), so its $ref is not examined.
        # items' $ref resolves to nothing. contains is ignored. '$' < 'i' < 'p'.
        case("H24", "unused cycles count; malformed values hide their contents",
             {"type": "string", "$defs": {"loop": {"$ref": "#/$defs/loop"}},
              "properties": {"a": {"$ref": "#/nope"}, "b": 3}, "items": {"$ref": "#/nope"},
              "contains": {"$ref": "#/nope"}},
             "ok",
             [PB("$ref", "/$defs/loop/$ref"), PB("$ref", "/items/$ref"), PB("properties", "/properties")]),
        # Every value fails both allOf members. Paths: "" -> "/", then "/10" < "/9" < "/B" < "/a"; within a path,
        # allOf/0/type sorts before allOf/1/maximum by schema_path.
        case("H25", "sort by path in code-point order, then by schema_path",
             {"additionalProperties": {"allOf": [{"type": "string"}, {"maximum": 0}]}},
             {"B": 1, "a": 2, "10": 3, "9": 4, "": 5},
             [E(p, kw, sp) for p in ("/", "/10", "/9", "/B", "/a")
              for kw, sp in (("type", "/additionalProperties/allOf/0/type"),
                             ("maximum", "/additionalProperties/allOf/1/maximum"))]),
        case("H26", "array indices sort as strings",
             {"items": {"type": "string"}}, ["a", "a", 3, "a", "a", "a", "a", "a", "a", "a", 5, "a"],
             [E("/10", "type", "/items/type"), E("/2", "type", "/items/type")]),
        # a: 1e300 is a whole float -> integer, and equals the maximum. b: "x" matches string, length 1 < 2.
        # c: 10**300 is not exactly the float 1e300.
        case("H27", "big whole floats are integers; exact equality with big ints",
             {"properties": {"a": {"type": "integer", "maximum": 1e300},
                             "b": {"type": ["integer", "string"], "minLength": 2},
                             "c": {"enum": [1e300]}}},
             {"a": 1e300, "b": "x", "c": 10 ** 300},
             [E("/b", "minLength", "/properties/b/minLength"), E("/c", "enum", "/properties/c/enum")]),
        # "a*" matches every key (empty match), so nothing is additional. zzz: 1.5 not integer.
        # x/y1: integer ok; "x/y" matches, 3 < 5. b: integer ok.
        case("H28", "patternProperties: empty matches count; pattern keys are escaped",
             {"patternProperties": {"a*": {"type": "integer"}, "x/y": {"minimum": 5}},
              "additionalProperties": False},
             {"zzz": 1.5, "x/y1": 3, "b": 2},
             [E("/x~1y1", "minimum", "/patternProperties/x~1y/minimum"), E("/zzz", "type", "/patternProperties/a*/type")]),
    ]


# ── Generated cases ─────────────────────────────────────────────────────────
TYPES = ["null", "boolean", "object", "array", "number", "integer", "string"]
TRAPS = [0, 1, -1, 1.0, 0.0, -0.0, 2.5, 0.1, 0.3, 1.15, 7.5, 1e20, 10 ** 20 + 1, True, False, None, "", "a", "ab",
         "abc", "a/b", "m~n", "h\u00e9llo", "\U0001F600", "x-1", [], [1], [1.0], [True], [1, 1.0], [0, False],
         {}, {"a": 1}, {"a": 1.0}, {"a": True}]
KEYS = ["a", "b", "x-1", "num", "", "a/b", "m~n", "B", "10", "9", "x-num", "~t"]
PATTERNS = ["^a", "b", "^x-", "num", "^$", "a*", "~", "/", "\\d$", "^[A-Z]", "^.{2}$"]
NUMS = [0, 1, 1.0, 2.5, 10, -1, 1e20, 0.1, 3, -0.0]
MULTS = [0.1, 0.01, 2, 3, 0.5, 1e-05, 2.5, 7, 1.5, 1]
UNKNOWN = [("contains", {"type": "string"}), ("format", "email"), ("minProperties", 1), ("additionalItems", False),
           ("definitions", {"z": {"type": "null"}}), ("$id", "x")]


def rvalue(r, depth):
    if depth <= 0 or r.chance(2, 3):
        return r.pick(TRAPS)
    if r.chance(1, 2):
        return [rvalue(r, depth - 1) for _ in range(r.below(4))]
    return {r.pick(KEYS): rvalue(r, depth - 1) for _ in range(r.below(4))}


NUM_INST = [0.3, 0.35, 1.15, 10, 7.5, 6, 0.00123, 9.0, 1e300, 2.5, 5, 5.0, -0.0, True, False, 10 ** 20 + 1, 1e20,
            0.1, 3, 1, 1.0, -1]
STR_INST = ["", "a", "ab", "abc", "ba", "abbc", "x-1", "h\u00e9llo", "\U0001F600\U0001F600", "Num9", "a\n", 5]
EQ_POOL = [0, 1, 1.0, -0.0, True, False, None, 2, 2.0, "1", [1], [1.0], [True], {"a": 1}, {"a": 1.0}, {"a": True}]


def leaf(r):
    k = r.below(14)
    if k == 0:
        return r.pick([True, False, {}])
    if k == 1:
        return {"type": r.pick(TYPES)}
    if k == 2:
        return {"const": r.pick(EQ_POOL)}
    if k == 3:
        return {"enum": [r.pick(EQ_POOL), r.pick(TRAPS)]}
    if k in (4, 5):
        return {"multipleOf": r.pick(MULTS)}
    if k == 6:
        return {r.pick(["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"]): r.pick(NUMS)}
    if k == 7:
        return {"type": "integer", r.pick(["minimum", "exclusiveMaximum"]): r.pick(NUMS)}
    if k == 8:
        return {"pattern": r.pick(PATTERNS)}
    if k == 9:
        return {r.pick(["minLength", "maxLength"]): 1 + r.below(3)}
    if k == 10:
        return {"uniqueItems": True}
    if k == 11:
        return {"type": [r.pick(["number", "integer"]), r.pick(["boolean", "string", "null"])]}
    if k == 12:
        return {"type": "string", "minLength": 2, "pattern": r.pick(PATTERNS)}
    return {"not": {"type": r.pick(TYPES)}}


def rschema(r, depth, inplace, deep):
    """inplace: $ref targets allowed at this location; deep: targets allowed below a depth-consuming keyword."""
    if depth <= 0 or r.chance(1, 4):
        return leaf(r)

    def sub(kind):
        return rschema(r, depth - 1, inplace if kind == "in" else deep, deep)

    s = {}
    for _ in range(1 + r.below(4)):
        k = r.below(26)
        if k == 0:
            s["type"] = r.pick(TYPES) if r.chance(1, 2) else [r.pick(TYPES[:3]), r.pick(TYPES[3:])]
        elif k == 1:
            s["enum"] = [r.pick(TRAPS) for _ in range(1 + r.below(3))]
        elif k == 2:
            s["const"] = r.pick(TRAPS)
        elif k == 3:
            s[r.pick(["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"])] = r.pick(NUMS)
        elif k == 4:
            s["multipleOf"] = r.pick(MULTS)
        elif k == 5:
            s[r.pick(["minLength", "maxLength"])] = r.below(4)
        elif k == 6:
            s["pattern"] = r.pick(PATTERNS)
        elif k == 7:
            s[r.pick(["minItems", "maxItems"])] = r.below(4)
        elif k == 8:
            s["uniqueItems"] = r.chance(3, 4)
        elif k in (9, 10):
            s["properties"] = {r.pick(KEYS): sub("deep") for _ in range(1 + r.below(3))}
        elif k == 11:
            s["patternProperties"] = {r.pick(PATTERNS): sub("deep") for _ in range(1 + r.below(2))}
        elif k == 12:
            s["additionalProperties"] = False if r.chance(1, 2) else sub("deep")
        elif k == 13:
            s["required"] = [r.pick(KEYS) for _ in range(1 + r.below(2))]
        elif k == 14:
            s["items"] = sub("deep")
        elif k == 15:
            s["prefixItems"] = [sub("deep") for _ in range(1 + r.below(2))]
        elif k in (16, 17, 18):
            s[["allOf", "anyOf", "oneOf"][k - 16]] = [sub("in") for _ in range(2 + r.below(2))]
        elif k == 19:
            s["not"] = sub("in")
        elif k == 20:
            s["if"] = sub("in")
            if r.chance(3, 4):
                s["then"] = sub("in")
            if r.chance(3, 4):
                s["else"] = sub("in")
        elif k == 21:
            s[r.pick(["then", "else"])] = sub("in")
        elif k in (22, 23) and inplace:
            s["$ref"] = r.pick(inplace)
        elif k == 24:
            kw, v = r.pick(UNKNOWN)
            s[kw] = v
        elif k == 25 and "type" not in s:
            s["type"] = r.pick(["object", "array", "number", "string"])
    return s


def guided(r, s, depth):
    """An instance shaped by the schema, so that nested keywords actually run."""
    if type(s) is not dict or depth <= 0 or r.chance(1, 6):
        return rvalue(r, 1)
    if any(k in s for k in ("multipleOf", "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum")):
        return r.pick(NUM_INST)
    if any(k in s for k in ("pattern", "minLength", "maxLength")):
        return r.pick(STR_INST)
    if "uniqueItems" in s or "const" in s or "enum" in s:
        return [r.pick(EQ_POOL) for _ in range(2 + r.below(3))] if r.chance(2, 3) else r.pick(EQ_POOL)
    if "$ref" in s and r.chance(1, 2):
        return rvalue(r, 2)
    if "properties" in s or "patternProperties" in s or "required" in s or "additionalProperties" in s:
        out = {}
        for k, sub in s.get("properties", {}).items():
            if r.chance(3, 4):
                out[k] = guided(r, sub, depth - 1)
        for k in s.get("required", []):
            if r.chance(1, 2):
                out[k] = rvalue(r, 1)
        for _ in range(r.below(3)):
            out[r.pick(KEYS)] = rvalue(r, 1)
        return out
    if "items" in s or "prefixItems" in s:
        pre = s.get("prefixItems", [])
        return [guided(r, pre[i], depth - 1) if i < len(pre) else guided(r, s.get("items", True), depth - 1)
                for i in range(r.below(5))]
    for kw in ("allOf", "anyOf", "oneOf"):
        if kw in s:
            return guided(r, r.pick(s[kw]), depth)
    return rvalue(r, 1)


def bundle_cases():
    """Many independent property schemas side by side, so each case exercises many keywords directly."""
    out = []
    for i in range(40):
        r = SplitMix(150000 + i)
        props, inst = {}, {}
        for j in range(4 + r.below(6)):
            k = r.pick(KEYS) if r.chance(1, 4) else f"k{j}"
            s = leaf(r) if r.chance(2, 3) else rschema(r, 2, [], ["#"])
            props[k] = s
            inst[k] = guided(r, s, 2)
        root = {"properties": props}
        if r.chance(1, 2):
            root["patternProperties"] = {r.pick(PATTERNS): leaf(r) for _ in range(1 + r.below(2))}
        if r.chance(1, 2):
            root["additionalProperties"] = False if r.chance(1, 2) else leaf(r)
        if r.chance(1, 3):
            root["required"] = [r.pick(KEYS), r.pick(list(props))]
        if r.chance(1, 3):
            root["type"] = r.pick(["object", "object", "array"])
        for _ in range(r.below(4)):
            inst[r.pick(KEYS)] = r.pick(NUM_INST + STR_INST)
        out.append({"id": f"R{len(out) + 1:03d}", "title": "random property bundle", "args": [root, inst]})
    return out


def validation_cases():
    out = []
    for i in range(60):
        r = SplitMix(160000 + i)
        n_defs = r.below(4)
        names = [f"d{j}" for j in range(n_defs)]
        everything = [f"#/$defs/{n}" for n in names] + ["#"]
        defs = {}
        for j, n in enumerate(names):
            defs[n] = rschema(r, 3, [f"#/$defs/{m}" for m in names[j + 1:]], everything)
        root = rschema(r, 3, [f"#/$defs/{n}" for n in names], everything)
        if type(root) is dict and defs:
            root["$defs"] = defs
        inst = guided(r, root, 4) if r.chance(3, 4) else rvalue(r, 3)
        out.append({"id": f"R{40 + len(out) + 1:03d}", "title": "random schema and instance", "args": [root, inst]})
    return out


BAD_VALUES = [("type", "int"), ("type", []), ("type", ["string", "string"]), ("minLength", 2.0), ("minLength", -1),
              ("maxItems", True), ("required", "a"), ("required", [1]), ("exclusiveMinimum", True),
              ("minimum", "0"), ("multipleOf", 0), ("multipleOf", -2), ("allOf", []), ("anyOf", {}),
              ("items", [{}]), ("pattern", "("), ("pattern", 5), ("uniqueItems", 1), ("enum", "x"),
              ("properties", {"a": 1}), ("patternProperties", {"[": {}}), ("not", None), ("if", "x"),
              ("prefixItems", []), ("$defs", []), ("$ref", 7)]
REF_FORMS = ["#/$defs/{n}", "#/$defs/{n}", "#/$defs/{n}", "#/$defs/{n}/not", "#/$defs/{n}/allOf/0",
             "#/$defs/{n}/items", "#/definitions/{n}", "#/$defs/{n}/", "#{n}", "#/$defs/0{n}", "#"]


def problem_cases():
    """Schemas whose $ref graph may contain cycles, plus malformed values and odd pointers."""
    out = []
    for i in range(30):
        r = SplitMix(260000 + i)
        n = 2 + r.below(6)
        names = [f"d{j}" for j in range(n)] + (["a/b", "t~1"] if r.chance(1, 2) else [])
        defs = {}
        for name in names:
            d = {}
            for _ in range(1 + r.below(3)):
                tgt = r.pick(REF_FORMS).format(n=r.pick(names).replace("~", "~0").replace("/", "~1"))
                form = r.below(9)
                if form == 0:
                    d["$ref"] = tgt
                elif form == 1:
                    d["allOf"] = [{"type": "object"}, {"$ref": tgt}]
                elif form == 2:
                    d["anyOf"] = [{"$ref": tgt}]
                elif form == 3:
                    d["not"] = {"$ref": tgt}
                elif form == 4:
                    d[r.pick(["if", "then", "else"])] = {"$ref": tgt}
                elif form == 5:
                    d["properties"] = {"p": {"$ref": tgt}}
                elif form == 6:
                    d["items"] = {"$ref": tgt}
                elif form == 7:
                    d["oneOf"] = [{"type": "null"}, {"allOf": [{"$ref": tgt}]}]
                else:
                    kw, v = r.pick(BAD_VALUES) if r.chance(1, 2) else r.pick(UNKNOWN)
                    d[kw] = v
            defs[name] = d
        root = {"$defs": defs, "$ref": "#/$defs/" + r.pick(names).replace("~", "~0").replace("/", "~1")}
        if r.chance(1, 3):
            root["properties"] = {"x": {"$ref": "#"}}
        out.append({"id": f"R{100 + len(out) + 1:03d}", "title": "random $ref graph",
                    "args": [root, rvalue(r, 2)]})
    return out


def equality_cases():
    """uniqueItems / enum / const over values that Python's == or json.dumps compare differently."""
    pool = [0, 1, 1.0, -0.0, 0.0, True, False, None, 2, 2.0, "1", [1], [1.0], [True], [0], [False], {"a": 1},
            {"a": 1.0}, {"a": True}, {"b": 1, "a": 2}, {"a": 2, "b": 1.0}, [[1, 2]], [[1.0, 2.0]], [[2, 1]],
            10 ** 20, 1e20, 10 ** 20 + 1]
    out = []
    for i in range(16):
        r = SplitMix(360000 + i)
        arrays = [[r.pick(pool) for _ in range(2 + r.below(4))] for _ in range(4)]
        schema = {"properties": {"u": {"items": {"uniqueItems": True}},
                                 "e": {"items": {"enum": [r.pick(pool) for _ in range(3)]}},
                                 "c": {"items": {"const": r.pick(pool)}}}}
        out.append({"id": f"R{130 + len(out) + 1:03d}", "title": "JSON equality traps",
                    "args": [schema, {"u": arrays, "e": [r.pick(pool) for _ in range(4)],
                                      "c": [r.pick(pool) for _ in range(4)]}]})
    return out


def hidden():
    return hand() + bundle_cases() + validation_cases() + problem_cases() + equality_cases()


# ── Stress ──────────────────────────────────────────────────────────────────
def stress():
    return [{"id": "S1", "title": "instance 20 000 containers deep through a recursive $ref", "seed": 1601,
             "levels": 10000},
            {"id": "S2", "title": "uniqueItems over 50 000 mixed elements", "seed": 1602, "n": 50000},
            {"id": "S3", "title": "18 000 $defs in one long in-place chain, cycles near its end",
             "seed": 1603, "n": 18000, "segment": 18000}]


def _deep(case):
    r = SplitMix(case["seed"])
    n = case["levels"]
    schema = {"$defs": {"node": {"type": "object", "required": ["id"],
                                 "properties": {"id": {"type": "integer", "minimum": 0},
                                                "tags": {"type": "array", "uniqueItems": True, "maxItems": 3},
                                                "kids": {"type": "array", "items": {"$ref": "#/$defs/node"}}},
                                 "patternProperties": {"^x-": {"type": "string"}},
                                 "additionalProperties": False}},
              "$ref": "#/$defs/node"}
    bad = {n // 3: ("id", -1), n // 2: ("zz", 1), n - 2: ("tags", [1, 1.0]), n - 1: ("x-note", 5),
           7: ("id", 2.5)}
    child = None
    for depth in range(n - 1, -1, -1):
        obj = {"id": depth}
        if r.chance(1, 4):
            obj["tags"] = [depth, str(depth)]
        if r.chance(1, 5):
            obj["x-n"] = "s"
        if child is not None:
            obj["kids"] = [child] if r.chance(3, 4) else [child, {"id": depth}]
        if depth in bad:
            k, v = bad[depth]
            obj[k] = v
        child = obj
    return [schema, child]


def _unique(case):
    n = case["n"]

    def item(i):
        k = i % 7
        if k == 0:
            return i
        if k == 1:
            return i + 0.5
        if k == 2:
            return str(i)
        if k == 3:
            return [i, "x"]
        if k == 4:
            return {"k": i, "j": [i]}
        if k == 5:
            return float(-i)
        return [[i]]

    a = [item(i) for i in range(n)] + [True, False, None, 1, [1], [True], {"a": 1}, {"a": True}]
    b = [item(i) for i in range(3 * n // 5)] + [7.0]                      # equals 7, far earlier
    c = [item(i) for i in range(n // 5)] + [{"j": [11.0], "k": 11.0}]     # equals {"k": 11, "j": [11]}
    schema = {"type": "object", "required": ["a", "b", "c"],
              "properties": {"a": {"type": "array", "uniqueItems": True},
                             "b": {"uniqueItems": True,
                                   "items": {"type": ["number", "string", "array", "object", "boolean", "null"]}},
                             "c": {"uniqueItems": True, "maxItems": n}}}
    return [schema, {"a": a, "b": b, "c": c}]


def _graph(case):
    """Chains d0 -> d1 -> ... linked in place; the last link of each segment goes through items (not in place).
    Back links close cycles only in the last quarter of each segment, so most $refs are not cyclic yet reach
    thousands of locations in place (a reachability search per $ref is quadratic)."""
    r = SplitMix(case["seed"])
    n, seg = case["n"], case["segment"]
    defs = {}
    for i in range(n):
        nxt = f"#/$defs/d{(i + 1) % n}"
        if (i + 1) % seg == 0:
            d = {"items": {"$ref": nxt}}
        else:
            form = r.below(8)
            if form == 0:
                d = {"$ref": nxt}
            elif form == 1:
                d = {"allOf": [{"type": "object"}, {"$ref": nxt}]}
            elif form == 2:
                d = {"anyOf": [{"$ref": nxt}, {"type": "null"}]}
            elif form == 3:
                d = {"oneOf": [{"type": "string"}, {"$ref": nxt}]}
            elif form == 4:
                d = {"not": {"$ref": nxt}}
            elif form == 5:
                d = {"if": {"$ref": nxt}, "then": {"minimum": 0}}
            elif form == 6:
                d = {"then": {"$ref": nxt}}
            else:
                d = {"else": {"allOf": [{"$ref": nxt}]}}
        side = r.below(40)
        if side == 0:
            d["properties"] = {"p": {"$ref": f"#/$defs/d{r.below(n)}"}}
        elif side == 1:
            d["minLength"] = 2.0
        elif side == 2:
            d["$defs"] = {"a/b": {"$ref": f"#/$defs/d{i}/$defs/a~1b"}}
        elif side == 3:
            d["patternProperties"] = {"^q": {"$ref": f"#/$defs/d{r.below(n)}/$defs/zz"}}
        elif side in (4, 5, 6, 7) and i % seg >= 3 * seg // 4:
            back = {"$ref": f"#/$defs/d{i - 1 - r.below(1200)}"}
            kw = next(k for k in ("oneOf", "anyOf", "allOf", "not") if k not in d)
            d[kw] = back if kw == "not" else [back, True]
        defs[f"d{i}"] = d
    return [{"$defs": defs, "$ref": "#/$defs/d0"}, {"any": "thing"}]


def stress_args(case):
    return {"S1": _deep, "S2": _unique, "S3": _graph}[case["id"]](case)
