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
PART_T = 0.1         # partition thickness (mod_wall_partition)
STAIR_LOCAL = (-4.6, -2.6)   # stair centre offset inside its cell
STAIR_SIZE = (2.4, 3.4)      # stair module footprint
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
    "wall_partition": "mod_wall_partition.glb",
    "wall_partition_door": "mod_wall_partition_door.glb",
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


# ---------------------------------------------------------------------------
# interior partition plan — walls, doorways, rooms
# ---------------------------------------------------------------------------
class WallSpec:
    """One straight interior wall, axis aligned, with doorways in named slots.

    ``axis='x'``  wall runs along X at ``y = pos``
    ``axis='y'``  wall runs along Y at ``x = pos``
    ``lo``/``hi`` are the *design* span (inner faces of the walls it meets); the
    placed module is grown by ``expand`` at both ends so it buries its end caps
    inside the neighbouring solid instead of leaving a coplanar face.
    ``doors`` is a tuple of slot indices, or the string "all".
    """

    def __init__(self, axis, pos, lo, hi, doors=(), expand=0.05, label=""):
        self.axis = axis
        self.pos = float(pos)
        self.lo = float(lo)
        self.hi = float(hi)
        self.doors = doors
        self.expand = expand
        self.label = label or f"{axis}{pos:+.2f}"

    # -- geometry -----------------------------------------------------------
    @property
    def length(self):
        return self.hi - self.lo

    def slots(self):
        n = max(1, int(math.ceil(self.length / GRID - 1e-9)))
        return n, self.length / n

    def slot_centers(self):
        n, step = self.slots()
        return [self.lo + (k + 0.5) * step for k in range(n)]

    def door_slots(self):
        n, _ = self.slots()
        if self.doors == "all":
            return tuple(range(n))
        return tuple(d for d in self.doors if 0 <= d < n)

    def door_points(self):
        """World (x, y) of every doorway centre on this wall."""
        pts = []
        for k, c in enumerate(self.slot_centers()):
            if k in self.door_slots():
                pts.append((c, self.pos) if self.axis == "x" else (self.pos, c))
        return pts

    def segment(self):
        if self.axis == "x":
            return (self.lo, self.pos), (self.hi, self.pos)
        return (self.pos, self.lo), (self.pos, self.hi)

    def __repr__(self):
        return (f"WallSpec({self.axis} {self.pos:+.2f} "
                f"{self.lo:+.2f}..{self.hi:+.2f} doors={self.door_slots()})")


def footprint_rects(spec):
    """Outline rectangles (world coords) of the cell footprint.

    Rows of contiguous cells are merged, so a 2x2 becomes ONE 30x30 rectangle
    and the L-shaped villa becomes two rectangles.  Room splitting needs the
    outline (not the cells), otherwise a wall on a cell boundary would be
    invisible to the splitter.
    """
    nx, ny = spec["nx"], spec["ny"]
    rows = {}
    for (i, j) in footprint_cells(spec):
        rows.setdefault(j, []).append(i)

    def row_rect(run, j):
        x0 = -nx * GRID / 2.0 + min(run) * GRID
        y0 = -ny * GRID / 2.0 + j * GRID
        return (x0, y0, x0 + len(run) * GRID, y0 + GRID)

    rects = []
    for j in sorted(rows):
        xs = sorted(rows[j])
        run = [xs[0]]
        for a, b in zip(xs, xs[1:]):
            if b == a + 1:
                run.append(b)
            else:
                rects.append(row_rect(run, j))
                run = [b]
        rects.append(row_rect(run, j))

    merged = []
    for r in rects:
        if merged and abs(merged[-1][0] - r[0]) < 1e-9 and abs(merged[-1][2] - r[2]) < 1e-9 \
                and abs(merged[-1][3] - r[1]) < 1e-9:
            merged[-1] = (r[0], merged[-1][1], r[2], r[3])
        else:
            merged.append(r)
    return merged


def split_rects(rects, wall):
    """Cut every rectangle the wall fully crosses into two."""
    out = []
    eps = 0.25
    for (x0, y0, x1, y1) in rects:
        if wall.axis == "x":
            if y0 < wall.pos < y1 and x0 >= wall.lo - eps and x1 <= wall.hi + eps:
                out += [(x0, y0, x1, wall.pos), (x0, wall.pos, x1, y1)]
            else:
                out.append((x0, y0, x1, y1))
        else:
            if x0 < wall.pos < x1 and y0 >= wall.lo - eps and y1 <= wall.hi + eps:
                out += [(x0, y0, wall.pos, y1), (wall.pos, y0, x1, y1)]
            else:
                out.append((x0, y0, x1, y1))
    return out


def build_plan(spec):
    """Turn the recipe's ``plan`` shorthand into walls + room rectangles."""
    rects = footprint_rects(spec)
    x_lo = min(r[0] for r in rects); x_hi = max(r[2] for r in rects)
    y_lo = min(r[1] for r in rects); y_hi = max(r[3] for r in rects)
    plan = spec.get("plan") or {}
    kind = plan.get("type", "none")
    walls = []

    if kind == "middle":
        # one wall splitting the building in half, doorway(s) in chosen slots
        walls.append(WallSpec("y", 0.0, y_lo + WALL_T, y_hi - WALL_T,
                              doors=plan.get("doors", (0,)), label="mid"))
        nook = plan.get("nook")
        if nook:
            # keep the small room on the opposite side of the building from the
            # staircase, so a flight never lands inside the bedroom
            sc = spec.get("stair_cell")
            if nook.get("side") in ("auto", None):
                side = "W" if (sc and sc[0] >= nx / 2.0) else "E"
            else:
                side = nook["side"]
            if side == "E":
                lo, hi = 0.05, x_hi - WALL_T
            else:
                lo, hi = x_lo + WALL_T, -0.05
            walls.append(WallSpec("x", nook["y"], lo, hi, doors=(0,),
                                  label="nook"))
    elif kind == "cross":
        # horizontal wall dividing a 1x1 hut into a front room and a back room
        walls.append(WallSpec("x", plan.get("pos", 0.0), x_lo + WALL_T,
                              x_hi - WALL_T, doors=plan.get("doors", (0,)),
                              label="cross"))
    elif kind == "hallway":
        hw = plan.get("half_width", 2.5)
        walls.append(WallSpec("x", +hw, x_lo + WALL_T, x_hi - WALL_T,
                              doors="all", label="hallN"))
        walls.append(WallSpec("x", -hw, x_lo + WALL_T, x_hi - WALL_T,
                              doors="all", label="hallS"))
        bays = int(round((x_hi - x_lo) / GRID))
        for b in range(1, bays):
            xb = x_lo + b * GRID
            walls.append(WallSpec("y", xb, hw + 0.05, y_hi - WALL_T,
                                  doors=(), label=f"divN{b}"))
            walls.append(WallSpec("y", xb, y_lo + WALL_T, -hw - 0.05,
                                  doors=(), label=f"divS{b}"))
    elif kind == "custom":
        for w in plan.get("walls", []):
            walls.append(WallSpec(**w))

    room_rects = list(rects)
    for w in walls:
        room_rects = split_rects(room_rects, w)
    return walls, room_rects


def add_partition_walls(walls, floors, material, parts):
    """Instance the partition modules on every storey. Returns modules placed."""
    count = 0
    for wall in walls:
        n, step = wall.slots()
        centers = wall.slot_centers()
        doors = set(wall.door_slots())
        for level in range(floors):
            z = floor_top(level)
            for k, c in enumerate(centers):
                key = "wall_partition_door" if k in doors else "wall_partition"
                # grow by 10 cm so the two halves overlap at the joint and both
                # end caps are buried inside the walls they meet
                length = step + 0.10
                if wall.axis == "x":
                    loc, rot = (c, wall.pos, z), 0.0
                else:
                    loc, rot = (wall.pos, c, z), math.pi / 2.0
                place(key, f"Part{level}_{wall.label}_{k}", loc, rot_z=rot,
                      scale=(length / GRID, 1.0, 1.0), material=material,
                      parts=parts)
                count += 1
    return count



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


# ---------------------------------------------------------------------------
# furniture — placed inside the rooms the partitions created
# ---------------------------------------------------------------------------
FURNITURE_PITCH = 2.6      # anchor spacing inside a room
FURNITURE_MARGIN = 1.0     # keep clear of the walls
DOOR_CLEAR = 2.8           # no furniture within this radius of any doorway
STAIR_CLEAR = 1.2          # extra margin around the stair footprint

# how much floor space a piece needs, used to stop pieces overlapping
BLOCK_RADIUS = {"bed": 2.3, "sofa": 2.0, "table": 1.9, "counter": 1.9,
                "shelf": 1.6, "crate": 0.9}

# pieces that should be pushed against a wall
WALL_HUG = {"bed", "shelf", "counter"}

# half extents of each module in its own local space (x, y)
FURNITURE_SIZE = {"bed": (1.06, 0.68), "table": (1.10, 0.55), "crate": (0.57, 0.57),
                  "shelf": (0.90, 0.23), "counter": (1.38, 0.46), "sofa": (1.15, 0.48)}


def rect_area(r):
    return (r[2] - r[0]) * (r[3] - r[1])


def rect_contains(r, p, eps=1e-6):
    return r[0] - eps <= p[0] <= r[2] + eps and r[1] - eps <= p[1] <= r[3] + eps


def rect_center(r):
    return ((r[0] + r[2]) / 2.0, (r[1] + r[3]) / 2.0)


def point_rect_dist(r, p):
    dx = max(r[0] - p[0], 0.0, p[0] - r[2])
    dy = max(r[1] - p[1], 0.0, p[1] - r[3])
    return math.hypot(dx, dy)


def assign_room_kinds(rects, entrance_pt):
    """Corridors become 'hall'; the room nearest the front door is the
    living/kitchen; the smallest (and, on a tie, the farthest) room becomes
    the bedroom; everything else is a generic room."""
    kinds = [None] * len(rects)
    for idx, r in enumerate(rects):
        w, h = r[2] - r[0], r[3] - r[1]
        short, long_ = min(w, h), max(w, h)
        if short <= 6.5 and long_ / short >= 3.2:
            kinds[idx] = "hall"

    free = [i for i, k in enumerate(kinds) if k is None]
    if free:
        ordered = sorted(free, key=lambda i: (-rect_area(rects[i]),
                                              point_rect_dist(rects[i], entrance_pt),
                                              i))
        kinds[ordered[0]] = "living"
        if len(ordered) > 1:
            kinds[ordered[-1]] = "bedroom"
        for i in ordered[1:-1]:
            kinds[i] = "room"
    return [k or "room" for k in kinds]


def room_anchors(rect, door_pts, stair_box):
    """Lattice of candidate furniture spots inside one room."""
    x0, y0, x1, y1 = rect
    ax0, ax1 = x0 + FURNITURE_MARGIN, x1 - FURNITURE_MARGIN
    ay0, ay1 = y0 + FURNITURE_MARGIN, y1 - FURNITURE_MARGIN
    if ax1 - ax0 < 1.2 or ay1 - ay0 < 1.2:
        return []

    def line(a, b):
        span = b - a
        n = max(1, int(round(span / FURNITURE_PITCH)) + 1)
        if n == 1:
            return [(a + b) / 2.0]
        return [a + span * k / (n - 1) for k in range(n)]

    out = []
    for px in line(ax0, ax1):
        for py in line(ay0, ay1):
            if any(math.hypot(px - qx, py - qy) < DOOR_CLEAR for (qx, qy) in door_pts):
                continue
            if stair_box is not None and (
                    stair_box[0] - STAIR_CLEAR <= px <= stair_box[2] + STAIR_CLEAR and
                    stair_box[1] - STAIR_CLEAR <= py <= stair_box[3] + STAIR_CLEAR):
                continue
            out.append(dict(p=(px, py),
                            walls={"W": px - x0, "E": x1 - px,
                                   "S": py - y0, "N": y1 - py}))
    return out


def nearest_wall(anchor):
    return min(anchor["walls"].items(), key=lambda kv: kv[1])


def rotated_half(kind, rot):
    """Axis-aligned half extents of a piece after a z rotation."""
    hx, hy = FURNITURE_SIZE.get(kind, (0.6, 0.6))
    c, s = abs(math.cos(rot)), abs(math.sin(rot))
    return hx * c + hy * s, hx * s + hy * c


def fits_in_room(rect, px, py, ex, ey, pad=0.06):
    return (px - ex >= rect[0] + pad and px + ex <= rect[2] - pad and
            py - ey >= rect[1] + pad and py + ey <= rect[3] - pad)


def snap_to_wall(px, py, kind, rot, side, rect, gap=0.06):
    """Slide a wall-hugging piece until its back is `gap` off the wall."""
    ex, ey = rotated_half(kind, rot)
    if side == "W":
        return rect[0] + gap + ex, py
    if side == "E":
        return rect[2] - gap - ex, py
    if side == "S":
        return px, rect[1] + gap + ey
    return px, rect[3] - gap - ey


def furniture_rotation(kind, anchor, room_center, rng):
    """Rotate a piece so it sits sensibly against its closest wall."""
    side, dist = nearest_wall(anchor)
    px, py = anchor["p"]
    if kind == "bed":
        # headboard is at local -X -> point it at the wall
        return {"W": 0.0, "E": math.pi, "S": math.pi / 2.0,
                "N": -math.pi / 2.0}[side]
    if kind in ("shelf", "counter", "sofa"):
        # back panel is at local +Y -> point it at the wall
        turn = {"N": 0.0, "S": math.pi, "W": math.pi / 2.0, "E": -math.pi / 2.0}[side]
        if kind == "sofa" and dist > 2.2:
            turn = 0.0
        return turn
    if kind == "table":
        return 0.0 if side in ("N", "S") else math.pi / 2.0
    return rng.choice([0.0, math.pi / 2.0, math.pi, -math.pi / 2.0])


def choose_room(kind, rooms, anchors, kinds_used, placed_per_room, skip=()):
    """Pick the room that best fits the piece (loot is spread round-robin)."""
    avail = [i for i, a in enumerate(anchors) if a and i not in skip]
    if not avail:
        return None
    if kind == "crate":
        # fewest pieces first -> crates end up in every corner of the house
        avail.sort(key=lambda i: (placed_per_room[i], rooms[i]["level"], i))
        return avail[0]

    def pref(i):
        k = rooms[i]["kind"]
        level = rooms[i]["level"]
        if kind == "bed":
            weight = {"bedroom": 0.0, "room": 2.0, "living": 3.0, "hall": 5.0}.get(k, 4.0)
            return weight - 0.6 * level          # beds prefer the upper floors
        weight = {"living": 0.0, "room": 1.0, "bedroom": 2.0, "hall": 3.0}.get(k, 4.0)
        return weight - 0.15 * level

    avail.sort(key=lambda i: (kind in kinds_used[i], pref(i),
                              placed_per_room[i], i))
    return avail[0]


# ---------------------------------------------------------------------------
# plan + geometry checks  (the CRITICAL RULES of the room pass)
# ---------------------------------------------------------------------------
def point_segment_dist(p, seg):
    (x1, y1), (x2, y2) = seg
    px, py = p
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 == 0.0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def segment_hits_box(wall, box, pad=0.0):
    """Does an axis-aligned wall segment cut through an axis-aligned box?"""
    bx0, by0, bx1, by1 = (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
    if wall.axis == "x":
        return by0 < wall.pos < by1 and wall.lo < bx1 and wall.hi > bx0
    return bx0 < wall.pos < bx1 and wall.lo < by1 and wall.hi > by0


def check_plan(name, walls, rooms, stair_box, entrance_pts):
    """Fail the build if a partition blocks a door, a stair or a room."""
    problems = []

    for wall in walls:
        if stair_box is not None and segment_hits_box(wall, stair_box, pad=0.15):
            problems.append(f"{wall.label} cuts through the staircase")
        for pt in wall.door_points():
            if stair_box is not None and (
                    stair_box[0] - 1.2 <= pt[0] <= stair_box[2] + 1.2 and
                    stair_box[1] - 1.2 <= pt[1] <= stair_box[3] + 1.2):
                problems.append(f"{wall.label}: doorway at {pt} is in the stairwell")
            for other in walls:
                if other is wall:
                    continue
                d = point_segment_dist(pt, other.segment())
                if d < 1.1:
                    problems.append(f"{wall.label}: doorway at {pt} blocked by "
                                    f"{other.label} ({d:.2f} m)")
            for (ex, ey), _inner in entrance_pts:
                if math.hypot(pt[0] - ex, pt[1] - ey) < 2.4:
                    problems.append(f"{wall.label}: doorway at {pt} sits in front "
                                    f"of the main entrance")

    # ---- every room must be reachable through a doorway -------------------
    def room_index(pt):
        for k, r in enumerate(rooms):
            if rect_contains(r, pt):
                return k
        return None

    graph = {k: set() for k in range(len(rooms))}
    for wall in walls:
        nxv, nyv = (0.0, 1.0) if wall.axis == "x" else (1.0, 0.0)
        for (px, py) in wall.door_points():
            a = room_index((px + nxv * 0.35, py + nyv * 0.35))
            b = room_index((px - nxv * 0.35, py - nyv * 0.35))
            if a is None or b is None or a == b:
                problems.append(f"{wall.label}: doorway at ({px:.1f}, {py:.1f}) "
                                f"does not join two rooms")
                continue
            graph[a].add(b)
            graph[b].add(a)

    if entrance_pts:
        start = room_index(entrance_pts[0][1])
        seen = {start}
        stack = [start]
        while stack:
            cur = stack.pop()
            for nxt in graph.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        unreachable = [k for k in range(len(rooms)) if k not in seen]
        if unreachable:
            problems.append(f"rooms {unreachable} cannot be reached from the entrance")

    if problems:
        raise RuntimeError(f"{name}: interior plan failed — " + "; ".join(problems))


def check_geometry(obj, name, walls, door_specs, shift, avoid=()):
    """Ray-cast the finished mesh: partitions must be solid, doorways open."""
    ox, oy, oz = shift
    failures = []

    def cast(origin, direction, distance):
        return obj.ray_cast(Vector(origin), Vector(direction), distance=distance)

    def clear_of_furniture(p):
        return all(math.hypot(p[0] - q[0], p[1] - q[1]) > 1.7 for q in avoid)

    tested = 0
    for wall in walls:
        if wall.axis == "y":
            nrm = (1.0, 0.0)
        else:
            nrm = (0.0, 1.0)
        doors = set(wall.door_slots())
        candidates = []
        for k, c in enumerate(wall.slot_centers()):
            if k in doors:                       # solid part beside the doorway
                candidates += [c - 2.6, c - 3.9, c + 2.6, c + 3.9, c - 5.2, c + 5.2]
            else:
                candidates += [c, c - 2.5, c + 2.5]
        for t in candidates:
            if not (wall.lo + 0.6 < t < wall.hi - 0.6):
                continue
            p = (t, wall.pos) if wall.axis == "x" else (wall.pos, t)
            # probe above every furniture piece (the tallest is the 2.0 m
            # shelf) but well below the 3.0 m wall top
            origin = (p[0] + ox - nrm[0] * 1.4, p[1] + oy - nrm[1] * 1.4, 2.65 + oz)
            hit, loc, _n, _i = cast(origin, (nrm[0], nrm[1], 0.0), 2.8)
            tested += 1
            if not hit:
                failures.append(f"{wall.label}: no collision at "
                                f"({p[0]:.1f}, {p[1]:.1f})")

    for (p, nrm) in door_specs:
        origin = (p[0] + ox - nrm[0] * 1.3, p[1] + oy - nrm[1] * 1.3, 1.4 + oz)
        hit, loc, _n, _i = cast(origin, (nrm[0], nrm[1], 0.0), 2.6)
        if hit:
            failures.append(f"doorway at ({p[0]:.1f}, {p[1]:.1f}) is blocked "
                            f"at {loc[0] + 0.0:.1f}")

    if failures:
        raise RuntimeError(f"{name}: geometry check failed — " + "; ".join(failures))
    print(f"      {tested} wall probes + {len(door_specs)} doorways verified")


def piece_clear(kind, rot, px, py, rect, walls, pad=0.06):
    """True if the piece's footprint stays inside its room and off every wall."""
    ex, ey = rotated_half(kind, rot)
    if not fits_in_room(rect, px, py, ex, ey, pad):
        return False
    x0, x1 = px - ex, px + ex
    y0, y1 = py - ey, py + ey
    half = PART_T / 2.0 + pad
    for w in walls:
        if w.axis == "x":       # wall runs along X at y = w.pos
            if x1 <= w.lo - half or x0 >= w.hi + half:
                continue        # beside the end of the wall
            if y1 <= w.pos - half or y0 >= w.pos + half:
                continue        # entirely on one side
            return False
        else:                   # wall runs along Y at x = w.pos
            if y1 <= w.lo - half or y0 >= w.hi + half:
                continue
            if x1 <= w.pos - half or x0 >= w.pos + half:
                continue
            return False
    return True


def furnish(spec, rooms, walls, door_pts, stair_box, parts):
    """Distribute the recipe's furniture across the rooms, logically.

    beds -> bedrooms (smallest room, upper floors first)
    tables / shelves / counters / sofas -> living room / kitchen
    crates -> every room in turn, so loot has to be searched for
    """
    counts = spec.get("furniture", {})
    items: list[str] = []
    for kind, n in counts.items():
        items += [kind] * n
    if not items or not rooms:
        return 0, []

    priority = ["bed", "sofa", "counter", "shelf", "table", "crate"]
    items.sort(key=lambda k: priority.index(k) if k in priority else 99)

    anchors = [room_anchors(r["rect"], door_pts, stair_box) for r in rooms]
    placed_per_room = [0] * len(rooms)
    kinds_used = [set() for _ in rooms]
    rng = random.Random(spec.get("seed", 7))
    placed = 0
    placed_pts = []
    placements = []

    for kind in items:
        skipped = set()
        chosen = None
        idx = None
        for _attempt in range(len(rooms) + 1):
            idx = choose_room(kind, rooms, anchors, kinds_used, placed_per_room,
                              skip=skipped)
            if idx is None:
                break
            room = rooms[idx]
            rect = room["rect"]
            spots = anchors[idx]
            if kind in WALL_HUG:
                spots = sorted(spots, key=lambda a: (nearest_wall(a)[1], a["p"]))
            else:
                spots = sorted(spots, key=lambda a: (
                    (a["p"][0] * 7.3 + a["p"][1] * 3.1) % 11.0, a["p"]))

            for a in spots:
                rot = furniture_rotation(kind, a, rect_center(rect), rng)
                candidates = []
                if kind in WALL_HUG:
                    side, _d = nearest_wall(a)
                    candidates.append(snap_to_wall(*a["p"], kind, rot, side, rect))
                candidates.append(tuple(a["p"]))
                for (px, py) in candidates:
                    if not all(math.hypot(px - qx, py - qy) >= DOOR_CLEAR - 0.6
                               for (qx, qy) in door_pts):
                        continue
                    if not piece_clear(kind, rot, px, py, rect, walls):
                        continue
                    chosen = (a, px, py, rot)
                    break
                if chosen:
                    break
            if chosen is None:
                skipped.add(idx)
                continue
            break

        if chosen is None or idx is None:
            print(f"      ! no room with space left for {kind}")
            continue

        a, px, py, rot = chosen
        place(kind, f"Furn_{kind}_{placed}", (px, py, floor_top(rooms[idx]["level"])),
              rot_z=rot, parts=parts)

        radius = BLOCK_RADIUS.get(kind, 1.5)
        anchors[idx] = [q for q in anchors[idx]
                        if math.hypot(q["p"][0] - a["p"][0],
                                      q["p"][1] - a["p"][1]) > radius]
        kinds_used[idx].add(kind)
        placed_per_room[idx] += 1
        placed_pts.append((px, py))
        placements.append(dict(kind=kind, x=px, y=py, rot=rot,
                               level=rooms[idx]["level"], rect=rooms[idx]["rect"]))
        placed += 1

    # ---- exact self-check: every piece inside a room, off every wall ------
    bad = [q for q in placements
           if not piece_clear(q["kind"], q["rot"], q["x"], q["y"], q["rect"], walls)]
    if bad:
        raise RuntimeError(f"{spec['name']}: furniture blocking a wall — "
                           + "; ".join(f"{q['kind']} ({q['x']:.1f}, {q['y']:.1f})"
                                       for q in bad[:4]))
    return placed, placed_pts


# ---------------------------------------------------------------------------
# plan + geometry checks  (the CRITICAL RULES of the room pass)
# ---------------------------------------------------------------------------
def point_segment_dist(p, seg):
    (x1, y1), (x2, y2) = seg
    px, py = p
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 == 0.0:
        return math.hypot(px - x1, py - y1)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def segment_hits_box(wall, box, pad=0.0):
    """Does an axis-aligned wall segment cut through an axis-aligned box?"""
    bx0, by0, bx1, by1 = (box[0] - pad, box[1] - pad, box[2] + pad, box[3] + pad)
    if wall.axis == "x":
        return by0 < wall.pos < by1 and wall.lo < bx1 and wall.hi > bx0
    return bx0 < wall.pos < bx1 and wall.lo < by1 and wall.hi > by0


def check_plan(name, walls, rooms, stair_box, entrance_pts):
    """Fail the build if a partition blocks a door, a stair or a room."""
    problems = []

    for wall in walls:
        if stair_box is not None and segment_hits_box(wall, stair_box, pad=0.15):
            problems.append(f"{wall.label} cuts through the staircase")
        for pt in wall.door_points():
            if stair_box is not None and (
                    stair_box[0] - 1.2 <= pt[0] <= stair_box[2] + 1.2 and
                    stair_box[1] - 1.2 <= pt[1] <= stair_box[3] + 1.2):
                problems.append(f"{wall.label}: doorway at {pt} is in the stairwell")
            for other in walls:
                if other is wall:
                    continue
                d = point_segment_dist(pt, other.segment())
                if d < 1.1:
                    problems.append(f"{wall.label}: doorway at {pt} blocked by "
                                    f"{other.label} ({d:.2f} m)")
            for (ex, ey), _inner in entrance_pts:
                if math.hypot(pt[0] - ex, pt[1] - ey) < 2.4:
                    problems.append(f"{wall.label}: doorway at {pt} sits in front "
                                    f"of the main entrance")

    # ---- every room must be reachable through a doorway -------------------
    def room_index(pt):
        for k, r in enumerate(rooms):
            if rect_contains(r, pt):
                return k
        return None

    graph = {k: set() for k in range(len(rooms))}
    for wall in walls:
        nxv, nyv = (0.0, 1.0) if wall.axis == "x" else (1.0, 0.0)
        for (px, py) in wall.door_points():
            a = room_index((px + nxv * 0.35, py + nyv * 0.35))
            b = room_index((px - nxv * 0.35, py - nyv * 0.35))
            if a is None or b is None or a == b:
                problems.append(f"{wall.label}: doorway at ({px:.1f}, {py:.1f}) "
                                f"does not join two rooms")
                continue
            graph[a].add(b)
            graph[b].add(a)

    if entrance_pts:
        start = room_index(entrance_pts[0][1])
        seen = {start}
        stack = [start]
        while stack:
            cur = stack.pop()
            for nxt in graph.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    stack.append(nxt)
        unreachable = [k for k in range(len(rooms)) if k not in seen]
        if unreachable:
            problems.append(f"rooms {unreachable} cannot be reached from the entrance")

    if problems:
        raise RuntimeError(f"{name}: interior plan failed — " + "; ".join(problems))


def check_geometry(obj, name, walls, door_specs, shift, avoid=()):
    """Ray-cast the finished mesh: partitions must be solid, doorways open."""
    ox, oy, oz = shift
    failures = []

    def cast(origin, direction, distance):
        return obj.ray_cast(Vector(origin), Vector(direction), distance=distance)

    def clear_of_furniture(p):
        return all(math.hypot(p[0] - q[0], p[1] - q[1]) > 1.7 for q in avoid)

    tested = 0
    for wall in walls:
        if wall.axis == "y":
            nrm = (1.0, 0.0)
        else:
            nrm = (0.0, 1.0)
        doors = set(wall.door_slots())
        candidates = []
        for k, c in enumerate(wall.slot_centers()):
            if k in doors:                       # solid part beside the doorway
                candidates += [c - 2.6, c - 3.9, c + 2.6, c + 3.9, c - 5.2, c + 5.2]
            else:
                candidates += [c, c - 2.5, c + 2.5]
        for t in candidates:
            if not (wall.lo + 0.6 < t < wall.hi - 0.6):
                continue
            p = (t, wall.pos) if wall.axis == "x" else (wall.pos, t)
            # probe above every furniture piece (the tallest is the 2.0 m
            # shelf) but well below the 3.0 m wall top
            origin = (p[0] + ox - nrm[0] * 1.4, p[1] + oy - nrm[1] * 1.4, 2.65 + oz)
            hit, loc, _n, _i = cast(origin, (nrm[0], nrm[1], 0.0), 2.8)
            tested += 1
            if not hit:
                failures.append(f"{wall.label}: no collision at "
                                f"({p[0]:.1f}, {p[1]:.1f})")

    for (p, nrm) in door_specs:
        origin = (p[0] + ox - nrm[0] * 1.3, p[1] + oy - nrm[1] * 1.3, 1.4 + oz)
        hit, loc, _n, _i = cast(origin, (nrm[0], nrm[1], 0.0), 2.6)
        if hit:
            failures.append(f"doorway at ({p[0]:.1f}, {p[1]:.1f}) is blocked "
                            f"at {loc[0] + 0.0:.1f}")

    if failures:
        raise RuntimeError(f"{name}: geometry check failed — " + "; ".join(failures))
    print(f"      {tested} wall probes + {len(door_specs)} doorways verified")


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

    # ---- interior plan: partitions + the rooms they create ---------------
    plan_walls, room_rects = build_plan(spec)
    stair_cell = tuple(spec["stair_cell"]) if spec.get("stair_cell") else None
    stair_box = None
    if floors > 1 and stair_cell is not None:
        scx, scy = cell_center(stair_cell[0], stair_cell[1], nx, ny)
        sx, sy = scx + STAIR_LOCAL[0], scy + STAIR_LOCAL[1]
        hx, hy = STAIR_SIZE[0] / 2.0, STAIR_SIZE[1] / 2.0
        stair_box = (sx - hx, sy - hy, sx + hx, sy + hy)

    entrance_pts = []
    for (side, i, j) in doors:
        ex, ey, _ = edge_transform(side, i, j, nx, ny)
        nv = edge_normal(side)
        # edge_normal() points out of the building -> step the other way
        entrance_pts.append(((ex, ey), (ex - nv[0] * 2.0, ey - nv[1] * 2.0)))

    check_plan(name, plan_walls, room_rects, stair_box, entrance_pts)

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

    # ---- interior partitions + doorways ----------------------------------
    modules_used += add_partition_walls(plan_walls, floors, wall_mat, parts)

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

    # ---- furniture, inside the rooms -------------------------------------
    interior_door_pts = [pt for w in plan_walls for pt in w.door_points()]
    all_door_pts = interior_door_pts + [e[0] for e in entrance_pts]
    rooms = []
    for level in range(floors):
        kinds = assign_room_kinds(room_rects,
                                  entrance_pts[0][1] if entrance_pts else (0.0, 0.0))
        for rect, kind in zip(room_rects, kinds):
            rooms.append(dict(level=level, rect=rect, kind=kind))
    furniture_count, furniture_pts = furnish(spec, rooms, plan_walls, all_door_pts,
                                             stair_box, parts)

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

    merged = dedupe_materials(obj)
    if merged:
        print(f"      merged {merged} duplicate material slots")

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
    obj["room_count"] = len(room_rects) * floors
    obj["partition_count"] = len(plan_walls)

    # ---- prove the partitions are solid + the doorways are clear ----------
    if spec.get("destroy", 0.0) <= 0.0:
        door_specs = []
        for w in plan_walls:
            n = (0.0, 1.0) if w.axis == "x" else (1.0, 0.0)
            door_specs += [(pt, n) for pt in w.door_points()]
        for (pt, inner) in entrance_pts:
            n = (inner[0] - pt[0], inner[1] - pt[1])
            l = math.hypot(n[0], n[1]) or 1.0
            door_specs.append((pt, (n[0] / l, n[1] / l)))
        shift = (-(min_x + max_x) / 2.0, -(min_y + max_y) / 2.0, -min_z)
        check_geometry(obj, name, plan_walls, door_specs, shift, furniture_pts)
    return obj


# ----------------------------------------------------------------------------
# export / verify
# ----------------------------------------------------------------------------
def dedupe_materials(obj):
    """Collapse duplicate material datablocks (Mod_Wood.001 -> Mod_Wood)."""
    mats = obj.data.materials
    base = lambda n: n.split(".")[0]
    keep, remap = {}, {}
    for i, m in enumerate(mats):
        if m is None:
            continue
        b = base(m.name)
        if b in keep:
            remap[i] = keep[b]
        else:
            keep[b] = i
    if not remap:
        return 0
    for poly in obj.data.polygons:
        if poly.material_index in remap:
            poly.material_index = remap[poly.material_index]
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.material_slot_remove_unused()
    return len(remap)


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

# interior plans ------------------------------------------------------------
# middle + nook  -> 3 rooms per storey: big living/kitchen, hall, small bedroom
HOME_PLAN = dict(type="middle", doors=(0,), nook=dict(side="E", y=7.5))
# hallway       -> central 5 m corridor with 3 rooms on each side
CORRIDOR_PLAN = dict(type="hallway", half_width=2.5)
# cross         -> 1x1 hut split into front room + back bedroom
HUT_PLAN = dict(type="cross", pos=0.0, doors=(0,))

BUILDINGS = [
    dict(name="house_blue", title="House Blue", nx=2, ny=2, floors=2,
         wall="BrightBlue", trim="BlueDark", floor="InteriorFloor",
         roof="slanted", roof_mat="DarkGrey",
         doors=[("S", 0, 0)], windows="all", stair_cell=(1, 1),
         plan=HOME_PLAN,
         furniture={"bed": 2, "shelf": 2, "table": 2, "counter": 2, "crate": 6},
         blurb="2×2, 2 floors, blue walls, living/kitchen + hall + bedroom"),

    dict(name="school_yellow", title="School Yellow", nx=3, ny=2, floors=2,
         wall="SchoolYellow", trim="YellowDark", floor="InteriorFloor",
         roof="flat", roof_mat="FlatConcrete",
         doors=[("S", 1, 0)], windows="all", stair_cell=(2, 1),
         plan=CORRIDOR_PLAN,
         furniture={"table": 12, "shelf": 6, "counter": 3, "crate": 6},
         blurb="3×2, 2 floors, school yellow, 6 classrooms off a central hall"),

    dict(name="apartment_green", title="Apartment Green", nx=2, ny=2, floors=3,
         wall="ConcreteGreen", trim="GreenDark", floor="InteriorFloor",
         roof="flat", roof_mat="FlatConcrete",
         doors=[("S", 1, 0)], windows="all", stair_cell=(0, 0),
         plan=HOME_PLAN,
         furniture={"bed": 4, "table": 3, "shelf": 3, "counter": 2, "crate": 9},
         blurb="2×2, 3 floors, green concrete, one bedroom per floor + stairs"),

    dict(name="warehouse_metal", title="Warehouse Metal", nx=3, ny=2, floors=1,
         wall="SteelBlue", trim="SteelDark", floor="InteriorFloor",
         roof="flat", roof_mat="RustOrange",
         doors=[("S", 0, 0)], garages=[("S", 1, 0)], windows="alternate",
         plan=CORRIDOR_PLAN,
         furniture={"crate": 18, "shelf": 4, "table": 3},
         blurb="3×2, steel blue, rust roof, 6 m garage, 6 store bays + corridor"),

    dict(name="cabin_wood", title="Cabin Wood", nx=1, ny=1, floors=1,
         wall="WoodBrown", trim="WoodDark", floor="InteriorFloor",
         roof="slanted", roof_mat="SlantedRed",
         doors=[("S", 0, 0)], windows="all",
         plan=HUT_PLAN,
         furniture={"bed": 1, "table": 1, "shelf": 1, "counter": 1, "crate": 2},
         blurb="1×1 (15 m), wood, red hip roof, front room + back bedroom"),

    dict(name="ruined_building", title="Ruined Building", nx=2, ny=2, floors=2,
         wall="DamagedConcrete", trim="ConcreteDark", floor="RubbleGrey",
         roof="none",
         doors=[("S", 0, 0)], windows="all", stair_cell=(1, 1),
         missing_walls=[("N", 1, 1, 1), ("E", 1, 0, 1), ("S", 0, 1, 1)],
         destroy=0.20, seed=11,
         plan=dict(type="middle", doors=(0,), nook=dict(side="E", y=7.5)),
         furniture={"crate": 8, "shelf": 2},
         details=[("wall_holes", 5, 3), ("rubble", 9, 5)],
         blurb="2×2, 2 floors, damaged concrete, shattered interior partitions"),

    dict(name="shop_row", title="Shop Row", nx=2, ny=1, floors=1,
         wall="OffWhite", trim="WoodDark", floor="InteriorFloor",
         roof="slanted", roof_mat="SlantedRed",
         doors=[("S", 0, 0), ("S", 1, 0)], windows="all",
         plan=dict(type="middle", doors=(0,)),
         furniture={"counter": 4, "shelf": 6, "table": 2, "crate": 2},
         details=[("awning", "S", 0, 0), ("awning", "S", 1, 0)],
         blurb="2×1 (30×15 m), off-white, two shops joined by an internal door"),

    dict(name="villa_white", title="Villa White", nx=2, ny=2, floors=2,
         footprint=VILLA_L,
         wall="OffWhite", trim="StoneGrey", floor="InteriorFloor",
         roof="flat", roof_mat="FlatConcrete",
         doors=[("S", 1, 0)], windows="all", stair_cell=(0, 1),
         plan=dict(type="custom", walls=[
             dict(axis="y", pos=0.0, lo=-14.8, hi=0.0, doors=(0,), label="villaMid"),
             dict(axis="x", pos=0.0, lo=-14.8, hi=-0.05, doors=(0,), label="villaNorth"),
         ]),
         furniture={"sofa": 4, "table": 3, "bed": 2, "shelf": 2,
                    "counter": 2, "crate": 4},
         details=[("roof_terrace", 1, 0)],
         blurb="L-shaped 2×2, off-white, 3 rooms/floor + roof terrace"),

    dict(name="farmhouse_stone", title="Farmhouse Stone", nx=2, ny=1, floors=1,
         wall="BrickRed", trim="BrickDark", floor="InteriorFloor",
         roof="slanted", roof_mat="TiledTerracotta",
         doors=[("S", 1, 0)], windows="all",
         plan=dict(type="middle", doors=(0,)),
         furniture={"bed": 1, "table": 4, "shelf": 2, "crate": 5},
         blurb="2×1 (30×15 m), brick red, kitchen + bedroom either side"),

    dict(name="bunker_military", title="Bunker Military", nx=1, ny=1, floors=1,
         wall="DarkCamoGreen", wall_alt="CamoBrown", trim="BunkerTrim",
         floor="InteriorFloor",
         roof="flat", roof_mat="FlatConcrete",
         doors=[("S", 0, 0)], windows="none",
         plan=HUT_PLAN,
         furniture={"crate": 8, "shelf": 4, "bed": 1},
         blurb="1×1, camo green, no windows, bunk room + supply room"),

    dict(name="tower_sniper", title="Tower Sniper", nx=1, ny=1, floors=4,
         wall="ConcreteGrey", trim="ConcreteDark", floor="InteriorFloor",
         roof="open", roof_mat="FlatConcrete",
         doors=[("S", 0, 0)], windows="all", stair_cell=(0, 0),
         plan=HUT_PLAN,
         furniture={"crate": 2, "shelf": 1},
         blurb="1×1, 4 floors (13 m), concrete grey, open top, 2 rooms/floor"),
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
        rc = obj.get("room_count", 0)
        pc = obj.get("partition_count", 0)
        path = export_glb(obj, spec["name"] + ".glb")
        exported.append(path)
        print(f"      {mc} modules · {fc} furniture pieces · "
              f"{pc} partition walls · {rc} rooms")

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
