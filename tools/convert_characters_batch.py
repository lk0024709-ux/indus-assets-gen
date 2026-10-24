#!/usr/bin/env python3
"""Batch character converter — every OBJ in docs/models/Character/ -> solid GLB.

Scans the raw character folder and turns each ``.obj`` into one game-ready,
texture-free character, exactly like ``player_tactical.glb``:

    docs/models/Character/*.obj  ->  docs/models/characters/<name>.glb

For every file it:

1. imports the OBJ (legacy ``bpy.ops.import_scene.obj`` when the running
   Blender still has it, else ``bpy.ops.wm.obj_import``),
2. joins the mesh,
3. throws away the broken ``.mtl`` materials and rebuilds them as **solid
   Principled BSDF materials** keyed off the OBJ's own ``usemtl`` groups,
4. normalises the character to exactly **1.80 m** with a bottom-centre
   ``(0, 0, 0)`` origin, and
5. exports one GLB with **zero image textures**.

Colour rules
------------
| Role | Applied to | Colour |
|---|---|---|
| skin | head, neck, hands (and bare arms/legs) | ``#D2A679`` |
| shirt | torso + arms + dress | **per-character tactical colour** |
| shirt accent | collar/shirt trim, light jacket panels | shirt colour, lightened |
| pants | legs, shorts, socks | ``#1A1A1A`` |
| shoes | shoes (and shoe soles hidden in the ``Eyes`` group) | ``#101112`` |
| hair | hair, hair base, eyebrows | ``#241A18`` |
| eyes / details / tie | eyeballs, belt+glasses, tie | ``#F2F0EA`` / ``#5A616B`` / ``#16202B`` |

The "random tactical" shirt colour is **seeded**, not ``random.random()``: the
palette is shuffled once with a fixed seed, then handed out down the sorted
character list. Every deploy therefore produces byte-identical GLBs, while the
roster still reads as a varied pool. Because the list is sorted, each
``Smooth_*`` high-poly twin lands on a different shirt colour than its
low-poly sibling, so the two never look like the same character.

Outputs
-------
* ``docs/models/characters/<name>.glb`` — one per OBJ
* ``docs/models/characters/characters.json`` — manifest of what shipped
* ``docs/models/characters/gallery.js`` — entries the Pages gallery loads

Run:
    pip install bpy
    python tools/convert_characters_batch.py [--shading flat|smooth]
                                             [--preview DIR] [--only NAME ...]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys

import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import character_lib as lib  # noqa: E402  (needs the path tweak above)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Where the raw OBJs live. docs/models/Character/ is the repo upload; the
# downloaded_obj/ fallback covers a fresh local drop of the same pack.
SOURCE_DIRS = (
    os.path.join(REPO_ROOT, "docs", "models", "Character"),
    os.path.join(REPO_ROOT, "downloaded_obj", "characters"),
)
OUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "characters")
MANIFEST_PATH = os.path.join(OUT_DIR, "characters.json")
GALLERY_JS_PATH = os.path.join(OUT_DIR, "gallery.js")

TARGET_HEIGHT_M = 1.80
SEED = 20261024

# Male_Suit.obj is already shipped as the hand-tuned player_tactical.glb
# (fixed #2C3E50 shirt) — converting it again would duplicate the player.
SKIP_STEMS = {"male_suit"}

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
FIXED_COLORS = {
    "skin":        {"hex": "D2A679", "metallic": 0.00, "roughness": 0.72},
    "pants":       {"hex": "1A1A1A", "metallic": 0.00, "roughness": 0.85},
    "shoes":       {"hex": "101112", "metallic": 0.00, "roughness": 0.60},
    "hair":        {"hex": "241A18", "metallic": 0.00, "roughness": 0.75},
    "eyes":        {"hex": "F2F0EA", "metallic": 0.00, "roughness": 0.35},
    "details":     {"hex": "5A616B", "metallic": 0.35, "roughness": 0.45},
    "tie":         {"hex": "16202B", "metallic": 0.00, "roughness": 0.70},
}

# Unmistakably "tactical": muted, dark, no neon. One is handed to each character.
SHIRT_PALETTE = [
    ("Dark Blue",    "2C3E50"),
    ("Forest Green", "2E4A32"),
    ("Grey",         "4A4F55"),
    ("Brown",        "4A3B2A"),
    ("Navy",         "1F2A44"),
    ("Olive",        "3F4A2E"),
    ("Maroon",       "4A2A2E"),
    ("Slate Blue",   "35455C"),
]

# OBJ group (normalised) -> colour role
GROUP_ROLES = {
    "skin": "skin",
    "shirt": "shirt",
    "shirt2": "shirt_accent",
    "jacket": "shirt",
    "lightjacket": "shirt_accent",
    "dress": "shirt",
    "tanktop": "shirt",
    "pants": "pants",
    "socks": "pants",
    "shorts": "pants",
    "shoes": "shoes",
    "hair": "hair",
    "hairbase": "hair",
    "hair2": "hair_accent",
    "eyebrows": "hair",
    "eyes": "eyes",
    "details": "details",
    "tietexture": "tie",
}

ROLE_MATERIAL_NAMES = {
    "skin": "Skin",
    "shirt": "TacticalShirt",
    "shirt_accent": "ShirtAccent",
    "pants": "Pants",
    "shoes": "Shoes",
    "hair": "Hair",
    "hair_accent": "HairAccent",
    "eyes": "Eyes",
    "details": "Details",
    "tie": "Tie",
}


# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------
def normalise_group_name(name: str) -> str:
    base = name.split(".")[0].strip().lower()
    return "".join(ch for ch in base if ch.isalnum())


def display_name(stem: str) -> str:
    parts = stem.split("_")
    high_poly = parts[0] == "smooth"
    if high_poly:
        parts = parts[1:]
    title = " ".join(p.capitalize() for p in parts)
    title = title.replace("Tanktop", "Tank Top").replace("Longsleeve", "Long Sleeve")
    return f"{title} (High-poly)" if high_poly else title


def find_source_objs() -> list[str]:
    seen, found = set(), []
    for directory in SOURCE_DIRS:
        if not os.path.isdir(directory):
            continue
        for name in sorted(os.listdir(directory)):
            if not name.lower().endswith(".obj"):
                continue
            stem = os.path.splitext(name)[0].lower()
            if stem in seen:
                continue
            seen.add(stem)
            found.append(os.path.join(directory, name))
    return sorted(found, key=lambda p: os.path.basename(p).lower())


# ---------------------------------------------------------------------------
# Colour assignment
# ---------------------------------------------------------------------------
def resolve_colors(shirt_name: str, shirt_hex: str) -> dict:
    """Role -> {hex, metallic, roughness} for one character."""
    colors = {role: dict(spec) for role, spec in FIXED_COLORS.items()}
    colors["shirt"] = {"hex": shirt_hex, "metallic": 0.0, "roughness": 0.80}
    colors["shirt_accent"] = {
        "hex": lib.lighten_hex(shirt_hex, 0.18), "metallic": 0.0, "roughness": 0.80,
    }
    colors["hair_accent"] = {
        "hex": lib.lighten_hex(FIXED_COLORS["hair"]["hex"], 0.18),
        "metallic": 0.0, "roughness": 0.75,
    }
    colors["_shirt_name"] = shirt_name
    return colors


def assign_materials(obj, colors: dict):
    """Rebuild every material slot as a solid colour, keyed off the OBJ groups."""
    me = obj.data
    if not me.materials:
        raise RuntimeError("Imported mesh has no material groups to key colours from")

    slot_roles = []
    for slot in me.materials:
        role = GROUP_ROLES.get(normalise_group_name(slot.name))
        if role is None:
            print(f"    ! unknown OBJ group '{slot.name}' -> neutral grey")
        slot_roles.append(role)

    zs = [v.co.z for v in me.vertices]
    feet_z = min(zs) + (max(zs) - min(zs)) * lib.FEET_FRACTION

    # Decide a role per polygon *before* the slot list is rebuilt.
    poly_roles = []
    unknown = 0
    for poly in me.polygons:
        role = slot_roles[poly.material_index] if poly.material_index < len(slot_roles) else None
        if role is None:
            role = "details"
            unknown += 1
        # Several of these OBJs hide the shoe soles inside the "Eyes" group.
        if role == "eyes" and poly.center.z < feet_z:
            role = "shoes"
        poly_roles.append(role)

    order = []
    for role in poly_roles:
        if role not in order:
            order.append(role)

    # Drop the imported MTL materials so our clean names are not pushed to
    # "Skin.001" — Godot shows these names in the inspector.
    stale = list(me.materials)
    me.materials.clear()
    for mat in stale:
        if mat is not None and mat.users == 0 and mat.name in bpy.data.materials:
            bpy.data.materials.remove(mat)

    for role in order:
        spec = colors[role]
        me.materials.append(lib.make_solid_material(
            ROLE_MATERIAL_NAMES[role], spec["hex"], spec["metallic"], spec["roughness"]
        ))
    index_of = {role: i for i, role in enumerate(order)}
    for poly, role in zip(me.polygons, poly_roles):
        poly.material_index = index_of[role]
    me.update()

    if unknown:
        print(f"    ! {unknown} face(s) had no usable group -> neutral grey")

    counts = {}
    for role in poly_roles:
        counts[role] = counts.get(role, 0) + 1
    expected = {ROLE_MATERIAL_NAMES[r]: colors[r]["hex"] for r in order}
    return expected, counts


# ---------------------------------------------------------------------------
# One character
# ---------------------------------------------------------------------------
def convert_one(obj_path: str, shirt_name: str, shirt_hex: str,
                shading: str) -> dict:
    stem = os.path.splitext(os.path.basename(obj_path))[0]
    out_name = stem.lower().replace(" ", "_")
    out_path = os.path.join(OUT_DIR, out_name + ".glb")
    colors = resolve_colors(shirt_name, shirt_hex)

    lib.clear_scene()
    imported, importer = lib.import_obj(obj_path)
    obj = lib.join_meshes(imported)
    lib.normalise_transform(obj, TARGET_HEIGHT_M, "".join(p.capitalize() for p in out_name.split("_")))
    expected, counts = assign_materials(obj, colors)
    lib.set_shading(obj, shading, lib.SMOOTH_ANGLE_DEG)

    obj["asset"] = out_name
    obj["role"] = "Character pool — Battle Royale"
    obj["source"] = f"{os.path.relpath(obj_path, REPO_ROOT)} (Quaternius, CC0)"
    obj["height_m"] = TARGET_HEIGHT_M
    obj["origin"] = "bottom-centre (0,0,0)"
    obj["textures"] = "none — solid Principled BSDF colours only"
    obj["shirt_color"] = f"{shirt_name} #{shirt_hex}"
    obj["shading"] = shading

    lib.export_glb(obj, out_path)
    stats = lib.verify_character_glb(out_path, expected, TARGET_HEIGHT_M)

    palette = ", ".join(f"{ROLE_MATERIAL_NAMES[r]}=#{colors[r]['hex']}"
                        for r in sorted(counts))
    return {
        "file": f"models/characters/{out_name}.glb",
        "name": display_name(out_name),
        "source": os.path.relpath(obj_path, REPO_ROOT),
        "shirt_color": shirt_name,
        "shirt_hex": shirt_hex,
        "accent_hex": colors["shirt_accent"]["hex"],
        "tris": stats["tris"],
        "bytes": stats["bytes"],
        "height_m": stats["height_m"],
        "materials": stats["material_count"],
        "counts": counts,
        "palette": palette,
        "has_dress": "shirt" in counts and "pants" not in counts,
        "high_poly": out_name.startswith("smooth_"),
        "importer": importer,
    }


def stable_shirt_assignments(stems: list[str]) -> dict:
    """Deterministic 'random tactical colour' per character.

    The palette is shuffled once with a fixed seed, then dealt down the sorted
    list. Re-running (or re-deploying) can never change a shipped colour, and
    each ``smooth_*`` twin differs from its low-poly sibling because the two
    are exactly ``len(SHIRT_PALETTE) - 1`` slots apart.
    """
    order = list(SHIRT_PALETTE)
    random.Random(SEED).shuffle(order)
    return {stem: order[i % len(order)] for i, stem in enumerate(sorted(stems))}


# ---------------------------------------------------------------------------
# Gallery output
# ---------------------------------------------------------------------------
def gallery_entry(meta: dict) -> dict:
    """Turn a manifest row into a gallery card, describing only what shipped."""
    high = meta["high_poly"]
    body = meta["name"].replace(" (High-poly)", "")
    dress = meta.get("has_dress")
    counts = meta["counts"]

    role_hex = {
        "skin": FIXED_COLORS["skin"]["hex"],
        "shirt": meta["shirt_hex"],
        "shirt_accent": meta["accent_hex"],
        "pants": FIXED_COLORS["pants"]["hex"],
        "shoes": FIXED_COLORS["shoes"]["hex"],
        "hair": FIXED_COLORS["hair"]["hex"],
        "hair_accent": lib.lighten_hex(FIXED_COLORS["hair"]["hex"], 0.18),
        "eyes": FIXED_COLORS["eyes"]["hex"],
        "details": FIXED_COLORS["details"]["hex"],
        "tie": FIXED_COLORS["tie"]["hex"],
    }
    role_label = {
        "skin": "skin", "shirt": "shirt", "shirt_accent": "trim",
        "pants": "pants", "shoes": "shoes", "hair": "hair",
        "hair_accent": "hair highlight", "eyes": "eyes",
        "details": "details", "tie": "tie",
    }
    if dress:
        role_label["shirt"] = "dress"
        role_label["shirt_accent"] = "dress trim"
    order = ["skin", "shirt", "shirt_accent", "pants", "shoes", "hair",
             "hair_accent", "eyes", "details", "tie"]
    present = [r for r in order if counts.get(r)]
    # Only describe materials that really exist on this mesh.
    parts = ", ".join(f"{role_label[r]} #{role_hex[r]}" for r in present)
    garment = "dress" if dress else "shirt"
    chip_materials = " / ".join(
        f"{ROLE_MATERIAL_NAMES[r]} #{role_hex[r]}" for r in present
    )

    desc = (
        f"{body} converted from {meta['source']} with tools/convert_characters_batch.py. "
        f"The OBJ's own material groups are remapped to solid colours \u2014 {parts} \u2014 "
        f"so the character ships as one joined, smooth-shaded mesh at exactly 1.80 m with a "
        f"bottom-centre (0,0,0) origin and no image textures at all, which is what stops Godot "
        f"falling back to an untextured mesh."
    )
    if dress:
        desc += (" The dress covers the torso and thighs, with bare arms and lower legs left in "
                 "the skin tone.")
    else:
        desc += f" The {meta['shirt_color'].lower()} tactical {garment} is the only per-character colour."
    if high:
        desc += (" This is the high-poly 'Smooth' variant of the same body, so it keeps a rounder "
                 "silhouette at a higher triangle count.")

    return {
        "id": os.path.splitext(os.path.basename(meta["file"]))[0],
        "file": meta["file"],
        "name": f"\U0001F9D1 {meta['name']} \u00B7 {meta['shirt_color']}",
        "alt": (f"Low-poly character: skin-toned head and hands, {meta['shirt_color'].lower()} "
                f"tactical {garment}, dark shoes and hair"),
        "desc": desc,
        "dims": "1.80 m tall",
        "material": (f"{chip_materials} \u00B7 {meta['tris']:,} tris "
                     f"\u00B7 {meta['materials']} mats \u00B7 0 textures"),
        "orbit": "-22deg 78deg 165%",
        "fov": "30deg",
        "exposure": "1.1",
        "bg": "radial-gradient(circle at 50% 34%, #3a4a5c 0%, #1b2430 62%, #0b1017 100%)",
        "chip": ".glb \u00B7 solid-colour PBR \u00B7 0 textures \u00B7 origin (0,0,0)",
    }


def write_gallery_js(entries: list[dict]) -> None:
    lines = [
        "// AUTO-GENERATED by tools/convert_characters_batch.py — do not edit by hand.",
        "// Regenerated on every deploy so the gallery can never drift from the GLBs.",
        "window.CHARACTER_ENTRIES = [",
    ]
    for entry in entries:
        lines.append("  {")
        for key, value in entry.items():
            lines.append(f"    {key}: {json.dumps(value, ensure_ascii=False)},")
        lines.append("  },")
    lines.append("];")
    lines.append("")
    with open(GALLERY_JS_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--shading", choices=("flat", "smooth"), default="smooth")
    parser.add_argument("--preview", metavar="DIR", default=None,
                        help="render a front + 3/4 QA PNG per character into DIR")
    parser.add_argument("--only", nargs="+", metavar="NAME", default=None,
                        help="convert only these stems (e.g. female_dress)")
    args = parser.parse_args(argv)

    print(f"Blender {bpy.app.version_string} — batch character conversion")
    sources = find_source_objs()
    if not sources:
        raise SystemExit(f"No .obj files found in {SOURCE_DIRS}")

    roster = []
    for path in sources:
        stem = os.path.splitext(os.path.basename(path))[0].lower()
        if stem in SKIP_STEMS:
            print(f"  skip {stem}: shipped as player_tactical.glb")
            continue
        roster.append((stem, path))
    selected = [(s, p) for s, p in roster if not args.only or s in args.only]
    if not selected:
        raise SystemExit("Nothing selected to convert")

    # Colours are dealt across the WHOLE roster, so a single-character run
    # (--only) reproduces exactly the colour that character gets in a full run.
    assignments = stable_shirt_assignments([stem for stem, _ in roster])
    print(f"  {len(selected)} character(s) -> {os.path.relpath(OUT_DIR, REPO_ROOT)}\n")

    metas, failures = [], []
    for stem, path in selected:
        shirt_name, shirt_hex = assignments[stem]
        print(f"  [{stem}] {shirt_name} #{shirt_hex}")
        try:
            meta = convert_one(path, shirt_name, shirt_hex, args.shading)
        except Exception as exc:  # keep going so one bad file cannot block the roster
            print(f"    FAILED: {exc}\n")
            failures.append((stem, str(exc)))
            continue
        print(f"    {meta['materials']} materials · {meta['tris']:,} tris · "
              f"{meta['bytes'] / 1024:.1f} KB · 1.80 m · 0 textures")
        if args.preview:
            obj = bpy.data.objects[0]
            lib.render_previews(obj, os.path.join(args.preview, stem), TARGET_HEIGHT_M,
                                views={"three_quarter": (2.3, -2.3, TARGET_HEIGHT_M * 0.62)},
                                samples=24, prefix=stem)
        metas.append(meta)
        print()

    if not metas:
        raise SystemExit("Every character failed")

    # Sibling check: a Smooth_* twin must never share its low-poly shirt colour.
    by_stem = {os.path.splitext(os.path.basename(m["file"]))[0]: m for m in metas}
    for stem, meta in by_stem.items():
        twin = stem[len("smooth_"):] if stem.startswith("smooth_") else f"smooth_{stem}"
        other = by_stem.get(twin)
        if other and other["shirt_hex"] == meta["shirt_hex"]:
            raise SystemExit(f"{stem} and {twin} share shirt #{meta['shirt_hex']}")

    metas.sort(key=lambda m: m["file"])
    with open(MANIFEST_PATH, "w", encoding="utf-8") as fh:
        json.dump({
            "generated_by": "tools/convert_characters_batch.py",
            "blender": bpy.app.version_string,
            "height_m": TARGET_HEIGHT_M,
            "shirt_palette": [{"name": n, "hex": h} for n, h in SHIRT_PALETTE],
            "characters": metas,
        }, fh, indent=2)
        fh.write("\n")
    write_gallery_js([gallery_entry(m) for m in metas])

    total_kb = sum(m["bytes"] for m in metas) / 1024
    print(f"  {len(metas)} GLB(s), {total_kb:.0f} KB total, "
          f"{sum(m['tris'] for m in metas):,} tris")
    print(f"  manifest -> {os.path.relpath(MANIFEST_PATH, REPO_ROOT)}")
    print(f"  gallery  -> {os.path.relpath(GALLERY_JS_PATH, REPO_ROOT)}")
    if failures:
        for stem, err in failures:
            print(f"  FAILED {stem}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
