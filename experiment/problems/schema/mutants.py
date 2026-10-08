"""Planted misreadings of SPEC.md for Problem 16. Each must be caught by at least one non-public case."""

MUTANTS = {
    "M01 type checks with isinstance (True is an integer, 1.0 is not)": [
        ("        return t is int or t is float\n    return t is int or (t is float and x.is_integer())",
         "        return isinstance(x, (int, float))\n    return isinstance(x, int)"),
    ],
    "M02 Python equality: True equals 1": [
        ("    if t is bool:\n        return (1, v)", "    if t is bool:\n        return (2, v)"),
    ],
    "M03 type-strict equality: 1 differs from 1.0": [
        ("    if t is int or t is float:\n        return (2, v)",
         "    if t is int or t is float:\n        return (2, type(v).__name__, v)"),
    ],
    "M04 multipleOf by floating-point remainder": [
        ('(exact(x) / exact(s["multipleOf"])).denominator != 1', 'x % s["multipleOf"] != 0'),
    ],
    "M05 patterns anchored at the start (re.match)": [
        ('self.cache[s["pattern"]].search(x) is None', 'self.cache[s["pattern"]].match(x) is None'),
        ("if self.cache[p].search(k) is not None:", "if self.cache[p].match(k) is not None:"),
    ],
    "M06 additionalProperties ignores patternProperties matches": [
        ("                        matched = True\n                        yield (loc + \"/patternProperties/\"",
         "                        yield (loc + \"/patternProperties/\""),
    ],
    "M07 additionalProperties false is one error at the object": [
        ("                if additional and not matched:\n"
         "                    yield (loc + \"/additionalProperties\", v, (path, tok), sink)",
         "                if additional and not matched:\n"
         "                    if s[\"additionalProperties\"] is False:\n"
         "                        sink.append((path, \"additionalProperties\", loc + \"/additionalProperties\"))\n"
         "                    else:\n"
         "                        yield (loc + \"/additionalProperties\", v, (path, tok), sink)"),
    ],
    "M08 a type failure does not stop the other keywords": [
        ("                sink.append((path, \"type\", loc + \"/type\"))\n                return\n",
         "                sink.append((path, \"type\", loc + \"/type\"))\n"),
    ],
    "M09 anyOf also reports its members' errors": [
        ("            ok = False\n            for i in range(len(s[\"anyOf\"])):\n                sub = []\n"
         "                yield (loc + \"/anyOf/\" + str(i), x, path, sub)\n                if not sub:\n",
         "            ok = False\n            for i in range(len(s[\"anyOf\"])):\n                sub = []\n"
         "                yield (loc + \"/anyOf/\" + str(i), x, path, sub)\n                sink.extend(sub)\n"
         "                if not sub:\n"),
    ],
    "M10 oneOf passes when several elements accept": [
        ("            if accepted != 1:", "            if accepted == 0:"),
    ],
    "M11 errors of the if schema are reported": [
        ("            yield (loc + \"/if\", x, path, sub)\n",
         "            yield (loc + \"/if\", x, path, sub)\n            sink.extend(sub)\n"),
    ],
    "M12 $ref siblings ignored (older drafts)": [
        ("        if \"type\" in s:\n            names = s[\"type\"]",
         "        if loc in self.targets:\n            yield (self.targets[loc], x, path, sink)\n            return\n"
         "        if \"type\" in s:\n            names = s[\"type\"]"),
    ],
    "M13 duplicate errors kept": [
        ("    found = {(render(path), at, kw) for path, kw, at in sink}",
         "    found = [(render(path), at, kw) for path, kw, at in sink]"),
    ],
    "M14 pointer escaping replaces / before ~": [
        ('    return key.replace("~", "~0").replace("/", "~1")', '    return key.replace("/", "~1").replace("~", "~0")'),
    ],
    "M15 cycle search follows only $ref links": [
        ("            if kw in IN_PLACE:\n                out.extend(c for c, _ in children)\n", ""),
    ],
    "M16 then/else are in-place links only when if is present": [
        ("            if kw in IN_PLACE:\n",
         "            if kw in IN_PLACE and (kw not in (\"then\", \"else\") or \"if\" in s):\n"),
    ],
    "M17 every subschema link counts as in place (recursion is a cycle)": [
        ('IN_PLACE = frozenset(["allOf", "anyOf", "oneOf", "not", "if", "then", "else"])',
         'IN_PLACE = frozenset(["allOf", "anyOf", "oneOf", "not", "if", "then", "else", "properties", "items",\n'
         '                      "patternProperties", "additionalProperties", "prefixItems"])'),
    ],
    "M18 errors sorted by keyword before schema_path": [
        ('for p, at, kw in sorted(found)]', 'for p, at, kw in sorted(found, key=lambda e: (e[0], e[2], e[1]))]'),
    ],
    "M19 items applies from index 0 even with prefixItems": [
        ("                for i in range(n, len(x)):", "                for i in range(len(x)):"),
    ],
    "M20 whole floats accepted for count keywords": [
        ("        return type(v) is int and v >= 0",
         "        return is_number(v) and v >= 0 and v == int(v)"),
    ],
}
