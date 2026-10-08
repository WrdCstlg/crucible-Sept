def _split_lines(s):
    if not s:
        return []
    parts = s.split("\n")
    last = parts.pop()
    lines = [p + "\n" for p in parts]
    if last:
        lines.append(last)
    return lines


def _diff(a, b):
    """Return list m of length len(a): m[x] = matched index in b, or -1."""
    N = len(a)
    M = len(b)
    maxd = N + M
    off = maxd + 1
    V = [0] * (2 * maxd + 3)
    trace = []
    D = 0
    found = False
    for d in range(maxd + 1):
        for k in range(-d, d + 1, 2):
            i = off + k
            if k == -d:
                x = V[i + 1]
            elif k == d:
                x = V[i - 1] + 1
            else:
                xd = V[i + 1]
                xr = V[i - 1] + 1
                x = xd if xd >= xr else xr
            y = x - k
            if x < N and y < M and a[x] == b[y]:
                x += 1
                y += 1
                L = 1
                while True:
                    r = N - x
                    r2 = M - y
                    if r2 < r:
                        r = r2
                    if r <= 0:
                        break
                    if L > r:
                        L = r
                    if a[x:x + L] == b[y:y + L]:
                        x += L
                        y += L
                        L <<= 1
                    elif L == 1:
                        break
                    else:
                        L >>= 1
            V[i] = x
            if x == N and y == M:
                found = True
                break
        if found:
            D = d
            break
        trace.append(V[off - d: off + d + 1: 2])

    mapping = [-1] * N
    x = N
    k = N - M
    for d in range(D, 0, -1):
        prev = trace[d - 1]
        pd = d - 1
        if k == -d:
            down = True
        elif k == d:
            down = False
        else:
            down = prev[(k + 1 + pd) >> 1] >= prev[(k - 1 + pd) >> 1] + 1
        if down:
            pk = k + 1
            px = prev[(pk + pd) >> 1]
            xs = px
        else:
            pk = k - 1
            px = prev[(pk + pd) >> 1]
            xs = px + 1
        while x > xs:
            x -= 1
            mapping[x] = x - k
        x = px
        k = pk
    # step 0: diagonal 0 snake from (0, 0)
    while x > 0:
        x -= 1
        mapping[x] = x
    return mapping


def merge(base, ours, theirs):
    bl = _split_lines(base)
    ol = _split_lines(ours)
    tl = _split_lines(theirs)

    ids = {}

    def enc(lines):
        get = ids.setdefault
        return [get(l, len(ids)) for l in lines]

    bi = enc(bl)
    oi = enc(ol)
    ti = enc(tl)

    mo = _diff(bi, oi)
    mt = _diff(bi, ti)

    N = len(bl)
    nO = len(ol)
    nT = len(tl)

    out = []
    conflicts = 0

    def add_part(part):
        out.extend(part)
        if part and not part[-1].endswith("\n"):
            out.append("\n")

    ps = po = pt = -1
    for s in range(N + 1):
        if s < N:
            o = mo[s]
            t = mt[s]
            if o < 0 or t < 0:
                continue
        else:
            o = nO
            t = nT
        if not (s == ps + 1 and o == po + 1 and t == pt + 1):
            bpart = bl[ps + 1:s]
            opart = ol[po + 1:o]
            tpart = tl[pt + 1:t]
            bid = bi[ps + 1:s]
            oid = oi[po + 1:o]
            tid = ti[pt + 1:t]
            if oid == bid:
                out.extend(tpart)
            elif tid == bid:
                out.extend(opart)
            elif oid == tid:
                out.extend(opart)
            else:
                conflicts += 1
                out.append("<<<<<<< ours\n")
                add_part(opart)
                out.append("||||||| base\n")
                add_part(bpart)
                out.append("=======\n")
                add_part(tpart)
                out.append(">>>>>>> theirs\n")
        if s < N:
            out.append(bl[s])
        ps, po, pt = s, o, t

    text = "".join(out)
    return {"text": text, "conflicts": conflicts, "clean": conflicts == 0}