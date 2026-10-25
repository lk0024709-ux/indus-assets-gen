#!/usr/bin/env python3
"""Low-poly tree generator — pine, oak and palm (bpy).

Three distinct tree types for Indus : Battle Royale, each built from solid
Principled BSDF colours (no image textures) and flat-shaded to stay cheap on
4 GB-RAM phones:

    docs/models/nature/tree_pine.glb   9.0 m   mountains / Aravalli foothills
    docs/models/nature/tree_oak.glb    9.0 m   forests / villages
    docs/models/nature/tree_palm.glb  12.0 m   beaches / lake shores

Design
------
* **Pine** — brown trunk cylinder with three stacked dark-green cones
  (shrinking radius, overlapping slightly so there is no gap between tiers).
* **Oak** — thick brown trunk with three tapered branches, under one large
  bright-green low-poly icosphere canopy, flattened to 82 % to read as bushy.
* **Palm** — a tall, gently curved light-brown trunk (rings swept along an
  arc, tapering 0.34 m -> 0.16 m) carrying 7 flat bright-green fronds that
  radiate like a star and arch up then droop at the tips.

Every trunk/limb is a swept ring frustum with real outward-facing normals,
every cone is a closed cap + tip fan, and every tree is one joined mesh with
its origin at the bottom centre (0, 0, 0) so it drops onto terrain in Godot
without a manual offset.

Run:
    pip install bpy
    python tools/generate_trees.py [--preview DIR]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys

import bpy
from mathutils import Matrix, Vector

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "nature")

# ---------------------------------------------------------------------------
# Palette — hex is sRGB, converted to linear so the GLB displays the requested
# colour exactly (glTF baseColorFactor is linear).
# ---------------------------------------------------------------------------
PALETTE = {
    # pine — bark + three tonal steps of dark green so the tiers read apart
    "pine_bark":    {"hex": "4A3423", "metallic": 0.0, "roughness": 0.92},
    "pine_low":     {"hex": "1E4023", "metallic": 0.0, "roughness": 0.88},
    "pine_mid":     {"hex": "244C28", "metallic": 0.0, "roughness": 0.88},
    "pine_high":    {"hex": "2A582D", "metallic": 0.0, "roughness": 0.88},
    # oak — lighter grey-brown bark, bright canopy
    "oak_bark":     {"hex": "5C4128", "metallic": 0.0, "roughness": 0.92},
    "oak_canopy":   {"hex": "4E8B2F", "metallic": 0.0, "roughness": 0.85},
    # palm — pale trunk, vivid fronds
    "palm_bark":    {"hex": "A07A50", "metallic": 0.0, "roughness": 0.90},
    "palm_frond":   {"hex": "4FA83C", "metallic": 0.0, "roughness": 0.82},
    # shared coconut/eye-level accent, unused unless a species needs it
    "palm_nut":     {"hex": "5A4326", "metallic": 0.0, "roughness": 0.80},
}

# name -> (target height, allowed range)
TREES = {
    "tree_pine": {"height": 9.0, "min": 8.0, "max": 10.0},
    "tree_oak":  {"height": 9.0, "min": 8.0, "max": 10.0},
    "tree_palm": {"height": 12.0, "min": 11.0, "max": 12.5},
}

TRUNK_SEGMENTS = 8       # ring resolution for trunks
LIMB_SEGMENTS = 6        # ring resolution for branches
CONE_SEGMENTS = 8        # ring resolution for pine cones


# ---------------------------------------------------------------------------
# Colour / material helpers
# ---------------------------------------------------------------------------
def srgb_to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def hex_to_linear_rgba(value: str) -> tuple[float, float, float, float]:
    value = value.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), 1.0)


def make_material(key: str):
    spec = PALETTE[key]
    mat = bpy.data.materials.new(f"TREE_{key}")
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
    for name, value in (("Alpha", 1.0), ("Emission Strength", 0.0)):
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = value
    mat.diffuse_color = rgba
    return mat


# ---------------------------------------------------------------------------
# Geometry helpers — all return (verts, faces) and get stitched by add_part
# ---------------------------------------------------------------------------
def mesh_object(name: str, verts, faces, material):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate(verbose=False)
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    me.materials.append(material)
    return obj


def _ring(center: Vector, right: Vector, up: Vector, radius: float, segments: int):
    pts = []
    for i in range(segments):
        a = 2.0 * math.pi * i / segments
        pts.append(center + right * (math.cos(a) * radius) + up * (math.sin(a) * radius))
    return pts


def frustum(center_xy, z0, z1, r0, r1, segments=TRUNK_SEGMENTS,
            cap_bottom=True, cap_top=True):
    """Vertical ring frustum; ``r1 == 0`` makes a cone with a tip fan."""
    cx, cy = center_xy
    verts, faces = [], []
    bottom = _ring(Vector((cx, cy, z0)), Vector((1, 0, 0)), Vector((0, 1, 0)),
                   r0, segments)
    verts.extend(tuple(p) for p in bottom)

    if r1 > 1e-6:
        top = _ring(Vector((cx, cy, z1)), Vector((1, 0, 0)), Vector((0, 1, 0)),
                    r1, segments)
        verts.extend(tuple(p) for p in top)
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((i, j, segments + j, segments + i))
        if cap_top:
            faces.append(tuple(range(segments, 2 * segments)))
    else:
        tip = len(verts)
        verts.append((cx, cy, z1))
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((i, j, tip))

    if cap_bottom:
        faces.append(tuple(reversed(range(segments))))
    return verts, faces


def tapered_limb(start, direction, length, r0, r1, segments=LIMB_SEGMENTS,
                 cap_start=True, cap_end=True):
    """Ring frustum swept along an arbitrary direction (branches, frond ribs)."""
    d = Vector(direction).normalized()
    ref = Vector((0, 0, 1)) if abs(d.z) < 0.95 else Vector((1, 0, 0))
    right = d.cross(ref).normalized()
    up = right.cross(d).normalized()

    a = Vector(start)
    b = a + d * length
    verts = [tuple(p) for p in _ring(a, right, up, r0, segments)]
    verts += [tuple(p) for p in _ring(b, right, up, r1, segments)]
    faces = []
    for i in range(segments):
        j = (i + 1) % segments
        faces.append((i, j, segments + j, segments + i))
    if cap_end:
        faces.append(tuple(range(segments, 2 * segments)))
    if cap_start:
        faces.append(tuple(reversed(range(segments))))
    return verts, faces


def curved_trunk(base_xy, height, r_base, r_top, lean, bend, segments=TRUNK_SEGMENTS,
                 rings=9):
    """Trunk swept along a gentle arc: x = lean * t**bend, radius tapers."""
    cx, cy = base_xy
    verts, faces = [], []
    for k in range(rings):
        t = k / (rings - 1)
        z = height * t
        x = cx + lean * (t ** bend)
        radius = r_base * (1.0 - t) + r_top * t
        verts.extend(tuple(p) for p in _ring(Vector((x, cy, z)),
                                             Vector((1, 0, 0)), Vector((0, 1, 0)),
                                             radius, segments))
    for k in range(rings - 1):
        a, b = k * segments, (k + 1) * segments
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((a + i, a + j, b + j, b + i))
    faces.append(tuple(reversed(range(segments))))                      # base cap
    faces.append(tuple(range((rings - 1) * segments, rings * segments)))  # top cap
    return verts, faces


def ridged_frond(origin, yaw, length, rise, droop, widths, fold=0.42,
                 stations=(0.0, 0.25, 0.5, 0.75, 1.0)):
    """A palm frond with a raised centre spine, arching up then drooping.

    Three vertices per station (left, raised centre, right) instead of a flat
    quad: the ridge gives the frond volume so it still reads from edge-on
    angles, which is the failure mode of flat planes in a game camera.
    """
    ox, oy, oz = origin
    verts = []
    for station, w in zip(stations, widths):
        d = length * station
        z = oz + rise * math.sin(math.pi * min(station, 1.0) * 0.92) \
            - droop * (station ** 2) * length
        px = ox + math.cos(yaw) * d
        py = oy + math.sin(yaw) * d
        perp = Vector((-math.sin(yaw), math.cos(yaw), 0.0))
        centre = Vector((px, py, z + fold * w * 0.5))
        left = Vector((px, py, z)) + perp * w
        right = Vector((px, py, z)) - perp * w
        verts.extend([tuple(left), tuple(centre), tuple(right)])

    faces = []
    for i in range(len(stations) - 1):
        l0, c0, r0 = i * 3, i * 3 + 1, i * 3 + 2
        l1, c1, r1 = (i + 1) * 3, (i + 1) * 3 + 1, (i + 1) * 3 + 2
        faces.append((l0, c0, c1, l1))
        faces.append((c0, r0, r1, c1))
    return verts, faces


def icosphere(name, center, radius, subdivisions, scale_z, material):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=subdivisions, radius=radius,
                                          location=(0, 0, 0))
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = name
    obj.data.transform(Matrix.Diagonal((1.0, 1.0, scale_z, 1.0)))
    obj.data.transform(Matrix.Translation(Vector(center)))
    obj.data.update()
    obj.data.materials.append(material)
    return obj


def _merge_into(target_obj, parts):
    """Join every part object into ``target_obj`` (the exported mesh)."""
    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts:
        obj.select_set(True)
    target_obj.select_set(True)
    bpy.context.view_layer.objects.active = target_obj
    if len(parts) > 1:
        bpy.ops.object.join()
    return bpy.context.view_layer.objects.active


# ---------------------------------------------------------------------------
# Species
# ---------------------------------------------------------------------------
def build_pine(materials):
    parts = []

    # trunk: visible between the ground and the lowest cone skirt
    v, f = frustum((0.0, 0.0), 0.0, 2.65, 0.28, 0.19, TRUNK_SEGMENTS)
    parts.append(mesh_object("Pine_Trunk", v, f, materials["pine_bark"]))

    # three stacked cones (base radius, base z, apex z) — overlapping tiers
    tiers = [
        ("Pine_Cone_Low",  2.35, 1.55, 5.05, "pine_low"),
        ("Pine_Cone_Mid",  1.78, 3.95, 7.15, "pine_mid"),
        ("Pine_Cone_High", 1.20, 6.05, 9.00, "pine_high"),
    ]
    for name, radius, z0, z1, key in tiers:
        v, f = frustum((0.0, 0.0), z0, z1, radius, 0.0, CONE_SEGMENTS)
        parts.append(mesh_object(name, v, f, materials[key]))
    return parts


def build_oak(materials):
    parts = []

    # thick trunk: splits into limbs higher up so the canopy looks supported
    v, f = frustum((0.0, 0.0), 0.0, 3.55, 0.62, 0.42, TRUNK_SEGMENTS)
    parts.append(mesh_object("Oak_Trunk", v, f, materials["oak_bark"]))

    # four branches fanning up into the canopy from different heights
    branches = [
        ((0.06, 0.02, 2.30), (0.78, 0.22, 0.58), 2.15, 0.24, 0.12),
        ((-0.10, 0.05, 2.55), (-0.72, 0.40, 0.57), 2.05, 0.22, 0.11),
        ((0.02, -0.08, 2.15), (0.16, -0.82, 0.55), 1.95, 0.20, 0.10),
        ((-0.04, -0.02, 2.95), (0.32, 0.60, 0.73), 1.35, 0.16, 0.09),
    ]
    for i, (start, direction, length, r0, r1) in enumerate(branches):
        v, f = tapered_limb(start, direction, length, r0, r1, LIMB_SEGMENTS)
        parts.append(mesh_object(f"Oak_Branch_{i + 1}", v, f, materials["oak_bark"]))

    # canopy: one flattened low-poly mass, then a few offset lobes so the
    # silhouette reads as a bushy crown instead of a bowling ball on a stick
    parts.append(icosphere("Oak_Canopy", (0.0, 0.0, 6.05), 2.85, 2, 0.86,
                           materials["oak_canopy"]))
    lobes = [
        ("Oak_Lobe_N", (1.75, 0.55, 6.55), 1.75, 0.90),
        ("Oak_Lobe_W", (-1.85, -0.35, 5.75), 1.65, 0.88),
        ("Oak_Lobe_E", (0.35, 1.90, 5.85), 1.55, 0.92),
        ("Oak_Lobe_Top", (-0.55, -0.85, 7.35), 1.45, 0.88),
    ]
    for name, center, radius, squash in lobes:
        parts.append(icosphere(name, center, radius, 2, squash,
                               materials["oak_canopy"]))
    return parts


def build_palm(materials):
    parts = []

    trunk_h = 11.35
    lean = 1.55                       # clearly but gently curved
    v, f = curved_trunk((0.0, 0.0), trunk_h, 0.34, 0.17, lean, bend=1.9,
                        segments=TRUNK_SEGMENTS, rings=10)
    parts.append(mesh_object("Palm_Trunk", v, f, materials["palm_bark"]))

    # crown sits at the (leaned) top of the trunk
    crown = (lean, 0.0, trunk_h)

    # 8 fronds radiating like a star; alternating length and pitch keeps the
    # silhouette varied so no two fronds line up with the camera.
    count = 8
    for i in range(count):
        yaw = 2.0 * math.pi * i / count + math.radians(10.0)
        even = i % 2 == 0
        length = 4.85 if even else 4.35
        rise = 0.34 if even else 0.27
        droop = 0.19 if even else 0.26
        widths = (0.10, 0.46, 0.66, 0.44, 0.05)
        v, f = ridged_frond(crown, yaw, length, rise, droop, widths)
        parts.append(mesh_object(f"Palm_Frond_{i + 1}", v, f,
                                 materials["palm_frond"]))

    # crown nub so the fronds do not appear to float off the trunk
    v, f = frustum((lean, 0.0), trunk_h - 0.42, trunk_h + 0.26, 0.32, 0.13,
                   TRUNK_SEGMENTS)
    parts.append(mesh_object("Palm_Crown", v, f, materials["palm_bark"]))
    return parts


BUILDERS = {
    "tree_pine": (build_pine, ["pine_bark", "pine_low", "pine_mid", "pine_high"]),
    "tree_oak": (build_oak, ["oak_bark", "oak_canopy"]),
    "tree_palm": (build_palm, ["palm_bark", "palm_frond"]),
}


# ---------------------------------------------------------------------------
# Finish / export / verify
# ---------------------------------------------------------------------------
def finish_tree(obj, name: str, target_height: float):
    """Flat shade, normalise to the exact height, origin at bottom-centre."""
    me = obj.data
    for poly in me.polygons:
        poly.use_smooth = False
    # Drop any inherited split normals so flat shading actually reads flat.
    attr = me.attributes.get("custom_normal")
    if attr is not None:
        me.attributes.remove(attr)

    zs = [v.co.z for v in me.vertices]
    height = max(zs) - min(zs)
    if height <= 0:
        raise RuntimeError("Degenerate mesh")
    scale = target_height / height
    me.transform(Matrix.Diagonal((scale, scale, scale, 1.0)))

    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    cx = (max(xs) + min(xs)) * 0.5
    cy = (max(ys) + min(ys)) * 0.5
    me.transform(Matrix.Translation((-cx, -cy, -min(zs))))
    me.update()

    obj.name = name
    me.name = name
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    return obj


def export_glb(obj, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
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
        export_animations=False,
        export_extras=True,
    )
    try:
        bpy.ops.export_scene.gltf(**kwargs)
    except TypeError:
        for option in ("export_image_format", "export_extras", "export_tangents"):
            kwargs.pop(option, None)
        bpy.ops.export_scene.gltf(**kwargs)
    if not os.path.isfile(path):
        raise RuntimeError(f"Export failed: {path} not written")


def verify_glb(path: str, heights: dict) -> dict:
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"glTF":
        raise RuntimeError("Not a GLB file")
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_len])

    if gltf.get("images"):
        raise RuntimeError("Textures found — this asset must be solid-colour only")

    tris = 0
    pos_min = [1e9] * 3
    pos_max = [-1e9] * 3
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if "indices" in prim:
                count = gltf["accessors"][prim["indices"]]["count"]
            else:
                count = gltf["accessors"][prim["attributes"]["POSITION"]]["count"]
            tris += count // 3
            acc = gltf["accessors"][prim["attributes"]["POSITION"]]
            for i in range(3):
                pos_min[i] = min(pos_min[i], acc["min"][i])
                pos_max[i] = max(pos_max[i], acc["max"][i])

    height = pos_max[1] - pos_min[1]
    stats = {
        "bytes": len(data),
        "materials": len(gltf.get("materials", [])),
        "images": len(gltf.get("images", [])),
        "tris": tris,
        "height_m": round(height, 3),
        "gltf_min": [round(v, 4) for v in pos_min],
        "gltf_max": [round(v, 4) for v in pos_max],
        "material_names": [m.get("name") for m in gltf.get("materials", [])],
    }
    if abs(stats["gltf_min"][1]) > 1e-3:
        raise RuntimeError(f"Origin is not at the bottom: minY={stats['gltf_min'][1]}")
    if not (heights["min"] <= stats["height_m"] <= heights["max"]):
        raise RuntimeError(
            f"Height {stats['height_m']} m outside {heights['min']}-{heights['max']} m"
        )
    if tris > 800:
        raise RuntimeError(f"Triangle budget exceeded: {tris}")
    return stats


def object_bbox(obj):
    xs = [v.co.x for v in obj.data.vertices]
    ys = [v.co.y for v in obj.data.vertices]
    zs = [v.co.z for v in obj.data.vertices]
    return min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)


# ---------------------------------------------------------------------------
# Optional QA preview (Cycles CPU — headless friendly)
# ---------------------------------------------------------------------------
def render_preview(obj, out_path: str, height: float) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 48
    scene.render.resolution_x = 640
    scene.render.resolution_y = 720
    scene.world = bpy.data.worlds.new("PreviewWorld")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.48, 0.62, 0.78, 1.0)   # daylight sky
    bg.inputs[1].default_value = 1.1

    ground = bpy.data.meshes.new("Ground")
    size = 30.0
    ground.from_pydata([(-size, -size, 0), (size, -size, 0), (size, size, 0), (-size, size, 0)],
                       [], [(0, 1, 2, 3)])
    gmat = bpy.data.materials.new("GroundMat")
    gmat.use_nodes = True
    gbsdf = gmat.node_tree.nodes["Principled BSDF"]
    gbsdf.inputs["Base Color"].default_value = hex_to_linear_rgba("6F7F49")
    gbsdf.inputs["Roughness"].default_value = 0.95
    ground.materials.append(gmat)
    gobj = bpy.data.objects.new("Ground", ground)
    scene.collection.objects.link(gobj)

    sun = bpy.data.lights.new("Sun", "SUN")
    sun.energy = 3.4
    sun.angle = math.radians(6)
    sobj = bpy.data.objects.new("Sun", sun)
    scene.collection.objects.link(sobj)
    sobj.location = (6, -8, 14)
    sobj.rotation_euler = (math.radians(52), 0, math.radians(38))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 55
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    dist = height * 2.1
    cam.location = (dist * 0.62, -dist * 0.78, height * 0.62)
    cam.rotation_euler = (
        math.atan2(math.hypot(cam.location[0], cam.location[1]), cam.location[2] - height * 0.46),
        0.0,
        math.atan2(cam.location[1], cam.location[0]) + math.pi / 2,
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)


# ---------------------------------------------------------------------------
def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def build_tree(name: str, preview_dir: str | None = None) -> dict:
    spec = TREES[name]
    builder, material_keys = BUILDERS[name]
    clear_scene()

    materials = {key: make_material(key) for key in material_keys}
    parts = builder(materials)
    obj = _merge_into(parts[0], parts)
    finish_tree(obj, name, spec["height"])

    obj["asset"] = name
    obj["height_m"] = spec["height"]
    obj["origin"] = "bottom-centre (0,0,0)"
    obj["textures"] = "none — solid Principled BSDF colours only"
    obj["shading"] = "flat"

    tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    x0, x1, y0, y1, z0, z1 = object_bbox(obj)
    print(f"  {name}: {z1 - z0:.2f} m tall x {x1 - x0:.2f} m wide | "
          f"{len(obj.data.vertices)} verts | {len(obj.data.polygons)} faces | "
          f"~{tris} tris | {len(obj.data.materials)} materials | "
          f"minZ={z0:.4f} | mats={[m.name for m in obj.data.materials]}")

    if preview_dir:
        render_preview(obj, os.path.join(preview_dir, f"{name}.png"), spec["height"])

    out_path = os.path.join(OUT_DIR, f"{name}.glb")
    export_glb(obj, out_path)
    stats = verify_glb(out_path, spec)
    print(f"    verified: {stats['bytes'] / 1024:.1f} KB, {stats['materials']} materials, "
          f"{stats['images']} textures, {stats['tris']} tris, height {stats['height_m']} m, "
          f"min {stats['gltf_min']}")
    return {**stats, "object": name, "file": f"models/nature/{name}.glb"}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--preview", metavar="DIR", default=None,
                        help="render a QA PNG per tree into DIR")
    args = parser.parse_args(argv)

    print(f"Blender {bpy.app.version_string} — low-poly tree generator")
    results = [build_tree(name, args.preview) for name in TREES]
    total = sum(r["tris"] for r in results)
    print(f"  Exported {len(results)} trees to "
          f"{os.path.relpath(OUT_DIR, REPO_ROOT)} ({total} tris total)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
