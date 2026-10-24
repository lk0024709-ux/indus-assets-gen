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
``docs/models/Character/Male_Suit.obj`` (or ``downloaded_obj/characters/``)
— Quaternius "Animated Men Characters" pack (CC0). Low-poly male in a suit:
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

For the whole roster in one go, see ``convert_characters_batch.py``.

Run:
    pip install bpy
    python tools/convert_character_obj.py [--shading flat|smooth] [--preview DIR]
"""

from __future__ import annotations

import argparse
import os
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import character_lib as lib  # noqa: E402  (needs the path tweak above)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Where the raw character OBJ can live. The repo keeps the upload in
# docs/models/Character/; downloaded_obj/characters/ is kept as a fallback for
# a local drop of the same Quaternius file (the two are byte-identical).
OBJ_CANDIDATES = (
    os.path.join(REPO_ROOT, "downloaded_obj", "characters", "Male_Suit.obj"),
    os.path.join(REPO_ROOT, "docs", "models", "Character", "Male_Suit.obj"),
)
OBJ_PATH = next((p for p in OBJ_CANDIDATES if os.path.isfile(p)), OBJ_CANDIDATES[0])
OUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "characters")
OUT_PATH = os.path.join(OUT_DIR, "player_tactical.glb")

ASSET_NAME = "player_tactical"
OBJ_NAME = "PlayerTactical"

TARGET_HEIGHT_M = 1.80   # metres — human male, matches the repo's metre scale
FEET_FRACTION = lib.FEET_FRACTION
SMOOTH_ANGLE_DEG = lib.SMOOTH_ANGLE_DEG

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


def make_material(key: str):
    spec = PALETTE[key]
    return lib.make_solid_material(
        MATERIAL_NAMES[key], spec["hex"], spec["metallic"], spec["roughness"]
    )


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


def verify_glb(path: str) -> dict:
    """Parse the GLB back and prove it is solid-colour, correct size, no textures."""
    expected = {MATERIAL_NAMES[k]: v["hex"] for k, v in PALETTE.items()}
    stats = lib.verify_character_glb(path, expected, TARGET_HEIGHT_M)

    print("  GLB materials (baseColorFactor -> sRGB):")
    for name, info in stats["materials"].items():
        want = expected.get(name)
        flag = "" if want is None else ("" if want.upper() == info["hex"].upper()
                                        else f"  !! expected #{want}")
        print(f"    {name:14s} #{info['hex']}{flag}")

    missing = [n for n in expected if n not in stats["materials"]]
    if missing:
        print(f"  note: unused palette slots not present in mesh: {missing}")
    if stats["material_count"] < 5:
        raise RuntimeError(f"Expected >= 5 solid materials, got {stats['material_count']}")

    print(f"  verified {os.path.basename(path)}: {stats['bytes'] / 1024:.1f} KB, "
          f"{stats['material_count']} materials, {stats['images']} textures, "
          f"{stats['tris']:,} tris, height {stats['height_m']} m, "
          f"min {stats['min']}")
    return stats


def build(shading: str = "smooth"):
    print(f"Blender {bpy.app.version_string} — player_tactical OBJ -> GLB")
    lib.clear_scene()
    print(f"  source: {os.path.relpath(OBJ_PATH, REPO_ROOT)}")
    imported, importer = lib.import_obj(OBJ_PATH)
    print(f"  importer: {importer}")
    print(f"  imported: {len(imported)} mesh object(s) — "
          f"{sum(len(o.data.polygons) for o in imported):,} faces")
    obj = lib.join_meshes(imported)
    if len(imported) > 1:
        print(f"  joined {len(imported)} parts into one mesh")
    else:
        print("  single mesh — nothing to join")
    lib.normalise_transform(obj, TARGET_HEIGHT_M, OBJ_NAME)
    print(f"  normalised -> {TARGET_HEIGHT_M:.2f} m tall, origin at bottom-centre (0, 0, 0)")
    assign_solid_materials(obj)
    lib.set_shading(obj, shading, SMOOTH_ANGLE_DEG)
    print(f"  shading: {shading}" + (f" by angle ({SMOOTH_ANGLE_DEG:.0f}°)" if shading == "smooth" else ""))

    obj["asset"] = ASSET_NAME
    obj["role"] = "Player character — Battle Royale tactical build"
    obj["source"] = f"{os.path.relpath(OBJ_PATH, REPO_ROOT)} (Quaternius, CC0)"
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
        lib.render_previews(obj, args.preview, TARGET_HEIGHT_M,
                            views={
                                "front": (0.0, -3.2, TARGET_HEIGHT_M * 0.58),
                                "three_quarter": (2.3, -2.3, TARGET_HEIGHT_M * 0.62),
                                "side": (3.2, 0.0, TARGET_HEIGHT_M * 0.58),
                                "back": (0.0, 3.2, TARGET_HEIGHT_M * 0.58),
                            },
                            samples=48, prefix="preview")
    lib.export_glb(obj, OUT_PATH)
    verify_glb(OUT_PATH)
    print(f"  Exported -> {os.path.relpath(OUT_PATH, REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
