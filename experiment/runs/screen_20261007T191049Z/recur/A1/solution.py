import datetime

WEEKDAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def is_leap_year(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def days_in_month(y, m):
    if m in (1, 3, 5, 7, 8, 10, 12):
        return 31
    if m in (4, 6, 9, 11):
        return 30
    return 29 if is_leap_year(y) else 28


def parse_datetime(s):
    if not isinstance(s, str) or len(s) != 16:
        return None
    if s[4] != "-" or s[7] != "-" or s[10] != "T" or s[13] != ":":
        return None
    for part in (s[0:4], s[5:7], s[8:10], s[11:13], s[14:16]):
        if not (part.isdigit() and all("0" <= c <= "9" for c in part)):
            return None
    y = int(s[0:4])
    m = int(s[5:7])
    d = int(s[8:10])
    h = int(s[11:13])
    minute = int(s[14:16])
    if y < 1 or y > 9999 or m < 1 or m > 12:
        return None
    if d < 1 or d > days_in_month(y, m):
        return None
    if h < 0 or h > 23 or minute < 0 or minute > 59:
        return None
    return y, m, d, h, minute


def parse_unsigned_int(s, min_val, max_val):
    if not s or not all("0" <= c <= "9" for c in s):
        return None
    if s[0] == "0":
        return None
    val = int(s)
    if min_val <= val <= max_val:
        return val
    return None


def parse_signed_int(s, min_val, max_val):
    if not s:
        return None
    if s[0] in ("+", "-"):
        sign = -1 if s[0] == "-" else 1
        num_str = s[1:]
    else:
        sign = 1
        num_str = s
    if not num_str or not all("0" <= c <= "9" for c in num_str):
        return None
    if num_str[0] == "0":
        return None
    val = sign * int(num_str)
    if min_val <= val <= max_val:
        return val
    return None


def parse_rule(rule_str):
    if not isinstance(rule_str, str) or rule_str == "":
        return None
    if rule_str.startswith(";") or rule_str.endswith(";"):
        return None

    raw_parts = rule_str.split(";")
    allowed_names = {
        "FREQ",
        "INTERVAL",
        "COUNT",
        "UNTIL",
        "WKST",
        "BYMONTH",
        "BYMONTHDAY",
        "BYDAY",
        "BYSETPOS",
    }
    seen_names = set()
    parts_dict = {}

    for p in raw_parts:
        if p.count("=") != 1:
            return None
        name, val = p.split("=")
        if name not in allowed_names or name in seen_names:
            return None
        seen_names.add(name)
        parts_dict[name] = val

    if "FREQ" not in seen_names:
        return None
    if "COUNT" in seen_names and "UNTIL" in seen_names:
        return None

    freq = parts_dict["FREQ"]
    if freq not in ("DAILY", "WEEKLY", "MONTHLY", "YEARLY"):
        return None

    interval = 1
    if "INTERVAL" in seen_names:
        interval = parse_unsigned_int(parts_dict["INTERVAL"], 1, 100000)
        if interval is None:
            return None

    count = None
    if "COUNT" in seen_names:
        count = parse_unsigned_int(parts_dict["COUNT"], 1, 1000000)
        if count is None:
            return None

    until = None
    if "UNTIL" in seen_names:
        val = parts_dict["UNTIL"]
        if parse_datetime(val) is None:
            return None
        until = val

    wkst = 0
    if "WKST" in seen_names:
        val = parts_dict["WKST"]
        if val not in WEEKDAYS:
            return None
        wkst = WEEKDAYS[val]

    bymonth = None
    if "BYMONTH" in seen_names:
        val = parts_dict["BYMONTH"]
        if not val or val.startswith(",") or val.endswith(","):
            return None
        items = val.split(",")
        bymonth = []
        for it in items:
            v = parse_unsigned_int(it, 1, 12)
            if v is None:
                return None
            bymonth.append(v)

    bymonthday = None
    if "BYMONTHDAY" in seen_names:
        if freq == "WEEKLY":
            return None
        val = parts_dict["BYMONTHDAY"]
        if not val or val.startswith(",") or val.endswith(","):
            return None
        items = val.split(",")
        bymonthday = []
        for it in items:
            v = parse_signed_int(it, -31, 31)
            if v is None or v == 0:
                return None
            bymonthday.append(v)

    byday = None
    if "BYDAY" in seen_names:
        val = parts_dict["BYDAY"]
        if not val or val.startswith(",") or val.endswith(","):
            return None
        items = val.split(",")
        byday = []
        for it in items:
            if len(it) < 2:
                return None
            code = it[-2:]
            if code not in WEEKDAYS:
                return None
            prefix = it[:-2]
            if prefix == "":
                ord_val = None
            else:
                ord_val = parse_signed_int(prefix, -53, 53)
                if ord_val is None or ord_val == 0:
                    return None
            if ord_val is not None and freq in ("DAILY", "WEEKLY"):
                return None
            byday.append((ord_val, WEEKDAYS[code]))

    bysetpos = None
    if "BYSETPOS" in seen_names:
        if (
            "BYMONTH" not in seen_names
            and "BYMONTHDAY" not in seen_names
            and "BYDAY" not in seen_names
        ):
            return None
        val = parts_dict["BYSETPOS"]
        if not val or val.startswith(",") or val.endswith(","):
            return None
        items = val.split(",")
        bysetpos = []
        for it in items:
            v = parse_signed_int(it, -366, 366)
            if v is None or v == 0:
                return None
            bysetpos.append(v)

    return {
        "freq": freq,
        "interval": interval,
        "count": count,
        "until": until,
        "wkst": wkst,
        "bymonth": bymonth,
        "bymonthday": bymonthday,
        "byday": byday,
        "bysetpos": bysetpos,
    }


def filter_bysetpos(candidates, bysetpos):
    if bysetpos is None or not candidates:
        return candidates
    l_cand = len(candidates)
    kept_indices = set()
    for p in bysetpos:
        if 1 <= p <= l_cand:
            kept_indices.add(p - 1)
        elif 1 <= -p <= l_cand:
            kept_indices.add(l_cand + p)
    return [candidates[i] for i in sorted(kept_indices)]


def occurrences(event, range_start, range_end):
    if not isinstance(event, dict):
        return {"ok": False, "error": "bad_datetime"}

    for key in ("start", "exdates", "rdates"):
        if key not in event:
            return {"ok": False, "error": "bad_datetime"}

    start_str = event["start"]
    if parse_datetime(start_str) is None:
        return {"ok": False, "error": "bad_datetime"}
    if parse_datetime(range_start) is None:
        return {"ok": False, "error": "bad_datetime"}
    if parse_datetime(range_end) is None:
        return {"ok": False, "error": "bad_datetime"}

    exdates_list = event["exdates"]
    if not isinstance(exdates_list, list):
        return {"ok": False, "error": "bad_datetime"}
    for item in exdates_list:
        if parse_datetime(item) is None:
            return {"ok": False, "error": "bad_datetime"}

    rdates_list = event["rdates"]
    if not isinstance(rdates_list, list):
        return {"ok": False, "error": "bad_datetime"}
    for item in rdates_list:
        if parse_datetime(item) is None:
            return {"ok": False, "error": "bad_datetime"}

    rule_str = event.get("rule")
    rule = None
    if rule_str is not None:
        rule = parse_rule(rule_str)
        if rule is None:
            return {"ok": False, "error": "bad_rule"}

    if range_end <= range_start:
        return {"ok": True, "occurrences": []}

    exdates_set = set(exdates_list)
    results = set()

    if range_start <= start_str < range_end and start_str not in exdates_set:
        results.add(start_str)

    if rule is None:
        for rd in rdates_list:
            if range_start <= rd < range_end and rd not in exdates_set:
                results.add(rd)
        return {"ok": True, "occurrences": sorted(results)}

    freq = rule["freq"]
    interval = rule["interval"]
    count = rule["count"]
    until_str = rule["until"]
    wkst = rule["wkst"]
    bymonth = rule["bymonth"]
    bymonthday = rule["bymonthday"]
    byday = rule["byday"]
    bysetpos = rule["bysetpos"]

    start_y, start_m, start_d, _, _ = parse_datetime(start_str)
    start_date = datetime.date(start_y, start_m, start_d)
    start_time_str = start_str[10:]

    has_bymonth = bymonth is not None
    has_bymonthday = bymonthday is not None
    has_byday = byday is not None

    if freq == "WEEKLY" and not has_byday:
        byday = [(None, start_date.weekday())]
    elif freq == "MONTHLY" and not has_bymonthday and not has_byday:
        bymonthday = [start_date.day]
    elif freq == "YEARLY" and not has_bymonthday and not has_byday:
        bymonthday = [start_date.day]
        if not has_bymonth:
            bymonth = [start_date.month]

    bymonth_set = set(bymonth) if bymonth is not None else None
    if bymonthday is not None:
        bymonthday_pos = {v for v in bymonthday if v > 0}
        bymonthday_neg = {v for v in bymonthday if v < 0}
    else:
        bymonthday_pos = bymonthday_neg = None

    if byday is not None:
        byday_weekdays = {wd for _, wd in byday}
    else:
        byday_weekdays = None

    until_date = None
    if until_str is not None:
        u_y, u_m, u_d, _, _ = parse_datetime(until_str)
        until_date = datetime.date(u_y, u_m, u_d)

    range_end_y, range_end_m, range_end_d, _, _ = parse_datetime(range_end)
    range_end_date = datetime.date(range_end_y, range_end_m, range_end_d)

    range_start_y, range_start_m, range_start_d, _, _ = parse_datetime(range_start)
    range_start_date = datetime.date(range_start_y, range_start_m, range_start_d)

    offset = (start_date.weekday() - wkst) % 7
    p0_week_start = start_date - datetime.timedelta(days=offset)

    if count is not None:
        start_period_idx = 0
    else:
        if freq == "DAILY":
            diff = (range_start_date - start_date).days
            start_period_idx = max(0, (diff // interval) - 1) if diff > 0 else 0
        elif freq == "WEEKLY":
            diff = (range_start_date - p0_week_start).days
            start_period_idx = max(0, ((diff // 7) // interval) - 1) if diff > 0 else 0
        elif freq == "MONTHLY":
            m0 = start_date.year * 12 + (start_date.month - 1)
            mt = range_start_date.year * 12 + (range_start_date.month - 1)
            diff = mt - m0
            start_period_idx = max(0, (diff // interval) - 1) if diff > 0 else 0
        else:
            diff = range_start_date.year - start_date.year
            start_period_idx = max(0, (diff // interval) - 1) if diff > 0 else 0

    series_count = 1
    period_idx = start_period_idx
    min_date = datetime.date(1, 1, 1)
    max_date = datetime.date(9999, 12, 31)

    while True:
        if count is not None and series_count >= count:
            break

        k = period_idx * interval

        if freq == "DAILY":
            try:
                p_date = start_date + datetime.timedelta(days=k)
            except OverflowError:
                break
            if p_date.year > 9999:
                break
            if p_date > range_end_date and (
                until_date is None or p_date > until_date
            ):
                break
            if p_date < min_date:
                period_idx += 1
                continue

            passed = True
            if bymonth_set is not None and p_date.month not in bymonth_set:
                passed = False
            if passed and bymonthday is not None:
                dim = days_in_month(p_date.year, p_date.month)
                if (
                    p_date.day not in bymonthday_pos
                    and (p_date.day - dim - 1) not in bymonthday_neg
                ):
                    passed = False
            if passed and byday_weekdays is not None:
                if p_date.weekday() not in byday_weekdays:
                    passed = False

            candidates = [p_date] if passed else []
            candidates = filter_bysetpos(candidates, bysetpos)

        elif freq == "WEEKLY":
            try:
                p_start = p0_week_start + datetime.timedelta(days=7 * k)
            except OverflowError:
                break
            if p_start.year > 9999:
                break
            if p_start > range_end_date and (
                until_date is None or p_start > until_date
            ):
                break

            candidates = []
            sorted_wds = sorted(byday_weekdays, key=lambda w: (w - wkst) % 7)
            for w in sorted_wds:
                try:
                    d_cur = p_start + datetime.timedelta(days=(w - wkst) % 7)
                except OverflowError:
                    continue
                if d_cur < min_date or d_cur > max_date:
                    continue
                if bymonth_set is not None and d_cur.month not in bymonth_set:
                    continue
                candidates.append(d_cur)

            candidates = filter_bysetpos(candidates, bysetpos)

        elif freq == "MONTHLY":
            m_idx = (start_date.year * 12 + start_date.month - 1) + k
            year = m_idx // 12
            month = (m_idx % 12) + 1
            if year > 9999:
                break
            m_start = datetime.date(year, month, 1)
            if m_start > range_end_date and (
                until_date is None or m_start > until_date
            ):
                break
            if year < 1:
                period_idx += 1
                continue

            if bymonth_set is not None and month not in bymonth_set:
                candidates = []
            else:
                dim = days_in_month(year, month)
                if bymonthday is not None:
                    mday_days = {
                        d
                        for d in range(1, dim + 1)
                        if d in bymonthday_pos
                        or (d - dim - 1) in bymonthday_neg
                    }
                else:
                    mday_days = None

                if byday is not None:
                    byday_days = set()
                    first_wd = datetime.date(year, month, 1).weekday()
                    for ord_val, wd in byday:
                        first_d = 1 + (wd - first_wd) % 7
                        wd_days = list(range(first_d, dim + 1, 7))
                        l_wd = len(wd_days)
                        if ord_val is None:
                            byday_days.update(wd_days)
                        elif 1 <= ord_val <= l_wd:
                            byday_days.add(wd_days[ord_val - 1])
                        elif 1 <= -ord_val <= l_wd:
                            byday_days.add(wd_days[l_wd + ord_val])
                else:
                    byday_days = None

                if mday_days is not None and byday_days is not None:
                    matched = sorted(mday_days & byday_days)
                elif mday_days is not None:
                    matched = sorted(mday_days)
                elif byday_days is not None:
                    matched = sorted(byday_days)
                else:
                    matched = list(range(1, dim + 1))

                candidates = [datetime.date(year, month, d) for d in matched]
                candidates = filter_bysetpos(candidates, bysetpos)

        else:
            year = start_date.year + k
            if year > 9999:
                break
            y_start = datetime.date(year, 1, 1)
            if y_start > range_end_date and (
                until_date is None or y_start > until_date
            ):
                break
            if year < 1:
                period_idx += 1
                continue

            byday_scope_is_month = bymonth is not None
            if byday_scope_is_month:
                months_to_check = [m for m in range(1, 13) if m in bymonth_set]
                year_candidates = []
                for month in months_to_check:
                    dim = days_in_month(year, month)
                    if bymonthday is not None:
                        mday_days = {
                            d
                            for d in range(1, dim + 1)
                            if d in bymonthday_pos
                            or (d - dim - 1) in bymonthday_neg
                        }
                    else:
                        mday_days = None

                    if byday is not None:
                        byday_days = set()
                        first_wd = datetime.date(year, month, 1).weekday()
                        for ord_val, wd in byday:
                            first_d = 1 + (wd - first_wd) % 7
                            wd_days = list(range(first_d, dim + 1, 7))
                            l_wd = len(wd_days)
                            if ord_val is None:
                                byday_days.update(wd_days)
                            elif 1 <= ord_val <= l_wd:
                                byday_days.add(wd_days[ord_val - 1])
                            elif 1 <= -ord_val <= l_wd:
                                byday_days.add(wd_days[l_wd + ord_val])
                    else:
                        byday_days = None

                    if mday_days is not None and byday_days is not None:
                        matched = sorted(mday_days & byday_days)
                    elif mday_days is not None:
                        matched = sorted(mday_days)
                    elif byday_days is not None:
                        matched = sorted(byday_days)
                    else:
                        matched = list(range(1, dim + 1))

                    year_candidates.extend(
                        datetime.date(year, month, d) for d in matched
                    )
                candidates = filter_bysetpos(year_candidates, bysetpos)

            else:
                if byday is not None:
                    byday_dates = set()
                    y_first_wd = datetime.date(year, 1, 1).weekday()
                    for ord_val, wd in byday:
                        first_offset = (wd - y_first_wd) % 7
                        first_wd_date = datetime.date(
                            year, 1, 1
                        ) + datetime.timedelta(days=first_offset)
                        wd_dates = []
                        curr = first_wd_date
                        while curr.year == year:
                            wd_dates.append(curr)
                            curr += datetime.timedelta(days=7)
                        l_wd = len(wd_dates)
                        if ord_val is None:
                            byday_dates.update(wd_dates)
                        elif 1 <= ord_val <= l_wd:
                            byday_dates.add(wd_dates[ord_val - 1])
                        elif 1 <= -ord_val <= l_wd:
                            byday_dates.add(wd_dates[l_wd + ord_val])

                    if bymonthday is not None:
                        matched_dates = []
                        for d_val in byday_dates:
                            dim = days_in_month(year, d_val.month)
                            if (
                                d_val.day in bymonthday_pos
                                or (d_val.day - dim - 1) in bymonthday_neg
                            ):
                                matched_dates.append(d_val)
                    else:
                        matched_dates = list(byday_dates)
                else:
                    matched_dates = []
                    for month in range(1, 13):
                        dim = days_in_month(year, month)
                        for d in range(1, dim + 1):
                            if (
                                d in bymonthday_pos
                                or (d - dim - 1) in bymonthday_neg
                            ):
                                matched_dates.append(
                                    datetime.date(year, month, d)
                                )

                candidates = sorted(matched_dates)
                candidates = filter_bysetpos(candidates, bysetpos)

        stop_loop = False
        for c_date in candidates:
            inst = f"{c_date.isoformat()}{start_time_str}"
            if inst <= start_str:
                continue
            if until_str is not None and inst > until_str:
                stop_loop = True
                break

            series_count += 1
            if range_start <= inst < range_end and inst not in exdates_set:
                results.add(inst)

            if count is not None and series_count >= count:
                stop_loop = True
                break
            if inst >= range_end:
                stop_loop = True
                break

        if stop_loop:
            break

        period_idx += 1

    for rd in rdates_list:
        if range_start <= rd < range_end and rd not in exdates_set:
            results.add(rd)

    return {"ok": True, "occurrences": sorted(results)}