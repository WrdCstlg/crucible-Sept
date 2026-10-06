"""Planted misreadings of SPEC.md for Problem 8. Each must be caught by at least one non-public case."""

MUTANTS = {
    "M01 unary minus binds looser than ^": [
        ("    def power(self):\n        return self.binary((\"^\",), self.unary)\n\n    def unary(self):\n"
         "        t = self.peek()\n        if t[0] == \"op\" and t[1] in (\"-\", \"+\"):\n            self.take()\n"
         "            return (\"neg\" if t[1] == \"-\" else \"pos\", self.unary())\n        return self.primary()",
         "    def power(self):\n        t = self.peek()\n        if t[0] == \"op\" and t[1] in (\"-\", \"+\"):\n"
         "            self.take()\n            return (\"neg\" if t[1] == \"-\" else \"pos\", self.power())\n"
         "        return self.binary((\"^\",), self.primary)\n\n    def unary(self):\n        return self.power()"),
    ],
    "M02 ^ is right-associative": [
        ("    def power(self):\n        return self.binary((\"^\",), self.unary)",
         "    def power(self):\n        base = self.unary()\n        if self.peek() == (\"op\", \"^\"):\n"
         "            self.take()\n            return (\"bin\", \"^\", base, self.power())\n        return base"),
    ],
    "M03 & binds tighter than +": [
        ("        return self.binary((\"&\",), self.additive)", "        return self.additive()"),
        ("        return self.binary((\"+\", \"-\"), self.term)",
         "        return self.binary((\"+\", \"-\"), lambda: self.binary((\"&\",), self.term))"),
    ],
    "M04 string comparison is case-sensitive": [
        ("    elif ra == 1:\n        a, b = ascii_lower(a), ascii_lower(b)", "    elif ra == 1:\n        pass"),
    ],
    "M05 cross-type comparison by converting to number": [
        ("    if ra != rb:\n        return -1 if ra < rb else 1",
         "    if ra != rb:\n        x, y = to_number(a), to_number(b)\n"
         "        if type(x) is Err or type(y) is Err:\n            return -1 if ra < rb else 1\n"
         "        return (x > y) - (x < y)"),
    ],
    "M06 operands converted before error check": [
        ("            if type(a) is Err:\n                return a\n            if type(b) is Err:\n                return b\n"
         "            if op in", "            if op in"),
    ],
    "M07 ranges skip nothing (text counts as 0)": [
        ("                    if is_range:\n                        if type(v) is float:\n                            nums.append(v)",
         "                    if is_range:\n                        x = to_number(v)\n"
         "                        nums.append(x if type(x) is float else 0.0)"),
    ],
    "M08 dynamic cycle detection only": [
        ("    for key in cycle_nodes(keys, edges):", "    for key in cycle_nodes(keys, {}):"),
    ],
    "M09 ROUND uses banker's rounding": [
        ("    return float(q)\n", "    return float(round(x, n))\n"),
    ],
    "M10 empty formula value reads as 0": [
        ("                values[node] = sheet.ev(asts[node])",
         "                v = sheet.ev(asts[node])\n                values[node] = 0.0 if v is EMPTY else v"),
    ],
    "M11 IF evaluates both branches": [
        ("            if cond:\n                return self.plain(args[1])",
         "            other = [self.plain(a) for a in args[1:]]\n"
         "            err = next((o for o in other if type(o) is Err), None)\n"
         "            if err is not None:\n                return err\n"
         "            if cond:\n                return self.plain(args[1])"),
    ],
    "M12 AND short-circuits": [
        ("                    if type(v) is Err:\n                        return v\n                    if is_range:\n"
         "                        if type(v) is bool:",
         "                    if type(v) is Err:\n                        return (False if name == \"AND\" and False in used else\n"
         "                                True if name == \"OR\" and True in used else v)\n                    if is_range:\n"
         "                        if type(v) is bool:"),
    ],
    "M13 SUM via math.fsum": [
        ("                total = 0.0\n                for x in nums:\n                    total += x",
         "                total = math.fsum(nums)"),
    ],
    "M14 ranges column-major": [
        ("    return [chr(c) + str(r) for r in range(rl, rh + 1) for c in range(ord(cl), ord(ch) + 1)]",
         "    return [chr(c) + str(r) for c in range(ord(cl), ord(ch) + 1) for r in range(rl, rh + 1)]"),
    ],
    "M15 numbers compared without rounding": [
        ("    if ra == 0:\n        a, b = round(a, 9), round(b, 9)", "    if ra == 0:\n        pass"),
    ],
    "M16 unary plus converts to number": [
        ("        if kind == \"pos\" or kind == \"paren\":\n            return self.ev(node[1])",
         "        if kind == \"paren\":\n            return self.ev(node[1])\n"
         "        if kind == \"pos\":\n            return to_number(self.ev(node[1]))"),
    ],
    "M17 single REF argument treated as an expression": [
        ("        if arg[0] == \"ref\":\n            return True, [self.cell(arg[1])]", "        if False:\n            pass"),
    ],
    "M18 number text uses repr without rounding": [
        ("def fmt(x):\n    r = round(x, 9)", "def fmt(x):\n    r = x"),
    ],
    "M19 COUNT propagates errors": [
        ("                for v in vals:\n                    t = type(v)\n",
         "                for v in vals:\n                    t = type(v)\n                    if t is Err:\n"
         "                        return v\n"),
    ],
    "M20 invalid range treated as a name (#NAME?)": [
        ("                toks.append((\"range\", (a, b)) if a and b else (\"badref\", None))",
         "                toks.append((\"range\", (a, b)) if a and b else (\"name\", None))"),
    ],
    "M21 recursive evaluation (recursion limit on long chains)": [
        ("    def cell(self, key):\n        return self.values.get(key, EMPTY)",
         "    def cell(self, key):\n        if key in self.pending:\n            node = self.pending.pop(key)\n"
         "            self.values[key] = self.ev(node)\n        return self.values.get(key, EMPTY)"),
        ("    sheet = Sheet(values)\n", "    sheet = Sheet(values)\n    sheet.pending = dict(asts)\n"
         "    for key in list(asts):\n        sheet.cell(key)\n    asts = {}\n"),
    ],
}
