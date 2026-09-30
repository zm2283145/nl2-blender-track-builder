"""Pack NoLimits 2 track assets into nl2_track_builder/assets/nl2_assets.json.gz.

Usage:
  python build_assets.py --list nl2vfsdump.txt          (file list for the dump DLL)
  python build_assets.py --vfs <dump>/vfs/data [--bolts flange_bolts.pkl]

Inputs:
  * the VFS dump of YOUR OWN NoLimits 2 install, written by nl2vfsdump.dll from the
    nl2-model-export project (<dll folder>/vfs/data/...)
  * optional: a captured B&M flange bolt set (pickle). Without it simple procedural
    bolts/nuts are generated and the B&M flange bolt rings are skipped.

The resulting asset pack contains meshes owned by the NoLimits 2 developers. It is for
personal use only: never commit, share or sell it (it is excluded by .gitignore).

Every mesh is stored in a common *track-local* frame (metres):
  x = to the right of the track, y = up (track up vector), z = forward along the track.
LWO files already use that convention; 3DS ties are inches with (x, z-up, y-forward).
"""
import argparse, gzip, json, os, pickle, sys
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import lwo, tds  # noqa: E402

VFS = os.environ.get("NL2_VFS", "")
BOLTS = os.environ.get("NL2_BOLTS", "")
OUT = os.path.join(HERE, "nl2_track_builder", "assets", "nl2_assets.json.gz")

SURF_SLOT = {"AUTOTIE": "tie", "AUTOTIEFLAT": "tie", "AUTOMAIN": "spine", "AUTOSUPPORT": "support",
             "AUTORAIL": "rail", "AUTOHANDRAIL": "rail", "CONCRETE": "concrete", "SEITE": "concrete", "TOP": "concrete",
             "AUTONOPAINTMETAL": "metal", "AUTOMETAL": "metal"}


def slot_for(name):
    n = (name or "").upper()
    for k, v in SURF_SLOT.items():
        if n.startswith(k):
            return v
    return "steel"


def pack(V, polys, slots):
    V = np.asarray(V, dtype=float).reshape(-1, 3)
    counts = [len(p) for p in polys]
    return {"v": np.round(V, 5).reshape(-1).tolist(), "c": counts,
            "i": [int(i) for p in polys for i in p], "s": slots}


# Stored frame for every asset: x = track LEFT, y = track UP, z = FORWARD (right-handed), so that
# placement is a pure rotation [L, U, F].
def load_lwo_mesh(rel, markers=True):
    m = lwo.load_lwo(open(os.path.join(VFS, rel), "rb").read())
    V, P, S, bolts, nuts = [], [], [], [], []
    slotnames = []
    for L in m["layers"]:
        pts = np.array(L["points"], dtype=float).reshape(-1, 3)
        pts = pts * np.array([-1.0, 1.0, 1.0])  # LWO x = right  ->  x = left (fixes LWO handedness)
        special = L["name"].upper() in ("SPECIALBOLT", "SPECIALNUT")
        base = len(V)
        if not special:
            V.extend(pts.tolist())
        for typ, tag, vs in L["polys"]:
            if typ != "FACE" or len(vs) < 3:
                continue
            if special:
                if not markers:
                    continue
                q = pts[vs[:3]]
                n = -np.cross(q[1] - q[0], q[2] - q[0])  # mirrored data: flip the cross product
                ln = np.linalg.norm(n)
                if ln < 1e-12:
                    continue
                size = max(np.linalg.norm(q[1] - q[0]), np.linalg.norm(q[2] - q[1]), np.linalg.norm(q[0] - q[2]))
                rec = np.round(np.r_[q.mean(0), n / ln, size], 5).tolist()
                (bolts if L["name"].upper() == "SPECIALBOLT" else nuts).append(rec)
                continue
            sl = slot_for(m["tags"][tag] if tag < len(m["tags"]) else "")
            if sl not in slotnames:
                slotnames.append(sl)
            P.append([base + v for v in vs])
            S.append(slotnames.index(sl))
    d = pack(V, P, S)
    d["slots"] = slotnames
    if bolts:
        d["bolts"] = bolts
    if nuts:
        d["nuts"] = nuts
    return d


def load_3ds_mesh(rel, scale=0.0254):
    m = tds.load_3ds(open(os.path.join(VFS, rel), "rb").read())
    V, P, S = [], [], []
    for o in m["objects"]:
        if not o["points"]:
            continue
        pts = np.array(o["points"], dtype=float) * scale
        # 3DS (x = right, y = forward, z = up) -> (left, up, forward): a proper rotation, keep winding
        pts = np.c_[-pts[:, 0], pts[:, 2], pts[:, 1]]
        base = len(V)
        V.extend(pts.tolist())
        for f in o["faces"]:
            P.append([base + int(f[0]), base + int(f[1]), base + int(f[2])])
            S.append(0)
    d = pack(V, P, S)
    d["slots"] = ["tie"]
    return d


TIES = {
    # B&M
    "bm_std": "coasterstyles/bandm/bmtie_standard_best.lwo",
    "bm_std_good": "coasterstyles/bandm/bmtie_standard_good.lwo",
    "bm_start": "coasterstyles/bandm/bmtie_start_best.lwo",
    "bm_end": "coasterstyles/bandm/bmtie_end_best.lwo",
    "bm_larger_start": "coasterstyles/bandm/bmtie_larger_start_best.lwo",
    "bm_larger_end": "coasterstyles/bandm/bmtie_larger_end_best.lwo",
    "bm_largest_start": "coasterstyles/bandm/bmtie_largest_start_best.lwo",
    "bm_largest_end": "coasterstyles/bandm/bmtie_largest_end_best.lwo",
    "bm_lowered": "coasterstyles/bandm/bmtie_lowered_best.lwo",
    "bm_lowered_start": "coasterstyles/bandm/bmtie_lowered_start_best.lwo",
    "bm_lowered_end": "coasterstyles/bandm/bmtie_lowered_end_best.lwo",
    "bm_lift": "coasterstyles/bandm/bmtie_lift_best.lwo",
    # B&M dive
    "dive_std": "coasterstyles/divecoaster/bmdivetie_standard_best.lwo",
    "dive_start": "coasterstyles/divecoaster/bmdivetie_start_best.lwo",
    "dive_end": "coasterstyles/divecoaster/bmdivetie_end_best.lwo",
    "dive_medium_start": "coasterstyles/divecoaster/bmdivetie_medium_start_best.lwo",
    "dive_medium_end": "coasterstyles/divecoaster/bmdivetie_medium_end_best.lwo",
    "dive_large_start": "coasterstyles/divecoaster/bmdivetie_large_start_best.lwo",
    "dive_large_end": "coasterstyles/divecoaster/bmdivetie_large_end_best.lwo",
    "dive_lowered": "coasterstyles/divecoaster/bmdivetie_lowered_best.lwo",
    "dive_lowered_start": "coasterstyles/divecoaster/bmdivetie_lowered_start_best.lwo",
    "dive_lowered_end": "coasterstyles/divecoaster/bmdivetie_lowered_end_best.lwo",
    # Intamin
    "int_2t": "coasterstyles/int_hyper/int_2t_best.lwo",
    "int_2t_start": "coasterstyles/int_hyper/int_2t_start_best.lwo",
    "int_2t_end": "coasterstyles/int_hyper/int_2t_end_best.lwo",
    "int_3t": "coasterstyles/int_hyper/int_3t_best.lwo",
    "int_3t_start": "coasterstyles/int_hyper/int_3t_start_best.lwo",
    "int_3t_end": "coasterstyles/int_hyper/int_3t_end_best.lwo",
    "int_4t": "coasterstyles/int_hyper/int_4t_best.lwo",
    "int_4t_start": "coasterstyles/int_hyper/int_4t_start_best.lwo",
    "int_4t_end": "coasterstyles/int_hyper/int_4t_end_best.lwo",
    "int_rocket": "coasterstyles/int_doublespine/int_rocket_tie2_best.lwo",
    "int_rocket_aux": "coasterstyles/int_doublespine/int_rocket_tie2_auxpipe_best.lwo",
    "int_rocket_single_start": "coasterstyles/int_doublespine/int_rocket_tie2_single_start_best.lwo",
    "int_rocket_double_start": "coasterstyles/int_doublespine/int_rocket_tie2_double_start_best.lwo",
    # Gerstlauer
    "gerst1200": "coasterstyles/gerstlauer/tie1200_best.lwo",
    "gerst1200_start": "coasterstyles/gerstlauer/tie1200_start_best.lwo",
    "gerst1200_end": "coasterstyles/gerstlauer/tie1200_end_best.lwo",
    "gerst1200_3t": "coasterstyles/gerstlauer/gerst_1200_3tube_best.lwo",
    "gerst1200_3t_start": "coasterstyles/gerstlauer/gerst_1200_3tube_start_best.lwo",
    "gerst1200_3t_end": "coasterstyles/gerstlauer/gerst_1200_3tube_end_best.lwo",
    "gerst1200_modern_start": "coasterstyles/gerst_track_1200_modern/start_tie_best.lwo",
    "gerst800": "coasterstyles/gerstlauer/tie800_best.lwo",
    "gerst800_start": "coasterstyles/gerstlauer/tie800_start_best.lwo",
    "gerst800_end": "coasterstyles/gerstlauer/tie800_end_best.lwo",
    "gerst800_3t": "coasterstyles/gerstlauer/gerst_800_3tube_best.lwo",
    "gerst800_3t_start": "coasterstyles/gerstlauer/gerst_800_3tube_start_best.lwo",
    "gerst800_3t_end": "coasterstyles/gerstlauer/gerst_800_3tube_end_best.lwo",
    # Vekoma / Arrow corkscrew family
    "vek_tie": "coasterstyles/corkscrew/vekoma_tie_best.lwo",
    "vek_double": "coasterstyles/corkscrew/vekoma_double_spine_tie_best.lwo",
    "mk900": "coasterstyles/vek_trackstyles/mk900_tie_best.lwo",
    "minetrain": "coasterstyles/vek_minetrain/minetrain_tie_best.lwo",
    "minetrain_cbeam": "coasterstyles/vek_minetrain/minetrain_tie_cbeam_best.lwo",
    "minetrain_cbeam_start": "coasterstyles/vek_minetrain/minetrain_tie_cbeam_start.lwo",
    # Mack
    "mack": "coasterstyles/mack_launch/macklaunch_tie_best.lwo",
    "mack_start": "coasterstyles/mack_launch/macklaunch_tie_start_best.lwo",
    "mack_end": "coasterstyles/mack_launch/macklaunch_tie_end_best.lwo",
    # Maurer
    "xcar": "coasterstyles/maurer_trackstyles/xcar_tie_best.lwo",
    "xcar_start": "coasterstyles/maurer_trackstyles/xcar_tie_start_best.lwo",
    "xcar_end": "coasterstyles/maurer_trackstyles/xcar_tie_end_best.lwo",
    "evo_3t_start": "coasterstyles/maurer_trackstyles/evo_tie_3t_start_best.lwo",
    "mspin": "coasterstyles/maurer_trackstyles/mspintie_standard_best.lwo",
    "mspin_start": "coasterstyles/maurer_trackstyles/mspintie_start_best.lwo",
    "mspin_end": "coasterstyles/maurer_trackstyles/mspintie_end_best.lwo",
    # Premier
    "premier": "coasterstyles/premier_limlaunched/tie_best.lwo",
    "premier_start": "coasterstyles/premier_limlaunched/tie_start.lwo",
    "premier_end": "coasterstyles/premier_limlaunched/tie_end.lwo",
    # Schwarzkopf
    "schwarz": "coasterstyles/schwarzkopf/crosstie_best.lwo",
    "schwarz_even": "coasterstyles/schwarzkopf/crosstie_even_best.lwo",
    "schwarz_start": "coasterstyles/schwarzkopf/crosstie_start_best.lwo",
    "schwarz_end": "coasterstyles/schwarzkopf/crosstie_end_best.lwo",
    "schwarz_box": "coasterstyles/schwarzkopf/crosstie_boxtube_best.lwo",
    # Zamperla
    "zamtwist": "coasterstyles/zamperla_trackstyles/zamtwist_tie.lwo",
    "zamtwist_start": "coasterstyles/zamperla_trackstyles/zamtwist_tie_start.lwo",
    "zamtwist_end": "coasterstyles/zamperla_trackstyles/zamtwist_tie_end.lwo",
    # Wooden / RMC
    "wood": "coasterstyles/misc/wood_tie.lwo",
    "wood_gci": "coasterstyles/misc/wood_tie_gci.lwo",
    "ironhorse": "coasterstyles/rmc/rmc_ties/ironhorse_best.lwo",
    "rmc_box_start": "coasterstyles/rmc/rmc_ties/RMCTIEbox_best_start.lwo",
    "rmc_box_end": "coasterstyles/rmc/rmc_ties/RMCTIEbox_best_end.lwo",
}
TIES_3DS = {
    "susp": "coasterstyles/suspended/suspended_tie_best.3DS",
    "4d_v1": "coasterstyles/4d/crossties/4DTIE_ver1_best.3DS",
    "4d_v1_start": "coasterstyles/4d/crossties/4DTIE_ver1_start_best.3DS",
    "4d_v1_end": "coasterstyles/4d/crossties/4DTIE_ver1_end_best.3DS",
    "4d_v2": "coasterstyles/4d/crossties/4DTIE_ver2_best.3DS",
    "4d_v3": "coasterstyles/4d/crossties/4DTIE_ver3_best.3DS",
    "4d_v3_start": "coasterstyles/4d/crossties/4DTIE_ver3_start_best.3DS",
    "4d_v3_end": "coasterstyles/4d/crossties/4DTIE_ver3_end_best.3DS",
    "4d_v4": "coasterstyles/4d/crossties/4DTIE_ver4_best.3DS",
    "4d_v4_start": "coasterstyles/4d/crossties/4DTIE_ver4_start_best.3DS",
    "4d_v4_end": "coasterstyles/4d/crossties/4DTIE_ver4_end_best.3DS",
}
RASCS = ["4dcon_double", "4dcon_single", "bmcon0", "corkcon0", "gerst_1200_2t", "gerst_1200_3t",
         "int_900_2t", "int_900_3t", "int_900_4t", "schwarz_900_2t", "suspended_horz"] + \
        ["bmcon_%s_%d" % (k, d) for k in ("vert", "horz", "dive_vert", "dive_horz") for d in (20, 30, 42)]
# connectors that live with their track style
RASCS_EXTRA = {
    "ironhorse_rasc1_left": "coasterstyles/rmc/rmc_ties/ironhorse_rasc1_left.lwo",
    "ironhorse_rasc1_right": "coasterstyles/rmc/rmc_ties/ironhorse_rasc1_right.lwo",
    "ironhorse_rasc2": "coasterstyles/rmc/rmc_ties/ironhorse_rasc2.lwo",
}
FOOTERS = {
    "steel_base": "coaster/footers/new20/steel-round-base-lod1.lwo",
    "steel_main": "coaster/footers/new20/steel-round-main-lod1.lwo",
    "steel_top": "coaster/footers/new20/steel-round-top-lod1.lwo",
    "old_base": "coaster/footers/expnl16/footer-base-normal.lwo",
    "old_main": "coaster/footers/expnl16/footer-normal.lwo",
    "old_top_box": "coaster/footers/expnl16/top-box-normal.lwo",
    "tri_fin": "coaster/footers/expnl16/tri_fin.lwo",
    "tri_fin_arrow": "coaster/footers/expnl16/tri_fin_arrow.lwo",
    "wood_round_main": "coaster/footers/new20/wood-round-main-lod1.lwo",
    "wood_round_base": "coaster/footers/new20/wood-round-base-lod1.lwo",
    "wood_square_main": "coaster/footers/new20/wood-square-main-lod1.lwo",
    "wood_square_base": "coaster/footers/new20/wood-square-base-lod1.lwo",
    "wood_mount": "coaster/footers/new20/wood-footer-mount.lwo",
}


def bolt_meshes():
    d = pickle.load(open(BOLTS, "rb"))
    pieces = d["pieces"]
    smin = min(p[0][:, 0].min() for p in pieces)
    smax = max(p[0][:, 0].max() for p in pieces)
    shift = -(smin + smax) / 2.0

    def mesh(plist, fn):
        V, P = [], []
        for pv, pf in plist:
            base = len(V)
            V.extend(fn(np.asarray(pv, dtype=float)).tolist())
            P.extend([[base + int(a), base + int(b), base + int(c)] for a, b, c in pf])
        out = pack(V, P, [0] * len(P))
        out["slots"] = ["steel"]
        return out

    # capture is (s, l, u) -> stored (l, u, s), proper rotation
    flange = mesh(pieces, lambda V: np.c_[V[:, 1], V[:, 2], V[:, 0] + shift])
    one = d["one"]
    one = sorted(one, key=lambda p: np.asarray(p[0])[:, 0].mean())
    head_side = [p for p in one if np.asarray(p[0])[:, 0].mean() < 0]
    nut_side = [p for p in one if np.asarray(p[0])[:, 0].mean() >= 0]

    def centred(V):
        c = np.asarray(V, dtype=float)
        return c
    # axis of the bolt is s. Centre the cross-section on the bolt axis.
    allv = np.vstack([np.asarray(p[0], dtype=float) for p in one])
    cl, cu = np.median(allv[:, 1]), np.median(allv[:, 2])
    # head: seat plane at s = -0.035 facing -s. Marker frame: z = outward normal, seat at z = 0.
    bolt = mesh(head_side, lambda V: np.c_[V[:, 1] - cl, -(V[:, 2] - cu), -(V[:, 0]) - 0.035])
    nut = mesh(nut_side, lambda V: np.c_[V[:, 1] - cl, V[:, 2] - cu, V[:, 0] - 0.044])
    return flange, bolt, nut


def _hex_prism(r, z0, z1, n=6, rot=np.pi / 6):
    a = np.linspace(0, 2 * np.pi, n, endpoint=False) + rot
    ring = np.c_[r * np.cos(a), r * np.sin(a)]
    V = np.vstack([np.c_[ring, np.full(n, z0)], np.c_[ring, np.full(n, z1)]])
    P = [list(range(n))[::-1], list(range(n, 2 * n))]
    P += [[i, (i + 1) % n, n + (i + 1) % n, n + i] for i in range(n)]
    return V, P


def _merge(parts):
    V, P = [], []
    for pv, pp in parts:
        base = len(V)
        V.extend(np.asarray(pv).tolist())
        P.extend([[base + i for i in f] for f in pp])
    out = pack(V, P, [0] * len(P))
    out["slots"] = ["steel"]
    return out


def procedural_bolts():
    """Plain hex bolt head / nut in the marker frame (seat at z = 0, axis +z)."""
    bolt = _merge([_hex_prism(0.04, 0.0, 0.022), _hex_prism(0.017, 0.022, 0.033, n=12, rot=0)])
    nut = _merge([_hex_prism(0.022, 0.003, 0.02), _hex_prism(0.011, 0.02, 0.03, n=12, rot=0)])
    return bolt, nut


def main():
    global VFS, BOLTS
    ap = argparse.ArgumentParser(description="Build the NL2 asset pack from your own NoLimits 2 VFS dump")
    ap.add_argument("--vfs", default=VFS, help="folder containing coasterstyles/ and coaster/ (vfs/data)")
    ap.add_argument("--bolts", default=BOLTS, help="optional captured flange bolt set (.pkl)")
    ap.add_argument("--list", metavar="TXT", help="write the game files this script needs (the input list for "
                    "nl2vfsdump.dll, i.e. nl2vfsdump.txt) and exit")
    args = ap.parse_args()
    if args.list:
        rels = list(TIES.values()) + list(TIES_3DS.values()) + ["coaster/rascs/%s.lwo" % k for k in RASCS] + \
            list(RASCS_EXTRA.values()) + list(FOOTERS.values())
        with open(args.list, "w") as fh:
            fh.write("\n".join("base:data/" + r for r in rels) + "\n")
        print("wrote", args.list, len(rels), "paths")
        return
    VFS, BOLTS = args.vfs, args.bolts
    if not VFS or not os.path.isdir(os.path.join(VFS, "coasterstyles")):
        ap.error("--vfs must point at the dumped vfs/data folder (it must contain coasterstyles/)")
    assets = {"ties": {}, "rascs": {}, "footers": {}, "bolts": {}}
    for k, rel in TIES.items():
        try:
            assets["ties"][k] = load_lwo_mesh(rel)
        except FileNotFoundError:
            print("missing", rel)
    for k, rel in TIES_3DS.items():
        try:
            assets["ties"][k] = load_3ds_mesh(rel)
        except FileNotFoundError:
            print("missing", rel)
    for k in RASCS:
        assets["rascs"][k] = load_lwo_mesh("coaster/rascs/%s.lwo" % k)
    for k, rel in RASCS_EXTRA.items():
        assets["rascs"][k] = load_lwo_mesh(rel)
    for k, rel in FOOTERS.items():
        assets["footers"][k] = load_lwo_mesh(rel)
    if BOLTS and os.path.isfile(BOLTS):
        flange, bolt, nut = bolt_meshes()
        assets["bolts"] = {"bm_flange": flange, "bolt": bolt, "nut": nut}
    else:
        bolt, nut = procedural_bolts()
        assets["bolts"] = {"bolt": bolt, "nut": nut}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with gzip.open(OUT, "wt", encoding="utf-8") as fh:
        json.dump(assets, fh, separators=(",", ":"))
    print("wrote", OUT, os.path.getsize(OUT), "bytes;",
          {k: len(v) for k, v in assets.items()})


if __name__ == "__main__":
    main()
