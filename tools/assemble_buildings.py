#!/usr/bin/env python3
"""
Assemble the 11 standard Battle-Royale buildings from the modular "Lego" blocks.
===============================================================================
Task 2: imports the 8 modules from docs/models/modules/ and places them at exact
X / Y / Z coordinates per building recipe, then joins each building into ONE
mesh and exports it.

Modules (all 10 m grid, wall 3 m high, origin bottom-centre):
  mod_wall_solid / mod_wall_window / mod_wall_door / mod_wall_garage
  mod_floor / mod_roof_flat / mod_roof_slanted / mod_stairs

The 11 buildings (recipe list at the bottom of this file):
  house_small · cabin_wood · house_tactical · school_yellow · apartment_green
  warehouse_metal · warehouse · garage · sniper_tower · ruined_building · shop_row

Output: docs/models/buildings/modular/<name>.glb   (originals are NOT touched)
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
OUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "buildings", "modular")
os.makedirs(OUT_DIR, exist_ok=True)

GRID = 10.0          # module footprint
STOREY = 3.0         # wall module height
SLAB = 0.2           # floor slab thickness
WALL_T = 0.2
STAIR_Z_SCALE = 1.5  # the 2.0 m / 10-step module stretched to bridge a 3 m storey

bpy.ops.wm.read_factory_settings(use_empty=True)

# ----------------------------------------------------------------------------
# palette (hex sRGB -> linear, so the GLB shows the intended colour)
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


PALETTE = {
    "Sandstone": ("#D9C089", 0.80, 0.0),
    "SandstoneLight": ("#EDDBB3", 0.78, 0.0),
    "SandstoneDark": ("#B39466", 0.82, 0.0),
    "BrickRed": ("#9E4B3C", 0.82, 0.0),
    "BrickDark": ("#7A3A2E", 0.85, 0.0),
    "ConcreteGrey": ("#B4B4AE", 0.85, 0.0),
    "ConcreteDark": ("#8E8E88", 0.87, 0.0),
    "Wood": ("#8B5A2B", 0.80, 0.0),
    "WoodDark": ("#5E3A1B", 0.85, 0.0),
    "Yellow": ("#E8C24A", 0.80, 0.0),
    "YellowLight": ("#F2D97A", 0.78, 0.0),
    "Green": ("#5E9E5A", 0.80, 0.0),
    "GreenDark": ("#3F7A44", 0.82, 0.0),
    "SteelBlue": ("#4A7C99", 0.55, 0.25),
    "SteelDark": ("#35596E", 0.55, 0.25),
    "Rust": ("#B4552E", 0.75, 0.0),
    "Teal": ("#2FA8A0", 0.55, 0.1),
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
    print(f"  loaded {len(_MODULE_MESHES)} modules: {', '.join(sorted(_MODULE_MESHES))}")


def place(key: str, name: str, loc, rot_z=0.0, scale=(1.0, 1.0, 1.0),
          material=None, parts=None, keep_slots_above=None):
    """Instance a module mesh at an exact position, optionally recoloured."""
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
            # keep the secondary slot (e.g. the sandstone coping on mod_roof_flat)
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
# building assembly
# ----------------------------------------------------------------------------
def side_wall_positions(nx, ny, side):
    """(x, y, rot_z) for every wall module along one side of the footprint."""
    W, D = nx * GRID, ny * GRID
    out = []
    if side in ("S", "N"):
        y = (-D / 2 + WALL_T / 2) if side == "S" else (D / 2 - WALL_T / 2)
        for i in range(nx):
            out.append((-W / 2 + GRID / 2 + i * GRID, y, 0.0))
    else:
        x = (-W / 2 + WALL_T / 2) if side == "W" else (W / 2 - WALL_T / 2)
        for j in range(ny):
            out.append((x, -D / 2 + GRID / 2 + j * GRID, math.pi / 2))
    return out


def assemble(spec: dict) -> bpy.types.Object:
    name = spec["name"]
    nx, ny, floors = spec["nx"], spec["ny"], spec["floors"]
    W, D = nx * GRID, ny * GRID
    parts: list[bpy.types.Object] = []

    wall_mat = P(spec.get("wall", "Sandstone"))
    trim_mat = P(spec.get("trim", "SandstoneDark"))
    floor_mat = P(spec.get("floor", "ConcreteGrey"))
    roof_mat = P(spec.get("roof_mat", "BrickRed"))

    walls = spec.get("walls", {})
    modules_used = 0

    # ---- floor slabs (one per storey) -------------------------------------
    for level in range(floors):
        z = max(0.0, level * STOREY - SLAB)
        for ix in range(nx):
            for iy in range(ny):
                place("floor", f"Slab{level}_{ix}_{iy}",
                      (-W / 2 + GRID / 2 + ix * GRID, -D / 2 + GRID / 2 + iy * GRID, z),
                      material=floor_mat, parts=parts)
                modules_used += 1

    # ---- walls (per side, per 10 m bay, per storey) -----------------------
    for level in range(floors):
        z = level * STOREY
        for side in ("S", "N", "E", "W"):
            pattern = list(walls.get(side, ["solid"] * (nx if side in "SN" else ny)))
            bay_count = nx if side in ("S", "N") else ny
            pattern = (pattern + ["solid"] * bay_count)[:bay_count]
            for idx, (x, y, rot) in enumerate(side_wall_positions(nx, ny, side)):
                variant = pattern[idx]
                if level > 0 and variant == "door":
                    variant = "window"   # only the ground floor gets doors
                key = {"solid": "wall_solid", "window": "wall_window",
                       "door": "wall_door", "garage": "wall_garage"}.get(variant, "wall_solid")
                place(key, f"Wall{level}_{side}{idx}", (x, y, z), rot_z=rot,
                      material=wall_mat, parts=parts)
                modules_used += 1

    # ---- optional interior partition --------------------------------------
    if spec.get("partition"):
        # interior spine wall across the depth, with a doorway so rooms stay walkable
        for i in range(spec["partition"]):
            y = -D / 2 + GRID * (i + 1)
            if abs(y) < D / 2 - 0.5:
                place("wall_door", f"Partition{i}", (0.0, y, 0.0),
                      rot_z=math.pi / 2, scale=(1.0, ny, 1.0),
                      material=trim_mat, parts=parts)
                modules_used += 1

    # ---- stairs (multi-storey) -------------------------------------------
    if floors > 1:
        for level in range(floors - 1):
            sx = -W / 2 + 2.4
            sy = -D / 2 + 2.2
            place("stairs", f"Stairs{level}", (sx, sy, level * STOREY),
                  scale=(1.0, 1.0, STAIR_Z_SCALE), material=floor_mat, parts=parts)
            modules_used += 1

    # ---- roof -------------------------------------------------------------
    roof = spec.get("roof", "flat")
    roof_z = floors * STOREY
    if roof == "flat":
        for ix in range(nx):
            for iy in range(ny):
                place("roof_flat", f"Roof{ix}_{iy}",
                      (-W / 2 + GRID / 2 + ix * GRID, -D / 2 + GRID / 2 + iy * GRID, roof_z),
                      material=roof_mat, keep_slots_above=1, parts=parts)
                modules_used += 1
    elif roof == "slanted":
        place("roof_slanted", "RoofSlanted", (0.0, 0.0, roof_z),
              scale=(nx, ny, 1.0), material=roof_mat, parts=parts)
        modules_used += 1

    # ---- optional extra details ------------------------------------------
    for i, detail in enumerate(spec.get("details", [])):
        kind = detail[0]
        if kind == "awning":       # wood shop awning over the front
            dx, dy, dz, sx, sy = detail[1]
            mesh = bpy.data.meshes.new(f"Awning{i}Mesh")
            verts = [(-sx / 2, -sy / 2, 0), (sx / 2, -sy / 2, 0),
                     (sx / 2, sy / 2, 0), (-sx / 2, sy / 2, 0)]
            mesh.from_pydata(verts, [], [(0, 1, 2, 3)])
            mesh.update()
            obj = bpy.data.objects.new(f"Awning{i}", mesh)
            bpy.context.collection.objects.link(obj)
            obj.location = (dx, dy, dz)
            obj.rotation_euler = (math.radians(18), 0.0, 0.0)
            obj.data.materials.append(P("Wood"))
            for poly in obj.data.polygons:
                poly.use_smooth = False
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
            solid = obj.modifiers.new("Solid", type="SOLIDIFY")
            solid.thickness = 0.12
            bpy.ops.object.modifier_apply(modifier=solid.name)
            parts.append(obj)
        elif kind == "rubble":
            rng = random.Random(detail[1])
            for k in range(detail[2]):
                bpy.ops.mesh.primitive_cube_add(size=1.0, location=(
                    rng.uniform(-W / 2 + 1, W / 2 - 1),
                    rng.uniform(-D / 2 + 1, D / 2 - 1),
                    rng.uniform(0.1, 0.45)))
                o = bpy.context.active_object
                o.name = f"Rubble{k}"
                o.scale = (rng.uniform(0.5, 1.6), rng.uniform(0.5, 1.6),
                           rng.uniform(0.25, 0.8))
                o.rotation_euler = (0.0, 0.0, rng.uniform(0, math.pi))
                bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
                o.data.materials.clear()
                o.data.materials.append(P("ConcreteDark") if "Grey" not in spec.get("wall", "")
                                        else P("ConcreteGrey"))
                for poly in o.data.polygons:
                    poly.use_smooth = False
                parts.append(o)

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

    # ---- optional destruction -------------------------------------------
    if spec.get("destroy", 0.0) > 0.0:
        destroy(obj, spec["destroy"], seed=spec.get("seed", 7))

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
    return obj


def destroy(obj, ratio: float, seed: int = 7):
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
    print(f"    destroyed {len(victims)} faces ({ratio * 100:.0f}% target)")


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
    print(f"  {os.path.basename(path):26s} {max(xs) - min(xs):5.1f} x "
          f"{max(ys) - min(ys):5.1f} x {max(zs) - min(zs):5.1f} m  "
          f"minZ {min(zs):+.3f}  {tris:6d} tris  {mats} mats  {size / 1024:6.1f} KB")
    return min(zs)


# ----------------------------------------------------------------------------
# the 11 building recipes
# ----------------------------------------------------------------------------
BUILDINGS = [
    dict(name="house_small", title="House Small — 2×2, sandstone, slanted roof",
         nx=2, ny=2, floors=1, roof="slanted",
         wall="Sandstone", trim="WoodDark", floor="ConcreteGrey", roof_mat="BrickRed",
         walls={"S": ["door", "window"], "N": ["window", "solid"],
                "E": ["window", "solid"], "W": ["solid", "solid"]},

         details=[("awning", (0.0, -5.4, 2.3, 4.0, 1.6))]),
    dict(name="cabin_wood", title="Cabin Wood — 1×1, wood, slanted roof",
         nx=1, ny=1, floors=1, roof="slanted",
         wall="Wood", trim="WoodDark", floor="ConcreteDark", roof_mat="BrickRed",
         walls={"S": ["door"], "N": ["solid"], "E": ["window"], "W": ["window"]}),
    dict(name="house_tactical", title="House Tactical — 2×2, red brick, 2 floors, slanted roof",
         nx=2, ny=2, floors=2, roof="slanted", partition=1,
         wall="BrickRed", trim="Wood", floor="ConcreteDark", roof_mat="Rust",
         walls={"S": ["door", "window"], "N": ["window", "window"],
                "E": ["window", "solid"], "W": ["solid", "window"]}),
    dict(name="school_yellow", title="School Yellow — 3×2, 2 floors, flat roof",
         nx=3, ny=2, floors=2, roof="flat", partition=1,
         wall="Yellow", trim="SandstoneLight", floor="ConcreteGrey", roof_mat="ConcreteGrey",
         walls={"S": ["window", "door", "window"], "N": ["window", "window", "window"],
                "E": ["window", "window"], "W": ["window", "window"]}),
    dict(name="apartment_green", title="Apartment Green — 2×2, 3 floors, flat roof",
         nx=2, ny=2, floors=3, roof="flat", partition=1,
         wall="Green", trim="GreenDark", floor="ConcreteGrey", roof_mat="ConcreteGrey",
         walls={"S": ["door", "window"], "N": ["window", "window"],
                "E": ["window", "window"], "W": ["window", "window"]}),
    dict(name="warehouse_metal", title="Warehouse Metal — 3×2, steel blue, flat roof, 6 m garage door",
         nx=3, ny=2, floors=1, roof="flat",
         wall="SteelBlue", trim="SteelDark", floor="ConcreteDark", roof_mat="Rust",
         walls={"S": ["window", "garage", "window"], "N": ["solid", "solid", "solid"],
                "E": ["solid", "solid"], "W": ["solid", "solid"]}),
    dict(name="warehouse", title="Warehouse — 3×2, concrete, flat roof",
         nx=3, ny=2, floors=1, roof="flat",
         wall="ConcreteGrey", trim="ConcreteDark", floor="ConcreteDark", roof_mat="Rust",
         walls={"S": ["window", "garage", "window"], "N": ["solid", "solid", "solid"],
                "E": ["solid", "solid"], "W": ["solid", "solid"]}),
    dict(name="garage", title="Garage — 1×1, concrete, flat roof",
         nx=1, ny=1, floors=1, roof="flat",
         wall="ConcreteGrey", trim="ConcreteDark", floor="ConcreteDark", roof_mat="Rust",
         walls={"S": ["garage"], "N": ["solid"], "E": ["solid"], "W": ["solid"]}),
    dict(name="sniper_tower", title="Sniper Tower — 1×1, 4 floors, flat roof",
         nx=1, ny=1, floors=4, roof="flat",
         wall="ConcreteDark", trim="ConcreteGrey", floor="ConcreteGrey", roof_mat="ConcreteGrey",
         walls={"S": ["window"], "N": ["window"], "E": ["window"], "W": ["window"]}),
    dict(name="ruined_building", title="Ruined Building — 2×2, 2 floors, bombed out",
         nx=2, ny=2, floors=2, roof="none", partition=1,
         wall="ConcreteDark", trim="ConcreteGrey", floor="ConcreteDark", roof_mat="ConcreteGrey",
         walls={"S": ["door", "window"], "N": ["window", "solid"],
                "E": ["window", "solid"], "W": ["solid", "window"]},
         destroy=0.18, seed=11, details=[("rubble", 5, 7)]),
    dict(name="shop_row", title="Shop Row — 2×1, sandstone, slanted roof, 2 shopfronts",
         nx=2, ny=1, floors=1, roof="slanted",
         wall="Sandstone", trim="Wood", floor="ConcreteGrey", roof_mat="Teal",
         walls={"S": ["door", "door"], "N": ["window", "window"],
                "E": ["solid"], "W": ["solid"]},
         details=[("awning", (-5.0, -5.3, 2.3, 8.5, 1.6)),
                  ("awning", (5.0, -5.3, 2.3, 8.5, 1.6))]),
]


def main():
    print(f"Blender bpy {bpy.app.version_string}")
    print("— loading modules —")
    load_modules()

    print("— assembling 11 buildings —")
    exported = []
    for spec in BUILDINGS:
        print(f"  · {spec['name']}  ({spec['nx']}×{spec['ny']} grid, {spec['floors']} floor(s), "
              f"{spec['roof']} roof)")
        obj = assemble(spec)
        x0, x1 = min(v.co.x for v in obj.data.vertices), max(v.co.x for v in obj.data.vertices)
        y0, y1 = min(v.co.y for v in obj.data.vertices), max(v.co.y for v in obj.data.vertices)
        z1 = max(v.co.z for v in obj.data.vertices)
        mc = obj.get("module_count", 0)
        path = export_glb(obj, spec["name"] + ".glb")
        exported.append(path)
        print(f"      {x1 - x0:.1f} × {y1 - y0:.1f} × {z1:.1f} m · {mc} modules")

    print("— verification (re-import) —")
    bad = []
    for path in exported:
        min_z = verify(path)
        if abs(min_z) > 1e-4:
            bad.append((path, min_z))
    if bad:
        raise RuntimeError(f"origin verification failed: {bad}")
    print(f"Done — {len(exported)} modular buildings generated in docs/models/buildings/modular/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
