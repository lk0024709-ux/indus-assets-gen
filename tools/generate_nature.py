#!/usr/bin/env python3
"""Phase 2 — Nature & Plants asset generator for Indus : Battle Royale.

Generates low-poly nature and plant meshes for 4GB RAM devices,
1K textures, and origin at bottom-center (0, 0, 0).

Assets:
  tree_pine.glb   — 8m tall. Cylinder trunk + 3 stacked cones (wood_plank_1k.png + grass_1k.png)
  tree_oak.glb    — 6m tall. Thick trunk + large low-poly green canopy (wood_plank_1k.png + grass_1k.png)
  tree_dead.glb   — Bare jagged branches (wood_plank_1k.png)
  rock_large.glb  — Displaced icosphere (3x3x2m) (rock_stone_1k.png)
  rock_small.glb  — Displaced icosphere (1x1x0.8m) (rock_stone_1k.png)
  bush.glb        — Cluster of 3 small green spheres (grass_1k.png)
  grass_clump.glb — 3 crossed planes with a green material (grass_1k.png)

Usage:
  pip install bpy pillow numpy
  python tools/generate_nature.py
"""

from __future__ import annotations

import json
import math
import os
import random
import shutil
import struct
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURE_DIR = os.path.join(REPO_ROOT, "docs", "textures")
NATURE_DIR = os.path.join(REPO_ROOT, "docs", "models", "nature")

MAP_SCALE = 0.3

MATERIALS = {
    "wood": {"file": "wood_plank_1k.png", "fallback": "wood_plank.png", "roughness": 0.78, "metallic": 0.0, "tile": 1.5},
    "grass": {"file": "grass_1k.png", "fallback": "grass.png", "roughness": 0.90, "metallic": 0.0, "tile": 2.0},
    "rock": {"file": "rock_stone_1k.png", "roughness": 0.90, "metallic": 0.0, "tile": 1.5},
}

_MATERIAL_CACHE: dict[str, object] = {}


# ---------------------------------------------------------------------------
# Procedural 1K texture helpers
# ---------------------------------------------------------------------------
def _fft_noise(size: int, cutoff: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    spectrum = np.fft.fft2(rng.normal(size=(size, size)))
    fy = np.fft.fftfreq(size)[:, None]
    fx = np.fft.fftfreq(size)[None, :]
    radius = np.sqrt(fx ** 2 + fy ** 2)
    spectrum *= np.exp(-((radius / cutoff) ** 2))
    field = np.real(np.fft.ifft2(spectrum))
    field -= field.mean()
    field /= field.std() + 1e-9
    return field


def _lerp_rgb(c0, c1, t):
    c0 = np.asarray(c0, dtype=np.float64)
    c1 = np.asarray(c1, dtype=np.float64)
    return c0[None, None, :] + (c1 - c0)[None, None, :] * t[..., None]


def ensure_textures() -> None:
    from PIL import Image

    os.makedirs(TEXTURE_DIR, exist_ok=True)
    for src, dst in [
        ("wood_plank.png", "wood_plank_1k.png"),
        ("concrete_wall.png", "concrete_wall_1k.png"),
        ("grass.png", "grass_1k.png"),
    ]:
        d = os.path.join(TEXTURE_DIR, dst)
        if not os.path.isfile(d):
            s = os.path.join(TEXTURE_DIR, src)
            if os.path.isfile(s):
                shutil.copy(s, d)
                print(f"  copied {src} -> {dst}")

    rock_dst = os.path.join(TEXTURE_DIR, "rock_stone_1k.png")
    if not os.path.isfile(rock_dst):
        size = 1024
        base_n = _fft_noise(size, 0.015, seed=31)
        detail_n = _fft_noise(size, 0.08, seed=32)
        crack_n = _fft_noise(size, 0.04, seed=33)
        fine = _fft_noise(size, 0.5, seed=34)
        t = np.clip(0.5 + 0.35 * base_n + 0.2 * detail_n, 0.0, 1.0)
        col = _lerp_rgb((0.35, 0.33, 0.30), (0.55, 0.52, 0.48), t)
        crack_mask = np.clip((np.clip(0.5 + 0.6 * crack_n, 0.0, 1.0) - 0.6) * 3.0, 0.0, 1.0)
        crack_col = _lerp_rgb((0.22, 0.21, 0.20), (0.18, 0.17, 0.16), np.clip(0.5 + 0.3 * detail_n, 0, 1))
        col = col * (1 - crack_mask[..., None] * 0.7) + crack_col * crack_mask[..., None] * 0.7
        col = np.clip(col + 0.06 * fine[..., None], 0.0, 1.0)
        Image.fromarray((col * 255).astype(np.uint8), "RGB").save(rock_dst, "PNG")
        print("  generated rock_stone_1k.png")


# ---------------------------------------------------------------------------
# Scene & material helpers
# ---------------------------------------------------------------------------
def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _MATERIAL_CACHE.clear()


def set_metric_units() -> None:
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0


def create_cylinder(name: str, radius: float, depth: float, location, vertices: int = 8, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cylinder_add(
        radius=radius,
        depth=depth,
        vertices=vertices,
        location=location,
        rotation=rotation,
    )
    o = bpy.context.active_object
    o.name = name
    o.data.name = name + "Mesh"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return o


def create_cone(name: str, radius1: float, radius2: float, depth: float, location, vertices: int = 8, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices,
        radius1=radius1,
        radius2=radius2,
        depth=depth,
        location=location,
        rotation=rotation,
    )
    o = bpy.context.active_object
    o.name = name
    o.data.name = name + "Mesh"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return o


def create_ico_sphere(name: str, subdivisions: int, radius: float, location):
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=subdivisions,
        radius=radius,
        location=location,
    )
    o = bpy.context.active_object
    o.name = name
    o.data.name = name + "Mesh"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return o


def smart_unwrap(obj, target_density: float | None = None) -> None:
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try:
        bpy.ops.mesh.normals_make_consistent(inside=False)
    except RuntimeError:
        pass
    try:
        bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.02)
    except TypeError:
        bpy.ops.uv.smart_project()
    bpy.ops.object.mode_set(mode="OBJECT")

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
            cx = sum(us) / len(us)
            cy = sum(vs) / len(vs)
            for i, u, v in zip(idxs, us, vs):
                x, y = u - cx, v - cy
                uvl.data[i].uv = (cx - y, cy + x)

    if target_density:
        area3d = sum(p.area for p in me.polygons)
        area_uv = 0.0
        for p in me.polygons:
            pts = [uvl.data[i].uv for i in p.loop_indices]
            if len(pts) < 3:
                continue
            s = 0.0
            for a in range(len(pts)):
                b = (a + 1) % len(pts)
                s += pts[a].x * pts[b].y - pts[b].x * pts[a].y
            area_uv += abs(s) / 2.0
        if area3d > 1e-9 and area_uv > 1e-9:
            cur = math.sqrt(area_uv / area3d)
            k = target_density / cur
            for layer in obj.data.uv_layers:
                for uv in layer.data:
                    uv.uv = uv.uv * k


def density_for(preset: str) -> float | None:
    tile = MATERIALS[preset]["tile"]
    if not tile:
        return None
    return 1.0 / (MAP_SCALE * tile)


def make_material(name: str, preset: str, double_sided: bool = False):
    key = f"{name}:{preset}:{double_sided}"
    if key in _MATERIAL_CACHE:
        return _MATERIAL_CACHE[key]
    spec = MATERIALS[preset]
    mat = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    if double_sided:
        mat.use_backface_culling = False

    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError("Principled BSDF not found")

    tex_path = os.path.join(TEXTURE_DIR, spec["file"])
    if not os.path.isfile(tex_path):
        fb = spec.get("fallback")
        if fb:
            tex_path = os.path.join(TEXTURE_DIR, fb)
        if not os.path.isfile(tex_path):
            raise FileNotFoundError(f"Texture missing: {tex_path}")
    img = bpy.data.images.load(tex_path, check_existing=True)

    coord = nt.nodes.new("ShaderNodeTexCoord")
    coord.location = (-760, 220)
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.location = (-560, 220)
    mapping.inputs["Scale"].default_value = (MAP_SCALE, MAP_SCALE, MAP_SCALE)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.location = (-350, 220)
    tex.image = img
    tex.extension = "REPEAT"
    tex.label = spec["file"]

    nt.links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

    bsdf.inputs["Roughness"].default_value = spec["roughness"]
    bsdf.inputs["Metallic"].default_value = spec["metallic"]
    _MATERIAL_CACHE[key] = mat
    return mat


def assign_material(obj, mat) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def join_objects(objs, name: str):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs:
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    j = bpy.context.active_object
    j.name = name
    j.data.name = name + "Mesh"
    return j


def set_origin_bottom_center(obj) -> None:
    coords = [obj.matrix_world @ v.co for v in obj.data.vertices]
    min_x = min(c.x for c in coords)
    max_x = max(c.x for c in coords)
    min_y = min(c.y for c in coords)
    max_y = max(c.y for c in coords)
    min_z = min(c.z for c in coords)
    off = Vector((-(min_x + max_x) / 2.0, -(min_y + max_y) / 2.0, -min_z))
    obj.data.transform(Matrix.Translation(off))
    obj.data.validate(clean_customdata=True)
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


def export_glb(path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    kwargs = dict(
        filepath=path,
        export_format="GLB",
        export_image_format="JPEG",
        export_lights=False,
    )
    try:
        bpy.ops.export_scene.gltf(export_image_quality=90, **kwargs)
    except TypeError:
        bpy.ops.export_scene.gltf(**kwargs)
    if not os.path.isfile(path):
        raise RuntimeError(f"Export failed {path}")
    return path


def verify_glb(path: str) -> dict:
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"glTF":
        raise RuntimeError(f"Not GLB {path}")
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_len])
    images = gltf.get("images", [])
    if not images:
        raise RuntimeError(f"No packed images in {path}")
    tris = 0
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if "indices" in prim:
                count = gltf["accessors"][prim["indices"]]["count"]
            else:
                count = gltf["accessors"][prim["attributes"]["POSITION"]]["count"]
            tris += count // 3
    stats = {
        "bytes": os.path.getsize(path),
        "materials": len(gltf.get("materials", [])),
        "images": len(images),
        "tris": tris,
    }
    print(
        f"  verified {os.path.basename(path)}: {stats['bytes']} bytes, "
        f"{stats['materials']} mat, {stats['images']} img, ~{stats['tris']} tris"
    )
    return stats


def report(obj, label: str) -> None:
    x0, x1, y0, y1, z0, z1 = object_bbox(obj)
    print(
        f"  {label}: {x1 - x0:.2f}m x {y1 - y0:.2f}m x {z1 - z0:.2f}m | "
        f"{len(obj.data.polygons)} faces | origin=({obj.location.x:.2f}, "
        f"{obj.location.y:.2f}, {obj.location.z:.2f})"
    )


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------
def build_tree_pine():
    """1. tree_pine.glb: 8m tall. Cylinder trunk + 3 stacked cones."""
    parts = []
    # Trunk: 0.26m radius, 2.8m tall (base at z=0.0, top at z=2.8)
    trunk = create_cylinder("PineTrunk", radius=0.26, depth=2.8, location=(0.0, 0.0, 1.4), vertices=8)
    parts.append((trunk, "wood"))

    # 3 stacked low-poly cones reaching exactly z = 8.0m
    cone_specs = [
        (1.85, 2.6, 2.0),  # bottom cone: z = 2.0 .. 4.6
        (1.40, 2.3, 3.8),  # middle cone: z = 3.8 .. 6.1
        (0.95, 2.5, 5.5),  # top cone:    z = 5.5 .. 8.0
    ]
    for i, (rad, h, base_z) in enumerate(cone_specs):
        cone = create_cone(
            f"PineCone{i}",
            radius1=rad,
            radius2=0.0,
            depth=h,
            location=(0.0, 0.0, base_z + h / 2.0),
            vertices=8,
        )
        parts.append((cone, "grass"))

    mats = {}
    for obj, kind in parts:
        if kind not in mats:
            mats[kind] = make_material(f"Pine_{kind}", kind)
        smart_unwrap(obj, density_for(kind))
        assign_material(obj, mats[kind])

    joined = join_objects([o for o, _ in parts], "TreePine")
    set_origin_bottom_center(joined)
    return joined


def build_tree_oak():
    """2. tree_oak.glb: 6m tall. Thick trunk + large low-poly green canopy."""
    rng = random.Random(77)
    parts = []
    # Thick trunk: 0.42m radius, 3.2m tall
    trunk = create_cone("OakTrunk", radius1=0.48, radius2=0.32, depth=3.2, location=(0.0, 0.0, 1.6), vertices=8)
    parts.append((trunk, "wood"))

    # Large low-poly green canopy: main icosphere + 2 secondary lobes reaching z = 6.0m
    canopy_main = create_ico_sphere("OakCanopyMain", subdivisions=1, radius=1.9, location=(0.0, 0.0, 4.1))
    canopy_lobe1 = create_ico_sphere("OakCanopyLobe1", subdivisions=1, radius=1.25, location=(0.85, 0.35, 3.9))
    canopy_lobe2 = create_ico_sphere("OakCanopyLobe2", subdivisions=1, radius=1.20, location=(-0.75, -0.45, 4.0))
    for c in (canopy_main, canopy_lobe1, canopy_lobe2):
        for v in c.data.vertices:
            v.co += Vector((rng.uniform(-0.08, 0.08), rng.uniform(-0.08, 0.08), rng.uniform(-0.06, 0.06)))
        c.data.update()
        parts.append((c, "grass"))

    mats = {}
    for obj, kind in parts:
        if kind not in mats:
            mats[kind] = make_material(f"Oak_{kind}", kind)
        smart_unwrap(obj, density_for(kind))
        assign_material(obj, mats[kind])

    joined = join_objects([o for o, _ in parts], "TreeOak")
    set_origin_bottom_center(joined)
    x0, x1, y0, y1, z0, z1 = object_bbox(joined)
    scale_to_exact_size(joined, (x1 - x0, y1 - y0, 6.0))
    return joined


def _make_tapered_limb(name: str, p_start: Vector, p_end: Vector, r_start: float, r_end: float, sides: int = 6):
    """Create a low-poly tapered limb segment directly between two 3D points."""
    axis = p_end - p_start
    length = axis.length
    direction = axis.normalized()
    # Orthonormal basis around direction
    ref = Vector((1.0, 0.0, 0.0)) if abs(direction.x) < 0.8 else Vector((0.0, 1.0, 0.0))
    u = direction.cross(ref).normalized()
    v = direction.cross(u).normalized()

    verts = []
    for k in range(sides):
        ang = (2.0 * math.pi * k) / sides
        offset = u * math.cos(ang) + v * math.sin(ang)
        verts.append(tuple(p_start + offset * r_start))
    for k in range(sides):
        ang = (2.0 * math.pi * k) / sides
        offset = u * math.cos(ang) + v * math.sin(ang)
        verts.append(tuple(p_end + offset * r_end))

    # End cap centers
    idx_start_cap = len(verts)
    verts.append(tuple(p_start))
    idx_end_cap = len(verts)
    verts.append(tuple(p_end))

    faces = []
    for k in range(sides):
        kn = (k + 1) % sides
        faces.append((k, kn, sides + kn, sides + k))
        faces.append((kn, k, idx_start_cap))
        faces.append((sides + k, sides + kn, idx_end_cap))

    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def build_tree_dead():
    """3. tree_dead.glb: Bare jagged branches."""
    # Build connected trunk and jagged forked branches using _make_tapered_limb
    limbs = [
        # Main gnarly trunk segments
        (Vector((0.0, 0.0, 0.0)), Vector((0.08, -0.05, 2.2)), 0.36, 0.26, 7),
        (Vector((0.08, -0.05, 2.2)), Vector((-0.05, 0.06, 4.1)), 0.26, 0.16, 7),
        (Vector((-0.05, 0.06, 4.1)), Vector((0.15, 0.12, 5.5)), 0.16, 0.05, 6),
        # Primary jagged branches
        (Vector((0.05, -0.02, 2.0)), Vector((1.25, 0.45, 3.4)), 0.18, 0.08, 6),
        (Vector((1.25, 0.45, 3.4)), Vector((1.85, 0.80, 4.5)), 0.08, 0.03, 5),
        (Vector((1.25, 0.45, 3.4)), Vector((1.65, -0.10, 4.0)), 0.06, 0.02, 5),
        (Vector((0.0, 0.02, 2.6)), Vector((-1.20, 0.55, 3.9)), 0.16, 0.07, 6),
        (Vector((-1.20, 0.55, 3.9)), Vector((-1.75, 0.90, 4.9)), 0.07, 0.025, 5),
        (Vector((-0.02, 0.04, 3.2)), Vector((0.35, -1.15, 4.4)), 0.14, 0.06, 6),
        (Vector((0.35, -1.15, 4.4)), Vector((0.60, -1.65, 5.2)), 0.06, 0.02, 5),
        (Vector((-0.04, 0.05, 3.7)), Vector((-0.75, -0.85, 4.8)), 0.12, 0.04, 5),
    ]
    objs = []
    mat_wood = make_material("TreeDead_Wood", "wood")
    for i, (p0, p1, r0, r1, sides) in enumerate(limbs):
        limb = _make_tapered_limb(f"DeadLimb{i}", p0, p1, r0, r1, sides=sides)
        smart_unwrap(limb, density_for("wood"))
        assign_material(limb, mat_wood)
        objs.append(limb)

    joined = join_objects(objs, "TreeDead")
    set_origin_bottom_center(joined)
    return joined


def scale_to_exact_size(obj, target_size) -> None:
    set_origin_bottom_center(obj)
    x0, x1, y0, y1, z0, z1 = object_bbox(obj)
    sx = target_size[0] / max(x1 - x0, 1e-6)
    sy = target_size[1] / max(y1 - y0, 1e-6)
    sz = target_size[2] / max(z1 - z0, 1e-6)
    obj.data.transform(Matrix.Diagonal((sx, sy, sz, 1.0)))
    obj.data.update()
    set_origin_bottom_center(obj)


def build_rock_large():
    """4. rock_large.glb: Displaced icosphere (3x3x2m)."""
    rng = random.Random(123)
    obj = create_ico_sphere("RockLarge", subdivisions=2, radius=1.5, location=(0.0, 0.0, 1.0))
    for v in obj.data.vertices:
        n = v.co.normalized()
        disp = Vector((
            rng.uniform(-0.28, 0.28),
            rng.uniform(-0.28, 0.28),
            rng.uniform(-0.22, 0.22),
        ))
        v.co += disp + n * rng.uniform(-0.15, 0.18)
    obj.data.update()

    scale_to_exact_size(obj, (3.0, 3.0, 2.0))
    smart_unwrap(obj, density_for("rock"))
    assign_material(obj, make_material("RockLarge_Rock", "rock"))
    set_origin_bottom_center(obj)
    return obj


def build_rock_small():
    """5. rock_small.glb: Displaced icosphere (1x1x0.8m)."""
    rng = random.Random(456)
    obj = create_ico_sphere("RockSmall", subdivisions=1, radius=0.5, location=(0.0, 0.0, 0.4))
    for v in obj.data.vertices:
        v.co += Vector((
            rng.uniform(-0.12, 0.12),
            rng.uniform(-0.12, 0.12),
            rng.uniform(-0.09, 0.09),
        ))
    obj.data.update()

    scale_to_exact_size(obj, (1.0, 1.0, 0.8))
    smart_unwrap(obj, density_for("rock"))
    assign_material(obj, make_material("RockSmall_Rock", "rock"))
    set_origin_bottom_center(obj)
    return obj


def build_bush():
    """6. bush.glb: Cluster of 3 small green spheres."""
    rng = random.Random(789)
    parts = []
    specs = [
        ((0.0, 0.0, 0.55), 0.62),
        ((0.52, 0.22, 0.46), 0.50),
        ((-0.48, 0.30, 0.50), 0.54),
    ]
    mat_grass = make_material("Bush_Grass", "grass")
    for i, (center, rad) in enumerate(specs):
        sphere = create_ico_sphere(f"BushSphere{i}", subdivisions=1, radius=rad, location=center)
        for v in sphere.data.vertices:
            v.co += Vector((rng.uniform(-0.04, 0.04), rng.uniform(-0.04, 0.04), rng.uniform(-0.03, 0.03)))
        sphere.data.update()
        smart_unwrap(sphere, density_for("grass"))
        assign_material(sphere, mat_grass)
        parts.append(sphere)

    joined = join_objects(parts, "Bush")
    set_origin_bottom_center(joined)
    return joined


def build_grass_clump():
    """7. grass_clump.glb: 3 crossed planes with a green material."""
    parts = []
    mat_grass = make_material("GrassClump_Grass", "grass", double_sided=True)

    def create_crossed_plane(name: str, angle_deg: float):
        w = 0.85
        h = 0.90
        ang = math.radians(angle_deg)
        ca, sa = math.cos(ang), math.sin(ang)
        # Taper slightly toward the top like a grass blade cluster, double-sided faces
        pts = [
            (-w / 2.0, 0.0, 0.0),
            ( w / 2.0, 0.0, 0.0),
            ( w * 0.42, 0.0, h),
            (-w * 0.42, 0.0, h),
        ]
        verts = []
        for x, y, z in pts:
            verts.append((x * ca - y * sa, x * sa + y * ca, z))
        # Front and back quad so lighting and visibility work from both sides
        faces = [(0, 1, 2, 3), (0, 3, 2, 1)]
        mesh = bpy.data.meshes.new(name + "Mesh")
        mesh.from_pydata(verts, [], faces)
        mesh.validate()
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        return obj

    for i, ang in enumerate((0.0, 60.0, 120.0)):
        p = create_crossed_plane(f"GrassPlane{i}", ang)
        smart_unwrap(p, density_for("grass"))
        assign_material(p, mat_grass)
        parts.append(p)

    joined = join_objects(parts, "GrassClump")
    set_origin_bottom_center(joined)
    return joined


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    print(f"Blender {bpy.app.version_string} — Phase 2 Nature & Plants Generator")
    ensure_textures()
    os.makedirs(NATURE_DIR, exist_ok=True)
    failures = []

    def run(label: str, filename: str, builder):
        print(f"Building {label} ...")
        try:
            clear_scene()
            set_metric_units()
            obj = builder()
            report(obj, label)
            path = os.path.join(NATURE_DIR, filename)
            export_glb(path)
            verify_glb(path)
        except Exception as exc:
            failures.append((label, exc))
            print(f"  FAILED {label}: {exc!r}")

    run("tree_pine.glb", "tree_pine.glb", build_tree_pine)
    run("tree_oak.glb", "tree_oak.glb", build_tree_oak)
    run("tree_dead.glb", "tree_dead.glb", build_tree_dead)
    run("rock_large.glb", "rock_large.glb", build_rock_large)
    run("rock_small.glb", "rock_small.glb", build_rock_small)
    run("bush.glb", "bush.glb", build_bush)
    run("grass_clump.glb", "grass_clump.glb", build_grass_clump)

    if failures:
        print(f"\n{len(failures)} task(s) failed:")
        for label, exc in failures:
            print(f"  - {label}: {exc!r}")
        return 1
    print("Done — Nature & Plants assets generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
