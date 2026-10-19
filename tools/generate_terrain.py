#!/usr/bin/env python3
"""Phase 2 — Terrain asset generator for Indus : Battle Royale.

Generates low-poly terrain meshes for 4GB RAM devices, 1K textures,
and origin at bottom-center (0, 0, 0).

Assets:
  terrain_ground.glb       — 1000x1000m flat plane (grass_1k.png)
  terrain_hill_large.glb   — 40m tall, 80m wide jagged mountain (rock_stone_1k.png on steep parts, grass_1k.png on top)
  terrain_plateau.glb      — 200m wide, 15m tall flat elevated plateau with sloped ramps on 4 sides (grass_1k.png)
  terrain_valley.glb       — V-shaped depression/cutout in a terrain block (depth 15m) with steep sides (grass_1k.png + rock_stone_1k.png)

Usage:
  pip install bpy pillow numpy
  python tools/generate_terrain.py
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
TERRAIN_DIR = os.path.join(REPO_ROOT, "docs", "models", "terrain")

MAP_SCALE = 0.3

MATERIALS = {
    "grass": {"file": "grass_1k.png", "fallback": "grass.png", "roughness": 0.95, "metallic": 0.0, "tile": 4.0},
    "rock": {"file": "rock_stone_1k.png", "roughness": 0.90, "metallic": 0.0, "tile": 2.5},
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


def ensure_grass_1k() -> None:
    from PIL import Image

    dst = os.path.join(TEXTURE_DIR, "grass_1k.png")
    if os.path.isfile(dst):
        return
    src = os.path.join(TEXTURE_DIR, "grass.png")
    if os.path.isfile(src):
        img = Image.open(src).convert("RGB")
        if img.size != (1024, 1024):
            img = img.resize((1024, 1024), Image.LANCZOS)
        img.save(dst, "PNG")
        print("  created grass_1k.png (1024x1024)")
        return

    size = 1024
    patches = _fft_noise(size, 0.012, seed=11)
    clumps = _fft_noise(size, 0.05, seed=12)
    blades = _fft_noise(size, 0.25, seed=13)
    fine = _fft_noise(size, 0.9, seed=14)
    g = (0.5 * patches + 0.32 * clumps + 0.30 * blades + 0.16 * fine) / 1.05
    t = np.clip(0.5 + 0.30 * g, 0.0, 1.0)
    col = _lerp_rgb((0.10, 0.20, 0.07), (0.24, 0.42, 0.14), t)
    dry_t = np.clip(0.5 + 0.5 * patches, 0.0, 1.0)
    dry_strength = np.clip(0.5 + 0.42 * patches - 0.32, 0.0, 1.0) ** 2
    dry_col = _lerp_rgb((0.40, 0.43, 0.18), (0.52, 0.47, 0.22), dry_t)
    col = col * (1.0 - dry_strength[..., None]) + dry_col * dry_strength[..., None]
    col = np.clip(col + 0.05 * fine[..., None], 0.0, 1.0)
    Image.fromarray((col * 255).astype(np.uint8), "RGB").save(dst, "PNG")
    print("  generated grass_1k.png (1024x1024)")


def ensure_rock_stone_1k() -> None:
    from PIL import Image

    dst = os.path.join(TEXTURE_DIR, "rock_stone_1k.png")
    if os.path.isfile(dst):
        return
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
    Image.fromarray((col * 255).astype(np.uint8), "RGB").save(dst, "PNG")
    print("  generated rock_stone_1k.png (1024x1024)")


def ensure_textures() -> None:
    os.makedirs(TEXTURE_DIR, exist_ok=True)
    ensure_grass_1k()
    ensure_rock_stone_1k()
    for src_name, dst_name in [
        ("wood_plank.png", "wood_plank_1k.png"),
        ("concrete_wall.png", "concrete_wall_1k.png"),
    ]:
        dst = os.path.join(TEXTURE_DIR, dst_name)
        if not os.path.isfile(dst):
            src = os.path.join(TEXTURE_DIR, src_name)
            if os.path.isfile(src):
                shutil.copy(src, dst)


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
            current = math.sqrt(area_uv / area3d)
            k = target_density / current
            for layer in obj.data.uv_layers:
                for loop_uv in layer.data:
                    loop_uv.uv = loop_uv.uv * k


def density_for(preset: str) -> float | None:
    tile = MATERIALS[preset]["tile"]
    if not tile:
        return None
    return 1.0 / (MAP_SCALE * tile)


def make_material(name: str, preset: str):
    cache_key = f"{name}:{preset}"
    if cache_key in _MATERIAL_CACHE:
        return _MATERIAL_CACHE[cache_key]
    spec = MATERIALS[preset]
    mat = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError("Principled BSDF not found")

    tex_path = os.path.join(TEXTURE_DIR, spec["file"])
    if not os.path.isfile(tex_path):
        fallback = spec.get("fallback")
        if fallback:
            tex_path = os.path.join(TEXTURE_DIR, fallback)
        if not os.path.isfile(tex_path):
            raise FileNotFoundError(f"Texture not found: {tex_path}")
    image = bpy.data.images.load(tex_path, check_existing=True)

    coord = nt.nodes.new("ShaderNodeTexCoord")
    coord.location = (-760, 220)
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.location = (-560, 220)
    mapping.inputs["Scale"].default_value = (MAP_SCALE, MAP_SCALE, MAP_SCALE)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.location = (-350, 220)
    tex.image = image
    tex.extension = "REPEAT"
    tex.label = spec["file"]

    nt.links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

    bsdf.inputs["Roughness"].default_value = spec["roughness"]
    bsdf.inputs["Metallic"].default_value = spec["metallic"]
    _MATERIAL_CACHE[cache_key] = mat
    return mat


def assign_material(obj, mat) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def set_origin_bottom_center(obj) -> None:
    coords = [obj.matrix_world @ v.co for v in obj.data.vertices]
    min_x = min(c.x for c in coords)
    max_x = max(c.x for c in coords)
    min_y = min(c.y for c in coords)
    max_y = max(c.y for c in coords)
    min_z = min(c.z for c in coords)
    offset = Vector((-(min_x + max_x) / 2.0, -(min_y + max_y) / 2.0, -min_z))
    obj.data.transform(Matrix.Translation(offset))
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
        raise RuntimeError(f"Export failed: {path}")
    return path


def verify_glb(path: str) -> dict:
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"glTF":
        raise RuntimeError(f"Not GLB: {path}")
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_len])
    images = gltf.get("images", [])
    if not images:
        raise RuntimeError(f"No packed images in {path}")
    for img in images:
        if "bufferView" not in img and "uri" not in img:
            raise RuntimeError(f"Image not embedded in {path}: {img}")
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
def build_terrain_ground():
    """1. terrain_ground.glb: A massive 1000x1000m flat plane (for the base ground)."""
    bpy.ops.mesh.primitive_plane_add(size=1000.0, location=(0.0, 0.0, 0.0))
    ground = bpy.context.active_object
    ground.name = "TerrainGround"
    ground.data.name = "TerrainGroundMesh"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    smart_unwrap(ground, density_for("grass"))
    assign_material(ground, make_material("TerrainGround_Grass", "grass"))
    set_origin_bottom_center(ground)
    return ground


def build_terrain_hill_large():
    """2. terrain_hill_large.glb: A displaced icosphere or cone, 40m tall, 80m wide,
    looking like a jagged mountain. Apply rock_stone_1k.png to the steep parts
    and grass to the top."""
    rng = random.Random(42)
    # Build a multi-ring low-poly mountain cone/dome so we have steep rocky cliffs
    # and a grassy upper crown/top.
    n_angles = 16
    # Rings from bottom (r=40, z=0) up to summit plateau and peak (z=40)
    ring_specs = [
        (40.0, 0.0, 0.0),    # base ring (grounded at z=0)
        (33.0, 10.0, 2.8),   # lower cliff
        (24.0, 21.0, 3.2),   # mid rocky ridge
        (15.0, 31.0, 2.5),   # upper rocky shoulder
        (7.5,  37.0, 1.2),   # grassy crown rim
    ]
    verts = []
    for ring_idx, (rad, z_base, jitter) in enumerate(ring_specs):
        for k in range(n_angles):
            ang = (2.0 * math.pi * k) / n_angles + (0.12 if ring_idx % 2 else 0.0)
            r_var = rad + (rng.uniform(-jitter, jitter) if ring_idx > 0 else rng.uniform(-1.2, 1.2))
            z_var = z_base + (rng.uniform(-jitter * 0.6, jitter * 0.6) if ring_idx > 0 else 0.0)
            verts.append((r_var * math.cos(ang), r_var * math.sin(ang), z_var))

    # Summit vertex at index len(verts)
    summit_idx = len(verts)
    verts.append((0.0, 0.0, 40.0))
    # Base center vertex for closed bottom
    base_center_idx = len(verts)
    verts.append((0.0, 0.0, 0.0))

    faces = []
    face_is_grass = []

    # Side quads between consecutive rings
    for r in range(len(ring_specs) - 1):
        b0 = r * n_angles
        b1 = (r + 1) * n_angles
        for k in range(n_angles):
            kn = (k + 1) % n_angles
            faces.append((b0 + k, b0 + kn, b1 + kn, b1 + k))
            # Top ring band (r == 3) + summit cap get grass; steeper lower rings get rock
            face_is_grass.append(r >= 3)

    # Summit cap triangles (grass)
    top_ring_base = (len(ring_specs) - 1) * n_angles
    for k in range(n_angles):
        kn = (k + 1) % n_angles
        faces.append((top_ring_base + k, top_ring_base + kn, summit_idx))
        face_is_grass.append(True)

    # Bottom cap triangles (rock)
    for k in range(n_angles):
        kn = (k + 1) % n_angles
        faces.append((kn, k, base_center_idx))
        face_is_grass.append(False)

    mesh = bpy.data.meshes.new("TerrainHillLargeMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new("TerrainHillLarge", mesh)
    bpy.context.collection.objects.link(obj)

    # Normalize exact dimensions to 80m x 80m x 40m
    set_origin_bottom_center(obj)
    x0, x1, y0, y1, z0, z1 = object_bbox(obj)
    obj.data.transform(Matrix.Diagonal((80.0 / (x1 - x0), 80.0 / (y1 - y0), 40.0 / (z1 - z0), 1.0)))
    obj.data.update()
    set_origin_bottom_center(obj)

    smart_unwrap(obj, density_for("rock"))

    mat_rock = make_material("Hill_Rock", "rock")
    mat_grass = make_material("Hill_Grass", "grass")
    obj.data.materials.clear()
    obj.data.materials.append(mat_rock)   # slot 0
    obj.data.materials.append(mat_grass)  # slot 1

    for poly, is_grass in zip(obj.data.polygons, face_is_grass):
        poly.material_index = 1 if is_grass else 0

    set_origin_bottom_center(obj)
    return obj


def build_terrain_plateau():
    """3. terrain_plateau.glb: A large elevated flat area (200m wide, 15m tall)
    with sloped ramps on 4 sides so players can walk up."""
    # Total width = 200m (-100..100). Elevated flat top = 120m x 120m (-60..60) at z=15m.
    # On all 4 sides (+Y, -Y, +X, -X), sloped walk-up ramps extend from the 60m inner edge
    # out to the 100m outer edge (40m ramp run, 15m rise -> walkable ~20.5 deg slope),
    # while the corner bastions form steeper angled embankments.
    outer = 100.0
    inner = 60.0
    ramp_half = 30.0
    h = 15.0

    # Build a clean 5x5 grid of (x, y, z) vertices over [-100, -60, -30, 30, 60, 100]
    coords_1d = [-outer, -inner, -ramp_half, ramp_half, inner, outer]
    n = len(coords_1d)
    verts = []
    for y in coords_1d:
        for x in coords_1d:
            ax, ay = abs(x), abs(y)
            if ax <= inner and ay <= inner:
                z = h
            else:
                z = 0.0
            verts.append((x, y, z))

    def idx(ix, iy):
        return iy * n + ix

    faces = []
    for iy in range(n - 1):
        for ix in range(n - 1):
            v00 = idx(ix, iy)
            v10 = idx(ix + 1, iy)
            v11 = idx(ix + 1, iy + 1)
            v01 = idx(ix, iy + 1)
            faces.append((v00, v10, v11, v01))

    # Bottom closure quad
    b0 = idx(0, 0)
    b1 = idx(n - 1, 0)
    b2 = idx(n - 1, n - 1)
    b3 = idx(0, n - 1)
    faces.append((b0, b3, b2, b1))

    mesh = bpy.data.meshes.new("TerrainPlateauMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new("TerrainPlateau", mesh)
    bpy.context.collection.objects.link(obj)

    smart_unwrap(obj, density_for("grass"))
    assign_material(obj, make_material("Plateau_Grass", "grass"))
    set_origin_bottom_center(obj)
    return obj


def build_terrain_valley():
    """4. terrain_valley.glb: A V-shaped depression/cutout in a terrain block
    (depth 15m) with steep sides."""
    # Terrain block: 200m x 200m x 15m tall, with a V-shaped valley cutout running
    # along the X axis (top banks at z=15m for |y| >= 25m, steep V-sides sloping down
    # to z=0m at y=0m). Closed front/back/side/bottom faces so it is a solid 3D block.
    half_x = 100.0
    ys = [-100.0, -25.0, 0.0, 25.0, 100.0]
    zs_top = [15.0, 15.0, 0.0, 15.0, 15.0]

    verts = []
    # Top profile at x = -half_x (indices 0..4) and x = +half_x (indices 5..9)
    for x in (-half_x, half_x):
        for y, z in zip(ys, zs_top):
            verts.append((x, y, z))
    # Bottom corners of the terrain block at z = 0 (indices 10..13)
    verts.extend([
        (-half_x, -100.0, 0.0),  # 10
        (-half_x,  100.0, 0.0),  # 11
        ( half_x, -100.0, 0.0),  # 12
        ( half_x,  100.0, 0.0),  # 13
    ])

    # Top surface quads (4 quads along Y)
    faces = [
        (0, 5, 6, 1),  # left flat grass bank
        (1, 6, 7, 2),  # steep left V-slope (rock)
        (2, 7, 8, 3),  # steep right V-slope (rock)
        (3, 8, 9, 4),  # right flat grass bank
        # Outer side walls
        (0, 10, 12, 5),   # y = -100m side wall
        (4, 9, 13, 11),   # y = +100m side wall
        # Front/back end walls (left & right of the V cutout)
        (0, 1, 2, 10),    # x = -half_x, left half
        (2, 3, 4, 11),    # x = -half_x, right half
        (5, 12, 7, 6),    # x = +half_x, left half
        (7, 13, 9, 8),    # x = +half_x, right half
        # Bottom faces
        (10, 2, 7, 12),
        (2, 11, 13, 7),
    ]
    # Steep V-slope faces (indices 1 and 2) use rock; flat top banks & block exterior use grass
    steep_rock_faces = {1, 2}

    mesh = bpy.data.meshes.new("TerrainValleyMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new("TerrainValley", mesh)
    bpy.context.collection.objects.link(obj)

    smart_unwrap(obj, density_for("grass"))
    mat_grass = make_material("Valley_Grass", "grass")
    mat_rock = make_material("Valley_Rock", "rock")
    obj.data.materials.clear()
    obj.data.materials.append(mat_grass)  # slot 0
    obj.data.materials.append(mat_rock)   # slot 1
    for idx_f, poly in enumerate(obj.data.polygons):
        poly.material_index = 1 if idx_f in steep_rock_faces else 0

    set_origin_bottom_center(obj)
    return obj


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    print(f"Blender {bpy.app.version_string} — Phase 2 Terrain Generator")
    ensure_textures()
    os.makedirs(TERRAIN_DIR, exist_ok=True)
    failures = []

    def run(label: str, filename: str, builder):
        print(f"Building {label} ...")
        try:
            clear_scene()
            set_metric_units()
            obj = builder()
            report(obj, label)
            path = os.path.join(TERRAIN_DIR, filename)
            export_glb(path)
            verify_glb(path)
        except Exception as exc:
            failures.append((label, exc))
            print(f"  FAILED {label}: {exc!r}")

    run("terrain_ground.glb", "terrain_ground.glb", build_terrain_ground)
    run("terrain_hill_large.glb", "terrain_hill_large.glb", build_terrain_hill_large)
    run("terrain_plateau.glb", "terrain_plateau.glb", build_terrain_plateau)
    run("terrain_valley.glb", "terrain_valley.glb", build_terrain_valley)

    if failures:
        print(f"\n{len(failures)} task(s) failed:")
        for label, exc in failures:
            print(f"  - {label}: {exc!r}")
        return 1
    print("Done — Terrain assets generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
