#!/usr/bin/env python3
"""Elite Cargo Dropship — "Indus Ascendant" — bpy generator.

Builds the next-gen stealth cargo plane used in the Battle Royale drop
sequence and exports a single game-ready GLB:

    docs/models/vehicles/plane_cargo_elite.glb

Design brief
------------
* 45.0 m wingspan x 35.0 m overall length (lowered rear ramp included).
* Blended-wing-body, chined/faceted stealth fuselage (no round tube).
* Four massive octagonal engine nacelles with emissive cyan + orange
  thrusters, intake fans and vectoring nozzle petals.
* Sleek faceted canopy in deep tinted glass, nose sensor pods.
* Swept wings with canted winglets and two under-wing drop tanks.
* Canted twin tails, dorsal spine, many hull/wing access panels, vent
  banks, blade antennas and navigation / formation lights.
* Rear cargo bay opened by a real Boolean cut, with an interior
  (ribs, ceiling lights, crates), a wide lowered ramp and red/green
  indicator lights around the opening.
* NO textures anywhere: 12 solid Principled BSDF materials using the
  requested palette (#2C2E33 body, lighter access panels, neon cyan,
  ember orange, tinted glass).
* One joined mesh, flat shaded, origin at bottom-centre (0, 0, 0).

Run:
    pip install bpy
    python tools/generate_plane_cargo_elite.py
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
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "vehicles")
OUT_PATH = os.path.join(OUT_DIR, "plane_cargo_elite.glb")

TARGET_SPAN = 45.0       # X, wingtip to wingtip
TARGET_LENGTH = 35.0     # Y, nose tip to lowered-ramp tip
RNG = random.Random(20261021)

# ---------------------------------------------------------------------------
# Palette — hex is sRGB, converted to linear so the GLB displays the
# requested colour exactly (glTF baseColorFactor is linear).
# ---------------------------------------------------------------------------
PALETTE = {
    "body":     {"hex": "2C2E33", "metallic": 0.55, "roughness": 0.62},
    "panel":    {"hex": "4A4E57", "metallic": 0.60, "roughness": 0.42},
    "dark":     {"hex": "15171B", "metallic": 0.45, "roughness": 0.48},
    "edge":     {"hex": "78808C", "metallic": 0.85, "roughness": 0.28},
    "engine":   {"hex": "1B1D22", "metallic": 0.78, "roughness": 0.30},
    "glass":    {"hex": "123A66", "metallic": 0.80, "roughness": 0.10},
    "interior": {"hex": "23262C", "metallic": 0.35, "roughness": 0.70},
    "cyan":     {"hex": "21E6FF", "metallic": 0.10, "roughness": 0.25,
                 "emission": "21E6FF", "strength": 5.0},
    "orange":   {"hex": "FF7A18", "metallic": 0.10, "roughness": 0.30,
                 "emission": "FF7A18", "strength": 6.0},
    "red":      {"hex": "FF2B36", "metallic": 0.10, "roughness": 0.30,
                 "emission": "FF2B36", "strength": 6.0},
    "green":    {"hex": "35FF6E", "metallic": 0.10, "roughness": 0.30,
                 "emission": "35FF6E", "strength": 6.0},
    "white":    {"hex": "DFF6FF", "metallic": 0.10, "roughness": 0.25,
                 "emission": "DFF6FF", "strength": 5.0},
}

_MATERIALS: dict[str, object] = {}
_PARTS: list = []


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def srgb_to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def hex_to_linear_rgba(value: str) -> tuple[float, float, float, float]:
    value = value.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), 1.0)


def set_bsdf_input(bsdf, names, value) -> bool:
    for name in names:
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = value
            return True
    return False


def make_material(key: str):
    if key in _MATERIALS:
        return _MATERIALS[key]
    spec = PALETTE[key]
    mat = bpy.data.materials.new(f"PLANE_{key}")
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    mat.use_backface_culling = False
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError("Principled BSDF not found")
    rgba = hex_to_linear_rgba(spec["hex"])
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Metallic"].default_value = spec["metallic"]
    bsdf.inputs["Roughness"].default_value = spec["roughness"]
    if "emission" in spec:
        er, eg, eb, _ = hex_to_linear_rgba(spec["emission"])
        set_bsdf_input(bsdf, ("Emission Color", "Emission"), (er, eg, eb, 1.0))
        set_bsdf_input(bsdf, ("Emission Strength",), spec["strength"])
        # make the solid colour read as neon even under flat viewer lighting
        bsdf.inputs["Base Color"].default_value = (er, eg, eb, 1.0)
    mat.diffuse_color = rgba
    _MATERIALS[key] = mat
    return mat


def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _MATERIALS.clear()
    _PARTS.clear()
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0


def register(obj, material_key: str | None = None):
    if material_key is not None:
        obj.data.materials.clear()
        obj.data.materials.append(make_material(material_key))
    for poly in obj.data.polygons:
        poly.use_smooth = False
    _PARTS.append(obj)
    return obj


def mesh_object(name: str, verts, faces, material_key: str):
    me = bpy.data.meshes.new(name + "Mesh")
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.validate(clean_customdata=True)
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return register(obj, material_key)


def recalc_normals(obj, closed: bool = True) -> None:
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    if closed:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


BOX_FACES = (
    (0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1),
    (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3),
)


def box(name: str, size, location, material_key: str, rotation=(0.0, 0.0, 0.0)):
    dx, dy, dz = (s * 0.5 for s in size)
    verts = [
        (-dx, -dy, -dz), (dx, -dy, -dz), (-dx, dy, -dz), (dx, dy, -dz),
        (-dx, -dy, dz), (dx, -dy, dz), (-dx, dy, dz), (dx, dy, dz),
    ]
    obj = mesh_object(name, verts, BOX_FACES, material_key)
    obj.location = Vector(location)
    obj.rotation_euler = rotation
    recalc_normals(obj, closed=True)
    return obj


def oriented_box(name: str, size, origin, axes, material_key: str):
    """Box whose local X/Y/Z match the given world-space unit vectors, so
    greebles can sit flush on a curved hull instead of floating."""
    ax, ay, az = (Vector(a).normalized() for a in axes)
    obj = box(name, size, (0.0, 0.0, 0.0), material_key)
    obj.matrix_world = Matrix((
        (ax.x, ay.x, az.x),
        (ax.y, ay.y, az.y),
        (ax.z, ay.z, az.z),
    )).to_4x4()
    obj.location = Vector(origin)
    return obj


def hull_axes(y: float, kf: float):
    p = hull_point(y, kf)
    t_k = (hull_point(y, kf + 0.06) - hull_point(y, kf - 0.06)).normalized()
    t_y = Vector((0.0, 1.0, 0.0))
    n = t_k.cross(t_y).normalized()
    center = Vector((0.0, y, hull_params(y)[2]))
    if n.dot(p - center) < 0:
        n = -n
    # keep the tangent frame right-handed (x = across, y = fore/aft, z = out)
    return t_k, t_y, n, p


def hull_greeble(name, y, kf, width, length, height, material_key,
                 offset: float = 0.0, shift_y: float = 0.0):
    ax, ay, az, p = hull_axes(y, kf)
    return oriented_box(name, (width, length, height), p + az * (offset + height * 0.5),
                        (ax, ay, az), material_key)


def beam(name: str, p1, p2, width: float, thickness: float, material_key: str):
    p1, p2 = Vector(p1), Vector(p2)
    direction = p2 - p1
    length = direction.length
    if length < 1e-5:
        return None
    obj = box(name, (width, length, thickness), (p1 + p2) * 0.5, material_key)
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("Y", "Z")
    return obj


def cylinder(name, radius, depth, location, material_key, axis="Y",
             vertices=12, rotation_extra=0.0):
    rot = {"Z": (0.0, 0.0, 0.0), "Y": (math.pi / 2.0, 0.0, 0.0),
           "X": (0.0, math.pi / 2.0, 0.0)}[axis]
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, end_fill_type="NGON",
        location=Vector(location), rotation=rot,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "Mesh"
    if rotation_extra:
        obj.rotation_euler.rotate_axis("Y", rotation_extra)
    return register(obj, material_key)


def cone(name, r1, r2, depth, location, material_key, axis="Y", vertices=12):
    rot = {"Z": (0.0, 0.0, 0.0), "Y": (math.pi / 2.0, 0.0, 0.0),
           "X": (0.0, math.pi / 2.0, 0.0)}[axis]
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices, radius1=r1, radius2=r2, depth=depth,
        end_fill_type="NGON", location=Vector(location), rotation=rot,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "Mesh"
    return register(obj, material_key)


def ico(name, radius, location, material_key, subdivisions=2):
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=subdivisions, radius=radius, location=Vector(location))
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "Mesh"
    return register(obj, material_key)


def torus(name, major_radius, minor_radius, location, material_key,
          axis="Y", major_segments=16, minor_segments=4):
    rot = {"Z": (0.0, 0.0, 0.0), "Y": (math.pi / 2.0, 0.0, 0.0),
           "X": (0.0, math.pi / 2.0, 0.0)}[axis]
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius, minor_radius=minor_radius,
        major_segments=major_segments, minor_segments=minor_segments,
        location=Vector(location), rotation=rot,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name + "Mesh"
    return register(obj, material_key)


def bevel(obj, width: float, segments: int = 1) -> None:
    mod = obj.modifiers.new("EdgeChamfer", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.limit_method = "ANGLE"
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def loft(name: str, rings, material_key: str, cap_start=True, cap_end=True):
    count = len(rings[0])
    verts = [p for ring in rings for p in ring]
    faces = []
    for r in range(len(rings) - 1):
        a0 = r * count
        b0 = (r + 1) * count
        for k in range(count):
            k2 = (k + 1) % count
            faces.append((a0 + k, a0 + k2, b0 + k2, b0 + k))
    if cap_start:
        faces.append(tuple(range(count - 1, -1, -1)))
    if cap_end:
        base = (len(rings) - 1) * count
        faces.append(tuple(base + k for k in range(count)))
    obj = mesh_object(name, verts, faces, material_key)
    recalc_normals(obj, closed=True)
    return obj


def ring_of_points(center, radius_x, radius_z, sides=8, phase=math.pi / 8.0):
    cx, cy, cz = center
    return [
        (cx + radius_x * math.cos(phase + 2 * math.pi * i / sides), cy,
         cz + radius_z * math.sin(phase + 2 * math.pi * i / sides))
        for i in range(sides)
    ]


# ---------------------------------------------------------------------------
# Fuselage / blended wing body
# ---------------------------------------------------------------------------
HULL_PROFILE = [
    (0.00, 1.00), (0.36, 0.95), (0.68, 0.74), (0.92, 0.38),
    (1.00, 0.00), (0.92, -0.38), (0.66, -0.74), (0.35, -0.94),
    (0.00, -1.00), (-0.35, -0.94), (-0.66, -0.74), (-0.92, -0.38),
    (-1.00, 0.00), (-0.92, 0.38), (-0.68, 0.74), (-0.36, 0.95),
]
HULL_STATIONS = [
    # (y, half_width, half_height, centre_z)
    (-17.50, 0.16, 0.15, 4.10),
    (-17.10, 0.52, 0.40, 4.08),
    (-16.20, 0.98, 0.72, 4.05),
    (-15.00, 1.52, 1.12, 4.02),
    (-13.00, 2.22, 1.54, 3.98),
    (-10.00, 2.93, 1.90, 3.94),
    (-6.00, 3.53, 2.18, 3.90),
    (-1.00, 3.85, 2.30, 3.86),
    (4.00, 3.80, 2.30, 3.84),
    (9.00, 3.45, 2.20, 3.88),
    (12.00, 3.15, 2.05, 3.92),
    (13.80, 2.90, 1.92, 3.96),
]
HULL_N = len(HULL_PROFILE)
HULL_LAST_Y = HULL_STATIONS[-1][0]


def hull_params(y: float):
    if y <= HULL_STATIONS[0][0]:
        return HULL_STATIONS[0][1:]
    if y >= HULL_STATIONS[-1][0]:
        return HULL_STATIONS[-1][1:]
    for i in range(len(HULL_STATIONS) - 1):
        y0, w0, h0, c0 = HULL_STATIONS[i]
        y1, w1, h1, c1 = HULL_STATIONS[i + 1]
        if y0 <= y <= y1:
            t = (y - y0) / (y1 - y0)
            return (
                w0 + (w1 - w0) * t,
                h0 + (h1 - h0) * t,
                c0 + (c1 - c0) * t,
            )
    return HULL_STATIONS[-1][1:]


def profile_point(kf: float):
    kf = kf % HULL_N
    i = int(math.floor(kf))
    t = kf - i
    p0 = HULL_PROFILE[i]
    p1 = HULL_PROFILE[(i + 1) % HULL_N]
    return (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)


def hull_point(y: float, kf: float, offset: float = 0.0):
    px, pz = profile_point(kf)
    w, h, zc = hull_params(y)
    x = px * w
    z = zc + pz * h
    nx = px / max(w, 1e-6)
    nz = pz / max(h, 1e-6)
    n = Vector((nx, 0.0, nz))
    if n.length > 1e-9:
        n.normalize()
    return Vector((x, y, z)) + n * offset


def hull_top(y: float) -> float:
    return hull_params(y)[2] + hull_params(y)[1]


def hull_ring(y: float, offset=0.0):
    return [hull_point(y, k, offset) for k in range(HULL_N)]


def build_hull():
    rings = [hull_ring(y) for y, *_ in HULL_STATIONS]
    hull = loft("Fuselage", rings, "body")
    return hull


def open_cargo_bay(hull):
    """Boolean-cut the rear cargo opening.  Returns the cutter bbox for checks."""
    cutter = box("CargoBayCutter", (4.84, 7.6, 2.65), (0, 12.0, 3.875), "dark")
    bevel(cutter, 0.26, 1)
    mod = hull.modifiers.new("CargoBayBoolean", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter
    bpy.context.view_layer.objects.active = hull
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    hull.data.update()

    # Ray from behind the aircraft, through the opening, along -Y.  It must
    # reach the forward void wall instead of stopping on a closed rear face.
    depsgraph = bpy.context.evaluated_depsgraph_get()
    bvh = BVHTree.FromObject(hull, depsgraph)
    hit, normal, index, dist = bvh.ray_cast(Vector((0.0, 19.0, 3.9)), Vector((0.0, -1.0, 0.0)), 40.0)
    if hit is None:
        raise RuntimeError("Cargo Boolean failed: ray passed through no geometry")
    if hit.y > 12.5:
        raise RuntimeError(f"Cargo Boolean failed: rear wall still closed at y={hit.y:.2f}")
    print(f"  Boolean verified: rear ramp opening is open, ray hit interior wall at y={hit.y:.2f}")
    return hull


# ---------------------------------------------------------------------------
# Surface details on the hull
# ---------------------------------------------------------------------------
def hull_ribbon_longitudinal(name, kf, y0, y1, width_k, offset, material_key, segments=12):
    verts = []
    faces = []
    for i in range(segments + 1):
        y = y0 + (y1 - y0) * i / segments
        verts.append(hull_point(y, kf - width_k, offset))
        verts.append(hull_point(y, kf + width_k, offset))
    for i in range(segments):
        a = i * 2
        faces.append((a, a + 1, a + 3, a + 2))
    obj = mesh_object(name, verts, faces, material_key)
    return obj


def hull_ribbon_ring(name, y, half_width, offset, material_key):
    verts = []
    for yy in (y - half_width, y + half_width):
        verts.extend(hull_point(yy, k, offset) for k in range(HULL_N))
    faces = []
    for k in range(HULL_N):
        k2 = (k + 1) % HULL_N
        faces.append((k, k2, HULL_N + k2, HULL_N + k))
    return mesh_object(name, verts, faces, material_key)


def hull_patch(name, y0, y1, k0, k1, offset, height, material_key):
    corners_low = [
        hull_point(y0, k0, offset), hull_point(y0, k1, offset),
        hull_point(y1, k1, offset), hull_point(y1, k0, offset),
    ]
    corners_high = [
        hull_point(y0, k0, offset + height), hull_point(y0, k1, offset + height),
        hull_point(y1, k1, offset + height), hull_point(y1, k0, offset + height),
    ]
    verts = corners_low + corners_high
    faces = [(4, 5, 6, 7)]
    for i in range(4):
        j = (i + 1) % 4
        faces.append((i, j, 4 + j, 4 + i))
    obj = mesh_object(name, verts, faces, material_key)
    return obj


def hull_vent_bank(name, y, k_lo, k_hi, material_frame="dark",
                   material_slat="panel", count=4, length=1.4):
    """Vent bank defined by an explicit angular span so the mirrored bank on
    the other flank covers exactly the reflected span (no drift)."""
    hull_patch(name + "_Frame", y - 0.2, y + length + 0.2,
               k_lo - 0.30, k_hi + 0.30, 0.004, 0.018, material_frame)
    for i in range(count):
        k = k_lo + (k_hi - k_lo) * (i + 0.5) / count
        p1 = hull_point(y, k, 0.030)
        p2 = hull_point(y + length, k, 0.030)
        beam(f"{name}_Slat{i}", p1, p2, 0.075, 0.035, material_slat)


def mirrored_span(k_lo: float, k_hi: float):
    """Reflect an angular span on the hull ring (k -> -k mod N)."""
    return ((HULL_N - k_hi) % HULL_N, (HULL_N - k_lo) % HULL_N)


def build_hull_details():
    # Longitudinal panel lines (thin dark strips that follow the curvature)
    line_ks = [1.45, 2.45, 3.45, 5.0, 6.45]
    for k in line_ks:
        for mirror in (False, True):
            kk = (HULL_N - k) % HULL_N if mirror else k
            tag = "L" if mirror else "R"
            hull_ribbon_longitudinal(
                f"PanelLine_Long_{tag}_{k:.2f}", kk, -14.4, 13.2,
                0.032, 0.012, "dark", segments=24)
    # Ring seams around the hull
    for i, y in enumerate((-14.8, -12.6, -9.4, -5.2, -1.4, 2.8, 6.6, 9.4, 12.6)):
        hull_ribbon_ring(f"PanelLine_Ring_{i}", y, 0.042, 0.013, "dark")

    # Raised access panels, port + starboard (lighter grey = depth)
    panel_specs = [
        # (k0, k1, y0, y1, material)
        (2.05, 3.02, -8.2, -5.3, "panel"),
        (2.05, 3.02, -3.4, -0.4, "panel"),
        (2.05, 3.02, 2.0, 5.4, "panel"),
        (2.05, 3.02, 7.0, 9.4, "dark"),
        (3.10, 4.0, -6.7, -3.2, "panel"),
        (3.10, 4.0, 0.8, 4.2, "panel"),
        (5.25, 6.1, -4.4, -1.0, "dark"),
        (5.25, 6.1, 5.4, 8.6, "panel"),
        (6.55, 7.2, 2.2, 5.0, "dark"),
    ]
    idx = 0
    for k0, k1, y0, y1, mat in panel_specs:
        for mirror in (False, True):
            kk0 = (HULL_N - k1) % HULL_N if mirror else k0
            kk1 = (HULL_N - k0) % HULL_N if mirror else k1
            hull_patch(f"AccessPanel_{idx:02d}", y0, y1, kk0, kk1,
                       0.012, 0.030, mat)
            idx += 1

    # Top anti-glare panel and dorsal spine plates
    hull_patch("NoseAntiGlare", -16.2, -14.6, 15.25, 16.25, 0.010, 0.022, "dark")
    top_y = -8.6
    i = 0
    while top_y < 12.6:
        length = 0.85 if i % 3 else 1.35
        z = hull_top(top_y + length * 0.5) + 0.02
        mat = "panel" if i % 2 == 0 else "dark"
        box(f"DorsalSpinePlate_{i:02d}", (0.78, length, 0.10),
            (0.0, top_y + length * 0.5, z), mat)
        if i % 3 == 1:
            box(f"DorsalSpineRib_{i:02d}", (1.15, 0.12, 0.16),
                (0.0, top_y + 0.08, z + 0.04), "edge")
        top_y += length + 0.24
        i += 1

    # Long raised spine rail with cyan power line
    beam("DorsalConduit", (0, -7.6, hull_top(-7.6) + 0.08),
         (0, 5.4, hull_top(5.4) + 0.08), 0.32, 0.14, "dark")
    beam("DorsalPowerLine", (0, -7.3, hull_top(-7.3) + 0.17),
         (0, 4.9, hull_top(4.9) + 0.17), 0.055, 0.035, "cyan")

    # Vent banks on the shoulders / flanks (span mirroring keeps both sides equal)
    for y in (6.2, 9.4):
        span = (2.55, 2.55 + 5 * 0.15)
        for side, (k_lo, k_hi) in (("R", span), ("L", mirrored_span(*span))):
            hull_vent_bank(f"Vent_{side}_{y:.0f}", y, k_lo, k_hi, count=5,
                           length=1.15)
    for y in (2.0, 10.4):
        span = (5.25, 5.25 + 3 * 0.18)
        for side, (k_lo, k_hi) in (("R", span), ("L", mirrored_span(*span))):
            hull_vent_bank(f"LowerVent_{side}_{y:.0f}", y, k_lo, k_hi, count=3,
                           length=0.9)

    # Small formation lights along both flanks + belly
    for side in (-1, 1):
        for y, k in ((-7.5, 4.55), (0.0, 4.55), (7.0, 4.55)):
            p = hull_point(y, (HULL_N - k) % HULL_N if side < 0 else k, 0.045)
            ico(f"FormationLight_{side}_{y:.0f}", 0.085, p, "cyan", 1)
    for y in (-2.0, 5.0):
        p = hull_point(y, 8.0, 0.05)
        beam(f"BellyStrip_{y:.0f}", (p.x - 1.4, p.y, p.z), (p.x + 1.4, p.y, p.z),
             0.10, 0.035, "cyan")

    # Blade antennas (dorsal + ventral)
    antenna_specs = [
        (-8.2, 0.62, -0.42, "dark"), (2.3, 0.72, 0.30, "edge"),
        (8.2, 1.05, -0.48, "dark"), (11.9, 0.62, 0.18, "edge"),
    ]
    for i, (y, height, sweep, mat) in enumerate(antenna_specs):
        base = hull_top(y) + 0.02
        verts = [
            (-0.055, y - 0.42, base), (0.055, y - 0.42, base),
            (0.045, y + 0.36, base), (-0.045, y + 0.36, base),
            (-0.022, y + sweep, base + height), (0.022, y + sweep, base + height),
        ]
        faces = [(0, 1, 2, 3), (0, 4, 5, 1), (3, 2, 5, 4),
                 (0, 3, 4), (1, 5, 2)]
        obj = mesh_object(f"BladeAntenna_{i}", verts, faces, mat)
        recalc_normals(obj, closed=True)
    for i, y in enumerate((4.2, 9.0)):
        p = hull_point(y, 8.0, -0.01)
        beam(f"VentralAntenna_{i}", p, (p.x, p.y + 0.55, p.z - 0.85),
             0.055, 0.10, "dark")

    # Nose sensor pods + pitot probes + EO turret
    for side in (-1, 1):
        x = side * 1.42
        cylinder(f"NoseSensorPod_{side}", 0.16, 1.05,
                 (x, -14.55, 4.28), "dark", axis="Y", vertices=10)
        cylinder(f"NoseSensorLens_{side}", 0.115, 0.06,
                 (x, -15.10, 4.28), "cyan", axis="Y", vertices=10)
        torus(f"NoseSensorRing_{side}", 0.155, 0.028,
              (x, -15.05, 4.28), "edge", axis="Y", major_segments=10,
              minor_segments=3)
        beam(f"PitotProbe_{side}", (side * 0.62, -15.55, 4.18),
             (side * 0.62, -17.35, 4.18), 0.045, 0.045, "edge")
        ico(f"PitotTip_{side}", 0.055, (side * 0.62, -17.37, 4.18), "red", 1)
    cylinder("EOTurret", 0.34, 0.45, (0.0, -15.55, 3.20), "dark",
             axis="Y", vertices=8)
    cylinder("EOTurretLens", 0.22, 0.07, (0.0, -15.79, 3.20), "cyan",
             axis="Y", vertices=8)
    torus("EOTurretRing", 0.30, 0.035, (0.0, -15.72, 3.20), "edge",
          axis="Y", major_segments=8, minor_segments=3)

    # Under-nose landing lights, recessed into the belly
    for side in (-1, 1):
        p = hull_point(-14.4, 7.6 + (0.5 if side > 0 else -0.5), -0.02)
        ico(f"NoseLight_{side}", 0.09, (side * 0.45, p.y, p.z + 0.02), "white", 1)
    # Chined side strips that trace the maximum-width chine from nose to wing
    for mirror in (False, True):
        k = (HULL_N - 4) % HULL_N if mirror else 4
        hull_ribbon_longitudinal(
            f"ChineStrip_{'L' if mirror else 'R'}", k, -15.2, 1.4,
            0.045, 0.016, "edge", segments=18)

    # Belly gear doors (flush panels) + drop-hatch frames
    for i, (y0, y1) in enumerate(((-5.6, -1.8), (1.4, 5.2))):
        hull_patch(f"GearDoor_{i}", y0, y1, 7.55, 8.45, 0.006, 0.024, "panel")
        hull_patch(f"GearDoorLine_{i}", y0 + 0.15, y1 - 0.15, 7.8, 8.2,
                   0.032, 0.012, "dark")


# ---------------------------------------------------------------------------
# Cockpit canopy
# ---------------------------------------------------------------------------
CANOPY_STATIONS = [
    # (y, half_width, top_z)
    (-14.35, 0.52, 5.66),
    (-13.45, 1.12, 6.04),
    (-12.10, 1.50, 6.22),
    (-10.45, 1.42, 6.18),
    (-9.25, 0.82, 5.98),
]


def canopy_profile(half_width: float, base_z: float, top_z: float):
    return [
        (-half_width, base_z),
        (-0.70 * half_width, top_z - 0.12),
        (0.0, top_z),
        (0.70 * half_width, top_z - 0.12),
        (half_width, base_z),
        (0.0, base_z - 0.16),
    ]


def canopy_point(t: float, kf: float, offset: float = 0.0) -> Vector:
    """t=0 at windshield base (front), t=1 at rear."""
    t = min(max(t, 0.0), 1.0)
    seg = t * (len(CANOPY_STATIONS) - 1)
    i = min(int(seg), len(CANOPY_STATIONS) - 2)
    f = seg - i
    y0, w0, z0 = CANOPY_STATIONS[i]
    y1, w1, z1 = CANOPY_STATIONS[i + 1]
    y = y0 + (y1 - y0) * f
    w = w0 + (w1 - w0) * f
    ztop = z0 + (z1 - z0) * f
    zb = hull_top(y) - 0.24
    pts = canopy_profile(w, zb, ztop)
    kf = kf % len(pts)
    k = int(math.floor(kf))
    ft = kf - k
    p0 = pts[k]
    p1 = pts[(k + 1) % len(pts)]
    px = p0[0] + (p1[0] - p0[0]) * ft
    pz = p0[1] + (p1[1] - p0[1]) * ft
    cz = (zb + ztop) * 0.5
    n = Vector((px, 0.0, pz - cz))
    if n.length > 1e-9:
        n.normalize()
    return Vector((px, y, pz)) + n * offset


def build_canopy():
    rings = []
    for t in (0.0, 0.16, 0.34, 0.55, 0.76, 1.0):
        rings.append([canopy_point(t, k) for k in range(6)])
    glass = loft("CockpitCanopy", rings, "glass")

    # Clean structural framing: 3 arches (windshield bow, mid hoop, rear hoop)
    for ti, t in enumerate((0.0, 0.55, 1.0)):
        for k in range(5):
            beam(f"CanopyArch_{ti}_{k}", canopy_point(t, k, 0.030),
                 canopy_point(t, k + 1, 0.030), 0.075, 0.050, "dark")
    # Two shoulder rails + a central spine rail only (no busy diagonal lattice)
    for li, k in enumerate((1.0, 3.0)):
        for ti, (t0, t1) in enumerate(((0.0, 0.34), (0.34, 0.76), (0.76, 1.0))):
            beam(f"CanopyRail_{li}_{ti}", canopy_point(t0, k, 0.030),
                 canopy_point(t1, k, 0.030), 0.055, 0.040, "dark")
    for ti, (t0, t1) in enumerate(((0.0, 0.16), (0.16, 0.55), (0.55, 1.0))):
        beam(f"CanopySpine_{ti}", canopy_point(t0, 2.0, 0.032),
             canopy_point(t1, 2.0, 0.032), 0.060, 0.045, "dark")
    # cyan recognition strips along each shoulder rail (k=1 / k=3 mirror exactly)
    for side in (1.0, 3.0):
        p1 = canopy_point(0.30, side, 0.058)
        p2 = canopy_point(0.90, side, 0.058)
        beam(f"CanopyCyan_{side:.0f}", p1, p2, 0.032, 0.020, "cyan")

    # Canopy side sills / cockpit coaming
    for side in (-1, 1):
        p_front = canopy_point(0.0, 4.0 if side > 0 else 0.0, 0.03)
        p_rear = canopy_point(1.0, 4.0 if side > 0 else 0.0, 0.03)
        beam(f"CanopySill_{side}", p_front, p_rear, 0.17, 0.12, "panel")
        # rear-view mirror pod at the windshield shoulder
        ico(f"CanopyMirror_{side}", 0.10,
            canopy_point(0.08, 4.15 if side > 0 else -0.15, 0.12), "dark", 1)

    # armored spine fairing behind the glass
    box("CanopySpineFairing", (0.52, 1.6, 0.20), (0.0, -7.86, 6.10), "panel")
    bevel(_PARTS[-1], 0.05, 1)
    box("CanopySpineVent", (0.30, 0.80, 0.09), (0.0, -8.38, 6.20), "dark")
    for i in range(3):
        beam(f"CanopySpineSlat_{i}", (-0.16, -8.6 + i * 0.22, 6.25),
             (0.16, -8.6 + i * 0.22, 6.25), 0.05, 0.035, "edge")
    return glass


# ---------------------------------------------------------------------------
# Wings, winglets, tails
# ---------------------------------------------------------------------------
WING_SECTIONS = [
    # (x, leading_edge_y, trailing_edge_y, centre_z, thickness)
    (2.40, -9.00, 7.70, 3.64, 0.95),
    (6.00, -5.60, 7.20, 3.60, 0.72),
    (10.00, -2.80, 6.40, 3.55, 0.54),
    (14.00, -0.20, 5.60, 3.49, 0.40),
    (18.00, 2.10, 4.80, 3.42, 0.28),
    (20.50, 3.40, 4.30, 3.37, 0.19),
    (21.50, 3.60, 5.00, 3.34, 0.14),
]
WING_PROFILE = [
    (0.00, 0.00), (0.12, 0.52), (0.34, 0.82), (0.60, 0.60),
    (0.90, 0.25), (1.00, 0.05), (0.90, -0.25), (0.60, -0.55),
    (0.30, -0.60), (0.10, -0.40),
]
WING_N = len(WING_PROFILE)


def wing_params(t: float):
    t = min(max(t, 0.0), 1.0)
    seg = t * (len(WING_SECTIONS) - 1)
    i = min(int(seg), len(WING_SECTIONS) - 2)
    f = seg - i
    s0 = WING_SECTIONS[i]
    s1 = WING_SECTIONS[i + 1]
    return tuple(a + (b - a) * f for a, b in zip(s0, s1))


def wing_point(t: float, kf: float, offset: float = 0.0, side: int = 1) -> Vector:
    x, le, te, zc, th = wing_params(t)
    kf = kf % WING_N
    k = int(math.floor(kf))
    f = kf - k
    p0 = WING_PROFILE[k]
    p1 = WING_PROFILE[(k + 1) % WING_N]
    fy = p0[0] + (p1[0] - p0[0]) * f
    fz = p0[1] + (p1[1] - p0[1]) * f
    z = zc + fz * th + math.copysign(offset, fz if abs(fz) > 1e-6 else 1.0)
    return Vector((side * x, le + fy * (te - le), z))


def build_wing(side: int):
    rings = []
    for si, (x, le, te, zc, th) in enumerate(WING_SECTIONS):
        ring = []
        for fy, fz in WING_PROFILE:
            ring.append((side * x, le + fy * (te - le), zc + fz * th))
        rings.append(ring)
    wing = loft(f"Wing_{'R' if side > 0 else 'L'}", rings, "body")
    return wing


def fin_profile_points(center: Vector, chord: float, thickness: float,
                       normal: Vector, chord_frac: float, thick_frac: float):
    return center + Vector((0.0, chord_frac * chord, 0.0)) + normal * (thick_frac * thickness)


FIN_PROFILE = [
    (-0.50, 0.00), (-0.32, 0.38), (-0.10, 0.50), (0.20, 0.42),
    (0.50, 0.00), (0.20, -0.42), (-0.10, -0.50), (-0.32, -0.38),
]


def build_fin(name, root_center, tip_center, root_chord, tip_chord,
              root_thickness, tip_thickness, material_key="body", segments=6):
    root_c = Vector(root_center)
    tip_c = Vector(tip_center)
    direction = tip_c - root_c
    normal = direction.cross(Vector((0.0, 1.0, 0.0)))
    if normal.length < 1e-8:
        normal = Vector((1.0, 0.0, 0.0))
    normal.normalize()
    rings = []
    for i in range(segments + 1):
        t = i / segments
        center = root_c + direction * t
        chord = root_chord + (tip_chord - root_chord) * t
        thick = root_thickness + (tip_thickness - root_thickness) * t
        # slight faceted leading-edge droop for a stealthy silhouette
        ring = [fin_profile_points(center, chord, thick, normal, fy, fz)
                for fy, fz in FIN_PROFILE]
        rings.append(ring)
    fin = loft(name, rings, material_key)
    # dark leading edge + glowing upper trailing edge
    le_pts = [root_c + direction * (i / segments)
              + Vector((0.0, -0.5 * (root_chord + (tip_chord - root_chord) * i / segments), 0.0))
              for i in range(segments + 1)]
    for i in range(segments):
        beam(f"{name}_LE_{i}", le_pts[i] + normal * 0.01,
             le_pts[i + 1] + normal * 0.01, 0.12, 0.08, "dark")
    for i in range(3, segments):
        t = i / segments
        center = root_c + direction * t
        chord = root_chord + (tip_chord - root_chord) * t
        p = center + Vector((0.0, 0.49 * chord, 0.0))
        p2 = center + direction / segments + Vector((0.0, 0.49 * chord, 0.0))
        beam(f"{name}_Cyan_{i}", p + normal * 0.02, p2 + normal * 0.02,
             0.05, 0.03, "cyan")
    return fin


def build_tail():
    for side in (-1, 1):
        root = (side * 2.90, 11.15, 5.88)
        tip = (side * 4.35, 13.00, 9.70)
        fin = build_fin(f"TailFin_{'R' if side > 0 else 'L'}",
                        root, tip, 3.20, 1.10, 0.32, 0.10, "body", 6)
        # fin root glove / fairing
        box(f"TailRootFairing_{side}", (0.65, 3.1, 0.42),
            (side * 2.95, 11.15, 5.98), "panel")
        # tip caps, nav light and antenna
        ico(f"TailNavLight_{side}", 0.12, (side * 4.37, 12.55, 9.74),
            "green" if side > 0 else "red", 1)
        beam(f"TailTipAntenna_{side}", (side * 4.35, 13.35, 9.68),
             (side * 4.35, 13.75, 10.35), 0.040, 0.055, "edge")
        # bolt-on fin actuators
        for i, y in enumerate((10.2, 11.1, 12.0)):
            p = Vector((side * 2.96, y, 6.10 + i * 0.10))
            box(f"FinActuator_{side}_{i}", (0.30, 0.55, 0.20), p, "edge")

    # Dorsal fairing between the fins — a tapered stealth wedge, not a box
    fairing_rings = []
    for t, hw, top in ((0.0, 1.72, 0.20), (0.35, 1.62, 0.34),
                       (0.75, 1.42, 0.30), (1.0, 1.18, 0.12)):
        y = 9.55 + 3.75 * t
        z = hull_top(y) + 0.02
        fairing_rings.append([
            (-hw, y, z), (hw, y, z), (hw * 0.82, y, z + top),
            (-hw * 0.82, y, z + top),
        ])
    fairing = loft("TailDorsalFairing", fairing_rings, "panel")
    bevel(fairing, 0.05, 1)
    box("TailDorsalFairingTop", (2.60, 3.0, 0.09), (0.0, 11.35, 6.36), "dark")
    for i in range(5):
        box(f"TailDorsalRib_{i}", (2.55, 0.14, 0.10),
            (0.0, 9.95 + i * 0.75, 6.41), "edge")
    beam("TailFormationStrip", (-1.58, 10.2, 6.44), (-1.58, 13.2, 6.44),
         0.08, 0.05, "cyan")
    beam("TailFormationStrip2", (1.58, 10.2, 6.44), (1.58, 13.2, 6.44),
         0.08, 0.05, "cyan")
    ico("TailStrobe", 0.11, (0.0, 13.30, 6.44), "white", 1)
    # rear-facing heat exchanger exhausts under the fairing
    for side in (-1, 1):
        for i in range(3):
            box(f"TailHeatVent_{side}_{i}", (0.44, 0.20, 0.30),
                (side * 0.95 + i * 0.0, 13.32, 5.86 - i * 0.0), "dark")
            beam(f"TailHeatSlat_{side}_{i}", (side * 0.95 - 0.18, 13.43, 5.72 + i * 0.20),
                 (side * 0.95 + 0.18, 13.43, 5.72 + i * 0.20), 0.045, 0.03, "orange")


def build_wing_details():
    for side in (-1, 1):
        tag = "R" if side > 0 else "L"
        # leading-edge dark band and a short cyan recognition strip
        for i in range(10):
            t0, t1 = i / 10, (i + 1) / 10
            p1 = wing_point(t0, 0.0, 0.03, side)
            p2 = wing_point(t1, 0.0, 0.03, side)
            beam(f"WingLE_{tag}_{i}", p1, p2, 0.16, 0.10, "dark")
        for i in range(6):
            t = 0.55 + i * 0.06
            p1 = wing_point(t, 0.18, 0.035, side)
            p2 = wing_point(t + 0.06, 0.18, 0.035, side)
            beam(f"WingCyanLE_{tag}_{i}", p1, p2, 0.055, 0.025, "cyan")

        # spanwise panel lines across the upper wing
        for k in (2.0, 3.6, 5.4):
            for seg in range(8):
                t0 = seg / 8
                t1 = (seg + 1) / 8
                p1a = wing_point(t0, k - 0.025, 0.022, side)
                p1b = wing_point(t0, k + 0.025, 0.022, side)
                p2a = wing_point(t1, k - 0.025, 0.022, side)
                p2b = wing_point(t1, k + 0.025, 0.022, side)
                verts = [p1a, p1b, p2b, p2a]
                mesh_object(f"WingPanelLine_{tag}_{k}_{seg}", verts,
                            [(0, 1, 2, 3)], "dark")
        # chordwise seams / control-surface hinge lines
        for t in (0.28, 0.48, 0.67, 0.83):
            for k in (4.1, 4.6, 5.1):
                p1 = wing_point(t - 0.006, k, 0.026, side)
                p2 = wing_point(t + 0.006, k, 0.026, side)
                beam(f"WingSeam_{tag}_{t}_{k}", p1, p2, 0.07, 0.035, "dark")
        # lighter access hatches on the wing
        panel_ts = [(0.16, 0.28), (0.36, 0.46), (0.56, 0.66), (0.74, 0.84)]
        for pi, (t0, t1) in enumerate(panel_ts):
            for k0, k1 in ((1.5, 2.3), (2.8, 3.7)):
                points = [
                    wing_point(t0, k0, 0.035, side), wing_point(t0, k1, 0.035, side),
                    wing_point(t1, k1, 0.035, side), wing_point(t1, k0, 0.035, side),
                ]
                mesh_object(f"WingAccessPanel_{tag}_{pi}_{k0}", points,
                            [(0, 1, 2, 3)], "panel")
        # vortex generators near the leading edge
        for i in range(7):
            t = 0.2 + i * 0.1
            p = wing_point(t, 0.34, 0.04, side)
            nxt = wing_point(t + 0.025, 0.34, 0.04, side)
            beam(f"VortexGen_{tag}_{i}", p, nxt, 0.045, 0.12, "edge")

        # winglet
        root = Vector((side * 21.5, 4.30, 3.34))
        tip = Vector((side * 22.40, 4.82, 7.10))
        build_fin(f"Winglet_{tag}", root, tip, 1.40, 0.70, 0.16, 0.07,
                  "body", 6)
        # winglet root fairing and tip cap
        box(f"WingletFairing_{tag}", (0.55, 1.65, 0.24),
            (side * 21.55, 4.3, 3.40), "panel")
        beam(f"WingletCyan_{tag}", (side * 21.8, 4.95, 5.0),
             (side * 22.22, 4.95, 6.9), 0.055, 0.03, "cyan")
        ico(f"WingtipNav_{tag}", 0.14, (side * 22.42, 4.55, 7.12),
            "green" if side > 0 else "red", 1)
        ico(f"WingtipStrobe_{tag}", 0.09, (side * 22.38, 5.05, 7.10),
            "white", 1)

        # under-wing drop tanks
        pod_x = side * 14.4
        body_center = (pod_x, 0.65, 2.48)
        cylinder(f"DropTank_{tag}", 0.56, 3.9, body_center, "panel",
                 axis="Y", vertices=10)
        cone(f"DropTankNose_{tag}", 0.56, 0.10, 1.35,
             (pod_x, -1.975, 2.48), "dark", axis="Y", vertices=10)
        cone(f"DropTankTail_{tag}", 0.56, 0.16, 1.05,
             (pod_x, 3.125, 2.48), "dark", axis="Y", vertices=10)
        torus(f"DropTankBand_{tag}", 0.57, 0.045, (pod_x, -0.8, 2.48),
              "edge", axis="Y", major_segments=12, minor_segments=3)
        torus(f"DropTankGlow_{tag}", 0.57, 0.035, (pod_x, 1.7, 2.48),
              "cyan", axis="Y", major_segments=12, minor_segments=3)
        for i in range(4):
            ang = math.pi / 2 * i + math.pi / 4
            fx = pod_x + 0.62 * math.cos(ang)
            fz = 2.48 + 0.62 * math.sin(ang)
            box(f"DropTankFin_{tag}_{i}", (0.08, 0.85, 0.42),
                (fx, 2.9, fz), "dark",
                rotation=(0.0, ang, 0.0))
        beam(f"DropTankPylon_{tag}", (pod_x, 0.7, 3.85),
             (pod_x, 0.7, 2.98), 0.36, 0.95, "panel")


# ---------------------------------------------------------------------------
# Engines
# ---------------------------------------------------------------------------
def build_engine(name: str, cx: float, cy: float, cz: float,
                 length: float, radius_x: float, radius_z: float):
    y0 = cy - length * 0.5
    y1 = cy + length * 0.5
    stations = [
        (y0, 0.86), (y0 + 0.32, 1.04), (y0 + 1.25, 1.0),
        (y1 - 1.25, 0.99), (y1 - 0.25, 0.93), (y1, 0.84),
    ]
    rings = []
    for y, scale in stations:
        rings.append(ring_of_points((cx, y, cz), radius_x * scale,
                                    radius_z * scale, 8))
    # Open-ended shell so the fan and duct read as a real intake
    shell = loft(name, rings, "body", cap_start=False, cap_end=False)
    bevel(shell, 0.035, 1)

    # Recessed intake duct, spinner cone and 10-blade fan
    cylinder(f"{name}_IntakeDuct", radius_x * 0.80, 1.30,
             (cx, y0 + 0.70, cz), "dark", axis="Y", vertices=16)
    cone(f"{name}_Spinner", radius_x * 0.22, 0.02, 0.62,
         (cx, y0 + 0.14, cz), "edge", axis="Y", vertices=10)
    torus(f"{name}_SpinnerBase", radius_x * 0.225, 0.030,
          (cx, y0 + 0.42, cz), "cyan", axis="Y", major_segments=12,
          minor_segments=3)
    for i in range(10):
        ang = 2 * math.pi * i / 10
        r_in = radius_x * 0.20
        r_out = radius_x * 0.72
        beam(f"{name}_FanBlade_{i}",
             (cx + r_in * math.cos(ang), y0 + 0.60, cz + r_in * 0.92 * math.sin(ang)),
             (cx + r_out * math.cos(ang + 0.22), y0 + 0.34,
              cz + r_out * 0.92 * math.sin(ang + 0.22)),
             0.11, 0.030, "edge")
    torus(f"{name}_IntakeGlowRing", radius_x * 0.755, 0.032,
          (cx, y0 + 0.40, cz), "cyan", axis="Y", major_segments=16,
          minor_segments=3)
    torus(f"{name}_IntakeLip", radius_x * 0.955, 0.085,
          (cx, y0 + 0.16, cz), "edge", axis="Y", major_segments=16,
          minor_segments=3)
    torus(f"{name}_IntakeCyanRing", radius_x * 0.90, 0.030,
          (cx, y0 - 0.02, cz), "cyan", axis="Y", major_segments=16,
          minor_segments=3)
    # intake internal guide vanes
    for i in range(4):
        ang = math.pi / 2 * i + math.pi / 4
        box(f"{name}_IntakeVane_{i}", (0.05, 0.54, 0.95),
            (cx + radius_x * 0.56 * math.cos(ang), y0 + 0.92,
             cz + radius_z * 0.56 * math.sin(ang)), "engine",
            rotation=(0.0, ang, 0.0))

    # armoured bands along the nacelle
    for i, frac in enumerate((0.24, 0.52, 0.78)):
        y = y0 + length * frac
        torus(f"{name}_Band_{i}", radius_x * 1.005, 0.070,
              (cx, y, cz), "panel", axis="Y", major_segments=16,
              minor_segments=3)
        box(f"{name}_BandTab_{i}", (0.22, 0.22, 0.10),
            (cx, y, cz + radius_z * 1.02), "edge")

    # top equipment rail + cyan power spine
    box(f"{name}_TopRail", (0.36, length * 0.62, 0.10),
        (cx, cy, cz + radius_z * 0.99), "dark")
    beam(f"{name}_TopGlow", (cx, cy - length * 0.25, cz + radius_z * 1.04),
         (cx, cy + length * 0.22, cz + radius_z * 1.04), 0.07, 0.035, "cyan")

    # side heat-exchange vents
    for side in (-1, 1):
        for v in range(3):
            vy = y0 + 1.7 + v * 1.5
            for s in range(4):
                z = cz + 0.26 + s * 0.16
                beam(f"{name}_Vent_{side}_{v}_{s}",
                     (cx + side * radius_x * 0.96, vy, z),
                     (cx + side * radius_x * 0.96, vy + 0.8, z),
                     0.05, 0.035, "dark")
        # running-light dots
        for v in range(3):
            ico(f"{name}_SideLight_{side}_{v}", 0.055,
                (cx + side * radius_x * 1.0, y0 + 2.0 + v * 1.7, cz - 0.44),
                "cyan", 1)

    # vectoring nozzle petals
    for i in range(8):
        ang = 2 * math.pi * i / 8 + math.pi / 8
        inner = Vector((cx + radius_x * 0.56 * math.cos(ang), y1 + 0.05,
                        cz + radius_z * 0.56 * math.sin(ang)))
        outer = Vector((cx + radius_x * 0.97 * math.cos(ang), y1 + 0.56,
                        cz + radius_z * 0.97 * math.sin(ang)))
        mid = (inner + outer) * 0.5
        beam(f"{name}_NozzlePetal_{i}", outer, inner, 0.26, 0.10, "dark")
        box(f"{name}_NozzleTip_{i}", (0.11, 0.20, 0.20),
            (outer.x, y1 + 0.56, outer.z), "edge",
            rotation=(0.0, -ang, 0.0))

    # glowing exhaust stack: cyan outer cylinder + hot orange core
    cylinder(f"{name}_ExhaustCone", radius_x * 0.82, 1.10,
             (cx, y1 + 0.20, cz), "engine", axis="Y", vertices=16)
    cylinder(f"{name}_ThrusterOuter", radius_x * 0.68, 0.60,
             (cx, y1 + 0.30, cz), "cyan", axis="Y", vertices=16)
    cylinder(f"{name}_ThrusterOrange", radius_x * 0.42, 0.80,
             (cx, y1 + 0.34, cz), "orange", axis="Y", vertices=12)
    cylinder(f"{name}_ThrusterCore", radius_x * 0.12, 0.92,
             (cx, y1 + 0.38, cz), "white", axis="Y", vertices=8)
    torus(f"{name}_NozzleCyanRing", radius_x * 0.78, 0.042,
          (cx, y1 + 0.16, cz), "cyan", axis="Y", major_segments=16,
          minor_segments=3)
    torus(f"{name}_NozzleDarkRing", radius_x * 0.94, 0.085,
          (cx, y1 - 0.02, cz), "engine", axis="Y", major_segments=16,
          minor_segments=3)

    # under-nacelle pylon that anchors into the wing skin
    wing_top = 4.05
    pylon_bottom = wing_top - 0.30
    pylon_top = cz - radius_z * 0.85
    box(f"{name}_Pylon", (0.58, 2.6, pylon_top - pylon_bottom),
        (cx, cy - 0.35, (pylon_top + pylon_bottom) * 0.5), "panel")
    bevel(_PARTS[-1], 0.07, 1)
    beam(f"{name}_PylonGlow", (cx, cy - 1.55, pylon_bottom + 0.22),
         (cx, cy + 0.85, pylon_bottom + 0.22), 0.055, 0.028, "cyan")
    for i in range(3):
        box(f"{name}_PylonRib_{i}", (0.66, 0.11, 0.20),
            (cx, cy - 1.3 + i * 0.85, pylon_bottom + 0.55), "dark")
    # pylon shoulder fairings (stealth blended roots)
    for s in (-1, 1):
        box(f"{name}_PylonShoulder_{s}", (0.30, 1.9, 0.55),
            (cx + s * 0.34, cy - 0.35, pylon_top - 0.18), "body",
            rotation=(0.0, s * math.radians(12.0), 0.0))

    # dorsal heat-exchanger fins on the nacelle
    for i in range(5):
        box(f"{name}_HeatFin_{i}", (0.09, 0.95, 0.34),
            (cx - 0.42 + i * 0.21, cy + 2.1, cz + radius_z * 0.96), "edge")
    return shell


def build_engine_deck():
    # raised engine-deck plating between the inner nacelles
    for i in range(4):
        y = 3.6 + i * 2.2
        z = hull_top(y) + 0.10
        box(f"EngineDeckPlate_{i}", (2.6, 1.7, 0.10), (0.0, y, z), "panel")
        box(f"EngineDeckRib_{i}", (2.8, 0.12, 0.06), (0.0, y + 0.7, z + 0.08), "dark")
    box("EngineDeckBus", (0.28, 9.2, 0.10), (0.0, 7.2, hull_top(7.2) + 0.18), "cyan")


# ---------------------------------------------------------------------------
# Cargo bay interior, ramp, opening frame and lights
# ---------------------------------------------------------------------------
def build_cargo_bay():
    # floor / ceiling / side walls / forward bulkhead (inside the Boolean void)
    box("CargoFloor", (4.66, 5.9, 0.14), (0.0, 11.05, 2.63), "interior")
    for side in (-1, 1):
        box(f"CargoWall_{side}", (0.10, 5.9, 2.55),
            (side * 2.36, 11.05, 3.88), "interior")
    box("CargoCeiling", (4.8, 5.9, 0.12), (0.0, 11.05, 5.11), "interior")
    box("CargoBulkhead", (4.7, 0.14, 2.55), (0.0, 8.28, 3.88), "panel")
    box("CargoBulkheadDoor", (1.25, 0.06, 1.95), (0.0, 8.20, 3.60), "dark")

    # structural ribs
    for i, y in enumerate((9.0, 10.3, 11.6, 12.9)):
        for side in (-1, 1):
            box(f"CargoRib_{i}_{side}", (0.16, 0.20, 2.48),
                (side * 2.26, y, 3.88), "panel")
        box(f"CargoRibTop_{i}", (4.66, 0.20, 0.14), (0.0, y, 5.02), "panel")
        box(f"CargoRibFloor_{i}", (4.66, 0.20, 0.10), (0.0, y, 2.76), "dark")

    # ceiling lighting + floor guide rails
    for side in (-1, 1):
        box(f"CargoCeilingLight_{side}", (0.18, 4.9, 0.035),
            (side * 1.02, 11.0, 5.03), "cyan")
        box(f"CargoFloorRail_{side}", (0.14, 5.2, 0.04),
            (side * 1.55, 11.0, 2.72), "dark")
        for i in range(5):
            box(f"CargoTieDown_{side}_{i}", (0.22, 0.12, 0.05),
                (side * 1.55, 9.2 + i * 0.9, 2.75), "edge")

    # cargo containers (bevel + straps + glowing tags)
    crates = [
        (-1.05, 10.15, 1.32, "panel"), (0.95, 11.45, 1.48, "dark"),
        (0.10, 9.35, 1.05, "panel"), (-1.30, 12.35, 1.10, "dark"),
    ]
    for i, (x, y, size, mat) in enumerate(crates):
        z = 2.70 + size * 0.5
        crate = box(f"CargoCrate_{i}", (size, size, size), (x, y, z), mat)
        bevel(crate, 0.04, 1)
        for s in (-1, 1):
            box(f"CargoCrateStrap_{i}_{s}", (size + 0.03, 0.08, 0.12),
                (x, y + s * size * 0.28, z + size * 0.45), "edge")
        box(f"CargoCrateTag_{i}", (0.22, 0.04, 0.08),
            (x + size * 0.30, y - size * 0.51, z + size * 0.18), "cyan")

    # rear opening frame (covers the Boolean seam)
    for side in (-1, 1):
        box(f"CargoFrameSide_{side}", (0.30, 0.42, 2.95),
            (side * 2.52, 13.86, 3.87), "panel")
    box("CargoFrameTop", (5.35, 0.42, 0.30), (0.0, 13.86, 5.32), "panel")
    box("CargoFrameBottom", (5.35, 0.42, 0.30), (0.0, 13.86, 2.42), "panel")
    for i in range(6):
        x = -2.05 + i * 0.82
        box(f"CargoFrameBolt_{i}", (0.10, 0.05, 0.10), (x, 14.09, 5.32), "edge")
        box(f"CargoFrameBoltB_{i}", (0.10, 0.05, 0.10), (x, 14.09, 2.42), "edge")

    # red / green indicator lights around the ramp
    indicators = [
        (-2.52, 5.10, "green"), (2.52, 5.10, "green"),
        (-2.52, 2.60, "red"), (2.52, 2.60, "red"),
        (-2.52, 3.95, "green"), (2.52, 3.95, "green"),
        (-1.30, 5.33, "green"), (1.30, 5.33, "green"),
        (-1.30, 2.41, "red"), (1.30, 2.41, "red"),
    ]
    for i, (x, z, mat) in enumerate(indicators):
        ico(f"RampLight_{i}", 0.105, (x, 14.13, z), mat, 1)
        torus(f"RampLightBezel_{i}", 0.145, 0.028, (x, 14.10, z),
              "dark", axis="Y", major_segments=10, minor_segments=3)

    # --- lowered ramp -------------------------------------------------------
    # Explicit ramp-local frame: u runs down the slope, v is across it and w
    # is the surface normal, so every detail sits exactly on the plate.
    hinge = Vector((0.0, 13.78, 2.72))
    tip = Vector((0.0, 17.26, 0.34))
    u = (tip - hinge).normalized()
    v = Vector((1.0, 0.0, 0.0))
    w = u.cross(v).normalized() * -1.0
    if w.z < 0:
        w = -w
    ramp_len = (tip - hinge).length
    half_w = 2.62
    thick = 0.20

    def ramp_point(d: float, x: float, up: float) -> Vector:
        return hinge + u * d + v * x + w * up

    top = [ramp_point(0.0, -half_w, 0.0), ramp_point(0.0, half_w, 0.0),
           ramp_point(ramp_len, half_w, 0.0), ramp_point(ramp_len, -half_w, 0.0)]
    bottom = [p - w * thick for p in top]
    verts = top + bottom
    faces = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1),
             (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    ramp = mesh_object("CargoRamp", verts, faces, "panel")
    recalc_normals(ramp, closed=True)

    # treads, cross ribs and cyan edge strips follow the plate
    for i in range(11):
        d = 0.24 + i * (ramp_len - 0.5) / 10.0
        box(f"RampTread_{i}", (4.90, 0.17, 0.055),
            ramp_point(d, 0.0, 0.03), "dark",
            rotation=(-math.asin(u.z), 0.0, 0.0))
    for side in (-1, 1):
        p_a = ramp_point(0.10, side * (half_w - 0.10), 0.05)
        p_b = ramp_point(ramp_len - 0.05, side * (half_w - 0.10), 0.05)
        beam(f"RampRail_{side}", p_a, p_b, 0.13, 0.16, "edge")
        p_a = ramp_point(0.12, side * (half_w - 0.23), 0.07)
        p_b = ramp_point(ramp_len - 0.06, side * (half_w - 0.23), 0.07)
        beam(f"RampGlow_{side}", p_a, p_b, 0.045, 0.028, "cyan")
        # underside support beams
        beam(f"RampUnderBeam_{side}",
             ramp_point(0.35, side * 1.85, -thick - 0.13),
             ramp_point(ramp_len - 0.20, side * 1.85, -thick - 0.13),
             0.16, 0.20, "engine")
    # hinge barrel + caps
    cylinder("RampHinge", 0.17, 5.40, ramp_point(0.0, 0.0, -0.02), "engine",
             axis="X", vertices=12)
    for side in (-1, 1):
        torus(f"RampHingeCap_{side}", 0.22, 0.05,
              ramp_point(0.02, side * 2.56, -0.02), "edge", axis="X",
              major_segments=10, minor_segments=3)
        # hydraulic actuator, mounted OUTBOARD of the ramp plate so it never
        # crosses the walking surface: barrel hangs off the frame, the polished
        # rod runs down to a bracket on the ramp's outer edge.
        ax = side * 2.78
        beam(f"RampActuatorBarrel_{side}", (ax, 13.05, 4.62),
             (ax, 14.85, 3.26), 0.17, 0.17, "engine")
        beam(f"RampActuatorRod_{side}", (ax, 14.70, 3.38),
             (ax, 15.55, 2.32), 0.10, 0.10, "edge")
        cylinder(f"RampActuatorBracket_{side}", 0.24, 0.34,
                 (ax, 13.05, 4.62), "dark", axis="X", vertices=8)
        box(f"RampActuatorMount_{side}", (0.26, 0.34, 0.26),
            ramp_point(2.05, side * 2.62, 0.02), "dark")
    # orange hazard tabs at the ramp lip + green "clear to drop" strip
    for i in range(5):
        box(f"RampHazard_{i}", (0.44, 0.14, 0.045),
            ramp_point(ramp_len - 0.22, -1.6 + i * 0.8, 0.03), "orange",
            rotation=(-math.asin(u.z), 0.0, 0.0))
    beam("RampDropStrip", ramp_point(ramp_len - 0.55, -1.9, 0.045),
         ramp_point(ramp_len - 0.55, 1.9, 0.045), 0.06, 0.03, "green")
    # "drop master" beacon above the opening
    ico("RampBeacon", 0.14, (0.0, 13.62, 5.66), "orange", 2)
    torus("RampBeaconBezel", 0.20, 0.04, (0.0, 13.62, 5.62), "dark",
          axis="Y", major_segments=10, minor_segments=3)


# ---------------------------------------------------------------------------
# Extra greebling pass
# ---------------------------------------------------------------------------
def build_greebles():
    rng = random.Random(4711)

    # RCS thruster quads — nose flanks and rear quarters
    rcs_spots = [(-13.6, 3.55), (-12.9, 4.15), (11.9, 3.5), (12.6, 4.2)]
    for i, (y, k) in enumerate(rcs_spots):
        for mirror in (False, True):
            kk = (HULL_N - k) % HULL_N if mirror else k
            _, _, az, p = hull_axes(y, kk)
            hull_greeble(f"RCSPod_{i}_{mirror}", y, kk, 0.34, 0.46, 0.16, "dark")
            ico(f"RCSJet_{i}_{mirror}", 0.075, p + az * 0.18, "cyan", 1)
            hull_greeble(f"RCSLip_{i}_{mirror}", y, kk, 0.40, 0.52, 0.05,
                         "edge", offset=-0.02)

    # Chaff / flare dispenser banks on the lower rear flanks
    for side in (-1, 1):
        for i in range(4):
            y = 10.2 + i * 0.55
            kk = (HULL_N - 6.1) % HULL_N if side < 0 else 6.1
            _, _, az, p = hull_axes(y, kk)
            hull_greeble(f"Dispenser_{side}_{i}", y, kk, 0.22, 0.40, 0.11, "dark")
            ico(f"DispenserDot_{side}_{i}", 0.055, p + az * 0.13, "orange", 1)

    # Chin radar / FLIR turret under the nose
    cylinder("ChinTurretBase", 0.42, 0.22, (0.0, -14.4, 2.62), "dark",
             axis="Z", vertices=10)
    ico("ChinTurretDome", 0.34, (0.0, -14.4, 2.50), "panel", 2)
    cylinder("ChinTurretLens", 0.20, 0.10, (0.0, -14.66, 2.45), "glass",
             axis="Y", vertices=10)
    torus("ChinTurretRing", 0.30, 0.035, (0.0, -14.58, 2.47), "edge",
          axis="Y", major_segments=12, minor_segments=3)

    # Lift / tie-down rings and jacking points along the belly
    for i, y in enumerate((-9.0, -3.0, 3.0, 9.0)):
        for side in (-1, 1):
            p = hull_point(y, (HULL_N - 7.6) % HULL_N if side < 0 else 7.6, 0.02)
            torus(f"TieDown_{i}_{side}", 0.11, 0.028,
                  (p.x, p.y, p.z + 0.02), "edge", axis="Y",
                  major_segments=8, minor_segments=3)

    # Randomised service hatches on the hull shoulders (deterministic seed) —
    # oriented to the local hull normal so nothing floats off the skin
    hatch_y = [-12.0, -10.2, -6.6, -3.8, 0.6, 3.4, 6.8, 10.8]
    for i, y in enumerate(hatch_y):
        k = 2.55 + rng.random() * 0.45
        sx = 0.32 + rng.random() * 0.36
        sy = 0.26 + rng.random() * 0.44
        sz = 0.035 + rng.random() * 0.035
        for mirror in (False, True):
            kk = (HULL_N - k) % HULL_N if mirror else k
            hull_greeble(f"ServiceHatch_{i}_{mirror}", y, kk, sx, sy, sz, "panel")
            # recessed vent slots across the hatch face
            for s in range(2):
                hull_greeble(f"ServiceHatchVent_{i}_{mirror}_{s}",
                             y - sy * 0.16 + s * sy * 0.30, kk,
                             sx * 0.55, 0.045, 0.020, "dark",
                             offset=sz * 0.85)

    # Wing flap hinge fairings under the trailing edge
    for side in (-1, 1):
        tag = "R" if side > 0 else "L"
        for i, (t, fx) in enumerate(((0.22, 0.30), (0.42, 0.34), (0.62, 0.30),
                                     (0.80, 0.24))):
            x, le, te, zc, th = wing_params(t)
            p = Vector((side * x, te - 0.20, zc - th * 0.30))
            ico(f"FlapFairing_{tag}_{i}", fx, p, "panel", 2)
            beam(f"FlapHinge_{tag}_{i}", (side * x, te - 0.55, zc - th * 0.42),
                 (side * x, te + 0.10, zc - th * 0.42), 0.09, 0.06, "edge")
        # fuel caps on the upper wing
        for i, t in enumerate((0.30, 0.52, 0.72)):
            p = wing_point(t, 2.6, 0.02, side)
            torus(f"FuelCap_{tag}_{i}", 0.20, 0.035, p + Vector((0, 0, 0.02)),
                  "edge", axis="Z", major_segments=10, minor_segments=3)
            ico(f"FuelCapDot_{tag}_{i}", 0.07, p + Vector((0, 0, 0.05)),
                "cyan", 1)

        # cyan wing chevrons (solid geometry markings, near the tip)
        for i in range(3):
            t = 0.68 + i * 0.055
            p1 = wing_point(t, 1.5, 0.045, side)
            p2 = wing_point(t + 0.045, 1.9, 0.045, side)
            beam(f"WingChevron_{tag}_{i}", p1, p2, 0.18, 0.035, "cyan")

    # Dorsal sensor blisters
    for i, (y, r) in enumerate(((-11.2, 0.30), (-4.6, 0.36), (1.8, 0.30))):
        p = Vector((0.0, y, hull_top(y) + 0.10))
        ico(f"SensorBlister_{i}", r, p, "dark", 2)
        torus(f"SensorBlisterRing_{i}", r * 1.02, 0.045,
              (0.0, y, p.z - 0.05), "edge", axis="Z",
              major_segments=12, minor_segments=3)

    # Cargo door outline on the port flank (external bay hatch)
    for i in range(4):
        hull_patch(f"CargoHatchLine_{i}", 9.3 + i * 0.9, 9.42 + i * 0.9,
                   3.55, 4.6, 0.014, 0.024, "dark")
    hull_patch("CargoHatchPanel", 9.4, 12.9, 3.6, 4.55, 0.006, 0.022, "panel")

    # Boarding step + grab handles under the cockpit door
    for side in (-1, 1):
        k = (HULL_N - 5.15) % HULL_N if side < 0 else 5.15
        _, _, az, p = hull_axes(-11.0, k)
        hull_greeble(f"BoardingStep_{side}", -11.0, k, 0.60, 0.34, 0.09, "edge")
        for s in (-1, 1):
            beam(f"GrabHandle_{side}_{s}", p + az * 0.10 + Vector((0, -0.55 + 0.35 * (s + 1), 0.30)),
                 p + az * 0.10 + Vector((0, 0.15 + 0.35 * (s + 1), 0.30)),
                 0.035, 0.035, "edge")


# ---------------------------------------------------------------------------
# Assembly / export
# ---------------------------------------------------------------------------
def build_plane():
    hull = build_hull()
    open_cargo_bay(hull)
    build_hull_details()
    build_canopy()
    for side in (-1, 1):
        build_wing(side)
    build_wing_details()
    build_tail()
    build_engine_deck()

    engine_specs = [
        ("EngineInner_R", 5.85, 6.95, 5.72, 8.6, 1.36, 1.24),
        ("EngineInner_L", -5.85, 6.95, 5.72, 8.6, 1.36, 1.24),
        ("EngineOuter_R", 11.40, 7.55, 5.56, 8.0, 1.26, 1.14),
        ("EngineOuter_L", -11.40, 7.55, 5.56, 8.0, 1.26, 1.14),
    ]
    for spec in engine_specs:
        build_engine(*spec)
    build_cargo_bay()
    build_greebles()


def join_and_finish():
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise RuntimeError("No mesh objects to join")
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    hull = bpy.data.objects.get("Fuselage") or meshes[0]
    bpy.context.view_layer.objects.active = hull
    bpy.ops.object.join()
    obj = bpy.context.active_object
    obj.name = "PlaneCargoElite"
    obj.data.name = "PlaneCargoEliteMesh"

    # dedupe material slots, keep a clean fixed order
    old_mats = list(obj.data.materials)
    unique = []
    remap = {}
    for m in old_mats:
        if m is None:
            continue
        if m.name not in remap:
            remap[m.name] = len(unique)
            unique.append(m)
    new_indices = []
    for poly in obj.data.polygons:
        old = old_mats[poly.material_index] if poly.material_index < len(old_mats) else None
        new_indices.append(remap.get(old.name, 0) if old else 0)
        poly.use_smooth = False
    # Clearing the slot list resets every polygon to index 0, so assign the
    # remapped indices only after the clean material list is rebuilt.
    obj.data.materials.clear()
    for m in unique:
        obj.data.materials.append(m)
    for poly, index in zip(obj.data.polygons, new_indices):
        poly.material_index = index
    obj.data.update()

    # normalise to exactly 45.0 m span x 35.0 m length, then set origin at
    # bottom-centre (0, 0, 0).
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    zs = [v.co.z for v in obj.data.vertices]
    span = max(xs) - min(xs)
    length = max(ys) - min(ys)
    sx = TARGET_SPAN / span
    sy = TARGET_LENGTH / length
    sz = sy
    obj.data.transform(Matrix.Diagonal((sx, sy, sz, 1.0)))
    obj.data.update()
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    zs = [v.co.z for v in obj.data.vertices]
    cx = (max(xs) + min(xs)) * 0.5
    cy = (max(ys) + min(ys)) * 0.5
    min_z = min(zs)
    obj.data.transform(Matrix.Translation(Vector((-cx, -cy, -min_z))))
    obj.data.update()
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    obj.data.validate(clean_customdata=True)
    return obj


def object_bbox(obj):
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    zs = [v.co.z for v in obj.data.vertices]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


def export_glb(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj = bpy.data.objects["PlaneCargoElite"]
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    kwargs = dict(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_image_format="NONE",
        export_texcoords=False,
        export_normals=True,
        export_tangents=False,
        export_cameras=False,
        export_lights=False,
        export_extras=True,
        export_animations=False,
    )
    try:
        bpy.ops.export_scene.gltf(**kwargs)
    except TypeError:
        kwargs.pop("export_image_format", None)
        bpy.ops.export_scene.gltf(**kwargs)
    if not os.path.isfile(path):
        raise RuntimeError(f"Export failed: {path} not written")


def verify_glb(path: str) -> dict:
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"glTF":
        raise RuntimeError("Not a GLB file")
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_len])
    if gltf.get("images"):
        raise RuntimeError("Textures found — this asset must be solid-colour only")
    tris = 0
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if "indices" in prim:
                count = gltf["accessors"][prim["indices"]]["count"]
            else:
                count = gltf["accessors"][prim["attributes"]["POSITION"]]["count"]
            tris += count // 3
    pos_min = [1e9, 1e9, 1e9]
    pos_max = [-1e9, -1e9, -1e9]
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            acc = gltf["accessors"][prim["attributes"]["POSITION"]]
            for i in range(3):
                pos_min[i] = min(pos_min[i], acc["min"][i])
                pos_max[i] = max(pos_max[i], acc["max"][i])
    strengths = []
    for mat in gltf.get("materials", []):
        strength = (
            mat.get("extensions", {})
            .get("KHR_materials_emissive_strength", {})
            .get("emissiveStrength")
        )
        if strength is not None:
            strengths.append(strength)
    stats = {
        "bytes": len(data),
        "materials": len(gltf.get("materials", [])),
        "images": len(gltf.get("images", [])),
        "nodes": len(gltf.get("nodes", [])),
        "meshes": len(gltf.get("meshes", [])),
        "tris": tris,
        "emissive_strengths": strengths,
        "gltf_bbox": [round(pos_max[i] - pos_min[i], 3) for i in range(3)],
        "gltf_min": [round(v, 3) for v in pos_min],
        "gltf_max": [round(v, 3) for v in pos_max],
    }
    print(
        f"  verified {os.path.basename(path)}: {stats['bytes'] / 1024 / 1024:.2f} MB, "
        f"{stats['materials']} materials, {stats['images']} textures, "
        f"{stats['tris']:,} tris, glTF bbox {stats['gltf_bbox']} m, "
        f"min {stats['gltf_min']}, emissive {sorted(set(stats['emissive_strengths']))}"
    )
    if stats["tris"] > 120000:
        raise RuntimeError(f"Triangle budget exceeded: {stats['tris']}")
    if stats["materials"] < 10:
        raise RuntimeError("Expected at least 10 solid materials")
    return stats


def main() -> int:
    print(f"Blender {bpy.app.version_string} — Elite Cargo Plane generator")
    clear_scene()
    build_plane()
    obj = join_and_finish()
    x0, x1, y0, y1, z0, z1 = object_bbox(obj)
    tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    print(
        f"  PlaneCargoElite: {x1 - x0:.2f} m span x {y1 - y0:.2f} m length x "
        f"{z1 - z0:.2f} m tall | {len(obj.data.vertices):,} verts | "
        f"{len(obj.data.polygons):,} faces | ~{tris:,} tris | "
        f"{len(obj.data.materials)} materials | origin=({obj.location.x:.2f}, "
        f"{obj.location.y:.2f}, {obj.location.z:.2f}) | minZ={z0:.3f}"
    )
    if abs((x1 - x0) - TARGET_SPAN) > 0.01 or abs((y1 - y0) - TARGET_LENGTH) > 0.01:
        raise RuntimeError("Dimension normalisation failed")
    if abs(z0) > 1e-4:
        raise RuntimeError(f"Origin is not at the bottom: minZ={z0}")
    obj["asset"] = "plane_cargo_elite"
    obj["role"] = "Elite stealth cargo dropship for the Battle Royale drop sequence"
    obj["span_m"] = 45.0
    obj["length_m"] = 35.0
    obj["origin"] = "bottom-centre (0,0,0)"
    obj["textures"] = "none — 12 solid Principled BSDF materials"
    obj["greebles"] = "panel lines, access panels, vent banks, antennas, sensors, thrusters, crates"

    export_glb(OUT_PATH)
    stats = verify_glb(OUT_PATH)
    print(f"  Exported -> {os.path.relpath(OUT_PATH, REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
