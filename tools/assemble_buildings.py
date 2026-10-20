#!/usr/bin/env python3
"""
Assemble the 11 Battle-Royale buildings from the 15 m modular kit.
=================================================================
Imports the modules from docs/models/modules/ and places them at exact X / Y / Z
coordinates on a **15 m grid** (3 m storeys, 0.2 m slabs), re-skins every wall in
the building's own palette and drops furniture inside without blocking doors or
stairs.  Each building is joined into ONE mesh and exported.

Why they all look different
  · footprint     1x1 / 2x1 / 2x2 / 3x2 / L-shaped
  · height        1 - 4 storeys
  · wall colour   6 wall colours + steel blue / damaged concrete / camo green
  · roof          flat + parapet, hip (4 colours), or none
  · features      awnings, roof terrace, garage doors, camo bands, rubble

Output: docs/models/buildings_modular/<name>.glb
"""
from __future__ import annotations

import json
import math
import os
import random
import struct
import sys

import bpy  # noqa: E402  (must be imported before bmesh / mathutils)
import bmesh
from mathutils import Matrix, Vector

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_DIR = os.path.join(REPO_ROOT, "docs", "models", "modules")
OUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "buildings_modular")
os.makedirs(OUT_DIR, exist_ok=True)

GRID = 15.0          # module footprint
STOREY = 3.0         # wall module height
SLAB = 0.2           # floor slab thickness
WALL_T = 0.2

bpy.ops.wm.read_factory_settings(use_empty=True)


# ----------------------------------------------------------------------------
# TASK 1 — palette (hex sRGB -> linear so the exported GLB shows the hex)
# ----------------------------------------------------------------------------
def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_color(hex_str: str) -> tuple[float, float, float]:
    h = hex_str.lstrip("#")
    return tuple(srgb_to_linear(int(h[i:i + 2], 16) / 255.0) for i in (0, 2, 4))


_MATS: dict[str, bpy.types.Material] = {}


def mat(name: str, hex_str: str, rough: float = 0.8,
        metal: float = 0.0) -> bpy.types.Material:
    if name in _MATS:
        return _MATS[name]
    m = bpy.data.materials.new(name=name)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    rgb = hex_color(hex_str)
    bsdf.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    m.diffuse_color = (rgb[0], rgb[1], rgb[2], 1.0)
    _MATS[name] = m
    return m


# name -> (hex, roughness, metallic)
PALETTE = {
    # ---------------- WALL COLOURS (TASK 1) --------------------------------
    "BrightBlue":      ("#2F6FBF", 0.78, 0.00),
    "SchoolYellow":    ("#E8C24A", 0.78, 0.00),
    "ConcreteGreen":   ("#5E9E5A", 0.80, 0.00),
    "WoodBrown":       ("#8B5A2B", 0.82, 0.00),
    "BrickRed":        ("#9E4B3C", 0.82, 0.00),
    "OffWhite":        ("#E8E4DA", 0.76, 0.00),
    # extra wall colours the recipes need
    "SteelBlue":       ("#4A7C99", 0.55, 0.25),
    "DamagedConcrete": ("#8C8C84", 0.88, 0.00),
    "DarkCamoGreen":   ("#414B36", 0.86, 0.00),
    "CamoBrown":       ("#5B4A33", 0.86, 0.00),
    "ConcreteGrey":    ("#B4B4AE", 0.85, 0.00),
    # ---------------- ROOF COLOURS (TASK 1) --------------------------------
    "DarkGrey":        ("#43454A", 0.80, 0.00),
    "RustOrange":      ("#B4552E", 0.80, 0.00),
    "SlantedRed":      ("#8E3B31", 0.80, 0.00),
    "FlatConcrete":    ("#A8A8A2", 0.85, 0.00),
    "TiledTerracotta": ("#A9573C", 0.80, 0.00),
    # ---------------- trims / interiors ------------------------------------
    "BlueDark":        ("#1E4E8C", 0.80, 0.00),
    "YellowDark":      ("#B8952F", 0.80, 0.00),
    "GreenDark":       ("#3F7343", 0.82, 0.00),
    "WoodDark":        ("#5E3A1B", 0.85, 0.00),
    "BrickDark":       ("#7A3A2E", 0.85, 0.00),
    "StoneGrey":       ("#B8B2A6", 0.82, 0.00),
    "SteelDark":       ("#35596E", 0.55, 0.25),
    "BunkerTrim":      ("#333B2A", 0.86, 0.00),
    "ConcreteDark":    ("#8E8E88", 0.87, 0.00),
    "InteriorFloor":   ("#9A968C", 0.86, 0.00),
    "RubbleGrey":      ("#6E6E68", 0.90, 0.00),
}


def P(key: str) -> bpy.types.Material:
    hex_str, rough, metal = PALETTE[key]
    return mat("Mod_" + key, hex_str, rough, metal)


# ----------------------------------------------------------------------------
# module loading
# ----------------------------------------------------------------------------
MODULE_FILES = {
    "wall_solid": "mod_wall_solid.glb",
    "wall_window": "mod_wall_window.glb",
    "wall_door": "mod_wall_door.glb",
    "wall_garage": "mod_wall_garage.glb",
    "floor": "mod_floor.glb",
    "roof_flat": "mod_roof_flat.glb",
    "roof_slanted": "mod_roof_slanted.glb",
    "stairs": "mod_stairs.glb",
    "table": "mod_table.glb",
    "bed": "mod_bed.glb",
    "crate": "mod_crate.glb",
    "shelf": "mod_shelf.glb",
    "counter": "mod_counter.glb",
    "sofa": "mod_sofa.glb",
}

_MODULE_MESHES: dict[str, bpy.types.Mesh] = {}


def load_modules():
    for key, filename in MODULE_FILES.items():
        path = os.path.join(MODULE_DIR, filename)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"missing module {path} — run generate_building_modules.py first")
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=path)
        imported = [o for o in bpy.data.objects if o not in before]
        mesh_obj = next((o for o in imported if o.type == "MESH"), None)
        if mesh_obj is None:
            raise RuntimeError(f"no mesh in {filename}")
        mesh = mesh_obj.data
        mesh.name = "MOD_" + key
        mesh.use_fake_user = True
        _MODULE_MESHES[key] = mesh
        for o in imported:
            bpy.data.objects.remove(o, do_unlink=True)
    print(f"  loaded {len(_MODULE_MESHES)} modules")


def place(key: str, name: str, loc, rot_z=0.0, scale=(1.0, 1.0, 1.0),
          material=None, parts=None, keep_slots_above=None):
    """Instance a module at an exact position, optionally recolouring slot 0."""
    src = _MODULE_MESHES[key]
    mesh = src.copy()
    mesh.name = name + "Mesh"
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.location = tuple(loc)
    obj.rotation_euler = (0.0, 0.0, rot_z)
    obj.scale = tuple(scale)

    if material is not None:
        if keep_slots_above is None:
            obj.data.materials.clear()
            obj.data.materials.append(material)
        else:
            kept = obj.data.materials[keep_slots_above]
            obj.data.materials.clear()
            obj.data.materials.append(material)
            obj.data.materials.append(kept)
            for poly in obj.data.polygons:
                if poly.material_index >= 1:
                    poly.material_index = 1
    for poly in obj.data.polygons:
        poly.use_smooth = False
    if parts is not None:
        parts.append(obj)
    return obj


# ----------------------------------------------------------------------------
# footprint / edge helpers
# ----------------------------------------------------------------------------
def footprint_cells(spec):
    if spec.get("footprint"):
        return list(spec["footprint"])
    return [(i, j) for j in range(spec["ny"]) for i in range(spec["nx"])]


def exterior_edges(cells):
    """Every cell side whose neighbour is outside the footprint."""
    cs = set(cells)
    edges = []
    for (i, j) in sorted(cs, key=lambda c: (c[1], c[0])):
        if (i, j - 1) not in cs:
            edges.append(("S", i, j))
        if (i, j + 1) not in cs:
            edges.append(("N", i, j))
        if (i - 1, j) not in cs:
            edges.append(("W", i, j))
        if (i + 1, j) not in cs:
            edges.append(("E", i, j))
    return edges


def cell_center(i, j, nx, ny):
    return (-nx * GRID / 2.0 + (i + 0.5) * GRID,
            -ny * GRID / 2.0 + (j + 0.5) * GRID)


def edge_transform(side, i, j, nx, ny):
    """(x, y, rot_z) for a 15 m wall panel sitting on that cell edge."""
    cx, cy = cell_center(i, j, nx, ny)
    x0 = -nx * GRID / 2.0
    y0 = -ny * GRID / 2.0
    if side == "S":
        return (cx, y0 + j * GRID + WALL_T / 2.0, 0.0)
    if side == "N":
        return (cx, y0 + (j + 1) * GRID - WALL_T / 2.0, 0.0)
    if side == "W":
        return (x0 + i * GRID + WALL_T / 2.0, cy, math.pi / 2.0)
    return (x0 + (i + 1) * GRID - WALL_T / 2.0, cy, math.pi / 2.0)


def edge_normal(side):
    return {"S": (0.0, -1.0), "N": (0.0, 1.0), "W": (-1.0, 0.0), "E": (1.0, 0.0)}[side]


def floor_top(level):
    return 0.2 if level == 0 else level * STOREY


# ----------------------------------------------------------------------------
# boolean helpers
# ----------------------------------------------------------------------------
def boolean_box(target, name, center, size):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=center)
    cutter = bpy.context.active_object
    cutter.name = name
    cutter.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
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


# ----------------------------------------------------------------------------
# furniture
# ----------------------------------------------------------------------------
# anchors inside a 15 m cell: a 3 x 5 lattice, 2.5 m apart (>= furniture half-sizes)
ANCHOR_X = (-5.0, 0.0, 5.0)
ANCHOR_Y = (-5.0, -2.5, 0.0, 2.5, 5.0)
ANCHORS = [(x, y) for y in ANCHOR_Y for x in ANCHOR_X]

# stair occupies this box (cell-local metres) -> furniture must not overlap it
STAIR_LOCAL = (-4.6, -2.6, 2.6, 3.6)   # cx, cy, half_x, half_y


def free_anchors(level, cell, nx, ny, door_points, is_stair_cell):
    """Anchor spots that are clear of every doorway and of the staircase."""
    cx, cy = cell_center(cell[0], cell[1], nx, ny)
    stair_world = None
    if is_stair_cell:
        stair_world = (cx + STAIR_LOCAL[0], cy + STAIR_LOCAL[1])
    out = []
    for (dx, dy) in ANCHORS:
        px, py = cx + dx, cy + dy
        if any((px - qx) ** 2 + (py - qy) ** 2 < 2.4 ** 2 for (qx, qy) in door_points):
            continue
        if stair_world and (px - stair_world[0]) ** 2 + (py - stair_world[1]) ** 2 < 3.0 ** 2:
            continue
        out.append((px, py))
    # deterministic shuffle so furniture spreads over the room instead of
    # stacking up in the first (south-west) corner
    rng = random.Random(1000 + level * 31 + cell[0] * 7 + cell[1] * 13)
    rng.shuffle(out)
    return out


def furnish(spec, cells, nx, ny, floors, stair_cell, door_edges, parts):
    """Scatter the recipe's furniture across rooms; never in a doorway or stairwell."""
    counts = spec.get("furniture", {})
    items: list[str] = []
    for kind, n in counts.items():
        items += [kind] * n
    if not items:
        return 0

    priority = {"bed": 0, "sofa": 1, "counter": 2, "shelf": 3, "table": 4, "crate": 5}
    items.sort(key=lambda k: priority.get(k, 9))

    rooms = [(level, cell) for level in range(floors) for cell in cells]
    if not rooms:
        return 0

    door_points_by_cell = {}
    for (side, i, j) in door_edges:
        door_points_by_cell.setdefault((i, j), []).append(edge_transform(side, i, j, nx, ny)[:2])

    state = {}
    for (level, cell) in rooms:
        state[(level, cell)] = free_anchors(level, cell, nx, ny,
                                            door_points_by_cell.get(cell, []),
                                            cell == stair_cell)

    def interleave(room_list):
        """Round-robin across storeys so upper-floor rooms all get furnished."""
        by_level = {}
        for (lv, c) in room_list:
            by_level.setdefault(lv, []).append((lv, c))
        out = []
        while any(by_level.values()):
            for lv in sorted(by_level):
                if by_level[lv]:
                    out.append(by_level[lv].pop(0))
        return out

    upper = interleave([(lv, c) for (lv, c) in rooms if lv > 0]) or rooms
    ground = interleave([(lv, c) for (lv, c) in rooms if lv == 0]) or rooms

    cursor = {"upper": 0, "ground": 0}
    placed = 0
    for kind in items:
        pool = upper if kind in ("bed", "sofa") else ground
        slot = "upper" if pool is upper else "ground"
        target = None
        for attempt in range(len(pool)):
            idx = (cursor[slot] + attempt) % len(pool)
            room = pool[idx]
            if state.get(room):
                target = room
                cursor[slot] = (idx + 1) % len(pool)
                break
        if target is None:          # every room full -> use whatever is left
            for room in rooms:
                if state.get(room):
                    target = room
                    break
        if target is None:
            break
        (level, cell) = target
        x, y = state[target].pop(0)
        _, cy = cell_center(cell[0], cell[1], nx, ny)
        rot = 0.0
        if kind in ("shelf", "counter"):
            rot = math.pi if y > cy else 0.0        # face into the room
        elif kind == "crate":
            rot = math.radians((placed * 37) % 90)
        place(kind, f"Furn_{kind}_{placed}", (x, y, floor_top(level)),
              rot_z=rot, parts=parts)
        placed += 1
    return placed


# ----------------------------------------------------------------------------
# detail builders
# ----------------------------------------------------------------------------
def add_box_raw(parts, name, size, loc, mat_key, rot=(0.0, 0.0, 0.0)):
    """Plain box in a palette colour, appended to the part list."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.name = name
    o.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    o.data.materials.clear()
    o.data.materials.append(P(mat_key))
    for poly in o.data.polygons:
        poly.use_smooth = False
    parts.append(o)
    return o


def add_awning(parts, cx, cy, z, width=6.0, depth=2.0, name="Awning"):
    """Cantilevered shop awning tilted 16° down towards the street."""
    add_box_raw(parts, name, (width, depth, 0.12), (cx, cy - depth / 2.0, z),
                "WoodDark", rot=(math.radians(16.0), 0.0, 0.0))
    add_box_raw(parts, name + "_Fascia", (width, 0.10, 0.34),
                (cx, cy - depth + 0.05, z - 0.28), "WoodBrown")


def add_roof_terrace(parts, cx, cy, z, w=9.0, d=6.0):
    """Raised deck + railing + pergola on a flat roof (the villa 'balcony')."""
    add_box_raw(parts, "Terrace_Deck", (w, d, 0.18), (cx, cy, z + 0.09), "WoodDark")
    top = z + 0.18
    # railings on the west + south edges
    add_box_raw(parts, "Terrace_RailW", (0.10, d, 0.10),
                (cx - w / 2 + 0.05, cy, top + 1.0), "WoodDark")
    add_box_raw(parts, "Terrace_RailS", (w, 0.10, 0.10),
                (cx, cy - d / 2 + 0.05, top + 1.0), "WoodDark")
    add_box_raw(parts, "Terrace_RailW2", (0.10, d, 0.10),
                (cx - w / 2 + 0.05, cy, top + 0.55), "WoodDark")
    add_box_raw(parts, "Terrace_RailS2", (w, 0.10, 0.10),
                (cx, cy - d / 2 + 0.05, top + 0.55), "WoodDark")
    for k in range(4):
        add_box_raw(parts, f"Terrace_BalusterW{k}", (0.10, 0.10, 1.0),
                    (cx - w / 2 + 0.05, cy - d / 2 + 0.6 + k * (d - 1.2) / 3,
                     top + 0.5), "WoodDark")
    # pergola posts + slats over the deck
    for k, (sx, sy) in enumerate([(-1, -1), (1, -1), (-1, 1), (1, 1)]):
        add_box_raw(parts, f"Terrace_Post{k}", (0.14, 0.14, 2.5),
                    (cx + sx * (w / 2 - 0.4), cy + sy * (d / 2 - 0.4), top + 1.25),
                    "WoodDark")
    for k in range(4):
        add_box_raw(parts, f"Terrace_Slat{k}", (w - 0.6, 0.10, 0.12),
                    (cx, cy - d / 2 + 0.9 + k * (d - 1.8) / 3, top + 2.55), "WoodDark")


def add_rubble(parts, cx, cy, count, seed, radius=9.0, mat_key="RubbleGrey"):
    rng = random.Random(seed)
    for k in range(count):
        add_box_raw(parts, f"Rubble{k}",
                    (rng.uniform(0.6, 1.8), rng.uniform(0.6, 1.8), rng.uniform(0.3, 0.9)),
                    (cx + rng.uniform(-radius, radius),
                     cy + rng.uniform(-radius, radius),
                     rng.uniform(0.12, 0.5)),
                    mat_key, rot=(0.0, 0.0, rng.uniform(0, math.pi)))


def damage(obj, ratio: float, seed: int = 7):
    """Randomly delete faces (BMesh) so the building reads as bombed out."""
    rng = random.Random(seed)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.faces.ensure_lookup_table()
    victims = [f for f in bm.faces if rng.random() < ratio]
    bmesh.ops.delete(bm, geom=victims, context="FACES")
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    print(f"      {len(victims)} faces destroyed ({ratio * 100:.0f}% target)")


# ----------------------------------------------------------------------------
# TASK 2/3 — the assembler
# ----------------------------------------------------------------------------
def assemble(spec: dict) -> bpy.types.Object:
    name = spec["name"]
    nx, ny, floors = spec["nx"], spec["ny"], spec["floors"]
    cells = footprint_cells(spec)
    edges = exterior_edges(cells)

    wall_mat = P(spec.get("wall", "OffWhite"))
    wall_alt = P(spec["wall_alt"]) if spec.get("wall_alt") else None
    trim_mat = P(spec.get("trim", "ConcreteDark"))
    floor_mat = P(spec.get("floor", "InteriorFloor"))
    roof_mat = P(spec.get("roof_mat", "FlatConcrete"))

    doors = {tuple(d) for d in spec.get("doors", [])}
    garages = {tuple(g) for g in spec.get("garages", [])}
    missing = {tuple(m) for m in spec.get("missing_walls", [])}
    window_rule = spec.get("windows", "all")
    solid_edges = {tuple(e) for e in spec.get("solid_edges", [])}

    parts: list[bpy.types.Object] = []
    wall_objs: list[bpy.types.Object] = []
    slab_objs: dict[tuple, bpy.types.Object] = {}
    modules_used = 0

    # ---- floor slabs (one per storey per cell) ---------------------------
    for level in range(floors):
        z = max(0.0, level * STOREY - SLAB)
        for (i, j) in cells:
            cx, cy = cell_center(i, j, nx, ny)
            slab = place("floor", f"Slab{level}_{i}_{j}", (cx, cy, z),
                         material=floor_mat, parts=parts)
            slab_objs[(level, i, j)] = slab
            modules_used += 1

    # ---- walls -----------------------------------------------------------
    for level in range(floors):
        z = level * STOREY
        for idx, (side, i, j) in enumerate(edges):
            key = (side, i, j)
            if (side, i, j, level) in missing:
                continue
            variant = "solid"
            if level == 0 and key in garages:
                variant = "garage"
            elif level == 0 and key in doors:
                variant = "door"
            elif window_rule != "none" and key not in solid_edges:
                if window_rule == "alternate":
                    variant = "window" if idx % 2 == 0 else "solid"
                else:
                    variant = "window"
            module_key = {"solid": "wall_solid", "window": "wall_window",
                          "door": "wall_door", "garage": "wall_garage"}[variant]
            x, y, rot = edge_transform(side, i, j, nx, ny)
            m = wall_mat
            if wall_alt is not None and idx % 3 == 1:
                m = wall_alt
            w = place(module_key, f"Wall{level}_{side}{i}{j}", (x, y, z),
                      rot_z=rot, material=m, parts=parts)
            wall_objs.append(w)
            modules_used += 1

    # ---- plinth band around the ground floor ------------------------------
    for (side, i, j) in edges:
        if (side, i, j) in doors or (side, i, j) in garages:
            continue
        x, y, rot = edge_transform(side, i, j, nx, ny)
        nxv, nyv = edge_normal(side)
        if side in ("N", "S"):
            size = (GRID, 0.34, 0.48)
        else:
            size = (0.34, GRID, 0.48)
        add_box_raw(parts, f"Plinth_{side}{i}{j}", size,
                    (x + nxv * 0.06, y + nyv * 0.06, 0.24), spec.get("trim", "ConcreteDark"))
        modules_used += 1

    # ---- internal stairs + slab holes ------------------------------------
    stair_cell = tuple(spec["stair_cell"]) if spec.get("stair_cell") else None
    stair_pos = None
    if floors > 1 and stair_cell is not None:
        scx, scy = cell_center(stair_cell[0], stair_cell[1], nx, ny)
        stair_pos = (scx + STAIR_LOCAL[0], scy + STAIR_LOCAL[1])
        for level in range(floors - 1):
            z = level * STOREY
            place("stairs", f"Stairs{level}", (stair_pos[0], stair_pos[1], z),
                  material=floor_mat, parts=parts)
            modules_used += 1
            # hole in the slab above, over the top of the flight
            above = slab_objs.get((level + 1, stair_cell[0], stair_cell[1]))
            if above is not None:
                boolean_box(above, f"StairHole{level}",
                            (stair_pos[0], stair_pos[1] + 1.0,
                             (level + 1) * STOREY - SLAB / 2 - 0.05),
                            (2.9, 3.8, 0.6))

    # ---- roof -------------------------------------------------------------
    roof = spec.get("roof", "flat")
    roof_z = floors * STOREY
    if roof == "flat":
        for (i, j) in cells:
            cx, cy = cell_center(i, j, nx, ny)
            place("roof_flat", f"Roof{i}_{j}", (cx, cy, roof_z),
                  material=roof_mat, keep_slots_above=1, parts=parts)
            modules_used += 1
    elif roof == "slanted":
        place("roof_slanted", "RoofSlanted", (0.0, 0.0, roof_z),
              scale=(nx, ny, 1.0), material=roof_mat, keep_slots_above=1,
              parts=parts)
        modules_used += 1
    elif roof == "open":
        # open top: low parapet only, so the top storey is a rooftop platform
        top = roof_z
        for (side, i, j) in edges:
            x, y, rot = edge_transform(side, i, j, nx, ny)
            nxv, nyv = edge_normal(side)
            if side in ("N", "S"):
                size = (GRID + WALL_T, 0.25, 0.95)
            else:
                size = (0.25, GRID + WALL_T, 0.95)
            add_box_raw(parts, f"Parapet_{side}{i}{j}", size,
                        (x + nxv * 0.12, y + nyv * 0.12, top + 0.475),
                        spec.get("trim", "ConcreteDark"))
            modules_used += 1
    # roof == "none" -> ruined building, open to the sky

    # ---- details ---------------------------------------------------------
    for idx, detail in enumerate(spec.get("details", [])):
        kind = detail[0]
        if kind == "awning":
            _, side, i, j = detail
            x, y, _rot = edge_transform(side, i, j, nx, ny)
            add_awning(parts, x, y - 0.35, 2.55, name=f"Awning{idx}")
        elif kind == "roof_terrace":
            _, i, j = detail
            cx, cy = cell_center(i, j, nx, ny)
            add_roof_terrace(parts, cx, cy, roof_z + SLAB)
        elif kind == "rubble":
            _, count, seed = detail
            add_rubble(parts, 0.0, 0.0, count, seed,
                       radius=min(nx, ny) * GRID / 2 - 2.0)
        elif kind == "wall_holes":
            _, count, seed = detail
            rng = random.Random(seed)
            for k in range(count):
                target = rng.choice(wall_objs)
                target["noop"] = True
                hx = target.location.x + rng.uniform(-3.0, 3.0)
                hy = target.location.y + rng.uniform(-3.0, 3.0)
                hz = target.location.z + rng.uniform(0.9, 2.2)
                boolean_box(target, f"DamageHole{k}", (hx, hy, hz),
                            (rng.uniform(1.6, 2.8), rng.uniform(1.6, 2.8),
                             rng.uniform(1.4, 2.2)))

    # ---- furniture --------------------------------------------------------
    furniture_count = furnish(spec, cells, nx, ny, floors, stair_cell,
                              [(s, i, j) for (s, i, j) in doors | garages],
                              parts)

    # ---- join into one mesh ----------------------------------------------
    bpy.ops.object.select_all(action="DESELECT")
    for p in parts:
        p.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "Mesh"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    if spec.get("destroy", 0.0) > 0.0:
        damage(obj, spec["destroy"], seed=spec.get("seed", 7))

    # ---- origin bottom-centre -------------------------------------------
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
    obj["module_count"] = modules_used
    obj["furniture_count"] = furniture_count
    return obj


# ----------------------------------------------------------------------------
# export / verify
# ----------------------------------------------------------------------------
def export_glb(obj, filename):
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
    mats = [m["name"] for m in g.get("materials", [])]
    return os.path.getsize(path), tris, mats


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
    def fam(m):
        base = m.split(".")[0]
        for prefix, label in (("Mod_BedFrame", "bed"), ("Mod_TableTop", "table"),
                              ("Mod_CrateWood", "crate"), ("Mod_ShelfWood", "shelf"),
                              ("Mod_CounterBody", "counter"), ("Mod_SofaFabric", "sofa")):
            if base == prefix:
                return label
        return None
    furn = len({fam(m) for m in mats if fam(m)})
    print(f"  {os.path.basename(path):24s} {max(xs) - min(xs):5.1f} x "
          f"{max(ys) - min(ys):5.1f} x {max(zs) - min(zs):5.1f} m  "
          f"minZ {min(zs):+.3f}  {tris:6d} tris  {len(mats):2d} mats  "
          f"{furn} furn  {size / 1024:6.1f} KB")
    return min(zs)


# ----------------------------------------------------------------------------
# TASK 2 — the 11 recipes (all on the 15 m grid)
# ----------------------------------------------------------------------------
FULL_2x2 = [(0, 0), (1, 0), (0, 1), (1, 1)]
VILLA_L = [(0, 0), (1, 0), (0, 1)]          # 3 of 4 quadrants -> L shape

BUILDINGS = [
    dict(name="house_blue", title="House Blue", nx=2, ny=2, floors=2,
         wall="BrightBlue", trim="BlueDark", floor="InteriorFloor",
         roof="slanted", roof_mat="DarkGrey",
         doors=[("S", 0, 0)], windows="all", stair_cell=(1, 1),
         furniture={"bed": 1, "crate": 2},
         blurb="2×2 grid, 2 floors, bright blue walls, dark grey hip roof"),

    dict(name="school_yellow", title="School Yellow", nx=3, ny=2, floors=2,
         wall="SchoolYellow", trim="YellowDark", floor="InteriorFloor",
         roof="flat", roof_mat="FlatConcrete",
         doors=[("S", 1, 0)], windows="all", stair_cell=(2, 1),
         furniture={"table": 8, "shelf": 4},
         blurb="3×2 grid, 2 floors, school yellow, flat concrete roof + parapet"),

    dict(name="apartment_green", title="Apartment Green", nx=2, ny=2, floors=3,
         wall="ConcreteGreen", trim="GreenDark", floor="InteriorFloor",
         roof="flat", roof_mat="FlatConcrete",
         doors=[("S", 1, 0)], windows="all", stair_cell=(0, 0),
         furniture={"bed": 4, "crate": 6},
         blurb="2×2 grid, 3 floors with internal stairs, concrete green walls"),

    dict(name="warehouse_metal", title="Warehouse Metal", nx=3, ny=2, floors=1,
         wall="SteelBlue", trim="SteelDark", floor="InteriorFloor",
         roof="flat", roof_mat="RustOrange",
         doors=[("S", 0, 0)], garages=[("S", 1, 0)], windows="alternate",
         furniture={"crate": 14},
         blurb="3×2 grid, steel blue, rust orange roof, 6 m garage door, loot crates"),

    dict(name="cabin_wood", title="Cabin Wood", nx=1, ny=1, floors=1,
         wall="WoodBrown", trim="WoodDark", floor="InteriorFloor",
         roof="slanted", roof_mat="SlantedRed",
         doors=[("S", 0, 0)], windows="all",
         furniture={"bed": 1, "table": 1},
         blurb="1×1 grid (15×15 m), wood brown walls, red hip roof"),

    dict(name="ruined_building", title="Ruined Building", nx=2, ny=2, floors=2,
         wall="DamagedConcrete", trim="ConcreteDark", floor="RubbleGrey",
         roof="none",
         doors=[("S", 0, 0)], windows="all", stair_cell=(1, 1),
         missing_walls=[("N", 1, 1, 1), ("E", 1, 0, 1), ("S", 0, 1, 1)],
         destroy=0.20, seed=11,
         furniture={"crate": 6},
         details=[("wall_holes", 5, 3), ("rubble", 9, 5)],
         blurb="2×2 grid, 2 floors, damaged concrete, no roof, holes + rubble"),

    dict(name="shop_row", title="Shop Row", nx=2, ny=1, floors=1,
         wall="OffWhite", trim="WoodDark", floor="InteriorFloor",
         roof="slanted", roof_mat="SlantedRed",
         doors=[("S", 0, 0), ("S", 1, 0)], windows="all",
         furniture={"counter": 4, "shelf": 6, "table": 2},
         details=[("awning", "S", 0, 0), ("awning", "S", 1, 0)],
         blurb="2×1 grid (30×15 m), off-white shops, awnings, counters + shelves"),

    dict(name="villa_white", title="Villa White", nx=2, ny=2, floors=2,
         footprint=VILLA_L,
         wall="OffWhite", trim="StoneGrey", floor="InteriorFloor",
         roof="flat", roof_mat="FlatConcrete",
         doors=[("S", 1, 0)], windows="all", stair_cell=(0, 1),
         furniture={"sofa": 4, "table": 3, "bed": 2},
         details=[("roof_terrace", 1, 0)],
         blurb="L-shaped 2×2 footprint, off-white, flat roof + roof balcony"),

    dict(name="farmhouse_stone", title="Farmhouse Stone", nx=2, ny=1, floors=1,
         wall="BrickRed", trim="BrickDark", floor="InteriorFloor",
         roof="slanted", roof_mat="TiledTerracotta",
         doors=[("S", 1, 0)], windows="all",
         furniture={"table": 4, "crate": 5},
         blurb="2×1 grid, brick red walls, terracotta tiled hip roof"),

    dict(name="bunker_military", title="Bunker Military", nx=1, ny=1, floors=1,
         wall="DarkCamoGreen", wall_alt="CamoBrown", trim="BunkerTrim",
         floor="InteriorFloor",
         roof="flat", roof_mat="FlatConcrete",
         doors=[("S", 0, 0)], windows="none",
         furniture={"crate": 8, "shelf": 4},
         blurb="1×1 grid, dark camo green, no windows, flat roof, supplies"),

    dict(name="tower_sniper", title="Tower Sniper", nx=1, ny=1, floors=4,
         wall="ConcreteGrey", trim="ConcreteDark", floor="InteriorFloor",
         roof="open", roof_mat="FlatConcrete",
         doors=[("S", 0, 0)], windows="all", stair_cell=(0, 0),
         furniture={"crate": 1},
         blurb="1×1 grid, 4 floors (12.7 m), concrete grey, open flat top"),
]


def main():
    print(f"Blender bpy {bpy.app.version_string}")
    print("— loading 15 m modules —")
    load_modules()

    print("— assembling 11 furnished buildings —")
    exported = []
    for spec in BUILDINGS:
        print(f"  · {spec['name']:18s} {spec['title']:18s} {spec['blurb']}")
        obj = assemble(spec)
        mc = obj.get("module_count", 0)
        fc = obj.get("furniture_count", 0)
        path = export_glb(obj, spec["name"] + ".glb")
        exported.append(path)
        print(f"      {mc} modules · {fc} furniture pieces")

    print("— verification (re-import) —")
    bad = []
    for path in exported:
        min_z = verify(path)
        if abs(min_z) > 1e-4:
            bad.append((path, min_z))
    if bad:
        raise RuntimeError(f"origin verification failed: {bad}")
    print(f"Done — {len(exported)} modular buildings in docs/models/buildings_modular/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
