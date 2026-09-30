"""UI, properties and operators for the NL2 Track Builder."""
import os
import time

import bpy
from bpy.props import (BoolProperty, EnumProperty, FloatProperty, FloatVectorProperty, IntProperty,
                       PointerProperty, StringProperty)

from . import blender_build as bb
from . import core
from . import styles as st
from .version import VERSION

_OPT_CACHE = {}


def _style_items(self, context):
    return _STYLE_ITEMS


_STYLE_ITEMS = st.style_items()


def _option_items(self, context):
    key = self.style
    if key not in _OPT_CACHE:
        _OPT_CACHE[key] = st.option_items(key)
    return _OPT_CACHE[key]


def _colour_update(self, context):
    bb.update_materials(self)


def _colour(name, default):
    return FloatVectorProperty(name=name, subtype="COLOR_GAMMA", size=3, min=0, max=1, default=default,
                               update=_colour_update)


class NL2TB_Props(bpy.types.PropertyGroup):
    csv_path: StringProperty(name="Spline CSV", subtype="FILE_PATH",
                             description="NoLimits 2 'Center Of Rails' spline export (CSV)")
    xml_path: StringProperty(name="Supports XML", subtype="FILE_PATH",
                             description="NoLimits 2 supports export (XML)")
    style: EnumProperty(name="Track Style", items=_style_items)
    option: EnumProperty(name="Spine", items=_option_items)
    inverted: BoolProperty(name="Inverted", default=False,
                           description="Roll the track style 180 degrees (inverted / flying / suspended rides "
                                       "whose export frame points towards the train)")
    close: EnumProperty(name="Closed Circuit", default="AUTO", items=[
        ("AUTO", "Auto", "Close the loop if the end of the spline leads back into the start"),
        ("ON", "Closed", "Always bridge the end back to the start"),
        ("OFF", "Open", "Leave the ends open")])
    tie_spacing: FloatProperty(name="Tie Spacing", default=0.0, min=0.0, max=10.0, unit="LENGTH",
                               description="0 = style default")
    flange_length: FloatProperty(name="Flange Interval", default=0.0, min=0.0, max=100.0, unit="LENGTH",
                                 description="Target track segment length between flanges (0 = style default)")
    gauge: FloatProperty(name="Gauge", default=0.0, min=0.0, max=5.0, unit="LENGTH",
                         description="Rail centre spacing override (0 = style default)")
    rail_r: FloatProperty(name="Rail Radius", default=0.0, min=0.0, max=0.5, unit="LENGTH",
                          description="Rail radius override (0 = style default)")
    custom_spine: EnumProperty(name="Custom Spine", default="TUBE", items=[
        ("NONE", "None", ""), ("TUBE", "Tube", ""), ("BOX", "Box", "")])
    custom_spine_y: FloatProperty(name="Spine Centre Y", default=-0.5, min=-5, max=5, unit="LENGTH")
    custom_spine_size: FloatProperty(name="Spine Radius / Half Height", default=0.15, min=0.01, max=2,
                                     unit="LENGTH")
    custom_spine_width: FloatProperty(name="Box Half Width", default=0.25, min=0.01, max=2, unit="LENGTH")
    colour_mode: EnumProperty(name="Spine Colour Mode", default="PLAIN", items=[
        ("PLAIN", "Plain", ""), ("TOP", "Top Accented", ""), ("TOPBOTTOM", "Top/Bottom Accented", ""),
        ("STRIPE", "Stripe", ""), ("BOTTOM", "Bottom Accented", "")])
    tube_sides: IntProperty(name="Tube Sides", default=12, min=6, max=48)
    ties: BoolProperty(name="Ties", default=True)
    flanges: BoolProperty(name="Flanges", default=True)
    bolts: BoolProperty(name="Bolts", default=True,
                        description="Add bolts and nuts as Geometry-Nodes instances")
    realize: BoolProperty(name="Realize Bolts", default=False,
                          description="Turn bolt instances into real geometry (heavy)")
    footers: BoolProperty(name="Footers", default=True)
    connectors: BoolProperty(name="Track Connectors", default=True)
    procedural: BoolProperty(name="Procedural Parts Only", default=False,
                             description="Generate ties, connectors, footers and bolts with the add-on's own "
                                         "geometry instead of the game asset pack. The whole model is then original "
                                         "(you may sell prints of it). Always on when no asset pack is installed")
    attach: FloatProperty(name="Support Attach Offset", default=0.0, min=-5, max=5, unit="LENGTH",
                          description="Distance below the rails where connectors meet the spine "
                                      "(0 = style default)")
    track_index: IntProperty(name="Support Track Index", default=-1, min=-1, max=64,
                                         description="custom_track_index of the supports that belong to this spline "
                                                     "(-1 = auto, the most common one). Connectors of other track "
                                                     "sections (e.g. transfer track) get a plate only")
    col_rails: _colour("Rails", (0.239, 0.475, 0.643))
    col_ties: _colour("Ties", (0.239, 0.475, 0.643))
    col_spine: _colour("Spine", (0.239, 0.475, 0.643))
    col_accent: _colour("Spine Accent", (0.45, 0.78, 0.18))
    col_supports: _colour("Supports", (0.92, 0.93, 0.93))
    col_concrete: _colour("Concrete", (0.62, 0.62, 0.6))
    col_steel: _colour("Bolts", (0.3, 0.3, 0.32))
    col_metal: _colour("Unpainted Metal", (0.56, 0.58, 0.6))
    col_catwalk: _colour("Catwalk", (0.85, 0.85, 0.83))
    col_handrails: _colour("Handrails", (0.92, 0.93, 0.93))
    last_info: StringProperty(default="")


def _style_and_option(p):
    s = st.BY_KEY.get(p.style, st.STYLES[0])
    try:
        o = dict(s["options"][int(p.option)])
    except (ValueError, IndexError):
        o = dict(s["options"][0])
    if s["key"] == "custom":
        parts = []
        if p.custom_spine == "TUBE":
            parts = [st.tube(0, p.custom_spine_y, p.custom_spine_size)]
        elif p.custom_spine == "BOX":
            parts = [st.box(-p.custom_spine_width, p.custom_spine_width, p.custom_spine_y - p.custom_spine_size,
                            p.custom_spine_y + p.custom_spine_size)]
        o["parts"] = parts
        o["attach"] = p.custom_spine_y - p.custom_spine_size if parts else -0.1
    return s, o


def _params(p):
    return dict(gauge=p.gauge or None, rail_r=p.rail_r or None, tie_spacing=p.tie_spacing or None,
                flange_length=p.flange_length or None, tube_sides=p.tube_sides, ties=p.ties, flanges=p.flanges,
                bolts=p.bolts, footers=p.footers, connectors=p.connectors, attach=p.attach or None,
                colour_mode=p.colour_mode, track_index=p.track_index, procedural=use_procedural(p))


def use_procedural(p):
    return p.procedural or not core.pack_available()


def load_track(p):
    path = bpy.path.abspath(p.csv_path)
    if not os.path.isfile(path):
        raise RuntimeError("Spline CSV not found: %s" % path)
    tr = core.Track.load_csv(path)
    if p.close == "ON" or (p.close == "AUTO" and tr.should_close()):
        tr.close()
    if p.inverted:
        tr.flip()
    return tr


def build(p, what=("track", "supports")):
    t0 = time.time()
    s, o = _style_and_option(p)
    bb.update_materials(p)
    track = load_track(p)
    root, col = bb.output_collections("NL2 " + s["label"].split(" (")[0].split(" /")[0])
    msgs = []
    params = _params(p)
    if "track" in what:
        res = core.build_track(track, s, o, params)
        bb.mesh_object("NL2 Track", res["mesh"], col)
        for key, (asset, inst) in res["instances"].items():
            bb.instancer_object("NL2 Track " + key.replace("_", " ").title(), asset.name, asset, inst, root, col,
                                p.realize)
        msgs.append(res["info"])
    if "supports" in what:
        path = bpy.path.abspath(p.xml_path) if p.xml_path else ""
        if not os.path.isfile(path):
            if "track" not in what:
                raise RuntimeError("Supports XML not found: %s" % path)
            msgs.append("no supports XML - supports skipped")
            p.last_info = "; ".join(msgs) + "  [%.1fs, v%s]" % (time.time() - t0, VERSION)
            return p.last_info
        sup = core.Supports(path)
        res = core.build_supports(track, sup, s, o, params)
        bb.update_materials(p, res["colours"])
        bb.mesh_object("NL2 Supports", res["mesh"], col)
        for key, (asset, inst) in res["instances"].items():
            bb.instancer_object("NL2 " + key.replace("_", " ").title(), asset.name, asset, inst, root, col,
                                p.realize)
        msgs.append(res["info"])
    msgs.append(PARTS_LABEL[params["procedural"]])
    p.last_info = "; ".join(msgs) + "  [%.1fs, v%s]" % (time.time() - t0, VERSION)
    return p.last_info


PARTS_LABEL = {True: "procedural parts only - original model, OK to sell",
               False: "includes game parts - personal use only"}


class NL2TB_OT_build(bpy.types.Operator):
    bl_idname = "nl2tb.build"
    bl_label = "Build"
    bl_description = "Build NL2 track and/or supports"
    bl_options = {"REGISTER", "UNDO"}
    what: EnumProperty(items=[("ALL", "All", ""), ("TRACK", "Track", ""), ("SUPPORTS", "Supports", "")],
                       default="ALL")

    def execute(self, context):
        p = context.scene.nl2tb
        what = {"ALL": ("track", "supports"), "TRACK": ("track",), "SUPPORTS": ("supports",)}[self.what]
        try:
            info = build(p, what)
        except Exception as e:  # report instead of a traceback popup
            self.report({"ERROR"}, str(e))
            return {"CANCELLED"}
        self.report({"INFO"}, info)
        return {"FINISHED"}


class NL2TB_OT_clear(bpy.types.Operator):
    bl_idname = "nl2tb.clear"
    bl_label = "Clear"
    bl_description = "Delete everything built by NL2 Track Builder"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        root = bpy.data.collections.get(bb.COLLECTION)
        if root is not None:
            for c in list(root.children_recursive) + [root]:
                for ob in list(c.objects):
                    bpy.data.objects.remove(ob, do_unlink=True)
            for c in list(root.children_recursive):
                bpy.data.collections.remove(c)
            bpy.data.collections.remove(root)
        for me in list(bpy.data.meshes):
            if me.users == 0 and me.name.startswith("NL2"):
                bpy.data.meshes.remove(me)
        return {"FINISHED"}


class NL2TB_PT_main(bpy.types.Panel):
    bl_label = "NL2 Track Builder"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "NL2"

    def draw(self, context):
        p = context.scene.nl2tb
        lay = self.layout
        lay.label(text="Version %s" % VERSION, icon="INFO")
        box = lay.box()
        box.prop(p, "csv_path")
        box.prop(p, "xml_path")
        box = lay.box()
        box.prop(p, "style")
        box.prop(p, "option")
        s, o = _style_and_option(p)
        if not o["exact"] and not use_procedural(p):
            box.label(text="Approximate style (no game tie model)", icon="INFO")
        if s["key"] == "custom":
            box.prop(p, "custom_spine")
            if p.custom_spine != "NONE":
                box.prop(p, "custom_spine_y")
                box.prop(p, "custom_spine_size")
                if p.custom_spine == "BOX":
                    box.prop(p, "custom_spine_width")
        row = box.row()
        row.prop(p, "inverted")
        row.prop(p, "close", text="")
        box = lay.box()
        if core.pack_available():
            box.prop(p, "procedural")
        else:
            box.label(text="No game asset pack: procedural parts", icon="CHECKMARK")
        proc = use_procedural(p)
        box.label(text=PARTS_LABEL[proc].capitalize(), icon="CHECKMARK" if proc else "ERROR")
        lay.operator("nl2tb.build", text="Build Track + Supports", icon="MOD_CURVE").what = "ALL"
        row = lay.row(align=True)
        row.operator("nl2tb.build", text="Track").what = "TRACK"
        row.operator("nl2tb.build", text="Supports").what = "SUPPORTS"
        row.operator("nl2tb.clear", text="", icon="TRASH")
        if p.last_info:
            for line in p.last_info.split("; "):
                lay.label(text=line)


class NL2TB_PT_detail(bpy.types.Panel):
    bl_label = "Detail"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "NL2"
    bl_parent_id = "NL2TB_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        p = context.scene.nl2tb
        lay = self.layout
        col = lay.column(align=True)
        col.prop(p, "tie_spacing")
        col.prop(p, "flange_length")
        col.prop(p, "gauge")
        col.prop(p, "rail_r")
        col.prop(p, "attach")
        col.prop(p, "track_index")
        col.prop(p, "tube_sides")
        row = lay.row()
        row.prop(p, "ties")
        row.prop(p, "flanges")
        row = lay.row()
        row.prop(p, "bolts")
        row.prop(p, "realize")
        row = lay.row()
        row.prop(p, "footers")
        row.prop(p, "connectors")


class NL2TB_PT_colours(bpy.types.Panel):
    bl_label = "Colours"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "NL2"
    bl_parent_id = "NL2TB_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        p = context.scene.nl2tb
        lay = self.layout
        lay.prop(p, "colour_mode")
        for a in ("col_rails", "col_ties", "col_spine", "col_accent", "col_supports", "col_concrete", "col_steel", "col_metal",
                  "col_catwalk", "col_handrails"):
            lay.prop(p, a)


CLASSES = (NL2TB_Props, NL2TB_OT_build, NL2TB_OT_clear, NL2TB_PT_main, NL2TB_PT_detail, NL2TB_PT_colours)


def register():
    for c in CLASSES:
        bpy.utils.register_class(c)
    bpy.types.Scene.nl2tb = PointerProperty(type=NL2TB_Props)


def unregister():
    del bpy.types.Scene.nl2tb
    for c in reversed(CLASSES):
        bpy.utils.unregister_class(c)
