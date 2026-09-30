import struct
def _vx(b, o):
    if b[o] == 0xFF:
        return struct.unpack_from(">I", b, o)[0] & 0xFFFFFF, o + 4
    return struct.unpack_from(">H", b, o)[0], o + 2
def _str(b, o):
    e = b.index(b"\0", o)
    s = b[o:e].decode("latin1")
    n = e - o + 1
    if n & 1: n += 1
    return s, o + n
def load_lwo(data):
    """Parse LWO2 -> dict(layers=[{name,pivot,points,polys:[(surf_idx,[vi..])]}], surfaces=[{name,color}], tags=[..])"""
    if data[:4] != b"FORM" or data[8:12] not in (b"LWO2", b"LWOB"):
        raise ValueError("not LWO2")
    end = 8 + struct.unpack_from(">I", data, 4)[0]
    o = 12
    tags = []; layers = []; surfs = {}
    cur = None
    while o + 8 <= end:
        cid = data[o:o+4]; sz = struct.unpack_from(">I", data, o+4)[0]; c = data[o+8:o+8+sz]
        o += 8 + sz + (sz & 1)
        if cid == b"TAGS":
            p = 0
            while p < len(c):
                s, p = _str(c, p); tags.append(s)
        elif cid == b"LAYR":
            piv = struct.unpack_from(">3f", c, 4)
            nm, _ = _str(c, 16) if len(c) > 16 else ("", 0)
            cur = dict(name=nm, pivot=piv, points=[], polys=[], ptags={})
            layers.append(cur)
        elif cid == b"PNTS":
            if cur is None:
                cur = dict(name="", pivot=(0,0,0), points=[], polys=[], ptags={}); layers.append(cur)
            cur["base"] = len(cur["points"])
            n = len(c) // 12
            cur["points"].extend(struct.unpack_from(">3f", c, i*12) for i in range(n))
        elif cid == b"POLS":
            typ = c[:4]; p = 4
            cur["ptype"] = typ
            cur["pbase"] = len(cur["polys"])
            while p < len(c):
                cnt = struct.unpack_from(">H", c, p)[0] & 0x3FF; p += 2
                vs = []
                for _ in range(cnt):
                    v, p = _vx(c, p); vs.append(v + cur.get("base", 0))
                cur["polys"].append([typ.decode(), 0, vs])
        elif cid == b"PTAG":
            typ = c[:4]; p = 4
            while p < len(c):
                pi, p = _vx(c, p); t = struct.unpack_from(">H", c, p)[0]; p += 2
                if typ == b"SURF":
                    idx = cur.get("pbase", 0) + pi
                    if idx < len(cur["polys"]): cur["polys"][idx][1] = t
        elif cid == b"SURF":
            nm, p = _str(c, 0); _, p = _str(c, p)
            col = (0.8, 0.8, 0.8)
            while p + 6 <= len(c):
                sid = c[p:p+4]; ss = struct.unpack_from(">H", c, p+4)[0]; sc = c[p+6:p+6+ss]
                if sid == b"COLR": col = struct.unpack_from(">3f", sc, 0)
                p += 6 + ss + (ss & 1)
            surfs[nm] = dict(name=nm, color=col)
    return dict(layers=layers, tags=tags, surfaces=surfs)
