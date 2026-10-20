#!/usr/bin/env python3
"""
Modular "Lego" building kit — 15 m grid, with interior furniture.
================================================================
Generates the wall / floor / roof / stair modules plus the furniture modules
used to furnish the 11 Battle-Royale buildings.  Everything is low-poly, flat
shaded, and has its origin at BOTTOM-CENTRE (0, 0, 0) with the base on z = 0.

Structural modules (15 m grid, 3 m storey)
  mod_wall_solid.glb     15.0 x 0.20 x 3.0 m   plain panel
  mod_wall_partition.glb 15.0 x 0.10 x 3.0 m   thin interior partition
  mod_wall_partition_door.glb 15.0 x 0.10 x 3.0 m  partition + 1.5 x 2.2 m doorway
  mod_wall_window.glb    15.0 x 0.38 x 3.0 m   two 1.5 x 1.5 m windows (sill 1.0)
  mod_wall_door.glb      15.0 x 0.30 x 3.0 m   1.5 x 2.2 m walk-through door
  mod_wall_garage.glb    15.0 x 0.42 x 3.0 m   6.0 x 2.6 m roller opening
  mod_floor.glb          15.0 x 15.0 x 0.2 m   floor / ceiling slab
  mod_roof_flat.glb      15.0 x 15.0 x 0.66 m  flat roof + 0.4 m parapet
  mod_roof_slanted.glb   15.0 x 15.0 x 3.04 m  hip roof, 3 m ridge
  mod_stairs.glb         2.4 x 3.4 x 3.0 m     10 steps, exactly one storey

Furniture modules
  mod_table.glb    2.2 x 1.1 x 0.78 m   desk / dining table
  mod_bed.glb      2.1 x 1.35 x 0.60 m  bed (frame, mattress, pillow, blanket)
  mod_crate.glb    1.1 x 1.1 x 1.1 m    loot crate with edge battens
  mod_shelf.glb    1.8 x 0.45 x 2.0 m   four-shelf storage unit
  mod_counter.glb  2.6 x 0.8 x 1.05 m   shop counter
  mod_sofa.glb     2.3 x 0.95 x 0.8 m   sofa

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

# ---- 15 m grid --------------------------------------------------------------
GRID = 15.0
WALL_H = 3.0
WALL_T = 0.2
PARTITION_T = 0.1     # interior partitions are half the exterior thickness
WINDOW_W, WINDOW_H, WINDOW_SILL = 1.5, 1.5, 1.0
WINDOW_OFFSET = 3.6          # two windows per 15 m panel
DOOR_W, DOOR_H = 1.5, 2.2
GARAGE_W, GARAGE_H = 6.0, 2.6
FLOOR_T = 0.2
ROOF_RIDGE = 3.0
STAIR_STEPS, STAIR_RISE, STAIR_TREAD, STAIR_W = 10, 0.3, 0.34, 2.4

bpy.ops.wm.read_factory_settings(use_empty=True)

_MATS: dict[str, bpy.types.Material] = {}


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_color(hex_str: str) -> tuple[float, float, float]:
    h = hex_str.lstrip("#")
    return tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


def make_material(name: str, hex_str: str, rough: float = 0.8,
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


# palette used by the kit itself (the assembler re-skins walls per building)
SANDSTONE = make_material("Mod_Sandstone", "#D9C089", rough=0.80)
BRICK_RED = make_material("Mod_BrickRed", "#9E4B3C", rough=0.82)
CONCRETE = make_material("Mod_ConcreteGrey", "#B4B4AE", rough=0.85)
WOOD = make_material("Mod_Wood", "#8B5A2B", rough=0.80)
WOOD_DARK = make_material("Mod_WoodDark", "#5E3A1B", rough=0.85)
METAL = make_material("Mod_Metal", "#5A6065", rough=0.45, metal=0.55)
MATTRESS = make_material("Mod_Mattress", "#EDE8DC", rough=0.9)
BLANKET = make_material("Mod_Blanket", "#3F6E8F", rough=0.9)
FABRIC = make_material("Mod_SofaFabric", "#8E5A46", rough=0.9)
CARDBOARD = make_material("Mod_CrateWood", "#A9713C", rough=0.85)
CRATE_BATTEN = make_material("Mod_CrateBatten", "#5E3A1B", rough=0.85)
TABLE_WOOD = make_material("Mod_TableTop", "#9C6634", rough=0.82)
BED_WOOD = make_material("Mod_BedFrame", "#6B4423", rough=0.84)
SHELF_WOOD = make_material("Mod_ShelfWood", "#7A4E27", rough=0.84)
TABLE_LEG = make_material("Mod_TableLegs", "#5E3A1B", rough=0.85)
SHELF_FRAME = make_material("Mod_ShelfFrame", "#5E3A1B", rough=0.85)
COUNTER_TOP = make_material("Mod_CounterTop", "#5E3A1B", rough=0.8)
COUNTER_WOOD = make_material("Mod_CounterBody", "#8A5A33", rough=0.82)


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


def box(name, size, loc, mat, parts=None, rot=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return finish(o, name, mat, parts)


def cyl(name, r, depth, loc, mat, verts=12, parts=None, rot=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth,
                                        location=loc, rotation=rot)
    o = bpy.context.active_object
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
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
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    verts = [v.co for v in obj.data.vertices]
    min_x = min(v.x for v in verts); max_x = max(v.x for v in verts)
    min_y = min(v.y for v in verts); max_y = max(v.y for v in verts)
    min_z = min(v.z for v in verts)
    obj.data.transform(Matrix.Translation((-(min_x + max_x) / 2.0,
                                           -(min_y + max_y) / 2.0, -min_z)))
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


# ----------------------------------------------------------------------------
# structural modules
# ----------------------------------------------------------------------------
def build_wall(variant: str, filename: str, name: str):
    panel = box(name, (GRID, WALL_T, WALL_H), (0.0, 0.0, WALL_H / 2.0), SANDSTONE)
    parts = [panel]

    if variant == "window":
        for sx in (-1, 1):
            cx = sx * WINDOW_OFFSET
            cutter = box("Cut", (WINDOW_W, WALL_T + 1.0, WINDOW_H),
                         (cx, 0.0, WINDOW_SILL + WINDOW_H / 2.0), SANDSTONE)
            boolean_cut(panel, cutter)
            parts.append(box("Sill", (WINDOW_W + 0.30, WALL_T + 0.18, 0.10),
                             (cx, 0.0, WINDOW_SILL - 0.05), SANDSTONE))
            parts.append(box("Lintel", (WINDOW_W + 0.30, WALL_T + 0.10, 0.10),
                             (cx, 0.0, WINDOW_SILL + WINDOW_H + 0.05), SANDSTONE))
    elif variant == "door":
        cutter = box("Cut", (DOOR_W, WALL_T + 1.0, DOOR_H),
                     (0.0, 0.0, DOOR_H / 2.0), SANDSTONE)
        boolean_cut(panel, cutter)
        parts += [
            box("DoorFrameL", (0.14, WALL_T + 0.12, DOOR_H),
                (-DOOR_W / 2 - 0.07, 0.0, DOOR_H / 2.0), SANDSTONE),
            box("DoorFrameR", (0.14, WALL_T + 0.12, DOOR_H),
                (DOOR_W / 2 + 0.07, 0.0, DOOR_H / 2.0), SANDSTONE),
            box("DoorHead", (DOOR_W + 0.28, WALL_T + 0.12, 0.14),
                (0.0, 0.0, DOOR_H + 0.07), SANDSTONE),
        ]
    elif variant == "garage":
        cutter = box("Cut", (GARAGE_W, WALL_T + 1.0, GARAGE_H),
                     (0.0, 0.0, GARAGE_H / 2.0), SANDSTONE)
        boolean_cut(panel, cutter)
        parts += [
            box("RollerBox", (GARAGE_W + 0.46, WALL_T + 0.24, 0.32),
                (0.0, 0.0, GARAGE_H + 0.16), SANDSTONE),
            box("TrackL", (0.18, WALL_T + 0.18, GARAGE_H),
                (-GARAGE_W / 2 - 0.09, 0.0, GARAGE_H / 2.0), SANDSTONE),
            box("TrackR", (0.18, WALL_T + 0.18, GARAGE_H),
                (GARAGE_W / 2 + 0.09, 0.0, GARAGE_H / 2.0), SANDSTONE),
        ]

    obj = join(parts, name)
    return export(obj, filename)


def build_wall_solid():
    return build_wall("solid", "mod_wall_solid.glb", "Mod_WallSolid")


def build_wall_window():
    return build_wall("window", "mod_wall_window.glb", "Mod_WallWindow")


def build_wall_door():
    return build_wall("door", "mod_wall_door.glb", "Mod_WallDoor")


def build_wall_garage():
    return build_wall("garage", "mod_wall_garage.glb", "Mod_WallGarage")


def build_partition(door: bool):
    """Thin interior wall (0.10 m) with no opening, or a 1.5 m doorway.

    One material slot only, so the assembler can re-skin the whole partition in
    the building's own wall colour without touching anything else.
    """
    t = PARTITION_T
    name = "Mod_WallPartitionDoor" if door else "Mod_WallPartition"
    filename = "mod_wall_partition_door.glb" if door else "mod_wall_partition.glb"
    panel = box(name, (GRID, t, WALL_H), (0.0, 0.0, WALL_H / 2.0), SANDSTONE)
    parts = [panel]
    if door:
        cutter = box("Cut", (DOOR_W, t + 1.0, DOOR_H),
                     (0.0, 0.0, DOOR_H / 2.0), SANDSTONE)
        boolean_cut(panel, cutter)
        frame_t = t + 0.12          # slim casing, 6 cm proud of each face
        parts += [
            box("FrameL", (0.12, frame_t, DOOR_H + 0.12),
                (-DOOR_W / 2 - 0.06, 0.0, (DOOR_H + 0.12) / 2.0), SANDSTONE),
            box("FrameR", (0.12, frame_t, DOOR_H + 0.12),
                (DOOR_W / 2 + 0.06, 0.0, (DOOR_H + 0.12) / 2.0), SANDSTONE),
            box("FrameHead", (DOOR_W + 0.36, frame_t, 0.12),
                (0.0, 0.0, DOOR_H + 0.06), SANDSTONE),
            box("SkirtL", (0.06, t + 0.06, 0.10),
                (-DOOR_W / 2 - 0.12, 0.0, 0.05), SANDSTONE),
            box("SkirtR", (0.06, t + 0.06, 0.10),
                (DOOR_W / 2 + 0.12, 0.0, 0.05), SANDSTONE),
        ]
    obj = join(parts, name)
    return export(obj, filename)


def build_wall_partition():
    return build_partition(door=False)


def build_wall_partition_door():
    return build_partition(door=True)


def build_floor():
    slab = box("Mod_Floor", (GRID, GRID, FLOOR_T),
               (0.0, 0.0, FLOOR_T / 2.0), CONCRETE)
    parts = [slab]
    for i in (-1, 1):
        parts.append(box(f"GrooveX{i}", (0.06, GRID - 0.6, 0.02),
                         (i * GRID / 3.0, 0.0, FLOOR_T - 0.01), CONCRETE))
        parts.append(box(f"GrooveY{i}", (GRID - 0.6, 0.06, 0.02),
                         (0.0, i * GRID / 3.0, FLOOR_T - 0.01), CONCRETE))
    obj = join(parts, "Mod_Floor")
    return export(obj, "mod_floor.glb")


def build_roof_flat():
    ph = 0.4
    parts = [box("Slab", (GRID, GRID, FLOOR_T), (0.0, 0.0, FLOOR_T / 2.0), CONCRETE)]
    parts += [
        box("ParapetN", (GRID, 0.2, ph), (0.0, GRID / 2 - 0.1, FLOOR_T + ph / 2), CONCRETE),
        box("ParapetS", (GRID, 0.2, ph), (0.0, -GRID / 2 + 0.1, FLOOR_T + ph / 2), CONCRETE),
        box("ParapetE", (0.2, GRID - 0.4, ph), (GRID / 2 - 0.1, 0.0, FLOOR_T + ph / 2), CONCRETE),
        box("ParapetW", (0.2, GRID - 0.4, ph), (-GRID / 2 + 0.1, 0.0, FLOOR_T + ph / 2), CONCRETE),
    ]
    for name, size, loc in [
        ("CopingN", (GRID, 0.20, 0.06), (0.0, GRID / 2 - 0.1, FLOOR_T + ph + 0.03)),
        ("CopingS", (GRID, 0.20, 0.06), (0.0, -GRID / 2 + 0.1, FLOOR_T + ph + 0.03)),
        ("CopingE", (0.20, GRID - 0.4, 0.06), (GRID / 2 - 0.1, 0.0, FLOOR_T + ph + 0.03)),
        ("CopingW", (0.20, GRID - 0.4, 0.06), (-GRID / 2 + 0.1, 0.0, FLOOR_T + ph + 0.03)),
    ]:
        parts.append(box(name, size, loc, SANDSTONE))
    obj = join(parts, "Mod_RoofFlat")
    return export(obj, "mod_roof_flat.glb")


def build_roof_slanted():
    h = ROOF_RIDGE
    hw, hd = GRID / 2.0, GRID / 2.0
    ridge_x = 3.0
    verts = [
        (-hw, -hd, 0.0), (hw, -hd, 0.0), (hw, hd, 0.0), (-hw, hd, 0.0),
        (-ridge_x, 0.0, h), (ridge_x, 0.0, h),
    ]
    faces = [
        (3, 2, 1, 0),          # underside
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
    parts = [obj,
             box("RidgeCap", (ridge_x * 2.0 + 0.5, 0.40, 0.16),
                 (0.0, 0.0, h - 0.06), WOOD_DARK),
             box("EaveS", (GRID, 0.18, 0.14), (0.0, -hd + 0.09, 0.05), WOOD_DARK),
             box("EaveN", (GRID, 0.18, 0.14), (0.0, hd - 0.09, 0.05), WOOD_DARK)]
    obj = join(parts, "Mod_RoofSlanted")
    return export(obj, "mod_roof_slanted.glb")


def build_stairs():
    parts = []
    for i in range(STAIR_STEPS):
        z_top = (i + 1) * STAIR_RISE
        y = -STAIR_STEPS * STAIR_TREAD / 2.0 + i * STAIR_TREAD + STAIR_TREAD / 2.0
        parts.append(box(f"Step{i}", (STAIR_W, STAIR_TREAD, z_top),
                         (0.0, y, z_top / 2.0), CONCRETE))
    run = STAIR_STEPS * STAIR_TREAD
    for sx in (-1, 1):
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.0))
        rail = bpy.context.active_object
        rail.name = f"Stringer{sx}"
        rail.scale = (0.12, run, 0.60)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        rail.data.transform(Matrix.Translation((sx * (STAIR_W / 2.0 - 0.06),
                                              0.0, STAIR_STEPS * STAIR_RISE / 2.0 + 0.1)))
        parts.append(finish(rail, f"Stringer{sx}", CONCRETE))
    obj = join(parts, "Mod_Stairs")
    return export(obj, "mod_stairs.glb")


# ----------------------------------------------------------------------------
# furniture modules
# ----------------------------------------------------------------------------
def build_table():
    parts = [box("Top", (2.2, 1.1, 0.07), (0.0, 0.0, 0.755), TABLE_WOOD)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(box(f"Leg{sx}{sy}", (0.09, 0.09, 0.72),
                             (sx * 0.98, sy * 0.44, 0.36), TABLE_LEG))
    parts.append(box("Stretcher", (1.9, 0.07, 0.07), (0.0, 0.0, 0.25), TABLE_LEG))
    obj = join(parts, "Mod_Table")
    return export(obj, "mod_table.glb")


def build_bed():
    parts = [
        box("Frame", (2.1, 1.35, 0.22), (0.0, 0.0, 0.24), BED_WOOD),
        box("Mattress", (2.0, 1.28, 0.22), (0.0, 0.0, 0.46), MATTRESS),
        box("Blanket", (1.35, 1.30, 0.10), (0.36, 0.0, 0.60), BLANKET),
        box("Pillow", (0.42, 0.85, 0.14), (-0.78, 0.0, 0.62), MATTRESS),
        box("Headboard", (0.10, 1.35, 0.80), (-1.02, 0.0, 0.40), BED_WOOD),
    ]
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(box(f"Leg{sx}{sy}", (0.10, 0.10, 0.14),
                             (sx * 0.95, sy * 0.58, 0.07), BED_WOOD))
    obj = join(parts, "Mod_Bed")
    return export(obj, "mod_bed.glb")


def build_crate():
    s = 1.1
    parts = [box("Body", (s, s, s), (0.0, 0.0, s / 2.0), CARDBOARD)]
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(box(f"Post{sx}{sy}", (0.10, 0.10, s + 0.02),
                             (sx * (s / 2 - 0.05), sy * (s / 2 - 0.05), s / 2.0),
                             CRATE_BATTEN))
    for z in (0.12, s - 0.12):
        parts.append(box(f"BandX{z}", (s + 0.03, 0.08, 0.10), (0.0, 0.0, z), CRATE_BATTEN))
        parts.append(box(f"BandY{z}", (0.08, s + 0.03, 0.10), (0.0, 0.0, z), CRATE_BATTEN))
    obj = join(parts, "Mod_Crate")
    return export(obj, "mod_crate.glb")


def build_shelf():
    parts = [
        box("SideL", (0.08, 0.45, 2.0), (-0.86, 0.0, 1.0), SHELF_FRAME),
        box("SideR", (0.08, 0.45, 2.0), (0.86, 0.0, 1.0), SHELF_FRAME),
        box("Back", (1.72, 0.06, 2.0), (0.0, 0.19, 1.0), SHELF_FRAME),
    ]
    for i in range(4):
        z = 0.22 + i * 0.52
        parts.append(box(f"Board{i}", (1.72, 0.42, 0.06), (0.0, -0.01, z), SHELF_WOOD))
    obj = join(parts, "Mod_Shelf")
    return export(obj, "mod_shelf.glb")


def build_counter():
    parts = [
        box("Body", (2.6, 0.8, 0.95), (0.0, 0.0, 0.5), COUNTER_WOOD),
        box("Top", (2.75, 0.92, 0.10), (0.0, 0.0, 1.0), COUNTER_TOP),
        box("Kick", (2.4, 0.7, 0.10), (0.0, 0.0, 0.05), COUNTER_TOP),
        box("CashBox", (0.45, 0.35, 0.28), (0.85, 0.0, 1.14), METAL),
    ]
    obj = join(parts, "Mod_Counter")
    return export(obj, "mod_counter.glb")


def build_sofa():
    parts = [
        box("Base", (2.3, 0.95, 0.42), (0.0, 0.0, 0.21), FABRIC),
        box("Back", (2.3, 0.22, 0.80), (0.0, 0.36, 0.40), FABRIC),
        box("Seat", (2.0, 0.70, 0.16), (0.0, -0.05, 0.50), MATTRESS),
    ]
    for sx in (-1, 1):
        parts.append(box(f"Arm{sx}", (0.20, 0.95, 0.30),
                         (sx * 1.05, 0.0, 0.57), FABRIC))
    obj = join(parts, "Mod_Sofa")
    return export(obj, "mod_sofa.glb")


# ----------------------------------------------------------------------------
# verify
# ----------------------------------------------------------------------------
def glb_stats(path):
    data = open(path, "rb").read()
    jl = struct.unpack("<I", data[12:16])[0]
    g = json.loads(data[20:20 + jl])
    tris = 0
    for m in g.get("meshes", []):
        for p in m.get("primitives", []):
            tris += (g["accessors"][p["indices"]]["count"] // 3
                     if "indices" in p
                     else g["accessors"][p["attributes"]["POSITION"]]["count"] // 3)
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
    return min(zs)


def main():
    print(f"Blender bpy {bpy.app.version_string}")
    builders = [
        ("mod_wall_solid.glb", build_wall_solid),
        ("mod_wall_window.glb", build_wall_window),
        ("mod_wall_door.glb", build_wall_door),
        ("mod_wall_garage.glb", build_wall_garage),
        ("mod_wall_partition.glb", build_wall_partition),
        ("mod_wall_partition_door.glb", build_wall_partition_door),
        ("mod_floor.glb", build_floor),
        ("mod_roof_flat.glb", build_roof_flat),
        ("mod_roof_slanted.glb", build_roof_slanted),
        ("mod_stairs.glb", build_stairs),
        ("mod_table.glb", build_table),
        ("mod_bed.glb", build_bed),
        ("mod_crate.glb", build_crate),
        ("mod_shelf.glb", build_shelf),
        ("mod_counter.glb", build_counter),
        ("mod_sofa.glb", build_sofa),
    ]
    print(f"— exporting {len(builders)} modules on the {GRID:.0f} m grid —")
    for filename, fn in builders:
        fn()
        bpy.ops.wm.read_factory_settings(use_empty=True)
        _MATS.clear()
        globals().update({
            "SANDSTONE": make_material("Mod_Sandstone", "#D9C089", rough=0.80),
            "BRICK_RED": make_material("Mod_BrickRed", "#9E4B3C", rough=0.82),
            "CONCRETE": make_material("Mod_ConcreteGrey", "#B4B4AE", rough=0.85),
            "WOOD": make_material("Mod_Wood", "#8B5A2B", rough=0.80),
            "WOOD_DARK": make_material("Mod_WoodDark", "#5E3A1B", rough=0.85),
            "METAL": make_material("Mod_Metal", "#5A6065", rough=0.45, metal=0.55),
            "MATTRESS": make_material("Mod_Mattress", "#EDE8DC", rough=0.9),
            "BLANKET": make_material("Mod_Blanket", "#3F6E8F", rough=0.9),
            "FABRIC": make_material("Mod_SofaFabric", "#8E5A46", rough=0.9),
            "CARDBOARD": make_material("Mod_CrateWood", "#A9713C", rough=0.85),
            "TABLE_WOOD": make_material("Mod_TableTop", "#9C6634", rough=0.82),
            "BED_WOOD": make_material("Mod_BedFrame", "#6B4423", rough=0.84),
            "SHELF_WOOD": make_material("Mod_ShelfWood", "#7A4E27", rough=0.84),
            "COUNTER_WOOD": make_material("Mod_CounterBody", "#8A5A33", rough=0.82),
            "TABLE_LEG": make_material("Mod_TableLegs", "#5E3A1B", rough=0.85),
            "SHELF_FRAME": make_material("Mod_ShelfFrame", "#5E3A1B", rough=0.85),
            "COUNTER_TOP": make_material("Mod_CounterTop", "#5E3A1B", rough=0.8),
            "CRATE_BATTEN": make_material("Mod_CrateBatten", "#5E3A1B", rough=0.85),
        })

    print("— verification (re-import) —")
    bad = []
    for filename, _ in builders:
        min_z = verify(os.path.join(OUT_DIR, filename))
        if abs(min_z) > 1e-4:
            bad.append((filename, min_z))
    if bad:
        raise RuntimeError(f"origin verification failed: {bad}")
    print(f"Done — {len(builders)} modules generated (15 m grid + partitions + furniture).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
