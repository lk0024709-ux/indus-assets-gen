#!/usr/bin/env python3
"""
Modular "Lego" building blocks — for the 11 standard Battle-Royale buildings.
=============================================================================
Generates 8 base modules with SOLID palette colours (Sandstone, Brick Red,
Concrete Grey, Wood), low-poly, flat shaded, origin at BOTTOM-CENTRE (0,0,0)
with the base sitting exactly on z = 0.

  mod_wall_solid.glb    10 x 3 x 0.2 m   plain wall panel
  mod_wall_window.glb   10 x 3 x 0.2 m   1.5 x 1.5 m window opening
  mod_wall_door.glb     10 x 3 x 0.2 m   1.5 x 2.2 m door opening
  mod_wall_garage.glb   10 x 3 x 0.2 m   6.0 x 2.6 m roller-door opening (bonus)
  mod_floor.glb         10 x 10 x 0.2 m  floor / ceiling slab
  mod_roof_flat.glb     10 x 10 x 0.6 m  flat roof + 0.4 m parapet
  mod_roof_slanted.glb  10 x 10 x 2.6 m  hip roof (ridge along X)
  mod_stairs.glb        2 x 3 m          10-step staircase, 2.0 m rise

Used by tools/assemble_buildings.py to build the 11 buildings.
Output: docs/models/modules/
"""
from __future__ import annotations

import json
import math
import os
import struct
import sys

import bpy
from mathutils import Matrix, Vector

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "modules")
os.makedirs(OUT_DIR, exist_ok=True)

# module dimensions
WALL_W, WALL_H, WALL_T = 10.0, 3.0, 0.2
WINDOW_W, WINDOW_H, WINDOW_SILL = 1.5, 1.5, 1.0
DOOR_W, DOOR_H = 1.5, 2.2
GARAGE_W, GARAGE_H = 6.0, 2.6
FLOOR_W, FLOOR_D, FLOOR_T = 10.0, 10.0, 0.2
ROOF_H = 2.6
STAIR_STEPS, STAIR_RISE, STAIR_TREAD, STAIR_W = 10, 0.2, 0.3, 2.0

bpy.ops.wm.read_factory_settings(use_empty=True)

_MATS: dict[str, bpy.types.Material] = {}


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_color(hex_str: str) -> tuple[float, float, float]:
    h = hex_str.lstrip("#")
    return tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def make_material(name: str, hex_str: str, rough: float = 0.75,
                  metal: float = 0.0) -> bpy.types.Material:
    if name in _MATS:
        return _MATS[name]
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    rgb = hex_color(hex_str)
    bsdf.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    mat.diffuse_color = (rgb[0], rgb[1], rgb[2], 1.0)
    _MATS[name] = mat
    return mat


# ---- the game palette -------------------------------------------------------
SANDSTONE = make_material("Mod_Sandstone", "#D9C089", rough=0.80)
BRICK_RED = make_material("Mod_BrickRed", "#9E4B3C", rough=0.82)
CONCRETE = make_material("Mod_ConcreteGrey", "#B4B4AE", rough=0.85)
WOOD = make_material("Mod_Wood", "#8B5A2B", rough=0.80)


# ----------------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------------
def finish(obj, name, mat, parts=None):
    obj.name = name
    obj.data.name = name + "Mesh"
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = False
    if parts is not None:
        parts.append(obj)
    return obj


def box(name, size, loc, mat, parts=None):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    o = bpy.context.active_object
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    return finish(o, name, mat, parts)


def boolean_cut(target, cutter):
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    mod = target.modifiers.new(name="Cut", type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.use_self = True
    mod.object = cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def join(parts, name):
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "Mesh"
    return obj


def set_origin_bottom_center(obj):
    """Bake the object transform into the mesh, then translate the mesh so the
    bbox is centred in X/Y with min Z exactly at 0 — origin = bottom-centre."""
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    verts = [v.co for v in obj.data.vertices]
    min_x = min(v.x for v in verts); max_x = max(v.x for v in verts)
    min_y = min(v.y for v in verts); max_y = max(v.y for v in verts)
    min_z = min(v.z for v in verts)
    off = Vector((-(min_x + max_x) / 2.0, -(min_y + max_y) / 2.0, -min_z))
    obj.data.transform(Matrix.Translation(off))
    obj.data.update()
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)


def export(obj, filename):
    set_origin_bottom_center(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    path = os.path.join(OUT_DIR, filename)
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB",
                              use_selection=True, export_apply=True)
    if not os.path.isfile(path):
        raise RuntimeError(f"export failed: {path}")
    bpy.data.objects.remove(obj, do_unlink=True)
    return path


def wall_panel(name, cut=None, mat=SANDSTONE):
    """10 x 3 x 0.2 wall panel standing on z=0, thickness along Y."""
    panel = box(name, (WALL_W, WALL_T, WALL_H), (0.0, 0.0, WALL_H / 2.0), mat)
    if cut == "window":
        cutter = box("Cut", (WINDOW_W, WALL_T + 1.0, WINDOW_H),
                     (0.0, 0.0, WINDOW_SILL + WINDOW_H / 2.0), mat)
        boolean_cut(panel, cutter)
        # sill ledge + lintel
        parts = [panel,
                 box("Sill", (WINDOW_W + 0.30, WALL_T + 0.18, 0.10),
                     (0.0, 0.0, WINDOW_SILL - 0.05), mat),
                 box("Lintel", (WINDOW_W + 0.30, WALL_T + 0.10, 0.10),
                     (0.0, 0.0, WINDOW_SILL + WINDOW_H + 0.05), mat)]
        panel = join(parts, name)
        panel.data.materials.clear()
        panel.data.materials.append(mat)
    elif cut == "door":
        cutter = box("Cut", (DOOR_W, WALL_T + 1.0, DOOR_H),
                     (0.0, 0.0, DOOR_H / 2.0), mat)
        boolean_cut(panel, cutter)
        parts = [panel,
                 box("DoorFrameL", (0.12, WALL_T + 0.10, DOOR_H),
                     (-DOOR_W / 2 - 0.06, 0.0, DOOR_H / 2.0), mat),
                 box("DoorFrameR", (0.12, WALL_T + 0.10, DOOR_H),
                     (DOOR_W / 2 + 0.06, 0.0, DOOR_H / 2.0), mat),
                 box("DoorHead", (DOOR_W + 0.24, WALL_T + 0.10, 0.12),
                     (0.0, 0.0, DOOR_H + 0.06), mat)]
        panel = join(parts, name)
        panel.data.materials.clear()
        panel.data.materials.append(mat)
    elif cut == "garage":
        cutter = box("Cut", (GARAGE_W, WALL_T + 1.0, GARAGE_H),
                     (0.0, 0.0, GARAGE_H / 2.0), mat)
        boolean_cut(panel, cutter)
        parts = [panel,
                 box("RollerBox", (GARAGE_W + 0.40, WALL_T + 0.22, 0.30),
                     (0.0, 0.0, GARAGE_H + 0.15), mat),
                 box("TrackL", (0.16, WALL_T + 0.16, GARAGE_H),
                     (-GARAGE_W / 2 - 0.08, 0.0, GARAGE_H / 2.0), mat),
                 box("TrackR", (0.16, WALL_T + 0.16, GARAGE_H),
                     (GARAGE_W / 2 + 0.08, 0.0, GARAGE_H / 2.0), mat)]
        panel = join(parts, name)
        panel.data.materials.clear()
        panel.data.materials.append(mat)
    return panel


# ----------------------------------------------------------------------------
# module builders
# ----------------------------------------------------------------------------
def build_wall_solid():
    obj = wall_panel("Mod_WallSolid", None, SANDSTONE)
    return export(obj, "mod_wall_solid.glb")


def build_wall_window():
    obj = wall_panel("Mod_WallWindow", "window", SANDSTONE)
    return export(obj, "mod_wall_window.glb")


def build_wall_door():
    obj = wall_panel("Mod_WallDoor", "door", SANDSTONE)
    return export(obj, "mod_wall_door.glb")


def build_wall_garage():
    obj = wall_panel("Mod_WallGarage", "garage", SANDSTONE)
    return export(obj, "mod_wall_garage.glb")


def build_floor():
    slab = box("Mod_Floor", (FLOOR_W, FLOOR_D, FLOOR_T),
               (0.0, 0.0, FLOOR_T / 2.0), CONCRETE)
    # shallow expansion grooves + border so the slab reads as panels
    parts = [slab]
    for i in (-1, 1):
        parts.append(box(f"GrooveX{i}", (0.06, FLOOR_D - 0.4, 0.02),
                         (i * FLOOR_W / 3.0, 0.0, FLOOR_T - 0.01), CONCRETE))
        parts.append(box(f"GrooveY{i}", (FLOOR_W - 0.4, 0.06, 0.02),
                         (0.0, i * FLOOR_D / 3.0, FLOOR_T - 0.01), CONCRETE))
    obj = join(parts, "Mod_Floor")
    return export(obj, "mod_floor.glb")


def build_roof_flat():
    parts = [box("Slab", (FLOOR_W, FLOOR_D, FLOOR_T),
                 (0.0, 0.0, FLOOR_T / 2.0), CONCRETE)]
    # parapet 0.4 m high, 0.2 m thick around the rim
    ph = 0.4
    parts += [
        box("ParapetN", (FLOOR_W, 0.2, ph), (0.0, FLOOR_D / 2 - 0.1, FLOOR_T + ph / 2), CONCRETE),
        box("ParapetS", (FLOOR_W, 0.2, ph), (0.0, -FLOOR_D / 2 + 0.1, FLOOR_T + ph / 2), CONCRETE),
        box("ParapetE", (0.2, FLOOR_D - 0.4, ph), (FLOOR_W / 2 - 0.1, 0.0, FLOOR_T + ph / 2), CONCRETE),
        box("ParapetW", (0.2, FLOOR_D - 0.4, ph), (-FLOOR_W / 2 + 0.1, 0.0, FLOOR_T + ph / 2), CONCRETE),
    ]
    # sandstone coping on the parapet
    for name, size, loc in [
        ("CopingN", (FLOOR_W, 0.20, 0.06), (0.0, FLOOR_D / 2 - 0.1, FLOOR_T + ph + 0.03)),
        ("CopingS", (FLOOR_W, 0.20, 0.06), (0.0, -FLOOR_D / 2 + 0.1, FLOOR_T + ph + 0.03)),
        ("CopingE", (0.20, FLOOR_D - 0.4, 0.06), (FLOOR_W / 2 - 0.1, 0.0, FLOOR_T + ph + 0.03)),
        ("CopingW", (0.20, FLOOR_D - 0.4, 0.06), (-FLOOR_W / 2 + 0.1, 0.0, FLOOR_T + ph + 0.03)),
    ]:
        parts.append(box(name, size, loc, SANDSTONE))
    obj = join(parts, "Mod_RoofFlat")
    # give the coping its own slot so the assembler keeps it sandstone
    obj.data.materials.append(SANDSTONE)
    return export(obj, "mod_roof_flat.glb")


def build_roof_slanted():
    h = ROOF_H
    hw, hd = FLOOR_W / 2.0, FLOOR_D / 2.0
    ridge_x = 2.0
    verts = [
        (-hw, -hd, 0.0), (hw, -hd, 0.0), (hw, hd, 0.0), (-hw, hd, 0.0),
        (-ridge_x, 0.0, h), (ridge_x, 0.0, h),
    ]
    faces = [
        (3, 2, 1, 0),          # base (down)
        (0, 1, 5, 4),          # south slope
        (2, 3, 4, 5),          # north slope
        (3, 0, 4),             # west hip
        (1, 2, 5),             # east hip
    ]
    mesh = bpy.data.meshes.new("Mod_RoofSlantedMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new("Mod_RoofSlanted", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.clear()
    obj.data.materials.append(BRICK_RED)
    for poly in obj.data.polygons:
        poly.use_smooth = False
    # ridge cap + eave trim in wood, joined in
    parts = [obj,
             box("RidgeCap", (ridge_x * 2.0 + 0.4, 0.36, 0.14), (0.0, 0.0, h - 0.05), WOOD),
             box("EaveS", (FLOOR_W, 0.18, 0.14), (0.0, -hd + 0.09, 0.05), WOOD),
             box("EaveN", (FLOOR_W, 0.18, 0.14), (0.0, hd - 0.09, 0.05), WOOD)]
    obj = join(parts, "Mod_RoofSlanted")
    # join already produced slot 0 = Brick Red (roof), slot 1 = Wood (ridge/eaves)
    return export(obj, "mod_roof_slanted.glb")


def build_stairs():
    parts = []
    for i in range(STAIR_STEPS):
        z_top = (i + 1) * STAIR_RISE
        y = -STAIR_STEPS * STAIR_TREAD / 2.0 + i * STAIR_TREAD + STAIR_TREAD / 2.0
        parts.append(box(f"Step{i}", (STAIR_W, STAIR_TREAD, z_top),
                         (0.0, y, z_top / 2.0), CONCRETE))
    # stringer side rails
    run = STAIR_STEPS * STAIR_TREAD
    for sx in (-1, 1):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))
        rail = bpy.context.active_object
        rail.name = f"Stringer{sx}"
        rail.scale = (0.12, run, 0.55)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        rail.data.transform(Matrix.Translation((sx * (STAIR_W / 2.0 - 0.06),
                                              0.0,
                                              STAIR_STEPS * STAIR_RISE / 2.0 + 0.1)))
        parts.append(finish(rail, f"Stringer{sx}", CONCRETE))
    obj = join(parts, "Mod_Stairs")
    obj.data.materials.clear()
    obj.data.materials.append(CONCRETE)
    return export(obj, "mod_stairs.glb")


# ----------------------------------------------------------------------------
# verify
# ----------------------------------------------------------------------------
def glb_stats(path):
    data = open(path, "rb").read()
    if data[:4] != b"glTF":
        raise RuntimeError("not a GLB")
    jl = struct.unpack("<I", data[12:16])[0]
    g = json.loads(data[20:20 + jl])
    tris = 0
    for m in g.get("meshes", []):
        for p in m.get("primitives", []):
            if "indices" in p:
                tris += g["accessors"][p["indices"]]["count"] // 3
            else:
                tris += g["accessors"][p["attributes"]["POSITION"]]["count"] // 3
    return os.path.getsize(path), tris, len(g.get("materials", []))


def verify(path):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    xs, ys, zs = [], [], []
    for o in objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            xs.append(w.x); ys.append(w.y); zs.append(w.z)
    size, tris, mats = glb_stats(path)
    print(f"  {os.path.basename(path):24s} {max(xs) - min(xs):5.2f} x "
          f"{max(ys) - min(ys):5.2f} x {max(zs) - min(zs):5.2f} m  "
          f"minZ {min(zs):+.3f}  {tris:5d} tris  {mats} mats  {size / 1024:5.1f} KB")
    return max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), min(zs)


def main():
    print(f"Blender bpy {bpy.app.version_string}")
    builders = [
        ("mod_wall_solid.glb", build_wall_solid),
        ("mod_wall_window.glb", build_wall_window),
        ("mod_wall_door.glb", build_wall_door),
        ("mod_wall_garage.glb", build_wall_garage),
        ("mod_floor.glb", build_floor),
        ("mod_roof_flat.glb", build_roof_flat),
        ("mod_roof_slanted.glb", build_roof_slanted),
        ("mod_stairs.glb", build_stairs),
    ]
    print("— exporting modules —")
    for filename, fn in builders:
        p = fn()
        bpy.ops.wm.read_factory_settings(use_empty=True)
        _MATS.clear()
        globals().update({
            "SANDSTONE": make_material("Mod_Sandstone", "#D9C089", rough=0.80),
            "BRICK_RED": make_material("Mod_BrickRed", "#9E4B3C", rough=0.82),
            "CONCRETE": make_material("Mod_ConcreteGrey", "#B4B4AE", rough=0.85),
            "WOOD": make_material("Mod_Wood", "#8B5A2B", rough=0.80),
        })
        print(f"  wrote {os.path.basename(p)}")
    print("— verification (re-import) —")
    ok = True
    for filename, _ in builders:
        dims = verify(os.path.join(OUT_DIR, filename))
        if abs(dims[3]) > 1e-4:
            ok = False
            print(f"    !! {filename} minZ is {dims[3]:.4f}, expected 0")
    if not ok:
        raise RuntimeError("module origin verification failed")
    print("Done — 8 modular building blocks generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
