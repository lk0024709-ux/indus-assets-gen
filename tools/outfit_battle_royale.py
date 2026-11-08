"""
Outfit 6 - Battle Royale tee + cargo pants (OUTFIT ONLY, no body)
Blender 3.x / 4.x.
Run: Scripting tab -> Run Script   OR   blender -b -P tools/outfit_battle_royale.py -- --export outfit_br.glb
Units: metres, character height ~1.75 m, Z up, front faces -Y.
PALETTE values are LINEAR RGB (not sRGB hex). Rotations/scales are baked into the meshes.
Har piece alag object hai, sab "Outfit_BR" empty ke child (easy outfit swap).
"""
import argparse
import math
import sys

import bpy

EXPORT_PATH = ""   # e.g. "/sdcard/outfit_br.glb" ; khali chhodo to export nahi hoga
NAME = "Outfit_BR"
M_PREFIX = NAME + "_M_"

if "--" in sys.argv:
    _parser = argparse.ArgumentParser(add_help=False)
    _parser.add_argument("--export", default=EXPORT_PATH)
    _args, _ = _parser.parse_known_args(sys.argv[sys.argv.index("--") + 1:])
    EXPORT_PATH = _args.export

PALETTE = {
    "tee":     (0.16, 0.19, 0.07),
    "pants":   (0.22, 0.17, 0.08),
    "kneepad": (0.09, 0.11, 0.05),
    "black":   (0.02, 0.02, 0.025),
    "boot":    (0.015, 0.015, 0.02),
    "steel":   (0.65, 0.65, 0.68),
    "gold":    (0.8, 0.55, 0.08),
    "brass":   (0.7, 0.45, 0.1),
}

# ---------- safety: Object Mode + re-run cleanup ----------
_ao = bpy.context.view_layer.objects.active
if _ao and _ao.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')

for _old in [c for c in bpy.data.collections
             if c.name == NAME or c.name.startswith(NAME + ".")]:
    for _o in list(_old.objects):
        _me = _o.data if _o.type == 'MESH' else None
        bpy.data.objects.remove(_o, do_unlink=True)
        if _me and _me.users == 0:
            bpy.data.meshes.remove(_me)
    bpy.data.collections.remove(_old)

for _m in [m for m in bpy.data.materials if m.name.startswith(M_PREFIX) and m.users == 0]:
    bpy.data.materials.remove(_m)

# ---------- scene setup ----------
coll = bpy.data.collections.new(NAME)
bpy.context.scene.collection.children.link(coll)
bpy.context.view_layer.active_layer_collection = \
    bpy.context.view_layer.layer_collection.children[coll.name]

_stray = bpy.data.objects.get(NAME)
if _stray and _stray.type == 'EMPTY':
    bpy.data.objects.remove(_stray, do_unlink=True)
bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
ROOT = bpy.context.active_object
ROOT.name = NAME


_MATS = {}   # materials are created fresh every run, so PALETTE edits always apply


def mat(key):
    if key in _MATS:
        return _MATS[key]
    m = bpy.data.materials.new(M_PREFIX + key)
    _MATS[key] = m
    m.use_nodes = True
    r, g, b = PALETTE[key]
    m.diffuse_color = (r, g, b, 1)
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = m.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1)
    bsdf.inputs["Roughness"].default_value = 0.3 if key in ("steel", "gold", "brass") else 0.9
    bsdf.inputs["Metallic"].default_value = 1.0 if key in ("steel", "gold", "brass") else 0.0
    return m


def finish(o, name, key, scale=(1, 1, 1)):
    o.scale = scale
    o.name = name
    o.data.name = name
    o.data.materials.append(mat(key))
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    for p in o.data.polygons:      # flat shading = faceted low-poly look
        p.use_smooth = False
    o.parent = ROOT
    return o


def cyl(name, key, loc, r, h, sc=(1, 1, 1), rot=(0, 0, 0), v=8, r2=None):
    if r2 is None:
        bpy.ops.mesh.primitive_cylinder_add(vertices=v, radius=r, depth=h, location=loc, rotation=rot)
    else:
        bpy.ops.mesh.primitive_cone_add(vertices=v, radius1=r, radius2=r2, depth=h, location=loc, rotation=rot)
    return finish(bpy.context.active_object, name, key, sc)


def box(name, key, loc, dim, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    return finish(bpy.context.active_object, name, key, dim)


# ---------- T-SHIRT ----------
cyl("Tee_Body", "tee", (0, 0, 1.275), 0.18, 0.51, sc=(1.1, 0.7, 1))
cyl("Tee_Collar", "tee", (0, 0, 1.53), 0.085, 0.035, sc=(1, 0.9, 1))
for s, side in ((1, "R"), (-1, "L")):
    cyl(f"Tee_Sleeve_{side}", "tee", (s * 0.285, 0, 1.429), 0.075, 0.2,
        rot=(0, s * math.radians(110), 0))
box("Tee_ChestPatch", "black", (0.075, -0.118, 1.38), (0.07, 0.012, 0.08))
box("Tee_ChestStar", "gold", (0.075, -0.125, 1.38), (0.03, 0.006, 0.03),
    rot=(0, math.radians(45), 0))

# ---------- CARGO PANTS ----------
cyl("Pants_Hips", "pants", (0, 0, 0.97), 0.21, 0.2, sc=(1, 0.65, 1))
for s, side in ((1, "R"), (-1, "L")):
    cyl(f"Pants_Leg_{side}", "pants", (s * 0.1, 0, 0.65), 0.10, 0.74, r2=0.105)
    box(f"KneePad_{side}", "kneepad", (s * 0.1, -0.1, 0.52), (0.13, 0.05, 0.15))

# cargo pocket (right side, +X) + flap
box("Cargo_Pocket", "pants", (0.215, -0.01, 0.74), (0.045, 0.12, 0.16))
box("Cargo_Flap", "pants", (0.22, -0.01, 0.82), (0.05, 0.125, 0.04))

# thigh holster (left side of image, -X) + 2 straps
box("Holster", "black", (-0.215, 0, 0.78), (0.05, 0.08, 0.2))
for i, z in enumerate((0.88, 0.72)):
    cyl(f"Holster_Strap_{i}", "black", (-0.1, 0, z), 0.108, 0.03)

# ---------- BELT + POUCHES ----------
cyl("Belt", "black", (0, 0, 1.04), 0.225, 0.07, sc=(1, 0.7, 1), v=12)
box("Belt_Buckle", "black", (0, -0.16, 1.04), (0.06, 0.02, 0.05))
box("Pouch_R", "black", (0.25, -0.01, 1.0), (0.05, 0.1, 0.11))
box("Pouch_L", "black", (-0.25, -0.01, 1.0), (0.05, 0.09, 0.1))
for i in range(3):                                  # bullets on right pouch
    cyl(f"Bullet_{i}", "brass", (0.25, -0.04 + i * 0.03, 1.07), 0.008, 0.04, v=6)

bpy.ops.mesh.primitive_torus_add(major_radius=0.025, minor_radius=0.005,
                                 major_segments=8, minor_segments=4,
                                 location=(0, -0.15, 0.975), rotation=(math.radians(90), 0, 0))
finish(bpy.context.active_object, "Carabiner", "steel")

# ---------- BOOTS ----------
for s, side in ((1, "R"), (-1, "L")):
    cyl(f"Boot_Shaft_{side}", "boot", (s * 0.1, 0, 0.16), 0.086, 0.28, r2=0.096)
    box(f"Boot_Foot_{side}", "boot", (s * 0.1, -0.065, 0.06), (0.178, 0.26, 0.06))
    box(f"Boot_Sole_{side}", "black", (s * 0.1, -0.065, 0.015), (0.188, 0.28, 0.03))

# ---------- EXPORT (optional, Godot/Unity ke liye .glb) ----------
if EXPORT_PATH:
    bpy.ops.object.select_all(action='DESELECT')
    ROOT.select_set(True)
    for o in ROOT.children:
        o.select_set(True)
    bpy.context.view_layer.objects.active = ROOT
    if not hasattr(bpy.ops.export_scene, "gltf"):
        print("glTF exporter addon is disabled - enable it in Preferences > Add-ons")
    else:
        try:
            bpy.ops.export_scene.gltf(filepath=EXPORT_PATH, export_format='GLB',
                                      use_selection=True, export_apply=True)
            print("Exported ->", EXPORT_PATH)
        except Exception as e:
            print("GLB export failed (%s): %r" % (EXPORT_PATH, e))

print("Done:", len(ROOT.children), "pieces")
