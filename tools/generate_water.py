#!/usr/bin/env python3
"""Phase 2 — Water & Beach asset generator for Indus : Battle Royale.

Generates low-poly water, beach, and dam meshes for 4GB RAM devices,
1K textures, and origin at bottom-center (0, 0, 0).

Assets:
  water_ocean.glb   — 4000x4000m flat plane with semi-transparent blue material (alpha = 0.6)
  water_river.glb   — Long, curved river mesh (width 30m) with semi-transparent water (alpha = 0.6)
  beach_sand.glb    — 50m wide sand-colored ring/plane at island edge (sand_1k.png)
  dam_concrete.glb  — Massive concrete wall (50m wide, 20m tall, 5m thick) with curved front face (concrete_wall_1k.png)

Usage:
  pip install bpy pillow numpy
  python tools/generate_water.py
"""

from __future__ import annotations

import json
import math
import os
import shutil
import struct
import sys

import bpy
import numpy as np
from mathutils import Matrix, Vector

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURE_DIR = os.path.join(REPO_ROOT, "docs", "textures")
WATER_DIR = os.path.join(REPO_ROOT, "docs", "models", "water")

MAP_SCALE = 0.3

MATERIALS = {
    "water": {"file": "water_1k.png", "roughness": 0.22, "metallic": 0.0, "tile": 20.0, "alpha": 0.6},
    "sand": {"file": "sand_1k.png", "roughness": 0.90, "metallic": 0.0, "tile": 4.0},
    "concrete": {"file": "concrete_wall_1k.png", "fallback": "concrete_wall.png", "roughness": 0.88, "metallic": 0.0, "tile": 2.5},
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


def ensure_water_1k() -> None:
    from PIL import Image

    dst = os.path.join(TEXTURE_DIR, "water_1k.png")
    if os.path.isfile(dst):
        return
    size = 1024
    swell = _fft_noise(size, 0.018, seed=61)
    ripples = _fft_noise(size, 0.075, seed=62)
    shimmer = _fft_noise(size, 0.22, seed=63)
    t = np.clip(0.5 + 0.30 * swell + 0.22 * ripples + 0.10 * shimmer, 0.0, 1.0)
    col = _lerp_rgb((0.06, 0.34, 0.64), (0.18, 0.60, 0.88), t)
    crest = np.clip((t - 0.72) * 3.2, 0.0, 1.0) ** 2
    col = col * (1.0 - crest[..., None] * 0.35) + np.array([0.55, 0.82, 0.96])[None, None, :] * (crest[..., None] * 0.35)
    col = np.clip(col, 0.0, 1.0)
    Image.fromarray((col * 255).astype(np.uint8), "RGB").save(dst, "PNG")
    print("  generated water_1k.png (1024x1024)")


def ensure_sand_1k() -> None:
    from PIL import Image

    dst = os.path.join(TEXTURE_DIR, "sand_1k.png")
    if os.path.isfile(dst):
        return
    size = 1024
    dunes = _fft_noise(size, 0.015, seed=51)
    ripples = _fft_noise(size, 0.08, seed=52)
    grains = _fft_noise(size, 0.45, seed=53)
    t = np.clip(0.5 + 0.30 * dunes + 0.20 * ripples, 0.0, 1.0)
    col = _lerp_rgb((0.76, 0.65, 0.44), (0.92, 0.83, 0.60), t)
    col = np.clip(col + 0.04 * grains[..., None], 0.0, 1.0)
    Image.fromarray((col * 255).astype(np.uint8), "RGB").save(dst, "PNG")
    print("  generated sand_1k.png (1024x1024)")


def ensure_concrete_1k() -> None:
    dst = os.path.join(TEXTURE_DIR, "concrete_wall_1k.png")
    if os.path.isfile(dst):
        return
    src = os.path.join(TEXTURE_DIR, "concrete_wall.png")
    if os.path.isfile(src):
        shutil.copy(src, dst)
        print("  copied concrete_wall.png -> concrete_wall_1k.png")


def ensure_textures() -> None:
    os.makedirs(TEXTURE_DIR, exist_ok=True)
    ensure_water_1k()
    ensure_sand_1k()
    ensure_concrete_1k()


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
        fb = spec.get("fallback")
        if fb:
            tex_path = os.path.join(TEXTURE_DIR, fb)
        if not os.path.isfile(tex_path):
            raise FileNotFoundError(f"Texture missing: {tex_path}")
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

    alpha = spec.get("alpha")
    if alpha is not None and alpha < 1.0:
        if hasattr(mat, "surface_render_method"):
            mat.surface_render_method = "BLENDED"
        elif hasattr(mat, "blend_method"):
            mat.blend_method = "BLEND"
        if "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = alpha

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
def build_water_ocean():
    """1. water_ocean.glb: A massive flat plane (4000x4000m) with a semi-transparent
    blue material (alpha = 0.6)."""
    bpy.ops.mesh.primitive_plane_add(size=4000.0, location=(0.0, 0.0, 0.0))
    obj = bpy.context.active_object
    obj.name = "WaterOcean"
    obj.data.name = "WaterOceanMesh"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    smart_unwrap(obj, density_for("water"))
    assign_material(obj, make_material("WaterOcean_Mat", "water"))
    set_origin_bottom_center(obj)
    return obj


def build_water_river():
    """2. water_river.glb: A long, curved river mesh (width 30m) with semi-transparent water."""
    length = 400.0
    width = 30.0
    segments = 24
    verts = []
    faces = []
    for i in range(segments + 1):
        u = i / segments
        x = -length / 2.0 + length * u
        # Smooth S-curve along X with tangent-perpendicular 30m width
        y_center = 38.0 * math.sin(2.0 * math.pi * u)
        dy_dx = (38.0 * (2.0 * math.pi / length)) * math.cos(2.0 * math.pi * u)
        tx, ty = 1.0, dy_dx
        t_len = math.hypot(tx, ty)
        nx, ny = -ty / t_len, tx / t_len
        half_w = width / 2.0
        verts.append((x - nx * half_w, y_center - ny * half_w, 0.0))
        verts.append((x + nx * half_w, y_center + ny * half_w, 0.0))

    for i in range(segments):
        a = i * 2
        b = i * 2 + 1
        c = (i + 1) * 2 + 1
        d = (i + 1) * 2
        faces.append((a, b, c, d))

    mesh = bpy.data.meshes.new("WaterRiverMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new("WaterRiver", mesh)
    bpy.context.collection.objects.link(obj)

    smart_unwrap(obj, density_for("water"))
    assign_material(obj, make_material("WaterRiver_Mat", "water"))
    set_origin_bottom_center(obj)
    return obj


def build_beach_sand():
    """3. beach_sand.glb: A 50m wide sand-colored ring/plane to place at the edge
    of the island where grass meets water."""
    # Octagonal/square shoreline ring with 50m wide beach strip (inner radius 450m,
    # outer radius 500m -> 1000m x 1000m island perimeter, 50m beach width, gentle
    # 0.5m slope from inner grass edge down to water level).
    inner = 450.0
    outer = 500.0   # outer - inner = 50.0m beach width
    verts = [
        # Outer shoreline perimeter at z = 0.0 (indices 0..3)
        (-outer, -outer, 0.0),
        ( outer, -outer, 0.0),
        ( outer,  outer, 0.0),
        (-outer,  outer, 0.0),
        # Inner grass-edge perimeter at z = 0.5m (indices 4..7)
        (-inner, -inner, 0.5),
        ( inner, -inner, 0.5),
        ( inner,  inner, 0.5),
        (-inner,  inner, 0.5),
    ]
    faces = [
        (0, 1, 5, 4),  # South beach strip (50m wide)
        (1, 2, 6, 5),  # East beach strip (50m wide)
        (2, 3, 7, 6),  # North beach strip (50m wide)
        (3, 0, 4, 7),  # West beach strip (50m wide)
    ]
    mesh = bpy.data.meshes.new("BeachSandMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new("BeachSand", mesh)
    bpy.context.collection.objects.link(obj)

    smart_unwrap(obj, density_for("sand"))
    assign_material(obj, make_material("BeachSand_Mat", "sand"))
    set_origin_bottom_center(obj)
    return obj


def build_dam_concrete():
    """4. dam_concrete.glb: A massive concrete wall (50m wide, 20m tall, 5m thick)
    with a curved front face to hold back the river water."""
    width = 50.0
    height = 20.0
    thick = 5.0
    segs = 10

    # Arch curve along X: wall is 5m thick everywhere, curving forward by 3.5m at center,
    # or front face curves cleanly with 5m wall thickness.
    # Let's make the front face curved (+Y arch) and total Y span = 5.0m (or wall thickness = 5.0m).
    xs = [-width / 2.0 + (width / segs) * i for i in range(segs + 1)]
    verts = []
    for x in xs:
        # Curved front face: extra arch thickness at center holding back water,
        # tapering at ends, with base wall thickness 5m
        arch = 2.5 * math.cos(math.pi * x / width)
        y_front = thick / 2.0 + arch
        y_back = -thick / 2.0 + arch * 0.4
        verts.append((x, y_front, 0.0))     # 0: front bottom
        verts.append((x, y_front, height))  # 1: front top
        verts.append((x, y_back, height))   # 2: back top
        verts.append((x, y_back, 0.0))      # 3: back bottom

    faces = []
    for i in range(segs):
        b0 = i * 4
        b1 = (i + 1) * 4
        faces.append((b0 + 0, b0 + 1, b1 + 1, b1 + 0))  # curved front face
        faces.append((b0 + 1, b0 + 2, b1 + 2, b1 + 1))  # top walkway crest
        faces.append((b0 + 2, b0 + 3, b1 + 3, b1 + 2))  # back face
        faces.append((b0 + 3, b0 + 0, b1 + 0, b1 + 3))  # bottom face

    # Left and right end caps
    faces.append((0, 3, 2, 1))
    last = segs * 4
    faces.append((last + 0, last + 1, last + 2, last + 3))

    mesh = bpy.data.meshes.new("DamConcreteMesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new("DamConcrete", mesh)
    bpy.context.collection.objects.link(obj)

    # Normalize Y depth to 5.0m (so bounding box is 50m wide x 5m thick x 20m tall
    # while preserving the curved front face!)
    set_origin_bottom_center(obj)
    obj.dimensions = (50.0, 5.0, 20.0)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    smart_unwrap(obj, density_for("concrete"))
    assign_material(obj, make_material("DamConcrete_Mat", "concrete"))
    set_origin_bottom_center(obj)
    return obj


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    print(f"Blender {bpy.app.version_string} — Phase 2 Water & Beach Generator")
    ensure_textures()
    os.makedirs(WATER_DIR, exist_ok=True)
    failures = []

    def run(label: str, filename: str, builder):
        print(f"Building {label} ...")
        try:
            clear_scene()
            set_metric_units()
            obj = builder()
            report(obj, label)
            path = os.path.join(WATER_DIR, filename)
            export_glb(path)
            verify_glb(path)
        except Exception as exc:
            failures.append((label, exc))
            print(f"  FAILED {label}: {exc!r}")

    run("water_ocean.glb", "water_ocean.glb", build_water_ocean)
    run("water_river.glb", "water_river.glb", build_water_river)
    run("beach_sand.glb", "beach_sand.glb", build_beach_sand)
    run("dam_concrete.glb", "dam_concrete.glb", build_dam_concrete)

    if failures:
        print(f"\n{len(failures)} task(s) failed:")
        for label, exc in failures:
            print(f"  - {label}: {exc!r}")
        return 1
    print("Done — Water & Beach assets generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
