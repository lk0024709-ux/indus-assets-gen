#!/usr/bin/env python3
"""
Rajasthani Mahal — ROOM-BY-ROOM MODULAR ASSEMBLY
================================================
Generates 4 walk-in room blocks with solid vibrant colours, then assembles the
whole palace from them.

TASK 1 — ROOM BLOCKS (origin bottom-centre (0,0,0), floor at z=0)
  room_darbar_hall.glb  20 x 15 x 6 m   throne room: raised dais + golden throne,
                                        8 banded pillars, teal/pink checkered floor,
                                        deep-blue arched windows, jali lattices
  room_courtyard.glb    20 x 20 x 6 m   aangan: open to sky, marble fountain dead
                                        centre, arched jharokha walkways on 4 sides,
                                        sandstone + marble floor
  room_ranivas.glb      15 x 10 x 6 m   two rooms + central corridor, protruding
                                        coloured cube patterns, 2 balconies
  room_gateway.glb      15 x  5 x 8.4 m multi-layered scalloped Mehrab arch
                                        (pink + gold), big open wooden doors

TASK 2 — assemble_mahal()
  courtyard (0,0,0) · darbar N (0,17.5) · ranivas E/W (±17.5,0) · gateway S (0,-12.5)
  + second floor (same rooms, scaled 0.85) + flat roof over everything except the
  courtyard + large central teal dome + 4 smaller golden corner domes.
  Joined into one mesh: rajasthani_mahal_mega.glb — continuous, gap-free geometry.

TASK 3 — exports to docs/models/mahal/rooms/ and docs/models/mahal/.
Every mesh is flat shaded, every material a Principled BSDF (roughness 0.6).
"""
from __future__ import annotations

import json
import math
import os
import struct
import sys

import bpy
from mathutils import Matrix, Vector

# ----------------------------------------------------------------------------
# paths
# ----------------------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_ROOT = os.path.join(REPO_ROOT, "docs", "models", "mahal")
OUT_ROOMS = os.path.join(OUT_ROOT, "rooms")
os.makedirs(OUT_ROOMS, exist_ok=True)

# ----------------------------------------------------------------------------
# dimensions (metres)
# ----------------------------------------------------------------------------
DARBAR_W, DARBAR_D, ROOM_H = 20.0, 15.0, 6.0
COURT_W, COURT_D = 20.0, 20.0
RANIVAS_W, RANIVAS_D = 15.0, 10.0
GATE_W, GATE_D, GATE_H = 15.0, 5.0, 8.4
WALL_T = 0.5

# TASK 2 layout — exactly as requested
POS_COURT = (0.0, 0.0, 0.0)
POS_DARBAR = (0.0, 17.5, 0.0)
POS_RANIVAS_E = (17.5, 0.0, 0.0)
POS_RANIVAS_W = (-17.5, 0.0, 0.0)
POS_GATE = (0.0, -12.5, 0.0)
FLOOR2_Z = 6.4          # top of the first flat roof deck
SECOND_SCALE = 0.85     # "scaled down slightly"
GATE_SECOND_SCALE = 0.60

PLAN_X0, PLAN_X1 = -25.0, 25.0
PLAN_Y0, PLAN_Y1 = -15.0, 25.0

# ----------------------------------------------------------------------------
# materials
# ----------------------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)

_MATS: dict[str, bpy.types.Material] = {}


def make_material(name: str, rgb: tuple[float, float, float],
                  rough: float = 0.6, metal: float = 0.0) -> bpy.types.Material:
    if name in _MATS:
        return _MATS[name]
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    mat.diffuse_color = (rgb[0], rgb[1], rgb[2], 1.0)
    _MATS[name] = mat
    return mat


PINK = make_material("Mahal_Pink", (0.96, 0.52, 0.58))
ROSE = make_material("Mahal_Rose", (0.90, 0.36, 0.44))
GOLD = make_material("Mahal_Gold", (0.96, 0.76, 0.22), rough=0.30, metal=0.80)
TEAL = make_material("Mahal_Teal", (0.10, 0.66, 0.66), rough=0.45)
TEAL_DARK = make_material("Mahal_TealDark", (0.06, 0.46, 0.50), rough=0.5)
BLUE = make_material("Mahal_DeepBlue", (0.10, 0.26, 0.72), rough=0.45)
YELLOW = make_material("Mahal_Yellow", (0.99, 0.84, 0.16))
ORANGE = make_material("Mahal_Orange", (0.96, 0.50, 0.16))
SAND = make_material("Mahal_Sandstone", (0.88, 0.75, 0.58), rough=0.7)
MARBLE = make_material("Mahal_Marble", (0.95, 0.94, 0.90), rough=0.35)
WOOD = make_material("Mahal_Wood", (0.44, 0.26, 0.13), rough=0.8)
WOOD_DARK = make_material("Mahal_WoodDark", (0.30, 0.16, 0.08), rough=0.85)
RED = make_material("Mahal_Red", (0.86, 0.14, 0.20), rough=0.65)


# ----------------------------------------------------------------------------
# primitives
# ----------------------------------------------------------------------------
def _finish(obj: bpy.types.Object, name: str, material: bpy.types.Material,
            parts: list | None) -> bpy.types.Object:
    obj.name = name
    obj.data.name = name + "Mesh"
    obj.data.materials.clear()
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = False
    if parts is not None:
        parts.append(obj)
    return obj


def add_box(name, size, loc, material, rot=(0.0, 0.0, 0.0), parts=None):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return _finish(o, name, material, parts)


def add_cylinder(name, radius, depth, loc, material, verts=16,
                 rot=(0.0, 0.0, 0.0), parts=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=radius, depth=depth,
                                        location=loc, rotation=rot)
    o = bpy.context.active_object
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return _finish(o, name, material, parts)


def add_sphere(name, radius, loc, material, seg=16, rings=8, parts=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=rings,
                                         radius=radius, location=loc)
    o = bpy.context.active_object
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return _finish(o, name, material, parts)


def add_cone(name, r1, r2, depth, loc, material, verts=16, parts=None):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2,
                                    depth=depth, location=loc)
    o = bpy.context.active_object
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return _finish(o, name, material, parts)


def add_torus(name, major, minor, loc, material, seg=16, ring=8,
              rot=(0.0, 0.0, 0.0), parts=None):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                     major_segments=seg, minor_segments=ring,
                                     location=loc, rotation=rot)
    o = bpy.context.active_object
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    return _finish(o, name, material, parts)


def join_parts(objs: list[bpy.types.Object], name: str) -> bpy.types.Object:
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "Mesh"
    return obj


def boolean(target, cutter, operation="DIFFERENCE"):
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    mod = target.modifiers.new(name="Bool", type="BOOLEAN")
    mod.operation = operation
    mod.solver = "EXACT"
    mod.use_self = True
    mod.object = cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


# ----------------------------------------------------------------------------
# arch / mehrab helpers
# ----------------------------------------------------------------------------
def arch_cutter(name, width, rect_h, radius, depth, cx, cy, z0,
                orient="x", seg=14):
    """Extruded arch profile: rectangle up to rect_h, then a true
    math.sin/cos semicircle of `radius`.  orient='x' cuts a wall running
    along X (depth on Y); orient='y' cuts a wall running along Y."""
    half = width / 2.0
    top = z0 + rect_h
    profile = [(-half, z0), (-half, top)]
    for i in range(1, seg):
        theta = math.pi * (1.0 - i / seg)
        profile.append((radius * math.cos(theta), top + radius * math.sin(theta)))
    profile += [(half, top), (half, z0)]

    n = len(profile)
    verts, faces = [], []
    for px, pz in profile:
        if orient == "x":
            verts.append((cx + px, cy - depth / 2.0, pz))
        else:
            verts.append((cx - depth / 2.0, cy + px, pz))
    for px, pz in profile:
        if orient == "x":
            verts.append((cx + px, cy + depth / 2.0, pz))
        else:
            verts.append((cx + depth / 2.0, cy + px, pz))
    faces.append(tuple(range(n)))
    faces.append(tuple(range(2 * n - 1, n - 1, -1)))
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, n + j, n + i))

    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def arch_trim(prefix, cx, cy, z0, rect_h, radius, material, orient="x",
              thickness=0.22, seg=9, parts=None):
    """Segmented gold arch trim: follows the semicircle with math.cos/sin."""
    top = z0 + rect_h
    if orient == "x":
        for i in range(seg + 1):
            theta = math.pi * i / seg
            x = cx + radius * math.cos(theta)
            z = top + radius * math.sin(theta)
            add_box(f"{prefix}_Arc{i}", (thickness, thickness, thickness),
                    (x, cy, z), material, parts=parts)
        for sgn in (-1, 1):
            add_box(f"{prefix}_Post{'L' if sgn < 0 else 'R'}",
                    (thickness, thickness, rect_h),
                    (cx + sgn * radius, cy, z0 + rect_h / 2.0), material, parts=parts)
    else:
        for i in range(seg + 1):
            theta = math.pi * i / seg
            y = cy + radius * math.cos(theta)
            z = top + radius * math.sin(theta)
            add_box(f"{prefix}_Arc{i}", (thickness, thickness, thickness),
                    (cx, y, z), material, parts=parts)
        for sgn in (-1, 1):
            add_box(f"{prefix}_Post{'L' if sgn < 0 else 'R'}",
                    (thickness, thickness, rect_h),
                    (cx, cy + sgn * radius, z0 + rect_h / 2.0), material, parts=parts)


def add_window(wall, name, cx, cy, z0, width, rect_h, radius, orient,
               pane=BLUE, frame=GOLD, panes=True, jali=False, parts=None):
    """Cut an arched window, insert a recessed pane and a gold trim."""
    cut = arch_cutter(name + "_Cut", width, rect_h, radius, WALL_T + 3.0,
                      cx, cy, z0, orient=orient)
    boolean(wall, cut)

    if panes:
        panel = arch_cutter(name + "_Pane", width * 0.96, rect_h, radius * 0.96,
                            0.12, cx, cy, z0, orient=orient)
        panel.data.materials.clear()
        panel.data.materials.append(pane)
        if parts is not None:
            parts.append(panel)

    arch_trim(name + "_Trim", cx, cy, z0, rect_h, radius, frame,
              orient=orient, thickness=0.18, parts=parts)

    if jali:
        # vertical bars: height follows the arch exactly
        n_v = 5
        for i in range(n_v):
            dx = -radius * 0.8 + (1.6 * radius) * i / (n_v - 1)
            inner = radius * 0.86
            top = z0 + rect_h + math.sqrt(max(0.0, inner * inner - dx * dx))
            bar_h = top - z0
            if orient == "x":
                add_box(f"{name}_VBar{i}", (0.10, 0.34, bar_h),
                        (cx + dx, cy, z0 + bar_h / 2.0), SAND, parts=parts)
            else:
                add_box(f"{name}_VBar{i}", (0.34, 0.10, bar_h),
                        (cx, cy + dx, z0 + bar_h / 2.0), SAND, parts=parts)
        # horizontal bars: width follows the arch exactly
        n_h = 4
        for j in range(n_h):
            z = z0 + (rect_h + radius * 0.55) * (j + 1) / (n_h + 1)
            dz = z - (z0 + rect_h)
            half = radius * 0.86 if dz <= 0 else math.sqrt(max(0.0, (radius * 0.86) ** 2 - dz * dz))
            if orient == "x":
                add_box(f"{name}_HBar{j}", (half * 2.0, 0.34, 0.10),
                        (cx, cy, z), SAND, parts=parts)
            else:
                add_box(f"{name}_HBar{j}", (0.34, half * 2.0, 0.10),
                        (cx, cy, z), SAND, parts=parts)


def add_checker_floor(prefix, x0, x1, y0, y1, tile, z_top, mat_a, mat_b,
                      parts=None, gap=0.94):
    nx = int(round((x1 - x0) / tile))
    ny = int(round((y1 - y0) / tile))
    for i in range(nx):
        for j in range(ny):
            x = x0 + tile * (i + 0.5)
            y = y0 + tile * (j + 0.5)
            mat = mat_a if (i + j) % 2 == 0 else mat_b
            add_box(f"{prefix}_{i}_{j}", (tile * gap, tile * gap, 0.08),
                    (x, y, z_top + 0.04), mat, parts=parts)


def add_pillar(prefix, x, y, radius, height, parts=None, bands=(RED, BLUE, YELLOW),
               base_mat=PINK, cap=True):
    add_cylinder(f"{prefix}_Shaft", radius, height, (x, y, height / 2.0), base_mat,
                 verts=16, parts=parts)
    for k, z in enumerate((height * 0.17, height * 0.50, height * 0.83)):
        add_torus(f"{prefix}_Band{k}", radius * 1.12, radius * 0.14, (x, y, z),
                  bands[k % len(bands)], seg=16, ring=8, parts=parts)
    add_box(f"{prefix}_Base", (radius * 2.6, radius * 2.6, 0.25),
            (x, y, 0.125), MARBLE, parts=parts)
    if cap:
        add_box(f"{prefix}_Capital", (radius * 2.8, radius * 2.8, 0.22),
                (x, y, height - 0.11), GOLD, parts=parts)


def add_dome(prefix, cx, cy, z_base, radius, material, spire=True, parts=None,
             seg=16, rings=8):
    """Hemisphere (bottom half Booleaned off) + gold finial."""
    dome = add_sphere(f"{prefix}_Dome", radius, (cx, cy, z_base), material,
                      seg=seg, rings=rings, parts=parts)
    cutter = add_box(f"{prefix}_DomeCut", (radius * 3.0, radius * 3.0, radius * 2.0),
                     (cx, cy, z_base - radius), GOLD)
    boolean(dome, cutter)
    if spire:
        add_cylinder(f"{prefix}_SpireCyl", radius * 0.10, radius * 0.7,
                     (cx, cy, z_base + radius + radius * 0.35), GOLD, verts=10, parts=parts)
        add_cone(f"{prefix}_SpireCone", radius * 0.16, 0.0, radius * 0.45,
                 (cx, cy, z_base + radius + radius * 0.9), GOLD, verts=12, parts=parts)
        add_sphere(f"{prefix}_Finial", radius * 0.09,
                   (cx, cy, z_base + radius + radius * 1.2), YELLOW, seg=10, rings=5,
                   parts=parts)


# ============================================================================
# ROOM 1 — DARBAR HALL  (20 x 15 x 6)
# ============================================================================
def build_darbar() -> bpy.types.Object:
    W, D, H = DARBAR_W, DARBAR_D, ROOM_H
    parts: list[bpy.types.Object] = []

    # floor: sandstone base + teal/pink checkered inlay
    add_box("Darbar_FloorBase", (W, D, 0.3), (0, 0, 0.15), SAND, parts=parts)
    add_checker_floor("Darbar_Tile", -9.0, 9.0, -6.0, 6.0, 2.0, 0.30,
                      TEAL, PINK, parts=parts)

    # walls
    back = add_box("Darbar_WallBack", (W, WALL_T, H), (0, D / 2 - WALL_T / 2, H / 2),
                   PINK, parts=parts)
    front = add_box("Darbar_WallFront", (W, WALL_T, H), (0, -D / 2 + WALL_T / 2, H / 2),
                    PINK, parts=parts)
    left = add_box("Darbar_WallLeft", (WALL_T, D, H), (-W / 2 + WALL_T / 2, 0, H / 2),
                   PINK, parts=parts)
    right = add_box("Darbar_WallRight", (WALL_T, D, H), (W / 2 - WALL_T / 2, 0, H / 2),
                    PINK, parts=parts)

    # gold string course around the room
    for name, size, loc in [
        ("Darbar_BandN", (W, 0.62, 0.22), (0, D / 2 - 0.31, 4.35)),
        ("Darbar_BandS", (W, 0.62, 0.22), (0, -D / 2 + 0.31, 4.35)),
        ("Darbar_BandE", (0.62, D, 0.22), (W / 2 - 0.31, 0, 4.35)),
        ("Darbar_BandW", (0.62, D, 0.22), (-W / 2 + 0.31, 0, 4.35)),
    ]:
        add_box(name, size, loc, GOLD, parts=parts)

    # grand south doorway (towards the courtyard)
    door_cut = arch_cutter("Darbar_DoorCut", 5.0, 3.0, 2.5, WALL_T + 3.0,
                           0.0, -D / 2 + WALL_T / 2, 0.0, orient="x")
    boolean(front, door_cut)
    arch_trim("Darbar_DoorTrim", 0.0, -D / 2 + WALL_T / 2, 0.0, 3.0, 2.5, GOLD,
              thickness=0.26, parts=parts)
    add_box("Darbar_DoorSill", (5.4, 0.9, 0.12), (0, -D / 2 + 0.45, 0.06), MARBLE,
            parts=parts)

    # deep-blue arched windows, east + west walls
    for side, wx in (("E", W / 2 - WALL_T / 2), ("W", -W / 2 + WALL_T / 2)):
        for idx, wy in enumerate((-3.6, 3.6)):
            add_window(right if side == "E" else left, f"Darbar_Win{side}{idx}",
                       wx, wy, 1.8, 2.4, 2.0, 1.2, orient="y", parts=parts)

    # jali lattice panels on the back (north) wall
    for idx, wx in enumerate((-5.2, 5.2)):
        add_window(back, f"Darbar_Jali{idx}", wx, D / 2 - WALL_T / 2, 1.8,
                   3.2, 2.6, 1.6, orient="x", panes=True, jali=True, parts=parts)

    # raised dais at the back + steps
    add_box("Darbar_Dais", (12.0, 3.0, 1.0), (0, 5.7, 0.5), SAND, parts=parts)
    add_box("Darbar_DaisTop", (12.0, 3.0, 0.08), (0, 5.7, 1.04), MARBLE, parts=parts)
    add_box("Darbar_Step1", (12.0, 0.7, 0.66), (0, 3.85, 0.33), SAND, parts=parts)
    add_box("Darbar_Step2", (12.0, 0.7, 0.33), (0, 3.15, 0.165), SAND, parts=parts)

    # golden throne + red cushion + canopy
    add_box("Throne_Base", (2.6, 1.9, 0.55), (0, 6.15, 1.28), GOLD, parts=parts)
    add_box("Throne_Cushion", (2.1, 1.5, 0.22), (0, 6.15, 1.67), RED, parts=parts)
    add_box("Throne_Back", (2.6, 0.32, 2.3), (0, 6.95, 2.2), GOLD, parts=parts)
    for sx in (-1.15, 1.15):
        add_box(f"Throne_Arm{sx}", (0.28, 1.7, 0.55), (sx, 6.15, 1.75), GOLD, parts=parts)
        add_cylinder(f"Throne_CanopyPost{sx}", 0.07, 2.7, (sx, 6.9, 2.9), GOLD,
                     verts=8, parts=parts)
    add_box("Throne_Canopy", (2.9, 1.9, 0.16), (0, 6.55, 4.25), TEAL, parts=parts)
    add_box("Throne_CanopyTrim", (3.0, 2.0, 0.08), (0, 6.55, 4.35), GOLD, parts=parts)
    for sx in (-1.1, 0.0, 1.1):
        add_cone(f"Throne_Finial{sx}", 0.16, 0.0, 0.5, (sx, 6.95, 3.6), GOLD,
                 verts=10, parts=parts)

    # 8 ornate pillars with red / blue / yellow bands
    for sx in (-6.5, -2.5, 2.5, 6.5):
        for sy in (-3.2, 3.2):
            add_pillar(f"Darbar_Pillar{sx}_{sy}", sx, sy, 0.32, H, parts=parts)

    # chandelier
    add_torus("Darbar_ChandelierRing", 1.0, 0.07, (0, 0, 4.2), GOLD, seg=20, ring=6,
              parts=parts)
    for i in range(6):
        a = math.radians(i * 60)
        add_sphere(f"Darbar_Bulb{i}", 0.11,
                   (1.0 * math.cos(a), 1.0 * math.sin(a), 4.2), YELLOW,
                   seg=8, rings=4, parts=parts)
    add_cylinder("Darbar_ChandelierChain", 0.035, 1.8, (0, 0, 5.1), GOLD, verts=6,
                 parts=parts)

    obj = join_parts(parts, "Room_DarbarHall")
    return obj


# ============================================================================
# ROOM 2 — COURTYARD / AANGAN  (20 x 20 x 6, open to sky)
# ============================================================================
def build_courtyard() -> bpy.types.Object:
    S, H = COURT_W, ROOM_H
    parts: list[bpy.types.Object] = []

    # sandstone + marble floor
    add_box("Court_FloorBase", (S, S, 0.3), (0, 0, 0.15), SAND, parts=parts)
    add_checker_floor("Court_Tile", -10.0, 10.0, -10.0, 10.0, 2.0, 0.30,
                      SAND, MARBLE, parts=parts)
    # marble border ring
    for name, size, loc in [
        ("Court_BorderN", (20.0, 0.7, 0.06), (0, 9.65, 0.33)),
        ("Court_BorderS", (20.0, 0.7, 0.06), (0, -9.65, 0.33)),
        ("Court_BorderE", (0.7, 20.0, 0.06), (9.65, 0, 0.33)),
        ("Court_BorderW", (0.7, 20.0, 0.06), (-9.65, 0, 0.33)),
    ]:
        add_box(name, size, loc, MARBLE, parts=parts)

    # ---- arcade (jharokha walkways) on all 4 sides ------------------------
    # raised walkway platform, 2.4 m deep
    for side in "NSEW":
        if side == "N":
            add_box("Court_WalkN", (20.0, 2.4, 0.35), (0, 8.8, 0.175), MARBLE, parts=parts)
        elif side == "S":
            add_box("Court_WalkS", (20.0, 2.4, 0.35), (0, -8.8, 0.175), MARBLE, parts=parts)
        elif side == "E":
            add_box("Court_WalkE", (2.4, 20.0, 0.35), (8.8, 0, 0.175), MARBLE, parts=parts)
        else:
            add_box("Court_WalkW", (2.4, 20.0, 0.35), (-8.8, 0, 0.175), MARBLE, parts=parts)

    # columns + arched spandrel panels.  centre bay stays open as passage.
    offsets = (-9.5, -5.5, -1.5, 1.5, 5.5, 9.5)
    for side in "NSEW":
        for i, t in enumerate(offsets):
            if side in "NS":
                x, y = t, (7.75 if side == "N" else -7.75)
            else:
                x, y = (7.75 if side == "E" else -7.75), t
            add_cylinder(f"Court_Col{side}{i}", 0.28, 5.65,
                         (x, y, 0.35 + 5.65 / 2), SAND, verts=12, parts=parts)
            add_torus(f"Court_ColCap{side}{i}", 0.32, 0.09, (x, y, 5.55), GOLD,
                      seg=12, ring=6, parts=parts)
        # arched panels between columns (skip the central passage bay)
        for i in range(len(offsets) - 1):
            if i == 2:      # central bay = passage, left open
                continue
            a, b = offsets[i], offsets[i + 1]
            mid = (a + b) / 2.0
            bay = abs(b - a) - 0.56
            if side in "NS":
                panel = add_box(f"Court_Panel{side}{i}", (bay, 0.34, 1.6),
                                (mid, 7.75 if side == "N" else -7.75, 5.2),
                                PINK, parts=parts)
                cut = add_cylinder(f"Court_PanelCut{side}{i}", 1.30, 0.9,
                                   (mid, 7.75 if side == "N" else -7.75, 4.4),
                                   PINK, verts=20, rot=(math.pi / 2, 0, 0))
            else:
                panel = add_box(f"Court_Panel{side}{i}", (0.34, bay, 1.6),
                                (7.75 if side == "E" else -7.75, mid, 5.2),
                                PINK, parts=parts)
                cut = add_cylinder(f"Court_PanelCut{side}{i}", 1.30, 0.9,
                                   (7.75 if side == "E" else -7.75, mid, 4.4),
                                   PINK, verts=20, rot=(math.pi / 2, 0, 0))
            boolean(panel, cut)
            add_box(f"Court_PanelTrim{side}{i}", (bay, 0.42, 0.14),
                    (mid, 7.75 if side == "N" else -7.75, 6.0), GOLD, parts=parts) \
                if side in "NS" else \
                add_box(f"Court_PanelTrim{side}{i}", (0.42, bay, 0.14),
                        (7.75 if side == "E" else -7.75, mid, 6.0), GOLD, parts=parts)

    # ---- marble fountain, exact centre -----------------------------------
    add_cylinder("Fountain_Basin", 2.4, 0.7, (0, 0, 0.65), MARBLE, verts=24, parts=parts)
    add_torus("Fountain_Rim", 2.35, 0.12, (0, 0, 1.0), GOLD, seg=24, ring=8, parts=parts)
    add_cylinder("Fountain_Water", 2.15, 0.12, (0, 0, 0.86), BLUE, verts=24, parts=parts)
    add_cylinder("Fountain_Pedestal", 0.55, 1.2, (0, 0, 1.6), MARBLE, verts=16, parts=parts)
    add_cylinder("Fountain_Bowl", 1.15, 0.28, (0, 0, 2.2), MARBLE, verts=20, parts=parts)
    add_cylinder("Fountain_WaterTop", 1.0, 0.1, (0, 0, 2.36), BLUE, verts=20, parts=parts)
    add_cylinder("Fountain_Column", 0.22, 0.9, (0, 0, 2.85), MARBLE, verts=12, parts=parts)
    add_cone("Fountain_Finial", 0.26, 0.0, 0.55, (0, 0, 3.55), GOLD, verts=12, parts=parts)

    # four small teal chhatris on the courtyard rim (roof level)
    for sx, sy in ((-9.0, -9.0), (9.0, -9.0), (-9.0, 9.0), (9.0, 9.0)):
        add_box(f"Court_ChhatriPlat{sx}_{sy}", (1.8, 1.8, 0.28),
                (sx, sy, 6.14), MARBLE, parts=parts)
        for dx, dy in ((-0.65, -0.65), (0.65, -0.65), (-0.65, 0.65), (0.65, 0.65)):
            add_cylinder(f"Court_ChhatriCol{sx}_{sy}_{dx}_{dy}", 0.10, 1.5,
                         (sx + dx, sy + dy, 7.0), GOLD, verts=8, parts=parts)
        add_dome(f"Court_Chhatri{sx}_{sy}", sx, sy, 7.75, 0.95, TEAL, parts=parts)

    obj = join_parts(parts, "Room_Courtyard")
    return obj


# ============================================================================
# ROOM 3 — RANIVAS  (15 x 10 x 6)
# ============================================================================
def build_ranivas() -> bpy.types.Object:
    W, D, H = RANIVAS_W, RANIVAS_D, ROOM_H
    parts: list[bpy.types.Object] = []

    add_box("Rani_FloorBase", (W, D, 0.3), (0, 0, 0.15), SAND, parts=parts)
    add_checker_floor("Rani_Tile", -7.0, 7.0, -4.5, 4.5, 1.5, 0.30,
                      MARBLE, SAND, parts=parts)
    # corridor runner
    add_box("Rani_Corridor", (3.0, 9.0, 0.10), (0, 0, 0.40), MARBLE, parts=parts)

    # outer walls
    north = add_box("Rani_WallN", (W, WALL_T, H), (0, D / 2 - WALL_T / 2, H / 2),
                    PINK, parts=parts)
    south = add_box("Rani_WallS", (W, WALL_T, H), (0, -D / 2 + WALL_T / 2, H / 2),
                    PINK, parts=parts)
    east = add_box("Rani_WallE", (WALL_T, D, H), (W / 2 - WALL_T / 2, 0, H / 2),
                   PINK, parts=parts)
    west = add_box("Rani_WallW", (WALL_T, D, H), (-W / 2 + WALL_T / 2, 0, H / 2),
                   PINK, parts=parts)

    # inner dividers at x = +/-1.6 with a 2 m door in the middle
    for sx in (-1.6, 1.6):
        for sy in (-2.75, 2.75):
            add_box(f"Rani_Divider{sx}_{sy}", (0.40, 3.5, H), (sx, sy, H / 2),
                    ROSE, parts=parts)
        add_box(f"Rani_DividerLintel{sx}", (0.40, 2.0, 2.2), (sx, 0, H - 1.1),
                ROSE, parts=parts)

    # doors to the courtyard (west) and to the outer garden (east)
    for side, wx, orient in (("W", -W / 2 + WALL_T / 2, "y"),
                             ("E", W / 2 - WALL_T / 2, "y")):
        wall = west if side == "W" else east
        cut = arch_cutter(f"Rani_DoorCut{side}", 2.6, 2.4, 1.3, WALL_T + 3.0,
                          wx, 0.0, 0.0, orient=orient)
        boolean(wall, cut)
        arch_trim(f"Rani_DoorTrim{side}", wx, 0.0, 0.0, 2.4, 1.3, GOLD,
                  orient=orient, thickness=0.2, parts=parts)

    # corridor windows on the north + south walls
    for side, wy in (("N", D / 2 - WALL_T / 2), ("S", -D / 2 + WALL_T / 2)):
        wall = north if side == "N" else south
        add_window(wall, f"Rani_Win{side}", 0.0, wy, 2.2, 2.2, 1.6, 1.1,
                   orient="x", parts=parts)

    # coloured geometric cube pattern on the long outer facades
    cols = (ORANGE, YELLOW, BLUE, TEAL, ROSE)
    for side, wy, facing in (("N", D / 2, 1), ("S", -D / 2, -1)):
        for i in range(15):
            x = -6.6 + i * 0.94
            for j in range(6):
                z = 1.1 + j * 0.62
                # chevron / diamond mask
                if abs(x) * 0.55 + abs(z - 3.0) * 0.9 > 4.6:
                    continue
                if (i + j) % 3 == 0:
                    continue
                mat = cols[(i * 2 + j) % len(cols)]
                add_box(f"Rani_Pattern{side}_{i}_{j}", (0.34, 0.18, 0.34),
                        (x, wy + facing * 0.09, z), mat, parts=parts)

    # 2 balconies on the outer (+X) facade
    for sy in (-2.6, 2.6):
        add_box(f"Rani_Balcony{sy}", (1.5, 3.0, 0.25), (W / 2 + 0.70, sy, 3.0),
                MARBLE, parts=parts)
        add_box(f"Rani_BalconyRail{sy}", (0.12, 3.0, 0.75), (W / 2 + 1.38, sy, 3.5),
                GOLD, parts=parts)
        for k in range(5):
            add_box(f"Rani_Baluster{sy}_{k}", (0.10, 0.10, 0.65),
                    (W / 2 + 1.38, sy - 1.2 + k * 0.6, 3.45), GOLD, parts=parts)
        for dy in (-1.35, 1.35):
            add_cylinder(f"Rani_BalconyPost{sy}_{dy}", 0.10, 2.0,
                         (W / 2 + 1.25, sy + dy, 4.05), PINK, verts=8, parts=parts)
        add_cone(f"Rani_BalconyRoof{sy}", 1.15, 0.0, 0.85,
                 (W / 2 + 0.85, sy, 5.45), GOLD, verts=16, parts=parts)

    obj = join_parts(parts, "Room_Ranivas")
    return obj


# ============================================================================
# ROOM 4 — GATEWAY  (15 x 5 x 8.4) with scalloped Mehrab
# ============================================================================
GATE_RECT_H = 4.4
GATE_SCALLOP_H = 2.2
GATE_HALF_W = 3.0
GATE_LOBES = 5
GATE_FOIL_R = 0.70


def scallop_centres() -> list[tuple[float, float]]:
    """Foils of the cusped Mehrab arch, along a true semi-ellipse."""
    out = []
    for i in range(GATE_LOBES):
        t = (i + 0.5) / GATE_LOBES
        ang = math.pi * (1.0 - t)
        out.append((GATE_HALF_W * math.cos(ang),
                    GATE_RECT_H + GATE_SCALLOP_H * math.sin(ang)))
    return out


def build_gateway() -> bpy.types.Object:
    W, D, H = GATE_W, GATE_D, GATE_H
    parts: list[bpy.types.Object] = []

    add_box("Gate_FloorBase", (W, D, 0.3), (0, 0, 0.15), SAND, parts=parts)
    add_box("Gate_Runner", (2.6, D, 0.10), (0, 0, 0.35), MARBLE, parts=parts)

    # main gate block
    gate = add_box("Gate_Block", (W, D, H), (0, 0, H / 2), PINK, parts=parts)

    # scalloped opening cutter: rectangular shaft + 5 circle foils
    cutter = add_box("Gate_CutRect", (GATE_HALF_W * 2.0 + 0.02, D + 2.0, GATE_RECT_H),
                     (0, 0, GATE_RECT_H / 2), PINK)
    for idx, (fx, fz) in enumerate(scallop_centres()):
        foil = add_cylinder(f"Gate_Foil{idx}", GATE_FOIL_R, D + 2.0, (fx, 0, fz),
                            PINK, verts=24, rot=(math.pi / 2, 0, 0))
        boolean(cutter, foil, operation="UNION")
    boolean(gate, cutter)

    # multi-layered scalloped frame — pink outer ring + gold inner ring
    front_y = -D / 2 - 0.02
    for idx, (fx, fz) in enumerate(scallop_centres()):
        add_torus(f"Gate_MehrabPink{idx}", GATE_FOIL_R + 0.18, 0.17,
                  (fx, front_y - 0.10, fz), ROSE, seg=20, ring=8,
                  rot=(math.pi / 2, 0, 0), parts=parts)
        add_torus(f"Gate_MehrabGold{idx}", GATE_FOIL_R + 0.01, 0.11,
                  (fx, front_y - 0.24, fz), GOLD, seg=20, ring=8,
                  rot=(math.pi / 2, 0, 0), parts=parts)
    # gold jamb posts + pink outer jamb
    for sx in (-1, 1):
        add_box(f"Gate_JambGold{sx}", (0.22, 0.20, GATE_RECT_H + 0.4),
                (sx * (GATE_HALF_W + 0.11), front_y - 0.24, (GATE_RECT_H + 0.4) / 2),
                GOLD, parts=parts)
        add_box(f"Gate_JambPink{sx}", (0.44, 0.28, GATE_RECT_H + 0.9),
                (sx * (GATE_HALF_W + 0.40), front_y - 0.06, (GATE_RECT_H + 0.9) / 2),
                ROSE, parts=parts)
        # green/blue spandrel inlay either side of the arch
        add_box(f"Gate_Spandrel{sx}", (3.2, 0.14, 2.0),
                (sx * 5.0, front_y - 0.02, 5.4), BLUE, parts=parts)
        add_box(f"Gate_SpandrelTrim{sx}", (3.4, 0.18, 0.18),
                (sx * 5.0, front_y - 0.06, 6.45), GOLD, parts=parts)

    # gold banding on the facade
    add_box("Gate_BandTop", (W, 0.18, 0.30), (0, front_y, H - 0.55), GOLD, parts=parts)
    add_box("Gate_BandBase", (W, 0.18, 0.22), (0, front_y, 0.42), GOLD, parts=parts)

    # two massive wooden leaves, swung open inwards (+Y)
    for sgn, angle in ((-1, 65.0), (1, -65.0)):
        hinge_x = sgn * GATE_HALF_W
        leaf_parts: list[bpy.types.Object] = []
        bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, 0, 0))
        leaf = bpy.context.active_object
        leaf.name = "Gate_Leaf"
        leaf.scale = (GATE_HALF_W, 0.16, GATE_RECT_H - 0.15)
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        # hinge at local origin, leaf extends toward the centre
        leaf.data.transform(Matrix.Translation((-sgn * GATE_HALF_W / 2.0, 0.0,
                                                (GATE_RECT_H - 0.15) / 2.0)))
        leaf_parts.append(leaf)
        # 3 plank battens + gold studs
        for k in range(3):
            add_box(f"Gate_LeafPlank{k}", (GATE_HALF_W * 0.92, 0.06, 0.20),
                    (-sgn * GATE_HALF_W / 2.0, -0.11,
                     (GATE_RECT_H - 0.15) * (0.22 + 0.28 * k)), WOOD_DARK,
                    parts=leaf_parts)
        for ix in range(3):
            for iz in range(4):
                add_sphere(f"Gate_Stud{ix}_{iz}", 0.055,
                           (-sgn * (0.35 + ix * 1.05), -0.10,
                            0.55 + iz * 1.10), GOLD, seg=8, rings=4,
                           parts=leaf_parts)
        bpy.ops.object.select_all(action="DESELECT")
        for p in leaf_parts:
            p.select_set(True)
        bpy.context.view_layer.objects.active = leaf
        bpy.ops.object.join()
        leaf = bpy.context.active_object
        leaf.name = f"Gate_Leaf{'L' if sgn < 0 else 'R'}"
        leaf.data.materials.clear()
        leaf.data.materials.append(WOOD)
        leaf.location = (hinge_x, -D / 2 + 0.30, 0.0)
        leaf.rotation_euler = (0.0, 0.0, math.radians(angle))
        parts.append(leaf)

    # flanking towers with gold domed chhatris
    for sx in (-6.2, 6.2):
        add_box(f"Gate_Tower{sx}", (2.2, D, 8.9), (sx, 0, 4.45), PINK, parts=parts)
        for k, z in enumerate((1.2, 4.4, 7.1)):
            add_box(f"Gate_TowerBand{sx}_{k}", (2.4, D + 0.10, 0.22), (sx, 0, z),
                    GOLD, parts=parts)
        add_box(f"Gate_TowerCap{sx}", (2.7, D + 0.4, 0.26), (sx, 0, 9.03), MARBLE,
                parts=parts)
        for dx, dy in ((-0.72, -0.72), (0.72, -0.72), (-0.72, 0.72), (0.72, 0.72)):
            add_cylinder(f"Gate_TowerCol{sx}_{dx}_{dy}", 0.09, 1.2,
                         (sx + dx, dy * 1.6, 9.76), GOLD, verts=8, parts=parts)
        add_dome(f"Gate_TowerDome{sx}", sx, 0, 10.2, 0.95, YELLOW, parts=parts,
                 seg=14, rings=7)

    obj = join_parts(parts, "Room_Gateway")
    return obj


# ============================================================================
# TASK 2 — ASSEMBLY
# ============================================================================
def _instance(mesh: bpy.types.Mesh, name: str, loc, rot_z=0.0, scale=1.0):
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (0.0, 0.0, rot_z)
    obj.scale = (scale, scale, scale)
    return obj


def _solid_block(prefix, x0, x1, y0, y1, height, parts, facade_axis=None,
                 facade_value=None):
    """Service wing filling a corner void: solid body, gold bands, blind arches."""
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    sx, sy = abs(x1 - x0), abs(y1 - y0)
    add_box(f"{prefix}_Body", (sx, sy, height), (cx, cy, height / 2.0), PINK,
            parts=parts)
    for k, z in enumerate((height - 0.5, height * 0.62)):
        add_box(f"{prefix}_Band{k}", (sx + 0.12, sy + 0.12, 0.22), (cx, cy, z),
                GOLD, parts=parts)
    # blind blue arches on the outward facade
    if facade_axis == "x":      # facade runs along X at y = facade_value
        for i, fx in enumerate((cx - sx * 0.30, cx, cx + sx * 0.30)):
            add_arch_panel(f"{prefix}_Arch{i}", fx, facade_value, 2.6, 1.9, 1.0, "x",
                           parts)
    elif facade_axis == "y":    # facade runs along Y at x = facade_value
        for i, fy in enumerate((cy - sy * 0.30, cy, cy + sy * 0.30)):
            add_arch_panel(f"{prefix}_Arch{i}", facade_value, fy, 2.6, 1.9, 1.0, "y",
                           parts)


def add_arch_panel(prefix, cx, cy, width, rect_h, radius, orient, parts):
    """Blue inlay arch with a gold outline, sitting slightly proud of a wall."""
    panel = arch_cutter(f"{prefix}_Panel", width, rect_h, radius, 0.22,
                        cx, cy, 0.0, orient=orient)
    panel.data.materials.clear()
    panel.data.materials.append(BLUE)
    parts.append(panel)
    arch_trim(f"{prefix}_Trim", cx, cy, 0.0, rect_h, radius, GOLD,
              orient=orient, thickness=0.16, parts=parts)


def assemble_mahal(darbar, courtyard, ranivas, gateway) -> bpy.types.Object:
    parts: list[bpy.types.Object] = []
    meshes = {
        "dar": darbar.data,
        "court": courtyard.data,
        "rani": ranivas.data,
        "gate": gateway.data,
    }
    for o in (darbar, courtyard, ranivas, gateway):
        bpy.data.objects.remove(o, do_unlink=True)

    # ---------------- ground floor: exact positions from the brief ---------
    court_inst = _instance(meshes["court"], "Mega_Courtyard", POS_COURT)
    parts.append(court_inst)
    parts.append(_instance(meshes["dar"], "Mega_Darbar", POS_DARBAR))
    parts.append(_instance(meshes["rani"], "Mega_RanivasE", POS_RANIVAS_E, 0.0, 1.0))
    parts.append(_instance(meshes["rani"], "Mega_RanivasW", POS_RANIVAS_W, math.pi, 1.0))
    parts.append(_instance(meshes["gate"], "Mega_Gateway", POS_GATE))

    # ---------------- corner service wings (fill the cross-plan voids) -----
    # NE / NW : between darbar (Y>=10) and ranivas (Y<=5)  -> y 5..25
    _solid_block("Mega_WingNE", 10.0, 25.0, 5.0, 25.0, ROOM_H, parts,
                 facade_axis="x", facade_value=25.0)
    _solid_block("Mega_WingNW", -25.0, -10.0, 5.0, 25.0, ROOM_H, parts,
                 facade_axis="x", facade_value=25.0)
    # SE / SW : south of ranivas -> y -15..-5
    _solid_block("Mega_WingSE", 10.0, 25.0, -15.0, -5.0, ROOM_H, parts,
                 facade_axis="x", facade_value=-15.0)
    _solid_block("Mega_WingSW", -25.0, -10.0, -15.0, -5.0, ROOM_H, parts,
                 facade_axis="x", facade_value=-15.0)
    # small strips flanking the gateway
    _solid_block("Mega_WingSE2", 7.5, 10.0, -15.0, -10.0, ROOM_H, parts)
    _solid_block("Mega_WingSW2", -10.0, -7.5, -15.0, -10.0, ROOM_H, parts)

    # ---------------- flat roof deck (everything except the courtyard) ----
    deck_z = ROOM_H            # 6.0
    deck_t = 0.4
    # north block (darbar footprint)
    add_box("Mega_RoofN", (50.0, 15.0, deck_t), (0.0, 17.5, deck_z + deck_t / 2),
            SAND, parts=parts)
    # east + west wings (beside the courtyard)
    add_box("Mega_RoofE", (15.0, 20.0, deck_t), (17.5, 0.0, deck_z + deck_t / 2),
            SAND, parts=parts)
    add_box("Mega_RoofW", (15.0, 20.0, deck_t), (-17.5, 0.0, deck_z + deck_t / 2),
            SAND, parts=parts)
    # south strips, leaving the gateway free-standing
    add_box("Mega_RoofSE", (17.5, 5.0, deck_t), (16.25, -12.5, deck_z + deck_t / 2),
            SAND, parts=parts)
    add_box("Mega_RoofSW", (17.5, 5.0, deck_t), (-16.25, -12.5, deck_z + deck_t / 2),
            SAND, parts=parts)

    # ---------------- second floor: same rooms, scaled 0.85 ---------------
    f2 = FLOOR2_Z
    add_box("Mega_RoofDarbar2", (DARBAR_W * SECOND_SCALE + 0.6,
                                 DARBAR_D * SECOND_SCALE + 0.6, 0.4),
            (0.0, 17.5, f2 + ROOM_H * SECOND_SCALE + 0.2), SAND, parts=parts)
    for sx in (17.5, -17.5):
        add_box(f"Mega_RoofRani2_{sx}", (RANIVAS_W * SECOND_SCALE + 0.5,
                                         RANIVAS_D * SECOND_SCALE + 0.5, 0.4),
                (sx, 0.0, f2 + ROOM_H * SECOND_SCALE + 0.2), SAND, parts=parts)

    # +0.02 m lift avoids coplanar z-fighting between room floors and the deck
    parts.append(_instance(meshes["dar"], "Mega_DarbarF2", (0.0, 17.5, f2 + 0.02),
                           0.0, SECOND_SCALE))
    parts.append(_instance(meshes["rani"], "Mega_RanivasEF2", (17.5, 0.0, f2 + 0.02),
                           0.0, SECOND_SCALE))
    parts.append(_instance(meshes["rani"], "Mega_RanivasWF2", (-17.5, 0.0, f2 + 0.02),
                           math.pi, SECOND_SCALE))
    parts.append(_instance(meshes["gate"], "Mega_GatewayF2", (0.0, -12.5, GATE_H + 0.02),
                           0.0, GATE_SECOND_SCALE))
    # little roof over the upper gate pavilion
    add_box("Mega_RoofGate2", (GATE_W * GATE_SECOND_SCALE + 0.5,
                               GATE_D * GATE_SECOND_SCALE + 0.5, 0.35),
            (0.0, -12.5, GATE_H + GATE_H * GATE_SECOND_SCALE + 0.17), SAND,
            parts=parts)

    # ---------------- crenellated parapet around the whole roof -----------
    add_crenellations(parts, PLAN_X0, PLAN_X1, PLAN_Y0, PLAN_Y1, FLOOR2_Z + 0.4)
    # parapet around the courtyard opening (roof edge safety rail)
    court_half = COURT_W / 2.0
    for name, size, loc in [
        ("Mega_CourtParapetN", (COURT_W + 1.2, 0.45, 0.95), (0, court_half + 0.25, FLOOR2_Z + 0.87)),
        ("Mega_CourtParapetS", (COURT_W + 1.2, 0.45, 0.95), (0, -court_half - 0.25, FLOOR2_Z + 0.87)),
        ("Mega_CourtParapetE", (0.45, COURT_D + 1.2, 0.95), (court_half + 0.25, 0, FLOOR2_Z + 0.87)),
        ("Mega_CourtParapetW", (0.45, COURT_D + 1.2, 0.95), (-court_half - 0.25, 0, FLOOR2_Z + 0.87)),
    ]:
        add_box(name, size, loc, PINK, parts=parts)
        add_box(name + "Cap", (size[0] + 0.14, size[1] + 0.14, 0.14),
                (loc[0], loc[1], loc[2] + 0.54), GOLD, parts=parts)

    # ---------------- CENTRAL TEAL DOME (over the darbar) -----------------
    drum_z = f2 + ROOM_H * SECOND_SCALE + 0.4      # 11.9
    add_cylinder("Mega_DomeDrum", 4.7, 1.2, (0.0, 17.5, drum_z + 0.6), MARBLE,
                 verts=24, parts=parts)
    add_torus("Mega_DomeDrumRing", 4.7, 0.20, (0.0, 17.5, drum_z + 1.2), GOLD,
              seg=24, ring=8, parts=parts)
    add_dome("Mega_CentralDome", 0.0, 17.5, drum_z + 1.2, 4.6, TEAL, seg=20,
             rings=10, parts=parts)

    # ---------------- 4 smaller GOLDEN corner domes -----------------------
    for cx, cy in ((-21.0, 21.0), (21.0, 21.0), (-21.0, -11.5), (21.0, -11.5)):
        add_box(f"Mega_CornerPlat{cx}_{cy}", (3.4, 3.4, 0.4),
                (cx, cy, FLOOR2_Z + 0.6), MARBLE, parts=parts)
        for dx, dy in ((-1.2, -1.2), (1.2, -1.2), (-1.2, 1.2), (1.2, 1.2)):
            add_cylinder(f"Mega_CornerCol{cx}_{cy}_{dx}_{dy}", 0.16, 1.7,
                         (cx + dx, cy + dy, FLOOR2_Z + 1.65), GOLD, verts=10,
                         parts=parts)
        add_dome(f"Mega_CornerDome{cx}_{cy}", cx, cy, FLOOR2_Z + 2.5, 2.1,
                 YELLOW, parts=parts)

    # ---------------- upper-level details ---------------------------------
    # parapet crenellations around the 2nd floor darbar
    add_crenellations(parts, -DARBAR_W * SECOND_SCALE / 2 + 0.9,
                      DARBAR_W * SECOND_SCALE / 2 - 0.9,
                      17.5 - DARBAR_D * SECOND_SCALE / 2 + 0.7,
                      17.5 + DARBAR_D * SECOND_SCALE / 2 - 0.7,
                      f2 + ROOM_H * SECOND_SCALE + 0.4, spacing=2.2)
    # banners on the central dome drum
    for i in range(4):
        a = math.radians(45 + i * 90)
        add_cylinder(f"Mega_FlagPole{i}", 0.06, 2.2,
                     (4.9 * math.cos(a), 17.5 + 4.9 * math.sin(a), drum_z + 2.3),
                     GOLD, verts=6, parts=parts)
        add_box(f"Mega_Flag{i}", (0.05, 0.9, 0.55),
                (4.9 * math.cos(a) + 0.28, 17.5 + 4.9 * math.sin(a) + 0.45,
                 drum_z + 3.1), [RED, YELLOW, TEAL, ORANGE][i], parts=parts)

    # ---------------- join everything into ONE mesh -----------------------
    mega = join_parts(parts, "RajasthaniMahalMega")
    mega.data.name = "rajasthani_mahal_mega"

    # safety: make sure the floor is exactly at z = 0
    min_z = min(v.co.z for v in mega.data.vertices)
    if abs(min_z) > 1e-6:
        mega.data.transform(Matrix.Translation((0.0, 0.0, -min_z)))
    mega.location = (0.0, 0.0, 0.0)
    mega.rotation_euler = (0.0, 0.0, 0.0)
    mega.scale = (1.0, 1.0, 1.0)
    return mega


def add_crenellations(parts, x0, x1, y0, y1, z, spacing=2.4, mat_a=PINK,
                      mat_b=YELLOW):
    """Alternating pink / yellow merlons around a rectangular roof edge."""
    nx = int(round((x1 - x0) / spacing))
    ny = int(round((y1 - y0) / spacing))
    k = 0
    for i in range(nx + 1):
        x = x0 + i * (x1 - x0) / nx
        for y in (y0 + 0.22, y1 - 0.22):
            add_box(f"CrenN{k}", (0.62, 0.44, 0.72), (x, y, z + 0.36),
                    mat_a if k % 2 == 0 else mat_b, parts=parts)
            k += 1
    for j in range(1, ny):
        y = y0 + j * (y1 - y0) / ny
        for x in (x0 + 0.22, x1 - 0.22):
            add_box(f"CrenE{k}", (0.44, 0.62, 0.72), (x, y, z + 0.36),
                    mat_a if k % 2 == 0 else mat_b, parts=parts)
            k += 1


# ============================================================================
# EXPORT / VERIFY
# ============================================================================
def object_bbox(obj):
    coords = [obj.matrix_world @ v.co for v in obj.data.vertices]
    return (min(c.x for c in coords), max(c.x for c in coords),
            min(c.y for c in coords), max(c.y for c in coords),
            min(c.z for c in coords), max(c.z for c in coords))


def export_glb(obj, path, name=None):
    if name:
        obj.name = name
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(filepath=path, export_format="GLB",
                              use_selection=True, export_apply=True)
    if not os.path.isfile(path):
        raise RuntimeError(f"export failed: {path}")
    return path


def glb_stats(path):
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"glTF":
        raise RuntimeError(f"not a GLB: {path}")
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_len])
    tris = 0
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if "indices" in prim:
                tris += gltf["accessors"][prim["indices"]]["count"] // 3
            else:
                tris += gltf["accessors"][prim["attributes"]["POSITION"]]["count"] // 3
    return {"bytes": os.path.getsize(path), "mats": len(gltf.get("materials", [])),
            "tris": tris, "nodes": len(gltf.get("nodes", []))}


def verify_import(path, label):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=path)
    objs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not objs:
        raise RuntimeError(f"no mesh imported from {path}")
    xs, ys, zs = [], [], []
    for o in objs:
        for corner in o.bound_box:
            w = o.matrix_world @ Vector(corner)
            xs.append(w.x); ys.append(w.y); zs.append(w.z)
    mats = {m.name for o in objs for m in o.data.materials if m}
    dims = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    st = glb_stats(path)
    print(f"  {label}: {dims[0]:.2f} x {dims[1]:.2f} x {dims[2]:.2f} m | "
          f"minZ {min(zs):+.3f} | {st['tris']} tris | {len(mats)} mats | "
          f"{st['bytes'] / 1024:.0f} KB")
    return dims, min(zs), st


# ============================================================================
# MAIN
# ============================================================================
def main():
    print(f"Blender bpy {bpy.app.version_string}")

    print("— TASK 1: building 4 room blocks —")
    darbar = build_darbar()
    print(f"  darbar   {object_bbox(darbar)[0]:.1f}..{object_bbox(darbar)[1]:.1f} X, "
          f"{len(darbar.data.polygons)} faces")
    courtyard = build_courtyard()
    print(f"  courtyard {len(courtyard.data.polygons)} faces")
    ranivas = build_ranivas()
    print(f"  ranivas  {len(ranivas.data.polygons)} faces")
    gateway = build_gateway()
    print(f"  gateway  {len(gateway.data.polygons)} faces")

    exports = [
        (darbar, os.path.join(OUT_ROOMS, "room_darbar_hall.glb")),
        (courtyard, os.path.join(OUT_ROOMS, "room_courtyard.glb")),
        (ranivas, os.path.join(OUT_ROOMS, "room_ranivas.glb")),
        (gateway, os.path.join(OUT_ROOMS, "room_gateway.glb")),
    ]
    print("— exporting room blocks —")
    for obj, path in exports:
        export_glb(obj, path)
        x0, x1, y0, y1, z0, z1 = object_bbox(obj)
        st = glb_stats(path)
        print(f"  {os.path.basename(path)}: {x1 - x0:.2f} x {y1 - y0:.2f} x "
              f"{z1 - z0:.2f} m | origin bottom-centre | {st['tris']} tris | "
              f"{st['bytes'] / 1024:.0f} KB")

    print("— TASK 2: assemble_mahal() —")
    mega = assemble_mahal(darbar, courtyard, ranivas, gateway)
    mega_path = os.path.join(OUT_ROOT, "rajasthani_mahal_mega.glb")
    export_glb(mega, mega_path, "rajasthani_mahal_mega")
    x0, x1, y0, y1, z0, z1 = object_bbox(mega)
    st = glb_stats(mega_path)
    print(f"  rajasthani_mahal_mega: {x1 - x0:.2f} x {y1 - y0:.2f} x {z1 - z0:.2f} m "
          f"| {len(mega.data.polygons)} faces | {st['tris']} tris | "
          f"{st['bytes'] / 1024 / 1024:.2f} MB | minZ {z0:+.3f}")

    print("— verification (re-import) —")
    for obj, path in exports:
        verify_import(path, os.path.basename(path))
    verify_import(mega_path, "rajasthani_mahal_mega.glb")

    print("Done — Rajasthani Mahal rooms + mega assembly generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
