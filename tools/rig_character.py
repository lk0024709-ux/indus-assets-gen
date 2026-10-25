#!/usr/bin/env python3
"""Rig + animate the player character with bpy (no external plugins).

Takes the already-shipped static mesh and produces a fully skinned, animated
character:

    docs/models/characters/player_tactical.glb   (static mesh, 1.80 m)
        -> docs/models/characters/player_animated.glb
           armature + skinned mesh + "Idle" + "Walk" animations

Everything is done with stock ``bpy``: no add-ons, no plugins, no external
rigging tools. Bone positions are computed from the 1.80 m height, and the
animation curves are generated from ``math.sin`` / ``math.cos``.

Why some bone coordinates differ from the brief
-----------------------------------------------
The brief supplies arm bones ``(0.2, 0, 1.4) -> (0.4, 0, 1.1)``. Measured
against the actual mesh, that tail sits **0.157 m outside** the geometry: the
character's widest point is ``|x| = 0.265`` and its arms hang almost straight
down (the sleeve centreline is at ``x ≈ 0.18-0.20`` from shoulder to wrist).
A bone pointing 45° out of the body puts the shoulder and the arm geometry at
roughly equal distance from two different bones, so the weights split and the
arm drags the torso with it.

Every *joint* the brief specifies is kept exactly (shoulder ``(±0.2, 0, 1.4)``,
hip ``(±0.15, 0, 0.9)``, and the whole spine chain). Only the *tails* of the
arm bones are re-aimed down the actual limb, and the lower arms / hands /
lower legs / feet are added -- which the brief explicitly allows ("add them if
it helps the deformation"). Pass ``--rig spec`` to reproduce the brief's eight
bones verbatim.

Binding
-------
The brief says ``bpy.ops.object.parent_set(type='ARMATURE_AUTO')``. That is
what this script runs first, but on this mesh Blender's bone-heat solver
**fails silently**: the operator returns ``FINISHED`` and creates the vertex
groups while assigning *zero* weight, because the character is a set of
disconnected shells (head, hands, shoes, hair are separate islands). The
script detects that (total weight == 0) and falls back to a deterministic
distance-to-bone-segment skinning solver, then asserts every vertex is
weighted and normalised.

Run:
    pip install bpy
    python tools/rig_character.py [--rig anatomical|spec] [--preview DIR]
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
CHAR_DIR = os.path.join(REPO_ROOT, "docs", "models", "characters")
SRC_GLB = os.path.join(CHAR_DIR, "player_tactical.glb")
OUT_GLB = os.path.join(CHAR_DIR, "player_animated.glb")

HEIGHT = 1.80          # metres — every coordinate below is derived from this
FPS = 30
IDLE_FRAMES = (1, 30)  # breathing loop
WALK_FRAMES = (1, 30)  # stride loop
ARM_SWING_DEG = 30.0
LEG_SWING_DEG = 30.0
BREATH_RISE = 0.02     # metres, chest lift at mid-breath
HIP_BOB = 0.070        # metres, hips drop at the stride extremes (tuned: keeps the planted foot on the ground)
MAX_INFLUENCES = 4     # glTF-friendly
WEIGHT_FALLOFF = 4.0   # exponent for the inverse-distance solver

# ---------------------------------------------------------------------------
# Skeleton — Blender is Z-up and the character faces -Y.
#
# Every entry: name -> (head, tail, parent, note). "brief" entries reproduce
# the brief's numbers exactly; "fitted" entries are measured from the mesh.
# ---------------------------------------------------------------------------
def skeleton(rig: str) -> list[tuple[str, tuple, tuple, str | None, str]]:
    arms_tail = {
        # brief: (0.4, 0, 1.1) — 0.157 m outside the mesh
        "spec": (0.4, 0.0, 1.1),
        "anatomical": (0.205, 0.0, 1.10),   # elbow, on the sleeve centreline
    }[rig]

    bones: list[tuple[str, tuple, tuple, str | None, str]] = [
        ("Hips",  (0.0, 0.0, 0.9), (0.0, 0.0, 1.0), None,    "brief"),
        ("Spine", (0.0, 0.0, 1.0), (0.0, 0.0, 1.2), "Hips",  "brief"),
        ("Chest", (0.0, 0.0, 1.2), (0.0, 0.0, 1.4), "Spine", "brief"),
        ("Head",  (0.0, 0.0, 1.5), (0.0, 0.0, 1.8), "Chest", "brief"),
        ("UpperArm.L",  (0.2, 0.0, 1.4), arms_tail,   "Chest", "brief head" if rig == "anatomical" else "brief"),
        ("UpperArm.R", (-0.2, 0.0, 1.4), _mirror(arms_tail), "Chest", "brief head" if rig == "anatomical" else "brief"),
        ("UpperLeg.L",  (0.15, 0.0, 0.9), (0.15, 0.0, 0.5), "Hips", "brief"),
        ("UpperLeg.R", (-0.15, 0.0, 0.9), (-0.15, 0.0, 0.5), "Hips", "brief"),
    ]
    if rig == "anatomical":
        # Neck closes the brief's 0.1 m gap between Chest (tail 1.4) and
        # Head (head 1.5) so the head is not a floating island.
        bones.append(("Neck", (0.0, 0.0, 1.4), (0.0, 0.0, 1.5), "Chest", "added"))
        for side, x in (("L", 1.0), ("R", -1.0)):
            bones += [
                (f"LowerArm.{side}", (x * 0.205, 0.0, 1.10), (x * 0.210, 0.0, 0.86),
                 f"UpperArm.{side}", "added"),
                (f"Hand.{side}",     (x * 0.210, 0.0, 0.86), (x * 0.200, 0.0, 0.62),
                 f"LowerArm.{side}", "added"),
                (f"LowerLeg.{side}", (x * 0.130, 0.0, 0.48), (x * 0.160, 0.0, 0.10),
                 f"UpperLeg.{side}", "added"),
                (f"Foot.{side}",     (x * 0.160, 0.0, 0.10), (x * 0.190, -0.10, 0.03),
                 f"LowerLeg.{side}", "added"),
            ]
    return bones


def _mirror(p: tuple) -> tuple:
    return (-p[0], p[1], p[2])


# ---------------------------------------------------------------------------
# TASK 1 — mesh
# ---------------------------------------------------------------------------
def prepare_mesh():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=SRC_GLB)
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    if len(meshes) != 1:
        raise RuntimeError(f"Expected exactly one mesh, found {len(meshes)}")
    mesh = meshes[0]

    # TASK 1 — apply every transform so the mesh is in a clean identity frame.
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = mesh
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # origin must be bottom-centre (0, 0, 0)
    co = [v.co for v in mesh.data.vertices]
    min_z = min(v.z for v in co)
    cx = (max(v.x for v in co) + min(v.x for v in co)) * 0.5
    cy = (max(v.y for v in co) + min(v.y for v in co)) * 0.5
    if abs(min_z) > 1e-4 or abs(cx) > 1e-4 or abs(cy) > 1e-3:
        mesh.data.transform(Matrix.Translation((-cx, -cy, -min_z)))
        mesh.data.update()
        print(f"  re-centred mesh by ({-cx:+.4f}, {-cy:+.4f}, {-min_z:+.4f})")
    else:
        print("  origin already bottom-centre (0, 0, 0)")

    co = [v.co for v in mesh.data.vertices]
    height = max(v.z for v in co) - min(v.z for v in co)
    print(f"  mesh: {mesh.name} | {len(co):,} verts | {len(mesh.data.polygons):,} faces | "
          f"{len(mesh.data.materials)} materials | height {height:.4f} m | "
          f"minZ {min(v.z for v in co):.4f}")
    if abs(height - HEIGHT) > 0.01:
        raise RuntimeError(f"Mesh height {height:.4f} m is not {HEIGHT} m")
    return mesh


# ---------------------------------------------------------------------------
# TASK 2 — armature
# ---------------------------------------------------------------------------
def build_armature(spec):
    arm_data = bpy.data.armatures.new("PlayerRigData")
    arm = bpy.data.objects.new("PlayerRig", arm_data)
    bpy.context.scene.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    arm.select_set(True)

    bpy.ops.object.mode_set(mode="EDIT")
    eb = arm_data.edit_bones
    for name, head, tail, parent, note in spec:
        bone = eb.new(name)
        bone.head = Vector(head)
        bone.tail = Vector(tail)
        bone.use_connect = False
        bone.roll = 0.0
        if parent:
            bone.parent = eb[parent]
    bpy.ops.object.mode_set(mode="OBJECT")

    print(f"  armature '{arm.name}': {len(arm_data.bones)} bones")
    for name, head, tail, parent, note in spec:
        b = arm_data.bones[name]
        print(f"    {name:12s} head={_fmt(b.head_local)} tail={_fmt(b.tail_local)} "
              f"len={b.length:.3f} parent={parent or '-':12s} [{note}]")
    return arm


def _fmt(v) -> str:
    return f"({v[0]:+.3f}, {v[1]:+.3f}, {v[2]:+.3f})"


# ---------------------------------------------------------------------------
# TASK 3 — bind
# ---------------------------------------------------------------------------
def bind_auto(mesh, arm) -> float:
    """The brief's method: bpy.ops.object.parent_set(type='ARMATURE_AUTO')."""
    bpy.ops.object.select_all(action="DESELECT")
    mesh.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.parent_set(type="ARMATURE_AUTO")
    bpy.context.view_layer.update()
    total = sum(g.weight for v in mesh.data.vertices for g in v.groups)
    unweighted = sum(1 for v in mesh.data.vertices if not [g for g in v.groups if g.weight > 1e-5])
    print(f"  ARMATURE_AUTO -> finished | {len(mesh.vertex_groups)} vertex groups | "
          f"total weight {total:.2f} | unweighted verts {unweighted}/{len(mesh.data.vertices)}")
    return total, unweighted


def segment_distance(p: Vector, a: Vector, b: Vector) -> float:
    ab = b - a
    denom = ab.length_squared
    if denom < 1e-12:
        return (p - a).length
    t = max(0.0, min(1.0, (p - a).dot(ab) / denom))
    return (p - (a + ab * t)).length


def _chains(arm):
    """Group the armature's bones into anatomical chains that exist on this rig."""
    present = {b.name for b in arm.data.bones}

    def pick(names):
        return [n for n in names if n in present]

    spine = pick(["Hips", "Spine", "Chest", "Neck"])
    head = pick(["Head"])
    arms = {s: pick([f"UpperArm.{s}", f"LowerArm.{s}", f"Hand.{s}"]) for s in ("L", "R")}
    legs = {s: pick([f"UpperLeg.{s}", f"LowerLeg.{s}", f"Foot.{s}"]) for s in ("L", "R")}
    return spine, head, arms, legs


def candidate_bones(p: Vector, material: str, chains) -> list[str]:
    """Which bones a vertex is *allowed* to be weighted to.

    Pure distance-to-bone is not enough on this character: the hands hang at
    |x| ~= 0.21 right beside the thigh bones at |x| = 0.15, and the crotch sits
    equidistant from both legs. Without this filter those vertices pick up the
    wrong bone and tear into spikes when the rig moves.

    The mesh's own material groups give reliable semantic boundaries, so we use
    them: shoes only follow feet, hair/eyes only follow the head, low skin is
    hands (arm chain only), trousers are legs + hips, and everything else can
    reach the spine plus the arm chain on its own side.
    """
    spine, head, arms, legs = chains
    side = "L" if p.x >= 0.0 else "R"
    other = "R" if side == "L" else "L"
    # Near the centre line, let both sides compete so the seam blends.
    near_centre = abs(p.x) < 0.05

    if material in ("Hair", "Eyes"):
        return head + spine[-1:] if head else spine
    if material == "Skin":
        if p.z > 1.45:                      # face, neck, scalp
            return head + spine[-1:] if head else spine
        if p.z < 0.95:                      # hands
            return arms[side] if arms[side] else spine
        return spine + arms[side]           # neck / forearms of a bare-armed model
    if material == "Shoes":
        return legs[side] if legs[side] else spine

    if material == "Pants":
        allowed = list(spine) + legs[side]
        if near_centre:
            allowed += legs[other]
        return allowed

    # Forearm region: the sleeve below the elbow, out on the arm. It must use
    # exactly the same bone chain as the hand shell, otherwise the sleeve and
    # the wrist resolve to different bones and tear apart at the wrist.
    if abs(p.x) > 0.13 and p.z < 1.10 and arms[side]:
        return arms[side]

    # Shirt, tie, details, anything else: torso plus the arm chain on its side.
    allowed = list(spine) + arms[side]
    if near_centre:
        allowed += arms[other]
    # Deliberately NOT letting the shirt hem follow the legs: the jacket tails
    # hang over the thighs, and weighting them to the leg swings a visible dark
    # flap out of the hip at every stride. They ride with the torso instead.
    return allowed


def bind_geometric(mesh, arm) -> None:
    """Deterministic inverse-distance skinning — no bone-heat solver involved.

    Robust on this character because it is a set of disconnected shells, which
    is exactly what breaks Blender's heat weighting. Each vertex is restricted
    to an anatomically sane set of bones (:func:`candidate_bones`), then takes
    the closest ``MAX_INFLUENCES`` of those, weighted by 1/d^WEIGHT_FALLOFF and
    normalised -- so joints blend smoothly across the segment ends.
    """
    for vg in list(mesh.vertex_groups):
        mesh.vertex_groups.remove(vg)

    chains = _chains(arm)
    bones = {b.name: (b.head_local.copy(), b.tail_local.copy()) for b in arm.data.bones}
    groups = {name: mesh.vertex_groups.new(name=name) for name in bones}

    # Material of each vertex (a vertex can belong to several; first wins,
    # which is fine because the parts of this character do not overlap).
    mat_names = [m.name if m else "" for m in mesh.data.materials]
    vert_material = [""] * len(mesh.data.vertices)
    for poly in mesh.data.polygons:
        name = mat_names[poly.material_index] if poly.material_index < len(mat_names) else ""
        for vi in poly.vertices:
            if not vert_material[vi]:
                vert_material[vi] = name

    for vert in mesh.data.vertices:
        p = vert.co
        allowed = candidate_bones(p, vert_material[vert.index], chains)
        if not allowed:
            allowed = list(bones)
        scored = []
        for name in allowed:
            head, tail = bones[name]
            scored.append((segment_distance(p, head, tail), name))
        scored.sort(key=lambda t: t[0])
        scored = scored[:MAX_INFLUENCES]
        weights = [(1.0 / ((d + 0.02) ** WEIGHT_FALLOFF), name) for d, name in scored]
        total = sum(w for w, _ in weights)
        for w, name in weights:
            groups[name].add([vert.index], w / total, "REPLACE")

    # parent + modifier, exactly what parent_set(ARMATURE_AUTO) would leave behind
    mesh.parent = arm
    mesh.matrix_parent_inverse = arm.matrix_world.inverted()
    arm_mods = [m for m in mesh.modifiers if m.type == "ARMATURE"]
    if arm_mods:
        arm_mods[0].object = arm
    else:
        mod = mesh.modifiers.new("Armature", "ARMATURE")
        mod.object = arm
    print(f"  geometric skinning -> {len(mesh.vertex_groups)} vertex groups, "
          f"<= {MAX_INFLUENCES} influences/vertex, material-aware bone restriction")


def verify_weights(mesh, arm) -> dict:
    bone_names = {b.name for b in arm.data.bones}
    unweighted, over_limit, bad_sum = 0, 0, 0
    per_group = {name: 0 for name in bone_names}
    for v in mesh.data.vertices:
        groups = [g for g in v.groups if g.weight > 1e-5]
        if not groups:
            unweighted += 1
            continue
        if len(groups) > MAX_INFLUENCES:
            over_limit += 1
        if abs(sum(g.weight for g in groups) - 1.0) > 1e-3:
            bad_sum += 1
        for g in groups:
            name = mesh.vertex_groups[g.group].name
            if name in per_group:
                per_group[name] += 1

    print("  weight check:")
    for name in sorted(per_group):
        print(f"    {name:12s} {per_group[name]:5d} verts")
    empty = [n for n, c in per_group.items() if c == 0]
    print(f"    unweighted verts={unweighted} over-{MAX_INFLUENCES}-influence={over_limit} "
          f"unnormalised={bad_sum} bones-with-no-verts={empty}")
    if unweighted:
        raise RuntimeError(f"{unweighted} vertices have no weights — mesh would not deform")
    if bad_sum:
        raise RuntimeError(f"{bad_sum} vertices have unnormalised weights")
    if empty:
        raise RuntimeError(f"Bones with no vertices: {empty}")
    return {"unweighted": unweighted, "per_group": per_group}


# ---------------------------------------------------------------------------
# TASK 4 — animations
# ---------------------------------------------------------------------------
def new_action(arm, name: str):
    act = bpy.data.actions.new(name)
    act.use_fake_user = True
    if arm.animation_data is None:
        arm.animation_data_create()
    arm.animation_data.action = act
    # Blender 4.4+ slotted actions: bind a slot so keyframes have somewhere to go.
    if hasattr(arm.animation_data, "action_slot") and act.slots:
        arm.animation_data.action_slot = act.slots[0]
    return act


def action_fcurves(action):
    """All f-curves of an action, across Blender's old and slotted layouts.

    Blender <= 4.3 keeps them on ``action.fcurves``. Blender 4.4+ replaced that
    with layered actions: layers -> strips -> channelbags -> fcurves. This
    helper walks whichever layout the running Blender has.
    """
    if hasattr(action, "fcurves"):
        return list(action.fcurves)
    curves = []
    for layer in getattr(action, "layers", []):
        for strip in getattr(layer, "strips", []):
            for bag in getattr(strip, "channelbags", []):
                curves.extend(bag.fcurves)
    return curves


def prepare_pose(arm) -> None:
    for pb in arm.pose.bones:
        pb.rotation_mode = "XYZ"
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.location = (0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)


def reset_pose(arm) -> None:
    """Clear every pose channel back to rest.

    Important before evaluating or exporting an action: Blender only overrides
    the channels an action actually animates, so leftovers from a previously
    applied action persist. The Idle clip lifts the Chest by 20 mm; without this
    reset that lift stays in the pose when Walk is applied, and because the
    exporter samples the evaluated pose, the offset would be baked into the
    exported Walk clip as a permanent 20 mm chest lift.
    """
    for pb in arm.pose.bones:
        pb.location = (0.0, 0.0, 0.0)
        pb.rotation_euler = (0.0, 0.0, 0.0)
        pb.rotation_quaternion = (1.0, 0.0, 0.0, 0.0)
        pb.scale = (1.0, 1.0, 1.0)


def build_idle(arm) -> dict:
    """30-frame breathing loop: chest rises BREATH_RISE at frame 15.

    Note on the axis: the brief says "move Chest up on the Z-axis", but
    ``pose_bone.location`` is in **bone-local** space, where a bone's Y runs
    head->tail. The Chest bone points straight up, so bone-local Y *is* world
    Z: ``location = (0, BREATH_RISE, 0)`` lifts the chest 2 cm in world space.
    Setting ``location.z`` instead would slide the chest forward, not up.
    """
    action = new_action(arm, "Idle")
    chest = arm.pose.bones["Chest"]
    start, end = IDLE_FRAMES
    mid = (start + end) // 2

    keys = {start: 0.0, mid: BREATH_RISE, end: 0.0}
    for frame, rise in keys.items():
        chest.location = (0.0, rise, 0.0)
        chest.keyframe_insert(data_path="location", frame=frame)

    # Gentle arm settle so the idle is not perfectly stiff.
    for side, sign in (("L", 1.0), ("R", -1.0)):
        name = f"UpperArm.{side}"
        if name not in arm.pose.bones:
            continue
        pb = arm.pose.bones[name]
        for frame, deg in ((start, 0.0), (mid, 2.0 * sign), (end, 0.0)):
            pb.rotation_euler = (math.radians(deg), 0.0, 0.0)
            pb.keyframe_insert(data_path="rotation_euler", frame=frame)

    curves = action_fcurves(action)
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
    print(f"  Idle: frames {start}-{end}, chest lift {BREATH_RISE * 1000:.0f} mm at frame {mid}, "
          f"{len(curves)} f-curves")
    return {"name": "Idle", "frames": [start, end], "fcurves": len(curves)}


def build_walk(arm) -> dict:
    """30-frame stride loop driven by cos() for the swing and sin() for the bob.

    Frame 1 and frame 30 are identical (the loop seam) and frame 15 is the
    exact reverse, matching the brief. A cosine over a half period of 14
    frames puts +1 at f1, -1 at f15 and +1 again at f30, so the specified
    frame values land exactly while every in-between frame follows the same
    trig curve. Values are baked on every frame so the exported curve is a
    true cosine instead of a bezier approximation of three keys.

    Sign convention (measured, not assumed): a bone pointing down with roll 0
    swings its tail toward +Y for +X rotation, and the character faces -Y. So
    -X rotation = limb forward. The brief's frame 1 (arm L +30 = back, leg L
    -30 = forward) is therefore correct contralateral gait.
    """
    action = new_action(arm, "Walk")
    start, end = WALK_FRAMES
    half = (end - start) / 2.0        # 14 frames -> half a cycle

    # brief frame 1: UpperArm.L +30, UpperArm.R -30, UpperLeg.L -30, UpperLeg.R +30
    swing = {
        "UpperArm.L": ARM_SWING_DEG,
        "UpperArm.R": -ARM_SWING_DEG,
        "UpperLeg.L": -LEG_SWING_DEG,
        "UpperLeg.R": LEG_SWING_DEG,
    }
    # Knee follow-through, quarter cycle behind the hip.
    #
    # Deliberately NOT animated at the elbow: the hands are separate mesh
    # shells, so any extra elbow rotation swings them away from the sleeve and
    # tears a visible gap at the wrist. The knee is safe because the trouser
    # leg is one continuous tube from hip to ankle.
    follow = {
        "LowerLeg.L": -22.0, "LowerLeg.R": -22.0,
    }

    hips = arm.pose.bones["Hips"]
    frames = list(range(start, end + 1))
    for frame in frames:
        t = (frame - start) / (end - start)        # 0 .. 1 over the loop
        phase = math.cos(math.pi * (frame - start) / half)   # +1 f1, -1 f15, +1 f30

        for name, amp in swing.items():
            pb = arm.pose.bones.get(name)
            if pb is None:
                continue
            pb.rotation_euler = (math.radians(amp * phase), 0.0, 0.0)
            pb.keyframe_insert(data_path="rotation_euler", frame=frame)

        # Ankle counter-rotation keeps the soles roughly level instead of
        # pointing them at the floor as the leg swings.
        for side, leg_amp in (("L", swing["UpperLeg.L"]), ("R", swing["UpperLeg.R"])):
            foot = arm.pose.bones.get(f"Foot.{side}")
            if foot is not None:
                foot.rotation_euler = (math.radians(-leg_amp * phase * 0.55), 0.0, 0.0)
                foot.keyframe_insert(data_path="rotation_euler", frame=frame)

        for name, amp in follow.items():
            pb = arm.pose.bones.get(name)
            if pb is None:
                continue
            lead = math.cos(math.pi * (frame - start) / half - math.pi * 0.25)
            pb.rotation_euler = (math.radians(amp * lead), 0.0, 0.0)
            pb.keyframe_insert(data_path="rotation_euler", frame=frame)

        # Hip bob, driven by sin(). A straight leg swung by 30 deg is
        # 0.8 * (1 - cos 30) = 0.107 m shorter vertically, so without this the
        # feet float ~14 cm off the ground at the stride extremes. Dropping the
        # hips by ~0.09 m there puts the planted foot back down:
        #   t=0    (stride extreme) sin=0 -> hips low
        #   t=0.25 (legs passing)   sin=1 -> hips at rest height
        # It uses sin^2 so the bounce has two dips per stride and loops cleanly.
        bob = -HIP_BOB * (1.0 - math.sin(2.0 * math.pi * t) ** 2)
        hips.location = (0.0, bob, 0.0)
        hips.keyframe_insert(data_path="location", frame=frame)

        # Slight torso counter-rotation keeps the walk from looking robotic.
        chest = arm.pose.bones.get("Chest")
        if chest is not None:
            chest.rotation_euler = (0.0, 0.0, math.radians(4.0 * phase))
            chest.keyframe_insert(data_path="rotation_euler", frame=frame)

    curves = action_fcurves(action)
    for fc in curves:
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR"    # baked every frame; linear = exact
    print(f"  Walk: frames {start}-{end}, {len(frames)} baked frames, "
          f"arm +/-{ARM_SWING_DEG:.0f}deg, leg +/-{LEG_SWING_DEG:.0f}deg, "
          f"hip drop {HIP_BOB * 1000:.0f} mm at stride extremes, {len(curves)} f-curves")
    return {"name": "Walk", "frames": [start, end], "fcurves": len(curves)}


def sample_pose_world(arm, action, frame: int, bone: str) -> tuple:
    """World-space position of a bone's tail at a given frame (for verification)."""
    arm.animation_data.action = action
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    return tuple(arm.matrix_world @ arm.pose.bones[bone].tail)


# ---------------------------------------------------------------------------
# TASK 5 — export
# ---------------------------------------------------------------------------
def skin_follows(mesh, arm, action, frame: int, bone: str) -> tuple:
    """Centroid of the vertices most influenced by ``bone`` at ``frame``.

    Used to prove the skin still deforms after the temporary unparent in
    :func:`export_glb` -- a skinned mesh only needs its Armature modifier, but
    it is worth checking rather than assuming.
    """
    reset_pose(arm)
    arm.animation_data.action = action
    if hasattr(arm.animation_data, "action_slot") and action.slots:
        arm.animation_data.action_slot = action.slots[0]
    # Step through a neighbouring frame first: asking for the same frame twice
    # in a row can hand back a cached evaluated mesh, which makes this sampler
    # report phantom deformation drift after a render has just run.
    bpy.context.scene.frame_set(frame + 1 if frame < 30 else frame - 1)
    bpy.context.view_layer.update()
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg)
    me = ev.to_mesh()
    out = [ev.matrix_world @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    return out


def export_glb(arm, mesh, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    arm.select_set(True)
    mesh.select_set(True)
    bpy.context.view_layer.objects.active = arm

    # The mesh stays parented to the armature: that is what the brief asks for,
    # and what Blender's exporter wants ("Armature must be the parent of skinned
    # mesh"). This does produce one informational glTF validator notice,
    # NODE_SKINNED_MESH_NON_ROOT, because the skinned mesh node ends up under
    # the armature node rather than at the scene root -- which is exactly what
    # every stock Blender rigged export looks like, and what three.js, Godot,
    # Unity and Unreal all expect. It is accepted deliberately:
    #   * unparenting to silence it makes the exporter warn in the other
    #     direction and previously caused non-deterministic deformation;
    #   * export_hierarchy_flatten_objs does not change it (verified);
    #   * no engine is affected, because the armature node has an identity
    #     transform.

    kwargs = dict(
        filepath=path,
        export_format="GLB",          # critical
        export_animations=True,       # critical
        export_skins=True,            # critical
        export_yup=True,              # critical
        use_selection=True,
        export_apply=False,           # never apply modifiers on a skinned mesh
        export_materials="EXPORT",
        export_image_format="NONE",
        export_texcoords=False,
        export_normals=True,
        export_tangents=False,
        export_cameras=False,
        export_lights=False,
        export_extras=True,
        export_animation_mode="ACTIONS",
        export_bake_animation=False,
        export_force_sampling=True,
        export_optimize_animation_size=False,
        export_anim_single_armature=True,
        export_def_bones=False,
        export_rest_position_armature=True,
    )
    try:
        bpy.ops.export_scene.gltf(**kwargs)
    except TypeError as exc:
        print(f"  ! exporter rejected an option ({exc}); retrying with a minimal set")
        for key in list(kwargs):
            if key not in ("filepath", "export_format", "use_selection", "export_apply",
                           "export_animations", "export_skins", "export_yup",
                           "export_materials", "export_image_format", "export_normals"):
                kwargs.pop(key)
        bpy.ops.export_scene.gltf(**kwargs)
    if not os.path.isfile(path):
        raise RuntimeError(f"Export failed: {path} not written")


# ---------------------------------------------------------------------------
# Post-export: quaternion hemisphere continuity
# ---------------------------------------------------------------------------
def enforce_quaternion_continuity(path: str) -> int:
    """Make consecutive rotation keys share a hemisphere, in place.

    ``q`` and ``-q`` describe the same orientation, but Blender's exporter can
    emit the negated form for keys that sit either side of the rest pose. The
    result is a pair of neighbouring keys whose dot product is about -1: the
    same rotation numerically, yet a naive normalised-lerp player will spin the
    limb almost 180 degrees for one frame before snapping back. (three.js and
    Godot slerp correctly, but this makes the file safe for every player.)

    Floats are the same size in either form, so this patches the binary chunk
    in place -- no geometry or timing changes.
    """
    with open(path, "rb") as fh:
        data = bytearray(fh.read())
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(bytes(data[20:20 + json_len]))
    bin_start = 20 + json_len + 8            # skip BIN chunk header

    negations = 0
    for anim in gltf.get("animations", []):
        for channel in anim.get("channels", []):
            if channel["target"]["path"] != "rotation":
                continue
            sampler = anim["samplers"][channel["sampler"]]
            acc = gltf["accessors"][sampler["output"]]
            if acc["type"] != "VEC4" or acc["componentType"] != 5126:
                continue
            view = gltf["bufferViews"][acc["bufferView"]]
            stride = view.get("byteStride") or 16
            base = bin_start + view.get("byteOffset", 0) + acc.get("byteOffset", 0)

            prev = None
            for k in range(acc["count"]):
                off = base + k * stride
                q = list(struct.unpack_from("<4f", data, off))
                if prev is not None and sum(a * b for a, b in zip(prev, q)) < 0.0:
                    q = [-c for c in q]
                    struct.pack_into("<4f", data, off, *q)
                    negations += 1
                prev = q

    if negations:
        with open(path, "wb") as fh:
            fh.write(data)
    return negations


def count_quaternion_flips(path: str) -> int:
    """How many consecutive rotation keys still straddle the hemisphere."""
    with open(path, "rb") as fh:
        data = fh.read()
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_len])
    bin_start = 20 + json_len + 8
    flips = 0
    for anim in gltf.get("animations", []):
        for channel in anim.get("channels", []):
            if channel["target"]["path"] != "rotation":
                continue
            sampler = anim["samplers"][channel["sampler"]]
            acc = gltf["accessors"][sampler["output"]]
            view = gltf["bufferViews"][acc["bufferView"]]
            stride = view.get("byteStride") or 16
            base = bin_start + view.get("byteOffset", 0) + acc.get("byteOffset", 0)
            prev = None
            for k in range(acc["count"]):
                q = struct.unpack_from("<4f", data, base + k * stride)
                if prev is not None and sum(a * b for a, b in zip(prev, q)) < 0.0:
                    flips += 1
                prev = q
    return flips


# ---------------------------------------------------------------------------
# Verification — parse the written GLB back
# ---------------------------------------------------------------------------
def verify_glb(path: str) -> dict:
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"glTF":
        raise RuntimeError("Not a GLB file")
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_len])

    skins = gltf.get("skins", [])
    animations = gltf.get("animations", [])
    if not skins:
        raise RuntimeError("No skin in the GLB — the mesh is not skinned")
    if not animations:
        raise RuntimeError("No animations in the GLB")

    names = [a.get("name") for a in animations]
    for wanted in ("Idle", "Walk"):
        if wanted not in names:
            raise RuntimeError(f"Missing animation '{wanted}' (found {names})")

    joints = len(skins[0].get("joints", []))
    prims = [p for m in gltf.get("meshes", []) for p in m["primitives"]]
    skinned = [p for p in prims if "JOINTS_0" in p["attributes"] and "WEIGHTS_0" in p["attributes"]]
    if len(skinned) != len(prims):
        raise RuntimeError(f"{len(prims) - len(skinned)} primitive(s) lack JOINTS_0/WEIGHTS_0")

    # per-animation channel + duration detail
    detail = []
    for anim in animations:
        inputs = {s["input"] for s in anim["samplers"]}
        times = []
        for idx in inputs:
            acc = gltf["accessors"][idx]
            times.append(acc.get("max", [0])[0])
        targets = {c["target"]["path"] for c in anim["channels"]}
        detail.append({
            "name": anim.get("name"),
            "channels": len(anim["channels"]),
            "duration_s": round(max(times), 4) if times else 0.0,
            "paths": sorted(targets),
        })

    # Are the weights actually populated? Read WEIGHTS_0 for primitive 0.
    boff = 20 + json_len
    blen = struct.unpack("<I", data[boff:boff + 4])[0]
    bin_chunk = data[boff + 8:boff + 8 + blen]

    def read_accessor(index):
        acc = gltf["accessors"][index]
        bv = gltf["bufferViews"][acc["bufferView"]]
        comp = {5126: ("f", 4), 5125: ("I", 4), 5123: ("H", 2), 5121: ("B", 1)}[acc["componentType"]]
        n = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}[acc["type"]]
        stride = bv.get("byteStride") or comp[1] * n
        base = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
        out = []
        for k in range(acc["count"]):
            vals = struct.unpack_from("<" + comp[0] * n, bin_chunk, base + k * stride)
            out.append(vals)
        return out

    zero_weight_verts = 0
    total_verts = 0
    for prim in skinned:
        weights = read_accessor(prim["attributes"]["WEIGHTS_0"])
        total_verts += len(weights)
        for w in weights:
            if sum(w) < 1e-4:
                zero_weight_verts += 1
    if zero_weight_verts:
        raise RuntimeError(f"{zero_weight_verts}/{total_verts} exported vertices have zero weight")

    stats = {
        "bytes": len(data),
        "skins": len(skins),
        "joints": joints,
        "animations": detail,
        "animation_names": names,
        "primitives": len(prims),
        "skinned_primitives": len(skinned),
        "vertices": total_verts,
        "images": len(gltf.get("images", [])),
    }
    return stats


def report(stats: dict) -> None:
    print(f"  verified {os.path.basename(OUT_GLB)}: {stats['bytes'] / 1024:.1f} KB | "
          f"{stats['skins']} skin, {stats['joints']} joints | "
          f"{stats['skinned_primitives']}/{stats['primitives']} primitives skinned | "
          f"{stats['vertices']:,} verts all weighted | {stats['images']} textures")
    for anim in stats["animations"]:
        print(f"    animation '{anim['name']}': {anim['channels']} channels, "
              f"{anim['duration_s']:.3f} s, paths {anim['paths']}")


# ---------------------------------------------------------------------------
# Optional QA render
# ---------------------------------------------------------------------------
def render_frames(arm, mesh, action, frames, out_dir, tag, views=None):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 24
    scene.render.resolution_x = 480
    scene.render.resolution_y = 640
    if scene.world is None:
        scene.world = bpy.data.worlds.new("W")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.18, 0.20, 0.24, 1.0)
    bg.inputs[1].default_value = 1.0

    key = bpy.data.lights.new("Key", "AREA")
    key.energy = 420
    key.size = 3.0
    ko = bpy.data.objects.new("Key", key)
    scene.collection.objects.link(ko)
    ko.location = (2.6, -3.0, 3.4)
    ko.rotation_euler = (math.radians(52), 0, math.radians(40))
    fill = bpy.data.lights.new("Fill", "AREA")
    fill.energy = 160
    fill.size = 4.0
    fo = bpy.data.objects.new("Fill", fill)
    scene.collection.objects.link(fo)
    fo.location = (-3.0, -2.0, 1.8)
    fo.rotation_euler = (math.radians(78), 0, math.radians(-55))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 60
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    reset_pose(arm)
    arm.animation_data.action = action
    if hasattr(arm.animation_data, "action_slot") and action.slots:
        arm.animation_data.action_slot = action.slots[0]

    views = views or {
        "side": (3.4, 0.0, 1.0),
        "front": (0.0, -3.4, 1.0),
        "three_quarter": (2.4, -2.4, 1.15),
    }
    os.makedirs(out_dir, exist_ok=True)
    for name, (x, y, z) in views.items():
        cam.location = (x, y, z)
        target_z = 0.95
        cam.rotation_euler = (
            math.atan2(math.hypot(x, y), z - target_z),
            0.0,
            math.atan2(y, x) + math.pi / 2,
        )
        for frame in frames:
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            scene.render.filepath = os.path.join(out_dir, f"{tag}_{name}_f{frame:02d}.png")
            bpy.ops.render.render(write_still=True)


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--rig", choices=("anatomical", "spec"), default="anatomical",
                        help="'spec' = the brief's eight bones verbatim")
    parser.add_argument("--preview", metavar="DIR", default=None)
    args = parser.parse_args(argv)

    print(f"Blender {bpy.app.version_string} — rigging player_tactical")
    bpy.context.scene.render.fps = FPS

    print("TASK 1 — prepare mesh")
    mesh = prepare_mesh()

    print(f"TASK 2 — armature ({args.rig})")
    spec = skeleton(args.rig)
    arm = build_armature(spec)

    print("TASK 3 — bind")
    total, unweighted = bind_auto(mesh, arm)
    if total < 1e-6 or unweighted:
        # Full OR partial failure both count: heat weighting silently leaves
        # vertices at zero weight when shells are disconnected, and a partly
        # weighted mesh tears apart as soon as it animates.
        print(f"  ! bone-heat weighting failed for {unweighted}/{len(mesh.data.vertices)} "
              f"vertices (Blender's solver cannot handle this mesh's disconnected shells)")
        print("  -> falling back to the deterministic geometric solver")
        bind_geometric(mesh, arm)
    verify_weights(mesh, arm)
    print(f"  mesh parent={mesh.parent.name if mesh.parent else None} "
          f"modifiers={[m.type for m in mesh.modifiers]}")

    print("TASK 4 — animations")
    prepare_pose(arm)
    idle = build_idle(arm)
    walk = build_walk(arm)
    idle_action = bpy.data.actions["Idle"]
    walk_action = bpy.data.actions["Walk"]

    # numeric proof that the requested frame values landed
    print("  pose sampling (world-space bone tails, metres):")
    for frame in (1, 15, 30):
        lh = sample_pose_world(arm, walk_action, frame, "UpperArm.L")
        ll = sample_pose_world(arm, walk_action, frame, "UpperLeg.L")
        print(f"    walk f{frame:02d}: hand.L y={lh[1]:+.3f} z={lh[2]:.3f} | "
              f"foot.L y={ll[1]:+.3f} z={ll[2]:.3f}")
    for frame in (1, 15, 30):
        chest = sample_pose_world(arm, idle_action, frame, "Chest")
        print(f"    idle f{frame:02d}: chest tail z={chest[2]:.4f}")

    if args.preview:
        bpy.context.scene.frame_start, bpy.context.scene.frame_end = WALK_FRAMES
        render_frames(arm, mesh, walk_action, (1, 8, 15, 23), args.preview, "walk")
        render_frames(arm, mesh, idle_action, (1, 15), args.preview, "idle",
                      views={"front": (0.0, -3.4, 1.0)})

    print("TASK 5 — export")
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, 30
    reset_pose(arm)
    arm.animation_data.action = walk_action   # a sensible default clip

    before = skin_follows(mesh, arm, walk_action, 1, "UpperLeg.L")
    export_glb(arm, mesh, OUT_GLB)
    fixed = enforce_quaternion_continuity(OUT_GLB)
    remaining = count_quaternion_flips(OUT_GLB)
    print(f"  quaternion continuity: negated {fixed} key(s), {remaining} hemisphere flips left")
    if remaining:
        raise RuntimeError(f"{remaining} quaternion sign flips survived the fix")
    after = skin_follows(mesh, arm, walk_action, 1, "UpperLeg.L")
    deltas = [((a - b).length, i) for i, (a, b) in enumerate(zip(before, after))]
    drift, worst = max(deltas)
    print(f"  deformation check: max vertex drift across the export "
          f"= {drift * 1000:.3f} mm (vertex {worst})")
    if drift > 1e-4:
        before2 = before[worst]
        after2 = after[worst]
        vg = [(mesh.vertex_groups[g.group].name, round(g.weight, 3))
              for g in mesh.data.vertices[worst].groups if g.weight > 1e-4]
        raise RuntimeError(
            f"Mesh deformation changed across the export: vertex {worst} moved "
            f"{tuple(round(c, 4) for c in before2)} -> {tuple(round(c, 4) for c in after2)} "
            f"(weights {vg})"
        )
    stats = verify_glb(OUT_GLB)
    report(stats)
    print(f"  Exported -> {os.path.relpath(OUT_GLB, REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
