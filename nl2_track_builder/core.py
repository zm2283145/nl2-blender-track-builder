"""Pure-numpy geometry for the NL2 Track Builder (no bpy imports, so it can be tested outside Blender).

Coordinates: NL2 is Y-up; everything is converted to Blender Z-up with (x, y, z) -> (x, -z, y)
right after loading. Local track frame: x = LEFT, y = UP, z = FORWARD.
"""
import csv
import gzip
import json
import math
import os
import xml.etree.ElementTree as ET

import numpy as np

from . import styles as _styles

HERE = os.path.dirname(os.path.abspath(__file__))
_ASSETS = None


def nl2_to_blender(a):
    a = np.asarray(a, dtype=float)
    return np.stack([a[..., 0], -a[..., 2], a[..., 1]], axis=-1)


# ----------------------------------------------------------------------------------------- assets
class Asset:
    __slots__ = ("V", "idx", "counts", "slot", "slots", "bolts", "nuts", "name")

    def __init__(self, name, d):
        self.name = name
        self.V = np.asarray(d["v"], dtype=float).reshape(-1, 3)
        self.counts = np.asarray(d["c"], dtype=np.int64)
        self.idx = np.asarray(d["i"], dtype=np.int64)
        self.slot = np.asarray(d["s"], dtype=np.int64)
        self.slots = list(d.get("slots", ["steel"]))
        self.bolts = np.asarray(d.get("bolts", []), dtype=float).reshape(-1, 7)
        self.nuts = np.asarray(d.get("nuts", []), dtype=float).reshape(-1, 7)

    def copy(self):
        a = Asset.__new__(Asset)
        for k in Asset.__slots__:
            v = getattr(self, k)
            setattr(a, k, v.copy() if isinstance(v, np.ndarray) else (list(v) if isinstance(v, list) else v))
        return a


PACK = os.path.join(HERE, "assets", "nl2_assets.json.gz")
_PROC = {}


def pack_available():
    return os.path.isfile(PACK)


def assets():
    """The game asset pack (personal use only), built from the user's own NoLimits 2 install."""
    global _ASSETS
    if _ASSETS is None:
        if not os.path.isfile(PACK):
            raise RuntimeError("NL2 asset pack not found (%s). Turn on 'Procedural Parts' or build the pack from "
                               "your own NoLimits 2 install with build_assets.py - see the README." % PACK)
        with gzip.open(PACK, "rt", encoding="utf-8") as fh:
            raw = json.load(fh)
        _ASSETS = {g: {k: Asset(k, v) for k, v in grp.items()} for g, grp in raw.items()}
    return _ASSETS


def get_assets(style, option, params):
    """Game asset pack, or (params['procedural']) original generated parts for this style / option."""
    if not params.get("procedural"):
        return assets()
    from . import procedural
    gauge = params.get("gauge") or style["gauge"]
    rail_r = params.get("rail_r") or style["rail_r"]
    attach = params.get("attach") or option.get("attach") or -0.7
    key = (style["key"], repr(option["parts"]), gauge, rail_r, attach)
    if key not in _PROC:
        raw = procedural.pack(style, option, gauge, rail_r, attach)
        _PROC.clear()
        _PROC[key] = {g: {k: Asset("proc_" + k, v) for k, v in grp.items()} for g, grp in raw.items()}
    return _PROC[key]


# ------------------------------------------------------------------------------------ mesh builder
class MeshBuilder:
    """Accumulates polygons with a material name and smooth flag per face."""

    def __init__(self):
        self.V, self.idx, self.counts, self.mat, self.smooth = [], [], [], [], []
        self.nv = 0

    def add(self, V, idx, counts, mat, smooth=False):
        V = np.asarray(V, dtype=float).reshape(-1, 3)
        idx = np.asarray(idx, dtype=np.int64).ravel()
        counts = np.asarray(counts, dtype=np.int64).ravel()
        if len(V) == 0 or len(counts) == 0:
            return
        nf = len(counts)
        if isinstance(mat, str):
            mat = [mat] * nf
        if isinstance(smooth, (bool, np.bool_)):
            smooth = np.full(nf, bool(smooth))
        self.V.append(V)
        self.idx.append(idx + self.nv)
        self.counts.append(counts)
        self.mat.extend(mat)
        self.smooth.append(np.asarray(smooth, dtype=bool))
        self.nv += len(V)

    def add_quads(self, V, quads, mat, smooth=False):
        quads = np.asarray(quads, dtype=np.int64).reshape(-1, 4)
        self.add(V, quads.ravel(), np.full(len(quads), 4), mat, smooth)

    def empty(self):
        return self.nv == 0

    def arrays(self):
        if self.empty():
            return None
        return (np.concatenate(self.V), np.concatenate(self.idx), np.concatenate(self.counts),
                list(self.mat), np.concatenate(self.smooth))


# --------------------------------------------------------------------------------------- the track
def _norm(v):
    n = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.maximum(n, 1e-12)


class Track:
    """Centre-of-rails spline with orthonormal frames, in Blender coordinates."""

    def __init__(self, P, F, L, U, nl2_count):
        self.P, self.F, self.L, self.U = P, F, L, U
        seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
        self.s = np.r_[0.0, np.cumsum(seg)]
        self.length = float(self.s[-1])
        self.nl2_count = nl2_count  # number of CSV rows (before any closing bridge)
        self.closed = False

    @staticmethod
    def load_csv(path):
        rows = []
        with open(path, newline="", encoding="utf-8-sig") as fh:
            sample = fh.read(4096)
            fh.seek(0)
            delim = "\t" if "\t" in sample else ("," if sample.count(",") > sample.count(";") else ";")
            for r in csv.reader(fh, delimiter=delim):
                if not r:
                    continue
                try:
                    vals = [float(x) for x in r[1:13]]
                except ValueError:
                    continue
                if len(vals) == 12:
                    rows.append(vals)
        if len(rows) < 2:
            raise ValueError("No track points found in %s" % path)
        A = np.array(rows)
        P, F, L, U = (nl2_to_blender(A[:, i:i + 3]) for i in (0, 3, 6, 9))
        F = _norm(F)
        U = _norm(U - np.sum(U * F, axis=1, keepdims=True) * F)
        L = np.cross(U, F)
        return Track(P, F, L, U, len(A))

    def gap(self):
        d = self.P[0] - self.P[-1]
        return float(np.linalg.norm(d)), d

    def should_close(self):
        g, d = self.gap()
        if g < 1e-3:
            return True
        if g > 60.0 or g > 0.1 * self.length:
            return False
        dirn = d / g
        return float(dirn @ self.F[-1]) > 0.7 and float(dirn @ self.F[0]) > 0.7

    def close(self, step=0.5):
        """Bridge the end back to the start with a Hermite curve (NL2 exports skip the last piece)."""
        g, _ = self.gap()
        if g > 1e-3:
            n = max(2, int(math.ceil(g / step)))
            t = np.linspace(0, 1, n + 1)[1:-1, None]
            p0, p1, m0, m1 = self.P[-1], self.P[0], self.F[-1] * g, self.F[0] * g
            h00, h10, h01, h11 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t, -2 * t**3 + 3 * t**2, t**3 - t**2
            Pb = h00 * p0 + h10 * m0 + h01 * p1 + h11 * m1
            dP = (6 * t**2 - 6 * t) * p0 + (3 * t**2 - 4 * t + 1) * m0 + (-6 * t**2 + 6 * t) * p1 + (3 * t**2 - 2 * t) * m1
            Fb = _norm(dP)
            Ub = _norm((1 - t) * self.U[-1] + t * self.U[0])
            Ub = _norm(Ub - np.sum(Ub * Fb, axis=1, keepdims=True) * Fb)
            Lb = np.cross(Ub, Fb)
            self.P, self.F = np.vstack([self.P, Pb]), np.vstack([self.F, Fb])
            self.U, self.L = np.vstack([self.U, Ub]), np.vstack([self.L, Lb])
        else:
            self.P, self.F, self.L, self.U = self.P[:-1], self.F[:-1], self.L[:-1], self.U[:-1]
        seg = np.linalg.norm(np.diff(np.vstack([self.P, self.P[:1]]), axis=0), axis=1)
        self.s = np.r_[0.0, np.cumsum(seg)[:-1]]
        self.length = float(np.sum(seg))
        self.closed = True

    def flip(self):
        """Inverted styles: roll the style 180 degrees about the forward axis."""
        self.L, self.U = -self.L, -self.U

    def frames_at(self, s):
        """Interpolated (P, L, U, F) at arc lengths s (array)."""
        s = np.asarray(s, dtype=float)
        if self.closed:
            s = np.mod(s, self.length)
            P = np.vstack([self.P, self.P[:1]])
            Ls, Us, Fs = (np.vstack([a, a[:1]]) for a in (self.L, self.U, self.F))
            sk = np.r_[self.s, self.length]
        else:
            s = np.clip(s, 0, self.length)
            P, Ls, Us, Fs, sk = self.P, self.L, self.U, self.F, self.s
        i = np.clip(np.searchsorted(sk, s, side="right") - 1, 0, len(sk) - 2)
        f = ((s - sk[i]) / np.maximum(sk[i + 1] - sk[i], 1e-9))[:, None]
        p = P[i] * (1 - f) + P[i + 1] * f
        F = _norm(Fs[i] * (1 - f) + Fs[i + 1] * f)
        U = Us[i] * (1 - f) + Us[i + 1] * f
        U = _norm(U - np.sum(U * F, axis=1, keepdims=True) * F)
        L = np.cross(U, F)
        return p, L, U, F

    def frames_at_nl2(self, coord):
        """Frame at an NL2 'center_rails_coord' (CSV rows are 0.5 m apart, so row = coord / 0.5)."""
        k = np.clip(np.asarray(coord, dtype=float) / 0.5, 0, self.nl2_count - 1)
        i = np.minimum(k.astype(int), self.nl2_count - 2)
        return self.frames_at(self.s[i] + (k - i) * (self.s[i + 1] - self.s[i]))


# -------------------------------------------------------------------------------------- sweeping
def sweep_profile(track, profile, mat, mb, smooth, caps=True):
    """Sweep 2-D rings (x = LEFT, y = UP) along the track.

    `profile` is a list of (ring, wrap). A wrapped ring is a closed CCW outline (tubes); an
    unwrapped 2-point ring is one flat side of a sharp-edged box."""
    P, L, U = track.P, track.L, track.U
    n = len(P)
    for ring, wrap in profile:
        ring = np.asarray(ring, dtype=float)
        k = len(ring)
        V = P[:, None, :] + ring[None, :, 0:1] * L[:, None, :] + ring[None, :, 1:2] * U[:, None, :]
        V = V.reshape(-1, 3)
        ii = np.arange(n if track.closed else n - 1)
        jn = (ii + 1) % n
        cols = np.arange(k if wrap else k - 1)
        cn = (cols + 1) % k
        a = ii[:, None] * k + cols[None, :]
        b = ii[:, None] * k + cn[None, :]
        c = jn[:, None] * k + cn[None, :]
        d = jn[:, None] * k + cols[None, :]
        quads = np.stack([a, b, c, d], axis=-1).reshape(-1, 4)
        mb.add_quads(V, quads, mat, smooth)
        if caps and wrap and not track.closed:
            for end, sign in ((0, -1), (n - 1, 1)):
                Vc = P[end] + ring[:, 0:1] * L[end] + ring[:, 1:2] * U[end]
                order = np.arange(k) if sign > 0 else np.arange(k)[::-1]
                mb.add(Vc, order, [k], mat, False)


def circle(x, y, r, sides):
    t = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    return np.c_[x + r * np.cos(t), y + r * np.sin(t)]


def box_sides(x0, x1, y0, y1):
    """Four 2-point rings, CCW (bottom, right-side(-x is right), top, left)."""
    c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    return [(np.array([c[i], c[(i + 1) % 4]]), False) for i in range(4)]


# ---------------------------------------------------------------------------------- instancing
def place(asset_V, P, L, U, F):
    """Transform local asset vertices (m, 3) by N frames -> (N, m, 3)."""
    V = asset_V
    return (P[:, None, :] + V[None, :, 0:1] * L[:, None, :] + V[None, :, 1:2] * U[:, None, :]
            + V[None, :, 2:3] * F[:, None, :])


def add_instances(mb, asset, P, L, U, F, slotmap, smooth=True):
    N = len(P)
    if N == 0 or len(asset.V) == 0:
        return
    W = place(asset.V, P, L, U, F).reshape(-1, 3)
    nv = len(asset.V)
    idx = (asset.idx[None, :] + (np.arange(N) * nv)[:, None]).ravel()
    counts = np.tile(asset.counts, N)
    mats = [slotmap.get(asset.slots[s], slotmap.get("*", "Steel")) for s in asset.slot]
    mb.add(W, idx, counts, mats * N, smooth)


def euler_xyz(M):
    """Blender XYZ Euler angles for rotation matrices M (N, 3, 3) (columns = local axes)."""
    a = np.arctan2(M[:, 2, 1], M[:, 2, 2])
    b = np.arcsin(np.clip(-M[:, 2, 0], -1, 1))
    c = np.arctan2(M[:, 1, 0], M[:, 0, 0])
    return np.c_[a, b, c]


class Instances:
    """Point cloud for Geometry-Nodes instancing: positions, rotation (Euler XYZ), uniform scale."""

    def __init__(self):
        self.pos, self.rot, self.scale = [], [], []

    def add(self, pos, M, scale=1.0):
        pos = np.asarray(pos, dtype=float).reshape(-1, 3)
        if len(pos) == 0:
            return
        self.pos.append(pos)
        self.rot.append(euler_xyz(np.asarray(M, dtype=float).reshape(-1, 3, 3)))
        self.scale.append(np.broadcast_to(np.asarray(scale, dtype=float), (len(pos),)).copy())

    def arrays(self):
        if not self.pos:
            return None
        return np.concatenate(self.pos), np.concatenate(self.rot), np.concatenate(self.scale)


def frame_matrix(L, U, F):
    return np.stack([L, U, F], axis=-1)  # columns


def axis_matrix(z):
    """Rotation matrices whose local z axis = z (N, 3)."""
    z = _norm(np.asarray(z, dtype=float).reshape(-1, 3))
    ref = np.where(np.abs(z[:, 2:3]) < 0.9, np.array([[0, 0, 1.0]]), np.array([[1.0, 0, 0]]))
    x = _norm(np.cross(ref, z))
    y = np.cross(z, x)
    return np.stack([x, y, z], axis=-1)


def marker_instances(asset_markers, P, L, U, F, inst, ref_size=0.054, xform=None):
    """Bolt/nut markers (pos, normal, size) of a placed model -> instances."""
    if len(asset_markers) == 0 or len(P) == 0:
        return
    loc = asset_markers[:, 0:3]
    nrm = asset_markers[:, 3:6]
    if xform is not None:
        loc = xform(loc)
    size = np.clip(asset_markers[:, 6] / ref_size, 0.4, 2.5)
    wp = place(loc, P, L, U, F).reshape(-1, 3)
    wn = (nrm[None, :, 0:1] * L[:, None, :] + nrm[None, :, 1:2] * U[:, None, :]
          + nrm[None, :, 2:3] * F[:, None, :]).reshape(-1, 3)
    inst.add(wp, axis_matrix(wn), np.tile(size, len(P)))


# ------------------------------------------------------------------------------ track building
def generated_tie(style, option, gauge, rail_r):
    """Original tie for styles without a game tie model (and for procedural builds)."""
    from . import procedural
    return Asset("proc_tie", procedural.tie(style, option, gauge, rail_r))


def tube_parts(style, option, gauge, rail_r):
    parts = []
    if gauge > 0 and rail_r > 0:
        parts += [("tube", gauge / 2, 0.0, rail_r, "Rails"), ("tube", -gauge / 2, 0.0, rail_r, "Rails")]
    for p in style["extra"]:
        parts.append(p + ("Rails",))
    for p in option["parts"]:
        parts.append(p + ("Spine",))
    return parts


def flange_positions(length, target, closed):
    if target <= 0 or length < target * 0.75:
        n = 1
    else:
        n = max(1, int(round(length / target)))
    seg = length / n
    b = np.arange(n + (0 if closed else 1)) * seg
    return b, seg


def build_track(track, style, option, params):
    """Returns dict(mesh=MeshBuilder, instances={name: (asset, Instances)}, info=str)."""
    A = get_assets(style, option, params)
    gauge = params.get("gauge") or style["gauge"]
    rail_r = params.get("rail_r") or style["rail_r"]
    sides = int(params.get("tube_sides", 12))
    spacing = params.get("tie_spacing") or option["spacing"]
    flange_len = params.get("flange_length") or option["flange"]
    mb = MeshBuilder()
    inst = {}

    # --- rails, extra tubes, spines
    for p in tube_parts(style, option, gauge, rail_r):
        if p[0] == "tube":
            _, x, y, r, mat = p
            nside = sides if r < 0.12 else max(sides, 20)
            sweep_profile(track, [(circle(x, y, r, nside), True)], mat, mb, True)
        elif p[0] == "box":
            _, x0, x1, y0, y1, mat = p
            mode = params.get("colour_mode", "PLAIN") if mat == "Spine" else "PLAIN"
            rings = box_sides(x0, x1, y0, y1)
            mats = [mat] * 4
            if mode in ("BOTTOM", "TOPBOTTOM"):
                mats[0] = "Spine Accent"
            if mode in ("TOP", "TOPBOTTOM"):
                mats[2] = "Spine Accent"
            if mode == "STRIPE":
                ym = (y0 + y1) / 2
                hs = (y1 - y0) * 0.15
                rings = [
                    (np.array([(x0, y0), (x1, y0)]), False),
                    (np.array([(x1, y0), (x1, ym - hs)]), False),
                    (np.array([(x1, ym - hs), (x1, ym + hs)]), False),
                    (np.array([(x1, ym + hs), (x1, y1)]), False),
                    (np.array([(x1, y1), (x0, y1)]), False),
                    (np.array([(x0, y1), (x0, ym + hs)]), False),
                    (np.array([(x0, ym + hs), (x0, ym - hs)]), False),
                    (np.array([(x0, ym - hs), (x0, y0)]), False),
                ]
                mats = [mat, mat, "Spine Accent", mat, mat, mat, "Spine Accent", mat]
            for ring, m in zip(rings, mats):
                sweep_profile(track, [ring], m, mb, False, caps=False)
            if not track.closed:
                sweep_caps_box(track, x0, x1, y0, y1, mat, mb)

    # --- ties and flange plates
    tie_map = {"tie": "Ties", "spine": "Spine", "support": "Supports", "rail": "Rails", "steel": "Steel",
               "metal": "Unpainted Metal", "concrete": "Concrete", "*": "Ties"}
    sx = option.get("tie_scale_x", 1.0)

    def get(key):
        if not key:
            return None
        a = A["ties"].get(key)
        if a is None:
            return None
        if sx != 1.0:
            a = a.copy()
            a.V[:, 0] *= sx
            if len(a.bolts):
                a.bolts[:, 0] *= sx
            if len(a.nuts):
                a.nuts[:, 0] *= sx
        return a

    mid = get(option["mid"]) or generated_tie(style, option, gauge, rail_r)
    start = get(option["start"])
    end = get(option["end"])
    if start is not None and end is None:
        end = start.copy()  # mirror the start plate onto the far side of the joint
        end.V[:, 2] *= -1
        end.V[:, 0] *= -1
        if len(end.bolts):
            end.bolts[:, [0, 2, 3, 5]] *= -1
        if len(end.nuts):
            end.nuts[:, [0, 2, 3, 5]] *= -1

    bounds, seg = flange_positions(track.length, flange_len, track.closed)
    nt = max(1, int(round(seg / spacing)))
    tie_s = (bounds[:len(bounds) - (0 if track.closed else 1)][:, None] + (np.arange(1, nt) * seg / nt)[None, :]).ravel()
    if params.get("ties", True):
        P, L, U, F = track.frames_at(tie_s)
        add_instances(mb, mid, P, L, U, F, tie_map)

    bolts = Instances()
    nuts = Instances()
    flange_sets = Instances()
    if params.get("flanges", True):
        Pb, Lb, Ub, Fb = track.frames_at(bounds)
        joint = np.ones(len(bounds), dtype=bool)
        if not track.closed:
            joint[0] = joint[-1] = False
        # start plates at every boundary except the very end, end plates at every boundary except 0
        has_start = np.ones(len(bounds), bool)
        has_end = np.ones(len(bounds), bool)
        if not track.closed:
            has_start[-1] = False
            has_end[0] = False
        if start is not None:
            k = has_start
            add_instances(mb, start, Pb[k], Lb[k], Ub[k], Fb[k], tie_map)
            marker_instances(start.bolts, Pb[k], Lb[k], Ub[k], Fb[k], bolts)
            marker_instances(start.nuts, Pb[k], Lb[k], Ub[k], Fb[k], nuts)
        if end is not None:
            k = has_end
            add_instances(mb, end, Pb[k], Lb[k], Ub[k], Fb[k], tie_map)
            marker_instances(end.bolts, Pb[k], Lb[k], Ub[k], Fb[k], bolts)
            marker_instances(end.nuts, Pb[k], Lb[k], Ub[k], Fb[k], nuts)
        if start is None and end is None:
            # rails are sleeved inside at the joints; only the spine gets a bolted flange
            spine = [p for p in tube_parts(style, option, gauge, rail_r) if p[-1] != "Rails"]
            generic_flanges(mb, spine, Pb, Lb, Ub, Fb, bolts)
        fb = option.get("flange_bolts")
        if fb and params.get("bolts", True) and "bm_flange" in A["bolts"]:
            k = joint
            flange_sets.add(Pb[k], frame_matrix(Lb[k], Ub[k], Fb[k]))
            inst["flange_bolts"] = (flange_bolt_asset(fb[1]), flange_sets)
    if params.get("bolts", True):
        inst["bolts"] = (A["bolts"]["bolt"], bolts)
        inst["nuts"] = (A["bolts"]["nut"], nuts)
    info = "%d ties, %d flanges (segment %.2f m, tie pitch %.3f m), track %.1f m%s" % (
        len(tie_s), len(bounds), seg, seg / nt, track.length, " (closed)" if track.closed else "")
    return dict(mesh=mb, instances=inst, info=info)


_FLANGE_CACHE = {}


def flange_bolt_asset(drop):
    if drop in _FLANGE_CACHE:
        return _FLANGE_CACHE[drop]
    a = assets()["bolts"]["bm_flange"].copy()
    a.name = "bm_flange_%g" % drop
    if drop:
        low = a.V[:, 1] < -0.44
        a.V[low, 1] += drop
    _FLANGE_CACHE[drop] = a
    return a


def sweep_caps_box(track, x0, x1, y0, y1, mat, mb):
    ring = np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
    for end, sign in ((0, -1), (len(track.P) - 1, 1)):
        V = track.P[end] + ring[:, 0:1] * track.L[end] + ring[:, 1:2] * track.U[end]
        order = np.arange(4) if sign > 0 else np.arange(4)[::-1]
        mb.add(V, order, [4], mat, False)


def disc(x, y, r_in, r_out, z0, z1, sides=16):
    """Annulus plate in the (x, y) plane between z0 and z1 -> (V, idx, counts)."""
    t = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    c, s = np.cos(t), np.sin(t)
    rings = []
    for z in (z0, z1):
        rings.append(np.c_[x + r_out * c, y + r_out * s, np.full(sides, z)])
        rings.append(np.c_[x + r_in * c, y + r_in * s, np.full(sides, z)])
    V = np.vstack(rings)  # 0 outer z0, 1 inner z0, 2 outer z1, 3 inner z1
    i = np.arange(sides)
    j = (i + 1) % sides
    o0, n0, o1, n1 = 0, sides, 2 * sides, 3 * sides
    quads = np.concatenate([
        np.c_[o0 + i, o0 + j, o1 + j, o1 + i],      # outer wall
        np.c_[n0 + j, n0 + i, n1 + i, n1 + j],      # inner wall
        np.c_[o1 + i, o1 + j, n1 + j, n1 + i],      # front face (+z)
        np.c_[o0 + j, o0 + i, n0 + i, n0 + j],      # back face (-z)
    ])
    return V, quads.ravel(), np.full(len(quads), 4)


def generic_flanges(mb, parts, P, L, U, F, bolts):
    """Flange rings + bolt circles for styles without flange plate models."""
    for p in parts:
        if p[0] == "tube":
            _, x, y, r, mat = p
            V, idx, cnt = disc(x, y, r * 0.98, r * 1.9, -0.02, 0.02, 16)
            nb = 6
            ang = np.linspace(0, 2 * np.pi, nb, endpoint=False) + np.pi / nb
            loc = np.c_[x + 1.5 * r * np.cos(ang), y + 1.5 * r * np.sin(ang), np.full(nb, 0.02)]
            size = max(0.4, min(1.2, r / 0.08))
        elif p[0] == "box":
            _, x0, x1, y0, y1, mat = p
            m = 0.05
            V = np.array([[x0 - m, y0 - m, -0.02], [x1 + m, y0 - m, -0.02], [x1 + m, y1 + m, -0.02], [x0 - m, y1 + m, -0.02],
                          [x0 - m, y0 - m, 0.02], [x1 + m, y0 - m, 0.02], [x1 + m, y1 + m, 0.02], [x0 - m, y1 + m, 0.02]])
            idx = np.array([4, 5, 6, 7, 3, 2, 1, 0, 0, 1, 5, 4, 1, 2, 6, 5, 2, 3, 7, 6, 3, 0, 4, 7])
            cnt = np.full(6, 4)
            xs = np.linspace(x0, x1, 4)
            ys = np.linspace(y0, y1, 4)
            loc = np.array([(xx, y1 + m * 0.5, 0.02) for xx in xs] + [(xx, y0 - m * 0.5, 0.02) for xx in xs]
                           + [(x0 - m * 0.5, yy, 0.02) for yy in ys[1:-1]] + [(x1 + m * 0.5, yy, 0.02) for yy in ys[1:-1]])
            size = 1.0
        else:
            continue
        a = Asset.__new__(Asset)
        a.V, a.idx, a.counts = V, np.asarray(idx), np.asarray(cnt)
        a.slot = np.zeros(len(cnt), dtype=np.int64)
        a.slots = [mat]
        add_instances(mb, a, P, L, U, F, {mat: mat}, smooth=False)
        W = place(loc, P, L, U, F).reshape(-1, 3)
        bolts.add(W, np.repeat(frame_matrix(L, U, F), len(loc), axis=0), size)


# ------------------------------------------------------------------------------------- supports
def _vec(el):
    return np.array([float(v) for v in el.text.split()])


class Supports:
    def __init__(self, path):
        root = ET.parse(path).getroot()
        self.footers, self.free, self.rascs, self.beams = {}, {}, [], []
        self.subnodes = {}
        self.beamnodes = {}
        for el in root.iter():
            tag = el.tag
            if tag == "footernode":
                rot = el.find("rotation")
                hat = el.find("height_above_terrain")
                self.footers[el.get("id")] = dict(
                    pos=nl2_to_blender(_vec(el.find("pos"))),
                    rot=float(rot.text) if rot is not None else 0.0,
                    hat=float(hat.text) if hat is not None else 0.0,
                    contype=int(el.get("contype", 0)), basetype=int(el.get("basetype", 0)))
            elif tag == "freenode":
                self.free[el.get("id")] = nl2_to_blender(_vec(el.find("pos")))
            elif tag == "rasc":
                subs = []
                for sn in el.findall("subnode"):
                    p = nl2_to_blender(_vec(sn.find("pos")))
                    subs.append((sn.get("id"), p))
                    self.subnodes[sn.get("id")] = p
                self.rascs.append(dict(type=int(el.get("type", 0)), coord=float(el.get("center_rails_coord", 0)),
                                       track=int(el.get("custom_track_index", 0) or 0),
                                       size=float(el.get("size")) if el.get("size") else None, subs=subs,
                                       mainspine=el.find("colormode_mainspine") is not None))
            elif tag == "beam":
                b = dict(start=el.get("start"), end=el.get("end"), type=int(el.get("type", 1)),
                         size1=float(el.get("size1", 0.5)), size2=float(el.get("size2", el.get("size1", 0.5))),
                         ex0=float(el.findtext("start_extra_length", "0") or 0),
                         ex1=float(el.findtext("end_extra_length", "0") or 0),
                         colour=None, mainspine=el.find("colormode_mainspine") is not None, nodes=[],
                         rot=float(el.findtext("rotation", "0") or 0), vertical=el.find("vertical") is not None,
                         offx=float(el.findtext("offset_rel_x", "0") or 0),
                         oy1=float(el.findtext("offset_abs_y1", "0") or 0),
                         oy2=float(el.findtext("offset_abs_y2", "0") or 0),
                         mode=("metal" if el.find("colormode_unpaintedmetal") is not None else
                               "catwalk" if el.find("colormode_catwalk") is not None else
                               "handrails" if el.find("colormode_handrails") is not None else None))
                c = el.find("colormode_custom")
                if c is not None:
                    b["colour"] = (float(c.get("r")), float(c.get("g")), float(c.get("b")))
                for bn in el.findall("beamnode"):
                    b["nodes"].append((bn.get("id"), float(bn.get("pos", 0.5)), int(bn.get("type", 0))))
                    self.beamnodes[bn.get("id")] = (len(self.beams), float(bn.get("pos", 0.5)))
                self.beams.append(b)
        self._cache = {}

    def pos(self, nid, depth=0):
        if nid in self._cache:
            return self._cache[nid]
        p = None
        if nid in self.footers:
            p = self.footers[nid]["pos"]
        elif nid in self.free:
            p = self.free[nid]
        elif nid in self.subnodes:
            p = self.subnodes[nid]
        elif nid in self.beamnodes and depth < 64:
            bi, t = self.beamnodes[nid]
            b = self.beams[bi]
            a, c = self.pos(b["start"], depth + 1), self.pos(b["end"], depth + 1)
            if a is not None and c is not None:
                if b["type"] in LUMBER_TYPES:
                    # wood/metal beam nodes are measured along the offset, extended beam
                    fr = lumber_frame(a, c, b)
                    if fr is not None:
                        a, c = fr[0], fr[1]
                p = a + (c - a) * t
        self._cache[nid] = p
        return p

    def beam_at(self, nid):
        if not hasattr(self, "_node_beam"):
            self._node_beam = {}
            for b in self.beams:
                self._node_beam.setdefault(b["start"], b)
                self._node_beam.setdefault(b["end"], b)
        return self._node_beam.get(nid)

    def beam_size_at(self, nid):
        b = self.beam_at(nid)
        return b["size1"] if b is not None else None


LUMBER_TYPES = (6, 7, 8)   # 6 = wood lumber, 7 = catwalk, 8 = steel C-channel (wooden/hybrid structures)
_UPW = np.array([0.0, 0.0, 1.0])


def lumber_frame(a, c, b):
    """End points (offset + extended) and section axes of a wood/metal beam.

    xr = the beam's lateral axis (NL2 offset_rel_x direction, dir x up), y = section 'up'.
    size1 runs along xr, size2 along y.  Vertical beams (posts) use `rotation` as the yaw of xr;
    for other beams `rotation` rolls the section about the beam axis.
    """
    d = c - a
    ln = np.linalg.norm(d)
    if ln < 1e-6:
        return None
    d = d / ln
    if b["vertical"] or abs(d[2]) > 0.98:
        th = b["rot"] if b["vertical"] else 0.0
        xr = np.array([math.cos(th), -math.sin(th), 0.0])
        xr = xr - (xr @ d) * d
        if np.linalg.norm(xr) < 1e-6:
            xr = np.array([0.0, 1.0, 0.0]) - d[1] * d
    else:
        xr = np.cross(d, _UPW)
    xr = _norm(xr)
    a = a + b["offx"] * xr + b["oy1"] * _UPW
    c = c + b["offx"] * xr + b["oy2"] * _UPW
    d = c - a
    ln = np.linalg.norm(d)
    if ln < 1e-6:
        return None
    d = d / ln
    xr = _norm(xr - (xr @ d) * d)
    y = np.cross(xr, d)
    if not b["vertical"] and b["rot"]:
        cr, sr = math.cos(b["rot"]), math.sin(b["rot"])
        xr, y = cr * xr + sr * y, -sr * xr + cr * y
    return a - d * b["ex0"], c + d * b["ex1"], d, xr, y


class _Prisms:
    """Batched straight prisms (lumber boxes and C-channels), emitted with numpy in one go."""
    TW, TF = 0.012, 0.014  # channel web / flange thickness

    def __init__(self):
        self.items = {}

    def add(self, mat, kind, a, c, xr, y, w, h):
        self.items.setdefault((mat, kind), []).append(np.r_[a, c, xr, y, w, h])

    @classmethod
    def _profile(cls, kind, w, h):
        w, h = w[:, None] / 2, h[:, None] / 2
        if kind == "box":
            px = np.hstack([-w, w, w, -w])
            py = np.hstack([-h, -h, h, h])
            caps = [(0, 1, 2, 3)]
        else:
            # C-channel, web on the +x side (towards the post the beam is offset from), CCW
            tw, tf = cls.TW, cls.TF
            px = np.hstack([-w, w, w, -w, -w, w - tw, w - tw, -w])
            py = np.hstack([-h, -h, h, h, h - tf, h - tf, -h + tf, -h + tf])
            caps = [(0, 1, 6, 7), (1, 2, 5, 6), (3, 4, 5, 2)]
        return px, py, caps

    def emit(self, mb):
        for (mat, kind), rows in self.items.items():
            R = np.array(rows)
            A, C, XR, Y, W, H = R[:, 0:3], R[:, 3:6], R[:, 6:9], R[:, 9:12], R[:, 12], R[:, 13]
            X = -XR  # (x, y, dir) right-handed
            px, py, caps = self._profile(kind, W, H)
            n = px.shape[1]
            off = px[:, :, None] * X[:, None, :] + py[:, :, None] * Y[:, None, :]
            V = np.concatenate([A[:, None, :] + off, C[:, None, :] + off], axis=1)  # (N, 2n, 3)
            i = np.arange(n)
            j = (i + 1) % n
            faces = [np.c_[i, j, n + j, n + i]]
            faces.append(np.array([tuple(reversed(q)) for q in caps]))
            faces.append(np.array(caps) + n)
            F = np.vstack(faces)
            N = len(R)
            idx = (F.ravel()[None, :] + (np.arange(N) * 2 * n)[:, None]).ravel()
            mb.add(V.reshape(-1, 3), idx, np.full(N * len(F), 4), mat, False)


def _catwalk(prisms, a, c, d, xr, y, width, mat):
    """Wooden catwalk: 2x8 deck planks across two stringers."""
    ln = float(np.linalg.norm(c - a))
    n = max(1, int(round(ln / 0.2)))
    pw, pt = 0.1778, 0.0381
    for k in range(n):
        m = a + d * ((k + 0.5) * ln / n)
        prisms.add(mat, "box", m - d * pw / 2, m + d * pw / 2, xr, y, width, pt)
    for s in (-1, 1):
        o = xr * s * (width / 2 - 0.06) - y * (pt / 2 + 0.07)
        prisms.add(mat, "box", a + o, c + o, xr, y, 0.0508, 0.14)


def beam_mesh(a, b, beam, sides, mb, mat, near_track_F=None):
    d = b - a
    ln = np.linalg.norm(d)
    if ln < 1e-6:
        return
    d /= ln
    a = a - d * beam["ex0"]
    b = b + d * beam["ex1"]
    if beam["type"] == 5:
        # box: size1 horizontal, size2 in the (up / along-track) direction
        if abs(d[2]) > 0.95:
            ax2 = near_track_F if near_track_F is not None else np.array([1.0, 0, 0])
            ax2 = ax2 - (ax2 @ d) * d
            if np.linalg.norm(ax2) < 1e-6:
                ax2 = np.array([1.0, 0, 0])
        else:
            ax2 = np.array([0, 0, 1.0]) - d[2] * d
        ax2 /= np.linalg.norm(ax2)
        ax1 = np.cross(d, ax2)
        h1, h2 = beam["size1"] / 2, beam["size2"] / 2
        prof = [(-h1, -h2), (h1, -h2), (h1, h2), (-h1, h2)]
        for i in range(4):
            p0, p1 = prof[i], prof[(i + 1) % 4]
            q = [a + p0[0] * ax1 + p0[1] * ax2, a + p1[0] * ax1 + p1[1] * ax2,
                 b + p1[0] * ax1 + p1[1] * ax2, b + p0[0] * ax1 + p0[1] * ax2]
            mb.add(np.array(q), [0, 3, 2, 1], [4], mat, False)
        capa = [a + p[0] * ax1 + p[1] * ax2 for p in prof]
        capb = [b + p[0] * ax1 + p[1] * ax2 for p in prof]
        mb.add(np.array(capa), [0, 1, 2, 3], [4], mat, False)
        mb.add(np.array(capb), [3, 2, 1, 0], [4], mat, False)
        return
    r = beam["size1"] / 2
    M = axis_matrix(d)[0]
    t = np.linspace(0, 2 * np.pi, sides, endpoint=False)
    ring = np.c_[r * np.cos(t), r * np.sin(t), np.zeros(sides)] @ M.T
    V = np.vstack([a + ring, b + ring])
    i = np.arange(sides)
    j = (i + 1) % sides
    quads = np.c_[i, j, sides + j, sides + i]
    mb.add_quads(V, quads, mat, True)
    mb.add(V[:sides], i[::-1], [sides], mat, False)
    mb.add(V[sides:], sides + i, [sides], mat, False)


def _face_verts(a, face_mask):
    starts = np.r_[0, np.cumsum(a.counts)][:-1]
    f = np.where(face_mask)[0]
    if len(f) == 0:
        return np.arange(len(a.V))
    return np.concatenate([a.idx[starts[j]:starts[j] + a.counts[j]] for j in f])


def _beam_dir(sup, nid, p):
    """Unit direction from node p along the (first) beam attached to node nid."""
    b = sup.beam_at(nid)
    if b is not None:
        o = sup.pos(b["end"] if b["start"] == nid else b["start"])
        if o is not None and np.linalg.norm(o - p) > 1e-6:
            return _norm(o - p)
    return None


def _flare(mb, a, O, x, y, z, P, L, U, F, spine_bottom, mat, top_hw=0.24, top_hl=0.61, ch=0.05):
    """Tapered web joining a connector plate (model y = 0 at O) to the underside of the spine."""
    V = a.V
    near = V[np.abs(V[:, 1]) < 0.001]
    if len(near) == 0:
        return
    px, pz = float(np.abs(near[:, 0]).max()), float(np.abs(near[:, 2]).max())

    def octagon(hx, hz, c):
        return np.array([(hx - c, -hz), (hx, -hz + c), (hx, hz - c), (hx - c, hz),
                         (-hx + c, hz), (-hx, hz - c), (-hx, -hz + c), (-hx + c, -hz)])

    lo = octagon(px, pz, ch)
    bot = O + lo[:, 0:1] * x + lo[:, 1:2] * z
    # map model x/z onto the spine's left/forward axes so the loft doesn't twist
    xl = x - (x @ U) * U
    if np.linalg.norm(xl) < 0.2:
        xl = L.copy()
    xl = _norm(xl)
    zl = np.cross(xl, U)
    if zl @ z < 0:
        zl = -zl
    hi = octagon(top_hw, top_hl, ch * 0.5)
    ctr = P + (spine_bottom + 0.03) * U
    top = ctr + hi[:, 0:1] * xl + hi[:, 1:2] * zl
    Vv = np.vstack([bot, top])
    n = len(lo)
    i = np.arange(n)
    j = (i + 1) % n
    quads = np.c_[i, j, n + j, n + i]
    # orient outward: face normal should point away from the loft axis
    c0 = Vv.mean(0)
    q = quads[0]
    nrm = np.cross(Vv[q[1]] - Vv[q[0]], Vv[q[3]] - Vv[q[0]])
    if nrm @ (Vv[q[0]] - c0) < 0:
        quads = quads[:, ::-1]
    mb.add(Vv, quads.ravel(), np.full(n, 4), mat, False)


def _column_connector(mb, node, top, L, F, r, top_hx, top_hz, sides, mat, bolts, nuts):
    """Arrow-style column head (rasc 259): bolted flange pair at the column top, then a neck that
    tapers from the round column into a rounded-rectangle saddle inside the spine."""
    ax = top - node
    ln = np.linalg.norm(ax)
    if ln < 1e-6:
        return
    ax /= ln
    ex = L - (L @ ax) * ax
    if np.linalg.norm(ex) < 1e-6:
        ex = np.cross(ax, F)
    ex = _norm(ex)
    ez = np.cross(ex, ax)
    if ez @ F < 0:
        ez = -ez
    n = max(16, sides * 2)
    th = np.linspace(0, 2 * np.pi, n, endpoint=False)
    c, s = np.cos(th), np.sin(th)
    fl = 0.05  # flange pair thickness
    base = node + fl * ax
    # square neck: round-cornered square at the flange, rounded rectangle inside the spine
    sx, sz = np.clip(c * 1.6, -1, 1), np.clip(s * 1.6, -1, 1)
    bot = base + 0.85 * r * (sx[:, None] * ex + sz[:, None] * ez)
    upper = top + top_hx * sx[:, None] * ex + top_hz * sz[:, None] * ez
    V = np.vstack([bot, upper])
    i = np.arange(n)
    j = (i + 1) % n
    quads = np.c_[i, j, n + j, n + i]
    q = quads[0]
    nrm = np.cross(V[q[1]] - V[q[0]], V[q[3]] - V[q[0]])
    if nrm @ (V[q[0]] - base) < 0:
        quads = quads[:, ::-1]
    mb.add(V, quads.ravel(), np.full(n, 4), mat, False)
    # flange pair (column flange + connector flange), bolted through
    M = axis_matrix(ax)[0]
    for z0, z1 in ((0.0, fl * 0.5), (fl * 0.5, fl)):
        Vd, idx, cnt = disc(0, 0, r * 0.9, r + 0.09, z0, z1, n)
        mb.add(node + Vd @ M.T, idx, cnt, mat, False)
    nb = max(8, int(round(2 * np.pi * (r + 0.045) / 0.2)))
    ang = np.linspace(0, 2 * np.pi, nb, endpoint=False)
    rb = r + 0.045
    ring = rb * np.c_[np.cos(ang), np.sin(ang), np.zeros(nb)]
    bolts.add(node + (ring + [0, 0, fl]) @ M.T, np.repeat(M[None], nb, 0), 0.9)
    Mn = M @ np.diag([1, -1, -1])
    nuts.add(node + ring @ M.T, np.repeat(Mn[None], nb, 0), 0.9)


def _scaled(a, k):
    b = a.copy()
    b.V = a.V * np.asarray(k, dtype=float)
    return b


def _pick_size(size):
    # the game rounds up to the next connector size (a 24" beam uses the 30" connector)
    for d, n in ((0.508, 20), (0.762, 30)):
        if size <= d + 0.01:
            return n
    return 42


def build_supports(track, sup, style, option, params):
    A = get_assets(style, option, params)
    mb = MeshBuilder()
    bolts, nuts, flanges = Instances(), Instances(), Instances()
    sides = int(params.get("beam_sides", 20))
    off_track = 0
    attach = params.get("attach") or option.get("attach") or -0.7
    colours = {}
    rascdef = _styles.RASC_MODELS.get(style["rasc"], {})
    sup_map = {"support": "Supports", "spine": "Spine", "tie": "Ties", "steel": "Steel", "concrete": "Concrete",
               "rail": "Rails", "metal": "Unpainted Metal", "*": "Supports"}

    def beam_mat(b):
        if b["colour"] is not None:
            key = "Custom %.3f %.3f %.3f" % b["colour"]
            colours[key] = b["colour"]
            return key
        if b["mode"]:
            return {"metal": "Unpainted Metal", "catwalk": "Catwalk", "handrails": "Handrails"}[b["mode"]]
        return "Spine" if b["mainspine"] else "Supports"

    # track points for orienting vertical box columns
    def nearest_F(p):
        i = int(np.argmin(np.sum((track.P - p) ** 2, axis=1)))
        f = track.F[i].copy()
        f[2] = 0
        n = np.linalg.norm(f)
        return f / n if n > 1e-6 else None

    # --- beams
    prisms = _Prisms()
    wb_pos, wb_dir = [], []
    for b in sup.beams:
        a, c = sup.pos(b["start"]), sup.pos(b["end"])
        if a is None or c is None:
            continue
        if b["type"] in LUMBER_TYPES:
            fr = lumber_frame(a, c, b)
            if fr is None:
                continue
            a2, c2, d, xr, y = fr
            mat = beam_mat(b)
            if b["type"] == 7:
                _catwalk(prisms, a2, c2, d, xr, y, b["size1"], mat)
                continue
            w, h = b["size1"], b["size2"]
            s = -1.0 if b["offx"] < 0 else 1.0
            if b["type"] == 8:
                # keep the channel web against the member it is bolted to
                prisms.add(mat, "chan", a2, c2, s * xr, s * y, w, h)
            else:
                prisms.add(mat, "box", a2, c2, xr, y, w, h)
            # beam nodes 2/3 (lumber) and 5/6 (channels) are the through-bolts at the joints
            for nid, t, typ in b["nodes"]:
                if typ not in (2, 3, 5, 6):
                    continue
                p = a2 + (c2 - a2) * t
                if b["type"] == 8:
                    for dy in (-0.25 * h, 0.25 * h):
                        wb_pos.append(p + s * (-w / 2 + _Prisms.TW) * xr + dy * y)
                        wb_dir.append(s * xr)
                else:
                    wb_pos.append(p + s * (w / 2) * xr)
                    wb_dir.append(s * xr)
            continue
        if b["type"] == 9:
            # steel cable handrail
            beam_mesh(a, c, b, 6, mb, beam_mat(b))
            continue
        nf = nearest_F(a if a[2] > c[2] else c) if b["type"] == 5 else None
        beam_mesh(a, c, b, sides, mb, beam_mat(b), nf)
        # flanges at type-1 beam nodes (bolted splices)
        d = c - a
        ln = np.linalg.norm(d)
        if ln < 1e-6:
            continue
        d /= ln
        for nid, t, typ in b["nodes"]:
            if typ != 1 or b["type"] == 5:
                continue
            p = a + (c - a) * t
            r = b["size1"] / 2
            V, idx, cnt = disc(0, 0, r * 0.9, r + 0.08, -0.025, 0.025, sides)
            M = axis_matrix(d)[0]
            mb.add(p + V @ M.T, idx, cnt, beam_mat(b), False)
            nb = max(8, int(round(2 * np.pi * (r + 0.04) / 0.12)))
            ang = np.linspace(0, 2 * np.pi, nb, endpoint=False)
            for sgn in (1, -1):
                loc = np.c_[(r + 0.045) * np.cos(ang), (r + 0.045) * np.sin(ang), np.full(nb, 0.025 * sgn)]
                Mz = M if sgn > 0 else M @ np.diag([1, -1, -1])
                (bolts if sgn > 0 else nuts).add(p + loc @ M.T, np.repeat(Mz[None], nb, 0), 0.9)
    prisms.emit(mb)
    if wb_pos:
        bolts.add(np.array(wb_pos), axis_matrix(np.array(wb_dir)), 0.6)

    # --- footers
    # Game footer (measured on Fury): chamfered concrete block (footer-normal) and a steel base plate
    # (top-box, 2 cm thick), both scaled in plan to 2.8 x the column diameter, 8 anchor bolts.
    # contype 1/2 add four triangular gussets (tri_fin_arrow / tri_fin) scaled by the diameter.
    if params.get("footers", True):
        FA = A["footers"]
        for fid, f in sup.footers.items():
            p = f["pos"]
            th = f["rot"]
            c, s = math.cos(th), math.sin(th)
            L = np.array([[c, s, 0.0]])
            F = np.array([[s, -c, 0.0]])  # F = L x U keeps the frame right-handed
            U = np.array([[0, 0, 1.0]])
            D = 0.6096
            btype, bsz = None, None
            b = sup.beam_at(fid)
            if b is not None:
                D = max(b["size1"], b["size2"]) if b["type"] in (5,) + LUMBER_TYPES else b["size1"]
                btype, bsz = b["type"], (b["size1"], b["size2"])
            k = 2.8 * D
            if (f["basetype"] in (2, 3) or btype == 6) and "wood_round_main" in FA:
                # wooden post footer: round (3) or square (2) concrete pier, steel post mount brackets
                sq = f["basetype"] == 2
                main = FA["wood_square_main" if sq else "wood_round_main"]
                base = FA["wood_square_base" if sq else "wood_round_base"]
                add_instances(mb, _scaled(main, (k, 1, k)), p[None], L, U, F, sup_map, smooth=not sq)
                h = f["hat"] + 0.2 - 0.41
                if h > 0.01:
                    add_instances(mb, _scaled(base, (k, h / 2.0, k)), (p - [0, 0, 0.41 + h])[None],
                                  L, U, F, sup_map, smooth=not sq)
                if f["contype"] == 1 and bsz is not None:
                    ax1 = np.array([c, -s, 0.0])   # post size1 axis (NL2 yaw -> Blender)
                    ax2 = np.array([s, c, 0.0])
                    for sg in (1, -1):
                        add_instances(mb, FA["wood_mount"], (p + sg * bsz[1] / 2 * ax2)[None],
                                      (sg * ax2)[None], U, (sg * ax1)[None], sup_map, smooth=False)
                continue
            if "old_main" in FA:
                add_instances(mb, _scaled(FA["old_main"], (k, 1, k)), p[None], L, U, F, sup_map, smooth=False)
                # pier below the block, only as deep as needed to reach 0.2 m below the terrain
                h = f["hat"] + 0.2 - 0.39
                if h > 0.01:
                    add_instances(mb, _scaled(FA["old_base"], (k, h / 2.4, k)), (p - [0, 0, 0.39 + h])[None],
                                  L, U, F, sup_map, smooth=False)
                add_instances(mb, _scaled(FA["old_top_box"], (k, 0.02, k)), p[None], L, U, F, sup_map,
                              smooth=False)
                top = p + [0, 0, 0.02]
                fin = {1: "tri_fin_arrow", 2: "tri_fin"}.get(f["contype"])
                nfin = 4 if fin else 0
                if fin:
                    # fin profile: radial z (inner edge -0.61, outer 1.2), height y 0..1, thickness x
                    zs = max(0.2, 0.5 * k - 0.5 * D - 0.04) / 1.2
                    fa = _scaled(FA[fin], (0.025, D, zs))
                    for j in range(nfin):
                        a_ = th + j * math.pi / 2
                        cj, sj = math.cos(a_), math.sin(a_)
                        # fin plane contains the radial direction (model z) and up
                        Fj = np.array([[cj, sj, 0.0]])
                        Lj = np.array([[-sj, cj, 0.0]])
                        add_instances(mb, fa, (top + 0.5 * D * Fj[0])[None], Lj, U, Fj, sup_map, smooth=False)
                nb = 8
                ang = th + (np.arange(nb) + 0.5) * 2 * math.pi / nb
                rb = 0.6 * D + 0.025 if not fin else min(1.15 * D, 0.45 * k)
                loc = top + np.c_[rb * np.cos(ang), rb * np.sin(ang), np.zeros(nb)]
                bolts.add(loc, np.repeat(np.eye(3)[None], nb, 0), 0.5 + D)
            else:
                add_instances(mb, FA["steel_top"], p[None], L, U, F, sup_map, smooth=False)
                add_instances(mb, FA["steel_main"], p[None], L, U, F, sup_map, smooth=False)
                add_instances(mb, FA["steel_base"], (p - [0, 0, 2.5])[None], L, U, F, sup_map, smooth=False)

    # --- track connectors
    if params.get("connectors", True) and sup.rascs:
        mode = params.get("colour_mode", "PLAIN")
        con_mat = "Spine Accent" if mode in ("BOTTOM", "TOPBOTTOM") else "Spine"
        con_map = dict(sup_map, spine=con_mat)
        boxes = [p for p in option["parts"] if p[0] == "box"]
        spine_bottom = min(p[3] for p in boxes) if boxes else attach
        # lowest structural part = what an Arrow column head (rasc 259) plugs into
        low = None
        for p in option["parts"]:
            if p[0] == "tube":
                cand = (p[2] - p[3], p[1], p[2], p[3] * 0.95)
            elif p[0] == "box":
                cand = (p[3], (p[1] + p[2]) / 2, (p[3] + p[4]) / 2, (p[2] - p[1]) / 2 * 0.95)
            else:
                continue
            if low is None or cand[0] < low[0]:
                low = cand
        coords = np.array([r["coord"] for r in sup.rascs])
        P, L, U, F = track.frames_at_nl2(coords)
        # connectors can belong to other track sections (custom_track_index) that aren't in this spline
        idxs = [r["track"] for r in sup.rascs]
        main_idx = params.get("track_index")
        if main_idx is None or main_idx < 0:
            main_idx = max(set(idxs), key=idxs.count)
        for k, r in enumerate(sup.rascs):
            subs = [p for _, p in r["subs"]]
            if not subs:
                continue
            Ap = P[k] + attach * U[k]
            if r["track"] != main_idx or min(np.linalg.norm(s - Ap) for s in subs) > 6.0:
                # not on this spline: just cap the support with a plate at its node
                off_track += 1
                if "tie" in rascdef:
                    continue
                pl = A["rascs"].get(rascdef.get("plate", "corkcon0"))
                if pl is not None:
                    for sid, sp in r["subs"]:
                        bdir = _beam_dir(sup, sid, sp)
                        if bdir is None:
                            continue
                        y = -bdir
                        z = np.cross(y, [0, 0, 1.0])
                        if np.linalg.norm(z) < 1e-6:
                            z = np.array([1.0, 0, 0])
                        z = _norm(z)
                        x = np.cross(y, z)
                        add_instances(mb, pl, sp[None], x[None], y[None], z[None], con_map, smooth=False)
                continue
            if "tie" in rascdef:
                # wooden / hybrid: shoe models placed in the track frame, they rest on the structure
                for key in rascdef["tie"]:
                    a = A["rascs"].get(key)
                    if a is None:
                        continue
                    sl = slice(k, k + 1)
                    add_instances(mb, a, P[sl], L[sl], U[sl], F[sl], sup_map, smooth=False)
                    marker_instances(a.bolts, P[sl], L[sl], U[sl], F[sl], bolts)
                    marker_instances(a.nuts, P[sl], L[sl], U[sl], F[sl], nuts)
                continue
            if r.get("type") == 259 and len(subs) == 1 and low is not None:
                size = r["size"] or sup.beam_size_at(r["subs"][0][0]) or 0.6096
                top = P[k] + low[1] * L[k] + low[2] * U[k]
                rc = size / 2
                _column_connector(mb, subs[0], top, L[k], F[k], rc, low[3], max(rc * 1.3, low[3]), sides,
                                  "Supports", bolts, nuts)
                continue
            size = r["size"] or sup.beam_size_at(r["subs"][0][0]) or 0.762
            if len(subs) >= 2:
                mids = subs[1:-1] if len(subs) > 2 else subs
                target = np.mean(mids, axis=0)
                cross = (subs[0], subs[-1])
            else:
                target = subs[0]
                cross = None
            dist = float(np.linalg.norm(target - Ap))
            mat_main = "Spine"
            if "vert" in rascdef and dist < 0.15:
                # direct plate onto the spine
                a = A["rascs"][rascdef["plate"]]
                bdir = _beam_dir(sup, r["subs"][0][0], target)
                y = -bdir if bdir is not None else U[k].copy()
                y = y / np.linalg.norm(y)
                z = F[k] - (F[k] @ y) * y
                z /= np.linalg.norm(z)
                x = np.cross(y, z)
                add_instances(mb, a, target[None], x[None], y[None], z[None], con_map, smooth=False)
                marker_instances(a.bolts, target[None], x[None], y[None], z[None], bolts)
                marker_instances(a.nuts, target[None], x[None], y[None], z[None], nuts)
                continue
            if "vert" in rascdef:
                # Game layout: the connector model's plate (y = 0) faces the spine, its body runs
                # along -y.  A flared web (spine colour) joins the plate to the underside of the spine.
                key = (rascdef["horz"] if cross else rascdef["vert"]) % _pick_size(size)
                a = A["rascs"][key]
                if cross is not None:
                    # horizontal crossbar: the model's round gussets wrap the bar, bar axis = model x
                    x = _norm(cross[1] - cross[0])
                    y = Ap - target
                    y = y - (y @ x) * x
                    if np.linalg.norm(y) < 1e-6:
                        y = U[k] - (U[k] @ x) * x
                    y = _norm(y)
                    z = np.cross(x, y)
                    sup_slot = a.slot == a.slots.index("support") if "support" in a.slots else None
                    Vs = a.V if sup_slot is None else a.V[np.unique(_face_verts(a, sup_slot))]
                    yc = -float(a.V[:, 1].min()) - float(np.abs(Vs[:, 2]).max())
                    O = target + yc * y
                else:
                    bdir = _beam_dir(sup, r["subs"][0][0], target)
                    y = -bdir if bdir is not None else _norm(Ap - target)
                    z = F[k] - (F[k] @ y) * y
                    if np.linalg.norm(z) < 1e-6:
                        z = L[k].copy()
                    z = _norm(z)
                    x = np.cross(y, z)
                    O = target
                add_instances(mb, a, O[None], x[None], y[None], z[None], con_map, smooth=False)
                marker_instances(a.bolts, O[None], x[None], y[None], z[None], bolts)
                marker_instances(a.nuts, O[None], x[None], y[None], z[None], nuts)
                _flare(mb, a, O, x, y, z, P[k], L[k], U[k], F[k], spine_bottom, con_mat)
            else:
                # tie-like clamp on the track, then a stub tube down to the node
                clamp = rascdef.get("clamp")
                if clamp == "int_900_3t":
                    ntube = sum(1 for p in option["parts"] if p[0] == "tube")
                    clamp = "int_900_%dt" % min(4, max(2, 2 + ntube))
                if clamp == "gerst_1200_2t" and any(p[0] == "tube" for p in option["parts"]):
                    clamp = "gerst_1200_3t"
                if clamp and clamp in A["rascs"]:
                    a = A["rascs"][clamp]
                    add_instances(mb, a, P[k:k + 1], L[k:k + 1], U[k:k + 1], F[k:k + 1], sup_map, smooth=False)
                    marker_instances(a.bolts, P[k:k + 1], L[k:k + 1], U[k:k + 1], F[k:k + 1], bolts)
                    marker_instances(a.nuts, P[k:k + 1], L[k:k + 1], U[k:k + 1], F[k:k + 1], nuts)
                if dist > 0.05:
                    beam_mesh(Ap, target, dict(type=1, size1=min(size, 0.4), ex0=0, ex1=0), sides, mb, "Supports")
                pl = A["rascs"].get(rascdef.get("plate", "corkcon0"))
                if pl is not None and dist > 0.3:
                    y = -_norm(target - Ap)
                    z = F[k] - (F[k] @ y) * y
                    z /= np.linalg.norm(z)
                    x = np.cross(y, z)
                    add_instances(mb, pl, target[None], x[None], y[None], z[None], sup_map, smooth=False)
            if cross is not None:
                c0, c1 = cross
                d = c1 - c0
                ln = np.linalg.norm(d)
                if ln > 1e-6:
                    d /= ln
                    rr = size / 2
                    beam_mesh(c0, c1, dict(type=1, size1=size, ex0=0, ex1=0), sides, mb,
                              "Supports")
                    for end, sgn in ((c0, -1), (c1, 1)):
                        tip = end + sgn * d * rr * 0.9
                        M = axis_matrix(d * sgn)[0]
                        t = np.linspace(0, 2 * np.pi, sides, endpoint=False)
                        ring = end + np.c_[rr * np.cos(t), rr * np.sin(t), np.zeros(sides)] @ M.T
                        V = np.vstack([ring, tip[None]])
                        i = np.arange(sides)
                        tri = np.c_[i, (i + 1) % sides, np.full(sides, sides)]
                        mb.add(V, tri.ravel(), np.full(sides, 3),
                               "Supports", True)

    inst = {}
    if params.get("bolts", True):
        inst["support_bolts"] = (A["bolts"]["bolt"], bolts)
        inst["support_nuts"] = (A["bolts"]["nut"], nuts)
    info = "%d beams, %d footers, %d connectors" % (len(sup.beams), len(sup.footers), len(sup.rascs))
    if off_track:
        info += " (%d on other track sections, not attached)" % off_track
    return dict(mesh=mb, instances=inst, colours=colours, info=info)
