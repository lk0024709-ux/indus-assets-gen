"""
outfit_fit_character.py - Battle Royale outfit FITTED to your rigged character
(T-pose, ~65 bones, e.g. Mixamo-style).  Blender 3.2+ / 4.x

HOW IT WORKS
  * Tee / pants / boots are cut out of the character's OWN body mesh (by bone
    vertex-group + height), pushed outward a little and solidified.  Fit is
    exact and skin weights come along, so the outfit is already rigged.
  * Belt, pouches, holster, straps, knee pads, patch, carabiner are measured
    from the body and skinned to the matching bone.

RUN
  1. Open your character in Blender (or set CHAR_PATH to a .glb/.fbx).
  2. Scripting tab -> open this file -> Run Script
     (or: blender -b -P tools/outfit_fit_character.py -- --char model.glb --export outfit.glb)
  3. Everything lands in collection "Outfit_BR_Fit".  Re-running replaces it.
Check the Console / System Console: it prints the body, rig and region counts.
Assumes: character in T-pose, 1 unit = 1 metre, objects not weirdly scaled.
"""
import argparse
import math
import re
import sys

import bmesh
import bpy

# ---------------- SETTINGS ----------------
CHAR_PATH = ""      # optional .glb/.gltf/.fbx. Empty = use what is already in the scene
BODY_NAME = ""      # optional exact name of the body mesh (empty = biggest skinned mesh)
EXPORT_PATH = ""    # optional: outfit + armature as .glb
FLAT_SHADE = True   # faceted look like the reference art
SLEEVE_T = 0.50     # sleeve length on upper arm: 0 = shoulder ... 1 = elbow

if "--" in sys.argv:
    _parser = argparse.ArgumentParser(add_help=False)
    _parser.add_argument("--char", default=CHAR_PATH)
    _parser.add_argument("--body", default=BODY_NAME)
    _parser.add_argument("--export", default=EXPORT_PATH)
    _args, _ = _parser.parse_known_args(sys.argv[sys.argv.index("--") + 1:])
    CHAR_PATH = _args.char
    BODY_NAME = _args.body
    EXPORT_PATH = _args.export

# heights as a fraction of body height (0 = soles, 1 = top of head)
Z_TEE_HEM = 0.53
Z_BELT = 0.575
Z_PANTS_TOP = 0.585
Z_PANTS_BOT = 0.11
Z_BOOT_TOP = 0.16

# (gap from skin, thickness) in metres for a 1.75 m character (auto-scaled)
TEE = (0.010, 0.006)
PANTS = (0.006, 0.008)
BOOTS = (0.003, 0.007)

NAME = "Outfit_BR_Fit"
M_PREFIX = NAME + "_M_"
PALETTE = {                       # LINEAR RGB
    "tee":     (0.16, 0.19, 0.07),
    "pants":   (0.22, 0.17, 0.08),
    "kneepad": (0.09, 0.11, 0.05),
    "black":   (0.02, 0.02, 0.025),
    "boot":    (0.015, 0.015, 0.02),
    "steel":   (0.65, 0.65, 0.68),
    "gold":    (0.8, 0.55, 0.08),
    "brass":   (0.7, 0.45, 0.1),
}

# ---------------- bone name -> body region ----------------
HAND = ("hand", "thumb", "index", "middle", "ring", "pinky", "pinkie", "finger", "palm")
HEAD = ("head", "neck", "jaw", "eye", "tongue", "teeth", "face", "hair")


def norm(name):
    name = re.split(r"[:|]", name)[-1]          # strip "mixamorig:" style prefixes
    return re.sub(r"[^a-z]", "", name.lower())


def region_of(name):
    n = norm(name)
    if any(k in n for k in HEAD):
        return "head"
    if any(k in n for k in HAND):
        return "hand"
    if "forearm" in n or "lowerarm" in n:
        return "forearm"
    if "upperarm" in n or "arm" in n:
        return "upperarm"
    if "shoulder" in n or "clavicle" in n:
        return "clavicle"
    if "upleg" in n or "upperleg" in n or "thigh" in n:
        return "thigh"
    if "toe" in n or "ball" in n:
        return "toe"
    if "foot" in n or "ankle" in n:
        return "foot"
    if "leg" in n or "calf" in n or "shin" in n:
        return "calf"
    if "pelvis" in n or "hips" in n or n == "hip":
        return "pelvis"
    if "spine" in n or "chest" in n or "torso" in n:
        return "spine"
    return "other"


# ---------------- safety / cleanup / import ----------------
_ao = bpy.context.view_layer.objects.active
if _ao and _ao.mode != 'OBJECT':
    bpy.ops.object.mode_set(mode='OBJECT')

for _c in [c for c in bpy.data.collections if c.name == NAME or c.name.startswith(NAME + ".")]:
    for _o in list(_c.objects):
        _me = _o.data if _o.type == 'MESH' else None
        bpy.data.objects.remove(_o, do_unlink=True)
        if _me and _me.users == 0:
            bpy.data.meshes.remove(_me)
    bpy.data.collections.remove(_c)
for _m in [m for m in bpy.data.materials if m.name.startswith(M_PREFIX) and m.users == 0]:
    bpy.data.materials.remove(_m)

if CHAR_PATH:
    _ext = CHAR_PATH.lower().rsplit(".", 1)[-1]
    if _ext in ("glb", "gltf"):
        bpy.ops.import_scene.gltf(filepath=CHAR_PATH)
    elif _ext == "fbx":
        bpy.ops.import_scene.fbx(filepath=CHAR_PATH)
    else:
        raise RuntimeError("CHAR_PATH must be .glb / .gltf / .fbx")

# ---------------- find body + armature ----------------
if BODY_NAME:
    body = bpy.data.objects.get(BODY_NAME)
    if body is None or body.type != 'MESH':
        raise RuntimeError("BODY_NAME '%s' is not a mesh in this file" % BODY_NAME)
else:
    _cands = [o for o in bpy.context.scene.objects if o.type == 'MESH' and len(o.vertex_groups) > 0]
    if not _cands:
        raise RuntimeError("No skinned mesh (with vertex groups) found. Load the character first.")
    body = max(_cands, key=lambda o: len(o.data.vertices))

arm = None
for _m in body.modifiers:
    if _m.type == 'ARMATURE' and _m.object:
        arm = _m.object
if arm is None and body.parent and body.parent.type == 'ARMATURE':
    arm = body.parent
if arm is None:
    _arms = [o for o in bpy.context.scene.objects if o.type == 'ARMATURE']
    arm = _arms[0] if _arms else None
if arm is None:
    raise RuntimeError("No armature found for the body mesh.")

# ---------------- per-vertex data (world space, rest pose) ----------------
mw = body.matrix_world
vgn = [g.name for g in body.vertex_groups]
vgset = set(vgn)
n = len(body.data.vertices)
WV, DOM, REG = [], [], []
for v in body.data.vertices:
    WV.append(mw @ v.co)
    if v.groups:
        g = max(v.groups, key=lambda g: g.weight)
        nm = vgn[g.group]
    else:
        nm = None
    DOM.append(nm)
    REG.append(region_of(nm) if nm else "other")

zmin = min(p.z for p in WV)
zmax = max(p.z for p in WV)
H = zmax - zmin
K = H / 1.75                                # detail-size scale (1.0 for a 1.75 m body)
ls = 1.0 / max(mw.to_scale().x, 1e-6)       # world -> local distance factor


def Z(f):
    return zmin + f * H


def band(zf, tol=0.012, xs=None):
    z0, t = Z(zf), tol * H
    return [p for p in WV if abs(p.z - z0) < t and (xs is None or xs(p.x))]


def ext(pts):
    if not pts:
        raise RuntimeError("No body vertices at that height - is the character in T-pose and upright (Z up)?")
    xs = [p.x for p in pts]
    ys = [p.y for p in pts]
    return min(xs), max(xs), min(ys), max(ys)


wx0, wx1, wy0, wy1 = ext(band(Z_BELT))
cx, cy = (wx0 + wx1) / 2, (wy0 + wy1) / 2

_foot = [WV[i].y for i in range(n) if REG[i] in ("foot", "toe")]
if _foot:
    FRONT = 1 if (max(_foot) - cy) > (cy - min(_foot)) else -1
else:
    FRONT = -1
RIGHT = FRONT                               # sign of X for the character's right side


def leg(sx, zf, tol=0.015):
    pts = band(zf, tol, lambda x: (x - cx) * sx > 0.02 * H)
    x0, x1, y0, y1 = ext(pts)
    return (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2


def front_y(x0, z0, tx=0.03, tz=0.03):
    ys = [p.y for p in WV if abs(p.x - x0) < tx * K and abs(p.z - z0) < tz * K]
    if not ys:
        raise RuntimeError("Could not find chest surface - check FRONT / T-pose.")
    return max(ys) if FRONT > 0 else min(ys)


bones = arm.data.bones
_bw = {}


def bone_world(b):
    if b.name not in _bw:
        _bw[b.name] = (arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local)
    return _bw[b.name]


def pick_bone(region, sx=None):
    c = [b for b in bones if region_of(b.name) == region and b.name in vgset]
    if sx is not None:
        c = [b for b in c if (bone_world(b)[0].x - cx) * sx > 0]
    if not c:
        raise RuntimeError("No '%s' bone found (side %s). Bone names: %s" %
                           (region, sx, ", ".join(b.name for b in bones)))
    return max(c, key=lambda b: bone_world(b)[0].z)


# upper-arm position along the bone (0 shoulder .. 1 elbow) for sleeve cut
TT = [None] * n
for i in range(n):
    if REG[i] == "upperarm":
        b = bones.get(DOM[i])
        if b:
            h, t = bone_world(b)
            d = t - h
            TT[i] = (WV[i] - h).dot(d) / max(d.length_squared, 1e-9)

counts = {}
for r in REG:
    counts[r] = counts.get(r, 0) + 1
print("[outfit] body=%s  armature=%s  H=%.3f m  K=%.3f  FRONT=%+d  verts=%d" %
      (body.name, arm.name, H, K, FRONT, n))
print("[outfit] vertices per region:", counts)

# ---------------- collection + materials ----------------
coll = bpy.data.collections.new(NAME)
bpy.context.scene.collection.children.link(coll)
bpy.context.view_layer.active_layer_collection = \
    bpy.context.view_layer.layer_collection.children[coll.name]

_MATS = {}


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
    metal = key in ("steel", "gold", "brass")
    bsdf.inputs["Roughness"].default_value = 0.3 if metal else 0.9
    bsdf.inputs["Metallic"].default_value = 1.0 if metal else 0.0
    return m


# ---------------- fitted garments (cut from the body) ----------------
def solidify(ob, thickness):
    for m in list(ob.modifiers):
        ob.modifiers.remove(m)
    m = ob.modifiers.new("Solid", 'SOLIDIFY')
    m.thickness = thickness * ls
    m.offset = 1.0
    m.use_even_offset = True
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg),
                                         preserve_all_data_layers=True, depsgraph=dg)
    old = ob.data
    ob.modifiers.remove(m)
    ob.data = me
    bpy.data.meshes.remove(old)
    me.name = ob.name


def make_piece(name, keep, offs, mat_key):
    gap, thick = offs[0] * K, offs[1] * K
    ob = body.copy()
    ob.data = body.data.copy()
    ob.name = name
    ob.data.name = name
    coll.objects.link(ob)
    if ob.data.shape_keys:
        ob.shape_key_clear()
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    kp = [keep(i) for i in range(n)]
    dead = [f for f in bm.faces if not all(kp[v.index] for v in f.verts)]
    bmesh.ops.delete(bm, geom=dead, context='FACES')
    loose = [v for v in bm.verts if not v.link_faces]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context='VERTS')
    if not bm.faces:
        raise RuntimeError("%s came out empty - region/height rules did not match this rig. "
                           "See the region counts printed above." % name)
    bm.normal_update()
    for v in bm.verts:
        v.co += v.normal * (gap * ls)
    bm.to_mesh(ob.data)
    bm.free()
    solidify(ob, thick)
    me = ob.data
    me.materials.clear()
    me.materials.append(mat(mat_key))
    for p in me.polygons:
        p.material_index = 0
        p.use_smooth = not FLAT_SHADE
    am = ob.modifiers.new("Armature", 'ARMATURE')
    am.object = arm
    print("[outfit] %-10s faces=%d" % (name, len(me.polygons)))
    return ob


def keep_tee(i):
    r, z = REG[i], WV[i].z
    if r in ("spine", "clavicle", "pelvis"):
        return z >= Z(Z_TEE_HEM)
    if r == "upperarm":
        return TT[i] is None or TT[i] <= SLEEVE_T
    return False


def keep_pants(i):
    return REG[i] in ("pelvis", "thigh", "calf") and Z(Z_PANTS_BOT) <= WV[i].z <= Z(Z_PANTS_TOP)


def keep_boots(i):
    return REG[i] in ("foot", "toe") or (REG[i] == "calf" and WV[i].z <= Z(Z_BOOT_TOP))


make_piece("Tee", keep_tee, TEE, "tee")
make_piece("Cargo_Pants", keep_pants, PANTS, "pants")
make_piece("Boots", keep_boots, BOOTS, "boot")


# ---------------- detail pieces (skinned to one bone each) ----------------
def part(o, name, key, bone, scale=(1, 1, 1)):
    o.scale = scale
    o.name = name
    o.data.name = name
    o.data.materials.append(mat(key))
    bpy.ops.object.select_all(action='DESELECT')
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    for p in o.data.polygons:
        p.use_smooth = not FLAT_SHADE
    o.parent = arm
    o.matrix_parent_inverse = arm.matrix_world.inverted()
    vg = o.vertex_groups.new(name=bone.name)
    vg.add(list(range(len(o.data.vertices))), 1.0, 'REPLACE')
    am = o.modifiers.new("Armature", 'ARMATURE')
    am.object = arm
    return o


def box(name, key, bone, loc, dim, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    return part(bpy.context.active_object, name, key, bone, dim)


def cyl(name, key, bone, loc, rx, ry, h, v=8, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=v, radius=1, depth=h, location=loc, rotation=rot)
    return part(bpy.context.active_object, name, key, bone, (rx, ry, 1))


pelvis_b = pick_bone("pelvis")
chest_b = pick_bone("spine")

# belt + buckle + pouches + bullets + carabiner
bz = Z(Z_BELT)
bx0, bx1, by0, by1 = ext(band(Z_BELT))
bcx, bcy = (bx0 + bx1) / 2, (by0 + by1) / 2
brx = (bx1 - bx0) / 2 + 0.030 * K
bry = (by1 - by0) / 2 + 0.030 * K
cyl("Belt", "black", pelvis_b, (bcx, bcy, bz), brx, bry, 0.05 * K, v=16)
box("Belt_Buckle", "black", pelvis_b, (bcx, bcy + FRONT * bry, bz), (0.06 * K, 0.02 * K, 0.05 * K))
box("Pouch_R", "black", pelvis_b, (bcx + RIGHT * (brx + 0.01 * K), bcy, bz - 0.02 * K),
    (0.05 * K, 0.10 * K, 0.11 * K))
box("Pouch_L", "black", pelvis_b, (bcx - RIGHT * (brx + 0.01 * K), bcy, bz - 0.02 * K),
    (0.05 * K, 0.09 * K, 0.10 * K))
for i in range(3):
    cyl("Bullet_%d" % i, "brass", pelvis_b,
        (bcx + RIGHT * (brx + 0.01 * K), bcy + (i - 1) * 0.03 * K, bz + 0.05 * K),
        0.008 * K, 0.008 * K, 0.04 * K, v=6)
bpy.ops.mesh.primitive_torus_add(major_radius=0.025 * K, minor_radius=0.005 * K,
                                 major_segments=8, minor_segments=4,
                                 location=(bcx, bcy + FRONT * (bry + 0.004 * K), bz - 0.04 * K),
                                 rotation=(math.radians(90), 0, 0))
part(bpy.context.active_object, "Carabiner", "steel", pelvis_b)

# legs: holster + straps (right), cargo pocket (left), knee pads (both)
OFF = (PANTS[0] + PANTS[1]) * K
for sx in (RIGHT, -RIGHT):
    thigh_b = pick_bone("thigh", sx)
    calf_b = pick_bone("calf", sx)
    lx, ly, lrx, lry = leg(sx, 0.40)
    kx, ky, krx, kry = leg(sx, 0.28)
    side = "R" if sx == RIGHT else "L"
    box("KneePad_" + side, "kneepad", calf_b,
        (kx, ky + FRONT * (kry + OFF + 0.02 * K), Z(0.28)), (0.13 * K, 0.05 * K, 0.15 * K))
    if sx == RIGHT:
        box("Holster", "black", thigh_b,
            (lx + sx * (lrx + OFF + 0.02 * K), ly, Z(0.40)), (0.05 * K, 0.08 * K, 0.20 * K))
        for j, zf in enumerate((0.45, 0.35)):
            sxc, syc, srx, sry = leg(sx, zf)
            cyl("Holster_Strap_%d" % j, "black", thigh_b, (sxc, syc, Z(zf)),
                srx + OFF + 0.008 * K, sry + OFF + 0.008 * K, 0.03 * K)
    else:
        box("Cargo_Pocket", "pants", thigh_b,
            (lx + sx * (lrx + OFF + 0.0225 * K), ly, Z(0.40)), (0.045 * K, 0.12 * K, 0.16 * K))
        box("Cargo_Flap", "pants", thigh_b,
            (lx + sx * (lrx + OFF + 0.0225 * K), ly, Z(0.40) + 0.09 * K), (0.05 * K, 0.125 * K, 0.04 * K))

# chest patch + star (character's left chest)
px = cx - RIGHT * 0.075 * K
pz = Z(0.74)
py = front_y(px, pz) + FRONT * ((TEE[0] + TEE[1]) * K + 0.006 * K)
box("Tee_ChestPatch", "black", chest_b, (px, py, pz), (0.07 * K, 0.012 * K, 0.08 * K))
box("Tee_ChestStar", "gold", chest_b, (px, py + FRONT * 0.006 * K, pz), (0.03 * K, 0.006 * K, 0.03 * K),
    rot=(0, math.radians(45), 0))

# ---------------- optional export (outfit + armature only) ----------------
if EXPORT_PATH:
    if not hasattr(bpy.ops.export_scene, "gltf"):
        print("glTF exporter addon is disabled - enable it in Preferences > Add-ons")
    else:
        bpy.ops.object.select_all(action='DESELECT')
        for o in coll.objects:
            o.select_set(True)
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        try:
            bpy.ops.export_scene.gltf(filepath=EXPORT_PATH, export_format='GLB', use_selection=True)
            print("Exported ->", EXPORT_PATH)
        except Exception as e:
            print("GLB export failed (%s): %r" % (EXPORT_PATH, e))

print("[outfit] Done:", len(coll.objects), "objects in", NAME)
