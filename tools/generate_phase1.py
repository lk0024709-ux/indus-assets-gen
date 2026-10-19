#!/usr/bin/env python3
"""Phase 1 asset generator for the Indus : Battle Royale 3D pipeline.

Runs headless through the pip-installable ``bpy`` module (Blender as a Python
module) and generates the colourful Phase 1 asset set:

TERRAIN
    ``base_ground.glb``  — 100 m x 100 m flat grass plane (origin = surface centre)

BUILDINGS (strict rules, see below)
    ``house_tactical.glb``   — 2 storeys, 10 x 8 m, RED/BROWN brick, wooden porch,
                               balcony, rusty metal gable roof, back fire escape;
                               all 4 doors swing INWARD (opposite side)
    ``school_yellow.glb``    — 2 storeys, 14 x 10 m, BRIGHT YELLOW concrete school
    ``apartment_green.glb``  — 3 storeys, 12 x 10 m, VIBRANT GREEN concrete,
                               stairs connecting all 3 floors AND the flat roof
    ``cabin_wood.glb``       — 1 storey, 8 x 6 m, WARM BROWN wood cabin, gable roof
    ``warehouse_metal.glb``  — 1 storey, 20 x 12 m, STEEL-BLUE walls with a
                               RUSTY RED-ORANGE roof/doors, concrete floor
    ``ruined_building.glb``  — 2 storeys, 10 x 8 m, darkened GREY concrete,
                               BMesh face deletion, exposed rebar, rubble,
                               bare doorway/window cutouts (no door leaf or
                               window shutters)

HERO SCENE (web preview)
    ``scene_phase1.glb``     — the 100 m ground with all six buildings placed
                               on it and soft shadows baked into the terrain

TASK 1 — UV MAPPING (no more stretching)
----------------------------------------
Every textured material is built as:
    Texture Coordinate (UV) -> Mapping (Scale 0.3, 0.3, 0.3) -> Image Texture
    (Extension = REPEAT) -> Principled BSDF Base Color
The exporter turns the Mapping node into ``KHR_texture_transform`` (verified).
Because Blender's smart_project packs each object's UVs into 0..1 (density
varies with object size — the old stretching bug), ``smart_unwrap`` re-scales
each object's UVs to a constant world density first, so ``tile_m`` metres of
surface == one texture tile after the 0.3 Mapping scale.  Bricks/planks/ribs
end up human-sized everywhere.

TASK 2 — COLOUR TINTING
-----------------------
Blender's glTF exporter DROPS MixRGB nodes between a texture and Base Color
(verified: exported image is byte-identical to the source), so the Multiply
tint is baked into generated texture variants (identical math, exporter-safe):
    out = clip(src * (target_mean / src_mean))
Textures: brick_red, concrete_yellow, concrete_green, wood_warm,
metal_steelblue, rust_orange, concrete_greydark (ruin), plus darker
concrete_dark / wood_dark for interior floors & ceilings (Task 3).

TASK 3 — INTERIOR & ROOF MATERIALS
----------------------------------
Floors, ceilings and slabs use the darker concrete_dark / wood_dark textures;
walls keep their vivid tint on both sides; every roof slab's UNDERSIDE carries
the roof material (single-material boxes).

CRITICAL RULES ENFORCED FOR EVERY BUILDING
------------------------------------------
* Stairs use trigonometry: ``step_depth = rise / math.tan(math.radians(32))``
  so every flight climbs at exactly 32 degrees.  Each flight gets a Boolean
  Difference hole of exactly 3.0 m x 1.5 m in the slab above it — spanning the
  final 3.0 m of run before the stair top (head-room swept volume at 32°) —
  and the stairs are placed exactly there.
* Perfect-fit OPEN openings: doors 1.5 m W x 2.2 m H and windows
  1.2 m x 1.2 m (sill 1.0 m) are cut, then hung OPEN with leaves/shutters
  sized EXACTLY to the opening (leaf = 1.5 x 2.2; each shutter = 0.6 x 1.2;
  full height, top flush with the opening head) — except the Ruined Building,
  whose doorway and window cutouts have NO door leaf or window shutters.
  Hinges sit precisely on
  the opening's side edges at the outer wall plane — no float, no undersize,
  no gap at the hinge line.  Openings stay passable (no glass, no blockers);
  garage openings hang a roll bundle exactly matching their 6 m width.
* Interiors: internal floors, ceilings, bed/table/crates cover, OmniLights.

Usage:
    pip install bpy pillow numpy
    python tools/generate_phase1.py
"""

from __future__ import annotations

import json
import math
import os
import random
import struct
import sys

import bpy
import bmesh
import numpy as np
from mathutils import Matrix, Vector

# --- Paths -----------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURE_DIR = os.path.join(REPO_ROOT, "docs", "textures")
MODELS_DIR = os.path.join(REPO_ROOT, "docs", "models")
BUILDINGS_DIR = os.path.join(MODELS_DIR, "buildings")
TERRAIN_DIR = os.path.join(MODELS_DIR, "terrain")

# --- Stair math (32 degrees, critical rule) --------------------------------
STAIR_RISE = 0.20
STAIR_ANGLE = math.radians(32.0)
STEP_DEPTH = STAIR_RISE / math.tan(STAIR_ANGLE)     # ≈ 0.3200 m
STAIR_W = 1.5
HOLE_LEN = 3.0
HOLE_CLEAR = 0.04

DOOR_W, DOOR_H = 1.5, 2.2
WIN_W, WIN_H, WIN_SILL = 1.2, 1.2, 1.0

# Mapping node scale (Task 1 spec) — exported as KHR_texture_transform.
MAP_SCALE = 0.3
# measured exporter offset for Mapping(loc=(0,0), scale=0.3) — see hero UV warp
MAP_EXPORT_OFFSET_Y = 0.7

# --- Hero layout (scene + baked-shadow texture) ----------------------------
HERO_SPOTS = {
    # name: (x, y, rotation_degrees)
    "house_tactical": (-26.0, 16.0, 20.0),
    "apartment_green": (12.0, 20.0, -12.0),
    "school_yellow": (34.0, -2.0, -28.0),
    "warehouse_metal": (-10.0, -26.0, 5.0),
    "ruined_building": (22.0, -24.0, 30.0),
    "cabin_wood": (-34.0, -6.0, 15.0),
}
HERO_SHADOW_DIR = (1.0, 0.62)
HERO_FOOTPRINTS = {
    "house_tactical": (10.0, 8.0),
    "apartment_green": (12.0, 10.0),
    "school_yellow": (14.0, 10.0),
    "warehouse_metal": (20.0, 12.0),
    "ruined_building": (10.0, 8.0),
    "cabin_wood": (8.0, 6.0),
}

# --- Material presets -------------------------------------------------------
# ``tile`` = metres of surface covered by one texture tile (after Mapping 0.3)
MATERIALS = {
    # tinted variants (Task 2)
    "brick_red": {"file": "brick_red.png", "roughness": 0.85, "metallic": 0.00, "tile": 1.5},
    "concrete_yellow": {"file": "concrete_yellow.png", "roughness": 0.88, "metallic": 0.00, "tile": 2.5},
    "concrete_green": {"file": "concrete_green.png", "roughness": 0.88, "metallic": 0.00, "tile": 2.5},
    "wood_warm": {"file": "wood_warm.png", "roughness": 0.72, "metallic": 0.00, "tile": 2.0},
    "metal_steelblue": {"file": "metal_steelblue.png", "roughness": 0.45, "metallic": 0.70, "tile": 1.0},
    "rust_orange": {"file": "rust_orange.png", "roughness": 0.78, "metallic": 0.45, "tile": 1.0},
    "concrete_greydark": {"file": "concrete_greydark.png", "roughness": 0.92, "metallic": 0.00, "tile": 2.5},
    # darker interior variants (Task 3)
    "concrete_dark": {"file": "concrete_dark.png", "roughness": 0.92, "metallic": 0.00, "tile": 2.5},
    "wood_dark": {"file": "wood_dark.png", "roughness": 0.78, "metallic": 0.00, "tile": 2.0},
    # untinted originals (accents, natural wood, ruin rebar)
    "concrete": {"file": "concrete_wall.png", "roughness": 0.90, "metallic": 0.00, "tile": 2.5},
    "wood": {"file": "wood_plank.png", "roughness": 0.72, "metallic": 0.00, "tile": 2.0},
    "rust": {"file": "metal_rusted.png", "roughness": 0.78, "metallic": 0.45, "tile": 1.0},
    "grass": {"file": "grass.png", "roughness": 0.95, "metallic": 0.00, "tile": 4.0},
    "grass_hero": {"file": "grass_hero.png", "roughness": 0.95, "metallic": 0.00, "tile": None},
}

SOLID_MATERIALS = {
    "mattress": {"rgba": (0.82, 0.80, 0.74, 1.0), "roughness": 0.90},
    "pillow": {"rgba": (0.92, 0.92, 0.90, 1.0), "roughness": 0.95},
}

# Tint table: texture file -> (source file, target mean RGB 0..1)  (Task 2)
TINTS = {
    "brick_red.png": ("brick_wall.png", (0.52, 0.24, 0.17)),          # house: red/brown
    "concrete_yellow.png": ("concrete_wall.png", (0.95, 0.80, 0.12)),  # school: bright yellow
    "concrete_green.png": ("concrete_wall.png", (0.18, 0.72, 0.26)),   # apartment: vibrant green
    "wood_warm.png": ("wood_plank.png", (0.58, 0.36, 0.19)),           # cabin: warm brown
    "metal_steelblue.png": ("metal_corrugated.png", (0.32, 0.50, 0.72)),  # warehouse: steel blue
    "rust_orange.png": ("metal_rusted.png", (0.66, 0.31, 0.15)),       # warehouse: rusty red/orange
    "concrete_greydark.png": ("concrete_wall.png", (0.26, 0.26, 0.27)),  # ruin: darkened grey
    "concrete_dark.png": ("concrete_wall.png", (0.30, 0.30, 0.31)),    # interiors: darker concrete
    "wood_dark.png": ("wood_plank.png", (0.34, 0.22, 0.13)),           # interiors: darker wood
}

_MATERIAL_CACHE: dict[str, object] = {}


# ---------------------------------------------------------------------------
# Procedural texture generation (numpy + Pillow)
# ---------------------------------------------------------------------------
def _fft_noise(size: int, cutoff: float, seed: int) -> np.ndarray:
    """Periodic (perfectly tileable) Gaussian noise field via FFT low-pass."""
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


def ensure_grass_texture() -> None:
    path = os.path.join(TEXTURE_DIR, "grass.png")
    if os.path.isfile(path):
        return
    from PIL import Image

    size = 1024
    patches = _fft_noise(size, 0.012, seed=11)
    clumps = _fft_noise(size, 0.05, seed=12)
    blades = _fft_noise(size, 0.25, seed=13)
    fine = _fft_noise(size, 0.9, seed=14)
    g = 0.5 * patches + 0.32 * clumps + 0.30 * blades + 0.16 * fine
    g /= 1.05
    t = np.clip(0.5 + 0.30 * g, 0.0, 1.0)
    col = _lerp_rgb((0.10, 0.20, 0.07), (0.24, 0.42, 0.14), t)
    dry_t = np.clip(0.5 + 0.5 * patches, 0.0, 1.0)
    dry_strength = np.clip(0.5 + 0.42 * patches - 0.32, 0.0, 1.0) ** 2
    dry_col = _lerp_rgb((0.40, 0.43, 0.18), (0.52, 0.47, 0.22), dry_t)
    col = col * (1.0 - dry_strength[..., None]) + dry_col * dry_strength[..., None]
    col += 0.05 * fine[..., None]
    col = np.clip(col, 0.0, 1.0)
    Image.fromarray((col * 255).astype(np.uint8), "RGB").save(path, "PNG")
    print(f"  generated texture {os.path.basename(path)}")


def ensure_rust_texture() -> None:
    from PIL import Image

    src = os.path.join(TEXTURE_DIR, "metal_rusted.png")
    if os.path.isfile(src):
        return
    original = os.path.join(TEXTURE_DIR, "metal_corrugated.png")
    if not os.path.isfile(original):
        return
    img = np.asarray(Image.open(original).convert("RGB"), dtype=np.float64) / 255.0
    size = img.shape[0]
    patch_n = _fft_noise(size, 0.02, seed=21)
    spot_n = _fft_noise(size, 0.09, seed=22)
    mask = np.clip(0.5 + 0.55 * patch_n + 0.30 * spot_n, 0.0, 1.0)
    mask = np.clip((mask - 0.45) * 2.4, 0.0, 1.0) * 0.88
    rust = _lerp_rgb((0.44, 0.20, 0.08), (0.30, 0.13, 0.05),
                     np.clip(0.5 + 0.3 * spot_n, 0, 1))
    out = img * (1.0 - mask[..., None]) + rust * mask[..., None]
    mean = out.mean()
    out = np.clip((out - mean) * 1.08 + 0.36, 0.0, 1.0)
    Image.fromarray((out * 255).astype(np.uint8), "RGB").save(src, "PNG")
    print(f"  generated texture {os.path.basename(src)}")


def ensure_tint_textures() -> None:
    """Colour-tinted texture variants (Task 2).

    Blender's glTF exporter drops MixRGB nodes, so the Multiply tint is baked
    into the pixels: ``out = clip(src * (target_mean / src_mean))`` — same
    math as a Multiply MixRGB, but it survives GLB export.
    """
    from PIL import Image

    for dst_name, (src_name, target) in TINTS.items():
        dst = os.path.join(TEXTURE_DIR, dst_name)
        if os.path.isfile(dst):
            continue
        src_path = os.path.join(TEXTURE_DIR, src_name)
        if not os.path.isfile(src_path):
            raise FileNotFoundError(f"tint source missing: {src_path}")
        img = np.asarray(Image.open(src_path).convert("RGB"), dtype=np.float64) / 255.0
        src_mean = img.mean(axis=(0, 1))
        gain = np.clip(np.asarray(target) / np.maximum(src_mean, 1e-6), 0.05, 4.0)
        out = np.clip(img * gain, 0.0, 1.0)
        # tiny contrast lift so vibrant tints keep detail
        out = np.clip((out - out.mean()) * 1.06 + out.mean(), 0.0, 1.0)
        Image.fromarray((out * 255).astype(np.uint8), "RGB").save(dst, "PNG")
        print(f"  generated tint {os.path.basename(dst)} (mean -> "
              f"{(out.mean(axis=(0,1)) * 255).round(0)})")


def ensure_hero_ground_texture() -> None:
    ensure_grass_texture()
    dst = os.path.join(TEXTURE_DIR, "grass_hero.png")
    if os.path.isfile(dst):
        return
    from PIL import Image

    grass = np.asarray(
        Image.open(os.path.join(TEXTURE_DIR, "grass.png")).convert("RGB"),
        dtype=np.float64,
    ) / 255.0
    size = grass.shape[0]
    lin = np.linspace(-50.0, 50.0, size)
    wx, wy = np.meshgrid(lin, lin)
    shade = np.ones((size, size), dtype=np.float64)

    sx, sy = HERO_SHADOW_DIR
    snorm = math.hypot(sx, sy)
    sx, sy = sx / snorm, sy / snorm

    for name, (cx, cy, rot_deg) in HERO_SPOTS.items():
        w, d = HERO_FOOTPRINTS[name]
        off = 0.16 * (w + d) * 0.5 + 1.1
        px = wx - (cx + sx * off)
        py = wy - (cy + sy * off)
        a = math.radians(-rot_deg)
        lx = px * math.cos(a) - py * math.sin(a)
        ly = px * math.sin(a) + py * math.cos(a)
        bx, by = w * 0.5 + 0.4, d * 0.5 + 0.4
        ex = np.maximum(np.abs(lx) - bx + 0.7, 0.0)
        ey = np.maximum(np.abs(ly) - by + 0.7, 0.0)
        dist = np.maximum(np.sqrt(ex ** 2 + ey ** 2) - 0.7, 0.0)
        falloff = np.exp(-((dist / 1.35) ** 2))
        shade = np.minimum(shade, 1.0 - 0.52 * falloff)

    out = np.clip(grass * shade[..., None], 0.0, 1.0)
    Image.fromarray((out * 255).astype(np.uint8), "RGB").save(dst, "PNG")
    print(f"  generated texture {os.path.basename(dst)}")


# ---------------------------------------------------------------------------
# Scene / object helpers
# ---------------------------------------------------------------------------
def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _MATERIAL_CACHE.clear()


def set_metric_units() -> None:
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0


def create_box(name: str, size, location=(0.0, 0.0, 0.0), rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "Mesh"
    obj.dimensions = tuple(size)
    obj.rotation_euler = rotation
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def create_triangular_prism(name, x_min, x_max, tri_yz):
    x0, x1 = (x_min, x_max) if x_min < x_max else (x_max, x_min)
    (y0, z0), (y1, z1), (y2, z2) = tri_yz
    verts = [
        (x0, y0, z0), (x0, y1, z1), (x0, y2, z2),
        (x1, y0, z0), (x1, y1, z1), (x1, y2, z2),
    ]
    faces = [
        (0, 2, 1), (3, 4, 5),
        (0, 1, 4, 3), (1, 2, 5, 4), (2, 0, 3, 5),
    ]
    mesh = bpy.data.meshes.new(name + "Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def apply_boolean_cut(target, cutter) -> None:
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


def smart_unwrap(obj, target_density: float | None = None) -> None:
    """UV-unwrap with smart_project, orient wall textures upright, then
    re-scale UVs to a constant world density (``target_density`` UV/metre).

    smart_project packs each object into 0..1, so density varies with object
    size — that's what made bricks stretch.  Normalising to a world density
    makes one tile = ``tile_m`` metres everywhere (Mapping 0.3 applies later).
    """
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

    # Rotate per-face UVs so texture V follows world Z on vertical faces.
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

    # Constant world density: scale UVs so UV/metre == target_density.
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
            current = math.sqrt(area_uv / area3d)      # UV per metre
            k = target_density / current
            for layer in obj.data.uv_layers:
                for loop_uv in layer.data:
                    loop_uv.uv = loop_uv.uv * k


def set_hero_ground_uvs(obj) -> None:
    """Exact 0..1 world UVs for the 100 m hero ground, pre-warped so the
    exported Mapping(0.3) + KHR_texture_transform offset compose to identity
    (the baked shadows must land at exact world positions)."""
    me = obj.data
    if not me.uv_layers:
        me.uv_layers.new(name="UVMap")
    uvl = me.uv_layers.active
    for poly in me.polygons:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            u = (co.x + 50.0) / 100.0
            v = (co.y + 50.0) / 100.0
            # undo: uv' = offset + 0.3 * uv  ->  uv = (u, (v - 0.7) / 0.3)
            uvl.data[li].uv = (
                u / MAP_SCALE,
                (v - MAP_EXPORT_OFFSET_Y) / MAP_SCALE,
            )


def make_material(name: str, preset: str):
    """Texture Coordinate (UV) -> Mapping (0.3) -> Image Texture (REPEAT)
    -> Principled BSDF Base Color.  Cached per scene run."""
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
        raise RuntimeError("Principled BSDF node not found in new material")

    tex_path = os.path.join(TEXTURE_DIR, spec["file"])
    if not os.path.isfile(tex_path):
        raise FileNotFoundError(f"Texture not found: {tex_path}")
    image = bpy.data.images.load(tex_path, check_existing=True)

    coord = nt.nodes.new("ShaderNodeTexCoord")
    coord.name = f"{name}_Coord"
    coord.location = (-760.0, 220.0)

    mapping = nt.nodes.new("ShaderNodeMapping")           # Task 1: scale 0.3
    mapping.name = f"{name}_Mapping"
    mapping.location = (-560.0, 220.0)
    mapping.inputs["Scale"].default_value = (MAP_SCALE, MAP_SCALE, MAP_SCALE)

    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.name = f"{name}_Texture"
    tex.label = spec["file"]
    tex.image = image
    tex.extension = "REPEAT"                              # Task 1: REPEAT
    tex.location = (-350.0, 220.0)

    nt.links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

    bsdf.inputs["Roughness"].default_value = spec["roughness"]
    bsdf.inputs["Metallic"].default_value = spec["metallic"]
    _MATERIAL_CACHE[cache_key] = mat
    return mat


def make_solid_material(name: str, spec, roughness: float | None = None):
    if name in _MATERIAL_CACHE:
        return _MATERIAL_CACHE[name]
    mat = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = tuple(spec["rgba"])
    bsdf.inputs["Roughness"].default_value = roughness or spec["roughness"]
    bsdf.inputs["Metallic"].default_value = 0.0
    _MATERIAL_CACHE[name] = mat
    return mat


def density_for(preset: str) -> float | None:
    """Numeric UV density (UV/metre) so that after Mapping(0.3) one tile
    spans exactly ``tile`` metres of surface."""
    tile = MATERIALS[preset]["tile"]
    if not tile:
        return None
    return 1.0 / (MAP_SCALE * tile)


def assign_material(obj, mat) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def join_objects(objects, name):
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


def add_omni_light(name: str, location, energy: float = 150.0, color=(1.0, 0.85, 0.62)):
    light_data = bpy.data.lights.new(name=name, type="POINT")
    light_data.energy = energy
    light_data.color = color
    light_data.shadow_soft_size = 0.25
    obj = bpy.data.objects.new(name, light_data)
    obj.location = tuple(location)
    bpy.context.collection.objects.link(obj)
    return obj


# ---------------------------------------------------------------------------
# Domain helpers: stairs, openings, shutters, furniture, rubble
# ---------------------------------------------------------------------------
def stair_flight(name: str, lane_x: float, y_start: float, direction: int,
                 base_z: float, target_z: float):
    """One 32-degree flight along Y; top tread flush with ``target_z``.
    Returns (step_boxes, hole) — hole = exact 3.0 x 1.5 m Boolean region in
    the slab above (final 3 m of run before the stair top)."""
    rise = STAIR_RISE
    n = round((target_z - base_z) / rise)
    if abs(base_z + n * rise - target_z) > 1e-6:
        raise ValueError(
            f"{name}: floor height {target_z - base_z} not a multiple of {rise}"
        )
    boxes = []
    for i in range(1, n + 1):
        tread_z = base_z + i * rise
        y_c = y_start + direction * ((i - 0.5) * STEP_DEPTH)
        boxes.append(create_box(
            f"{name}_Step{i:02d}",
            (STAIR_W, STEP_DEPTH, rise),
            (lane_x, y_c, tread_z - rise / 2.0),
        ))
    top_y = y_start + direction * n * STEP_DEPTH
    hole = {
        "x": lane_x,
        "y_center": top_y - direction * (HOLE_LEN / 2.0),
        "width": STAIR_W + HOLE_CLEAR,
        "length": HOLE_LEN + HOLE_CLEAR,
        "top_y": top_y,
        "steps": n,
    }
    return boxes, hole


def cut_stair_hole(slab, hole, slab_center_z: float, slab_thickness: float) -> None:
    cutter = create_box(
        "StairHoleCutter",
        (hole["width"], hole["length"], slab_thickness + 1.0),
        (hole["x"], hole["y_center"], slab_center_z),
    )
    apply_boolean_cut(slab, cutter)


def cut_opening(target, center, outward, wall_t: float, w: float, h: float,
                bottom_z: float, tag: str):
    cx, cy = center
    cz = bottom_z + h / 2.0
    if abs(outward[1]) > 0.5:
        size = (w, wall_t + 0.8, h)
    else:
        size = (wall_t + 0.8, w, h)
    cutter = create_box(f"{tag}_Cutter", size, (cx, cy, cz))
    apply_boolean_cut(target, cutter)
    return Vector((cx, cy, cz))


def cut_door(target, center, outward, wall_t: float, floor_top: float,
             slab_t: float, tag: str):
    """Door opening 1.5 m W x 2.2 m H above the floor; cutter dips through
    the floor-slab band so no wall strip pokes through the flush floor."""
    cut_bottom = floor_top - slab_t
    h = DOOR_H + (floor_top - cut_bottom)
    return cut_opening(target, center, outward, wall_t, DOOR_W, h, cut_bottom, tag)


def add_shutters(opening_center, outward, wall_t: float, tag: str,
                 damaged: bool = False):
    """Two OPEN shutter panels, each EXACTLY WIN_W/2 x WIN_H (together the
    pair matches the opening to the millimetre).  Hinges sit precisely on the
    opening's side edges at the outer wall plane — no float, no undersize,
    no gap at the hinge line.  Swing: 105 deg (128 deg when damaged)."""
    n = Vector((float(outward[0]), float(outward[1]), 0.0)).normalized()
    t = Vector((-n.y, n.x, 0.0))
    half_w = WIN_W / 2.0
    swing = math.radians(128.0 if damaged else 105.0)
    panels = []
    for side in (-1.0, 1.0):
        # hinge exactly on the opening's side edge, on the outer wall plane
        hinge = (Vector((opening_center.x, opening_center.y, 0.0))
                 + t * (side * half_w) + n * (wall_t / 2.0))
        closed_dir = -t * side
        v = closed_dir * math.cos(swing) + n * math.sin(swing)
        centre = hinge + v * (half_w / 2.0)
        yaw = math.atan2(v.y, v.x)
        roll = math.radians(6.0) if damaged else 0.0
        panels.append(create_box(
            f"{tag}_Shutter_{'L' if side < 0 else 'R'}",
            (half_w, 0.045, WIN_H),          # EXACT opening-derived size
            (centre.x, centre.y, opening_center.z),
            rotation=(roll, 0.0, yaw),
        ))
    return panels


def add_door_leaf(opening_center, outward, wall_t: float, door_w: float,
                  door_h: float, tag: str, bottom_z: float,
                  damaged: bool = False, swing_inward: bool = False):
    """OPEN door leaf EXACTLY door_w x door_h — full height, bottom on the
    floor, top flush with the opening top.  The hinge edge sits exactly on
    the opening's side edge (no float); sizing is opening-derived.
    Swing: 112 deg (138 deg when damaged).
    ``swing_inward=True`` reverses the swing to the OPPOSITE side — the leaf
    opens INTO the building, with the hinge axis on the interior wall face
    so the leaf clears the wall corner without slicing it."""
    n = Vector((float(outward[0]), float(outward[1]), 0.0)).normalized()
    t = Vector((-n.y, n.x, 0.0))
    hinge = (Vector((opening_center.x, opening_center.y, 0.0))
             + t * (door_w / 2.0) + n * ((-1.0 if swing_inward else 1.0)
                                         * (wall_t / 2.0)))
    swing = math.radians(138.0 if damaged else 112.0)
    closed_dir = -t
    side_dir = -n if swing_inward else n
    v = closed_dir * math.cos(swing) + side_dir * math.sin(swing)
    centre = hinge + v * (door_w / 2.0)
    yaw = math.atan2(v.y, v.x)
    roll = math.radians(10.0) if damaged else 0.0
    return create_box(
        f"{tag}_Leaf",
        (door_w, 0.05, door_h),              # EXACT opening-derived size
        (centre.x, centre.y, bottom_z + door_h / 2.0),
        rotation=(roll, 0.0, yaw),
    )


def add_bed(prefix: str, x: float, y: float, floor_z: float, rot_z: float = 0.0):
    a = math.radians(rot_z)
    ca, sa = math.cos(a), math.sin(a)

    def place(dx, dy):
        return (x + dx * ca - dy * sa, y + dx * sa + dy * ca)

    parts = []
    fx, fy = place(0.0, 0.0)
    parts.append((create_box(f"{prefix}_Frame", (2.0, 1.05, 0.24),
                             (fx, fy, floor_z + 0.12), rotation=(0, 0, a)), "wood"))
    mx, my = place(0.0, 0.0)
    parts.append((create_box(f"{prefix}_Mattress", (1.9, 0.96, 0.20),
                             (mx, my, floor_z + 0.34), rotation=(0, 0, a)), "mattress"))
    px, py = place(0.72, 0.0)
    parts.append((create_box(f"{prefix}_Pillow", (0.42, 0.6, 0.10),
                             (px, py, floor_z + 0.49), rotation=(0, 0, a)), "pillow"))
    return parts


def add_table(prefix: str, x: float, y: float, floor_z: float, rot_z: float = 0.0,
              size=(1.4, 0.85)):
    a = math.radians(rot_z)
    w, d = size
    parts = [(create_box(f"{prefix}_Top", (w, d, 0.07),
                         (x, y, floor_z + 0.74), rotation=(0, 0, a)), "wood")]
    ca, sa = math.cos(a), math.sin(a)
    for dx in (-w / 2 + 0.09, w / 2 - 0.09):
        for dy in (-d / 2 + 0.09, d / 2 - 0.09):
            lx = x + dx * ca - dy * sa
            ly = y + dx * sa + dy * ca
            parts.append((create_box(f"{prefix}_Leg", (0.09, 0.09, 0.70),
                                     (lx, ly, floor_z + 0.35), rotation=(0, 0, a)), "wood"))
    return parts


def add_crates(prefix: str, x: float, y: float, floor_z: float, n: int = 4,
               rng: random.Random | None = None):
    rng = rng or random.Random(0)
    parts = []
    s = 0.85
    slots = [(-s * 0.55, -s * 0.55), (s * 0.55, -s * 0.55),
             (-s * 0.55, s * 0.55), (s * 0.55, s * 0.55),
             (0.0, 0.0, s * 0.9)]
    for i in range(min(n, len(slots))):
        slot = slots[i]
        dx, dy = slot[0], slot[1]
        dz = slot[2] if len(slot) > 2 else 0.0
        parts.append((create_box(
            f"{prefix}_Crate{i}",
            (s, s, s),
            (x + dx, y + dy, floor_z + dz + s / 2.0),
            rotation=(0, 0, math.radians(rng.uniform(-18, 18))),
        ), "wood"))
    return parts


def add_rubble_pile(prefix: str, x: float, y: float, floor_z: float, count: int,
                    rng: random.Random, kind: str = "concrete_greydark"):
    parts = []
    for i in range(count):
        sx = rng.uniform(0.25, 0.85)
        sy = rng.uniform(0.25, 0.85)
        sz = rng.uniform(0.15, 0.5)
        dx = rng.uniform(-1.1, 1.1)
        dy = rng.uniform(-1.1, 1.1)
        dz = 0.0 if i < 4 else rng.uniform(0.15, 0.55)
        parts.append((create_box(
            f"{prefix}_Rubble{i}",
            (sx, sy, sz),
            (x + dx, y + dy, floor_z + dz + sz / 2.0),
            rotation=(rng.uniform(-0.25, 0.25), rng.uniform(-0.25, 0.25),
                      rng.uniform(0, math.pi)),
        ), kind))
    return parts


def _face_components(bm):
    seen = set()
    comps = []
    face_edges = {}
    for f in bm.faces:
        for e in f.edges:
            face_edges.setdefault(e.index, []).append(f)
    for f in bm.faces:
        if f.index in seen:
            continue
        stack = [f]
        comp = []
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            comp.append(cur)
            for e in cur.edges:
                for nb in face_edges.get(e.index, ()):
                    if nb.index not in seen:
                        seen.add(nb.index)
                        stack.append(nb)
        comps.append(comp)
    return comps


def destroy_faces(obj, p_bottom: float, p_top: float, keep: str, seed: int,
                  cuts: int = 5) -> None:
    """BMesh destruction: subdivide, delete random faces (height-weighted),
    keep only grounded/border components so no debris floats in the air."""
    rng = random.Random(seed)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=cuts, use_grid_fill=True)
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()

    zs = [v.co.z for v in bm.verts]
    zmin, zmax = min(zs), max(zs)
    doomed = []
    for f in bm.faces:
        c = f.calc_center_median()
        t = (c.z - zmin) / (zmax - zmin + 1e-9)
        p = p_bottom + (p_top - p_bottom) * (t ** 1.35)
        if rng.random() < p:
            doomed.append(f)
    bmesh.ops.delete(bm, geom=doomed, context="FACES")
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")

    xs = [v.co.x for v in bm.verts]
    ys = [v.co.y for v in bm.verts]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    keep_faces = []
    for comp in _face_components(bm):
        if keep == "bottom":
            grounded = any(f.calc_center_median().z <= zmin + 0.2 for f in comp)
        else:
            grounded = any(
                min(abs(v.co.x - xmin), abs(v.co.x - xmax),
                    abs(v.co.y - ymin), abs(v.co.y - ymax)) < 0.45
                for f in comp for v in f.verts
            )
        if grounded:
            keep_faces.extend(comp)
    keep_set = set(keep_faces)
    drop = [f for f in bm.faces if f not in keep_set]
    if drop:
        bmesh.ops.delete(bm, geom=drop, context="FACES")
        loose = [v for v in bm.verts if not v.link_faces]
        if loose:
            bmesh.ops.delete(bm, geom=loose, context="VERTS")

    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def add_rebar(anchors, rng, count: int = 18):
    rods = []
    if not anchors:
        return rods
    for i in range(count):
        ax, ay, az = anchors[rng.randrange(len(anchors))]
        length = rng.uniform(0.5, 1.1)
        if rng.random() < 0.65:
            rot = (math.radians(rng.uniform(-30, 30)),
                   math.radians(rng.uniform(-30, 30)),
                   math.radians(rng.uniform(0, math.pi)))
            loc = (ax + rng.uniform(-0.15, 0.15),
                   ay + rng.uniform(-0.15, 0.15),
                   az + length * 0.35)
            size = (0.035, 0.035, length)
        else:
            rot = (0.0, 0.0, math.radians(rng.uniform(0, math.pi)))
            loc = (ax + rng.uniform(-0.5, 0.5), ay + rng.uniform(-0.5, 0.5),
                   az + 0.04)
            size = (length, 0.035, 0.035)
        rods.append(create_box(f"Rebar_{i:02d}", size, loc, rotation=rot))
    return rods


def finish_building(parts, name: str, mat_prefix: str, light_specs):
    """Unwrap (world-density), assign materials, join, origin, add lights.

    ``parts`` = list of (object, preset_or_solid_kind).
    """
    materials = {}
    for obj, kind in parts:
        if kind in MATERIALS:
            if kind not in materials:
                materials[kind] = make_material(f"{mat_prefix}_{kind}", kind)
            smart_unwrap(obj, density_for(kind))
        else:
            if kind not in materials:
                materials[kind] = make_solid_material(f"{mat_prefix}_{kind}",
                                                      SOLID_MATERIALS[kind])
            smart_unwrap(obj, density_for("wood"))
        assign_material(obj, materials[kind])

    joined = join_objects([o for o, _ in parts], name)
    set_origin_bottom_center(joined)
    for i, (loc, energy) in enumerate(light_specs):
        color = (1.0, 0.78, 0.5) if mat_prefix == "Ruin" else (1.0, 0.85, 0.62)
        add_omni_light(f"{mat_prefix}_Omni{i}", loc, energy=energy, color=color)
    return joined


# ---------------------------------------------------------------------------
# TASK 1/2/3 — buildings with tinted materials
# ---------------------------------------------------------------------------
def build_house_tactical():
    """2 storeys, 10 x 8 m — RED/BROWN brick, wooden porch, balcony, rusty
    metal gable roof, back fire escape; doors swing INWARD, exact-fit hinges."""
    rng = random.Random(101)
    w, d = 10.0, 8.0
    t = 0.25
    slab_t = 0.20
    floor_z = slab_t
    s2_c, s2_t = 2.925, 0.15
    ceil_c = 5.925
    wall_top = 6.0

    parts = []
    # floors & ceilings use the darker interior textures (Task 3)
    parts += [
        (create_box("House_Base", (w - 0.02, d - 0.02, slab_t), (0.0, 0.0, slab_t / 2)),
         "concrete_dark"),
        (create_box("House_Slab2", (w - 0.02, d - 0.02, s2_t), (0.0, 0.0, s2_c)),
         "wood_dark"),
        (create_box("House_Ceiling", (w - 0.02, d - 0.02, 0.15), (0.0, 0.0, ceil_c)),
         "wood_dark"),
    ]

    walls = {
        "front": create_box("House_WallFront", (w - 2 * t, t, wall_top),
                            (0.0, -d / 2 + t / 2, wall_top / 2)),
        "back": create_box("House_WallBack", (w - 2 * t, t, wall_top),
                           (0.0, d / 2 - t / 2, wall_top / 2)),
        "left": create_box("House_WallLeft", (t, d, wall_top),
                           (-w / 2 + t / 2, 0.0, wall_top / 2)),
        "right": create_box("House_WallRight", (t, d, wall_top),
                            (w / 2 - t / 2, 0.0, wall_top / 2)),
    }
    parts += [(wt, "brick_red") for wt in walls.values()]

    part = create_box("House_Partition", (0.18, 4.3, wall_top - 0.15),
                      (0.6, -1.6, (0.15 + wall_top) / 2))
    cut_door(part, (0.6, -2.6), (1, 0), 0.18, floor_z, slab_t, "House_IntDoor1")
    cut_door(part, (0.6, -2.6), (1, 0), 0.18, 3.0, s2_t, "House_IntDoor2")
    parts.append((part, "brick_red"))

    # 32-degree flight + exact 3 x 1.5 hole in slab2 (parts[1])
    steps, hole = stair_flight("HouseStair", -3.95, -3.6, +1, floor_z, 3.0)
    cut_stair_hole(parts[1][0], hole, s2_c, s2_t)
    parts += [(s, "wood") for s in steps]

    normals = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}
    # ALL house doors swing INWARD (opposite side) into the building
    fd = cut_door(walls["front"], (1.0, -d / 2 + t / 2), (0, -1), t,
                  floor_z, slab_t, "House_FrontDoor")
    parts.append((add_door_leaf(fd, (0, -1), t, DOOR_W, DOOR_H,
                                "House_FrontDoor", floor_z,
                                swing_inward=True), "wood"))
    bd = cut_door(walls["back"], (2.6, d / 2 - t / 2), (0, 1), t,
                  floor_z, slab_t, "House_BackDoor")
    parts.append((add_door_leaf(bd, (0, 1), t, DOOR_W, DOOR_H,
                                "House_BackDoor", floor_z,
                                swing_inward=True), "wood"))
    fe = cut_door(walls["back"], (2.0, d / 2 - t / 2), (0, 1), t,
                  3.0, s2_t, "House_FireDoor")
    parts.append((add_door_leaf(fe, (0, 1), t, DOOR_W, DOOR_H,
                                "House_FireDoor", 3.0,
                                swing_inward=True), "rust"))
    bd2 = cut_door(walls["front"], (1.5, -d / 2 + t / 2), (0, -1), t,
                   3.0, s2_t, "House_BalconyDoor")
    parts.append((add_door_leaf(bd2, (0, -1), t, DOOR_W, DOOR_H,
                                "House_BalconyDoor", 3.0,
                                swing_inward=True), "wood"))

    window_specs = [
        ("front", -2.6, 0.0), ("back", -2.4, 0.0), ("left", 1.4, 0.0),
        ("right", -1.6, 0.0), ("right", 1.6, 0.0),
        ("front", -2.6, 3.0), ("back", -2.6, 3.0),
        ("left", 0.0, 3.0), ("left", 2.4, 3.0),
        ("right", 0.0, 3.0), ("right", 2.4, 3.0),
    ]
    for i, (wall, coord, fz) in enumerate(window_specs):
        n = normals[wall]
        if n[1] != 0:
            centre = (coord, -d / 2 + t / 2 if n[1] < 0 else d / 2 - t / 2)
        else:
            centre = (-w / 2 + t / 2 if n[0] < 0 else w / 2 - t / 2, coord)
        c = cut_opening(walls[wall], centre, n, t, WIN_W, WIN_H,
                        fz + WIN_SILL, f"House_Win{i}")
        parts += [(p, "wood") for p in add_shutters(c, n, t, f"House_Win{i}")]

    # wooden porch
    parts.append((create_box("House_PorchDeck", (9.8, 2.05, 0.20),
                             (0.0, -4.975, 0.10)), "wood"))
    for i, px in enumerate((-4.4, -1.6, 1.6, 4.4)):
        parts.append((create_box(f"House_PorchPost{i}", (0.15, 0.15, 2.35),
                                 (px, -5.9, 0.2 + 2.35 / 2)), "wood"))
    parts.append((create_box("House_PorchRoof", (9.9, 2.3, 0.12),
                             (0.0, -5.1, 2.6)), "rust"))
    for x0, x1 in ((-4.9, -0.1), (2.1, 4.9)):
        parts.append((create_box("House_PorchRail", (x1 - x0, 0.08, 0.08),
                                 ((x0 + x1) / 2, -5.95, 1.1)), "wood"))
    for px in (-4.85, -3.2, -1.5, 2.6, 3.6, 4.85):
        parts.append((create_box("House_PorchBal", (0.07, 0.07, 0.9),
                                 (px, -5.95, 0.65)), "wood"))

    # balcony
    parts.append((create_box("House_BalconyDeck", (6.0, 1.8, 0.15),
                             (1.7, -4.85, 2.925)), "wood"))
    for i, px in enumerate((-1.2, 0.2, 1.6, 3.0, 4.4)):
        parts.append((create_box(f"House_BalcPostF{i}", (0.08, 0.08, 1.0),
                                 (px, -5.7, 3.5)), "wood"))
    parts.append((create_box("House_BalcRailF", (6.0, 0.08, 0.08),
                             (1.7, -5.7, 4.0)), "wood"))
    parts.append((create_box("House_BalcRailF2", (6.0, 0.06, 0.06),
                             (1.7, -5.7, 3.5)), "wood"))
    for sx, tag in ((-1.2, "L"), (4.6, "R")):
        for dy in (-5.3, -4.7):
            parts.append((create_box(f"House_BalcPost{tag}", (0.08, 0.08, 1.0),
                                     (sx, dy, 3.5)), "wood"))
        parts.append((create_box(f"House_BalcRailSide{tag}", (0.08, 1.7, 0.08),
                                 (sx, -4.85, 4.0)), "wood"))
    for px in (-1.1, 4.5):
        parts.append((create_box("House_BalcSupport", (0.14, 0.14, 2.7),
                                 (px, -5.5, 1.55)), "wood"))

    # back fire escape (32 degrees, 15 risers, ground -> landing)
    parts.append((create_box("House_FE_Landing", (3.0, 1.7, 0.12),
                             (2.0, 4.8, 2.94)), "rust"))
    for px in (0.55, 1.5, 2.45, 3.45):
        parts.append((create_box("House_FE_Post", (0.06, 0.06, 1.0),
                                 (px, 5.6, 3.5)), "rust"))
    for zz, th in ((4.0, 0.07), (3.5, 0.05)):
        parts.append((create_box("House_FE_Rail", (3.0, 0.07, th),
                                 (2.0, 5.6, zz)), "rust"))
    fe_n = round(3.0 / STAIR_RISE)
    fe_x0 = -4.3
    for i in range(1, fe_n + 1):
        parts.append((create_box(
            f"HouseFE_Step{i:02d}",
            (STEP_DEPTH, STAIR_W, STAIR_RISE),
            (fe_x0 + (i - 0.5) * STEP_DEPTH, 4.8, i * STAIR_RISE - STAIR_RISE / 2.0),
        ), "rust"))
    fe_top = fe_x0 + fe_n * STEP_DEPTH
    parts.append((create_box(
        "HouseFE_SlopeRail",
        ((fe_top - fe_x0) / math.cos(STAIR_ANGLE) + 0.3, 0.06, 0.06),
        ((fe_x0 + fe_top) / 2.0, 5.55, 1.5 + 0.5),
        rotation=(0.0, -STAIR_ANGLE, 0.0),
    ), "rust"))
    for k in range(3):
        x_p = fe_x0 + 0.6 + k * 1.8
        z_p = (x_p - fe_x0) * math.tan(STAIR_ANGLE)
        parts.append((create_box("HouseFE_Post", (0.06, 0.06, 1.0),
                                 (x_p, 5.55, z_p + 0.5)), "rust"))

    # rusty metal gable roof (material covers top AND underside)
    pitch = math.radians(30.0)
    run = 4.4
    ridge_z = wall_top + run * math.tan(pitch)
    slab_len = run / math.cos(pitch) + 0.35
    for sy in (-1.0, 1.0):
        mid_y = sy * run / 2.0
        mid_z = ridge_z - (run / 2.0) * math.tan(pitch) - 0.15 / (2 * math.cos(pitch))
        parts.append((create_box(
            f"House_Roof_{'N' if sy > 0 else 'S'}",
            (w + 0.7, slab_len, 0.15),
            (0.0, mid_y, mid_z),
            rotation=(-sy * pitch, 0.0, 0.0),
        ), "rust"))
    parts.append((create_box("House_RidgeCap", (w + 0.7, 0.34, 0.14),
                             (0.0, 0.0, ridge_z + 0.02)), "rust"))
    apex = ridge_z - 0.12
    for sx in (-1.0, 1.0):
        parts.append((create_triangular_prism(
            f"House_Gable_{'E' if sx > 0 else 'W'}",
            sx * (w / 2 - t), sx * (w / 2),
            [(-d / 2 + 0.05, wall_top - 0.05), (d / 2 - 0.05, wall_top - 0.05),
             (0.0, apex)],
        ), "brick_red"))

    # furniture
    parts += add_bed("House_Bed", -2.6, -2.2, 3.0, rot_z=90)
    parts += add_table("House_Table", 2.6, 1.8, floor_z, rot_z=15)
    parts += add_crates("House_CrateA", 3.6, -2.6, floor_z, n=4, rng=rng)
    parts += add_crates("House_CrateB", -1.4, 2.6, 3.0, n=3, rng=rng)

    return finish_building(parts, "HouseTactical", "House", [
        ((2.4, 0.6, 2.35), 140.0),
        ((-1.5, 1.8, 5.3), 130.0),
    ])


def build_school_yellow():
    """2 storeys, 14 x 10 m — BRIGHT YELLOW concrete school; 32-degree stair
    with exact slab hole; flat roof (roof material on the underside)."""
    rng = random.Random(505)
    w, d = 14.0, 10.0
    t = 0.25
    slab_t = 0.20
    floor_z = slab_t
    s2_c, s2_t = 2.925, 0.15
    wall_top = 6.0

    parts = []
    parts += [
        (create_box("Sch_Base", (w - 0.02, d - 0.02, slab_t), (0.0, 0.0, slab_t / 2)),
         "concrete_dark"),
        (create_box("Sch_Slab2", (w - 0.02, d - 0.02, s2_t), (0.0, 0.0, s2_c)),
         "concrete_dark"),
        # flat roof — same concrete material top AND underside (Task 3)
        (create_box("Sch_Roof", (w - 0.02, d - 0.02, 0.15), (0.0, 0.0, 5.925)),
         "concrete"),
    ]

    walls = {
        "front": create_box("Sch_WallFront", (w - 2 * t, t, wall_top),
                            (0.0, -d / 2 + t / 2, wall_top / 2)),
        "back": create_box("Sch_WallBack", (w - 2 * t, t, wall_top),
                           (0.0, d / 2 - t / 2, wall_top / 2)),
        "left": create_box("Sch_WallLeft", (t, d, wall_top),
                           (-w / 2 + t / 2, 0.0, wall_top / 2)),
        "right": create_box("Sch_WallRight", (t, d, wall_top),
                            (w / 2 - t / 2, 0.0, wall_top / 2)),
    }
    parts += [(wt, "concrete_yellow") for wt in walls.values()]
    # parapet (yellow, like the facade)
    for size, loc in (
        ((w, t, 0.9), (0.0, -d / 2 + t / 2, 6.45)),
        ((w, t, 0.9), (0.0, d / 2 - t / 2, 6.45)),
        ((t, d - 2 * t, 0.9), (-w / 2 + t / 2, 0.0, 6.45)),
        ((t, d - 2 * t, 0.9), (w / 2 - t / 2, 0.0, 6.45)),
    ):
        parts.append((create_box("Sch_Parapet", size, loc), "concrete_yellow"))

    # corridor partition with a doorway per floor
    part = create_box("Sch_Partition", (0.2, d - 2 * t, wall_top - 0.15),
                      (2.5, 0.0, (0.15 + wall_top) / 2))
    for fz in (floor_z, 3.0):
        cut_door(part, (2.5, 1.0), (1, 0), 0.2, fz, 0.20 if fz < 1 else s2_t,
                 f"Sch_IntDoor{int(fz)}")
    parts.append((part, "concrete_yellow"))

    # stair: floor 1 -> floor 2 (lane A, +Y), hole in slab2
    steps, hole = stair_flight("SchStair", -5.95, -4.6, +1, floor_z, 3.0)
    cut_stair_hole(parts[1][0], hole, s2_c, s2_t)
    parts += [(s, "concrete_yellow") for s in steps]

    # doors (front & back)
    normals = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}
    fd = cut_door(walls["front"], (0.0, -d / 2 + t / 2), (0, -1), t,
                  floor_z, slab_t, "Sch_FrontDoor")
    parts.append((add_door_leaf(fd, (0, -1), t, DOOR_W, DOOR_H,
                                "Sch_FrontDoor", floor_z), "wood"))
    bd = cut_door(walls["back"], (0.0, d / 2 - t / 2), (0, 1), t,
                  floor_z, slab_t, "Sch_BackDoor")
    parts.append((add_door_leaf(bd, (0, 1), t, DOOR_W, DOOR_H,
                                "Sch_BackDoor", floor_z), "wood"))

    # windows: 8 per floor, sills 1.0 m above each floor
    specs = []
    for fz in (0.0, 3.0):
        specs += [
            ("front", -4.0, fz), ("front", 4.0, fz),
            ("back", -4.0, fz), ("back", 4.0, fz),
            ("left", -2.5, fz), ("left", 2.5, fz),
            ("right", -2.5, fz), ("right", 2.5, fz),
        ]
    for i, (wall, coord, fz) in enumerate(specs):
        n = normals[wall]
        if n[1] != 0:
            centre = (coord, -d / 2 + t / 2 if n[1] < 0 else d / 2 - t / 2)
        else:
            centre = (-w / 2 + t / 2 if n[0] < 0 else w / 2 - t / 2, coord)
        c = cut_opening(walls[wall], centre, n, t, WIN_W, WIN_H,
                        fz + WIN_SILL, f"Sch_Win{i}")
        parts += [(p, "wood") for p in add_shutters(c, n, t, f"Sch_Win{i}")]

    # classroom furniture: desks + crate stacks on both floors
    for (x, y) in ((-4.5, 2.5), (-4.5, 0.5), (-1.5, 2.5), (-1.5, 0.5)):
        parts += add_table(f"Sch_DeskG_{int(x)}_{int(y)}", x, y, floor_z, rot_z=0,
                           size=(1.5, 0.7))
    for (x, y) in ((-4.5, 2.5), (-4.5, -1.0), (4.5, 2.5), (4.5, -1.0)):
        parts += add_table(f"Sch_DeskU_{int(x)}_{int(y)}", x, y, 3.0, rot_z=0,
                           size=(1.5, 0.7))
    parts += add_crates("Sch_CrateG", 5.5, -3.5, floor_z, n=4, rng=rng)
    parts += add_crates("Sch_CrateU", 5.5, 3.6, 3.0, n=3, rng=rng)

    return finish_building(parts, "SchoolYellow", "Sch", [
        ((-3.0, -2.0, 2.35), 150.0),
        ((4.5, 2.0, 2.35), 140.0),
        ((-3.0, -2.0, 5.35), 140.0),
        ((4.5, 2.0, 5.35), 130.0),
    ])


def build_apartment_green():
    """3 storeys, 12 x 10 m — VIBRANT GREEN concrete; switchback stairs
    connect all 3 floors and the flat roof (exact 3 x 1.5 holes everywhere)."""
    rng = random.Random(202)
    w, d = 12.0, 10.0
    t = 0.25
    slab_t = 0.20
    floor_z = slab_t
    wall_top = 9.0
    s2_c, s3_c, rf_c = 2.925, 5.925, 8.925

    parts = []
    parts += [
        (create_box("Apt_Base", (w - 0.02, d - 0.02, 0.20), (0.0, 0.0, 0.10)),
         "concrete_dark"),
        (create_box("Apt_Slab2", (w - 0.02, d - 0.02, 0.15), (0.0, 0.0, s2_c)),
         "concrete_dark"),
        (create_box("Apt_Slab3", (w - 0.02, d - 0.02, 0.15), (0.0, 0.0, s3_c)),
         "concrete_dark"),
        # accessible flat roof — green concrete, underside included (Task 3)
        (create_box("Apt_RoofSlab", (w - 0.02, d - 0.02, 0.15), (0.0, 0.0, rf_c)),
         "concrete_green"),
    ]

    walls = {
        "front": create_box("Apt_WallFront", (w - 2 * t, t, wall_top),
                            (0.0, -d / 2 + t / 2, wall_top / 2)),
        "back": create_box("Apt_WallBack", (w - 2 * t, t, wall_top),
                           (0.0, d / 2 - t / 2, wall_top / 2)),
        "left": create_box("Apt_WallLeft", (t, d, wall_top),
                           (-w / 2 + t / 2, 0.0, wall_top / 2)),
        "right": create_box("Apt_WallRight", (t, d, wall_top),
                            (w / 2 - t / 2, 0.0, wall_top / 2)),
    }
    parts += [(wt, "concrete_green") for wt in walls.values()]

    for size, loc in (
        ((w, t, 0.9), (0.0, -d / 2 + t / 2, 9.45)),
        ((w, t, 0.9), (0.0, d / 2 - t / 2, 9.45)),
        ((t, d - 2 * t, 0.9), (-w / 2 + t / 2, 0.0, 9.45)),
        ((t, d - 2 * t, 0.9), (w / 2 - t / 2, 0.0, 9.45)),
    ):
        parts.append((create_box("Apt_Parapet", size, loc), "concrete_green"))

    part = create_box("Apt_Partition", (0.2, d - 2 * t, wall_top - 0.15),
                      (1.6, 0.0, (0.15 + wall_top) / 2))
    for fz, s_t in ((floor_z, 0.20), (3.0, 0.15), (6.0, 0.15)):
        cut_door(part, (1.6, 1.0), (1, 0), 0.2, fz, s_t, f"Apt_IntDoor{int(fz)}")
    parts.append((part, "concrete_green"))

    # three flights + one exact hole each (slab2, slab3, roof hatch)
    lane_a, lane_b = -4.9, -3.1
    fa, hole_a = stair_flight("AptStairA", lane_a, -4.6, +1, floor_z, 3.0)
    cut_stair_hole(parts[1][0], hole_a, s2_c, 0.15)
    fb, hole_b = stair_flight("AptStairB", lane_b, 0.05, -1, 3.0, 6.0)
    cut_stair_hole(parts[2][0], hole_b, s3_c, 0.15)
    fc, hole_c = stair_flight("AptStairC", lane_a, -0.12, +1, 6.0, 9.0)
    cut_stair_hole(parts[3][0], hole_c, rf_c, 0.15)
    parts += [(s, "concrete_green") for s in fa + fb + fc]

    normals = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}
    fd = cut_door(walls["front"], (0.0, -d / 2 + t / 2), (0, -1), t,
                  floor_z, 0.20, "Apt_FrontDoor")
    parts.append((add_door_leaf(fd, (0, -1), t, DOOR_W, DOOR_H,
                                "Apt_FrontDoor", floor_z), "wood"))

    specs = []
    for fz in (0.0, 3.0, 6.0):
        specs += [
            ("front", -3.4, fz), ("front", 3.4, fz),
            ("back", -3.4, fz), ("back", 3.4, fz),
            ("left", 0.0, fz), ("right", 0.0, fz),
        ]
    for i, (wall, coord, fz) in enumerate(specs):
        n = normals[wall]
        if n[1] != 0:
            centre = (coord, -d / 2 + t / 2 if n[1] < 0 else d / 2 - t / 2)
        else:
            centre = (-w / 2 + t / 2 if n[0] < 0 else w / 2 - t / 2, coord)
        c = cut_opening(walls[wall], centre, n, t, WIN_W, WIN_H,
                        fz + WIN_SILL, f"Apt_Win{i}")
        parts += [(p, "wood") for p in add_shutters(c, n, t, f"Apt_Win{i}")]

    parts += add_bed("Apt_Bed1", -1.5, 3.4, 3.0, rot_z=0)
    parts += add_bed("Apt_Bed2", -1.5, -3.4, 6.0, rot_z=180)
    parts += add_table("Apt_Table1", -1.8, -2.6, floor_z, rot_z=0)
    parts += add_table("Apt_Table2", -2.2, 2.4, 3.0, rot_z=90)
    parts += add_crates("Apt_Crate1", 4.4, -3.8, floor_z, n=4, rng=rng)
    parts += add_crates("Apt_Crate2", 4.4, 3.6, 6.0, n=3, rng=rng)

    lights = []
    for fz in (0.0, 3.0, 6.0):
        lights += [((-2.2, -2.6, fz + 2.35), 130.0),
                   ((4.0, 2.8, fz + 2.35), 110.0)]
    return finish_building(parts, "ApartmentGreen", "Apt", lights)


def build_cabin_wood():
    """1 storey, 8 x 6 m — WARM BROWN wood cabin, gable roof, porch, chimney."""
    rng = random.Random(606)
    w, d = 8.0, 6.0
    t = 0.20
    slab_t = 0.20
    floor_z = slab_t
    wall_top = 2.7

    parts = []
    parts.append((create_box("Cab_Floor", (w - 0.02, d - 0.02, slab_t),
                             (0.0, 0.0, slab_t / 2)), "wood_dark"))

    walls = {
        "front": create_box("Cab_WallFront", (w - 2 * t, t, wall_top),
                            (0.0, -d / 2 + t / 2, wall_top / 2)),
        "back": create_box("Cab_WallBack", (w - 2 * t, t, wall_top),
                           (0.0, d / 2 - t / 2, wall_top / 2)),
        "left": create_box("Cab_WallLeft", (t, d, wall_top),
                           (-w / 2 + t / 2, 0.0, wall_top / 2)),
        "right": create_box("Cab_WallRight", (t, d, wall_top),
                            (w / 2 - t / 2, 0.0, wall_top / 2)),
    }
    parts += [(wt, "wood_warm") for wt in walls.values()]

    # door + windows (sills at 1.0 m)
    normals = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}
    fd = cut_door(walls["front"], (0.0, -d / 2 + t / 2), (0, -1), t,
                  floor_z, slab_t, "Cab_Door")
    parts.append((add_door_leaf(fd, (0, -1), t, DOOR_W, DOOR_H,
                                "Cab_Door", floor_z), "wood"))
    win_specs = [("front", -2.5), ("front", 2.5), ("back", -2.5),
                 ("back", 2.5), ("left", 0.0), ("right", 0.0)]
    for i, (wall, coord) in enumerate(win_specs):
        n = normals[wall]
        if n[1] != 0:
            centre = (coord, -d / 2 + t / 2 if n[1] < 0 else d / 2 - t / 2)
        else:
            centre = (-w / 2 + t / 2 if n[0] < 0 else w / 2 - t / 2, coord)
        c = cut_opening(walls[wall], centre, n, t, WIN_W, WIN_H,
                        WIN_SILL, f"Cab_Win{i}")
        parts += [(p, "wood") for p in add_shutters(c, n, t, f"Cab_Win{i}")]

    # small porch
    parts.append((create_box("Cab_PorchDeck", (7.6, 1.55, 0.20),
                             (0.0, -3.825, 0.10)), "wood_warm"))
    for px in (-3.0, 3.0):
        parts.append((create_box("Cab_PorchPost", (0.14, 0.14, 2.3),
                                 (px, -4.5, 0.2 + 1.15)), "wood_warm"))
    parts.append((create_box("Cab_PorchRoof", (7.7, 1.7, 0.12),
                             (0.0, -3.9, 2.6)), "rust"))
    for x0, x1 in ((-3.8, -1.0), (1.0, 3.8)):
        parts.append((create_box("Cab_PorchRail", (x1 - x0, 0.08, 0.08),
                                 ((x0 + x1) / 2, -4.5, 1.1)), "wood_warm"))

    # gable roof (rusty metal, material on top AND underside)
    pitch = math.radians(30.0)
    run = 3.3
    ridge_z = wall_top + run * math.tan(pitch)
    slab_len = run / math.cos(pitch) + 0.30
    for sy in (-1.0, 1.0):
        mid_y = sy * run / 2.0
        mid_z = ridge_z - (run / 2.0) * math.tan(pitch) - 0.15 / (2 * math.cos(pitch))
        parts.append((create_box(
            f"Cab_Roof_{'N' if sy > 0 else 'S'}",
            (w + 0.6, slab_len, 0.15),
            (0.0, mid_y, mid_z),
            rotation=(-sy * pitch, 0.0, 0.0),
        ), "rust"))
    parts.append((create_box("Cab_RidgeCap", (w + 0.6, 0.3, 0.12),
                             (0.0, 0.0, ridge_z + 0.02)), "rust"))
    apex = ridge_z - 0.12
    for sx in (-1.0, 1.0):
        parts.append((create_triangular_prism(
            f"Cab_Gable_{'E' if sx > 0 else 'W'}",
            sx * (w / 2 - t), sx * (w / 2),
            [(-d / 2 + 0.05, wall_top - 0.05), (d / 2 - 0.05, wall_top - 0.05),
             (0.0, apex)],
        ), "wood_warm"))
    # brick chimney through the north slope
    parts.append((create_box("Cab_Chimney", (0.45, 0.45, 1.5),
                             (2.3, 1.4, 3.9)), "brick_red"))

    # interior
    parts += add_bed("Cab_Bed", 2.3, 1.6, floor_z, rot_z=180)
    parts += add_table("Cab_Table", -2.3, -1.4, floor_z, rot_z=-12)
    parts += add_crates("Cab_Crate", 3.1, -2.1, floor_z, n=3, rng=rng)

    return finish_building(parts, "CabinWood", "Cab", [
        ((0.0, 0.0, 2.45), 110.0),
    ])


def build_warehouse_metal():
    """1 storey, 20 x 12 m — STEEL-BLUE corrugated walls, RUSTY RED-ORANGE
    roof/beams, concrete floor, two open garage-door roll bundles."""
    rng = random.Random(303)
    w, d = 20.0, 12.0
    t = 0.30
    floor_t = 0.30
    floor_top = floor_t
    wall_top = 5.70

    parts = []
    parts.append((create_box("Wh_Floor", (w - 0.02, d - 0.02, floor_t),
                             (0.0, 0.0, floor_t / 2)), "concrete_dark"))

    walls = {
        "front": create_box("Wh_WallFront", (w - 2 * t, t, wall_top),
                            (0.0, -d / 2 + t / 2, wall_top / 2)),
        "back": create_box("Wh_WallBack", (w - 2 * t, t, wall_top),
                           (0.0, d / 2 - t / 2, wall_top / 2)),
        "left": create_box("Wh_WallLeft", (t, d, wall_top),
                           (-w / 2 + t / 2, 0.0, wall_top / 2)),
        "right": create_box("Wh_WallRight", (t, d, wall_top),
                            (w / 2 - t / 2, 0.0, wall_top / 2)),
    }
    parts += [(wt, "metal_steelblue") for wt in walls.values()]

    # rusty roof (material on top AND underside) + rusty beams
    parts.append((create_box("Wh_Roof", (w - 0.02, d - 0.02, 0.30),
                             (0.0, 0.0, wall_top + 0.15)), "rust_orange"))
    for bx in (-6.5, 0.0, 6.5):
        parts.append((create_box("Wh_Beam", (0.28, d - 2 * t, 0.42),
                                 (bx, 0.0, wall_top - 0.21)), "rust_orange"))

    # two large OPEN garage-door openings + rolled-up rusty bundles hanging
    # exactly across each opening (bundle width == opening width, x-aligned)
    for i, gx in enumerate((-4.9, 4.9)):
        cut_opening(walls["front"], (gx, -d / 2 + t / 2), (0, -1), t,
                    6.0, 4.5 + floor_top, 0.0, f"Wh_Garage{i}")
        parts.append((create_box(f"Wh_RollBundle{i}", (6.0, 0.55, 0.5),
                                 (gx, -d / 2 + t + 0.24,
                                  floor_top + 4.5 + 0.26)), "rust_orange"))

    # side personnel door (rusty leaf) + wooden shutters on windows
    pd = cut_door(walls["left"], (-w / 2 + t / 2, -2.0), (-1, 0), t,
                  floor_top, floor_t, "Wh_PersonDoor")
    parts.append((add_door_leaf(pd, (-1, 0), t, DOOR_W, DOOR_H,
                                "Wh_PersonDoor", floor_top), "rust_orange"))

    normals = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}
    specs = [
        ("right", -2.6, "Wh_WinR1"), ("right", 2.6, "Wh_WinR2"),
        ("back", -5.5, "Wh_WinB1"), ("back", 0.0, "Wh_WinB2"),
        ("back", 5.5, "Wh_WinB3"), ("front", 0.0, "Wh_WinF"),
    ]
    for wall, coord, tag in specs:
        n = normals[wall]
        if n[1] != 0:
            centre = (coord, -d / 2 + t / 2 if n[1] < 0 else d / 2 - t / 2)
        else:
            centre = (-w / 2 + t / 2 if n[0] < 0 else w / 2 - t / 2, coord)
        c = cut_opening(walls[wall], centre, n, t, WIN_W, WIN_H, WIN_SILL, tag)
        parts += [(p, "wood") for p in add_shutters(c, n, t, tag)]

    for (cx, cy, n) in ((-7.0, 3.4, 5), (7.2, 3.6, 4), (0.0, -3.6, 4),
                        (-7.5, -3.4, 3)):
        parts += add_crates(f"Wh_Crate{int(cx)}_{int(cy)}", cx, cy, floor_top,
                            n=n, rng=rng)
    parts += add_table("Wh_Table", 5.0, -4.0, floor_top, rot_z=-20, size=(1.8, 0.9))

    return finish_building(parts, "WarehouseMetal", "Wh", [
        ((-7.0, 0.0, 5.0), 220.0),
        ((7.0, 0.0, 5.0), 220.0),
        ((0.0, 0.0, 5.0), 220.0),
    ])


def build_ruined_building():
    """2 storeys, 10 x 8 m — darkened GREY concrete, BMesh face deletion,
    exposed rebar, rubble, bare doorway/window cutouts (no door leaf or
    window shutters), no intact roof."""
    rng = random.Random(404)
    w, d = 10.0, 8.0
    t = 0.25
    slab_t = 0.20
    floor_z = slab_t
    wall_top = 6.0
    s2_c, s2_t = 2.925, 0.15

    parts = []
    parts += [
        (create_box("Ruin_Base", (w - 0.02, d - 0.02, slab_t),
                    (0.0, 0.0, slab_t / 2)), "concrete_greydark"),
        (create_box("Ruin_Slab2", (w - 0.02, d - 0.02, s2_t),
                    (0.0, 0.0, s2_c)), "concrete_greydark"),
    ]
    roof = create_box("Ruin_RoofRemnant", (w - 0.02, d - 0.02, 0.15),
                      (0.0, 0.0, 5.925))

    walls = {
        "front": create_box("Ruin_WallFront", (w - 2 * t, t, wall_top),
                            (0.0, -d / 2 + t / 2, wall_top / 2)),
        "back": create_box("Ruin_WallBack", (w - 2 * t, t, wall_top),
                           (0.0, d / 2 - t / 2, wall_top / 2)),
        "left": create_box("Ruin_WallLeft", (t, d, wall_top),
                           (-w / 2 + t / 2, 0.0, wall_top / 2)),
        "right": create_box("Ruin_WallRight", (t, d, wall_top),
                            (w / 2 - t / 2, 0.0, wall_top / 2)),
    }

    # Bare doorway and window cutouts ONLY — no door leaf or window shutters
    # in the Ruined Building.
    normals = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}
    cut_door(walls["front"], (-1.5, -d / 2 + t / 2), (0, -1), t,
             floor_z, slab_t, "Ruin_Door")
    cut_door(walls["back"], (2.4, d / 2 - t / 2), (0, 1), t,
             floor_z, slab_t, "Ruin_BackDoor")

    specs = [
        ("front", 2.2, 0.0), ("right", -1.5, 0.0), ("right", 1.8, 0.0),
        ("back", -2.6, 0.0), ("left", 0.6, 0.0),
        ("front", -2.4, 3.0), ("back", 1.0, 3.0), ("left", -2.2, 3.0),
    ]
    for i, (wall, coord, fz) in enumerate(specs):
        n = normals[wall]
        if n[1] != 0:
            centre = (coord, -d / 2 + t / 2 if n[1] < 0 else d / 2 - t / 2)
        else:
            centre = (-w / 2 + t / 2 if n[0] < 0 else w / 2 - t / 2, coord)
        cut_opening(walls[wall], centre, n, t, WIN_W, WIN_H,
                    fz + WIN_SILL, f"Ruin_Win{i}")

    steps, hole = stair_flight("RuinStair", -3.95, -3.6, +1, floor_z, 3.0)
    cut_stair_hole(parts[1][0], hole, s2_c, s2_t)

    # BMesh destruction
    for i, wt in enumerate(walls.values()):
        destroy_faces(wt, p_bottom=0.30, p_top=0.88, keep="bottom",
                      seed=404 + i, cuts=5)
    destroy_faces(roof, p_bottom=0.72, p_top=0.72, keep="border",
                  seed=410, cuts=6)

    anchors = []
    for wt in walls.values():
        for v in wt.data.vertices:
            if v.co.z > 4.6:
                anchors.append((v.co.x, v.co.y, v.co.z))
    for v in roof.data.vertices:
        anchors.append((v.co.x, v.co.y, v.co.z))
    rods = add_rebar(anchors, rng, count=20)

    parts += [(wt, "concrete_greydark") for wt in walls.values()]
    parts.append((roof, "concrete_greydark"))
    parts += [(s, "concrete_greydark") for s in steps]
    parts += [(r, "rust") for r in rods]
    parts += add_rubble_pile("Ruin_RubbleA", 3.0, 2.4, floor_z, 7, rng)
    parts += add_rubble_pile("Ruin_RubbleB", -3.2, -3.0, floor_z, 5, rng)
    parts += add_rubble_pile("Ruin_RubbleC", 2.8, -3.2, floor_z, 5, rng)
    parts += add_rubble_pile("Ruin_RubbleUp", 3.2, 2.6, 3.0, 5, rng)
    parts += add_crates("Ruin_Crate", 4.0, 0.8, floor_z, n=3, rng=rng)
    parts += add_table("Ruin_Table", -3.6, 2.4, floor_z, rot_z=35)

    return finish_building(parts, "RuinedBuilding", "Ruin", [
        ((-1.0, 1.5, 2.3), 120.0),
        ((1.0, -1.0, 5.2), 90.0),
    ])


# ---------------------------------------------------------------------------
# TASK 1 — base terrain
# ---------------------------------------------------------------------------
def build_base_ground():
    bpy.ops.mesh.primitive_plane_add(size=100.0, location=(0.0, 0.0, 0.0))
    ground = bpy.context.active_object
    ground.name = "BaseGround"
    ground.data.name = "BaseGroundMesh"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    smart_unwrap(ground, density_for("grass"))
    assign_material(ground, make_material("Ground_Grass", "grass"))
    return ground


# ---------------------------------------------------------------------------
# Hero scene
# ---------------------------------------------------------------------------
def build_hero_scene():
    ensure_hero_ground_texture()
    ground = create_box("Hero_Ground", (100.0, 100.0, 0.4), (0.0, 0.0, -0.2))
    set_hero_ground_uvs(ground)                    # exact world UVs + warp
    assign_material(ground, make_material("Hero_GroundGrass", "grass_hero"))

    builders = [
        ("house_tactical", build_house_tactical),
        ("apartment_green", build_apartment_green),
        ("school_yellow", build_school_yellow),
        ("cabin_wood", build_cabin_wood),
        ("warehouse_metal", build_warehouse_metal),
        ("ruined_building", build_ruined_building),
    ]
    placed = []
    for name, builder in builders:
        x, y, rot = HERO_SPOTS[name]
        obj = builder()
        obj.location = (x, y, 0.0)
        obj.rotation_euler = (0.0, 0.0, math.radians(rot))
        placed.append(obj)
    return [ground] + placed


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------
def export_glb(path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    kwargs = dict(
        filepath=path,
        export_format="GLB",
        export_image_format="JPEG",
        export_lights=True,
    )
    try:
        bpy.ops.export_scene.gltf(export_image_quality=90, **kwargs)
    except TypeError:
        bpy.ops.export_scene.gltf(**kwargs)
    if not os.path.isfile(path):
        raise RuntimeError(f"Export failed, file not written: {path}")
    return path


def verify_glb(path: str) -> dict:
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"glTF":
        raise RuntimeError(f"Not a GLB file: {path}")
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_len])
    images = gltf.get("images", [])
    if not images:
        raise RuntimeError(f"No packed images found in {path}")
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
    lights = sum(
        1 for node in gltf.get("nodes", [])
        if "KHR_lights_punctual" in node.get("extensions", {})
    )
    mapped = 0
    for mat in gltf.get("materials", []):
        tex = mat.get("pbrMetallicRoughness", {}).get("baseColorTexture")
        if tex and "KHR_texture_transform" in tex.get("extensions", {}):
            mapped += 1
    stats = {
        "bytes": os.path.getsize(path),
        "materials": len(gltf.get("materials", [])),
        "images": len(images),
        "tris": tris,
        "lights": lights,
        "mapped": mapped,
    }
    print(
        f"  verified {os.path.basename(path)}: {stats['bytes']} bytes, "
        f"{stats['materials']} material(s) ({stats['mapped']} with Mapping 0.3), "
        f"{stats['images']} packed image(s), ~{stats['tris']} tris, "
        f"{stats['lights']} light(s)"
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
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    print(f"Blender (bpy) version: {bpy.app.version_string}")
    print(f"Stair math: rise={STAIR_RISE} m, angle=32deg, "
          f"step depth=rise/tan(32°)={STEP_DEPTH:.4f} m, hole={HOLE_LEN}x{STAIR_W} m")
    print(f"UV chain: TexCoord -> Mapping({MAP_SCALE}) -> ImageTexture(REPEAT) "
          f"-> BaseColor; density normalised per object (no stretching)")

    print("Ensuring procedural textures ...")
    os.makedirs(TEXTURE_DIR, exist_ok=True)
    ensure_grass_texture()
    ensure_rust_texture()
    ensure_tint_textures()
    ensure_hero_ground_texture()

    failures = []

    def run(label, path, builder, expect_lights=True, expect_mapped=True):
        print(f"Building {label} ...")
        try:
            clear_scene()
            set_metric_units()
            obj = builder()
            report(obj, label)
            export_glb(path)
            stats = verify_glb(path)
            if expect_lights and stats["lights"] < 1:
                raise RuntimeError("no exported lights in GLB")
            if expect_mapped and stats["mapped"] < 1:
                raise RuntimeError("Mapping(KHR_texture_transform) missing in GLB")
            return stats
        except Exception as exc:
            failures.append((label, exc))
            print(f"  FAILED {label}: {exc!r}")
            return None

    run("base_ground.glb", os.path.join(TERRAIN_DIR, "base_ground.glb"),
        build_base_ground, expect_lights=False)
    run("house_tactical.glb", os.path.join(BUILDINGS_DIR, "house_tactical.glb"),
        build_house_tactical)
    run("school_yellow.glb", os.path.join(BUILDINGS_DIR, "school_yellow.glb"),
        build_school_yellow)
    run("apartment_green.glb", os.path.join(BUILDINGS_DIR, "apartment_green.glb"),
        build_apartment_green)
    run("cabin_wood.glb", os.path.join(BUILDINGS_DIR, "cabin_wood.glb"),
        build_cabin_wood)
    run("warehouse_metal.glb", os.path.join(BUILDINGS_DIR, "warehouse_metal.glb"),
        build_warehouse_metal)
    run("ruined_building.glb", os.path.join(BUILDINGS_DIR, "ruined_building.glb"),
        build_ruined_building)

    print("Building scene_phase1.glb (hero: ground + 6 buildings) ...")
    try:
        clear_scene()
        set_metric_units()
        objs = build_hero_scene()
        for o in objs:
            report(o, o.name)
        hero_path = os.path.join(MODELS_DIR, "scene_phase1.glb")
        export_glb(hero_path)
        verify_glb(hero_path)
    except Exception as exc:
        failures.append(("scene_phase1.glb", exc))
        print(f"  FAILED scene_phase1.glb: {exc!r}")

    if failures:
        print(f"\n{len(failures)} task(s) failed:")
        for label, exc in failures:
            print(f"  - {label}: {exc!r}")
        return 1
    print("Done — colourful Phase 1 assets generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
