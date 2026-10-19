#!/usr/bin/env python3
"""Phase 1 asset generator for the Indus : Battle Royale 3D pipeline.

Runs headless through the pip-installable ``bpy`` module (Blender as a Python
module) and generates the Phase 1 asset set:

TERRAIN
    ``base_ground.glb``  — 100 m x 100 m flat grass plane (origin = surface centre)

BUILDINGS (strict rules, see below)
    ``house_tactical.glb``       — 2 storeys, 10 x 8 m, brick walls, wooden porch,
                                   balcony, rusty metal gable roof, back fire escape
    ``apartment_multifloor.glb`` — 3 storeys, 12 x 10 m, concrete, internal stairs
                                   connecting all 3 floors AND the flat roof
    ``warehouse_metal.glb``      — 1 storey, 20 x 12 m, corrugated metal walls,
                                   two large open garage doors, concrete floor
    ``ruined_building.glb``      — 2 storeys, 10 x 8 m, heavily destroyed with
                                   BMesh face deletion, exposed rebar, rubble

HERO SCENE (web preview)
    ``scene_phase1.glb``         — the 100 m ground with all four buildings placed
                                   on it and soft ground shadows baked into the
                                   terrain texture

CRITICAL RULES ENFORCED FOR EVERY BUILDING
------------------------------------------
* Stairs use trigonometry: ``step_depth = rise / math.tan(math.radians(32))``
  so every flight climbs at exactly 32 degrees.  Each flight gets a Boolean
  Difference hole of exactly 3.0 m x 1.5 m in the slab above it — the hole
  spans the final 3.0 m of run before the stair top (the head-room swept
  volume at 32 degrees) — and the stairs are placed exactly there.
* Passable openings: doors are 1.5 m W x 2.2 m H, windows are 1.2 m x 1.2 m
  with the sill at 1.0 m above the floor.  Cutter objects are always removed.
  No glass and no collision blockers are added to any hole.  Every outside
  window gets open wooden shutters; doors get an open door leaf.
* Interiors: internal floor slabs, ceilings, simple furniture (bed, table,
  crates) for cover, and OmniLights (point lights -> KHR_lights_punctual).
* Poly counts stay low (plain boxes + boolean cuts) for 4 GB RAM mobiles.

Procedural textures generated on first run (committed to docs/textures/):
    grass.png        — seamless FFT-noise grass (1024²)
    metal_rusted.png — corrugated metal graded to rust for gable/fire escape
    grass_hero.png   — grass with the four building shadows baked in (hero scene)

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
STAIR_RISE = 0.20                                   # riser height, metres
STAIR_ANGLE = math.radians(32.0)
# step depth (tread run) from the 32 degree incline: depth = rise / tan(32°)
STEP_DEPTH = STAIR_RISE / math.tan(STAIR_ANGLE)     # ≈ 0.3200 m
STAIR_W = 1.5                                       # stair width (hole width too)
HOLE_LEN = 3.0                                      # floor-slab hole length (rule)
HOLE_CLEAR = 0.04                                   # boolean clearance around steps

DOOR_W, DOOR_H = 1.5, 2.2
WIN_W, WIN_H, WIN_SILL = 1.2, 1.2, 1.0

# --- Hero layout (shared by the scene builder and the baked-shadow texture) -
HERO_SPOTS = {
    # name: (x, y, rotation_degrees)
    "house_tactical": (-24.0, 14.0, 20.0),
    "apartment_multifloor": (16.0, 16.0, -15.0),
    "warehouse_metal": (-6.0, -22.0, 0.0),
    "ruined_building": (24.0, -20.0, 30.0),
}
HERO_SHADOW_DIR = (1.0, 0.62)          # baked shadow direction (sun from opposite)
HERO_FOOTPRINTS = {                    # (width, depth) of each building
    "house_tactical": (10.0, 8.0),
    "apartment_multifloor": (12.0, 10.0),
    "warehouse_metal": (20.0, 12.0),
    "ruined_building": (10.0, 8.0),
}

# --- Material presets -------------------------------------------------------
MATERIALS = {
    "concrete": {"file": "concrete_wall.png", "roughness": 0.90, "metallic": 0.00, "uv_scale": 1.0},
    "wood": {"file": "wood_plank.png", "roughness": 0.72, "metallic": 0.00, "uv_scale": 1.0},
    "brick": {"file": "brick_wall.png", "roughness": 0.85, "metallic": 0.00, "uv_scale": 2.5},
    "metal": {"file": "metal_corrugated.png", "roughness": 0.50, "metallic": 0.70, "uv_scale": 1.5},
    "rust": {"file": "metal_rusted.png", "roughness": 0.78, "metallic": 0.45, "uv_scale": 1.5},
    "grass": {"file": "grass.png", "roughness": 0.95, "metallic": 0.00, "uv_scale": 25.0},
    "grass_hero": {"file": "grass_hero.png", "roughness": 0.95, "metallic": 0.00, "uv_scale": 1.0},
}

_MATERIAL_CACHE: dict[str, object] = {}


# ---------------------------------------------------------------------------
# Procedural texture generation (numpy + Pillow, seamless by construction)
# ---------------------------------------------------------------------------
def _fft_noise(size: int, cutoff: float, seed: int) -> np.ndarray:
    """Periodic (perfectly tileable) Gaussian noise field via FFT low-pass."""
    rng = np.random.default_rng(seed)
    spectrum = np.fft.fft2(rng.normal(size=(size, size)))
    fy = np.fft.fftfreq(size)[:, None]
    fx = np.fft.fftfreq(size)[None, :]
    radius = np.sqrt(fx ** 2 + fy ** 2)
    spectrum *= np.exp(-((radius / cutoff) ** 2))     # Gaussian low-pass => periodic
    field = np.real(np.fft.ifft2(spectrum))
    field -= field.mean()
    field /= field.std() + 1e-9
    return field


def _lerp_rgb(c0, c1, t):
    c0 = np.asarray(c0, dtype=np.float64)
    c1 = np.asarray(c1, dtype=np.float64)
    return c0[None, None, :] + (c1 - c0)[None, None, :] * t[..., None]


def ensure_grass_texture() -> None:
    """Seamless 1024x1024 grass: layered FFT noise mapped through a green ramp."""
    path = os.path.join(TEXTURE_DIR, "grass.png")
    if os.path.isfile(path):
        return
    from PIL import Image

    size = 1024
    patches = _fft_noise(size, 0.012, seed=11)   # broad light/dry patches
    clumps = _fft_noise(size, 0.05, seed=12)     # clump texture
    blades = _fft_noise(size, 0.25, seed=13)     # fine blade grain
    fine = _fft_noise(size, 0.9, seed=14)        # per-pixel speckle
    g = 0.5 * patches + 0.32 * clumps + 0.30 * blades + 0.16 * fine
    g /= 1.05

    t = np.clip(0.5 + 0.30 * g, 0.0, 1.0)                        # green ramp pos
    col = _lerp_rgb((0.10, 0.20, 0.07), (0.24, 0.42, 0.14), t)   # dark -> lush green
    dry_t = np.clip(0.5 + 0.5 * patches, 0.0, 1.0)
    dry_strength = np.clip(0.5 + 0.42 * patches - 0.32, 0.0, 1.0) ** 2
    dry_col = _lerp_rgb((0.40, 0.43, 0.18), (0.52, 0.47, 0.22), dry_t)
    col = col * (1.0 - dry_strength[..., None]) + dry_col * dry_strength[..., None]
    col += 0.05 * fine[..., None]                                # grain
    col = np.clip(col, 0.0, 1.0)
    Image.fromarray((col * 255).astype(np.uint8), "RGB").save(path, "PNG")
    print(f"  generated texture {os.path.basename(path)}")


def ensure_rust_texture() -> None:
    """Rusty corrugated metal derived from metal_corrugated.png (seamless)."""
    from PIL import Image

    src = os.path.join(TEXTURE_DIR, "metal_corrugated.png")
    dst = os.path.join(TEXTURE_DIR, "metal_rusted.png")
    if os.path.isfile(dst) or not os.path.isfile(src):
        return
    img = np.asarray(Image.open(src).convert("RGB"), dtype=np.float64) / 255.0
    size = img.shape[0]
    patch_n = _fft_noise(size, 0.02, seed=21)
    spot_n = _fft_noise(size, 0.09, seed=22)
    mask = np.clip(0.5 + 0.55 * patch_n + 0.30 * spot_n, 0.0, 1.0)
    mask = np.clip((mask - 0.45) * 2.4, 0.0, 1.0) * 0.88          # rust patch strength
    rust = _lerp_rgb((0.44, 0.20, 0.08), (0.30, 0.13, 0.05),
                     np.clip(0.5 + 0.3 * spot_n, 0, 1))
    out = img * (1.0 - mask[..., None]) + rust * mask[..., None]
    mean = out.mean()
    out = np.clip((out - mean) * 1.08 + 0.36, 0.0, 1.0)           # keep albedo in line
    Image.fromarray((out * 255).astype(np.uint8), "RGB").save(dst, "PNG")
    print(f"  generated texture {os.path.basename(dst)}")


def ensure_hero_ground_texture() -> None:
    """Grass with soft multiplicative shadows of the four buildings baked in.

    The hero scene uses a single non-tiled 100 m UV square, so the shadows can
    be painted at exact world positions — no transparent decals needed (keeps
    JPEG packing intact).
    """
    from PIL import Image

    ensure_grass_texture()
    dst = os.path.join(TEXTURE_DIR, "grass_hero.png")
    if os.path.isfile(dst):
        return
    grass = np.asarray(
        Image.open(os.path.join(TEXTURE_DIR, "grass.png")).convert("RGB"),
        dtype=np.float64,
    ) / 255.0
    size = grass.shape[0]

    # world coordinates of every pixel (ground spans -50..50 m, UV y up = +y)
    lin = np.linspace(-50.0, 50.0, size)
    wx, wy = np.meshgrid(lin, lin)
    shade = np.ones((size, size), dtype=np.float64)

    sx, sy = HERO_SHADOW_DIR
    snorm = math.hypot(sx, sy)
    sx, sy = sx / snorm, sy / snorm

    for name, (cx, cy, rot_deg) in HERO_SPOTS.items():
        w, d = HERO_FOOTPRINTS[name]
        # shadow offset: elongated away from the sun, scaled with building size
        off = 0.16 * (w + d) * 0.5 + 1.1
        px = wx - (cx + sx * off)
        py = wy - (cy + sy * off)
        a = math.radians(-rot_deg)
        lx = px * math.cos(a) - py * math.sin(a)
        ly = px * math.sin(a) + py * math.cos(a)
        # rounded-rect signed distance outside the footprint
        bx, by = w * 0.5 + 0.4, d * 0.5 + 0.4
        ex = np.maximum(np.abs(lx) - bx + 0.7, 0.0)
        ey = np.maximum(np.abs(ly) - by + 0.7, 0.0)
        dist = np.maximum(np.sqrt(ex ** 2 + ey ** 2) - 0.7, 0.0)   # rounded corners
        falloff = np.exp(-((dist / 1.35) ** 2))                    # soft ~1.4 m edge
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
    """Create a box of ``size`` (x, y, z metres) with all transforms baked in."""
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "Mesh"
    obj.dimensions = tuple(size)
    obj.rotation_euler = rotation
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj


def create_triangular_prism(name, x_min, x_max, tri_yz):
    """Triangular prism (gable end): triangle ``tri_yz`` extruded along x."""
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
    """Boolean DIFFERENCE of ``cutter`` out of ``target``, then REMOVE the cutter."""
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
    """UV-unwrap with bpy.ops.uv.smart_project() and orient wall textures upright."""
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
    if uv_scale != 1.0:
        for layer in obj.data.uv_layers:
            for loop_uv in layer.data:
                loop_uv.uv = loop_uv.uv * uv_scale

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


def make_material(name: str, preset: str):
    """Principled BSDF + Image Texture -> Base Color (cached per scene run)."""
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

    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.name = f"{name}_Texture"
    tex.label = spec["file"]
    tex.image = image
    tex.extension = "REPEAT"
    tex.location = (-350.0, 220.0)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])

    bsdf.inputs["Roughness"].default_value = spec["roughness"]
    bsdf.inputs["Metallic"].default_value = spec["metallic"]
    _MATERIAL_CACHE[cache_key] = mat
    return mat


def make_solid_material(name: str, rgba, roughness: float = 0.85, metallic: float = 0.0):
    """Plain-colour Principled material (mattress, pillow, …)."""
    if name in _MATERIAL_CACHE:
        return _MATERIAL_CACHE[name]
    mat = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = tuple(rgba)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    _MATERIAL_CACHE[name] = mat
    return mat


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
    """Shift mesh data so bbox bottom-centre sits at the object origin (0,0,0)."""
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
    """Warm interior OmniLight (point light -> KHR_lights_punctual on export)."""
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
    """One 32-degree flight along Y from ``base_z`` up to ``target_z``.

    ``step_depth = rise / tan(32°)`` (critical rule); the number of risers is
    derived so the top tread sits flush with the target slab top.  Returns
    (step_boxes, hole): ``hole`` is the exact 3.0 m x 1.5 m region to cut out
    of the slab above — the final 3.0 m of run before the stair top, i.e. the
    head-room swept volume at 32 degrees.
    """
    rise = STAIR_RISE
    n = round((target_z - base_z) / rise)
    if abs(base_z + n * rise - target_z) > 1e-6:
        raise ValueError(
            f"{name}: floor height {target_z - base_z} is not a multiple of the "
            f"riser {rise}"
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
    """Boolean Difference: 3 m x 1.5 m hole in the slab above a stair flight."""
    cutter = create_box(
        "StairHoleCutter",
        (hole["width"], hole["length"], slab_thickness + 1.0),
        (hole["x"], hole["y_center"], slab_center_z),
    )
    apply_boolean_cut(slab, cutter)


def cut_opening(target, center, outward, wall_t: float, w: float, h: float,
                bottom_z: float, tag: str):
    """Cut a rectangular opening through an axis-aligned wall; removes cutter.

    ``outward`` is the wall's outward normal (axis aligned). Returns the
    opening centre (Vector).
    """
    cx, cy = center
    cz = bottom_z + h / 2.0
    if abs(outward[1]) > 0.5:            # front/back wall (normal along Y)
        size = (w, wall_t + 0.8, h)
    else:                                 # side wall (normal along X)
        size = (wall_t + 0.8, w, h)
    cutter = create_box(f"{tag}_Cutter", size, (cx, cy, cz))
    apply_boolean_cut(target, cutter)
    return Vector((cx, cy, cz))


def cut_door(target, center, outward, wall_t: float, floor_top: float,
             slab_t: float, tag: str):
    """Door opening 1.5 m W x 2.2 m H above ``floor_top``.

    The cutter is extended down through the floor slab band so no wall strip
    is left poking through the (visually flush) floor — the opening itself
    still measures exactly 2.2 m above the floor.
    """
    cut_bottom = floor_top - slab_t
    h = DOOR_H + (floor_top - cut_bottom)
    return cut_opening(target, center, outward, wall_t, DOOR_W, h, cut_bottom, tag)


def add_shutters(opening_center, outward, wall_t: float, tag: str,
                 damaged: bool = False):
    """Two open wooden shutter panels hinged at a window's outer edges."""
    n = Vector((float(outward[0]), float(outward[1]), 0.0)).normalized()
    t = Vector((-n.y, n.x, 0.0))                     # tangent along the wall
    hinge_base = (Vector((opening_center.x, opening_center.y, opening_center.z))
                  + n * (wall_t / 2.0 + 0.045))
    swing = math.radians(105.0 if not damaged else 128.0)
    panels = []
    for side in (-1.0, 1.0):                         # -1 = left edge, +1 = right edge
        hinge = hinge_base + t * (side * (WIN_W / 2.0 + 0.01))
        closed_dir = -t * side                       # points toward window centre
        v = closed_dir * math.cos(swing) + n * math.sin(swing)
        centre = hinge + v * (WIN_W / 2.0 + 0.01)
        yaw = math.atan2(v.y, v.x)
        roll = math.radians(6.0) if damaged else 0.0
        panel = create_box(
            f"{tag}_Shutter_{'L' if side < 0 else 'R'}",
            (WIN_W / 2.0 + 0.02, 0.045, WIN_H + 0.04),
            (centre.x, centre.y, opening_center.z),
            rotation=(roll, 0.0, yaw),
        )
        panels.append(panel)
    return panels


def add_door_leaf(opening_center, outward, wall_t: float, door_w: float,
                  door_h: float, tag: str, bottom_z: float,
                  damaged: bool = False):
    """One open door leaf hinged at the door's edge (swung outward)."""
    n = Vector((float(outward[0]), float(outward[1]), 0.0)).normalized()
    t = Vector((-n.y, n.x, 0.0))
    hinge = (Vector((opening_center.x, opening_center.y, 0.0))
             + t * (door_w / 2.0) + n * (wall_t / 2.0 + 0.05))
    swing = math.radians(112.0 if not damaged else 138.0)
    v = -t * math.cos(swing) + n * math.sin(swing)
    centre = hinge + v * (door_w / 2.0)
    yaw = math.atan2(v.y, v.x)
    roll = math.radians(10.0) if damaged else 0.0
    return create_box(
        f"{tag}_Leaf",
        (door_w, 0.05, door_h - 0.04),
        (centre.x, centre.y, bottom_z + (door_h - 0.04) / 2.0),
        rotation=(roll, 0.0, yaw),
    )


def add_bed(prefix: str, x: float, y: float, floor_z: float, rot_z: float = 0.0):
    """Simple bed: wooden frame + mattress + pillow (cover furniture)."""
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
    """Table: top + four legs."""
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
    """Stack of wooden crates for cover."""
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
                    rng: random.Random):
    """Scattered broken-concrete chunks (boxes) for the ruined building."""
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
        ), "concrete"))
    return parts


def _face_components(bm):
    """Connected components of faces (linked through shared edges)."""
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
    """BMesh destruction: subdivide, delete random faces (weighted by height),
    then keep only components that are grounded (``keep='bottom'``) or that
    touch the slab border (``keep='border'``) so no debris floats in the air.
    """
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
        else:  # border of the slab (sits on the walls below)
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
    """Thin exposed reinforcement bars sticking out of broken edges."""
    rods = []
    if not anchors:
        return rods
    for i in range(count):
        ax, ay, az = anchors[rng.randrange(len(anchors))]
        length = rng.uniform(0.5, 1.1)
        if rng.random() < 0.65:                       # sticking up / tilted
            rot = (math.radians(rng.uniform(-30, 30)),
                   math.radians(rng.uniform(-30, 30)),
                   math.radians(rng.uniform(0, math.pi)))
            loc = (ax + rng.uniform(-0.15, 0.15),
                   ay + rng.uniform(-0.15, 0.15),
                   az + length * 0.35)
            size = (0.035, 0.035, length)
        else:                                          # bent flat on the slab
            rot = (0.0, 0.0, math.radians(rng.uniform(0, math.pi)))
            loc = (ax + rng.uniform(-0.5, 0.5), ay + rng.uniform(-0.5, 0.5),
                   az + 0.04)
            size = (length, 0.035, 0.035)
        rods.append(create_box(f"Rebar_{i:02d}", size, loc, rotation=rot))
    return rods


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------
def export_glb(path: str) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    kwargs = dict(
        filepath=path,
        export_format="GLB",
        export_image_format="JPEG",   # textures converted + packed into the GLB
        export_lights=True,           # OmniLights -> KHR_lights_punctual
    )
    try:
        bpy.ops.export_scene.gltf(export_image_quality=90, **kwargs)
    except TypeError:
        bpy.ops.export_scene.gltf(**kwargs)
    if not os.path.isfile(path):
        raise RuntimeError(f"Export failed, file not written: {path}")
    return path


def verify_glb(path: str) -> dict:
    """Sanity-check the GLB: packed textures + meshes (+ lights where expected)."""
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
    lights = 0
    for node in gltf.get("nodes", []):
        if "KHR_lights_punctual" in node.get("extensions", {}):
            lights += 1
    stats = {
        "bytes": os.path.getsize(path),
        "materials": len(gltf.get("materials", [])),
        "images": len(images),
        "tris": tris,
        "lights": lights,
    }
    print(
        f"  verified {os.path.basename(path)}: {stats['bytes']} bytes, "
        f"{stats['materials']} material(s), {stats['images']} packed image(s), "
        f"~{stats['tris']} tris, {stats['lights']} light(s)"
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
# TASK 1 — base terrain: 100 x 100 m flat grass plane
# ---------------------------------------------------------------------------
def build_base_ground():
    bpy.ops.mesh.primitive_plane_add(size=100.0, location=(0.0, 0.0, 0.0))
    ground = bpy.context.active_object
    ground.name = "BaseGround"
    ground.data.name = "BaseGroundMesh"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    smart_unwrap(ground, MATERIALS["grass"]["uv_scale"])
    assign_material(ground, make_material("Ground_Grass", "grass"))
    # origin already sits on the ground surface centre (0, 0, 0)
    return ground


# ---------------------------------------------------------------------------
# TASK 2 — buildings
# ---------------------------------------------------------------------------
def build_house_tactical():
    """2 storeys, 10 x 8 m: brick walls, wooden porch, balcony, rusty metal
    gable roof, back fire escape — fully accessible."""
    rng = random.Random(101)
    w, d = 10.0, 8.0
    t = 0.25
    slab_t = 0.20               # base slab 0..0.2
    floor_z = slab_t            # interior ground floor top
    s2_c, s2_t = 2.925, 0.15    # slab2 spans 2.85..3.0
    ceil_c = 5.925              # ceiling slab spans 5.85..6.0
    wall_top = 6.0

    shell, woodwork, metalwork = [], [], []

    # --- base + floor slabs (inset 1 cm so faces never go coplanar) --------
    base = create_box("House_Base", (w - 0.02, d - 0.02, slab_t), (0.0, 0.0, slab_t / 2))
    slab2 = create_box("House_Slab2", (w - 0.02, d - 0.02, s2_t), (0.0, 0.0, s2_c))
    ceiling = create_box("House_Ceiling", (w - 0.02, d - 0.02, 0.15), (0.0, 0.0, ceil_c))
    shell += [(base, "concrete"), (slab2, "wood"), (ceiling, "wood")]

    # --- exterior walls (full height, brick) ------------------------------
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
    for wt in walls.values():
        shell.append((wt, "brick"))

    # --- interior partition (cover) with a doorway per floor --------------
    part = create_box("House_Partition", (0.18, 4.3, wall_top - 0.15),
                      (0.6, -1.6, (0.15 + wall_top) / 2))
    cut_door(part, (0.6, -2.6), (1, 0), 0.18, floor_z, slab_t, "House_IntDoor1")
    cut_door(part, (0.6, -2.6), (1, 0), 0.18, 3.0, s2_t, "House_IntDoor2")
    shell.append((part, "brick"))

    # --- stairs: 32-degree flight, ground -> slab2, hole cut exactly there -
    lane_x = -3.95
    steps, hole = stair_flight("HouseStair", lane_x, -3.6, +1, floor_z, 3.0)
    cut_stair_hole(slab2, hole, s2_c, s2_t)
    for s in steps:
        woodwork.append((s, "wood"))

    # --- doors (exact 1.5 x 2.2 above the floor, cutter removed) -----------
    normals = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}
    fd = cut_door(walls["front"], (1.0, -d / 2 + t / 2), (0, -1), t,
                  floor_z, slab_t, "House_FrontDoor")
    woodwork.append((add_door_leaf(fd, (0, -1), t, DOOR_W, DOOR_H,
                                   "House_FrontDoor", floor_z), "wood"))
    bd = cut_door(walls["back"], (2.6, d / 2 - t / 2), (0, 1), t,
                  floor_z, slab_t, "House_BackDoor")
    woodwork.append((add_door_leaf(bd, (0, 1), t, DOOR_W, DOOR_H,
                                   "House_BackDoor", floor_z), "wood"))
    # floor-2 door onto the fire-escape landing (flush with slab2 top)
    fe = cut_door(walls["back"], (2.0, d / 2 - t / 2), (0, 1), t,
                  3.0, s2_t, "House_FireDoor")
    woodwork.append((add_door_leaf(fe, (0, 1), t, DOOR_W, DOOR_H,
                                   "House_FireDoor", 3.0), "rust"))
    # floor-2 door onto the balcony
    bd2 = cut_door(walls["front"], (1.5, -d / 2 + t / 2), (0, -1), t,
                   3.0, s2_t, "House_BalconyDoor")
    woodwork.append((add_door_leaf(bd2, (0, -1), t, DOOR_W, DOOR_H,
                                   "House_BalconyDoor", 3.0), "wood"))

    # --- windows (1.2 x 1.2, sill 1.0 m above each floor) + shutters ------
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
        for panel in add_shutters(c, n, t, f"House_Win{i}"):
            woodwork.append((panel, "wood"))

    # --- wooden porch (deck flush with the interior floor) ----------------
    porch = create_box("House_PorchDeck", (9.8, 2.05, 0.20), (0.0, -4.975, 0.10))
    woodwork.append((porch, "wood"))
    for i, px in enumerate((-4.4, -1.6, 1.6, 4.4)):
        post = create_box(f"House_PorchPost{i}", (0.15, 0.15, 2.35),
                          (px, -5.9, 0.2 + 2.35 / 2))
        woodwork.append((post, "wood"))
    awning = create_box("House_PorchRoof", (9.9, 2.3, 0.12), (0.0, -5.1, 2.6))
    metalwork.append((awning, "rust"))
    # porch railing with a gap in front of the door
    for x0, x1 in ((-4.9, -0.1), (2.1, 4.9)):
        rail = create_box("House_PorchRail", (x1 - x0, 0.08, 0.08),
                          ((x0 + x1) / 2, -5.95, 1.1))
        woodwork.append((rail, "wood"))
    for px in (-4.85, -3.2, -1.5, 2.6, 3.6, 4.85):
        p = create_box("House_PorchBal", (0.07, 0.07, 0.9), (px, -5.95, 0.65))
        woodwork.append((p, "wood"))

    # --- balcony (floor 2, front; deck embedded 5 cm into the wall) -------
    balc = create_box("House_BalconyDeck", (6.0, 1.8, 0.15), (1.7, -4.85, 2.925))
    woodwork.append((balc, "wood"))
    for i, px in enumerate((-1.2, 0.2, 1.6, 3.0, 4.4)):
        p = create_box(f"House_BalcPostF{i}", (0.08, 0.08, 1.0),
                       (px, -5.7, 3.5))
        woodwork.append((p, "wood"))
    top = create_box("House_BalcRailF", (6.0, 0.08, 0.08), (1.7, -5.7, 4.0))
    mid = create_box("House_BalcRailF2", (6.0, 0.06, 0.06), (1.7, -5.7, 3.5))
    woodwork.extend([(top, "wood"), (mid, "wood")])
    for sx, tag in ((-1.2, "L"), (4.6, "R")):
        for dy in (-5.3, -4.7):
            p = create_box(f"House_BalcPost{tag}", (0.08, 0.08, 1.0),
                           (sx, dy, 3.5))
            woodwork.append((p, "wood"))
        side = create_box(f"House_BalcRailSide{tag}", (0.08, 1.7, 0.08),
                          (sx, -4.85, 4.0))
        woodwork.append((side, "wood"))
    for px in (-1.1, 4.5):
        p = create_box("House_BalcSupport", (0.14, 0.14, 2.7), (px, -5.5, 1.55))
        woodwork.append((p, "wood"))

    # --- back fire escape: landing + full 32-degree stair to the ground ----
    landing = create_box("House_FE_Landing", (3.0, 1.7, 0.12), (2.0, 4.8, 2.94))
    metalwork.append((landing, "rust"))
    for px in (0.55, 1.5, 2.45, 3.45):
        p = create_box("House_FE_Post", (0.06, 0.06, 1.0), (px, 5.6, 3.5))
        metalwork.append((p, "rust"))
    for zz, th in ((4.0, 0.07), (3.5, 0.05)):
        r = create_box("House_FE_Rail", (3.0, 0.07, th), (2.0, 5.6, zz))
        metalwork.append((r, "rust"))
    # external stair climbing towards +X (32 degrees): base 0 -> 3.0, 15 risers
    fe_n = round(3.0 / STAIR_RISE)
    fe_x0 = -4.3
    for i in range(1, fe_n + 1):
        tread_z = i * STAIR_RISE
        x_c = fe_x0 + (i - 0.5) * STEP_DEPTH
        metalwork.append((create_box(
            f"HouseFE_Step{i:02d}",
            (STEP_DEPTH, STAIR_W, STAIR_RISE),
            (x_c, 4.8, tread_z - STAIR_RISE / 2.0),
        ), "rust"))
    fe_top = fe_x0 + fe_n * STEP_DEPTH            # = 0.5, meets the landing edge
    slope = create_box(
        "HouseFE_SlopeRail",
        ((fe_top - fe_x0) / math.cos(STAIR_ANGLE) + 0.3, 0.06, 0.06),
        ((fe_x0 + fe_top) / 2.0, 5.55, 1.5 + 1.0 * 0.5),
        rotation=(0.0, -STAIR_ANGLE, 0.0),
    )
    metalwork.append((slope, "rust"))
    for k in range(3):
        x_p = fe_x0 + 0.6 + k * 1.8
        z_p = (x_p - fe_x0) * math.tan(STAIR_ANGLE)
        p = create_box("HouseFE_Post", (0.06, 0.06, 1.0), (x_p, 5.55, z_p + 0.5))
        metalwork.append((p, "rust"))

    # --- rusty metal gable roof -------------------------------------------
    pitch = math.radians(30.0)
    run = 4.4                        # half-depth 4.0 + 0.4 overhang
    ridge_z = wall_top + run * math.tan(pitch)
    slab_len = run / math.cos(pitch) + 0.35
    for sy in (-1.0, 1.0):
        mid_y = sy * run / 2.0
        mid_z = ridge_z - (run / 2.0) * math.tan(pitch) - 0.15 / (2 * math.cos(pitch))
        slab = create_box(
            f"House_Roof_{'N' if sy > 0 else 'S'}",
            (w + 0.7, slab_len, 0.15),
            (0.0, mid_y, mid_z),
            rotation=(-sy * pitch, 0.0, 0.0),
        )
        metalwork.append((slab, "rust"))
    ridge = create_box("House_RidgeCap", (w + 0.7, 0.34, 0.14),
                       (0.0, 0.0, ridge_z + 0.02))
    metalwork.append((ridge, "rust"))
    # brick gable ends (apex tucked under the roof slabs)
    apex = ridge_z - 0.12
    for sx in (-1.0, 1.0):
        gable = create_triangular_prism(
            f"House_Gable_{'E' if sx > 0 else 'W'}",
            sx * (w / 2 - t), sx * (w / 2),
            [(-d / 2 + 0.05, wall_top - 0.05), (d / 2 - 0.05, wall_top - 0.05),
             (0.0, apex)],
        )
        shell.append((gable, "brick"))

    # --- furniture + lights ------------------------------------------------
    furn = []
    furn += add_bed("House_Bed", -2.6, -2.2, 3.0, rot_z=90)
    furn += add_table("House_Table", 2.6, 1.8, floor_z, rot_z=15)
    furn += add_crates("House_CrateA", 3.6, -2.6, floor_z, n=4, rng=rng)
    furn += add_crates("House_CrateB", -1.4, 2.6, 3.0, n=3, rng=rng)
    for obj, kind in furn:
        if kind == "wood":
            woodwork.append((obj, "wood"))
        elif kind == "mattress":
            shell.append((obj, "mattress"))
        else:
            shell.append((obj, "pillow"))

    # --- unwrap + materials + join ----------------------------------------
    mat_map = {
        "brick": make_material("House_Brick", "brick"),
        "concrete": make_material("House_Concrete", "concrete"),
        "wood": make_material("House_Wood", "wood"),
        "rust": make_material("House_Rust", "rust"),
        "mattress": make_solid_material("House_Mattress", (0.82, 0.80, 0.74, 1.0), 0.9),
        "pillow": make_solid_material("House_Pillow", (0.92, 0.92, 0.90, 1.0), 0.95),
    }
    all_parts = shell + woodwork + metalwork
    for obj, kind in all_parts:
        smart_unwrap(obj, MATERIALS[kind]["uv_scale"] if kind in MATERIALS else 1.0)
        assign_material(obj, mat_map[kind])

    house = join_objects([o for o, _ in all_parts], "HouseTactical")
    set_origin_bottom_center(house)
    add_omni_light("House_Omni_Ground", (2.4, 0.6, 2.35), energy=140.0)
    add_omni_light("House_Omni_Floor2", (-1.5, 1.8, 5.3), energy=130.0)
    return house


def build_apartment_multifloor():
    """3 storeys, 12 x 10 m concrete: internal stairs connect floors 1-2-3 and
    the flat roof (every slab carries an exact 3 m x 1.5 m stair hole)."""
    rng = random.Random(202)
    w, d = 12.0, 10.0
    t = 0.25
    slab_t = 0.20
    floor_z = slab_t
    wall_top = 9.0
    s2_c, s3_c, rf_c = 2.925, 5.925, 8.925   # bands: 2.85..3.0, 5.85..6.0, 8.85..9.0

    shell = []
    base = create_box("Apt_Base", (w - 0.02, d - 0.02, 0.20), (0.0, 0.0, 0.10))
    s2 = create_box("Apt_Slab2", (w - 0.02, d - 0.02, 0.15), (0.0, 0.0, s2_c))
    s3 = create_box("Apt_Slab3", (w - 0.02, d - 0.02, 0.15), (0.0, 0.0, s3_c))
    rf = create_box("Apt_RoofSlab", (w - 0.02, d - 0.02, 0.15), (0.0, 0.0, rf_c))
    shell += [(base, "concrete"), (s2, "concrete"), (s3, "concrete"), (rf, "concrete")]

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
    for wt in walls.values():
        shell.append((wt, "concrete"))

    # parapet around the accessible flat roof
    shell += [
        (create_box("Apt_ParapetF", (w, t, 0.9), (0.0, -d / 2 + t / 2, 9.45)), "concrete"),
        (create_box("Apt_ParapetB", (w, t, 0.9), (0.0, d / 2 - t / 2, 9.45)), "concrete"),
        (create_box("Apt_ParapetL", (t, d - 2 * t, 0.9), (-w / 2 + t / 2, 0.0, 9.45)), "concrete"),
        (create_box("Apt_ParapetR", (t, d - 2 * t, 0.9), (w / 2 - t / 2, 0.0, 9.45)), "concrete"),
    ]

    # interior partition with a doorway on each floor (cover + flow)
    part = create_box("Apt_Partition", (0.2, d - 2 * t, wall_top - 0.15),
                      (1.6, 0.0, (0.15 + wall_top) / 2))
    for fz, s_t in ((floor_z, 0.20), (3.0, 0.15), (6.0, 0.15)):
        cut_door(part, (1.6, 1.0), (1, 0), 0.2, fz, s_t, f"Apt_IntDoor{int(fz)}")
    shell.append((part, "concrete"))

    # --- three stair flights (switchback) + one exact 3 x 1.5 hole each ----
    lane_a, lane_b = -4.9, -3.1
    # A: floor 1 -> floor 2 (lane A, +Y)
    fa, hole_a = stair_flight("AptStairA", lane_a, -4.6, +1, floor_z, 3.0)
    cut_stair_hole(s2, hole_a, s2_c, 0.15)
    # B: floor 2 -> floor 3 (lane B, -Y)
    fb, hole_b = stair_flight("AptStairB", lane_b, 0.05, -1, 3.0, 6.0)
    cut_stair_hole(s3, hole_b, s3_c, 0.15)
    # C: floor 3 -> flat roof (lane A, +Y)
    fc, hole_c = stair_flight("AptStairC", lane_a, -0.12, +1, 6.0, 9.0)
    cut_stair_hole(rf, hole_c, rf_c, 0.15)
    steps = fa + fb + fc

    # --- front door (open leaf) -------------------------------------------
    normals = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}
    fd = cut_door(walls["front"], (0.0, -d / 2 + t / 2), (0, -1), t,
                  floor_z, 0.20, "Apt_FrontDoor")
    leaf = add_door_leaf(fd, (0, -1), t, DOOR_W, DOOR_H, "Apt_FrontDoor", floor_z)
    shell.append((leaf, "concrete"))

    # --- windows: 6 per floor (1.2 x 1.2, sill 1.0 m above the floor) ------
    specs = []
    for fz in (0.0, 3.0, 6.0):
        specs += [
            ("front", -3.4, fz), ("front", 3.4, fz),
            ("back", -3.4, fz), ("back", 3.4, fz),
            ("left", 0.0, fz),
            ("right", 0.0, fz),
        ]
    for i, (wall, coord, fz) in enumerate(specs):
        n = normals[wall]
        if n[1] != 0:
            centre = (coord, -d / 2 + t / 2 if n[1] < 0 else d / 2 - t / 2)
        else:
            centre = (-w / 2 + t / 2 if n[0] < 0 else w / 2 - t / 2, coord)
        c = cut_opening(walls[wall], centre, n, t, WIN_W, WIN_H,
                        fz + WIN_SILL, f"Apt_Win{i}")
        for panel in add_shutters(c, n, t, f"Apt_Win{i}"):
            shell.append((panel, "concrete"))

    # --- furniture ---------------------------------------------------------
    furn = []
    furn += add_bed("Apt_Bed1", -1.5, 3.4, 3.0, rot_z=0)
    furn += add_bed("Apt_Bed2", -1.5, -3.4, 6.0, rot_z=180)
    furn += add_table("Apt_Table1", -1.8, -2.6, floor_z, rot_z=0)
    furn += add_table("Apt_Table2", -2.2, 2.4, 3.0, rot_z=90)
    furn += add_crates("Apt_Crate1", 4.4, -3.8, floor_z, n=4, rng=rng)
    furn += add_crates("Apt_Crate2", 4.4, 3.6, 6.0, n=3, rng=rng)
    for obj, kind in furn:
        if kind == "wood":
            shell.append((obj, "wood"))
        elif kind == "mattress":
            shell.append((obj, "mattress"))
        else:
            shell.append((obj, "pillow"))

    # --- unwrap + materials + join ----------------------------------------
    mat_map = {
        "concrete": make_material("Apt_Concrete", "concrete"),
        "wood": make_material("Apt_Wood", "wood"),
        "mattress": make_solid_material("Apt_Mattress", (0.80, 0.78, 0.72, 1.0), 0.9),
        "pillow": make_solid_material("Apt_Pillow", (0.90, 0.90, 0.88, 1.0), 0.95),
    }
    parts = shell + [(s, "concrete") for s in steps]
    for obj, kind in parts:
        smart_unwrap(obj, MATERIALS[kind]["uv_scale"] if kind in MATERIALS else 1.0)
        assign_material(obj, mat_map[kind])

    apt = join_objects([o for o, _ in parts], "ApartmentMultifloor")
    set_origin_bottom_center(apt)
    for fz in (0.0, 3.0, 6.0):
        add_omni_light(f"Apt_Omni_{int(fz)}a", (-2.2, -2.6, fz + 2.35), energy=130.0)
        add_omni_light(f"Apt_Omni_{int(fz)}b", (4.0, 2.8, fz + 2.35), energy=110.0)
    return apt


def build_warehouse_metal():
    """1 storey, 20 x 12 m: corrugated metal walls, two large open garage
    doors, side personnel door, concrete floor."""
    rng = random.Random(303)
    w, d = 20.0, 12.0
    t = 0.30
    floor_t = 0.30
    floor_top = floor_t
    wall_top = 5.70

    parts = []

    floor = create_box("Wh_Floor", (w - 0.02, d - 0.02, floor_t), (0.0, 0.0, floor_t / 2))
    parts.append((floor, "concrete"))

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
    for wt in walls.values():
        parts.append((wt, "metal"))

    # flat corrugated roof (inset to avoid coplanar faces) + interior beams
    roof = create_box("Wh_Roof", (w - 0.02, d - 0.02, 0.30),
                      (0.0, 0.0, wall_top + 0.15))
    parts.append((roof, "metal"))
    for bx in (-6.5, 0.0, 6.5):
        beam = create_box("Wh_Beam", (0.28, d - 2 * t, 0.42),
                          (bx, 0.0, wall_top - 0.21))
        parts.append((beam, "metal"))

    # --- two large OPEN garage doors (6.0 W x 4.5 H) ----------------------
    for i, gx in enumerate((-4.9, 4.9)):
        cut_opening(walls["front"], (gx, -d / 2 + t / 2), (0, -1), t,
                    6.0, 4.5 + floor_top, 0.0, f"Wh_Garage{i}")
        # rolled-up shutter bundle parked above the opening (never blocks it)
        bundle = create_box(f"Wh_RollBundle{i}", (6.0, 0.55, 0.5),
                            (gx, -d / 2 + t + 0.24, floor_top + 4.5 + 0.26))
        parts.append((bundle, "metal"))

    # --- side personnel door with open metal leaf -------------------------
    pd = cut_door(walls["left"], (-w / 2 + t / 2, -2.0), (-1, 0), t,
                  floor_top, floor_t, "Wh_PersonDoor")
    leaf = add_door_leaf(pd, (-1, 0), t, DOOR_W, DOOR_H, "Wh_PersonDoor", floor_top)
    parts.append((leaf, "metal"))

    # --- windows with open wooden shutters (sill at 1.0 m) ----------------
    normals = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}
    specs = [
        ("right", -2.6, "Wh_WinR1"), ("right", 2.6, "Wh_WinR2"),
        ("back", -5.5, "Wh_WinB1"), ("back", 0.0, "Wh_WinB2"), ("back", 5.5, "Wh_WinB3"),
        ("front", 0.0, "Wh_WinF"),   # between the two garage doors
    ]
    for wall, coord, tag in specs:
        n = normals[wall]
        if n[1] != 0:
            centre = (coord, -d / 2 + t / 2 if n[1] < 0 else d / 2 - t / 2)
        else:
            centre = (-w / 2 + t / 2 if n[0] < 0 else w / 2 - t / 2, coord)
        c = cut_opening(walls[wall], centre, n, t, WIN_W, WIN_H, WIN_SILL, tag)
        for panel in add_shutters(c, n, t, tag):
            parts.append((panel, "wood"))

    # --- furniture: crate clusters + table --------------------------------
    for (cx, cy, n) in ((-7.0, 3.4, 5), (7.2, 3.6, 4), (0.0, -3.6, 4), (-7.5, -3.4, 3)):
        parts += add_crates(f"Wh_Crate{int(cx)}_{int(cy)}", cx, cy, floor_top,
                            n=n, rng=rng)
    parts += add_table("Wh_Table", 5.0, -4.0, floor_top, rot_z=-20, size=(1.8, 0.9))

    # --- unwrap + materials + join ----------------------------------------
    mat_map = {
        "concrete": make_material("Wh_Concrete", "concrete"),
        "metal": make_material("Wh_Metal", "metal"),
        "wood": make_material("Wh_Wood", "wood"),
    }
    for obj, kind in parts:
        smart_unwrap(obj, MATERIALS[kind]["uv_scale"])
        assign_material(obj, mat_map[kind])

    wh = join_objects([o for o, _ in parts], "WarehouseMetal")
    set_origin_bottom_center(wh)
    for i, loc in enumerate(((-7.0, 0.0, 5.0), (7.0, 0.0, 5.0), (0.0, 0.0, 5.0))):
        add_omni_light(f"Wh_Omni{i}", loc, energy=220.0)
    return wh


def build_ruined_building():
    """2 storeys, 10 x 8 m, heavily destroyed: BMesh random face deletion,
    exposed rebar, rubble piles, no intact roof."""
    rng = random.Random(404)
    w, d = 10.0, 8.0
    t = 0.25
    slab_t = 0.20
    floor_z = slab_t
    wall_top = 6.0
    s2_c, s2_t = 2.925, 0.15

    intact, furniture = [], []

    base = create_box("Ruin_Base", (w - 0.02, d - 0.02, slab_t), (0.0, 0.0, slab_t / 2))
    slab2 = create_box("Ruin_Slab2", (w - 0.02, d - 0.02, s2_t), (0.0, 0.0, s2_c))
    roof = create_box("Ruin_RoofRemnant", (w - 0.02, d - 0.02, 0.15), (0.0, 0.0, 5.925))
    intact += [(base, "concrete"), (slab2, "concrete")]

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

    # --- passable openings BEFORE destruction -----------------------------
    normals = {"front": (0, -1), "back": (0, 1), "left": (-1, 0), "right": (1, 0)}
    d0 = cut_door(walls["front"], (-1.5, -d / 2 + t / 2), (0, -1), t,
                  floor_z, slab_t, "Ruin_Door")
    leaf = add_door_leaf(d0, (0, -1), t, DOOR_W, DOOR_H, "Ruin_Door", floor_z,
                         damaged=True)
    furniture.append((leaf, "wood"))
    cut_door(walls["back"], (2.4, d / 2 - t / 2), (0, 1), t,
             floor_z, slab_t, "Ruin_BackDoor")

    shutters_src = []
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
        c = cut_opening(walls[wall], centre, n, t, WIN_W, WIN_H,
                        fz + WIN_SILL, f"Ruin_Win{i}")
        shutters_src.append((c, n, i))

    # --- stairs (32 deg) + hole in slab2 ----------------------------------
    steps, hole = stair_flight("RuinStair", -3.95, -3.6, +1, floor_z, 3.0)
    cut_stair_hole(slab2, hole, s2_c, s2_t)

    # --- BMesh destruction: walls heavily, roof almost completely gone -----
    for i, wt in enumerate(walls.values()):
        destroy_faces(wt, p_bottom=0.30, p_top=0.88, keep="bottom",
                      seed=404 + i, cuts=5)
    destroy_faces(roof, p_bottom=0.72, p_top=0.72, keep="border",
                  seed=410, cuts=6)

    # --- exposed rebar anchored to surviving broken edges -----------------
    anchors = []
    for wt in walls.values():
        for v in wt.data.vertices:
            if v.co.z > 4.6:
                anchors.append((v.co.x, v.co.y, v.co.z))
    for v in roof.data.vertices:
        anchors.append((v.co.x, v.co.y, v.co.z))
    rods = add_rebar(anchors, rng, count=20)

    # --- rubble piles on both floors (clear of the stairs) ----------------
    furniture += add_rubble_pile("Ruin_RubbleA", 3.0, 2.4, floor_z, 7, rng)
    furniture += add_rubble_pile("Ruin_RubbleB", -3.2, -3.0, floor_z, 5, rng)
    furniture += add_rubble_pile("Ruin_RubbleC", 2.8, -3.2, floor_z, 5, rng)
    furniture += add_rubble_pile("Ruin_RubbleUp", 3.2, 2.6, 3.0, 5, rng)
    furniture += add_crates("Ruin_Crate", 4.0, 0.8, floor_z, n=3, rng=rng)
    furniture += add_table("Ruin_Table", -3.6, 2.4, floor_z, rot_z=35)

    # damaged shutters still hanging on some windows
    for c, n, i in shutters_src:
        if i in (0, 3, 6):
            continue
        for panel in add_shutters(c, n, t, f"Ruin_Win{i}", damaged=True):
            furniture.append((panel, "wood"))

    parts = (intact
             + [(wt, "concrete") for wt in walls.values()]
             + [(roof, "concrete")]
             + [(s, "concrete") for s in steps]
             + [(r, "rust") for r in rods]
             + furniture)

    mat_map = {
        "concrete": make_material("Ruin_Concrete", "concrete"),
        "wood": make_material("Ruin_Wood", "wood"),
        "rust": make_material("Ruin_Rust", "rust"),
    }
    for obj, kind in parts:
        smart_unwrap(obj, MATERIALS[kind]["uv_scale"] if kind in MATERIALS else 1.0)
        assign_material(obj, mat_map[kind])

    ruin = join_objects([o for o, _ in parts], "RuinedBuilding")
    set_origin_bottom_center(ruin)
    add_omni_light("Ruin_Omni_Ground", (-1.0, 1.5, 2.3), energy=120.0,
                   color=(1.0, 0.78, 0.5))
    add_omni_light("Ruin_Omni_Floor2", (1.0, -1.0, 5.2), energy=90.0,
                   color=(1.0, 0.78, 0.5))
    return ruin


# ---------------------------------------------------------------------------
# Hero scene: ground + all four buildings + baked shadows
# ---------------------------------------------------------------------------
def build_hero_scene():
    ensure_hero_ground_texture()
    ground = create_box("Hero_Ground", (100.0, 100.0, 0.4), (0.0, 0.0, -0.2))
    smart_unwrap(ground, MATERIALS["grass_hero"]["uv_scale"])
    assign_material(ground, make_material("Hero_GroundGrass", "grass_hero"))

    builders = [
        ("house_tactical", build_house_tactical),
        ("apartment_multifloor", build_apartment_multifloor),
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
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    print(f"Blender (bpy) version: {bpy.app.version_string}")
    print(f"Stair math: rise={STAIR_RISE} m, angle=32deg, "
          f"step depth=rise/tan(32°)={STEP_DEPTH:.4f} m, "
          f"hole={HOLE_LEN}x{STAIR_W} m (+{HOLE_CLEAR} boolean clearance)")

    print("Ensuring procedural textures ...")
    os.makedirs(TEXTURE_DIR, exist_ok=True)
    ensure_grass_texture()
    ensure_rust_texture()
    ensure_hero_ground_texture()

    failures = []

    def run(label, path, builder, expect_lights=True):
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
            return stats
        except Exception as exc:      # keep going, fail at the end
            failures.append((label, exc))
            print(f"  FAILED {label}: {exc!r}")
            return None

    run("base_ground.glb", os.path.join(TERRAIN_DIR, "base_ground.glb"),
        build_base_ground, expect_lights=False)
    run("house_tactical.glb", os.path.join(BUILDINGS_DIR, "house_tactical.glb"),
        build_house_tactical)
    run("apartment_multifloor.glb",
        os.path.join(BUILDINGS_DIR, "apartment_multifloor.glb"),
        build_apartment_multifloor)
    run("warehouse_metal.glb", os.path.join(BUILDINGS_DIR, "warehouse_metal.glb"),
        build_warehouse_metal)
    run("ruined_building.glb", os.path.join(BUILDINGS_DIR, "ruined_building.glb"),
        build_ruined_building)

    print("Building scene_phase1.glb (hero: ground + 4 buildings) ...")
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
    print("Done — Phase 1 assets generated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
