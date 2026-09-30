"""NoLimits 2 track styles.

Geometry constants were read out of the NoLimits 2 executable. Each style's slot-2 "build tubes"
function gives the rails, the extra tubes and their radii. The constructors give the spine options
and tie spacing. Tie, flange and connector model keys refer to the optional personal asset pack
(assets/); without it, or with Procedural Parts Only, procedural.py generates original parts instead.

Local track frame used everywhere: x = LEFT, y = UP, z = FORWARD (metres).
Parts:
  ("tube", x, y, r)                 swept circle
  ("box",  x0, x1, y0, y1)          swept rectangle
  ("rails",)                        the two running rails at x = +-gauge/2, radius rail_r
Ties dict: mid / start / end = asset keys, or None for a generated tie.
`exact` marks options built from the game's own tie models *and* extracted constants.
"""

EXACT, APPROX = True, False


def tube(x, y, r):
    return ("tube", float(x), float(y), float(r))


def box(x0, x1, y0, y1):
    return ("box", float(x0), float(x1), float(y0), float(y1))


def opt(label, spacing, parts=(), mid=None, start=None, end=None, attach=None, flange=12.0,
        exact=APPROX, flange_bolts=None, tie_scale_x=1.0, spine_colour_parts=None):
    return dict(label=label, spacing=spacing, parts=list(parts), mid=mid, start=start, end=end,
                attach=attach, flange=flange, exact=exact, flange_bolts=flange_bolts,
                tie_scale_x=tie_scale_x)


def style(key, label, group, gauge, rail_r, options, rails=None, rasc="generic", extra=(),
          wooden=False):
    return dict(key=key, label=label, group=group, gauge=gauge, rail_r=rail_r, options=options,
                rails=rails, rasc=rasc, extra=list(extra), wooden=wooden)


BM_BOX_TOP = -0.176
STYLES = [
    # ------------------------------------------------------------------ B&M
    style("bm", "B&M Sitdown / Hyper / Inverted / Flyer / Wing", "B&M", 1.2192, 0.06985, [
        opt("Standard Box", 1.2, [box(-0.26, 0.26, -0.704, BM_BOX_TOP)], "bm_std", "bm_start", "bm_end",
            attach=-0.7, flange=12.09, exact=EXACT, flange_bolts=("bm_flange", 0.0)),
        opt("Medium Box", 1.2, [box(-0.26, 0.26, -0.974, BM_BOX_TOP)], "bm_std", "bm_larger_start",
            "bm_larger_end", attach=-0.98, flange=12.09, exact=EXACT, flange_bolts=("bm_flange", -0.27)),
        opt("Large Box", 1.2, [box(-0.26, 0.26, -1.374, BM_BOX_TOP)], "bm_std", "bm_largest_start",
            "bm_largest_end", attach=-1.38, flange=12.09, exact=EXACT, flange_bolts=("bm_flange", -0.67)),
        opt("Lowered Box", 1.2, [box(-0.26, 0.26, -1.104, -0.576)], "bm_lowered", "bm_lowered_start",
            "bm_lowered_end", attach=-1.1, flange=12.09),
        opt("I-Beam", 1.2, [box(-0.26, 0.26, -0.21, BM_BOX_TOP), box(-0.025, 0.025, -0.67, -0.21),
                            box(-0.26, 0.26, -0.704, -0.67)], "bm_std", "bm_start", "bm_end",
            attach=-0.7, flange=12.09, flange_bolts=("bm_flange", 0.0)),
        opt("Lift / Station (lift ties)", 1.2, [box(-0.26, 0.26, -0.704, BM_BOX_TOP)], "bm_lift",
            "bm_start", "bm_end", attach=-0.7, flange=12.09, flange_bolts=("bm_flange", 0.0)),
    ], rasc="bm"),
    style("bmdive", "B&M Dive", "B&M", 1.8288, 0.0762, [
        opt("Standard Box", 1.35, [box(-0.43, 0.43, -1.025, -0.35)], "dive_std", "dive_start", "dive_end",
            attach=-1.03, exact=EXACT),
        opt("Medium Box", 1.35, [box(-0.43, 0.43, -1.194, -0.35)], "dive_std", "dive_medium_start",
            "dive_medium_end", attach=-1.2, exact=EXACT),
        opt("Large Box", 1.35, [box(-0.43, 0.43, -1.363, -0.35)], "dive_std", "dive_large_start",
            "dive_large_end", attach=-1.37, exact=EXACT),
        opt("Lowered Box", 1.35, [box(-0.43, 0.43, -1.152, -0.35)], "dive_lowered", "dive_lowered_start",
            "dive_lowered_end", attach=-1.16, exact=EXACT),
    ], rasc="bmdive"),
    # ------------------------------------------------------------------ Intamin
    style("int", "Intamin Hyper / Mega / Impulse / Rocket (900)", "Intamin", 0.9, 0.06985, [
        opt("2 Pipe", 1.0, [], "int_2t", "int_2t_start", "int_2t_end", attach=-0.08, exact=EXACT),
        opt("3 Pipe", 1.0, [tube(0, -0.7794, 0.06985)], "int_3t", "int_3t_start", "int_3t_end",
            attach=-0.8594, exact=EXACT),
        opt("4 Pipe", 1.0, [tube(-0.45, -0.9, 0.06985), tube(0.45, -0.9, 0.06985)], "int_4t",
            "int_4t_start", "int_4t_end", attach=-0.98, exact=EXACT),
        opt("Modern Single Spine", 0.78, [tube(0, -0.28, 0.2)], "int_rocket", "int_rocket_single_start",
            None, attach=-0.5),
        opt("Modern Double Spine", 0.78, [tube(0, -0.28, 0.2), tube(0, -0.98, 0.1)], "int_rocket",
            "int_rocket_double_start", None, attach=-1.08),
    ], rasc="int"),
    # ------------------------------------------------------------------ Gerstlauer
    style("gerst1200", "Gerstlauer Euro-Fighter / Infinity (1200)", "Gerstlauer", 1.2, 0.08, [
        opt("2 Pipe", 0.75, [], "gerst1200", "gerst1200_start", "gerst1200_end", attach=-0.1, exact=EXACT),
        opt("3 Pipe", 0.72, [tube(0, -0.725, 0.08)], "gerst1200_3t", "gerst1200_3t_start",
            "gerst1200_3t_end", attach=-0.8, exact=EXACT),
        opt("Modern 2 Pipe", 1.0, [], "gerst1200", "gerst1200_modern_start", None, attach=-0.1),
        opt("Modern 3 Pipe", 1.0, [tube(0, -0.725, 0.08)], "gerst1200_3t", "gerst1200_modern_start",
            None, attach=-0.8),
    ], rasc="gerst"),
    style("gerst800", "Gerstlauer Bobsled / Family (800)", "Gerstlauer", 0.8, 0.07, [
        opt("2 Pipe", 0.6, [], "gerst800", "gerst800_start", "gerst800_end", attach=-0.08, exact=EXACT),
        opt("3 Pipe", 0.95, [tube(0, -0.52, 0.07)], "gerst800_3t", "gerst800_3t_start", "gerst800_3t_end",
            attach=-0.59, exact=EXACT),
    ], rasc="gerst"),
    style("gerstair", "Gerstlauer Airtime / Infinity 3-pipe (920)", "Gerstlauer", 0.92, 0.08, [
        opt("3 Pipe", 1.0, [tube(0, -0.8, 0.08)], attach=-0.88),
        opt("3 Pipe (heavy)", 1.0, [tube(0, -0.8, 0.1)], attach=-0.9),
    ]),
    style("gerstiic", "Gerstlauer Inverted (IIC)", "Gerstlauer", 1.0, 0.08, [
        opt("2 Pipe", 0.9, [], attach=0.1),
        opt("3 Pipe", 0.9, [tube(0, 0.8, 0.08)], attach=0.88),
    ]),
    # ------------------------------------------------------------------ Mack
    style("macklaunch", "Mack Launch / Mega", "Mack", 1.06, 0.07, [
        opt("3 Pipe", 1.04, [tube(0, -0.75, 0.07)], "mack", "mack_start", "mack_end", attach=-0.82,
            exact=EXACT),
    ], rasc="int"),
    style("mackstryker", "Mack Stryker / Big Dipper", "Mack", 1.2, 0.07, [
        opt("3 Pipe", 1.04, [tube(0, -0.75, 0.07)], "mack", "mack_start", "mack_end", attach=-0.82,
            tie_scale_x=0.6 / 0.53),
    ], rasc="int"),
    # ------------------------------------------------------------------ Maurer
    style("mspin", "Maurer Spinning / Wild Mouse", "Maurer", 0.68, 0.05, [
        opt("2 Pipe", 0.4, [], "mspin", "mspin_start", "mspin_end", attach=-0.06, exact=EXACT),
    ]),
    style("xcar", "Maurer X-Car / Sky Loop", "Maurer", 1.0, 0.08, [
        opt("Single Spine", 1.0, [tube(0, -0.42, 0.16)], "xcar", "xcar_start", "xcar_end", attach=-0.58,
            exact=EXACT),
    ]),
    style("evo", "Maurer Evo 1000", "Maurer", 1.0, 0.08, [
        opt("3 Pipe", 1.0, [tube(0, -0.87, 0.115)], None, "evo_3t_start", None, attach=-0.98),
    ]),
    style("xtrain", "Maurer X-Train", "Maurer", 1.3, 0.1, [
        opt("Single Spine", 1.0, [tube(0, -0.6, 0.39)], attach=-0.99),
    ]),
    # ------------------------------------------------------------------ Premier
    style("premier", "Premier LIM Launched", "Premier", 0.9144, 0.06604, [
        opt("Single Spine", 1.2, [tube(0, -0.35, 0.14224)], "premier", "premier_start", "premier_end",
            attach=-0.49, exact=EXACT),
    ]),
    # ------------------------------------------------------------------ Schwarzkopf
    style("schwarz", "Schwarzkopf Classic / Modern", "Schwarzkopf", 0.9, 0.0635, [
        opt("3 Pipe", 1.3, [tube(0, -0.35, 0.1905)], "schwarz", "schwarz_start", "schwarz_end",
            attach=-0.54, exact=EXACT),
        opt("Looping Box Spine", 1.1, [box(-0.34, 0.34, -0.83, -0.157)], "schwarz_box", "schwarz_start",
            "schwarz_end", attach=-0.83),
        opt("2 Pipe", 0.8, [], "schwarz_even", "schwarz_start", "schwarz_end", attach=-0.07),
        opt("3 Pipe (Transportable)", 1.3, [tube(0, -0.35, 0.1905)], "schwarz", "schwarz_start",
            "schwarz_end", attach=-0.54),
    ], rasc="schwarz"),
    # ------------------------------------------------------------------ Arrow / Vekoma corkscrew
    style("cork", "Arrow Corkscrew / Looper, Vekoma SLC & Flyer", "Arrow / Vekoma", 1.2192, 0.06731, [
        opt("Single Spine", 1.25, [tube(0, -0.6, 0.16193)], "vek_tie", None, None, attach=-0.95,
            exact=EXACT),
        opt("Double Spine", 1.25, [tube(-0.22, -0.6, 0.16193), tube(0.22, -0.6, 0.16193)], "vek_double",
            None, None, attach=-0.95, exact=EXACT),
    ], rasc="cork"),
    style("arrowsusp", "Arrow Suspended", "Arrow / Vekoma", 0.6096, 0.05715, [
        opt("Single Spine", 1.25, [tube(0, 0.41, 0.16193)], "susp", None, None, attach=0.57, exact=EXACT),
    ], rasc="susp"),
    style("arrow4d", "Arrow 4th Dimension", "Arrow / Vekoma", 1.2192, 0.0762, [
        opt("Single Spine", 1.8, [tube(0, -1.2954, 0.254)], "4d_v1", "4d_v1_start", "4d_v1_end",
            attach=-1.55, exact=EXACT),
        opt("Single Spine Low Stress", 2.0, [tube(0, -1.2954, 0.254)], "4d_v2", "4d_v1_start", "4d_v1_end",
            attach=-1.55, exact=EXACT),
        opt("Double Spine", 1.8, [tube(-0.4572, -1.2954, 0.254), tube(0.4572, -1.2954, 0.254)], "4d_v3",
            "4d_v3_start", "4d_v3_end", attach=-1.55, exact=EXACT),
        opt("Double Spine High Stress", 1.2, [tube(-0.4572, -1.2954, 0.254), tube(0.4572, -1.2954, 0.254)],
            "4d_v4", "4d_v4_start", "4d_v4_end", attach=-1.55, exact=EXACT),
    ], extra=[tube(1.1176, 0, 0.0762), tube(-1.1176, 0, 0.0762)], rasc="4d"),
    # ------------------------------------------------------------------ Vekoma
    style("mk900", "Vekoma MK-900 (Junior / Boomerang)", "Vekoma", 0.9, 0.065, [
        opt("Single Spine", 1.0, [tube(0, -0.3, 0.17)], "mk900", None, None, attach=-0.47, exact=EXACT),
    ]),
    style("mk906", "Vekoma MK-906", "Vekoma", 0.9, 0.07, [
        opt("Single Spine", 1.0, [tube(0, -0.3, 0.16)], attach=-0.46),
    ]),
    style("mk1100", "Vekoma MK-1100 (old)", "Vekoma", 1.1, 0.07, [
        opt("Single Spine", 1.0, [tube(0, -0.3, 0.2)], attach=-0.5),
    ]),
    style("mk1100v2", "Vekoma MK-1100 V2 (modern)", "Vekoma", 1.1, 0.07, [
        opt("Standard", 1.0, [tube(0, -0.3, 0.2)], attach=-0.5),
        opt("Thick", 1.0, [tube(0, -0.35, 0.25)], attach=-0.6),
        opt("C Box Beam", 1.0, [box(-0.2, 0.2, -0.7, -0.15)], attach=-0.7),
    ]),
    style("mk1300", "Vekoma MK-1300", "Vekoma", 1.3, 0.084, [
        opt("Single Spine", 1.0, [tube(0, -0.36, 0.24)], attach=-0.6),
    ]),
    style("mk700", "Vekoma MK-700 (Family)", "Vekoma", 0.7, 0.0635, [
        opt("With Spine", 1.0, [tube(0, -0.28, 0.108)], attach=-0.39),
        opt("No Spine", 1.0, [], attach=-0.07),
    ]),
    style("mk711", "Vekoma MK-711 Launch", "Vekoma", 0.7, 0.056, [
        opt("Single Spine", 1.0, [tube(0, -0.45, 0.1)], attach=-0.55),
    ]),
    style("minetrain", "Vekoma Mine Train", "Vekoma", 0.9, 0.06, [
        opt("Standard", 1.0, [], "minetrain", None, None, attach=-0.5, exact=EXACT),
        opt("No Planks", 1.0, [], None, None, None, attach=-0.1),
        opt("C Beam", 1.0, [box(-0.25, 0.25, -0.655, -0.38)], "minetrain_cbeam", "minetrain_cbeam_start",
            None, attach=-0.66, exact=EXACT),
    ]),
    # ------------------------------------------------------------------ Zamperla
    style("zam800", "Zamperla Junior 800", "Zamperla", 0.8, 0.061, [
        opt("3 Pipe", 1.0, [tube(0, -0.3, 0.125)], attach=-0.43),
    ]),
    style("zammoto", "Zamperla MotoGP", "Zamperla", 0.9, 0.07, [
        opt("2 Pipe", 1.0, [], attach=-0.08),
    ]),
    style("zamspin", "Zamperla Spinning / Twister 800", "Zamperla", 0.8, 0.061, [
        opt("2 Pipe", 0.8, [], "zamtwist", "zamtwist_start", "zamtwist_end", attach=-0.1, exact=EXACT),
    ]),
    style("zambolt", "Zamperla Thunderbolt 1300", "Zamperla", 1.3, 0.08, [
        opt("Single Spine", 1.0, [tube(0, -0.45, 0.2)], attach=-0.65),
    ]),
    # ------------------------------------------------------------------ Zierer
    style("esc", "Zierer ESC 900", "Zierer", 0.896, 0.0825, [
        opt("3 Pipe", 1.0, [tube(0, -0.779, 0.081)], attach=-0.86),
    ]),
    style("force", "Zierer Force 700", "Zierer", 0.7, 0.0538, [
        opt("Single Spine", 1.0, [tube(0, -0.4, 0.15)], attach=-0.55),
    ]),
    style("tower", "Zierer Tower 1200", "Zierer", 1.2, 0.08665, [
        opt("3 Pipe", 1.0, [tube(0, -1.04, 0.0854)], attach=-1.13),
    ]),
    # ------------------------------------------------------------------ Wooden & hybrids
    style("wood", "Wooden (classic)", "Wooden", 1.1, 0.0, [
        opt("Standard", 0.6096, [box(-0.6985, -0.4191, -0.245, 0.038), box(0.4191, 0.6985, -0.245, 0.038)],
            "wood", None, None, attach=-0.374, exact=EXACT),
    ], rasc="wood", wooden=True),
    style("gci", "GCI / PTC / Timberliner (wood)", "Wooden", 1.1, 0.0, [
        opt("Standard", 0.6096, [box(-0.6985, -0.4191, -0.245, 0.038), box(0.4191, 0.6985, -0.245, 0.038)],
            "wood_gci", None, None, attach=-0.374, exact=EXACT),
    ], rasc="wood", wooden=True),
    style("rmc", "RMC I-Box / Topper (hybrid)", "Wooden", 1.1, 0.0, [
        opt("I-Box", 0.6096, [box(-0.723, -0.49, -0.284, 0.035), box(0.49, 0.723, -0.284, 0.035)],
            "ironhorse", "rmc_box_start", "rmc_box_end", attach=-0.42, exact=EXACT),
    ], rasc="rmc", wooden=True),
    # ------------------------------------------------------------------ Misc
    style("dragster", "Intamin Accelerator / BTS Spike Dragster", "Other", 0.9, 0.08, [
        opt("Standard", 1.0, [tube(0, 0, 0.08), tube(0, -0.5, 0.053)], attach=-0.56),
    ]),
    style("spikevert", "BTS Spike Vertical", "Other", 1.0, 0.08, [
        opt("Standard", 1.0, [tube(0, 0, 0.08)], attach=-0.1),
    ]),
    style("monorail", "Monorail (approx.)", "Other", 0.0, 0.0, [
        opt("Box Beam", 1.0, [box(-0.35, 0.35, -0.9, 0.0)], attach=-0.9),
    ]),
    style("railroad", "Railroad (approx.)", "Other", 1.435, 0.0, [
        opt("Standard", 0.6, [box(-0.7535, -0.6815, -0.15, 0.0), box(0.6815, 0.7535, -0.15, 0.0)],
            attach=-0.35),
    ]),
    style("custom", "Custom (use Custom settings)", "Other", 1.2, 0.07, [
        opt("Custom", 1.0, [], attach=-0.5),
    ]),
]

BY_KEY = {s["key"]: s for s in STYLES}


def style_items():
    return [(s["key"], s["label"], s["group"]) for s in STYLES]


def option_items(style_key):
    s = BY_KEY.get(style_key, STYLES[0])
    return [(str(i), o["label"] + ("" if o["exact"] else "  (approx.)"), "") for i, o in enumerate(s["options"])]


RASC_MODELS = {
    # B&M style connectors: plate at the subnode, transition piece up into the spine
    "bm": dict(vert="bmcon_vert_%d", horz="bmcon_horz_%d", plate="bmcon0"),
    "bmdive": dict(vert="bmcon_dive_vert_%d", horz="bmcon_dive_horz_%d", plate="bmcon0"),
    # track-clamp connectors placed like a tie, with a stub down to the subnode
    "int": dict(clamp="int_900_3t", plate="corkcon0"),
    "gerst": dict(clamp="gerst_1200_2t", plate="corkcon0"),
    "schwarz": dict(clamp="schwarz_900_2t", plate="corkcon0"),
    "cork": dict(plate="corkcon0"),
    "4d": dict(plate="4dcon_single"),
    "susp": dict(clamp="suspended_horz", plate="corkcon0"),
    "generic": dict(plate="corkcon0"),
    # RMC: steel shoes under each I-box rail, placed like a tie; they sit on the cap channels
    "rmc": dict(tie=("ironhorse_rasc1_left", "ironhorse_rasc1_right")),
    # classic wood: the track sits directly on the ledgers
    "wood": dict(tie=()),
}
