#!/usr/bin/env python3
"""
Mahal Palace — Massive Battle Royale POI (40m x 40m x 15m)
Generates:
  docs/textures/sandstone_1k.png  — Red/Orange sandstone
  docs/textures/marble_1k.png     — White/cream marble with veins
  docs/textures/gold_trim_1k.png  — Shiny gold metallic
  docs/models/buildings/mahal_palace.glb — 40x40 fort with courtyard, domes, chhatris, stairs (30°), trig arches

Requirements enforced:
  - math.tan(math.radians(30)) for stairs
  - for loop with math.sin() and math.cos() for perfect arches
  - Boolean cutouts for entryways, holes for staircases
  - Origin at bottom-center, flat roof, 4 domes, chhatris, balconies, fountain, crates, OmniLights
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

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURE_DIR = os.path.join(REPO_ROOT, "docs", "textures")
OUTPUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "buildings")

# --- Palace dimensions ---
FOOTPRINT_W = 40.0
FOOTPRINT_D = 40.0
TOTAL_H = 15.0
FLOOR_H = 5.0
COURTYARD = 15.0

WALL_T_OUT = 0.65
WALL_T_IN = 0.45
SLAB_T_GROUND = 0.40
SLAB_T = 0.30
BALCONY_T = 0.15

# Stair constants — MUST use math.tan(math.radians(30))
STAIR_RISE = 0.25
STAIR_ANGLE_DEG = 30.0
STAIR_ANGLE = math.radians(STAIR_ANGLE_DEG)
# Requirement: Use math.tan(math.radians(30)) to create stairs
STEP_DEPTH = STAIR_RISE / math.tan(math.radians(30))  # ~0.433m

STAIR_W = 2.2
HOLE_W = 2.0   # across width
HOLE_LEN = 4.0  # along run
HOLE_CLEAR = 0.04

MAP_SCALE = 0.3

MATERIALS = {
    "sandstone": {"file": "sandstone_1k.png", "roughness": 0.88, "metallic": 0.0, "tile": 2.5},
    "marble": {"file": "marble_1k.png", "roughness": 0.12, "metallic": 0.0, "tile": 2.5},
    "gold": {"file": "gold_trim_1k.png", "roughness": 0.25, "metallic": 0.85, "tile": 1.5},
    "wood": {"file": "wood_plank_1k.png", "fallback": "wood_plank.png", "roughness": 0.72, "metallic": 0.0, "tile": 2.0},
}

_MATERIAL_CACHE = {}

# ---------------------------------------------------------------------------
# Procedural 1K texture helpers — tileable via FFT
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

def ensure_sandstone_1k():
    from PIL import Image
    dst = os.path.join(TEXTURE_DIR, "sandstone_1k.png")
    if os.path.isfile(dst):
        return
    size = 1024
    # Tileable noise fields
    base_n = _fft_noise(size, 0.015, seed=101)
    detail_n = _fft_noise(size, 0.08, seed=102)
    crack_n = _fft_noise(size, 0.04, seed=103)
    fine = _fft_noise(size, 0.45, seed=104)
    horizontal = _fft_noise(size, 0.035, seed=105)  # layering streaks

    # Base gradient sandstone red/orange
    t = np.clip(0.5 + 0.38 * base_n + 0.18 * detail_n + 0.12 * horizontal, 0.0, 1.0)
    col = _lerp_rgb((0.62, 0.32, 0.18), (0.86, 0.56, 0.34), t)  # dark brick-red -> light orange
    # Cracks and darker mortar lines
    crack_mask = np.clip((np.clip(0.5 + 0.6 * crack_n, 0.0, 1.0) - 0.62) * 3.2, 0.0, 1.0)
    crack_col = _lerp_rgb((0.38, 0.22, 0.12), (0.28, 0.16, 0.09), np.clip(0.5 + 0.3 * detail_n, 0, 1))
    col = col * (1 - crack_mask[..., None] * 0.65) + crack_col * crack_mask[..., None] * 0.65
    # Horizontal sandstone layer tint
    layer = np.clip(0.5 + 0.4 * horizontal, 0, 1)
    layer_col = _lerp_rgb((0.70, 0.42, 0.22), (0.80, 0.55, 0.30), layer)
    col = col * 0.88 + layer_col * 0.12
    col = np.clip(col + 0.05 * fine[..., None], 0.0, 1.0)
    # Slight vignette for depth
    col = np.clip((col - 0.5) * 1.08 + 0.5, 0, 1)
    Image.fromarray((col * 255).astype(np.uint8), "RGB").save(dst, "PNG")
    print(f"  generated sandstone_1k.png")

def ensure_marble_1k():
    from PIL import Image
    dst = os.path.join(TEXTURE_DIR, "marble_1k.png")
    if os.path.isfile(dst):
        return
    size = 1024
    base_n = _fft_noise(size, 0.018, seed=201)
    detail_n = _fft_noise(size, 0.08, seed=202)
    vein_n = _fft_noise(size, 0.04, seed=203)
    fine = _fft_noise(size, 0.45, seed=204)

    # Base cream marble
    t = np.clip(0.5 + 0.28 * base_n + 0.15 * detail_n, 0.0, 1.0)
    col = _lerp_rgb((0.96, 0.95, 0.92), (0.92, 0.90, 0.87), t)  # white-cream variation

    # Veins: use periodic vein field stretched diagonally
    # Create tileable vein mask from vein_n threshold
    wx = np.linspace(0, 1, size)
    wy = np.linspace(0, 1, size)
    WX, WY = np.meshgrid(wx, wy)
    # Directional vein pattern: sinusoidal flow + noise distortion
    # Tileable: use sin with integer frequency + noise
    flow = np.sin((WX * 12.0 + WY * 4.0 + vein_n * 2.5) * math.pi * 2.0)
    # Secondary cross veins
    flow2 = np.sin((WX * 3.0 - WY * 8.0 + base_n * 1.2) * math.pi * 2.0)
    # Combine to make sparse veins
    vein_strength = np.clip((np.abs(flow) * 0.6 + np.abs(flow2) * 0.4), 0, 1)
    # Threshold to make thin veins
    vein_mask = np.clip((0.85 - vein_strength) * 6.0, 0.0, 1.0)  # where flow near zero → vein
    # Modulate by vein_n randomness
    vein_mask = vein_mask * np.clip(0.5 + 0.8 * np.clip(vein_n, -1, 1), 0, 1) * 0.65

    # Grey-beige vein color
    vein_col = _lerp_rgb((0.72, 0.70, 0.68), (0.60, 0.58, 0.56), np.clip(0.5 + 0.4 * detail_n, 0, 1))
    # Add veins subtly
    col = col * (1.0 - vein_mask[..., None] * 0.9) + vein_col * vein_mask[..., None] * 0.9
    col = np.clip(col + 0.03 * fine[..., None], 0, 1)
    # Slight polish specular hint via brightness
    col = np.clip((col - 0.5) * 1.05 + 0.5, 0, 1)
    Image.fromarray((col * 255).astype(np.uint8), "RGB").save(dst, "PNG")
    print(f"  generated marble_1k.png")

def ensure_gold_trim_1k():
    from PIL import Image
    dst = os.path.join(TEXTURE_DIR, "gold_trim_1k.png")
    if os.path.isfile(dst):
        return
    size = 1024
    base_n = _fft_noise(size, 0.015, seed=301)
    detail_n = _fft_noise(size, 0.08, seed=302)
    glint_n = _fft_noise(size, 0.28, seed=303)
    brush_n = _fft_noise(size, 0.06, seed=304)

    # Gold gradient base: dark amber -> bright gold
    t = np.clip(0.5 + 0.32 * base_n + 0.20 * detail_n + 0.15 * brush_n, 0.0, 1.0)
    col = _lerp_rgb((0.62, 0.48, 0.12), (0.98, 0.82, 0.32), t)  # deep gold to highlight gold
    # Brushed metal streaks (horizontal)
    brush_mask = np.clip(0.5 + 0.5 * brush_n, 0, 1)
    brush_col = _lerp_rgb((0.70, 0.55, 0.15), (0.92, 0.76, 0.28), brush_mask)
    col = col * 0.75 + brush_col * 0.25
    # Glints/highlights for metallic shine
    glint = np.clip((glint_n - 0.75) * 4.0, 0.0, 1.0) ** 1.5
    highlight = np.array([1.0, 0.95, 0.65])[None, None, :]
    col = col * (1.0 - glint[..., None] * 0.5) + highlight * glint[..., None] * 0.5
    col = np.clip(col, 0.0, 1.0)
    # Add slight contrast for PBR
    col = np.clip((col - 0.5) * 1.12 + 0.5, 0, 1)
    Image.fromarray((col * 255).astype(np.uint8), "RGB").save(dst, "PNG")
    print(f"  generated gold_trim_1k.png")

def ensure_textures():
    os.makedirs(TEXTURE_DIR, exist_ok=True)
    ensure_sandstone_1k()
    ensure_marble_1k()
    ensure_gold_trim_1k()
    # Also ensure wood fallback copy if needed
    import shutil
    for src, dst in [("wood_plank.png", "wood_plank_1k.png")]:
        d = os.path.join(TEXTURE_DIR, dst)
        if not os.path.isfile(d):
            s = os.path.join(TEXTURE_DIR, src)
            if os.path.isfile(s):
                shutil.copy(s, d)
                print(f"  copied {src} -> {dst}")

# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------
def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _MATERIAL_CACHE.clear()

def set_metric_units():
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0

def create_box(name, size, location=(0,0,0), rotation=(0,0,0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "Mesh"
    obj.dimensions = tuple(size)
    obj.rotation_euler = rotation
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj

def create_cylinder(name, radius, depth, location, vertices=16):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=depth, vertices=vertices, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name+"Mesh"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj

def create_ico_sphere(name, radius, location, subdivisions=2):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions, radius=radius, location=location)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name+"Mesh"
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return obj

def create_arch_prism(name, width, rect_h, radius, depth, cx, cy, cz_bottom, orientation="x", segments=12):
    """
    Create arch-shaped prism using trigonometry: math.sin() and math.cos() for perfect half-circle.
    width = arch opening width (at base), rect_h = rectangular height, radius = width/2, depth = wall thickness + clearance
    orientation = "x" => width along X, depth along Y (for north/south walls)
                 "y" => width along Y, depth along X (for east/west walls)
    cz_bottom = bottom Z of arch (floor level)
    Uses for loop with math.sin() and math.cos() to generate arch points.
    """
    total_h = rect_h + radius
    # Build 2D profile points (local x,z) — centre at (0, cz_bottom)
    # Points: bottom-left -> top-left rect -> arc -> top-right rect -> bottom-right
    profile = []
    half_w = width / 2.0
    bottom = cz_bottom
    top_rect = bottom + rect_h

    profile.append((-half_w, bottom))          # bottom-left
    profile.append((-half_w, top_rect))        # top of rectangle left

    # --- Generate arch points via trigonometry (Requirement) ---
    # Use math.sin() and math.cos() in a for loop to create perfect semicircular top
    # Theta from pi to 0 gives left->right half circle
    num_arc = segments
    for i in range(num_arc + 1):
        # Need to skip endpoints if already in profile? We'll generate full inclusive and deduplicate
        # Use explicit trig
        theta = math.pi * (1.0 - i / num_arc)  # pi -> 0
        x = radius * math.cos(theta)
        z = top_rect + radius * math.sin(theta)
        # Avoid duplicating the rect corner points (they coincide with theta=pi and 0)
        if i == 0 or i == num_arc:
            continue  # already have these
        profile.append((x, z))

    profile.append((half_w, top_rect))         # top right rect
    profile.append((half_w, bottom))           # bottom-right

    # Now extrude profile along depth axis to create 3D prism
    n = len(profile)
    verts = []
    faces = []

    # Create front and back vertices
    # For orientation x: profile x is world X, depth is world Y
    # For orientation y: profile x is world Y, depth is world X (rotate 90)
    for (px, pz) in profile:
        if orientation == "x":
            # front at cy - depth/2, back at cy + depth/2
            verts.append((cx + px, cy - depth/2.0, pz))
        else:
            # width along Y: px is world Y offset, depth along X
            verts.append((cx - depth/2.0, cy + px, pz))
    # back
    offset = n
    for (px, pz) in profile:
        if orientation == "x":
            verts.append((cx + px, cy + depth/2.0, pz))
        else:
            verts.append((cx + depth/2.0, cy + px, pz))

    # front face (n vertices)
    faces.append(tuple(range(n)))
    # back face (reverse winding)
    faces.append(tuple(range(offset + n -1, offset-1, -1)))

    # side walls bridging front/back
    for i in range(n):
        j = (i+1) % n
        faces.append((i, j, offset + j, offset + i))

    # Bottom face not needed (coplanar with floor) but side walls close shape
    # Actually side walls already include bottom edge

    mesh = bpy.data.meshes.new(name+"Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.validate()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj

def apply_boolean_cut(target, cutter):
    mod = target.modifiers.new(name="Cutout", type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.object = cutter
    if hasattr(mod, "solver"):
        try:
            mod.solver = "EXACT"
        except:
            pass
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)

def smart_unwrap(obj, target_density=None):
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

    # orient textures upright on vertical faces
    uvl = obj.data.uv_layers.active
    me = obj.data
    def _cov(a,b):
        n=len(a)
        if n<2:
            return 0.0
        ma=sum(a)/n; mb=sum(b)/n
        return sum((a[i]-ma)*(b[i]-mb) for i in range(n))/n
    for poly in me.polygons:
        if abs(poly.normal.z) >= 0.55:
            continue
        idxs=list(poly.loop_indices)
        us=[uvl.data[i].uv.x for i in idxs]
        vs=[uvl.data[i].uv.y for i in idxs]
        zs=[me.vertices[me.loops[i].vertex_index].co.z for i in idxs]
        if abs(_cov(us,zs)) > abs(_cov(vs,zs)):
            cx=sum(us)/len(us); cy=sum(vs)/len(vs)
            for i,u,v in zip(idxs, us, vs):
                x,y = u-cx, v-cy
                uvl.data[i].uv = (cx - y, cy + x)

    if target_density:
        area3d=sum(p.area for p in me.polygons)
        area_uv=0.0
        for p in me.polygons:
            pts=[uvl.data[i].uv for i in p.loop_indices]
            if len(pts)<3:
                continue
            s=0.0
            for a in range(len(pts)):
                b=(a+1)%len(pts)
                s+=pts[a].x*pts[b].y - pts[b].x*pts[a].y
            area_uv+=abs(s)/2.0
        if area3d>1e-9 and area_uv>1e-9:
            cur=math.sqrt(area_uv/area3d)
            k=target_density/cur
            for layer in obj.data.uv_layers:
                for uv in layer.data:
                    uv.uv=uv.uv*k

def density_for(preset):
    tile=MATERIALS[preset]["tile"]
    if not tile:
        return None
    return 1.0/(MAP_SCALE*tile)

def make_material(name, preset):
    cache_key=f"{name}:{preset}"
    if cache_key in _MATERIAL_CACHE:
        return _MATERIAL_CACHE[cache_key]
    spec=MATERIALS[preset]
    mat=bpy.data.materials.new(name)
    if bpy.app.version < (5,0,0):
        mat.use_nodes=True
    nt=mat.node_tree
    bsdf=nt.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError("Principled BSDF not found")
    tex_path=os.path.join(TEXTURE_DIR, spec["file"])
    if not os.path.isfile(tex_path):
        # Try fallback
        if "fallback" in spec:
            tex_path=os.path.join(TEXTURE_DIR, spec["fallback"])
        if not os.path.isfile(tex_path):
            raise FileNotFoundError(f"Texture not found: {tex_path}")
    image=bpy.data.images.load(tex_path, check_existing=True)
    coord=nt.nodes.new("ShaderNodeTexCoord")
    coord.name=f"{name}_Coord"
    coord.location=(-760,220)
    mapping=nt.nodes.new("ShaderNodeMapping")
    mapping.name=f"{name}_Mapping"
    mapping.location=(-560,220)
    mapping.inputs["Scale"].default_value=(MAP_SCALE,MAP_SCALE,MAP_SCALE)
    tex=nt.nodes.new("ShaderNodeTexImage")
    tex.name=f"{name}_Texture"
    tex.label=spec["file"]
    tex.image=image
    tex.extension="REPEAT"
    tex.location=(-350,220)
    nt.links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value=spec["roughness"]
    bsdf.inputs["Metallic"].default_value=spec["metallic"]
    _MATERIAL_CACHE[cache_key]=mat
    return mat

def make_solid_material(name, rgba_dict, roughness=0.8):
    if name in _MATERIAL_CACHE:
        return _MATERIAL_CACHE[name]
    rgba = rgba_dict["rgba"] if isinstance(rgba_dict, dict) else rgba_dict
    mat=bpy.data.materials.new(name)
    if bpy.app.version < (5,0,0):
        mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value=tuple(rgba)
    bsdf.inputs["Roughness"].default_value=roughness
    bsdf.inputs["Metallic"].default_value=0.0
    _MATERIAL_CACHE[name]=mat
    return mat

def join_objects(objects, name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objects:
        o.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
    bpy.ops.object.join()
    joined=bpy.context.active_object
    joined.name=name
    joined.data.name=name+"Mesh"
    return joined

def set_origin_bottom_center(obj):
    coords=[obj.matrix_world @ v.co for v in obj.data.vertices]
    min_x=min(c.x for c in coords); max_x=max(c.x for c in coords)
    min_y=min(c.y for c in coords); max_y=max(c.y for c in coords)
    min_z=min(c.z for c in coords)
    offset=Vector((-(min_x+max_x)/2.0, -(min_y+max_y)/2.0, -min_z))
    obj.data.transform(Matrix.Translation(offset))
    obj.data.validate(clean_customdata=True)
    obj.data.update()
    obj.matrix_world=Matrix.Identity(4)
    obj.location=(0,0,0)
    obj.rotation_euler=(0,0,0)
    obj.scale=(1,1,1)

def object_bbox(obj):
    coords=[obj.matrix_world @ v.co for v in obj.data.vertices]
    return (min(c.x for c in coords), max(c.x for c in coords),
            min(c.y for c in coords), max(c.y for c in coords),
            min(c.z for c in coords), max(c.z for c in coords))

def add_omni_light(name, location, energy=180.0, color=(1.0,0.85,0.62)):
    light_data=bpy.data.lights.new(name=name, type="POINT")
    light_data.energy=energy
    light_data.color=color
    light_data.shadow_soft_size=0.25
    obj=bpy.data.objects.new(name, light_data)
    obj.location=tuple(location)
    bpy.context.collection.objects.link(obj)
    return obj

# --- Stair helpers ---
def stair_flight(name, lane_x, y_start, direction, base_z, target_z, lane_y_fixed=None):
    """
    Create marble stair flight using math.tan(math.radians(30)) for step depth
    Returns (step_boxes, hole_dict)
    lane_x: X position of stair center (for Y-running stairs) or Y for X-running stairs
    y_start: start Y (for Y-running)
    direction: +1 or -1 along Y
    """
    rise=STAIR_RISE
    n=round((target_z - base_z)/rise)
    if abs(base_z + n*rise - target_z) > 1e-6:
        raise ValueError(f"{name}: floor height {target_z-base_z} not multiple of {rise}")
    # Enforce trig requirement explicitly
    step_depth = rise / math.tan(math.radians(30))  # MUST use this formula
    boxes=[]
    for i in range(1, n+1):
        tread_z=base_z + i*rise
        y_c=y_start + direction*((i-0.5)*step_depth)
        # step box size: STAIR_W across, STEP_DEPTH along run, rise vertical
        # For Y-running stairs: width along X, depth along Y
        boxes.append(create_box(f"{name}_Step{i:02d}", (STAIR_W, step_depth, rise), (lane_x, y_c, tread_z - rise/2.0)))
    top_y=y_start + direction*n*step_depth
    hole={
        "x": lane_x,
        "y_center": top_y - direction*(HOLE_LEN/2.0),
        "width": STAIR_W + 0.3,  # hole width across stair width + clearance
        "length": HOLE_LEN + HOLE_CLEAR,
        "top_y": top_y,
        "steps": n,
        "y_start": y_start,
        "direction": direction,
    }
    return boxes, hole

def cut_stair_hole(slab, hole, slab_center_z, slab_thickness):
    cutter=create_box("StairHoleCutter", (hole["width"], hole["length"], slab_thickness+1.0), (hole["x"], hole["y_center"], slab_center_z))
    apply_boolean_cut(slab, cutter)

# ---------------------------------------------------------------------------
# Build Mahal
# ---------------------------------------------------------------------------
def build_mahal():
    rng=random.Random(777)
    parts=[]  # list of (obj, material_preset)

    # ---- Ground base ring slabs (4 parts) ----
    # Ring slabs composition to form 40x40 with 15x15 courtyard
    # North wing: 40 x 12.5 at y=+13.75
    # South wing: same at -13.75
    # East wing: 12.5 x 15 at x=+13.75
    # West wing: -13.75
    wing_t_ground=SLAB_T_GROUND
    z_ground=wing_t_ground/2.0

    # Ground floor slabs (level 0)
    north_ground = create_box("Mahal_Ground_North", (40.0, 12.5, wing_t_ground), (0, 13.75, z_ground))
    south_ground = create_box("Mahal_Ground_South", (40.0, 12.5, wing_t_ground), (0, -13.75, z_ground))
    east_ground = create_box("Mahal_Ground_East", (12.5, 15.0, wing_t_ground), (13.75, 0, z_ground))
    west_ground = create_box("Mahal_Ground_West", (12.5, 15.0, wing_t_ground), (-13.75, 0, z_ground))
    parts += [(north_ground,"sandstone"), (south_ground,"sandstone"), (east_ground,"sandstone"), (west_ground,"sandstone")]

    # Upper floor slabs at 5m and 10m, roof at 15m
    # Use slab_t =0.30 thickness
    # For each level, create 4 wing slabs
    levels = [
        (5.0, "Level2"),   # first upper floor (second floor)
        (10.0, "Level3"),  # second upper (third floor)
        (15.0, "Roof"),    # roof
    ]
    slab_objs_by_level = {}  # level_z -> list of slab objects for hole cutting
    for lvl_z, tag in levels:
        center_z = lvl_z - SLAB_T/2.0
        north = create_box(f"Mahal_{tag}_North", (40.0, 12.5, SLAB_T), (0, 13.75, center_z))
        south = create_box(f"Mahal_{tag}_South", (40.0, 12.5, SLAB_T), (0, -13.75, center_z))
        east = create_box(f"Mahal_{tag}_East", (12.5, 15.0, SLAB_T), (13.75, 0, center_z))
        west = create_box(f"Mahal_{tag}_West", (12.5, 15.0, SLAB_T), (-13.75, 0, center_z))
        parts += [(north,"sandstone"), (south,"sandstone"), (east,"sandstone"), (west,"sandstone")]
        slab_objs_by_level[lvl_z] = [north, south, east, west]

    # Courtyard marble floor (15x15)
    courtyard_floor = create_box("Mahal_Courtyard_Marble", (15.0, 15.0, 0.15), (0, 0, 0.075))
    parts.append((courtyard_floor, "marble"))
    # Also marble strips around? Add marble border inside courtyard edge
    # Fountain
    fountain_base = create_cylinder("Mahal_Fountain_Base", 3.2, 0.35, (0,0,0.25), vertices=24)
    parts.append((fountain_base,"marble"))
    fountain_pedestal = create_cylinder("Mahal_Fountain_Pedestal", 1.0, 0.9, (0,0,0.85), vertices=16)
    parts.append((fountain_pedestal,"marble"))
    fountain_top = create_cylinder("Mahal_Fountain_Top", 0.6, 0.2, (0,0,1.35), vertices=16)
    parts.append((fountain_top,"marble"))
    # Water plane in fountain (solid blueish)
    fountain_water = create_cylinder("Mahal_Fountain_Water", 2.8, 0.05, (0,0,0.42), vertices=24)
    parts.append((fountain_water,"marble"))  # will use solid later? keep marble for now but tint via solid?
    # Use solid material for water
    # We'll assign later separately

    # ---- Outer walls (40x40 perimeter) ----
    outer_walls = {}
    # North outer wall (full width)
    north_outer = create_box("Mahal_Outer_North", (40.0, WALL_T_OUT, TOTAL_H), (0, FOOTPRINT_D/2 - WALL_T_OUT/2, TOTAL_H/2))
    south_outer = create_box("Mahal_Outer_South", (40.0, WALL_T_OUT, TOTAL_H), (0, -FOOTPRINT_D/2 + WALL_T_OUT/2, TOTAL_H/2))
    # East/west between north/south
    east_outer = create_box("Mahal_Outer_East", (WALL_T_OUT, FOOTPRINT_D - 2*WALL_T_OUT, TOTAL_H), (FOOTPRINT_W/2 - WALL_T_OUT/2, 0, TOTAL_H/2))
    west_outer = create_box("Mahal_Outer_West", (WALL_T_OUT, FOOTPRINT_D - 2*WALL_T_OUT, TOTAL_H), (-FOOTPRINT_W/2 + WALL_T_OUT/2, 0, TOTAL_H/2))
    outer_walls["north"]=north_outer
    outer_walls["south"]=south_outer
    outer_walls["east"]=east_outer
    outer_walls["west"]=west_outer
    # Defer adding to parts until after boolean cuts

    # ---- Inner courtyard walls (15x15) ----
    inner_walls = {}
    north_inner = create_box("Mahal_Inner_North", (15.0, WALL_T_IN, TOTAL_H), (0, COURTYARD/2 + WALL_T_IN/2, TOTAL_H/2))
    south_inner = create_box("Mahal_Inner_South", (15.0, WALL_T_IN, TOTAL_H), (0, -COURTYARD/2 - WALL_T_IN/2, TOTAL_H/2))
    east_inner = create_box("Mahal_Inner_East", (WALL_T_IN, 15.0, TOTAL_H), (COURTYARD/2 + WALL_T_IN/2, 0, TOTAL_H/2))
    west_inner = create_box("Mahal_Inner_West", (WALL_T_IN, 15.0, TOTAL_H), (-COURTYARD/2 - WALL_T_IN/2, 0, TOTAL_H/2))
    inner_walls["north"]=north_inner
    inner_walls["south"]=south_inner
    inner_walls["east"]=east_inner
    inner_walls["west"]=west_inner

    # ---- Boolean cuts for outer large arched entryways (3m wide, 4m tall) on all 4 sides ----
    # Arch dimensions: width 3.0, total height 4.0, rect 2.5, radius 1.5
    outer_arch_w=3.0
    outer_arch_radius=1.5
    outer_arch_rect=2.5
    # For north outer wall: center at (0, y=19.675)
    # Need orientation: width along X for north/south, along Y for east/west
    for side, wall in outer_walls.items():
        if side=="north":
            cx, cy=0, FOOTPRINT_D/2 - WALL_T_OUT/2
            cutter=create_arch_prism(f"OuterArch_{side}", outer_arch_w, outer_arch_rect, outer_arch_radius, WALL_T_OUT+1.0, cx, cy, 0, orientation="x", segments=14)
            apply_boolean_cut(wall, cutter)
        elif side=="south":
            cx, cy=0, -FOOTPRINT_D/2 + WALL_T_OUT/2
            cutter=create_arch_prism(f"OuterArch_{side}", outer_arch_w, outer_arch_rect, outer_arch_radius, WALL_T_OUT+1.0, cx, cy, 0, orientation="x", segments=14)
            apply_boolean_cut(wall, cutter)
        elif side=="east":
            cx, cy=FOOTPRINT_W/2 - WALL_T_OUT/2, 0
            cutter=create_arch_prism(f"OuterArch_{side}", outer_arch_w, outer_arch_rect, outer_arch_radius, WALL_T_OUT+1.0, cx, cy, 0, orientation="y", segments=14)
            apply_boolean_cut(wall, cutter)
        elif side=="west":
            cx, cy=-FOOTPRINT_W/2 + WALL_T_OUT/2, 0
            cutter=create_arch_prism(f"OuterArch_{side}", outer_arch_w, outer_arch_rect, outer_arch_radius, WALL_T_OUT+1.0, cx, cy, 0, orientation="y", segments=14)
            apply_boolean_cut(wall, cutter)

    # Now add outer walls to parts after cuts
    for w in outer_walls.values():
        parts.append((w,"sandstone"))

    # ---- Arches for inner courtyard Jharokhas — ground floor — using sin/cos loop ----
    # For each inner wall, generate 3 arches
    jharokha_w=2.2
    jharokha_radius=1.1
    jharokha_rect=1.9  # total ~3.0m
    # Inner walls positions: north at y=7.725, south -7.725, east 7.725, west -7.725
    # Generate arches via for loop with sin cos (already in create_arch_prism)
    arch_positions = [-4.5, 0.0, 4.5]  # offset along wall length
    for side, wall in inner_walls.items():
        if side in ("north","south"):
            # width along X
            cy = wall.location.y
            for idx, off in enumerate(arch_positions):
                cx = off
                cutter = create_arch_prism(f"Jharokha_{side}_{idx}", jharokha_w, jharokha_rect, jharokha_radius, WALL_T_IN+1.0, cx, cy, 0, orientation="x", segments=12)
                apply_boolean_cut(wall, cutter)
                # Also add decorative frame? Could add arch frame pillars but skip for poly count
        else: # east/west
            cx = wall.location.x
            for idx, off in enumerate(arch_positions):
                cy = off
                cutter = create_arch_prism(f"Jharokha_{side}_{idx}", jharokha_w, jharokha_rect, jharokha_radius, WALL_T_IN+1.0, cx, cy, 0, orientation="y", segments=12)
                apply_boolean_cut(wall, cutter)

    # Also add additional archways for interior passages at ground floor connecting rooms? Add doorway arches in east/west inner walls middle?
    # For now add inner walls after cuts to parts
    for w in inner_walls.values():
        parts.append((w,"sandstone"))

    # ---- Partition walls interior (to form rooms) ----
    # North wing partitions: 2 walls dividing 40 wide into 3 rooms
    for px in (-9.0, 9.0):
        # partition runs Y direction (north-south) length 12.5 (depth of north wing)
        # placed at x=px, y=13.75, height 5 per floor? But we make full height 15 for simplicity, but with door openings per floor
        # Create 3 separate walls per floor height? Simpler: create full height wall then cut door openings per floor
        part_wall = create_box(f"Partition_North_{int(px)}", (0.25, 12.5, TOTAL_H), (px, 13.75, TOTAL_H/2))
        # Cut door openings at each floor (ground, 5,10) — using arch cutters? Use rectangular cutters for interior doors
        for floor_z in (0.4, 5.0, 10.0):
            # door 1.2x2.2? Use simple box cutter 1.5x2.2
            cutter = create_box(f"PartDoorCutter_N_{int(px)}_{int(floor_z)}", (1.5, 0.8, 2.2), (px, 13.75, floor_z+1.1))
            apply_boolean_cut(part_wall, cutter)
        parts.append((part_wall,"sandstone"))

    south_partitions = []
    for px in (-9.0, 9.0):
        part_wall = create_box(f"Partition_South_{int(px)}", (0.25, 12.5, TOTAL_H), (px, -13.75, TOTAL_H/2))
        for floor_z in (0.4,5.0,10.0):
            cutter=create_box(f"PartDoorCutter_S_{int(px)}_{int(floor_z)}", (1.5,0.8,2.2), (px, -13.75, floor_z+1.1))
            apply_boolean_cut(part_wall, cutter)
        parts.append((part_wall,"sandstone"))

    # East wing horizontal partition dividing 15 depth into 2 rooms (at y=0)
    east_part = create_box("Partition_East", (12.5, 0.25, TOTAL_H), (13.75, 0, TOTAL_H/2))
    for floor_z in (0.4,5.0,10.0):
        cutter=create_box(f"PartDoorCutter_E_{int(floor_z)}", (0.8,1.5,2.2), (13.75, 0, floor_z+1.1))
        apply_boolean_cut(east_part, cutter)
    parts.append((east_part,"sandstone"))

    west_part = create_box("Partition_West", (12.5, 0.25, TOTAL_H), (-13.75, 0, TOTAL_H/2))
    for floor_z in (0.4,5.0,10.0):
        cutter=create_box(f"PartDoorCutter_W_{int(floor_z)}", (0.8,1.5,2.2), (-13.75, 0, floor_z+1.1))
        apply_boolean_cut(west_part, cutter)
    parts.append((west_part,"sandstone"))

    # ---- Balconies on 2nd and 3rd floors overlooking courtyard ----
    balcony_length=9.0
    balcony_depth=1.4
    balcony_levels=[5.0,10.0]  # floor tops
    for lvl in balcony_levels:
        # center z for balcony slab top at lvl, slab thickness 0.15
        bz = lvl - BALCONY_T/2.0
        # North balcony (south facing)
        north_bal = create_box(f"Balcony_North_L{int(lvl)}", (balcony_length, balcony_depth, BALCONY_T), (0, COURTYARD/2 - balcony_depth/2, bz))
        parts.append((north_bal,"sandstone"))
        south_bal = create_box(f"Balcony_South_L{int(lvl)}", (balcony_length, balcony_depth, BALCONY_T), (0, -COURTYARD/2 + balcony_depth/2, bz))
        parts.append((south_bal,"sandstone"))
        east_bal = create_box(f"Balcony_East_L{int(lvl)}", (balcony_depth, balcony_length, BALCONY_T), (COURTYARD/2 - balcony_depth/2, 0, bz))
        parts.append((east_bal,"sandstone"))
        west_bal = create_box(f"Balcony_West_L{int(lvl)}", (balcony_depth, balcony_length, BALCONY_T), (-COURTYARD/2 + balcony_depth/2, 0, bz))
        parts.append((west_bal,"sandstone"))

        # Carved railings for each balcony: add posts and rails
        # For north balcony: railing along south edge (courtyard side) + sides
        # Simplify: create 5 posts along length + top rail
        # For each balcony we add railing parts
        def add_balcony_railings(bal_obj, orientation):
            # orientation north/south: length along X, depth along Y, railing on courtyard side
            bx, by, bz_center = bal_obj.location.x, bal_obj.location.y, bal_obj.location.z
            blen = balcony_length
            bdepth = balcony_depth
            # Determine railing line: for north balcony, railing y = by - bdepth/2? Actually balcony south edge faces courtyard
            # Balcony center y = courtyard edge - depth/2, so courtyard edge = y? Let's compute:
            # North balcony center y = 7.5 -0.7 =6.8, south edge = 6.8 -0.7 =6.1? But we want railing at south edge
            # For generic, railing on inner side (toward center 0,0)
            if orientation=="north":
                rail_y = by - bdepth/2  # south edge
                rail_x_center=bx
                # posts along X
                for i in range(5):
                    px = rail_x_center - blen/2 + 0.3 + i*( (blen-0.6)/4 )
                    post = create_box(f"RailPost_N_{int(lvl)}_{i}", (0.12,0.12,0.9), (px, rail_y, bz_center+0.45))
                    parts.append((post,"sandstone"))
                # top rail
                rail = create_box(f"RailTop_N_{int(lvl)}", (blen,0.12,0.12), (rail_x_center, rail_y, bz_center+0.85))
                parts.append((rail,"sandstone"))
                rail_mid = create_box(f"RailMid_N_{int(lvl)}", (blen,0.08,0.08), (rail_x_center, rail_y, bz_center+0.45))
                parts.append((rail_mid,"sandstone"))
                # side rails
                for side_x in (-blen/2, blen/2):
                    side_rail = create_box(f"SideRail_N_{int(lvl)}_{int(side_x)}", (0.12, bdepth,0.12), (rail_x_center+side_x, by, bz_center+0.85))
                    parts.append((side_rail,"sandstone"))
            elif orientation=="south":
                rail_y = by + bdepth/2
                rail_x_center=bx
                for i in range(5):
                    px = rail_x_center - blen/2 +0.3 + i*((blen-0.6)/4)
                    post=create_box(f"RailPost_S_{int(lvl)}_{i}", (0.12,0.12,0.9), (px, rail_y, bz_center+0.45))
                    parts.append((post,"sandstone"))
                rail=create_box(f"RailTop_S_{int(lvl)}", (blen,0.12,0.12), (rail_x_center, rail_y, bz_center+0.85))
                parts.append((rail,"sandstone"))
                rail_mid=create_box(f"RailMid_S_{int(lvl)}", (blen,0.08,0.08), (rail_x_center, rail_y, bz_center+0.45))
                parts.append((rail_mid,"sandstone"))
                for side_x in (-blen/2, blen/2):
                    side_rail=create_box(f"SideRail_S_{int(lvl)}_{int(side_x)}", (0.12,bdepth,0.12), (rail_x_center+side_x, by, bz_center+0.85))
                    parts.append((side_rail,"sandstone"))
            elif orientation=="east":
                rail_x = bx - bdepth/2
                rail_y_center=by
                for i in range(5):
                    py = rail_y_center - blen/2 +0.3 + i*((blen-0.6)/4)
                    post=create_box(f"RailPost_E_{int(lvl)}_{i}", (0.12,0.12,0.9), (rail_x, py, bz_center+0.45))
                    parts.append((post,"sandstone"))
                rail=create_box(f"RailTop_E_{int(lvl)}", (0.12, blen,0.12), (rail_x, rail_y_center, bz_center+0.85))
                parts.append((rail,"sandstone"))
                rail_mid=create_box(f"RailMid_E_{int(lvl)}", (0.08, blen,0.08), (rail_x, rail_y_center, bz_center+0.45))
                parts.append((rail_mid,"sandstone"))
                for side_y in (-blen/2, blen/2):
                    side_rail=create_box(f"SideRail_E_{int(lvl)}_{int(side_y)}", (bdepth,0.12,0.12), (bx, rail_y_center+side_y, bz_center+0.85))
                    parts.append((side_rail,"sandstone"))
            elif orientation=="west":
                rail_x = bx + bdepth/2
                rail_y_center=by
                for i in range(5):
                    py = rail_y_center - blen/2 +0.3 + i*((blen-0.6)/4)
                    post=create_box(f"RailPost_W_{int(lvl)}_{i}", (0.12,0.12,0.9), (rail_x, py, bz_center+0.45))
                    parts.append((post,"sandstone"))
                rail=create_box(f"RailTop_W_{int(lvl)}", (0.12, blen,0.12), (rail_x, rail_y_center, bz_center+0.85))
                parts.append((rail,"sandstone"))
                rail_mid=create_box(f"RailMid_W_{int(lvl)}", (0.08, blen,0.08), (rail_x, rail_y_center, bz_center+0.45))
                parts.append((rail_mid,"sandstone"))
                for side_y in (-blen/2, blen/2):
                    side_rail=create_box(f"SideRail_W_{int(lvl)}_{int(side_y)}", (bdepth,0.12,0.12), (bx, rail_y_center+side_y, bz_center+0.85))
                    parts.append((side_rail,"sandstone"))

        add_balcony_railings(north_bal,"north")
        add_balcony_railings(south_bal,"south")
        add_balcony_railings(east_bal,"east")
        add_balcony_railings(west_bal,"west")

    # ---- Stairs connecting floors and roof (grand marble stairs) ----
    # Two grand staircases: East and West wings
    # Each has 3 flights: ground->5, 5->10, 10->15
    # Using STAIR_W=2.2, STEP_DEPTH via tan(30)
    stair_systems=[]
    # East system at x=13.75 (center of east wing)
    east_x=13.75
    west_x=-13.75
    # Y start positions:
    # For Y-running stairs, Y start near south side of wing
    y_start_east = -5.5
    y_start_west = -5.5
    # For each level
    for lvl_idx, (base_z, target_z) in enumerate([(0,5.0),(5.0,10.0),(10.0,15.0)]):
        slab_level = target_z  # hole in this level's slab
        # East flight
        east_boxes, east_hole = stair_flight(f"EastStair_F{lvl_idx}", east_x, y_start_east, +1, base_z, target_z)
        # West flight
        west_boxes, west_hole = stair_flight(f"WestStair_F{lvl_idx}", west_x, y_start_west, +1, base_z, target_z)
        # Cut holes in the target slab (which is at target_z)
        # slab_objs_by_level has 4 wing slabs per level, but stair holes are in east/west wing slabs specifically
        # East wing slab at target level is east object; west similarly
        east_slab = None
        west_slab = None
        for o in slab_objs_by_level[target_z]:
            # east slabs have x~13.75, west -13.75; north/south have y 13.75
            if abs(o.location.x - 13.75) < 0.1:
                east_slab=o
            if abs(o.location.x +13.75) <0.1:
                west_slab=o
        # Note: east_slab exists for levels 5,10,15, west similarly
        if east_slab:
            # Find which slab to cut: need to identify the correct slab piece for hole y position
            # But slab is 12.5x15 at (13.75,0) — hole y_center ~1.6 which lies within slab Y range -7.5..7.5 OK
            cut_stair_hole(east_slab, east_hole, target_z - SLAB_T/2.0, SLAB_T)
        if west_slab:
            cut_stair_hole(west_slab, west_hole, target_z - SLAB_T/2.0, SLAB_T)

        # Add stair boxes to parts as marble
        for b in east_boxes:
            parts.append((b,"marble"))
        for b in west_boxes:
            parts.append((b,"marble"))
        stair_systems.append((east_boxes, east_hole))
        stair_systems.append((west_boxes, west_hole))

    # ---- Roof parapet (outer edge and inner courtyard edge) ----
    # Outer parapet: 4 walls on roof edge height 1.0 thickness 0.4
    parapet_h=1.0
    parapet_t=0.35
    # Outer
    north_para_outer = create_box("Parapet_North_Outer", (40.0, parapet_t, parapet_h), (0, FOOTPRINT_D/2 - parapet_t/2, TOTAL_H+parapet_h/2))
    south_para_outer = create_box("Parapet_South_Outer", (40.0, parapet_t, parapet_h), (0, -FOOTPRINT_D/2 + parapet_t/2, TOTAL_H+parapet_h/2))
    east_para_outer = create_box("Parapet_East_Outer", (parapet_t, FOOTPRINT_D-2*parapet_t, parapet_h), (FOOTPRINT_W/2 - parapet_t/2, 0, TOTAL_H+parapet_h/2))
    west_para_outer = create_box("Parapet_West_Outer", (parapet_t, FOOTPRINT_D-2*parapet_t, parapet_h), (-FOOTPRINT_W/2 + parapet_t/2, 0, TOTAL_H+parapet_h/2))
    # Add crenellations (battlements) for sniping spots: create notches? Add alternating merlons
    # Simpler add small boxes on top as cover crenellations? We'll add merlon blocks
    # For each outer para, add merlons every 2m
    def add_merlons(para_obj, orientation):
        px,py,pz = para_obj.location.x, para_obj.location.y, para_obj.location.z
        dims = para_obj.dimensions
        # orientation north/south => length along X
        if orientation in ("north","south"):
            length = dims.x
            count = int(length//2.0)  # every 2m
            for i in range(-count//2, count//2+1):
                x = i*2.0
                # Alternate high/low for crenellation
                if i%2==0:
                    merlon = create_box(f"Merlon_{orientation}_{i}", (0.8, parapet_t, 0.5), (x, py, TOTAL_H + parapet_h +0.25))
                    parts.append((merlon,"sandstone"))
        else:
            length = dims.y
            count = int(length//2.0)
            for i in range(-count//2, count//2+1):
                y = i*2.0
                if i%2==0:
                    merlon = create_box(f"Merlon_{orientation}_{i}", (parapet_t,0.8,0.5), (px, y, TOTAL_H+parapet_h+0.25))
                    parts.append((merlon,"sandstone"))

    parts += [(north_para_outer,"sandstone"), (south_para_outer,"sandstone"), (east_para_outer,"sandstone"), (west_para_outer,"sandstone")]
    add_merlons(north_para_outer,"north")
    add_merlons(south_para_outer,"south")
    add_merlons(east_para_outer,"east")
    add_merlons(west_para_outer,"west")

    # Inner courtyard parapet (around courtyard opening, height 1.0)
    inner_para_t=0.3
    north_para_inner = create_box("Parapet_North_Inner", (15.0, inner_para_t, parapet_h), (0, COURTYARD/2 + inner_para_t/2, TOTAL_H+parapet_h/2))
    south_para_inner = create_box("Parapet_South_Inner", (15.0, inner_para_t, parapet_h), (0, -COURTYARD/2 - inner_para_t/2, TOTAL_H+parapet_h/2))
    east_para_inner = create_box("Parapet_East_Inner", (inner_para_t, 15.0, parapet_h), (COURTYARD/2 + inner_para_t/2, 0, TOTAL_H+parapet_h/2))
    west_para_inner = create_box("Parapet_West_Inner", (inner_para_t, 15.0, parapet_h), (-COURTYARD/2 - inner_para_t/2, 0, TOTAL_H+parapet_h/2))
    parts += [(north_para_inner,"sandstone"), (south_para_inner,"sandstone"), (east_para_inner,"sandstone"), (west_para_inner,"sandstone")]

    # ---- Domes (Gumbad) at four corners ----
    dome_radius=2.8
    drum_h=1.0
    corner_inset=16.0  # distance from center to dome center (outer 20 - inset)
    corners=[(corner_inset, corner_inset), (-corner_inset, corner_inset), (corner_inset, -corner_inset), (-corner_inset, -corner_inset)]
    for idx, (dx, dy) in enumerate(corners):
        # Drum cylinder
        drum = create_cylinder(f"DomeDrum_{idx}", dome_radius, drum_h, (dx, dy, TOTAL_H + drum_h/2), vertices=20)
        parts.append((drum,"sandstone"))
        # Dome hemisphere: create icosphere then scale and cut bottom? Use primitive and delete lower half via geometry? Simpler: use half-icosphere by scaling? We'll create icosphere and position so bottom at drum top, but we need half sphere.
        # Create full icosphere, then we can keep upper half by moving vertices? Alternative: use uv sphere with half.
        # Easiest: bpy.ops.mesh.primitive_uv_sphere_add with half? But we want low poly half-icosphere.
        # We will create icosphere radius dome_radius at (dx,dy, TOTAL_H+drum_h) then after creation we can delete lower hemispheres via bmesh? Simpler to create icosphere and then scale bottom vertices to flatten? Or use primitive with 2 subdivisions and then move logic.
        # Instead, create icosphere and then set scale Z to 0.7 for flattened look and keep full sphere but bottom hidden inside drum? That will look like dome plus bottom hidden.
        # To make half visible, we can make sphere at (dx,dy, TOTAL_H+drum_h) with radius, but the lower half will intersect drum and be hidden? For low poly, we can just create ico sphere and hide lower half inside slab? Not perfect but okay.
        # Better: create UV sphere with rings and cut.
        # Use icosphere then delete bottom half using bmesh operation for cleaner.
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=dome_radius, location=(dx, dy, TOTAL_H+drum_h))
        dome_obj = bpy.context.active_object
        dome_obj.name=f"Dome_{idx}"
        dome_obj.data.name=f"Dome_{idx}Mesh"
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        # Delete lower half vertices with bmesh
        import bmesh as bm_mod
        bpy.ops.object.select_all(action="DESELECT")
        dome_obj.select_set(True)
        bpy.context.view_layer.objects.active=dome_obj
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(dome_obj.data)
        # Find vertices below center
        to_delete=[]
        for v in bm.verts:
            # world z via v.co (local since applied)
            if v.co.z < 0.01:  # below center (relative to object location)
                to_delete.append(v)
        # Also delete faces where center below
        if to_delete:
            # select and delete
            for v in to_delete:
                v.select=True
            bm.select_mode = {'VERT'}
            bm.select_flush(True)
            # delete verts
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.select], context='VERTS')
        bmesh.update_edit_mesh(dome_obj.data)
        bpy.ops.object.mode_set(mode="OBJECT")
        # Flatten slightly? Scale Z 0.8 for traditional dome flattened
        dome_obj.scale = (1,1,0.85)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        # Move dome up slightly to sit on drum: center already at drum top, with scale we need adjust
        # Already set location at drum top, scaling keeps center
        parts.append((dome_obj,"gold"))
        # Add small spire on top
        spire = create_cylinder(f"DomeSpire_{idx}", 0.08, 0.8, (dx, dy, TOTAL_H+drum_h + dome_radius*0.85 +0.4), vertices=8)
        parts.append((spire,"gold"))
        # Add base lotus petal ring? Skip

    # ---- Chhatris (small pavilions with pillars and small domes) on roof edges ----
    # 8 chhatris: 2 per side along outer edge but inset
    chhatri_positions=[]
    # North side 2
    chhatri_positions += [(-10, 16.0), (10,16.0)]
    # South side 2
    chhatri_positions += [(-10, -16.0), (10,-16.0)]
    # East side 2
    chhatri_positions += [(16.0, -10), (16.0,10)]
    # West side 2
    chhatri_positions += [(-16.0, -10), (-16.0,10)]

    for idx, (cx, cy) in enumerate(chhatri_positions):
        # 4 pillars
        pillar_h=1.6
        pillar_sz=0.18
        half=0.85  # half size of pavilion 1.7x1.7
        for sx in (-1,1):
            for sy in (-1,1):
                px = cx + sx*half
                py = cy + sy*half
                pill = create_box(f"ChhatriPillar_{idx}_{sx}_{sy}", (pillar_sz, pillar_sz, pillar_h), (px, py, TOTAL_H + pillar_h/2))
                parts.append((pill,"sandstone"))
        # Top slab (chajja)
        top_slab = create_box(f"ChhatriTop_{idx}", (2.2,2.2,0.18), (cx, cy, TOTAL_H + pillar_h +0.09))
        parts.append((top_slab,"sandstone"))
        # Small dome
        small_r=0.9
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=small_r, location=(cx, cy, TOTAL_H + pillar_h +0.18))
        s_dome=bpy.context.active_object
        s_dome.name=f"ChhatriDome_{idx}"
        s_dome.data.name=f"ChhatriDome_{idx}Mesh"
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        # Delete lower half similarly
        import bmesh as bm_mod2
        bpy.ops.object.select_all(action="DESELECT")
        s_dome.select_set(True)
        bpy.context.view_layer.objects.active=s_dome
        bpy.ops.object.mode_set(mode="EDIT")
        bm = bmesh.from_edit_mesh(s_dome.data)
        to_del=[]
        for v in bm.verts:
            if v.co.z < 0.01:
                to_del.append(v)
        if to_del:
            for v in to_del:
                v.select=True
            bm.select_mode={'VERT'}
            bm.select_flush(True)
            bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.select], context='VERTS')
        bmesh.update_edit_mesh(s_dome.data)
        bpy.ops.object.mode_set(mode="OBJECT")
        s_dome.scale=(1,1,0.75)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
        parts.append((s_dome,"gold"))

    # ---- Corner towers? Already domes ----
    # Add corner bastion octagonal towers? Skip to keep poly low, but we have outer walls.

    # ---- Interior wooden crates for cover ----
    crate_positions=[]
    # North wing ground floor crates
    crate_positions += [(-13, 13.75, 0.4), (13,13.75,0.4), (0,16,0.4)]
    # South wing
    crate_positions += [(-12,-13.75,0.4),(12,-13.75,0.4)]
    # East/west wing upper floors
    crate_positions += [(13.75, 5,5.0),(13.75,-5,10.0), (-13.75,5,5.0)]
    for idx,(cx,cy,cz) in enumerate(crate_positions):
        for j in range(2):
            c = create_box(f"Crate_{idx}_{j}", (0.85,0.85,0.85), (cx + rng.uniform(-0.6,0.6), cy + rng.uniform(-0.6,0.6), cz+0.425 + j*0.85), rotation=(0,0,math.radians(rng.uniform(-20,20))))
            parts.append((c,"wood"))
        # Add single crate stacks on roof for cover
    # Roof crates for sniper cover
    for idx,(cx,cy) in enumerate([(0,0),(8,8),(-8,8),(8,-8),(-8,-8)]):
        # Place on roof at TOTAL_H top
        c = create_box(f"RoofCrate_{idx}", (1.0,1.0,1.0), (cx, cy, TOTAL_H+0.5), rotation=(0,0,0))
        parts.append((c,"wood"))

    # ---- OmniLights interior ----
    # We'll add lights after join, but we need positions before origin shift
    # Define lights: per wing per floor
    light_specs=[]
    # Ground floor lights
    light_specs += [((0,13.75,2.5),200), ((0,-13.75,2.5),200), ((13.75,0,2.5),180), ((-13.75,0,2.5),180)]
    # Second floor
    light_specs += [((0,13.75,7.5),180), ((0,-13.75,7.5),180), ((13.75,0,7.5),160), ((-13.75,0,7.5),160)]
    # Third floor
    light_specs += [((0,13.75,12.5),160), ((0,-13.75,12.5),160)]
    # Courtyard central light near fountain (warm)
    light_specs += [((0,0,6.0),120)]
    # Roof lights? not needed

    # Save lights to add after origin

    # ---- Assign materials via unwrap ----
    # For fountain water solid we want separate solid material handling
    # We'll separate water object to use solid
    # Find water object and assign solid later
    # Prepare material mapping for each part
    # Need to handle fountain_water with solid blue
    # Let's identify fountain_water in parts list: it currently has marble, replace with solid
    # We'll after loop handle special

    # Create solid blue for fountain water
    water_blue = make_solid_material("FountainWater", {"rgba":(0.25,0.55,0.85,1.0)}, roughness=0.25)

    # Unwrap and assign
    materials_map={}
    for obj, preset in parts:
        # Special case: fountain_water name contains Fountain_Water
        if "Fountain_Water" in obj.name:
            smart_unwrap(obj, density_for("wood"))
            obj.data.materials.clear()
            obj.data.materials.append(water_blue)
            continue
        # Normal presets
        if preset in MATERIALS:
            if preset not in materials_map:
                materials_map[preset]=make_material(f"Mahal_{preset}", preset)
            smart_unwrap(obj, density_for(preset))
            obj.data.materials.clear()
            obj.data.materials.append(materials_map[preset])
        else:
            # fallback wood
            if "wood" not in materials_map:
                materials_map["wood"]=make_material("Mahal_wood", "wood")
            smart_unwrap(obj, density_for("wood"))
            obj.data.materials.clear()
            obj.data.materials.append(materials_map["wood"])

    # Join all mesh parts into one object
    mesh_objs=[o for o,_ in parts]  # but parts includes all; we need to handle water? Keep together
    # Note: fountain water is also mesh, keep
    joined=join_objects(mesh_objs, "MahalPalace")
    set_origin_bottom_center(joined)

    # Add OmniLights (after origin shift, positions are still in local space origin bottom-center)
    for (lx,ly,lz), energy in light_specs:
        add_omni_light(f"Mahal_Omni_{lx}_{ly}", (lx,ly,lz), energy=energy, color=(1.0,0.88,0.62))

    return joined

def export_glb(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    kwargs=dict(filepath=path, export_format="GLB", export_image_format="JPEG", export_lights=True)
    try:
        bpy.ops.export_scene.gltf(export_image_quality=90, **kwargs)
    except TypeError:
        bpy.ops.export_scene.gltf(**kwargs)
    if not os.path.isfile(path):
        raise RuntimeError(f"Export failed: {path}")
    return path

def verify_glb(path):
    with open(path,"rb") as fh:
        data=fh.read()
    if data[:4]!=b"glTF":
        raise RuntimeError("Not GLB")
    json_len=struct.unpack("<I", data[12:16])[0]
    gltf=json.loads(data[20:20+json_len])
    images=gltf.get("images",[])
    if not images:
        raise RuntimeError("No packed images")
    for img in images:
        if "bufferView" not in img and "uri" not in img:
            raise RuntimeError(f"Image not embedded: {img}")
    tris=0
    for mesh in gltf.get("meshes",[]):
        for prim in mesh.get("primitives",[]):
            if "indices" in prim:
                count=gltf["accessors"][prim["indices"]]["count"]
            else:
                count=gltf["accessors"][prim["attributes"]["POSITION"]]["count"]
            tris+=count//3
    lights=sum(1 for n in gltf.get("nodes",[]) if "KHR_lights_punctual" in n.get("extensions",{}))
    mapped=sum(1 for m in gltf.get("materials",[]) if "KHR_texture_transform" in m.get("pbrMetallicRoughness",{}).get("baseColorTexture",{}).get("extensions",{}))
    stats={"bytes":os.path.getsize(path),"materials":len(gltf.get("materials",[])),"images":len(images),"tris":tris,"lights":lights,"mapped":mapped}
    print(f"  verified {os.path.basename(path)}: {stats['bytes']} bytes, {stats['materials']} mats ({stats['mapped']} mapped), {stats['images']} imgs, ~{stats['tris']} tris, {stats['lights']} lights")
    return stats

def main():
    print(f"Blender bpy {bpy.app.version_string}")
    print(f"Stair math: rise={STAIR_RISE}, angle=30deg, step_depth=rise/tan(30)={STEP_DEPTH:.4f} m, hole={HOLE_LEN}x{HOLE_W}")
    print("Ensuring textures ...")
    ensure_textures()
    print("Building Mahal Palace ...")
    clear_scene()
    set_metric_units()
    obj=build_mahal()
    x0,x1,y0,y1,z0,z1=object_bbox(obj)
    print(f"  MahalPalace: {x1-x0:.2f} x {y1-y0:.2f} x {z1-z0:.2f} | {len(obj.data.polygons)} faces | origin (0,0,0) bottom-center")
    path=os.path.join(OUTPUT_DIR, "mahal_palace.glb")
    export_glb(path)
    verify_glb(path)
    print("Done — Mahal Palace generated.")
    return 0

if __name__=="__main__":
    sys.exit(main())
