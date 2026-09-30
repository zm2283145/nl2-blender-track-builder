import struct
def load_3ds(data):
    """Minimal 3DS reader -> list of objects {name, points, faces, matrix, material names per face}"""
    objs = []; mats = {}
    def rd_str(o):
        e = data.index(b"\0", o); return data[o:e].decode("latin1"), e + 1
    def walk(o, end, ctx):
        while o + 6 <= end:
            cid, ln = struct.unpack_from("<HI", data, o)
            if ln < 6: break
            c0, c1 = o + 6, o + ln
            if cid in (0x4D4D, 0x3D3D):
                walk(c0, c1, ctx)
            elif cid == 0x4000:
                nm, p = rd_str(c0)
                obj = dict(name=nm, points=[], faces=[], matrix=None, fmat=[])
                objs.append(obj); walk(p, c1, obj)
            elif cid == 0x4100:
                walk(c0, c1, ctx)
            elif cid == 0x4110:
                n = struct.unpack_from("<H", data, c0)[0]
                ctx["points"] = [struct.unpack_from("<3f", data, c0 + 2 + 12 * i) for i in range(n)]
            elif cid == 0x4120:
                n = struct.unpack_from("<H", data, c0)[0]
                ctx["faces"] = [struct.unpack_from("<3H", data, c0 + 2 + 8 * i) for i in range(n)]
                ctx["fmat"] = [None] * n
                walk(c0 + 2 + 8 * n, c1, ctx)
            elif cid == 0x4130:
                nm, p = rd_str(c0); n = struct.unpack_from("<H", data, p)[0]
                for i in range(n):
                    fi = struct.unpack_from("<H", data, p + 2 + 2 * i)[0]
                    if fi < len(ctx["fmat"]): ctx["fmat"][fi] = nm
            elif cid == 0x4160:
                ctx["matrix"] = struct.unpack_from("<12f", data, c0)
            elif cid == 0xAFFF:
                m = {}; walk(c0, c1, m)
                if "name" in m: mats[m["name"]] = m
            elif cid == 0xA000:
                ctx["name"], _ = rd_str(c0)
            elif cid == 0xA020:
                col = {}; walk(c0, c1, col); ctx["diffuse"] = col.get("rgb")
            elif cid in (0x0011,):
                ctx["rgb"] = tuple(b / 255 for b in data[c0:c0 + 3])
            elif cid in (0x0010,):
                ctx.setdefault("rgb", struct.unpack_from("<3f", data, c0))
            o = c1
    walk(0, len(data), {})
    return dict(objects=objs, materials=mats)
