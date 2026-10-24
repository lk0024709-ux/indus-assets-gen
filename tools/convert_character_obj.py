#!/usr/bin/env python3
"""Player Tactical character — OBJ -> solid-colour GLB converter (bpy).

Godot chokes on the raw ``Male_Suit.obj``: the ``.mtl`` references an external
tie texture, the material names mean nothing to the engine, and the file is
Y-up with an arbitrary unit scale. This tool imports the OBJ, throws away the
broken MTL materials, rebuilds them as **solid Principled BSDF materials**,
joins the mesh, and exports one game-ready character:

    docs/models/characters/player_tactical.glb

Source
------
``downloaded_obj/characters/Male_Suit.obj`` — Quaternius "Animated Men
Characters" pack (CC0). Low-poly male in business suit / tactical build:
1,044 verts, 1,165 faces, 7 OBJ material groups.

Colour mapping
--------------
The OBJ's own ``usemtl`` groups already separate the body into the parts the
brief asks for, so we colour **by geometry, not by guesswork**:

    OBJ group     Body part                  Final colour
    ---------     ------------------------   ---------------------------
    Skin          head, neck, hands          #D2A679  skin tone
    Shirt         torso + arms               #2C3E50  dark tactical shirt
    Pants         legs                       #1A1A1A  pants
    Hair          hair                       #241A18
    Eyes          eyeballs / brows           #F2F0EA
    Eyes (feet)   shoe soles                 #101112  (split by height)
    Details       belt, buttons, glasses     #5A616B
    TieTexture    tie                        #16202B

Each colour is converted **sRGB -> linear** before it reaches the shader, so
the hex in the code is the hex you see in the GLB (``baseColorFactor`` is
linear in glTF).

Run:
    pip install bpy
    python tools/convert_character_obj.py [--shading flat|smooth] [--preview DIR]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys

import bpy
from mathutils import Matrix

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OBJ_PATH = os.path.join(REPO_ROOT, "downloaded_obj", "characters", "Male_Suit.obj")
OUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "characters")
OUT_PATH = os.path.join(OUT_DIR, "player_tactical.glb")

ASSET_NAME = "player_tactical"
OBJ_NAME = "PlayerTactical"

TARGET_HEIGHT_M = 1.80   # metres — human male, matches the repo's metre scale
FEET_FRACTION = 0.15     # anything below 15 % of body height is "footwear"
SMOOTH_ANGLE_DEG = 40.0  # angle-based smoothing for the "smooth" mode

# ---------------------------------------------------------------------------
# Palette — hex is sRGB, converted to linear so the GLB displays the
# requested colour exactly (glTF baseColorFactor is linear).
# ---------------------------------------------------------------------------
PALETTE = {
    "skin":    {"hex": "D2A679", "metallic": 0.00, "roughness": 0.72},
    "shirt":   {"hex": "2C3E50", "metallic": 0.00, "roughness": 0.80},
    "pants":   {"hex": "1A1A1A", "metallic": 0.00, "roughness": 0.85},
    "hair":    {"hex": "241A18", "metallic": 0.00, "roughness": 0.75},
    "eyes":    {"hex": "F2F0EA", "metallic": 0.00, "roughness": 0.35},
    "shoes":   {"hex": "101112", "metallic": 0.00, "roughness": 0.60},
    "details": {"hex": "5A616B", "metallic": 0.35, "roughness": 0.45},
    "tie":     {"hex": "16202B", "metallic": 0.00, "roughness": 0.70},
}

# OBJ material name (normalised) -> palette key
GROUP_MAP = {
    "skin": "skin",
    "shirt": "shirt",
    "pants": "pants",
    "hair": "hair",
    "eyes": "eyes",
    "details": "details",
    "tietexture": "tie",
}

MATERIAL_NAMES = {
    "skin": "Skin",
    "shirt": "TacticalShirt",
    "pants": "Pants",
    "hair": "Hair",
    "eyes": "Eyes",
    "shoes": "Shoes",
    "details": "Details",
    "tie": "Tie",
}


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def srgb_to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def linear_to_srgb(channel: float) -> float:
    return channel * 12.92 if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def hex_to_linear_rgba(value: str) -> tuple[float, float, float, float]:
    value = value.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), 1.0)


def linear_rgba_to_hex(rgba) -> str:
    return "".join(
        f"{max(0, min(255, round(linear_to_srgb(c) * 255))):02X}" for c in rgba[:3]
    )


def set_bsdf_input(bsdf, names, value) -> bool:
    for name in names:
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = value
            return True
    return False


def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    # The OBJ importer is an operator extension; make sure it is available.
    try:
        import addon_utils
        # The glTF exporter is a bundled extension; older bpy builds ship it
        # as an add-on that must be enabled explicitly.
        try:
            addon_utils.enable("io_scene_gltf2", default_set=True, persistent=True)
        except Exception:
            pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# TASK 1 — import the OBJ
# ---------------------------------------------------------------------------
def import_obj(filepath: str):
    """Import an OBJ and return the list of imported mesh objects.

    Blender <= 3.6 ships the legacy ``bpy.ops.import_scene.obj`` operator.
    Blender 4.0 removed it in favour of the C++ ``bpy.ops.wm.obj_import``,
    which is what ``pip install bpy`` gives you today (4.2 here). We call the
    requested operator first and only fall back when it genuinely does not
    exist, so the script works on both the CI's latest bpy and older Blender.
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"OBJ not found: {filepath}")
    before = {o.name for o in bpy.data.objects}
    try:
        # Legacy operator (Blender 2.8 – 3.6) — preferred when present.
        bpy.ops.import_scene.obj(filepath=filepath)
        importer = "bpy.ops.import_scene.obj (legacy OBJ importer)"
    except AttributeError:
        # Blender 4.x: the OBJ I/O is now the bundled "Wavefront OBJ" extension.
        bpy.ops.wm.obj_import(filepath=filepath)
        importer = "bpy.ops.wm.obj_import (Blender 4.x replacement)"
    imported = [o for o in bpy.data.objects if o.name not in before and o.type == "MESH"]
    if not imported:
        raise RuntimeError("OBJ import produced no mesh objects")
    print(f"  importer: {importer}")
    print(f"  imported: {len(imported)} mesh object(s) — "
          f"{sum(len(o.data.polygons) for o in imported):,} faces")
    return imported


# ---------------------------------------------------------------------------
# TASK 2a — join into one mesh
# ---------------------------------------------------------------------------
def join_meshes(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    if len(objects) > 1:
        bpy.ops.object.join()
        print(f"  joined {len(objects)} parts into one mesh")
    else:
        print("  single mesh — nothing to join")
    obj = bpy.context.view_layer.objects.active
    obj.name = OBJ_NAME
    obj.data.name = OBJ_NAME
    return obj


# ---------------------------------------------------------------------------
# TASK 2b — orient, scale, origin
# ---------------------------------------------------------------------------
def normalise_transform(obj):
    """Y-up OBJ -> Z-up Blender, 1.80 m tall, origin at bottom-centre.

    The source faces +Z (the tie sits on +Z of the chest), and the OBJ "up"
    axis is +Y. Rotating +90 deg about X maps Y->Z (up) and Z->-Y, which the
    glTF exporter's Y-up conversion turns back into +Z facing the viewer.
    """
    me = obj.data
    me.transform(Matrix.Rotation(math.radians(90.0), 4, "X"))
    me.update()

    zs = [v.co.z for v in me.vertices]
    height = max(zs) - min(zs)
    if height <= 0:
        raise RuntimeError("Degenerate mesh (zero height)")
    scale = TARGET_HEIGHT_M / height
    me.transform(Matrix.Diagonal((scale, scale, scale, 1.0)))
    me.update()

    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    cx = (max(xs) + min(xs)) * 0.5
    cy = (max(ys) + min(ys)) * 0.5
    min_z = min(zs)
    me.transform(Matrix.Translation((-cx, -cy, -min_z)))
    me.update()

    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    print(f"  scaled x{scale:.4f} -> {TARGET_HEIGHT_M:.2f} m tall, "
          f"origin at bottom-centre (0, 0, 0)")
    return obj


# ---------------------------------------------------------------------------
# TASK 2c — replace the broken MTL materials with solid Principled BSDF ones
# ---------------------------------------------------------------------------
def make_material(key: str):
    spec = PALETTE[key]
    mat = bpy.data.materials.new(MATERIAL_NAMES[key])
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
    # A character must never be transparent or emissive.
    set_bsdf_input(bsdf, ("Alpha",), 1.0)
    set_bsdf_input(bsdf, ("Emission Strength",), 0.0)
    set_bsdf_input(bsdf, ("Emission Color", "Emission"), (0.0, 0.0, 0.0, 1.0))
    mat.diffuse_color = rgba
    return mat


def normalise_group_name(name: str) -> str:
    base = name.split(".")[0].strip().lower()
    return "".join(ch for ch in base if ch.isalnum())


def assign_solid_materials(obj):
    """Rebuild every material slot as a solid colour, keyed off the OBJ groups."""
    me = obj.data
    if not me.materials:
        raise RuntimeError("Imported mesh has no material groups to key colours from")

    slot_keys = []
    for slot in me.materials:
        key = GROUP_MAP.get(normalise_group_name(slot.name))
        if key is None:
            print(f"  ! unknown OBJ group '{slot.name}' -> neutral grey")
            key = None
        slot_keys.append(key)

    zs = [v.co.z for v in me.vertices]
    feet_h = min(zs) + (max(zs) - min(zs)) * FEET_FRACTION

    # Decide a palette key per polygon *before* the slot list is rebuilt.
    poly_keys = []
    unknown = 0
    for poly in me.polygons:
        key = slot_keys[poly.material_index] if poly.material_index < len(slot_keys) else None
        if key is None:
            key = "details"
            unknown += 1
        # The "Eyes" group also carries the shoe soles down at the feet.
        if key == "eyes" and poly.center.z < feet_h:
            key = "shoes"
        poly_keys.append(key)

    order = []
    for key in poly_keys:
        if key not in order:
            order.append(key)

    # Drop the imported MTL materials so our clean names ("Skin", "Pants", ...)
    # are not forced to collide into "Skin.001" — Godot shows these names.
    stale = list(me.materials)
    me.materials.clear()
    for mat in stale:
        if mat is not None and mat.users == 0 and mat.name in bpy.data.materials:
            bpy.data.materials.remove(mat)

    materials = {key: make_material(key) for key in order}

    for key in order:
        me.materials.append(materials[key])
    index_of = {key: i for i, key in enumerate(order)}
    for poly, key in zip(me.polygons, poly_keys):
        poly.material_index = index_of[key]
    me.update()

    if unknown:
        print(f"  ! {unknown} face(s) had no usable group -> neutral grey")

    counts = {}
    for key in poly_keys:
        counts[key] = counts.get(key, 0) + 1
    print("  solid Principled BSDF materials:")
    for key in order:
        spec = PALETTE[key]
        print(f"    {MATERIAL_NAMES[key]:14s} #{spec['hex']}  {counts[key]:4d} faces  "
              f"(metallic {spec['metallic']:.2f}, roughness {spec['roughness']:.2f})")
    return materials


# ---------------------------------------------------------------------------
# TASK 2d — shading
# ---------------------------------------------------------------------------
def clear_custom_normals(obj) -> None:
    """Drop the OBJ's baked split normals so the shading mode decides."""
    me = obj.data
    try:
        with bpy.context.temp_override(object=obj, active_object=obj,
                                       selected_objects=[obj],
                                       selected_editable_objects=[obj]):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
        return
    except Exception:
        pass
    attr = me.attributes.get("custom_normal")
    if attr is not None:
        me.attributes.remove(attr)


def set_shading(obj, mode: str) -> None:
    """mode: "flat" | "smooth"."""
    me = obj.data
    clear_custom_normals(obj)
    if mode == "flat":
        for poly in me.polygons:
            poly.use_smooth = False
        print("  shading: flat (faceted low-poly look)")
        return

    for poly in me.polygons:
        poly.use_smooth = True
    angle = math.radians(SMOOTH_ANGLE_DEG)
    # Blender 4.1+ replaced auto-smooth with sharp-edge storage on the mesh.
    if hasattr(me, "set_sharp_from_angle"):
        me.set_sharp_from_angle(angle=angle)
    else:  # Blender <= 4.0
        me.use_auto_smooth = True
        me.auto_smooth_angle = angle
    me.update()
    print(f"  shading: smooth by angle ({SMOOTH_ANGLE_DEG:.0f}°) — hard edges kept")


# ---------------------------------------------------------------------------
# TASK 2e — export
# ---------------------------------------------------------------------------
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
        export_texcoords=False,  # solid colours only: UVs would be dead weight
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


def verify_glb(path: str) -> dict:
    """Parse the GLB back and prove it is solid-colour, correct size, no textures."""
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

    found = {}
    for mat in gltf.get("materials", []):
        pbr = mat.get("pbrMetallicRoughness", {})
        if "baseColorTexture" in pbr:
            raise RuntimeError(f"Material '{mat.get('name')}' still references a texture")
        factor = pbr.get("baseColorFactor", [1, 1, 1, 1])
        found[mat.get("name")] = linear_rgba_to_hex(factor)

    expected = {MATERIAL_NAMES[k]: v["hex"] for k, v in PALETTE.items()}
    print("  GLB materials (baseColorFactor -> sRGB):")
    for name, hex_value in found.items():
        want = expected.get(name)
        flag = ""
        if want is None:
            flag = "  (extra)"
        elif want.upper() != hex_value.upper():
            flag = f"  !! expected #{want}"
        print(f"    {name:14s} #{hex_value}{flag}")

    for name, want in expected.items():
        if name in found and found[name].upper() != want.upper():
            raise RuntimeError(f"{name}: colour {found[name]} != requested {want}")

    missing = [n for n in expected if n not in found]
    if missing:
        print(f"  note: unused palette slots not present in mesh: {missing}")

    height = pos_max[1] - pos_min[1]
    stats = {
        "bytes": len(data),
        "materials": len(gltf.get("materials", [])),
        "images": len(gltf.get("images", [])),
        "nodes": len(gltf.get("nodes", [])),
        "meshes": len(gltf.get("meshes", [])),
        "tris": tris,
        "height_m": round(height, 3),
        "gltf_min": [round(v, 4) for v in pos_min],
        "gltf_max": [round(v, 4) for v in pos_max],
    }
    print(f"  verified {os.path.basename(path)}: {stats['bytes'] / 1024:.1f} KB, "
          f"{stats['materials']} materials, {stats['images']} textures, "
          f"{stats['tris']:,} tris, height {stats['height_m']} m, "
          f"min {stats['gltf_min']}")

    if abs(stats["height_m"] - TARGET_HEIGHT_M) > 0.01:
        raise RuntimeError(f"Height {stats['height_m']} m != {TARGET_HEIGHT_M} m")
    if abs(stats["gltf_min"][1]) > 1e-3:
        raise RuntimeError(f"Origin is not at the feet: minY={stats['gltf_min'][1]}")
    if stats["materials"] < 5:
        raise RuntimeError(f"Expected >= 5 solid materials, got {stats['materials']}")
    if stats["tris"] <= 0:
        raise RuntimeError("No triangles exported")
    return stats


# ---------------------------------------------------------------------------
# Optional QA preview render (Cycles CPU — headless friendly)
# ---------------------------------------------------------------------------
def render_previews(obj, out_dir: str) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 48
    scene.render.resolution_x = 512
    scene.render.resolution_y = 768
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("PreviewWorld")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.16, 0.17, 0.19, 1.0)
    bg.inputs[1].default_value = 1.0

    key = bpy.data.lights.new("Key", "AREA")
    key.energy = 420
    key.size = 3.0
    key_obj = bpy.data.objects.new("Key", key)
    scene.collection.objects.link(key_obj)
    key_obj.location = (2.6, -3.0, 3.4)
    key_obj.rotation_euler = (math.radians(52), 0, math.radians(40))

    fill = bpy.data.lights.new("Fill", "AREA")
    fill.energy = 160
    fill.size = 4.0
    fill_obj = bpy.data.objects.new("Fill", fill)
    scene.collection.objects.link(fill_obj)
    fill_obj.location = (-3.0, -2.0, 1.8)
    fill_obj.rotation_euler = (math.radians(78), 0, math.radians(-55))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 60
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    os.makedirs(out_dir, exist_ok=True)
    height = TARGET_HEIGHT_M
    views = {
        "front": (0.0, -3.2, height * 0.58),
        "three_quarter": (2.3, -2.3, height * 0.62),
        "side": (3.2, 0.0, height * 0.58),
        "back": (0.0, 3.2, height * 0.58),
    }
    for name, (x, y, z) in views.items():
        cam.location = (x, y, z)
        direction = (0.0, 0.0, height * 0.52)
        cam.rotation_euler = (
            math.atan2(math.hypot(x, y), z - direction[2]),
            0.0,
            math.atan2(y, x) + math.pi / 2,
        )
        scene.render.filepath = os.path.join(out_dir, f"preview_{name}.png")
        bpy.ops.render.render(write_still=True)
        print(f"  preview -> {scene.render.filepath}")


# ---------------------------------------------------------------------------
def build(shading: str = "smooth"):
    print(f"Blender {bpy.app.version_string} — player_tactical OBJ -> GLB")
    clear_scene()
    print(f"  source: {os.path.relpath(OBJ_PATH, REPO_ROOT)}")
    imported = import_obj(OBJ_PATH)
    obj = join_meshes(imported)
    normalise_transform(obj)
    assign_solid_materials(obj)
    set_shading(obj, shading)

    obj["asset"] = ASSET_NAME
    obj["role"] = "Player character — Battle Royale tactical build"
    obj["source"] = "downloaded_obj/characters/Male_Suit.obj (Quaternius, CC0)"
    obj["height_m"] = TARGET_HEIGHT_M
    obj["origin"] = "bottom-centre (0,0,0)"
    obj["textures"] = "none — solid Principled BSDF colours only"
    obj["palette"] = ", ".join(f"{MATERIAL_NAMES[k]}=#{v['hex']}" for k, v in PALETTE.items())
    obj["shading"] = shading
    return obj


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--shading", choices=("flat", "smooth"), default="smooth")
    parser.add_argument("--preview", metavar="DIR", default=None,
                        help="also render QA turntable PNGs into DIR")
    args = parser.parse_args(argv)

    obj = build(args.shading)
    if args.preview:
        render_previews(obj, args.preview)
    export_glb(obj, OUT_PATH)
    verify_glb(OUT_PATH)
    print(f"  Exported -> {os.path.relpath(OUT_PATH, REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
