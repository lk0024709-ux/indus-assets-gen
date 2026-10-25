#!/usr/bin/env python3
"""Retarget the Mixamo motion library onto the 27-bone Indus player rig (bpy only).

    characters/base_mesh/<any .glb/.gltf/.fbx/.blend/.obj>   (AI-generated base body)
        |  fallback: docs/models/characters/body_base_female_midpoly.glb
        |
        |  + docs/Motions/*.fbx   (Mixamo, 65-bone `mixamorig:` skeleton, cm scale)
        v
    characters/player_animated.glb          skinned body + 27-bone rig + N clips
    characters/clothing/clothing_*.glb       garments on the *same* 27 bones + clips
    characters/player_animated.report.json   machine-readable validation report

Everything is stock ``bpy`` (Blender 4.5 LTS as a Python module): no add-ons, no
Rokoko/Auto-Rig-Pro, no external retargeting services.

Why this file is shaped the way it is
=====================================

**Retargeting is done with rest-relative *world* deltas, not local copy-rotation.**
Mixamo's rig has 65 bones, three spine joints and its own per-bone roll; ours has
27 bones, two spine joints and the repo's ``align_roll((0,-1,0))`` convention. A
naive ``COPY_ROTATION`` therefore produces a character that is bent sideways in
rest. For every mapped pair the script instead computes

    delta  = R_src_pose_world @ R_src_rest_world^-1          # what the source *did*
    R_want = delta @ R_tgt_rest_world                         # applied to our rest

and then converts ``R_want`` into the target bone's local basis. Because the
delta is absolute (world) rather than parent-relative, a 3-joint source spine
collapses onto a 2-joint target spine with the chest ending up in exactly the
right orientation -- the parent's share is divided out by the basis conversion.
``tools/test_player_animated.py`` pins the underlying pose identity
(``pose = parent_pose @ parent_rest^-1 @ rest @ basis``) that this relies on; it
reproduces Blender's own evaluation to 4.5e-06.

**Foot float is fixed in three stages, because it has three causes.**

1. *Proportions.* Mixamo's skeleton is 1.82 m with its own leg length; ours is
   1.80 m with different femur/tibia ratios. Copying the hip height verbatim
   sinks or floats every clip. Vertical hip travel is therefore rescaled by the
   measured ``target_leg_length / source_leg_length`` ratio and horizontal travel
   by the height ratio.
2. *Clip datum.* Each clip is then given one constant Z offset so the lowest
   point the *skinned mesh* ever reaches during that clip is exactly z = 0. A
   constant offset cannot introduce sliding or popping, and it is what makes
   Prone Idle lie on the floor and Dive Roll touch it at the bottom of the roll.
3. *Per-foot residual.* Contacts are detected on the **source** animation (toe
   near its own floor + low horizontal speed), and for those frames an analytic
   two-bone IK solve pulls the target ankle down onto the ground by whatever
   residual the first two stages left. Corrections are smoothed with a 5-frame
   box filter and ramped in/out across contact boundaries so no frame pops.

**Quaternion flips** are removed by hemisphere-matching every bone's key
sequence (negate ``q`` whenever ``dot(q_prev, q) < 0``) and, for looping clips,
matching the last key back to the first. The report asserts the minimum
consecutive dot product over every curve is >= 0.

**Mesh stretching in extreme poses** is attacked on the weights, then measured.
Weights are pruned of implausible long-range influences (a knee bone touching
the chest is what tears Dive Roll apart), Laplacian-smoothed over the mesh
graph, limited to 4 influences and renormalised. The result is then *verified*
by skinning the mesh on the worst frames of Dive Roll / Prone Idle / Dying with
linear blend skinning in numpy and measuring per-edge length ratios. If the
worst edge exceeds the limit the smoothing is repeated (adaptively, up to
``--max-weight-rounds`` times) rather than silently shipped.

**Clothing** is cut out of the body itself and offset *away from the nearest bone
axis* by 5 % of the local limb radius. That is what "scaled 1.05x" means in the
only frame where it is well defined: a literal ``object.scale = 1.05`` is a scale
about the world origin, so it moves a shoulder four times as far as a wrist and
leaves the chest inside the shirt (``--clothing-mode scale`` reproduces it for
comparison). Every garment vertex keeps the vertex groups of the body vertex it
was cut from, so garment and body deform bit-identically -- that is the
"deform perfectly" requirement, and it is asserted, not hoped for.

Run
---
    pip install bpy==4.5.3
    python tools/retarget_animations.py                 # full curated clip set
    python tools/retarget_animations.py --quick         # 4 clips, for iteration
    python tools/retarget_animations.py --clips Run DiveRoll ProneIdle
    python tools/retarget_animations.py --no-mirror     # skip the docs/ copy
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

import bpy  # noqa: E402
import bmesh  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Quaternion, Vector  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
MOTION_DIR = REPO / "docs" / "Motions"
BASE_MESH_DIR = REPO / "characters" / "base_mesh"
FALLBACK_BASE = REPO / "docs" / "models" / "characters" / "body_base_female_midpoly.glb"
OUT_DIR = REPO / "characters"
OUT_CLOTHING = OUT_DIR / "clothing"
MIRROR_DIR = REPO / "docs" / "models" / "characters"

PLAYER_GLB = "player_animated.glb"
REPORT_JSON = "player_animated.report.json"

RIG_NAME = "Player_Rig"
BODY_NAME = "Player_Body"
TARGET_HEIGHT = 1.80
FPS = 30
MAX_INFLUENCES = 4
WEIGHT_EPS = 1e-4

# Deformation limits enforced on the extreme frames (Dive Roll / Prone / Dying).
# See measure_deformation() for why ratios are read off edges >= MIN_REST_EDGE
# and why squash is only a degeneracy guard.
MIN_REST_EDGE = 0.002          # m; below this a ratio is not a visible defect
# The body shell is the surface we skin and the surface the garments are cut
# from; it is held to a tight limit and measures 1.285x / 5.4 mm against it.
BODY_STRETCH_LIMIT = 1.75      # max posed/rest edge-length ratio
BODY_GROWTH_LIMIT = 0.030      # m; absolute tear guard
EDGE_SQUASH_LIMIT = 0.02       # min ratio -- collapse/inversion guard only
# Accessory shells (the base character's own sportswear, hair, eyes) arrive
# pre-weighted from whoever authored the base mesh and are separate mesh
# islands, so nothing done here can smooth across into them. Advisory limit:
# it fails the build if a *new* base mesh is much worse than the current one.
ACCESSORY_STRETCH_LIMIT = 4.5
ACCESSORY_GROWTH_LIMIT = 0.040

# Ground contract.
FLOOR_TOL_BELOW = 0.010        # m a vertex may dip under the floor
FLOOR_TOL_ABOVE = 0.012        # m the lowest point of a clip may hover
CONTACT_FLOAT_LIMIT = 0.020    # m a *planted* foot may hover
IK_PASSES = 4                  # measure -> correct -> re-measure iterations
IK_SMOOTH = (5, 3, 1, 1)       # box-filter width per pass; later passes mop up
ROOT_DROP_ROUNDS = 2           # re-seat the root when a planted leg runs out of reach
UPRIGHT_LEG_FRACTION = 0.62    # hip must clear the toe by this much of a leg

# ---------------------------------------------------------------------------
# The canonical 27-bone rig. Identical names, parents and proportions to
# tools/generate_body_female_midpoly.py, which is what already ships in
# docs/models/characters/body_base_female_midpoly.glb. Coordinates are quoted at
# the repo's 1.80 m reference height and rescaled if a taller/shorter base mesh
# is supplied.
# ---------------------------------------------------------------------------
def rig_spec(height: float = TARGET_HEIGHT):
    k = height / TARGET_HEIGHT
    out: list[tuple[str, str | None, tuple, tuple]] = []

    def add(name, head, tail, parent=None):
        out.append((name, parent, tuple(c * k for c in head), tuple(c * k for c in tail)))

    add("HIPS", (0, 0, .91), (0, 0, 1.04))
    add("SPINE_NAVAL", (0, 0, 1.04), (0, 0, 1.23), "HIPS")
    add("SPINE_CHEST", (0, 0, 1.23), (0, 0, 1.45), "SPINE_NAVAL")
    add("NECK", (0, 0, 1.45), (0, 0, 1.56), "SPINE_CHEST")
    add("HEAD", (0, 0, 1.56), (0, 0, 1.79), "NECK")
    for s, side in ((1, "L"), (-1, "R")):
        def p(x, y, z):
            return (s * x, y, z)
        add(f"CLAVICLE_{side}", p(.04, 0, 1.40), p(.205, 0, 1.40), "SPINE_CHEST")
        add(f"SHOULDER_{side}", p(.205, 0, 1.40), p(.46, 0, 1.40), f"CLAVICLE_{side}")
        add(f"ELBOW_{side}", p(.46, 0, 1.40), p(.70, 0, 1.40), f"SHOULDER_{side}")
        add(f"WRIST_{side}", p(.70, 0, 1.40), p(.77, 0, 1.40), f"ELBOW_{side}")
        add(f"HAND_{side}", p(.77, 0, 1.40), p(.84, 0, 1.40), f"WRIST_{side}")
        add(f"HANDTIP_{side}", p(.84, 0, 1.40), p(.875, 0, 1.40), f"HAND_{side}")
        add(f"THUMB_{side}", p(.785, -.025, 1.40), p(.825, -.085, 1.40), f"HAND_{side}")
        add(f"HIP_{side}", p(.115, 0, .90), p(.12, -.025, .525), "HIPS")
        add(f"KNEE_{side}", p(.12, -.025, .525), p(.12, 0, .14), f"HIP_{side}")
        add(f"ANKLE_{side}", p(.12, 0, .14), p(.12, -.045, .07), f"KNEE_{side}")
        add(f"FOOT_{side}", p(.12, -.045, .07), p(.12, -.235, .065), f"ANKLE_{side}")
    return out


RIG_BONES = [b[0] for b in rig_spec()]
RIG_PARENTS = {b[0]: b[1] for b in rig_spec()}
ROOT_BONE = "HIPS"

# ---------------------------------------------------------------------------
# Mixamo -> 27-bone map. Each entry pairs bones that drive the *same anatomical
# segment*: our ELBOW_L is the forearm (elbow -> wrist), which is Mixamo's
# LeftForeArm, not LeftHand. Mixamo's Spine1 has no counterpart and needs none:
# world-delta retargeting folds it into SPINE_CHEST automatically.
# ---------------------------------------------------------------------------
BONE_MAP = {
    "HIPS": "mixamorig:Hips",
    "SPINE_NAVAL": "mixamorig:Spine",
    "SPINE_CHEST": "mixamorig:Spine2",
    "NECK": "mixamorig:Neck",
    "HEAD": "mixamorig:Head",
}
for _side, _M in (("L", "Left"), ("R", "Right")):
    BONE_MAP.update({
        f"CLAVICLE_{_side}": f"mixamorig:{_M}Shoulder",
        f"SHOULDER_{_side}": f"mixamorig:{_M}Arm",
        f"ELBOW_{_side}": f"mixamorig:{_M}ForeArm",
        f"WRIST_{_side}": f"mixamorig:{_M}Hand",
        f"HAND_{_side}": f"mixamorig:{_M}HandMiddle1",
        f"HANDTIP_{_side}": f"mixamorig:{_M}HandMiddle3",
        f"THUMB_{_side}": f"mixamorig:{_M}HandThumb1",
        f"HIP_{_side}": f"mixamorig:{_M}UpLeg",
        f"KNEE_{_side}": f"mixamorig:{_M}Leg",
        f"ANKLE_{_side}": f"mixamorig:{_M}Foot",
        f"FOOT_{_side}": f"mixamorig:{_M}ToeBase",
    })

SRC_HIPS = "mixamorig:Hips"
SRC_LEG = {"L": ("mixamorig:LeftUpLeg", "mixamorig:LeftLeg", "mixamorig:LeftToeBase"),
           "R": ("mixamorig:RightUpLeg", "mixamorig:RightLeg", "mixamorig:RightToeBase")}

# ---------------------------------------------------------------------------
# The curated battle-royale clip set.
#   root="inplace"  -> horizontal hip travel removed, vertical bob kept
#   root="motion"   -> full hip travel retargeted (dives, deaths, jumps)
# ---------------------------------------------------------------------------
def _loco(prefix, source_prefix):
    eight = [("F", "forward"), ("FL", "forward left"), ("FR", "forward right"),
             ("L", "left"), ("R", "right"), ("B", "backward"),
             ("BL", "backward left"), ("BR", "backward right")]
    return [dict(name=f"{prefix}_{tag}", file=f"{source_prefix} {word}.fbx",
                 loop=True, root="inplace") for tag, word in eight]


CLIPS: list[dict] = [
    dict(name="Idle", file="idle.fbx", loop=True, root="inplace"),
    dict(name="IdleAiming", file="idle aiming.fbx", loop=True, root="inplace"),
    dict(name="IdleCrouch", file="idle crouching.fbx", loop=True, root="inplace"),
    dict(name="ProneIdle", file="Prone Idle.fbx", loop=True, root="inplace"),
    *_loco("Walk", "walk"),
    *_loco("Run", "run"),
    dict(name="Sprint", file="Running.fbx", loop=True, root="inplace"),
    dict(name="CrouchWalk", file="Crouch Walking.fbx", loop=True, root="inplace"),
    dict(name="DiveRoll", file="Dive Roll.fbx", loop=False, root="motion"),
    dict(name="TossGrenade", file="Toss Grenade.fbx", loop=False, root="inplace"),
    dict(name="FireRifle", file="firing rifle.fbx", loop=True, root="inplace"),
    dict(name="Reload", file="reloading.fbx", loop=False, root="inplace"),
    dict(name="HitReaction", file="hit reaction.fbx", loop=False, root="inplace"),
    dict(name="JumpUp", file="jump up.fbx", loop=False, root="motion"),
    dict(name="JumpLoop", file="jump loop.fbx", loop=True, root="motion"),
    dict(name="JumpDown", file="jump down.fbx", loop=False, root="motion"),
    dict(name="Dying", file="Dying.fbx", loop=False, root="motion"),
    dict(name="DeathFront", file="death from the front.fbx", loop=False, root="motion"),
    dict(name="DeathBack", file="death from the back.fbx", loop=False, root="motion"),
    dict(name="TurnLeft90", file="turn 90 left.fbx", loop=False, root="inplace"),
    dict(name="TurnRight90", file="turn 90 right.fbx", loop=False, root="inplace"),
]
QUICK_CLIPS = ("Idle", "Run_F", "DiveRoll", "ProneIdle")

# Clips whose poses are used to validate the skinning. These are the ones that
# actually fold the body in half.
STRESS_CLIPS = ("DiveRoll", "ProneIdle", "Dying", "IdleCrouch", "CrouchWalk")

# ---------------------------------------------------------------------------
# Garments. Regions are selected by *dominant deform bone*, which is resolution
# independent and survives a different base mesh. `waist_z` splits the HIPS
# region between shirt and trousers.
# ---------------------------------------------------------------------------
GARMENTS = {
    "clothing_shirt": dict(
        bones={"SPINE_NAVAL", "SPINE_CHEST", "CLAVICLE_L", "CLAVICLE_R",
               "SHOULDER_L", "SHOULDER_R", "ELBOW_L", "ELBOW_R"},
        hips_above_waist=True, hips_below_waist=False,
        colour="2C3E50", roughness=0.82, inflate=1.05, min_t=0.006, max_t=0.028),
    "clothing_pants": dict(
        bones={"HIP_L", "HIP_R", "KNEE_L", "KNEE_R"},
        hips_above_waist=False, hips_below_waist=True,
        colour="1A1A1A", roughness=0.86, inflate=1.05, min_t=0.004, max_t=0.020),
}
WAIST_Z = 0.95      # at 1.80 m; rescaled with the mesh
SKIN_COLOUR = "D2A679"

LOG_T0 = time.time()


def log(msg: str) -> None:
    print(f"[{time.time() - LOG_T0:7.1f}s] {msg}", flush=True)


def srgb_to_linear(hexcode: str):
    out = []
    for i in (0, 2, 4):
        c = int(hexcode[i:i + 2], 16) / 255.0
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


# ===========================================================================
# 1. Base character
# ===========================================================================
BASE_SUFFIXES = (".glb", ".gltf", ".blend", ".fbx", ".obj")


def find_base_mesh() -> tuple[Path, str]:
    """characters/base_mesh/<something> if the artist dropped one in, else the
    repo's own 27-bone mid-poly body so CI is never blocked on an upload."""
    if BASE_MESH_DIR.is_dir():
        found = sorted(
            (p for p in BASE_MESH_DIR.iterdir()
             if p.is_file() and p.suffix.lower() in BASE_SUFFIXES
             and not p.name.startswith(".")),
            key=lambda p: (BASE_SUFFIXES.index(p.suffix.lower()), p.name))
        if found:
            return found[0], "characters/base_mesh"
    if not FALLBACK_BASE.is_file():
        raise SystemExit(
            f"No base character. Put a .glb/.fbx/.blend in {BASE_MESH_DIR} "
            f"(or restore {FALLBACK_BASE}).")
    return FALLBACK_BASE, "fallback"


def import_base(path: Path) -> None:
    ext = path.suffix.lower()
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=str(path))
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=str(path), automatic_bone_orientation=False,
                                 ignore_leaf_bones=False)
    elif ext == ".obj":
        bpy.ops.wm.obj_import(filepath=str(path))
    elif ext == ".blend":
        with bpy.data.libraries.load(str(path)) as (src, dst):
            dst.objects = list(src.objects)
        for obj in dst.objects:
            if obj is not None:
                bpy.context.scene.collection.objects.link(obj)
    else:
        raise SystemExit(f"Unsupported base mesh format: {path}")


def activate(obj) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def load_base_character(path: Path):
    """-> (mesh, armature, source_object_name_per_vertex)

    Imports whatever the artist supplied, flattens every mesh part into one
    object, and guarantees a 27-bone rig: reused verbatim if the file already
    carries one, rebuilt and auto-bound if it does not.
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = FPS
    bpy.context.scene.unit_settings.system = "METRIC"
    import_base(path)

    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not meshes:
        raise SystemExit(f"{path} contains no mesh")
    log(f"  imported {len(meshes)} mesh part(s), {len(arms)} armature(s)")

    # Bake every object transform so armature space == world space == mesh space.
    for obj in meshes + arms:
        obj.parent = None
        activate(obj)
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # Tag provenance before the join: a per-part vertex group survives joining
    # and tells us later which polygons are body and which are hair/eyes/etc.
    for i, obj in enumerate(meshes):
        grp = obj.vertex_groups.new(name=f"__part{i:03d}")
        grp.add(list(range(len(obj.data.vertices))), 1.0, "REPLACE")

    part_names = [o.name for o in meshes]   # the join invalidates these pointers
    body = max(meshes, key=lambda o: len(o.data.vertices))
    if len(meshes) > 1:
        bpy.ops.object.select_all(action="DESELECT")
        for obj in meshes:
            obj.select_set(True)
        bpy.context.view_layer.objects.active = body
        bpy.ops.object.join()
    body.name = BODY_NAME
    body.data.name = BODY_NAME

    part_of_vertex = np.full(len(body.data.vertices), -1, dtype=np.int32)
    bm = bmesh.new()
    bm.from_mesh(body.data)
    dvert = bm.verts.layers.deform.verify()
    n_parts = len(part_names)
    tag_index = {body.vertex_groups[f"__part{i:03d}"].index: i
                 for i in range(n_parts) if f"__part{i:03d}" in body.vertex_groups}
    bm.verts.ensure_lookup_table()
    for vi, v in enumerate(bm.verts):
        for gi, w in v[dvert].items():
            if gi in tag_index and w > 0.5:
                part_of_vertex[vi] = tag_index[gi]
                break
    bm.free()
    for i in range(n_parts):
        grp = body.vertex_groups.get(f"__part{i:03d}")
        if grp:
            body.vertex_groups.remove(grp)

    # Normalise height / origin before the rig is fitted to it.
    co = np.empty(len(body.data.vertices) * 3, dtype=np.float64)
    body.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    height = float(co[:, 2].max() - co[:, 2].min())
    shift = Vector((-(co[:, 0].max() + co[:, 0].min()) * 0.5,
                    -(co[:, 1].max() + co[:, 1].min()) * 0.5,
                    -co[:, 2].min()))
    if shift.length > 1e-5:
        body.data.transform(Matrix.Translation(shift))
        body.data.update()
        log(f"  re-centred base to bottom-centre origin by {tuple(round(v, 4) for v in shift)}")

    arm = None
    for candidate in arms:
        names = {b.name for b in candidate.data.bones}
        if names == set(RIG_BONES):
            arm = candidate
            log(f"  reusing the supplied 27-bone rig '{candidate.name}' verbatim")
            break
    for other in arms:
        if other is not arm:
            bpy.data.objects.remove(other, do_unlink=True)

    if arm is None:
        log(f"  no 27-bone rig in the file -> building one fitted to {height:.3f} m")
        for grp in list(body.vertex_groups):
            body.vertex_groups.remove(grp)
        arm = build_rig(height)
        bind_auto(body, arm)
    else:
        arm.name = RIG_NAME
        arm.data.name = RIG_NAME + "_Data"
        missing = [b for b in RIG_BONES if b not in body.vertex_groups]
        if missing:
            log(f"  rig present but {len(missing)} vertex groups missing -> re-binding")
            bind_auto(body, arm)

    body.parent = arm
    body.matrix_parent_inverse = Matrix.Identity(4)
    if not any(m.type == "ARMATURE" for m in body.modifiers):
        mod = body.modifiers.new("Armature", "ARMATURE")
        mod.object = arm
    for mod in body.modifiers:
        if mod.type == "ARMATURE":
            mod.object = arm
    arm.matrix_world = Matrix.Identity(4)
    body.matrix_world = Matrix.Identity(4)
    return body, arm, part_of_vertex, part_names, height


def build_rig(height: float):
    data = bpy.data.armatures.new(RIG_NAME + "_Data")
    arm = bpy.data.objects.new(RIG_NAME, data)
    bpy.context.scene.collection.objects.link(arm)
    activate(arm)
    bpy.ops.object.mode_set(mode="EDIT")
    for name, parent, head, tail in rig_spec(height):
        eb = data.edit_bones.new(name)
        eb.head = Vector(head)
        eb.tail = Vector(tail)
        eb.use_connect = False
        # Same roll convention as the rest of the repo's character rigs.
        eb.align_roll(Vector((0, -1, 0)))
        if parent:
            eb.parent = data.edit_bones[parent]
    bpy.ops.object.mode_set(mode="OBJECT")
    assert len(data.bones) == 27, len(data.bones)
    return arm


def bind_auto(body, arm) -> None:
    """Blender's bone-heat solver, with the repo's documented fallback.

    ``ARMATURE_AUTO`` can return FINISHED and still assign zero weight when the
    mesh is a set of disconnected shells (eyes, hair, teeth), which is exactly
    what the mid-poly bodies are. Detect that and fall back to a deterministic
    inverse-distance-to-bone-segment solve.
    """
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    try:
        bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    except RuntimeError as exc:
        log(f"  ARMATURE_AUTO raised {exc!r}")
    weights = read_weights(body, [b.name for b in arm.data.bones])
    covered = float((weights.sum(axis=1) > 1e-6).mean())
    log(f"  ARMATURE_AUTO weighted {covered * 100:.1f}% of vertices")
    if covered < 0.999:
        log("  -> falling back to distance-to-bone-segment skinning")
        weights = distance_weights(body, arm)
        write_weights(body, [b.name for b in arm.data.bones], weights)


def bone_segments(arm) -> list[tuple[str, Vector, Vector]]:
    return [(b.name, b.head_local.copy(), b.tail_local.copy()) for b in arm.data.bones]


def distance_weights(body, arm, falloff: float = 4.0) -> np.ndarray:
    segs = bone_segments(arm)
    names = [s[0] for s in segs]
    heads = np.array([list(s[1]) for s in segs])
    tails = np.array([list(s[2]) for s in segs])
    co = np.empty(len(body.data.vertices) * 3)
    body.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    d = point_segment_distance(co, heads, tails)
    w = 1.0 / np.power(np.maximum(d, 1e-4), falloff)
    w /= w.sum(axis=1, keepdims=True)
    assert len(names) == w.shape[1]
    return w


def point_segment_distance(points: np.ndarray, heads: np.ndarray, tails: np.ndarray) -> np.ndarray:
    """(V,3), (B,3), (B,3) -> (V,B) perpendicular distance to each bone segment."""
    ab = tails - heads                                    # (B,3)
    denom = np.einsum("bi,bi->b", ab, ab)
    denom = np.where(denom < 1e-12, 1.0, denom)
    ap = points[:, None, :] - heads[None, :, :]           # (V,B,3)
    t = np.einsum("vbi,bi->vb", ap, ab) / denom
    t = np.clip(t, 0.0, 1.0)
    closest = heads[None, :, :] + t[..., None] * ab[None, :, :]
    return np.linalg.norm(points[:, None, :] - closest, axis=2)


# ===========================================================================
# 2. Weights: read / write / clean
# ===========================================================================
def read_weights(obj, names: list[str]) -> np.ndarray:
    idx = {}
    for n in names:
        grp = obj.vertex_groups.get(n)
        if grp is not None:
            idx[grp.index] = names.index(n)
    w = np.zeros((len(obj.data.vertices), len(names)), dtype=np.float64)
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    dvert = bm.verts.layers.deform.verify()
    for vi, v in enumerate(bm.verts):
        for gi, val in v[dvert].items():
            col = idx.get(gi)
            if col is not None:
                w[vi, col] = val
    bm.free()
    return w


def write_weights(obj, names: list[str], w: np.ndarray) -> None:
    for n in names:
        if n not in obj.vertex_groups:
            obj.vertex_groups.new(name=n)
    cols = [obj.vertex_groups[n].index for n in names]
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    dvert = bm.verts.layers.deform.verify()
    keep = set(cols)
    for vi, v in enumerate(bm.verts):
        d = v[dvert]
        for gi in [g for g in d.keys() if g in keep]:
            del d[gi]
        row = w[vi]
        for c, col in enumerate(cols):
            if row[c] > WEIGHT_EPS:
                d[col] = float(row[c])
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()


def mesh_adjacency(obj):
    """CSR-ish neighbour arrays built from mesh edges (used for weight smoothing)."""
    n = len(obj.data.vertices)
    e = np.empty(len(obj.data.edges) * 2, dtype=np.int64)
    obj.data.edges.foreach_get("vertices", e)
    e = e.reshape(-1, 2)
    both = np.concatenate([e, e[:, ::-1]], axis=0)
    order = np.argsort(both[:, 0], kind="stable")
    both = both[order]
    counts = np.bincount(both[:, 0], minlength=n)
    starts = np.concatenate([[0], np.cumsum(counts)])
    return both[:, 1], starts, counts


def smooth_weights(w: np.ndarray, nbr, starts, counts, factor: float, rounds: int) -> np.ndarray:
    """Laplacian smoothing of the weight field over the mesh graph."""
    out = w
    safe = np.maximum(counts, 1)[:, None]
    for _ in range(rounds):
        summed = np.add.reduceat(out[nbr], starts[:-1], axis=0)
        summed[counts == 0] = 0.0
        mean = summed / safe
        out = (1.0 - factor) * out + factor * mean
        out = np.maximum(out, 0.0)
        total = out.sum(axis=1, keepdims=True)
        out = np.divide(out, total, out=np.zeros_like(out), where=total > 1e-9)
    return out


def prune_long_range(w: np.ndarray, dist: np.ndarray, ratio: float = 2.6,
                     margin: float = 0.07) -> tuple[np.ndarray, int]:
    """Kill influences from bones that are implausibly far from the vertex.

    This is the single biggest cause of a mesh tearing in a Dive Roll: the heat
    solver occasionally leaks a few percent of a shin bone onto the chest, and
    once the shin swings 150 degrees that chest vertex is dragged with it.
    """
    nearest = dist.min(axis=1, keepdims=True)
    allowed = ratio * nearest + margin
    mask = dist <= allowed
    removed = int(((w > WEIGHT_EPS) & ~mask).sum())
    w = np.where(mask, w, 0.0)
    total = w.sum(axis=1, keepdims=True)
    # Never orphan a vertex: if pruning took everything, keep the nearest bone.
    dead = (total[:, 0] <= 1e-9)
    if dead.any():
        w[dead, np.argmin(dist[dead], axis=1)] = 1.0
        total = w.sum(axis=1, keepdims=True)
    return w / total, removed


# NOTE -- a closest-point weight transfer was implemented here and removed.
# The mid-poly base characters ship their sportswear as separate mesh islands
# that are almost entirely HIPS-weighted, so Laplacian smoothing (which only
# diffuses along edges) cannot reach them, and re-deriving their weights from
# the body surface underneath looked like the obvious fix. Measured over the
# five stress clips and every edge, it made them *worse*, not better:
#
#     Athletic_Shorts, max edge stretch   no transfer 4.03x   transfer 8.67x
#     Athletic_Shorts, max edge growth    no transfer 32.0mm  transfer 50.4mm
#     body shell (unaffected either way)  1.285x / 5.4mm
#
# A loose shell whose hem stands off the thigh tears open when the waist keeps
# hip weights and the hem gains thigh weights; a rigid shell merely intersects.
# The honest conclusion is that this is a property of the *base asset*, not of
# retargeting, and the deformation report splits the two so it stays visible.
# Supply a single welded body in characters/base_mesh/ and the issue disappears.


def limit_influences(w: np.ndarray, limit: int = MAX_INFLUENCES) -> np.ndarray:
    if w.shape[1] <= limit:
        return w
    keep = np.argpartition(-w, limit - 1, axis=1)[:, :limit]
    out = np.zeros_like(w)
    rows = np.arange(w.shape[0])[:, None]
    out[rows, keep] = w[rows, keep]
    total = out.sum(axis=1, keepdims=True)
    total[total < 1e-12] = 1.0
    return out / total


# ===========================================================================
# 3. Linear blend skinning in numpy (fast enough to run every frame)
# ===========================================================================
class Skinner:
    """Evaluates posed vertex positions without touching the depsgraph.

    The depsgraph route (``obj.evaluated_get(dg).to_mesh()``) costs ~30 ms per
    frame on this mesh; over 35 clips that is minutes. Linear blend skinning is
    what the armature modifier and every glTF runtime actually do, so this is
    not an approximation of the shipped result -- it *is* the shipped result.
    """

    def __init__(self, body, arm, names: list[str], subset: np.ndarray | None = None):
        self.names = names
        co = np.empty(len(body.data.vertices) * 3)
        body.data.vertices.foreach_get("co", co)
        self.rest_all = co.reshape(-1, 3)
        self.subset = np.arange(len(self.rest_all)) if subset is None else subset
        self.rest = self.rest_all[self.subset]
        w = read_weights(body, names)[self.subset]
        total = w.sum(axis=1, keepdims=True)
        total[total < 1e-12] = 1.0
        self.w = (w / total).astype(np.float64)
        self.inv_rest = {n: arm.data.bones[n].matrix_local.inverted() for n in names}

    def deform_flat(self, computed: dict) -> np.ndarray:
        rows = np.empty((len(self.names), 16))
        for i, n in enumerate(self.names):
            m = computed[n] @ self.inv_rest[n]
            rows[i] = [m[r][c] for r in range(4) for c in range(4)]
        return rows

    def skin(self, computed: dict) -> np.ndarray:
        m = (self.w @ self.deform_flat(computed)).reshape(-1, 4, 4)
        return np.einsum("vij,vj->vi", m[:, :3, :3], self.rest) + m[:, :3, 3]


# ===========================================================================
# 4. Retargeting
# ===========================================================================
class Target:
    """Pre-computed rest data for the 27-bone rig (identity world matrix)."""

    def __init__(self, arm, height: float):
        self.arm = arm
        self.order = topo_order(arm)
        self.rest = {n: arm.data.bones[n].matrix_local.copy() for n in self.order}
        self.rest3 = {n: self.rest[n].to_3x3() for n in self.order}
        self.offset = {}
        for n in self.order:
            p = RIG_PARENTS[n]
            self.offset[n] = (self.rest[p].inverted() @ self.rest[n]) if p else None
        self.leg_length = sum(arm.data.bones[b].length for b in ("HIP_L", "KNEE_L"))
        # Mesh height, not `max(tail.z)`: a rig that arrived through glTF has
        # importer-synthesised tails on every leaf bone, so HEAD's tail is an
        # arbitrary stub and the rig measures ~14 cm short of the character.
        self.height = float(height)


def topo_order(arm) -> list[str]:
    out: list[str] = []

    def walk(bone):
        out.append(bone.name)
        for child in bone.children:
            walk(child)

    for bone in arm.data.bones:
        if bone.parent is None:
            walk(bone)
    return out


def solve_pose(t: Target, desired: dict, root_head: Vector | None):
    """desired: bone -> wanted *armature-space* 3x3 rotation. -> (computed, q, loc)"""
    computed, quats, locs = {}, {}, {}
    for name in t.order:
        parent = RIG_PARENTS[name]
        base = t.rest[name] if parent is None else computed[parent] @ t.offset[name]
        base3 = base.to_3x3()
        want = desired.get(name)
        q = (base3.inverted() @ want).to_quaternion() if want is not None else Quaternion()
        q.normalize()
        loc = Vector((0.0, 0.0, 0.0))
        if name == ROOT_BONE and root_head is not None:
            loc = base3.inverted() @ (root_head - base.translation)
        computed[name] = base @ (Matrix.Translation(loc) @ q.to_matrix().to_4x4())
        quats[name] = q
        locs[name] = loc
    return computed, quats, locs


def sample_source(src, frames: list[int]):
    """-> (deltas[frame][bone] 3x3 world delta, hips_head[frame], toe_z[frame][side])"""
    scene = bpy.context.scene
    mw = src.matrix_world.copy()
    mw3 = mw.to_3x3()
    bones = src.data.bones
    rest3_inv, rest_head = {}, {}
    for name in set(BONE_MAP.values()) | {SRC_HIPS} | {b for v in SRC_LEG.values() for b in v}:
        if name in bones:
            m = mw @ bones[name].matrix_local
            rest3_inv[name] = m.to_3x3().inverted()
            rest_head[name] = m.translation.copy()

    deltas, hips_head, toe_pos = [], [], []
    for f in frames:
        scene.frame_set(f)
        ev = src.evaluated_get(bpy.context.evaluated_depsgraph_get())
        pb = ev.pose.bones
        frame_delta = {}
        for tgt_name, src_name in BONE_MAP.items():
            if src_name not in rest3_inv:
                continue
            world = mw3 @ pb[src_name].matrix.to_3x3()
            frame_delta[tgt_name] = (world @ rest3_inv[src_name]).to_quaternion().to_matrix()
        deltas.append(frame_delta)
        hips_head.append((mw @ pb[SRC_HIPS].matrix).translation.copy())
        toe_pos.append({s: (mw @ pb[SRC_LEG[s][2]].matrix).translation.copy()
                        for s in ("L", "R") if SRC_LEG[s][2] in bones})
    return deltas, hips_head, rest_head, toe_pos


def detect_contacts(toe_pos: list[dict], hips_head: list, src_leg: float,
                    scale_h: float, scale_v: float) -> dict:
    """Plantedness per foot per frame, read off the *source* animation.

    A foot is planted when its toe is near **the ground** and not travelling
    horizontally. The ground is the lowest either toe reaches in the clip, not
    the lowest *that* toe reaches: a foot that stays in the air for the whole
    clip (the trailing leg of a dive roll) would otherwise report a contact at
    its own lowest frame and get yanked down onto the floor. Deriving contacts
    from the source rather than from our own result keeps the contact pattern
    the animator's.
    """
    if not toe_pos or not toe_pos[0]:
        return {}, {}
    n = len(toe_pos)
    sides = list(toe_pos[0])
    floor = min(p[s].z for p in toe_pos for s in sides) * scale_v
    hips_z = np.array([h.z for h in hips_head])
    out, clearance = {}, {}
    for side in sides:
        z = np.array([p[side].z for p in toe_pos]) * scale_v
        xy = np.array([[p[side].x, p[side].y] for p in toe_pos]) * scale_h
        speed = np.zeros(n)
        if n > 1:
            d = np.linalg.norm(np.diff(xy, axis=0), axis=1)
            speed[:-1] = d
            speed[1:] = np.maximum(speed[1:], d)
        raw_z = np.array([p[side].z for p in toe_pos])
        upright = (hips_z - raw_z) > UPRIGHT_LEG_FRACTION * src_leg
        out[side] = ((z - floor) < 0.06) & (speed < 0.015) & upright
        # How high the *source* held this foot. The retarget target is to match
        # that clearance, not to slam the foot onto z = 0: in Death From Front
        # the character recoils 31 mm off the ground at frame 13 while still
        # looking planted, and absolute grounding reported that as a 38 mm
        # "float" and tried to IK it away.
        clearance[side] = np.maximum(z - floor, 0.0)
    return out, clearance


def box_smooth(a: np.ndarray, width: int) -> np.ndarray:
    if width <= 1 or a.size == 0:
        return a
    pad = width // 2
    padded = np.pad(a, pad, mode="edge")
    kernel = np.ones(width) / width
    return np.convolve(padded, kernel, mode="valid")[:a.size]


def shift_edge(a: np.ndarray, k: int) -> np.ndarray:
    """Shift by k samples, clamping at the ends (np.roll would wrap a short clip)."""
    if k == 0:
        return a
    out = np.empty_like(a)
    if k > 0:
        out[:k] = a[0]
        out[k:] = a[:-k]
    else:
        out[k:] = a[-1]
        out[:k] = a[-k:]
    return out


def ramp_contacts(planted: np.ndarray, ramp: int = 3) -> np.ndarray:
    """0..1 weight: 1 across the whole contact, fading out into the air frames.

    The mask is *dilated* before it is smoothed. Smoothing alone erodes the
    plateau, so the first and last frames of every footfall only received a
    fraction of their correction -- which is precisely where the worst
    remaining float was being measured.
    """
    w = planted.astype(np.float64)
    for _ in range(ramp):
        w = np.maximum.reduce([w, shift_edge(w, 1), shift_edge(w, -1)])
    return np.clip(box_smooth(w, 2 * ramp + 1), 0.0, 1.0)


def blend_lift(residual: np.ndarray, planted: np.ndarray, width: int) -> np.ndarray:
    """Smallest smooth lift that still guarantees no floor penetration.

    The obvious operator, ``maximum(box_smooth(residual), residual)``, is smooth
    and never under-lifts -- but a box filter of width 7 spreads a genuine
    penetration spike +-3 frames, and those neighbours are often exactly the
    frames where a foot is planted. That is what floated Death From Front: at
    frames 12-17 the *whole body* hung 30-38 mm up with the planted foot as its
    lowest point, and no amount of leg IK could reach back down because the leg
    was already straight (16 frames reported unreachable).

    A planted foot pins the body to the floor, so at those frames the only legal
    lift is the bare minimum, ``residual``. Away from contact we are free to
    smooth. Blending the two with the same contact ramp the IK uses keeps the
    curve continuous, and because ``smoothed >= residual`` pointwise the convex
    blend is also ``>= residual`` -- the no-penetration guarantee is preserved
    exactly, not traded away.
    """
    if not residual.any():
        return np.zeros(len(residual))
    smoothed = np.maximum(box_smooth(residual, width), residual)
    if not planted.any():
        return smoothed
    c = ramp_contacts(planted)
    return residual * c + smoothed * (1.0 - c)


def apply_leg_ik(desired: dict, computed: dict, side: str, dz: float) -> bool:
    """Analytic two-bone IK: move the ankle by `dz` in Z, keep the knee's plane.

    Only HIP/KNEE world rotations are touched. ANKLE and FOOT keep the world
    orientation the retarget gave them, so correcting a float never tips the
    sole off the ground.
    """
    hip, knee, ankle = f"HIP_{side}", f"KNEE_{side}", f"ANKLE_{side}"
    if hip not in desired or knee not in desired:
        return True
    p0 = computed[hip].translation.copy()
    pk = computed[knee].translation.copy()
    pa = computed[ankle].translation.copy()
    l1 = (pk - p0).length
    l2 = (pa - pk).length
    if l1 < 1e-5 or l2 < 1e-5:
        return True
    target = pa + Vector((0.0, 0.0, dz))
    to_target = target - p0
    d = to_target.length
    if d < 1e-5:
        return True
    reach = (l1 + l2) * 0.9995
    reachable = d <= reach
    d = min(max(d, abs(l1 - l2) + 1e-4), reach)
    direction = to_target.normalized()
    clamped = p0 + direction * d
    cos1 = max(-1.0, min(1.0, (l1 * l1 + d * d - l2 * l2) / (2.0 * l1 * d)))
    a1 = math.acos(cos1)
    perp = (pk - p0) - direction * (pk - p0).dot(direction)
    if perp.length < 1e-5:
        fwd = Vector((0.0, -1.0, 0.0))
        perp = fwd - direction * fwd.dot(direction)
        if perp.length < 1e-5:
            perp = Vector((0.0, 0.0, 1.0)) - direction * direction.z
    perp.normalize()
    knee_new = p0 + direction * (l1 * math.cos(a1)) + perp * (l1 * math.sin(a1))

    r1 = (pk - p0).rotation_difference(knee_new - p0).to_matrix()
    desired[hip] = r1 @ desired[hip]
    r2 = (pa - pk).rotation_difference(clamped - knee_new).to_matrix()
    desired[knee] = r2 @ desired[knee]
    return reachable


def fix_quaternion_flips(curves: dict, loop: bool) -> float:
    """Hemisphere-match each bone's key sequence. Returns the worst dot product.

    q and -q are the same rotation but interpolate the long way round between
    them, which is the classic "limb snaps through the body for one frame"
    glitch. glTF stores raw quaternions, so the fix has to happen here.
    """
    worst = 1.0
    for name, quats in curves.items():
        for i in range(1, len(quats)):
            if quats[i].dot(quats[i - 1]) < 0.0:
                quats[i] = Quaternion((-quats[i].w, -quats[i].x, -quats[i].y, -quats[i].z))
        if loop and len(quats) > 1 and quats[-1].dot(quats[0]) < 0.0:
            # A looping clip also has to be continuous across the wrap point.
            for i in range(len(quats)):
                q = quats[i]
                quats[i] = Quaternion((-q.w, -q.x, -q.y, -q.z))
        for i in range(1, len(quats)):
            worst = min(worst, quats[i].dot(quats[i - 1]))
    return worst


def retarget_clip(clip: dict, src, t: Target, skinner: Skinner,
                  foot_subsets: dict, ik: bool = True) -> dict:
    scene = bpy.context.scene
    action = src.animation_data.action
    f0, f1 = (int(round(v)) for v in action.frame_range)
    frames = list(range(f0, f1 + 1))
    deltas, hips_head, src_rest_head, toe_pos = sample_source(src, frames)

    # --- proportional scaling -------------------------------------------------
    src_height = max((src.matrix_world @ b.matrix_local).translation.z
                     for b in src.data.bones)
    src_leg = 0.0
    up, lo, _ = SRC_LEG["L"]
    if up in src.data.bones and lo in src.data.bones:
        sc = abs(src.matrix_world.to_scale()[0])
        src_leg = (src.data.bones[up].length + src.data.bones[lo].length) * sc
    scale_h = t.height / max(src_height, 1e-6)
    scale_v = (t.leg_length / src_leg) if src_leg > 1e-6 else scale_h
    inplace = clip.get("root") != "motion"

    rest_hips = t.rest[ROOT_BONE].translation.copy()
    src_hips_rest = src_rest_head[SRC_HIPS]

    def root_for(i: int, extra_z: float = 0.0) -> Vector:
        # Height is mapped **absolutely**, not as a rest-relative delta: the
        # Mixamo rig stands with its toes on z = 0, so `hips.z` already is
        # "hip height above the ground" and only needs the leg-length ratio.
        # A rest-relative delta (rest_z + dz * k) silently re-grounds every clip
        # to our rest hip height, which lifted the standing frames of Dive Roll
        # 249 mm into the air once the roll pushed the datum down.
        off = hips_head[i] - src_hips_rest
        x = 0.0 if inplace else off.x * scale_h
        y = 0.0 if inplace else off.y * scale_h
        return Vector((rest_hips.x + x, rest_hips.y + y,
                       hips_head[i].z * scale_v + extra_z))

    # --- pass 1: plain retarget ----------------------------------------------
    poses = []
    for i, _f in enumerate(frames):
        desired = {n: deltas[i][n] @ t.rest3[n] for n in deltas[i]}
        computed, _q, _l = solve_pose(t, desired, root_for(i))
        poses.append((desired, computed))

    # --- pass 2: ground adaptation -------------------------------------------
    # One rigid Z offset cannot serve a clip that both stands and tumbles. Our
    # torso is proportionally longer than Mixamo's, so a tucked Dive Roll takes
    # the head 127 mm lower than the source does; datum-ing the whole clip off
    # that worst frame lifted the *standing* frames 249 mm into the air.
    # So: take the datum from the frames the source says are planted (feet
    # land exactly on the floor), then add a smooth, non-negative lift wherever
    # the body would still penetrate. `maximum(smoothed, raw)` keeps the lift
    # visually smooth while guaranteeing the hard no-penetration constraint.
    contacts, clearance = detect_contacts(toe_pos, hips_head, src_leg,
                                          scale_h, scale_v)
    planted_any = np.zeros(len(frames), dtype=bool)
    for planted in contacts.values():
        planted_any |= planted
    low = np.array([skinner.skin(c)[:, 2].min() for _d, c in poses])
    const = -float(low[planted_any].min() if planted_any.any() else low.min())
    residual = np.maximum(-(low + const), 0.0)
    ground = const + blend_lift(residual, planted_any, 7)
    floor_shift = const
    for i in range(len(frames)):
        poses[i] = (poses[i][0], solve_pose(t, poses[i][0], root_for(i, ground[i]))[0])

    # --- pass 3: per-foot residual, via IK on detected contacts ---------------
    if not ik:
        contacts = {}
    ik_frames = 0
    unreachable: set = set()
    root_drop = 0.0
    residual_before = {}
    weights = {s: ramp_contacts(p) for s, p in contacts.items() if p.any()}
    for outer in range(ROOT_DROP_ROUNDS + 1):
        unreachable = set()
        for passno in range(IK_PASSES if contacts else 0):
            for side, weight in weights.items():
                planted = contacts[side]
                sub = foot_subsets[side]
                measured = np.array([float(sub.skin(c)[:, 2].min()) for _d, c in poses])
                err = measured - clearance[side]
                if outer == 0 and passno == 0:
                    residual_before[side] = float(np.abs(err[planted]).max())
                # The first pass smooths hard (the raw residual is noisy); later
                # passes only mop up what is left, so they barely need filtering.
                # Filtering them as hard as the first pass is what left a 38 mm
                # transient on the two knockback frames of Death From Front: the
                # spike was averaged away against its quiet neighbours faster
                # than the solve could converge on it.
                correction = -err * weight
                correction = box_smooth(correction,
                                        IK_SMOOTH[min(passno, len(IK_SMOOTH) - 1)])
                correction = np.clip(correction, -0.12, 0.12)
                for i in range(len(frames)):
                    if abs(correction[i]) < 2e-4:
                        continue
                    desired, computed = poses[i]
                    if not apply_leg_ik(desired, computed, side, correction[i]):
                        unreachable.add((side, i))
                    poses[i] = (desired,
                                solve_pose(t, desired, root_for(i, ground[i]))[0])
                    ik_frames += 1

        # --- pass 3b: drop the root where a planted foot cannot reach ---------
        # Leg IK is asymmetric: *raising* a foot only bends the knee and always
        # succeeds, while *lowering* one runs out of leg. Death From Front hangs
        # the body 103 mm up at the knockback (no penetration anywhere -- the
        # ground residual is a flat zero there), so the straightened leg is
        # still 38 mm short. Lowering the whole root closes that gap, and the
        # feet that were already correct simply bend their knees to stay put on
        # the next round. The drop is capped by the clip's own floor clearance,
        # so this can never introduce penetration.
        if outer == ROOT_DROP_ROUNDS or not unreachable:
            break
        excess = np.zeros(len(frames))
        for side, planted in contacts.items():
            sub = foot_subsets[side]
            measured = np.array([float(sub.skin(c)[:, 2].min()) for _d, c in poses])
            excess = np.maximum(excess, np.where(planted,
                                                 measured - clearance[side], 0.0))
        headroom = np.maximum(
            np.array([float(skinner.skin(c)[:, 2].min()) for _d, c in poses]), 0.0)
        drop = np.minimum(np.maximum(excess, 0.0), headroom)
        drop = box_smooth(drop * ramp_contacts(planted_any), 3)
        drop = np.minimum(drop, headroom)          # re-cap: smoothing can overshoot
        if drop.max() <= 2e-4:
            break
        root_drop = max(root_drop, float(drop.max()))
        ground = ground - drop
        for i in range(len(frames)):
            poses[i] = (poses[i][0],
                        solve_pose(t, poses[i][0], root_for(i, ground[i]))[0])

    # --- pass 4: hard no-penetration guard -----------------------------------
    # Pulling an ankle down can push a knee or a hip through the floor. Lift
    # whatever is left, smoothly, and never below the raw requirement.
    after_low = np.array([float(skinner.skin(c)[:, 2].min()) for _d, c in poses])
    sink = np.maximum(-after_low, 0.0)
    if sink.max() > 1e-4:
        ground = ground + blend_lift(sink, planted_any, 5)
        for i in range(len(frames)):
            poses[i] = (poses[i][0], solve_pose(t, poses[i][0], root_for(i, ground[i]))[0])

    # --- collect curves -------------------------------------------------------
    curves: dict[str, list[Quaternion]] = {n: [] for n in t.order}
    root_locs: list[Vector] = []
    for i in range(len(frames)):
        desired = poses[i][0]
        computed, quats, locs = solve_pose(t, desired, root_for(i, ground[i]))
        poses[i] = (desired, computed)
        for n in t.order:
            curves[n].append(quats[n])
        root_locs.append(locs[ROOT_BONE])
    worst_dot = fix_quaternion_flips(curves, bool(clip.get("loop")))

    # --- measurements ---------------------------------------------------------
    final_low = np.array([float(skinner.skin(c)[:, 2].min()) for _d, c in poses])
    skinned_min = float(final_low.min())
    grounded_min = float(final_low[planted_any].min()) if planted_any.any() else skinned_min
    contact_float = 0.0
    for side, planted in contacts.items():
        sub = foot_subsets[side]
        after = np.array([float(sub.skin(c)[:, 2].min()) for _d, c in poses])
        if planted.any():
            residual = np.abs(after - clearance[side])[planted]
            contact_float = max(contact_float, float(residual.max()))

    return dict(name=clip["name"], frames=frames, curves=curves, root=root_locs,
                loop=bool(clip.get("loop")), root_mode=clip.get("root", "inplace"),
                poses=[c for _d, c in poses],
                stats=dict(frame_count=len(frames), floor_shift=round(floor_shift, 5),
                           ground_lift_max=round(float(np.max(ground - const)), 5),
                           contact_frames=int(planted_any.sum()),
                           min_z=round(skinned_min, 5),
                           min_z_when_planted=round(grounded_min, 5),
                           contact_float_m=round(contact_float, 5),
                           contact_float_before_m={k: round(v, 5) for k, v in residual_before.items()},
                           ik_corrected_frames=ik_frames,
                           ik_unreachable_frames=len(unreachable),
                           root_drop_m=round(root_drop, 5),
                           min_quaternion_dot=round(worst_dot, 6),
                           scale_horizontal=round(scale_h, 5), scale_vertical=round(scale_v, 5)))


# ===========================================================================
# 5. Actions (Blender 4.4+ slotted actions, with a legacy fallback)
# ===========================================================================
def new_action(name: str, arm):
    """Return (action, make_fcurve) for whichever Action API this build exposes."""
    action = bpy.data.actions.new(name)
    action.use_fake_user = True
    if hasattr(action, "slots") and hasattr(action, "layers"):
        slot = action.slots.new(id_type="OBJECT", name=arm.name)
        layer = action.layers.new("Layer")
        strip = layer.strips.new(type="KEYFRAME")
        bag = strip.channelbag(slot, ensure=True)

        def make(path, index):
            return bag.fcurves.new(path, index=index)

        return action, make, slot

    def make_legacy(path, index):
        return action.fcurves.new(path, index=index)

    return action, make_legacy, None


def assign_action(arm, action, slot) -> None:
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = action
    if slot is not None and hasattr(arm.animation_data, "action_slot"):
        arm.animation_data.action_slot = slot


def build_action(arm, clip: dict):
    action, make, slot = new_action(clip["name"], arm)
    frames = clip["frames"]
    base = frames[0]
    xs = np.array([f - base + 1 for f in frames], dtype=np.float64)

    def write(path, index, values):
        fc = make(path, index)
        fc.keyframe_points.add(count=len(values))
        flat = np.empty(len(values) * 2)
        flat[0::2] = xs
        flat[1::2] = values
        fc.keyframe_points.foreach_set("co", flat)
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"
        fc.update()

    for name, quats in clip["curves"].items():
        path = f'pose.bones["{name}"].rotation_quaternion'
        comps = np.array([[q.w, q.x, q.y, q.z] for q in quats])
        for i in range(4):
            write(path, i, comps[:, i])
    locs = np.array([[v.x, v.y, v.z] for v in clip["root"]])
    for i in range(3):
        write(f'pose.bones["{ROOT_BONE}"].location', i, locs[:, i])
    if hasattr(action, "use_frame_range"):
        action.use_frame_range = True
        action.frame_start = float(xs[0])
        action.frame_end = float(xs[-1])
        action.use_cyclic = bool(clip["loop"])
    return action, slot


# ===========================================================================
# 6. Clothing
# ===========================================================================
def make_material(name: str, hexcode: str, roughness: float):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = srgb_to_linear(hexcode)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    mat.use_backface_culling = False
    return mat


def welded_normals(obj) -> np.ndarray:
    """Per-vertex normals averaged by *position*, not by index.

    Procedural bodies in this repo are partly unwelded (the same corner stored
    several times), and using raw per-vertex normals there tears a garment open
    along every seam.
    """
    me = obj.data
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    nor = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("normal", nor)
    nor = nor.reshape(-1, 3)
    keys = np.round(co * 1e5).astype(np.int64)
    _, inverse = np.unique(keys, axis=0, return_inverse=True)
    summed = np.zeros((inverse.max() + 1, 3))
    np.add.at(summed, inverse, nor)
    merged = summed[inverse]
    lengths = np.linalg.norm(merged, axis=1, keepdims=True)
    lengths[lengths < 1e-9] = 1.0
    return merged / lengths


def build_garment(body, arm, key: str, cfg: dict, weights: np.ndarray,
                  names: list[str], body_mask: np.ndarray, mode: str, height: float):
    """Cut the garment out of the body and inflate it off the limb axis."""
    waist = WAIST_Z * height / TARGET_HEIGHT
    dominant = np.argmax(weights, axis=1)
    dom_name = np.array(names, dtype=object)[dominant]
    co = np.empty(len(body.data.vertices) * 3)
    body.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)

    keep = np.isin(dom_name, list(cfg["bones"]))
    hips = dom_name == "HIPS"
    if cfg["hips_above_waist"]:
        keep |= hips & (co[:, 2] >= waist)
    if cfg["hips_below_waist"]:
        keep |= hips & (co[:, 2] < waist)
    keep &= body_mask
    if keep.sum() < 50:
        raise SystemExit(f"garment {key}: only {int(keep.sum())} vertices selected")

    activate(body)
    bpy.ops.object.duplicate()
    garment = bpy.context.view_layer.objects.active
    garment.name = key
    garment.data.name = key

    bm = bmesh.new()
    bm.from_mesh(garment.data)
    bm.verts.ensure_lookup_table()
    doomed = [v for i, v in enumerate(bm.verts) if not keep[i]]
    bmesh.ops.delete(bm, geom=doomed, context="VERTS")
    bm.to_mesh(garment.data)
    bm.free()
    garment.data.update()

    kept_idx = np.nonzero(keep)[0]
    garment.data.calc_normals_split() if hasattr(garment.data, "calc_normals_split") else None
    normals = welded_normals(garment)

    gco = np.empty(len(garment.data.vertices) * 3)
    garment.data.vertices.foreach_get("co", gco)
    gco = gco.reshape(-1, 3)

    if mode == "scale":
        # The literal reading of "scale 1.05x": a scale about the world origin.
        # Kept so the report can quote what it costs.
        new_co = gco * cfg["inflate"]
    else:
        heads = np.array([list(arm.data.bones[n].head_local) for n in names])
        tails = np.array([list(arm.data.bones[n].tail_local) for n in names])
        radius = point_segment_distance(gco, heads, tails).min(axis=1)
        thickness = np.clip((cfg["inflate"] - 1.0) * radius, cfg["min_t"], cfg["max_t"])
        new_co = gco + normals * thickness[:, None]
    garment.data.vertices.foreach_set("co", new_co.ravel())
    garment.data.update()

    garment.data.materials.clear()
    garment.data.materials.append(make_material(f"Cloth_{key}", cfg["colour"], cfg["roughness"]))
    for poly in garment.data.polygons:
        poly.material_index = 0

    for mod in list(garment.modifiers):
        garment.modifiers.remove(mod)
    mod = garment.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    garment.parent = arm
    garment.matrix_parent_inverse = Matrix.Identity(4)
    garment.matrix_world = Matrix.Identity(4)

    gw = read_weights(garment, names)
    identical = bool(np.allclose(gw, weights[kept_idx], atol=1e-6))
    coverage = float(np.linalg.norm(new_co - gco, axis=1).mean())
    return garment, dict(
        name=key, vertices=len(garment.data.vertices),
        triangles=sum(len(p.vertices) - 2 for p in garment.data.polygons),
        weights_identical_to_body=identical,
        mean_offset_mm=round(coverage * 1000, 3),
        min_offset_mm=round(float(np.linalg.norm(new_co - gco, axis=1).min()) * 1000, 3),
        max_offset_mm=round(float(np.linalg.norm(new_co - gco, axis=1).max()) * 1000, 3),
        mode=mode, source_vertices=kept_idx.tolist()[:0])


# ===========================================================================
# 7. Export
# ===========================================================================
def export_glb(path: Path, objects: list, extra: dict | None = None) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    kwargs = dict(
        filepath=str(path), export_format="GLB", use_selection=True,
        export_yup=True, export_apply=False,
        export_skins=True, export_influence_nb=MAX_INFLUENCES,
        export_all_influences=False, export_materials="EXPORT",
        export_animations=True, export_animation_mode="ACTIONS",
        export_bake_animation=False, export_force_sampling=False,
        export_optimize_animation_size=False,
        export_optimize_animation_keep_anim_armature=True,
        export_anim_slide_to_zero=False, export_nla_strips=False,
        export_frame_range=False, export_def_bones=False,
        export_rest_position_armature=True,
    )
    if extra:
        kwargs.update(extra)
    bpy.ops.export_scene.gltf(**kwargs)
    return path.stat().st_size


def glb_summary(path: Path) -> dict:
    import struct
    raw = path.read_bytes()
    magic, version, total = struct.unpack_from("<4sII", raw)
    assert magic == b"glTF" and version == 2 and total == len(raw), path
    length = struct.unpack_from("<I", raw, 12)[0]
    doc = json.loads(raw[20:20 + length])
    joints = {i for skin in doc.get("skins", []) for i in skin["joints"]}
    return dict(
        bytes=len(raw),
        animations=[a.get("name") for a in doc.get("animations", [])],
        animation_count=len(doc.get("animations", [])),
        joints=sorted(doc["nodes"][i].get("name") for i in joints),
        joint_count=len(joints),
        meshes=len(doc.get("meshes", [])),
        materials=len(doc.get("materials", [])),
        images=len(doc.get("images", [])),
    )


# ===========================================================================
# 8. Deformation validation
# ===========================================================================
def all_edges(body) -> np.ndarray:
    e = np.empty(len(body.data.edges) * 2, dtype=np.int64)
    body.data.edges.foreach_get("vertices", e)
    return e.reshape(-1, 2)


def measure_deformation(skinner: Skinner, edges: np.ndarray, body_edge: np.ndarray,
                        poses: list) -> dict:
    """How far the skin is pulled apart on the worst frames of the worst clips.

    Two deliberate choices, both learned from the measurements:

    * **Ratios are only read off edges >= MIN_REST_EDGE.** The mid-poly bodies
      carry 1.5 mm seam edges in the sportswear shells; one of those going to
      9 mm is a 6.2x "stretch" that nobody can see, and letting it drive the
      metric made the adaptive smoothing chew the whole rig to mush chasing it.
      The absolute growth in millimetres is reported alongside and *is* checked,
      so small edges are not simply ignored.
    * **Squash is checked only for degeneracy.** A knee tucked 150 degrees in a
      Dive Roll compresses the inside crease to a few percent under linear blend
      skinning; so does a real knee. That is a fold, not a defect. What matters
      is that it does not collapse to zero and invert.
    """
    rest = skinner.rest
    rest_len = np.linalg.norm(rest[edges[:, 0]] - rest[edges[:, 1]], axis=1)
    keep = (rest_len > 1e-6) & (rest_len >= MIN_REST_EDGE)
    edges, rest_len = edges[keep], rest_len[keep]
    is_body = body_edge[keep]
    worst = np.ones(len(edges))
    least = np.ones(len(edges))
    grow = np.zeros(len(edges))
    for computed in poses:
        p = skinner.skin(computed)
        length = np.linalg.norm(p[edges[:, 0]] - p[edges[:, 1]], axis=1)
        worst = np.maximum(worst, length / rest_len)
        least = np.minimum(least, length / rest_len)
        grow = np.maximum(grow, length - rest_len)

    def group(mask):
        if not mask.any():
            return dict(max_edge_stretch=1.0, min_edge_squash=1.0,
                        max_edge_growth_mm=0.0, edges=0)
        return dict(max_edge_stretch=round(float(worst[mask].max()), 4),
                    min_edge_squash=round(float(least[mask].min()), 4),
                    max_edge_growth_mm=round(float(grow[mask].max()) * 1000, 3),
                    p999_edge_stretch=round(float(np.percentile(worst[mask], 99.9)), 4),
                    edges=int(mask.sum()))

    return dict(body_shell=group(is_body), accessory_shells=group(~is_body),
                min_rest_edge_m=MIN_REST_EDGE, poses_sampled=len(poses),
                edges_total=int(len(edges)))


def deform_problems(d: dict) -> list[str]:
    out = []
    b, a = d["body_shell"], d["accessory_shells"]
    if b["max_edge_stretch"] > BODY_STRETCH_LIMIT:
        out.append(f"body stretches {b['max_edge_stretch']:.2f}x in extreme poses")
    if b["max_edge_growth_mm"] > BODY_GROWTH_LIMIT * 1000:
        out.append(f"a body edge grows {b['max_edge_growth_mm']:.1f} mm in extreme poses")
    if b["min_edge_squash"] < EDGE_SQUASH_LIMIT:
        out.append(f"body collapses to {b['min_edge_squash']:.3f}x in extreme poses")
    if a["edges"] and a["max_edge_stretch"] > ACCESSORY_STRETCH_LIMIT:
        out.append(f"accessory shells stretch {a['max_edge_stretch']:.2f}x "
                   f"(base-mesh quality, limit {ACCESSORY_STRETCH_LIMIT})")
    if a["edges"] and a["max_edge_growth_mm"] > ACCESSORY_GROWTH_LIMIT * 1000:
        out.append(f"an accessory edge grows {a['max_edge_growth_mm']:.1f} mm "
                   f"(base-mesh quality, limit {ACCESSORY_GROWTH_LIMIT * 1000:.0f} mm)")
    return out


def deform_ok(d: dict) -> bool:
    return not deform_problems(d)


def spread(items: list, count: int) -> list:
    if len(items) <= count:
        return list(items)
    step = len(items) / count
    return [items[int(i * step)] for i in range(count)]


# ===========================================================================
# 9. Pipeline
# ===========================================================================
EXCLUDE_PART_WORDS = ("hair", "eye", "iris", "lash", "brow", "lid", "nostril",
                      "lip", "tooth", "teeth", "tongue", "ear", "bra", "short",
                      "pant", "shirt", "cloth", "icosphere", "tie")


def body_part_mask(part_of_vertex: np.ndarray, part_names: list[str]) -> np.ndarray:
    counts = np.bincount(part_of_vertex[part_of_vertex >= 0],
                         minlength=max(len(part_names), 1))
    if counts.size == 0 or counts.sum() == 0:
        return np.ones(len(part_of_vertex), dtype=bool)
    largest = int(np.argmax(counts))
    keep = {largest}
    for i, name in enumerate(part_names):
        low = name.lower()
        if counts[i] >= 0.05 * counts.sum() and not any(w in low for w in EXCLUDE_PART_WORDS):
            keep.add(i)
    mask = np.isin(part_of_vertex, list(keep))
    # A single-object base mesh has no provenance to speak of: take everything.
    return mask if mask.any() else np.ones(len(part_of_vertex), dtype=bool)


def load_motion(path: Path):
    before = {o.name for o in bpy.data.objects}
    bpy.ops.import_scene.fbx(filepath=str(path), automatic_bone_orientation=False,
                             ignore_leaf_bones=False, use_anim=True)
    fresh = [o for o in bpy.data.objects if o.name not in before]
    arms = [o for o in fresh if o.type == "ARMATURE" and o.animation_data
            and o.animation_data.action]
    if not arms:
        raise SystemExit(f"{path.name}: no animated armature in the FBX")
    missing = [b for b in set(BONE_MAP.values()) if b not in arms[0].data.bones]
    if missing:
        raise SystemExit(f"{path.name}: not a Mixamo rig, missing {missing[:4]}")
    return arms[0], fresh


def discard(objects) -> None:
    actions = set()
    for obj in objects:
        if obj.animation_data and obj.animation_data.action:
            actions.add(obj.animation_data.action)
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        if isinstance(data, bpy.types.Armature) and data.users == 0:
            bpy.data.armatures.remove(data)
    for action in actions:
        # Unconditionally: export_animation_mode='ACTIONS' tries *every* action
        # in the file against the rig, and a leftover mixamorig action both
        # spams warnings and can land in the GLB.
        bpy.data.actions.remove(action)


def condition_weights(body, arm, names, rounds: int, prune: bool) -> dict:
    w = read_weights(body, names)
    heads = np.array([list(arm.data.bones[n].head_local) for n in names])
    tails = np.array([list(arm.data.bones[n].tail_local) for n in names])
    co = np.empty(len(body.data.vertices) * 3)
    body.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    dist = point_segment_distance(co, heads, tails)
    removed = 0
    if prune:
        w, removed = prune_long_range(w, dist)
    if rounds:
        nbr, starts, counts = mesh_adjacency(body)
        w = smooth_weights(w, nbr, starts, counts, factor=0.5, rounds=rounds)
    w = limit_influences(w)
    write_weights(body, names, w)
    total = w.sum(axis=1)
    return dict(smoothing_rounds=rounds, pruned_influences=removed,
                unweighted_vertices=int((total <= 1e-6).sum()),
                max_influences=int((w > WEIGHT_EPS).sum(axis=1).max()),
                weight_sum_error=round(float(np.abs(total - 1.0).max()), 6))


def run(args) -> dict:
    base_path, origin = find_base_mesh()
    log(f"base character: {base_path.relative_to(REPO)}  [{origin}]")
    body, arm, part_of_vertex, part_names, height = load_base_character(base_path)
    names = RIG_BONES
    log(f"  mesh {len(body.data.vertices):,} verts | rig {len(arm.data.bones)} bones "
        f"| height {height:.3f} m")
    assert {b.name for b in arm.data.bones} == set(names), "rig is not the canonical 27"

    body_mask = body_part_mask(part_of_vertex, part_names)
    log(f"  body region: {int(body_mask.sum()):,} of {len(body_mask):,} vertices")

    # --- weights -------------------------------------------------------------
    weight_info = condition_weights(body, arm, names, rounds=args.smooth_rounds,
                                    prune=not args.no_prune)
    log(f"  weights: pruned {weight_info['pruned_influences']} long-range influences, "
        f"{args.smooth_rounds} smoothing rounds, max {weight_info['max_influences']} influences")

    target = Target(arm, height)
    co = np.empty(len(body.data.vertices) * 3)
    body.data.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    # Ground measurements must ignore hair, eyelashes and other accessories:
    # an un-simulated ponytail swings 70 mm below the body in a Dive Roll and
    # would otherwise drive the whole clip's floor datum.
    low = co[:, 2] < 0.35 * height / TARGET_HEIGHT
    contact_subset = np.nonzero(body_mask & (low | (np.arange(len(co)) % 12 == 0)))[0]

    def foot_skinner(side: str) -> Skinner:
        w = read_weights(body, names)
        dom = np.argmax(w, axis=1)
        wanted = {names.index(f"ANKLE_{side}"), names.index(f"FOOT_{side}")}
        idx = np.nonzero(np.isin(dom, list(wanted)) & body_mask)[0]
        if idx.size < 10:
            idx = np.nonzero((w[:, names.index(f"ANKLE_{side}")] > 0.3) & body_mask)[0]
        return Skinner(body, arm, names, idx)

    skinner = Skinner(body, arm, names, contact_subset)
    full = Skinner(body, arm, names)
    feet = {s: foot_skinner(s) for s in ("L", "R")}
    log(f"  contact sample {len(contact_subset):,} verts | "
        f"feet L={len(feet['L'].subset)} R={len(feet['R'].subset)}")

    wanted = {c["name"] for c in CLIPS}
    if args.quick:
        selected = [c for c in CLIPS if c["name"] in QUICK_CLIPS]
    elif args.clips:
        unknown = set(args.clips) - wanted
        if unknown:
            raise SystemExit(f"unknown clip(s): {sorted(unknown)}")
        selected = [c for c in CLIPS if c["name"] in set(args.clips)]
    else:
        selected = list(CLIPS)

    # --- phase A: condition the skinning against the worst poses -------------
    edges = all_edges(body)
    body_edge = body_mask[edges[:, 0]] & body_mask[edges[:, 1]]
    stress = [c for c in CLIPS if c["name"] in STRESS_CLIPS
              and (MOTION_DIR / c["file"]).is_file()]
    deform = {"skipped": True}
    if stress and not args.no_deform_check:
        log(f"conditioning weights against {len(stress)} stress clips "
            f"({len(edges):,} edges, every edge measured)")
        best = None
        for attempt in range(args.max_weight_rounds + 1):
            poses = []
            for clip in stress:
                src, fresh = load_motion(MOTION_DIR / clip["file"])
                result = retarget_clip(clip, src, target, skinner, feet, ik=False)
                poses += spread(result["poses"], 14)
                discard(fresh)
            deform = measure_deformation(full, edges, body_edge, poses)
            b, a = deform["body_shell"], deform["accessory_shells"]
            log(f"  round {attempt}: body {b['max_edge_stretch']:.3f}x / "
                f"{b['max_edge_growth_mm']:.1f}mm | accessories "
                f"{a['max_edge_stretch']:.3f}x / {a['max_edge_growth_mm']:.1f}mm")
            score = (b["max_edge_stretch"], b["max_edge_growth_mm"])
            if best is None or score < best[0]:
                best = (score, read_weights(body, names), deform, attempt)
            ok = deform_ok(deform)
            if ok or attempt == args.max_weight_rounds:
                break
            if attempt and score > best[0]:
                # More smoothing is making it worse; stop and keep the best.
                log("  -> smoothing is regressing, keeping the best round")
                break
            weight_info = condition_weights(body, arm, names, rounds=2, prune=False)
            skinner = Skinner(body, arm, names, contact_subset)
            full = Skinner(body, arm, names)
            feet = {s: foot_skinner(s) for s in ("L", "R")}
            log("  -> extra weight smoothing and retry")
        if best is not None and best[2] is not deform:
            write_weights(body, names, best[1])
            skinner = Skinner(body, arm, names, contact_subset)
            full = Skinner(body, arm, names)
            feet = {s: foot_skinner(s) for s in ("L", "R")}
            deform = best[2]
            log(f"  restored the weights from round {best[3]}")
        deform["rounds_used"] = best[3] if best else 0

    # --- phase B: retarget everything ----------------------------------------
    log(f"retargeting {len(selected)} clips")
    clips_out, clip_stats = [], []
    for clip in selected:
        path = MOTION_DIR / clip["file"]
        if not path.is_file():
            log(f"  !! missing {clip['file']} -- skipped")
            continue
        src, fresh = load_motion(path)
        result = retarget_clip(clip, src, target, skinner, feet, ik=not args.no_ik)
        discard(fresh)
        stats = result.pop("stats")
        stats["name"] = clip["name"]
        stats["source"] = clip["file"]
        stats["loop"] = result["loop"]
        stats["root"] = result["root_mode"]
        clip_stats.append(stats)
        result.pop("poses")
        clips_out.append(result)
        log(f"  {clip['name']:<14s} {stats['frame_count']:>3d}f  "
            f"floor{stats['floor_shift']:+.3f}  minZ {stats['min_z']:+.4f}  "
            f"foot float {stats['contact_float_m'] * 1000:5.1f}mm  "
            f"qdot {stats['min_quaternion_dot']:.3f}")

    if not clips_out:
        raise SystemExit("no clips were retargeted")

    bpy.ops.object.select_all(action="DESELECT")
    actions = []
    for clip in clips_out:
        action, slot = build_action(arm, clip)
        actions.append((action, slot))
    assign_action(arm, actions[0][0], actions[0][1])
    log(f"built {len(actions)} actions")

    # --- clothing -------------------------------------------------------------
    weights = read_weights(body, names)
    garments, garment_stats = [], []
    for key, cfg in GARMENTS.items():
        garment, info = build_garment(body, arm, key, cfg, weights, names,
                                      body_mask, args.clothing_mode, height)
        garments.append(garment)
        garment_stats.append(info)
        log(f"  {key:<16s} {info['vertices']:>6,} verts  offset "
            f"{info['min_offset_mm']:.1f}-{info['max_offset_mm']:.1f} mm  "
            f"weights identical: {info['weights_identical_to_body']}")

    # --- body material --------------------------------------------------------
    if not body.data.materials:
        body.data.materials.append(make_material("Body_Skin", SKIN_COLOUR, 0.72))

    # --- export ---------------------------------------------------------------
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_CLOTHING.mkdir(parents=True, exist_ok=True)
    for g in garments:
        g.hide_set(True)
        g.hide_viewport = True
    player_path = OUT_DIR / PLAYER_GLB
    export_glb(player_path, [arm, body])
    for g in garments:
        g.hide_viewport = False
        g.hide_set(False)
    body.hide_viewport = True
    for g in garments:
        others = [x for x in garments if x is not g]
        for o in others:
            o.hide_viewport = True
        export_glb(OUT_CLOTHING / f"{g.name}.glb", [arm, g])
        for o in others:
            o.hide_viewport = False
    body.hide_viewport = False

    summary = {"player_animated.glb": glb_summary(player_path)}
    for g in garments:
        summary[f"clothing/{g.name}.glb"] = glb_summary(OUT_CLOTHING / f"{g.name}.glb")

    report = dict(
        generated_by="tools/retarget_animations.py",
        blender=bpy.app.version_string,
        base_mesh=dict(path=str(base_path.relative_to(REPO)), origin=origin,
                       height_m=round(height, 4),
                       vertices=len(body.data.vertices),
                       triangles=sum(len(p.vertices) - 2 for p in body.data.polygons),
                       body_region_vertices=int(body_mask.sum())),
        rig=dict(bones=len(arm.data.bones), names=sorted(names), root=ROOT_BONE,
                 bone_map=BONE_MAP),
        skinning=weight_info,
        deformation=deform,
        clips=clip_stats,
        clothing=garment_stats,
        outputs=summary,
        limits=dict(body_stretch=BODY_STRETCH_LIMIT, edge_squash=EDGE_SQUASH_LIMIT,
                    body_growth_m=BODY_GROWTH_LIMIT, min_rest_edge_m=MIN_REST_EDGE,
                    accessory_stretch=ACCESSORY_STRETCH_LIMIT,
                    accessory_growth_m=ACCESSORY_GROWTH_LIMIT,
                    floor_below_m=FLOOR_TOL_BELOW, floor_above_m=FLOOR_TOL_ABOVE,
                    contact_float_m=CONTACT_FLOAT_LIMIT),
    )
    # Write the report *before* verifying: a failing run is precisely when the
    # measured numbers are worth keeping, and verify() raises.
    (OUT_DIR / REPORT_JSON).write_text(json.dumps(report, indent=2) + "\n")
    verify(report)

    if not args.no_mirror:
        MIRROR_DIR.mkdir(parents=True, exist_ok=True)
        (MIRROR_DIR / "clothing").mkdir(parents=True, exist_ok=True)
        shutil.copy2(player_path, MIRROR_DIR / PLAYER_GLB)
        shutil.copy2(OUT_DIR / REPORT_JSON, MIRROR_DIR / REPORT_JSON)
        for g in garments:
            shutil.copy2(OUT_CLOTHING / f"{g.name}.glb",
                         MIRROR_DIR / "clothing" / f"{g.name}.glb")
        log(f"mirrored into {MIRROR_DIR.relative_to(REPO)}")

    if args.blend:
        bpy.ops.wm.save_as_mainfile(filepath=str(Path(args.blend).resolve()))
        log(f"saved {args.blend}")
    return report


def verify(report: dict) -> None:
    """Every promise this script makes, asserted against measured numbers."""
    problems = []
    for clip in report["clips"]:
        if clip["min_z"] < -FLOOR_TOL_BELOW:
            problems.append(f"{clip['name']}: sinks {-clip['min_z'] * 1000:.1f} mm through the floor")
        if clip["min_z"] > FLOOR_TOL_ABOVE:
            problems.append(f"{clip['name']}: floats {clip['min_z'] * 1000:.1f} mm above the floor")
        if clip["contact_float_m"] > CONTACT_FLOAT_LIMIT:
            problems.append(f"{clip['name']}: planted foot floats "
                            f"{clip['contact_float_m'] * 1000:.1f} mm")
        if clip["min_quaternion_dot"] < 0.0:
            problems.append(f"{clip['name']}: quaternion flip (dot {clip['min_quaternion_dot']})")
    d = report["deformation"]
    if not d.get("skipped"):
        problems += deform_problems(d)
    s = report["skinning"]
    if s["unweighted_vertices"]:
        problems.append(f"{s['unweighted_vertices']} unweighted vertices")
    if s["max_influences"] > MAX_INFLUENCES:
        problems.append(f"{s['max_influences']} influences per vertex (limit {MAX_INFLUENCES})")
    for garment in report["clothing"]:
        if not garment["weights_identical_to_body"]:
            problems.append(f"{garment['name']}: weights differ from the body")
    expected = {c["name"] for c in report["clips"]}
    for path, info in report["outputs"].items():
        if set(info["animations"]) != expected:
            problems.append(f"{path}: animations {sorted(set(info['animations']) ^ expected)} differ")
        if info["joint_count"] != 27:
            problems.append(f"{path}: {info['joint_count']} joints, expected 27")
        if info["images"]:
            problems.append(f"{path}: {info['images']} embedded images, expected 0")
    report["verified"] = not problems
    report["problems"] = problems
    if problems:
        for p in problems:
            log(f"  FAIL  {p}")
        raise SystemExit(f"{len(problems)} validation failure(s)")
    log("all validation checks passed")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--clips", nargs="*", metavar="NAME",
                        help="only retarget these clips (default: all curated clips)")
    parser.add_argument("--quick", action="store_true",
                        help=f"retarget only {', '.join(QUICK_CLIPS)}")
    parser.add_argument("--clothing-mode", choices=("shell", "scale"), default="shell",
                        help="shell: offset 5%% of local limb radius (default). "
                             "scale: literal 1.05x about the origin")
    parser.add_argument("--smooth-rounds", type=int, default=2,
                        help="initial Laplacian weight smoothing rounds (default 2)")
    parser.add_argument("--max-weight-rounds", type=int, default=3,
                        help="extra smoothing retries if extreme poses stretch (default 3)")
    parser.add_argument("--no-prune", action="store_true",
                        help="keep long-range bone influences")
    parser.add_argument("--no-ik", action="store_true", help="disable foot-contact IK")
    parser.add_argument("--no-deform-check", action="store_true",
                        help="skip the stress-pose deformation pass")
    parser.add_argument("--no-mirror", action="store_true",
                        help="do not copy outputs into docs/models/characters/")
    parser.add_argument("--blend", metavar="PATH", help="also save a .blend of the result")
    parser.add_argument("--list-clips", action="store_true")
    args = parser.parse_args(argv if argv is not None else argv_after_dashes())

    if args.list_clips:
        for c in CLIPS:
            mark = "ok " if (MOTION_DIR / c["file"]).is_file() else "MISS"
            print(f"  [{mark}] {c['name']:<14s} <- {c['file']}")
        return

    report = run(args)
    log(f"player   {report['outputs']['player_animated.glb']['bytes'] / 1024:,.0f} KB, "
        f"{report['outputs']['player_animated.glb']['animation_count']} animations")
    for key, info in report["outputs"].items():
        if key != "player_animated.glb":
            log(f"{key.split('/')[-1]:<22s} {info['bytes'] / 1024:,.0f} KB")


def argv_after_dashes() -> list[str]:
    """Works both as `python tools/x.py ...` and `blender -b --python x.py -- ...`."""
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]


if __name__ == "__main__":
    main()
