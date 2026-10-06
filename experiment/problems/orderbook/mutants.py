"""Plausible misreadings of SPEC.md, planted in reference.py. The screening cases must catch every one."""
MUTANTS = {
    "M01 iceberg refresh keeps time priority": [
        ("                    o.token = self._token()                 # back of the level\n"
         "                    self.levels[opp][o.price].append((o.token, o))\n", "")],
    "M02 no self-trade prevention": [("            if o.owner == owner:\n", "            if False:\n")],
    "M03 FOK ignores hidden quantity": [("total += o.vis + o.hid", "total += o.vis")],
    "M04 FOK counts own orders": [("if o.alive and o.token == tok and o.owner != owner:",
                                   "if o.alive and o.token == tok:")],
    "M05 trade at the incoming limit price": [
        ('"seq": len(self.trades) + 1, "price": o.price,',
         '"seq": len(self.trades) + 1, "price": limit if limit is not None else o.price,')],
    "M06 amend down loses priority": [("            if price == o.price and qty < rem:\n",
                                       "            if False:\n")],
    "M07 amend down takes visible first": [
        ("                d = min(o.hid, cut)\n                o.hid -= d\n                o.vis -= cut - d\n",
         "                d = min(o.vis - 1, cut)\n                o.vis -= d\n                o.hid -= cut - d\n")],
    "M08 stops trigger on strict inequality": [
        ('(self.last >= s.trigger if s.side == "B" else self.last <= s.trigger)',
         '(self.last > s.trigger if s.side == "B" else self.last < s.trigger)')],
    "M09 market with no fill is not rejected": [("        if traded == 0:\n", "        if False:\n")],
    "M10 str.isdigit accepts non-ASCII digits": [("    if not _NUM.fullmatch(s):\n", "    if not s.isdigit():\n")],
    "M11 incoming iceberg matches only its display": [
        ("        rem, _ = self._match(owner, oid, side, price, qty)\n",
         "        rem, _ = self._match(owner, oid, side, price, display if flag == \"ICE\" else qty)\n")],
    "M12 IOC remainder rests": [('        if rem > 0 and flag not in ("IOC", "FOK"):\n',
                                '        if rem > 0 and flag != "FOK":\n')],
    "M13 IDs reusable once the order is gone": [("            if oid in self.consumed:\n",
                                                 "            if oid in self.orders or oid in self.stops:\n")],
    "M14 stops picked by trigger price, not line": [
        ("                heapq.heappush(self.ready, (line, s))\n            while ps",
         "                heapq.heappush(self.ready, (s.trigger * 1000000 + line, s))\n            while ps")],
}
