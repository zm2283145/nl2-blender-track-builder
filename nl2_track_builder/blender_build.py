"""Blender object/material creation for the NL2 Track Builder."""
import math

import bpy
import numpy as np

COLLECTION = "NL2 Track Builder"
SOURCES = "NL2 Instance Sources"
GROUP = "NL2 Instancer"


def srgb_to_linear(c):
    c = np.asarray(c, dtype=float)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


MAT_PROPS = {
    "Rails": ("col_rails", 0.35, 0.35),
    "Ties": ("col_ties", 0.35, 0.4),
    "Spine": ("col_spine", 0.35, 0.4),
    "Spine Accent": ("col_accent", 0.35, 0.4),
    "Supports": ("col_supports", 0.2, 0.45),
    "Concrete": ("col_concrete", 0.0, 0.9),
    "Steel": ("col_steel", 0.8, 0.35),
    "Unpainted Metal": ("col_metal", 0.75, 0.4),
    "Catwalk": ("col_catwalk", 0.0, 0.7),
    "Handrails": ("col_handrails", 0.0, 0.6),
}


def material(name, rgb=None, metallic=0.3, rough=0.45):
    full = "NL2 " + name
    m = bpy.data.materials.get(full)
    if m is None:
        m = bpy.data.materials.new(full)
        m.use_nodes = True
    if rgb is not None:
        lin = srgb_to_linear(rgb)
        col = (float(lin[0]), float(lin[1]), float(lin[2]), 1.0)
        m.diffuse_color = col
        bsdf = m.node_tree.nodes.get("Principled BSDF") if m.node_tree else None
        if bsdf:
            bsdf.inputs["Base Color"].default_value = col
            bsdf.inputs["Metallic"].default_value = metallic
            bsdf.inputs["Roughness"].default_value = rough
    return m


def update_materials(props, extra=None):
    for name, (attr, met, rough) in MAT_PROPS.items():
        material(name, tuple(getattr(props, attr)), met, rough)
    for name, rgb in (extra or {}).items():
        material(name, rgb, 0.3, 0.45)


def collection(name, parent=None):
    col = bpy.data.collections.get(name)
    if col is None:
        col = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(col)
    return col


def remove_object(name):
    ob = bpy.data.objects.get(name)
    if ob is not None:
        data = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
        if data is not None and getattr(data, "users", 1) == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)


def mesh_from_arrays(name, arrays, smooth_angle=35.0):
    V, idx, counts, mats, smooth = arrays
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(V))
    me.vertices.foreach_set("co", V.astype(np.float32).ravel())
    me.loops.add(len(idx))
    me.loops.foreach_set("vertex_index", idx.astype(np.int32))
    me.polygons.add(len(counts))
    starts = np.r_[0, np.cumsum(counts)[:-1]].astype(np.int32)
    me.polygons.foreach_set("loop_start", starts)
    try:
        me.polygons.foreach_set("loop_total", counts.astype(np.int32))
    except (AttributeError, TypeError, RuntimeError):
        pass  # read-only in newer Blender; derived from loop_start
    names = list(dict.fromkeys(mats))
    lookup = {n: i for i, n in enumerate(names)}
    for n in names:
        me.materials.append(material(n))
    me.polygons.foreach_set("material_index", np.array([lookup[m] for m in mats], dtype=np.int32))
    me.update(calc_edges=True)
    me.polygons.foreach_set("use_smooth", smooth.astype(bool))
    if hasattr(me, "set_sharp_from_angle"):
        me.set_sharp_from_angle(angle=math.radians(smooth_angle))
    me.validate(clean_customdata=False)
    return me


def instancer_group(srcob, realize):
    """Geometry-Nodes group that instances `srcob` on the points (rotation / scale from attributes)."""
    name = "%s | %s%s" % (GROUP, srcob.name, " | realized" if realize else "")
    ng = bpy.data.node_groups.get(name)
    if ng is not None:
        return ng
    ng = bpy.data.node_groups.new(name, "GeometryNodeTree")
    ng.interface.new_socket("Geometry", in_out="INPUT", socket_type="NodeSocketGeometry")
    ng.interface.new_socket("Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry")
    n, l = ng.nodes, ng.links
    gi = n.new("NodeGroupInput")
    go = n.new("NodeGroupOutput")
    oi = n.new("GeometryNodeObjectInfo")
    oi.transform_space = "ORIGINAL"
    oi.inputs["Object"].default_value = srcob
    iop = n.new("GeometryNodeInstanceOnPoints")
    rot = n.new("GeometryNodeInputNamedAttribute")
    rot.data_type = "FLOAT_VECTOR"
    rot.inputs["Name"].default_value = "nl2_rot"
    sc = n.new("GeometryNodeInputNamedAttribute")
    sc.data_type = "FLOAT"
    sc.inputs["Name"].default_value = "nl2_scale"
    gi.location, oi.location, rot.location, sc.location = (-600, 0), (-400, -150), (-400, -350), (-400, -500)
    iop.location, go.location = (-150, 0), (250, 0)
    l.new(gi.outputs["Geometry"], iop.inputs["Points"])
    l.new(oi.outputs["Geometry"], iop.inputs["Instance"])
    l.new(rot.outputs["Attribute"], iop.inputs["Rotation"])
    l.new(sc.outputs["Attribute"], iop.inputs["Scale"])
    out = iop.outputs["Instances"]
    if realize:
        real = n.new("GeometryNodeRealizeInstances")
        real.location = (50, -100)
        l.new(out, real.inputs["Geometry"])
        out = real.outputs["Geometry"]
    l.new(out, go.inputs["Geometry"])
    return ng


def source_object(key, asset, root):
    """Hidden mesh object holding one instanced part (bolt, nut, flange bolt set)."""
    name = "NL2 src " + key
    ob = bpy.data.objects.get(name)
    if ob is not None:
        return ob
    V = asset.V
    counts = asset.counts
    mats = [("Steel" if asset.slots[s] == "steel" else asset.slots[s].title()) for s in asset.slot]
    me = mesh_from_arrays(name, (V, asset.idx, counts, mats, np.ones(len(counts), bool)), 50.0)
    ob = bpy.data.objects.new(name, me)
    src = collection(SOURCES, root)
    src.objects.link(ob)
    ob.hide_render = True
    ob.hide_viewport = True
    # keep the source collection out of renders and the viewport
    src.hide_render = True
    src.hide_viewport = True
    return ob


def instancer_object(name, key, asset, instances, root, col, realize=False):
    arr = instances.arrays()
    remove_object(name)
    if arr is None:
        return None
    pos, rot, scale = arr
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(pos))
    me.vertices.foreach_set("co", pos.astype(np.float32).ravel())
    a = me.attributes.new("nl2_rot", "FLOAT_VECTOR", "POINT")
    a.data.foreach_set("vector", rot.astype(np.float32).ravel())
    s = me.attributes.new("nl2_scale", "FLOAT", "POINT")
    s.data.foreach_set("value", scale.astype(np.float32))
    me.update()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    mod = ob.modifiers.new("NL2 Instances", "NODES")
    mod.node_group = instancer_group(source_object(key, asset, root), realize)
    return ob


def mesh_object(name, mb, col):
    remove_object(name)
    arr = mb.arrays()
    if arr is None:
        return None
    me = mesh_from_arrays(name, arr)
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    return ob


def output_collections(sub):
    root = collection(COLLECTION)
    return root, collection(sub, root)
