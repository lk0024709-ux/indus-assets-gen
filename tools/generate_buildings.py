#!/usr/bin/env python3
"""Building-asset generator for the Indus : Battle Royale 3D pipeline.

Runs headless through the pip-installable ``bpy`` module (Blender as a Python
module) and generates four textured, game-ready buildings:

1. ``garage.glb``       — 10m x 8m x 4m,  flat roof, 4m x 3m door cutout
2. ``sniper_tower.glb`` — 4m x 4m base,  10m tall, platform @ 8m, railings
3. ``house_small.glb``  — 6m x 6m x 3.5m walls, door + 2 windows, gable roof
4. ``warehouse.glb``    — 15m x 10m x 6m, sliding doors (5m x 4.5m), flat roof

Pipeline rules enforced for every building:

* real-world scale, 1 Blender unit = 1 metre (scene unit settings set to metric)
* the building's origin sits exactly at its bottom-centre -> (0, 0, 0)
* every mesh is UV-unwrapped with ``bpy.ops.uv.smart_project()`` BEFORE any
  material is applied
* materials are Principled BSDF + Image Texture (texture -> Base Color), using
  the seamless AI-generated textures in ``docs/textures/``
* boolean cutters (``modifier_apply``) create the door/window openings
* glTF export with ``export_image_format='JPEG'`` so textures are converted and
  packed inside the ``.glb`` container

Usage:
    pip install bpy
    python tools/generate_buildings.py
"""

from __future__ import annotations

import json
import math
import os
import struct
import sys

import bpy
from mathutils import Matrix, Vector

# --- Paths -----------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURE_DIR = os.path.join(REPO_ROOT, "docs", "textures")
OUTPUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "buildings")

# --- Material presets -------------------------------------------------------
MATERIALS = {
    "concrete": {"file": "concrete_wall.png", "roughness": 0.90, "metallic": 0.00, "uv_scale": 1.0},
    "wood": {"file": "wood_plank.png", "roughness": 0.72, "metallic": 0.00, "uv_scale": 1.0},
    "brick": {"file": "brick_wall.png", "roughness": 0.85, "metallic": 0.00, "uv_scale": 2.5},
    "metal": {"file": "metal_corrugated.png", "roughness": 0.50, "metallic": 0.70, "uv_scale": 1.5},
}


# ---------------------------------------------------------------------------
# Scene / object helpers
# ---------------------------------------------------------------------------
def clear_scene() -> None:
    """Reset Blender to a completely empty scene."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def set_metric_units() -> None:
    """Declare real-world metre scale for the scene."""
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0


def create_box(name: str, size, location=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0)):
    """Create a box of ``size`` (x, y, z metres) and bake all transforms.

    The object's mesh data ends up in world space with the object origin at
    (0, 0, 0), which keeps joins and boolean cuts simple and predictable.
    """
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "Mesh"
    obj.dimensions = tuple(size)
    obj.rotation_euler = rotation
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def create_triangular_prism(name, x_min, x_max, tri_yz):
    """Triangular prism (gable wall): triangle ``tri_yz`` extruded along x.

    ``tri_yz`` is a list of three (y, z) points.
    """
    (y0, z0), (y1, z1), (y2, z2) = tri_yz
    verts = [
        (x_min, y0, z0), (x_min, y1, z1), (x_min, y2, z2),
        (x_max, y0, z0), (x_max, y1, z1), (x_max, y2, z2),
    ]
    faces = [
        (0, 2, 1), (3, 4, 5),          # end triangles
        (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5),  # slope + base quads
    ]
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def apply_boolean_cut(target, cutter) -> None:
    """Cut ``cutter`` out of ``target`` with a boolean difference, then remove
    the cutter object. Used for door/window openings."""
    mod = target.modifiers.new(name="Cutout", type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    if hasattr(mod, "solver"):
        try:
            mod.solver = "EXACT"
        except (TypeError, ValueError):
            pass
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def smart_unwrap(obj, uv_scale: float = 1.0) -> None:
    """UV-unwrap ``obj`` with bpy.ops.uv.smart_project()."""
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    try:
        bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.02)
    except TypeError:
        bpy.ops.uv.smart_project()
    bpy.ops.object.mode_set(mode="OBJECT")
    if uv_scale != 1.0:
        for layer in obj.data.uv_layers:
            for loop_uv in layer.data:
                loop_uv.uv = loop_uv.uv * uv_scale
    # Orient textures upright on vertical faces (e.g. brick courses horizontal,
    # corrugation ribs vertical). smart_project picks each island's rotation;
    # for wall-like faces, rotate per-face UVs 90 degrees unless texture V is
    # already the face's vertical axis.
    uvl = obj.data.uv_layers.active
    me = obj.data

    def _cov(a, b):
        n = len(a)
        if n < 2:
            return 0.0
        ma = sum(a) / n
        mb = sum(b) / n
        return sum((a[i] - ma) * (b[i] - mb) for i in range(n)) / n

    for poly in me.polygons:
        if abs(poly.normal.z) >= 0.55:
            continue
        idxs = list(poly.loop_indices)
        us = [uvl.data[i].uv.x for i in idxs]
        vs = [uvl.data[i].uv.y for i in idxs]
        zs = [me.vertices[me.loops[i].vertex_index].co.z for i in idxs]
        if abs(_cov(us, zs)) > abs(_cov(vs, zs)):
            # texture U carries the vertical direction -> rotate 90 degrees
            cx = sum(us) / len(us)
            cy = sum(vs) / len(vs)
            for i, u, v in zip(idxs, us, vs):
                x, y = u - cx, v - cy
                uvl.data[i].uv = (cx - y, cy + x)


def make_material(name: str, preset: str):
    """Principled BSDF material with an Image Texture driving Base Color."""
    spec = MATERIALS[preset]
    mat = bpy.data.materials.new(name)
    # Node-based materials are mandatory since Blender 5.0 (use_nodes deprecated).
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError("Principled BSDF node not found in new material")

    tex_path = os.path.join(TEXTURE_DIR, spec["file"])
    if not os.path.isfile(tex_path):
        raise FileNotFoundError(f"Texture not found: {tex_path}")
    image = bpy.data.images.load(tex_path, check_existing=True)

    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.name = f"{name}_Texture"
    tex.label = spec["file"]
    tex.image = image
    tex.extension = "REPEAT"
    tex.location = (-350.0, 220.0)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

    bsdf.inputs["Roughness"].default_value = spec["roughness"]
    bsdf.inputs["Metallic"].default_value = spec["metallic"]
    return mat


def assign_material(obj, mat) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def join_objects(objects, name):
    """Join part meshes into one object and name it."""
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    joined = bpy.context.active_object
    joined.name = name
    joined.data.name = name + "Mesh"
    return joined


def set_origin_bottom_center(obj) -> None:
    """Move mesh data so the world bounding-box bottom-centre sits exactly at
    the object origin (0, 0, 0)."""
    coords = [obj.matrix_world @ v.co for v in obj.data.vertices]
    min_x = min(c.x for c in coords)
    max_x = max(c.x for c in coords)
    min_y = min(c.y for c in coords)
    max_y = max(c.y for c in coords)
    min_z = min(c.z for c in coords)
    offset = Vector((-(min_x + max_x) / 2.0, -(min_y + max_y) / 2.0, -min_z))
    obj.data.transform(Matrix.Translation(offset))
    obj.data.validate(clean_customdata=True)  # fix windings / degenerate data
    obj.data.update()
    obj.matrix_world = Matrix.Identity(4)
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)


def object_bbox(obj):
    coords = [obj.matrix_world @ v.co for v in obj.data.vertices]
    return (
        min(c.x for c in coords), max(c.x for c in coords),
        min(c.y for c in coords), max(c.y for c in coords),
        min(c.z for c in coords), max(c.z for c in coords),
    )


def export_glb(filename: str) -> str:
    """Export the scene as a packed binary glTF (.glb)."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, filename)
    export_kwargs = dict(
        filepath=path,
        export_format="GLB",
        export_image_format="JPEG",   # textures converted + packed into the GLB
    )
    try:
        bpy.ops.export_scene.gltf(export_image_quality=90, **export_kwargs)
    except TypeError:
        bpy.ops.export_scene.gltf(**export_kwargs)
    if not os.path.isfile(path):
        raise RuntimeError(f"Export failed, file not written: {path}")
    return path


def verify_glb(path: str) -> None:
    """Sanity-check the GLB container: textures packed + expected mesh present."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"glTF":
        raise RuntimeError(f"Not a GLB file: {path}")
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_len])
    images = gltf.get("images", [])
    materials = gltf.get("materials", [])
    textures = gltf.get("textures", [])
    if not images:
        raise RuntimeError(f"No packed images found in {path}")
    for img in images:
        if "bufferView" not in img and "uri" not in img:
            raise RuntimeError(f"Image not embedded in {path}: {img}")
    print(
        f"  verified {os.path.basename(path)}: {os.path.getsize(path)} bytes, "
        f"{len(materials)} material(s), {len(textures)} texture(s), "
        f"{len(images)} packed image(s)"
    )


# ---------------------------------------------------------------------------
# Building 1: Garage — 10m x 8m x 4m, flat roof, 4m x 3m door cutout
# ---------------------------------------------------------------------------
def build_garage():
    w, d, h = 10.0, 8.0, 4.0
    t = 0.28                     # wall thickness
    wall_h = 3.72                # walls stop here; flat roof slab -> h
    parts = []
    parts.append(create_box("Garage_Floor", (w, d, 0.20), (0.0, 0.0, 0.10)))
    # side walls span the full depth; front/back fit between them (no coplanar corners)
    parts.append(create_box("Garage_Wall_Left", (t, d, wall_h), (-w / 2 + t / 2, 0.0, wall_h / 2)))
    parts.append(create_box("Garage_Wall_Right", (t, d, wall_h), (w / 2 - t / 2, 0.0, wall_h / 2)))
    parts.append(create_box("Garage_Wall_Front", (w - 2 * t, t, wall_h), (0.0, -d / 2 + t / 2, wall_h / 2)))
    parts.append(create_box("Garage_Wall_Back", (w - 2 * t, t, wall_h), (0.0, d / 2 - t / 2, wall_h / 2)))
    roof = create_box("Garage_Roof", (w, d, h - wall_h), (0.0, 0.0, (h + wall_h) / 2))
    parts.append(roof)

    # 4m x 3m door opening, boolean-cut through the front wall
    front = parts[4]
    cutter = create_box("Garage_DoorCutter", (4.0, t + 0.8, 3.0), (0.0, -d / 2 + t / 2, 1.5))
    apply_boolean_cut(front, cutter)

    # UV-unwrap every mesh BEFORE materials are applied
    for p in parts:
        smart_unwrap(p, MATERIALS["concrete"]["uv_scale"])
    mat = make_material("Garage_Concrete", "concrete")
    for p in parts:
        assign_material(p, mat)

    garage = join_objects(parts, "Garage")
    set_origin_bottom_center(garage)
    return garage


# ---------------------------------------------------------------------------
# Building 2: Sniper tower — 4m x 4m base, 10m tall, platform @ 8m
# ---------------------------------------------------------------------------
def build_sniper_tower():
    parts = []
    # 4 pillars (0.5m x 0.5m) at the base corners; tops embed into the platform
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            parts.append(create_box(
                f"Tower_Pillar_{int(sx > 0)}{int(sy > 0)}",
                (0.5, 0.5, 7.85), (sx * 1.72, sy * 1.72, 3.925)))

    # wooden platform at 8m (top surface exactly z = 8.0)
    parts.append(create_box("Tower_Platform", (4.0, 4.0, 0.22), (0.0, 0.0, 7.89)))

    # railings around the platform: 4 corner posts + top and mid rails
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            parts.append(create_box(
                f"Tower_RailPost_{int(sx > 0)}{int(sy > 0)}",
                (0.1, 0.1, 1.14), (sx * 1.9, sy * 1.9, 8.49)))
    for z, tag in ((8.95, "Top"), (8.52, "Mid")):
        for s in (-1.0, 1.0):
            parts.append(create_box(f"Tower_RailX_{tag}_{int(s > 0)}", (0.1, 4.0, 0.1), (s * 1.95, 0.0, z)))
            parts.append(create_box(f"Tower_RailY_{tag}_{int(s > 0)}", (4.0, 0.1, 0.1), (0.0, s * 1.95, z)))

    # roof posts (embed into platform and roof slab) + small roof (top z = 10.0)
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            parts.append(create_box(
                f"Tower_RoofPost_{int(sx > 0)}{int(sy > 0)}",
                (0.18, 0.18, 1.96), (sx * 1.75, sy * 1.75, 8.90)))
    parts.append(create_box("Tower_Roof", (4.0, 4.0, 0.18), (0.0, 0.0, 9.91)))

    for p in parts:
        smart_unwrap(p, MATERIALS["wood"]["uv_scale"])
    mat = make_material("Tower_Wood", "wood")
    for p in parts:
        assign_material(p, mat)

    tower = join_objects(parts, "SniperTower")
    set_origin_bottom_center(tower)
    return tower


# ---------------------------------------------------------------------------
# Building 3: Small house — 6m x 6m x 3.5m walls, gable roof
# ---------------------------------------------------------------------------
def build_house_small():
    w, d, wall_h = 6.0, 6.0, 3.5
    t = 0.22
    angle = math.radians(28.0)   # roof pitch
    run = 3.4                    # half-span + 0.4m overhang
    ridge_z = wall_h + run * math.tan(angle)   # ~5.31m at y = 0 (overhang line)

    shell = []
    shell.append(create_box("House_Floor", (w, d, 0.18), (0.0, 0.0, 0.09)))
    # side walls span the full depth; front/back fit between them (no coplanar corners)
    shell.append(create_box("House_Wall_Left", (t, d, wall_h), (-w / 2 + t / 2, 0.0, wall_h / 2)))
    shell.append(create_box("House_Wall_Right", (t, d, wall_h), (w / 2 - t / 2, 0.0, wall_h / 2)))
    shell.append(create_box("House_Wall_Front", (w - 2 * t, t, wall_h), (0.0, -d / 2 + t / 2, wall_h / 2)))
    shell.append(create_box("House_Wall_Back", (w - 2 * t, t, wall_h), (0.0, d / 2 - t / 2, wall_h / 2)))
    walls = join_objects(shell, "House_Walls")

    # door: 1.2m x 2.2m through the front wall
    cutter = create_box("House_DoorCutter", (1.2, t + 0.8, 2.2), (0.0, -d / 2 + t / 2, 1.1))
    apply_boolean_cut(walls, cutter)
    # two windows: 1.2m x 1.2m through the left and right walls
    for sx in (-1.0, 1.0):
        cutter = create_box("House_WindowCutter", (t + 0.8, 1.2, 1.2), (sx * (w / 2 - t / 2), 0.0, 1.8))
        apply_boolean_cut(walls, cutter)

    # gable prism fills the attic; its sloped faces hide under the roof slabs
    apex_z = wall_h + (d / 2) * math.tan(angle) - 0.04   # just under the roof line
    gable = create_triangular_prism(
        "House_Gable", -w / 2, w / 2,
        [(-d / 2 + 0.03, wall_h - 0.03), (d / 2 - 0.03, wall_h - 0.03), (0.0, apex_z)])

    # two slanted roof slabs (wood), rotated about X
    slab_len = run / math.cos(angle)          # slope length
    mid_y = run / 2.0
    mid_z = ridge_z - mid_y * math.tan(angle) - 0.16 / (2 * math.cos(angle))
    roof_slabs = []
    for sy in (-1.0, 1.0):
        roof_slabs.append(create_box(
            f"House_RoofSlab_{int(sy > 0)}",
            (w + 0.8, slab_len, 0.16),
            (0.0, sy * mid_y, mid_z),
            rotation=(-sy * angle, 0.0, 0.0)))

    # UV-unwrap every mesh BEFORE any material is applied
    for p in [walls, gable]:
        smart_unwrap(p, MATERIALS["brick"]["uv_scale"])
    for slab in roof_slabs:
        smart_unwrap(slab, MATERIALS["wood"]["uv_scale"])

    mat_brick = make_material("House_Brick", "brick")
    mat_wood = make_material("House_RoofWood", "wood")
    assign_material(walls, mat_brick)
    assign_material(gable, mat_brick)
    for slab in roof_slabs:
        assign_material(slab, mat_wood)

    house = join_objects([walls, gable] + roof_slabs, "HouseSmall")
    set_origin_bottom_center(house)
    return house


# ---------------------------------------------------------------------------
# Building 4: Warehouse — 15m x 10m x 6m, sliding doors 5m x 4.5m, flat roof
# ---------------------------------------------------------------------------
def build_warehouse():
    w, d, h = 15.0, 10.0, 6.0
    t = 0.30
    wall_h = 5.72                # walls stop here; flat roof slab -> h
    parts = []
    parts.append(create_box("Warehouse_Floor", (w, d, 0.25), (0.0, 0.0, 0.125)))
    # side walls span the full depth; front/back fit between them (no coplanar corners)
    parts.append(create_box("Warehouse_Wall_Left", (t, d, wall_h), (-w / 2 + t / 2, 0.0, wall_h / 2)))
    parts.append(create_box("Warehouse_Wall_Right", (t, d, wall_h), (w / 2 - t / 2, 0.0, wall_h / 2)))
    parts.append(create_box("Warehouse_Wall_Front", (w - 2 * t, t, wall_h), (0.0, -d / 2 + t / 2, wall_h / 2)))
    parts.append(create_box("Warehouse_Wall_Back", (w - 2 * t, t, wall_h), (0.0, d / 2 - t / 2, wall_h / 2)))
    parts.append(create_box("Warehouse_Roof", (w, d, h - wall_h), (0.0, 0.0, (h + wall_h) / 2)))

    # 5m x 4.5m opening through the front wall
    front = parts[4]
    cutter = create_box("Warehouse_DoorCutter", (5.0, t + 0.8, 4.5), (0.0, -d / 2 + t / 2, 2.25))
    apply_boolean_cut(front, cutter)

    # two sliding door panels parked open beside the opening, slightly proud
    # of the facade (metal tracks would be level with the panel tops)
    for sx in (-1.0, 1.0):
        parts.append(create_box(
            f"Warehouse_SlideDoor_{int(sx > 0)}",
            (2.7, 0.12, 4.4), (sx * 4.3, -d / 2 - 0.21, 2.3)))

    for p in parts:
        smart_unwrap(p, MATERIALS["metal"]["uv_scale"])
    mat = make_material("Warehouse_Metal", "metal")
    for p in parts:
        assign_material(p, mat)

    warehouse = join_objects(parts, "Warehouse")
    set_origin_bottom_center(warehouse)
    return warehouse


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
BUILD_TASKS = [
    ("garage.glb", build_garage),
    ("sniper_tower.glb", build_sniper_tower),
    ("house_small.glb", build_house_small),
    ("warehouse.glb", build_warehouse),
]


def main() -> int:
    print(f"Blender (bpy) version: {bpy.app.version_string}")
    for filename, builder in BUILD_TASKS:
        print(f"Building {filename} ...")
        clear_scene()
        set_metric_units()
        obj = builder()
        x0, x1, y0, y1, z0, z1 = object_bbox(obj)
        print(
            f"  {obj.name}: {x1 - x0:.2f}m x {y1 - y0:.2f}m x {z1 - z0:.2f}m | "
            f"origin=({obj.location.x:.3f}, {obj.location.y:.3f}, {obj.location.z:.3f}) | "
            f"bbox bottom-centre=({(x0 + x1) / 2:.3f}, {(y0 + y1) / 2:.3f}, {z0:.3f})"
        )
        path = export_glb(filename)
        verify_glb(path)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
