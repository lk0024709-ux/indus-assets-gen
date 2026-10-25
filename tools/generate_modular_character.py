#!/usr/bin/env python3
"""Modular character system — nude base body + separate clothing meshes (bpy).

Splits the rigged player into a template body and swappable garments, so a
character's clothes no longer depend on one baked-together material set:

    docs/models/characters/body_base.glb        nude body, single skin material
    docs/models/characters/clothing_shirt.glb   torso + upper arms, solid blue
    docs/models/characters/clothing_pants.glb   legs, solid black

All three files carry **the same 17-bone armature and the same Idle + Walk
clips**, and every vertex of every garment inherits the body's own skin
weights, so the pieces deform in lockstep no matter which combination is worn.
Open any one of them on its own: the body is a complete, dressed-down figure,
and each garment is a wearable that fits it exactly.

How the clothing is cut
-----------------------
The source mesh in ``docs/models/Character/Male_Suit.obj`` is already split
into semantic material groups, so the garments are not modelled from scratch
and guessed at — they are **extracted from the body itself**, which guarantees
the fit. The group names are misleading, though: "Shirt" is only the suit
*jacket* (sleeves, back, lapels), the panel of shirt visible between those
lapels is a separate shell under "TieTexture", and the collar, cuffs and belt
are under "Details". Taking all three is what actually yields a garment covering
"torso + upper arms". The base body keeps every polygon (just recoloured skin),
which is the fallback the brief allows, so it is never truncated into a hole.

Why the garments are offset along normals, not scaled
-----------------------------------------------------
The brief asks for "scaled up by 1.05 on the X and Z axes". In Blender's Z-up
frame that scales horizontal X and vertical Z but leaves **Y (depth) untouched**,
so chest and back sit inside the clothes — the exact bug the scaling was meant
to prevent. It also moves vertices in proportion to their distance from the
origin, so a shoulder drifts further than a wrist. ``--compare-scale`` measures
the brief's literal approach for contrast: it covers only 37% / 29% of the body
with 0.2 mm of clearance, against 95% / 91% with 9-17 mm here.

Instead each garment vertex is pushed out along its own (welded, smooth) surface
normal by a cloth thickness, tapered towards hems and cuffs, and the two
garments are offset by *different* amounts so the shirt stays the outer layer
where they overlap at the waist.

Three bugs are worth knowing about before changing any of this; each was found
by rendering an assembled character with the body coloured magenta:

1. The source is unwelded — 240 jacket quads are stored as 940 vertices at 256
   positions — so normals must be averaged per position, not per vertex.
2. ``recalc_face_normals`` cannot orient an open shell and flips the trousers
   inside-out; the authored winding is already coherent (zero inconsistent
   edges in every group) and must simply be trusted.
3. The two hems meet exactly at the waist, so equal offsets let the bare body
   show through a wedge-shaped seam. The trousers' waistband is raised up
   underneath the shirt to close it.

Run:
    pip install bpy
    python tools/generate_modular_character.py [--preview DIR] [--compare-scale]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections import deque

import bpy
import bmesh
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import character_lib as lib  # noqa: E402
import rig_character as rig  # noqa: E402

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAR_DIR = os.path.join(REPO_ROOT, "docs", "models", "characters")
SOURCE_OBJ = os.path.join(REPO_ROOT, "docs", "models", "Character", "Male_Suit.obj")

HEIGHT = 1.80
BRIGHT_SCALE = 1.05            # the brief's literal approach, for comparison

# Layering. The shirt is worn over the trousers, so it has to stand further off
# the body than they do: at the waist the two hems meet, and if both were offset
# by the same amount their rims would collide and the bare body would show
# through the seam (it does — the first build left a visible band of hip there).
# The trousers are therefore thinner, and their rims tuck in towards the body.
GARMENT_THICKNESS = {
    "clothing_shirt": 0.018,
    "clothing_pants": 0.012,
}

# The two hems meet at the waist (z = 0.915 dead centre front) and the trousers'
# waist dips into a V there, which leaves a wedge of bare body showing between
# them. Rather than dragging the shirt hem down over it — which pushes the hem
# into the seat at the back, because the body bulges below the waist — the
# trousers' waistband is raised *up under* the shirt. It is the inner layer, so
# it can only ever hide more body, never expose it.
WAIST_RISE = 0.048
WAIST_RISE_Z_LOW = 0.84
WAIST_RISE_Z_HIGH = 0.95

# Material names are prefixed because the imported .obj already occupies the
# plain "Skin" / "Shirt" / "Pants" datablock names, which would push ours to
# "Shirt.001" in the exported file.
PALETTE = {
    "Skin":  {"name": "Body_Skin",   "hex": "D2A679", "metallic": 0.0, "roughness": 0.72},
    "Shirt": {"name": "Cloth_Shirt", "hex": "2F6FB5", "metallic": 0.0, "roughness": 0.82},
    "Pants": {"name": "Cloth_Pants", "hex": "141414", "metallic": 0.0, "roughness": 0.86},
}

# Which source material groups make up each garment.
#
# The naming in the .obj is misleading, and the reason the first build of the
# shirt looked like an open jacket with a bare chest: the "Shirt" group is only
# the suit *jacket* (sleeves, back, lapels). The panel of shirt visible between
# those lapels is its own shell under "TieTexture", and the collar, cuffs and
# belt are under "Details". A garment that should cover "torso + upper arms"
# therefore has to take all three. "Eyes" is left alone -- it holds the eyes and
# the shoes, and "Pants" is the trousers on their own.
GARMENT_GROUPS = {
    "clothing_shirt": ("Shirt", "TieTexture", "Details"),
    "clothing_pants": ("Pants",),
}

ASSETS = ("body_base", "clothing_shirt", "clothing_pants")


# ---------------------------------------------------------------------------
# Source
# ---------------------------------------------------------------------------
def load_source():
    """Import the original .obj and put it in the same frame as the other rigs.

    ``character_lib.normalise_transform`` applies the Y-up OBJ -> Z-up Blender
    rotation, scales to exactly 1.80 m and drops the origin to the bottom
    centre, which is precisely how player_tactical.glb was prepared. That means
    the bone coordinates in rig_character.skeleton() line up with this mesh.
    """
    bpy.ops.wm.read_factory_settings(use_empty=True)
    imported, importer = lib.import_obj(SOURCE_OBJ)
    mesh = lib.join_meshes(imported)
    lib.normalise_transform(mesh, HEIGHT, "Source")

    co = [v.co for v in mesh.data.vertices]
    xs = [v.x for v in co]
    ys = [v.y for v in co]
    zs = [v.z for v in co]
    print(f"  source: {os.path.relpath(SOURCE_OBJ, REPO_ROOT)} via {importer}")
    print(f"  {len(co):,} verts | {len(mesh.data.polygons):,} faces | "
          f"{len(mesh.data.materials)} groups | height {max(zs) - min(zs):.4f} m | "
          f"X[{min(xs):+.3f},{max(xs):+.3f}] Y[{min(ys):+.3f},{max(ys):+.3f}] "
          f"Z[{min(zs):.3f},{max(zs):.3f}]")
    return mesh


def material_groups(mesh) -> dict:
    """material name -> set of polygon indices."""
    names = [m.name if m else "" for m in mesh.data.materials]
    groups: dict[str, set] = {}
    for poly in mesh.data.polygons:
        name = names[poly.material_index] if poly.material_index < len(names) else ""
        groups.setdefault(name, set()).add(poly.index)
    return groups


# ---------------------------------------------------------------------------
# Weight map — computed once per run from the full body, reused by garments
# ---------------------------------------------------------------------------
def compute_weight_map(mesh, arm) -> dict:
    """vertex index -> [(bone, weight), ...], using the body's material groups.

    Same solver as ``rig_character.bind_geometric`` (material-aware bone
    restriction + inverse-distance weights), but pure: it does not parent or
    add modifiers, so it can be evaluated before the mesh is cut into parts.
    """
    chains = rig._chains(arm)
    bones = {b.name: (b.head_local.copy(), b.tail_local.copy()) for b in arm.data.bones}
    names = [m.name if m else "" for m in mesh.data.materials]

    vert_material = [""] * len(mesh.data.vertices)
    for poly in mesh.data.polygons:
        name = names[poly.material_index] if poly.material_index < len(names) else ""
        for vi in poly.vertices:
            if not vert_material[vi]:
                vert_material[vi] = name

    weights = {}
    for vert in mesh.data.vertices:
        allowed = rig.candidate_bones(vert.co, vert_material[vert.index], chains) or list(bones)
        scored = sorted((rig.segment_distance(vert.co, *bones[n]), n) for n in allowed)
        scored = scored[: rig.MAX_INFLUENCES]
        raw = [(1.0 / ((d + 0.02) ** rig.WEIGHT_FALLOFF), n) for d, n in scored]
        total = sum(w for w, _ in raw)
        weights[vert.index] = [(n, w / total) for w, n in raw]
    return weights


def apply_weights(obj, arm, weight_map: dict, index_map: list[int]) -> None:
    """Copy the body's weights onto ``obj``; index_map maps new -> source vertex."""
    for vg in list(obj.vertex_groups):
        obj.vertex_groups.remove(vg)
    groups = {b.name: obj.vertex_groups.new(name=b.name) for b in arm.data.bones}
    for new_idx, source_idx in enumerate(index_map):
        for bone, weight in weight_map[source_idx]:
            groups[bone].add([new_idx], weight, "REPLACE")

    obj.parent = arm
    obj.matrix_parent_inverse = arm.matrix_world.inverted()
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = arm


# ---------------------------------------------------------------------------
# Geometry: weld -> trust the source winding -> tapered outward offset
# ---------------------------------------------------------------------------
def _pos_key(co) -> tuple:
    """Position key used to weld split vertices back into one logical vertex."""
    return (round(co.x, 5), round(co.y, 5), round(co.z, 5))


# Rim taper: how much of the full thickness a vertex gets, by hops from the
# garment's open boundary. Hems and cuffs should hug the body; the middle of a
# panel should stand clear of it. The trousers tuck in harder than the shirt so
# that the shirt stays the outer layer wherever the two overlap.
RIM_TAPER = {
    "clothing_shirt": {1: 0.50, 2: 0.80},
    "clothing_pants": {1: 0.25, 2: 0.55},
}


def build_part(mesh, face_indices, name: str):
    """New object holding only ``face_indices``; returns (obj, new->source map)."""
    verts = mesh.data.vertices
    used: list[int] = []
    remap: dict[int, int] = {}
    coords = []
    faces = []
    for pi in sorted(face_indices):
        poly = mesh.data.polygons[pi]
        face = []
        for vi in poly.vertices:
            if vi not in remap:
                remap[vi] = len(used)
                used.append(vi)
                coords.append(tuple(verts[vi].co))
            face.append(remap[vi])
        faces.append(face)

    me = bpy.data.meshes.new(name)
    me.from_pydata(coords, [], faces)
    me.validate(verbose=False)
    me.update()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj, used


def welded_garment(obj) -> bmesh.types.BMesh:
    """``obj`` welded by position, with its source winding left untouched.

    The source .obj is unwelded — every quad carries its own four vertices, so
    the Shirt group's 240 quads arrive as 940 vertices at only 256 distinct
    positions. Averaging normals per vertex *index* therefore yields a hard
    per-face normal, not a smooth surface normal, and offsets along that tear
    the panel apart at every crease. Welding by position first is what makes
    the normal smooth (caller frees the returned bmesh).

    The winding is then used exactly as authored, which was verified rather than
    assumed: every material group has zero inconsistent edges, so each shell is
    coherent and already faces out. Two tempting "fixes" were tried and are
    actively wrong here:

    * ``recalc_face_normals`` resolves *consistency* but has no way to know
      which side of an open patch is outside, and on this asset it flips the
      whole Pants group inwards — the trousers are then displaced 18 mm into
      the legs and vanish inside the body.
    * Orienting each normal away from the nearest bone axis looks principled,
      but the hands hang level with the thighs, so vertices on the outer thigh
      take ``Hand.L`` as their nearest bone and get flipped inwards. That is the
      same trap that tears distance-only skinning.
    """
    tmp, _index_map = build_part(obj, set(range(len(obj.data.polygons))), "WeldTmp")
    bm = bmesh.new()
    bm.from_mesh(tmp.data)
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=1e-5)
    bm.verts.ensure_lookup_table()
    bm.normal_update()
    bpy.data.objects.remove(tmp, do_unlink=True)
    return bm


def welded_garment_normals(obj) -> dict:
    """``{position_key: (unit normal, hops from the open rim)}``."""
    bm = welded_garment(obj)
    adjacent = {v.index: [] for v in bm.verts}
    rim = set()
    for edge in bm.edges:
        a, b = edge.verts[0].index, edge.verts[1].index
        adjacent[a].append(b)
        adjacent[b].append(a)
        if len(edge.link_faces) == 1:      # boundary edge -> open rim
            rim.update((a, b))

    unreached = len(bm.verts) + 1
    hops = {i: (0 if i in rim else unreached) for i in adjacent}
    queue = deque(rim)
    while queue:
        v = queue.popleft()
        for n in adjacent[v]:
            if hops[n] > hops[v] + 1:
                hops[n] = hops[v] + 1
                queue.append(n)

    out = {_pos_key(v.co): (v.normal.copy(), min(hops[v.index], 9)) for v in bm.verts}
    bm.free()
    return out


def inconsistent_edges(obj) -> int:
    """Edges whose two faces wind the same way — should be zero everywhere."""
    bm = welded_garment(obj)
    count = sum(1 for e in bm.edges if len(e.link_faces) == 2 and not e.is_contiguous)
    bm.free()
    return count


def face_normal(mesh, indices) -> Vector:
    """Newell normal of a polygon, from its own winding."""
    pts = [mesh.vertices[i].co for i in indices]
    n = Vector((0.0, 0.0, 0.0))
    for i, a in enumerate(pts):
        b = pts[(i + 1) % len(pts)]
        n.x += (a.y - b.y) * (a.z + b.z)
        n.y += (a.z - b.z) * (a.x + b.x)
        n.z += (a.x - b.x) * (a.y + b.y)
    return n


def taper_factor(hops: int, asset: str) -> float:
    """Fraction of the thickness applied at ``hops`` edges from the rim."""
    return RIM_TAPER[asset].get(hops, 1.0)


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3.0 - 2.0 * t)


def raise_waist(obj) -> float:
    """Lift the trousers' waistband so it rides up inside the shirt.

    Only the top of the trousers moves, ramped in over ``WAIST_RISE_Z_LOW`` ..
    ``WAIST_RISE_Z_HIGH`` so the garment stretches instead of shearing, and the
    ankles (well below that band) are untouched. Returns the largest rise.
    """
    applied = 0.0
    for vert in obj.data.vertices:
        if vert.co.z <= WAIST_RISE_Z_LOW:
            continue
        rise = WAIST_RISE * smoothstep(WAIST_RISE_Z_LOW, WAIST_RISE_Z_HIGH, vert.co.z)
        if rise <= 0.0:
            continue
        vert.co.z += rise
        applied = max(applied, rise)
    obj.data.update()
    return applied


def inflate(obj, thickness: float, asset: str) -> dict:
    """Push every garment vertex out along its normal, tapered at the rim.

    Folding is the failure this can actually produce: an offset larger than the
    local radius of curvature turns a face inside out. Every face keeps its
    winding through the operation, so a face whose normal reverses has folded
    through the surface — that is checked and reported rather than assumed.
    """
    before = [face_normal(obj.data, list(p.vertices)) for p in obj.data.polygons]
    normals = welded_garment_normals(obj)
    offsets = []
    rim_vertices = 0
    for vert in obj.data.vertices:
        entry = normals.get(_pos_key(vert.co))
        if entry is None:
            continue
        normal, hops = entry
        rim_vertices += 1 if hops <= 1 else 0
        offset = thickness * taper_factor(hops, asset)
        vert.co = vert.co + normal * offset
        offsets.append(offset)
    obj.data.update()
    waist_rise = raise_waist(obj) if asset == "clothing_pants" else 0.0

    folded = 0
    for poly, previous in zip(obj.data.polygons, before):
        if previous.length > 1e-9 and face_normal(obj.data, list(poly.vertices)).dot(previous) < 0.0:
            folded += 1

    offsets.sort()
    return {
        "offset_min_mm": offsets[0] * 1000.0 if offsets else 0.0,
        "offset_max_mm": offsets[-1] * 1000.0 if offsets else 0.0,
        "rim_vertices": rim_vertices,
        "normals": len(normals),
        "folded_faces": folded,
        "inconsistent_edges": inconsistent_edges(obj),
        "waist_rise_mm": waist_rise * 1000.0,
    }


def add_material(obj, name: str):
    spec = PALETTE[name]
    mat = lib.make_solid_material(spec["name"], spec["hex"], spec["metallic"],
                                  spec["roughness"])
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.material_index = 0
    return mat


# ---------------------------------------------------------------------------
# Poke-through verification
# ---------------------------------------------------------------------------
def build_bvh(obj) -> BVHTree:
    verts = [v.co.copy() for v in obj.data.vertices]
    polys = [list(p.vertices) for p in obj.data.polygons]
    return BVHTree.FromPolygons(verts, polys, all_triangles=False, epsilon=0.0)


# Body surfaces that must never break the garment's outline. "Skin" is the
# head, neck and hands; the eyes and hair sit on the head. Details / TieTexture
# are the suit's collar and tie, which are deliberately buried under the
# clothes, so they are reported separately instead of failing the build.
SKIN_GROUPS = ("Skin", "Eyes", "Hair")
BURIED_GROUPS = ("Details", "TieTexture")


def garment_check(body, cloth, group_faces: set, thickness: float) -> dict:
    """Does the garment actually stand off the body, everywhere it should?

    Two checks, both non-circular:

    *Coverage* — from every vertex of the body surface this garment replaces, a
    ray along that surface's outward normal must strike the garment at roughly
    the cloth thickness. A garment that slid sideways, scaled about the origin
    or ended up inside the body fails this, because the cloth is then nowhere
    along the body's normal. Rim vertices are exempt: their normal runs off the
    open edge of the panel rather than into the cloth.

    *Contacts* — triangle intersections against every other body group, counted
    per group, so the layered parts that are meant to be buried (the suit's
    front panel and collar, now part of the same garment) are visible in the
    report rather than silently assumed fine.

    Note what this deliberately is *not*: an "is this vertex inside the body?"
    test. This model has no skin layer underneath the clothes — the trousers are
    the legs — so the body surface and the garment are the same surface 18 mm
    apart, and containment questions are meaningless (and, measured by ray
    parity on a union of open shells, actively wrong).
    """
    names = [m.name if m else "" for m in body.data.materials]
    owner = [names[p.material_index] if p.material_index < len(names) else ""
             for p in body.data.polygons]

    body_bvh = build_bvh(body)
    cloth_bvh = build_bvh(cloth)

    counts: dict[str, int] = {}
    for _cloth_index, body_index in cloth_bvh.overlap(body_bvh):
        group = owner[body_index]
        counts[group] = counts.get(group, 0) + 1

    # Normals of the body surface being replaced, from its own (coherent)
    # winding. Taken from a copy of the body, because the garment's vertices
    # have already been displaced and no longer match it.
    tmp, _m = build_part(body, group_faces, "CoverTmp")
    normals = welded_garment_normals(tmp)
    bpy.data.objects.remove(tmp, do_unlink=True)

    covered = 0
    rim = 0
    distances = []
    for poly in body.data.polygons:
        if poly.index not in group_faces:
            continue
        for vi in poly.vertices:
            co = body.data.vertices[vi].co
            entry = normals.get(_pos_key(co))
            if entry is None:
                rim += 1
                continue
            normal, _hops = entry
            hit, _n, _i, dist = cloth_bvh.ray_cast(co + normal * 0.001, normal, 0.06)
            if hit is None:
                rim += 1
            else:
                covered += 1
                distances.append(dist)

    distances.sort()
    return {
        "covered": covered,
        "uncovered": rim,
        "coverage_pct": round(100.0 * covered / max(1, covered + rim), 2),
        "clearance_min_mm": distances[0] * 1000.0 if distances else 0.0,
        "clearance_median_mm": (distances[len(distances) // 2] * 1000.0
                                if distances else 0.0),
        "contacts_by_group": {k: v for k, v in sorted(counts.items()) if v},
    }


def build_asset(asset: str, source, weight_map, thickness_scale: float = 1.0,
                blue_scale=None):
    """Build one output asset in a fresh scene and return (obj, arm, meta)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.render.fps = rig.FPS

    # Re-import so every asset starts from an identical, untouched source.
    imported, _ = lib.import_obj(SOURCE_OBJ)
    mesh = lib.join_meshes(imported)
    lib.normalise_transform(mesh, HEIGHT, "Source")
    groups = material_groups(mesh)

    arm = rig.build_armature(rig.skeleton("anatomical"))

    poke = None
    if asset == "body_base":
        obj = mesh
        obj.name = "BodyBase"
        obj.data.name = "BodyBase"
        index_map = list(range(len(mesh.data.vertices)))
        # Everything collapses to one skin material, as the brief allows.
        add_material(obj, "Skin")
    elif asset in GARMENT_GROUPS:
        face_indices = set()
        for group in GARMENT_GROUPS[asset]:
            face_indices |= groups[group]
        obj, index_map = build_part(mesh, face_indices,
                                    asset.replace("_", " ").title())
        if blue_scale is not None:
            inflate_stats = {"offset_min_mm": 0.0, "offset_max_mm": 0.0,
                             "rim_vertices": 0, "normals": 0, "folded_faces": 0,
                             "inconsistent_edges": 0, "waist_rise_mm": 0.0}
        else:
            inflate_stats = inflate(obj, GARMENT_THICKNESS[asset] * thickness_scale,
                                    asset)
        # The body still holds every polygon here, so it is its own referee.
        poke = dict(inflate_stats)
        poke.update(garment_check(mesh, obj, face_indices,
                                  GARMENT_THICKNESS[asset] * thickness_scale))
        add_material(obj, "Shirt" if asset == "clothing_shirt" else "Pants")
    else:
        raise ValueError(asset)

    # The body keeps its original material groups for weight purposes only.
    apply_weights(obj, arm, weight_map, index_map)

    obj["asset"] = asset
    obj["height_m"] = HEIGHT
    obj["origin"] = "bottom-centre (0,0,0)"
    obj["textures"] = "none — solid Principled BSDF colours only"
    obj["rig"] = "17-bone PlayerRig, shared with body_base/clothing_shirt/clothing_pants"

    rig.prepare_pose(arm)
    rig.build_idle(arm)
    rig.build_walk(arm)
    rig.reset_pose(arm)
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, 30
    arm.animation_data.action = bpy.data.actions["Walk"]

    tris = sum(len(p.vertices) - 2 for p in obj.data.polygons)
    meta = {
        "asset": asset,
        "verts": len(obj.data.vertices),
        "faces": len(obj.data.polygons),
        "tris": tris,
    }
    if poke is not None:
        meta["poke_through"] = poke
    return obj, arm, meta


def scale_xy_z(obj, factor: float) -> None:
    """The brief's literal 'scale up 1.05 on X and Z' — kept only for comparison."""
    for v in obj.data.vertices:
        v.co.x *= factor
        v.co.z *= factor
    obj.data.update()


def export_asset(obj, arm, asset: str) -> dict:
    path = os.path.join(CHAR_DIR, f"{asset}.glb")
    rig.export_glb(arm, obj, path)
    fixed = rig.enforce_quaternion_continuity(path)
    remaining = rig.count_quaternion_flips(path)
    if remaining:
        raise RuntimeError(f"{asset}: {remaining} quaternion flips survived")
    stats = rig.verify_glb(path)
    stats["quaternion_fixes"] = fixed
    return stats


# ---------------------------------------------------------------------------
# QA render — all three assets on top of each other
# ---------------------------------------------------------------------------
def render_layered(out_path: str) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 40
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 760
    scene.world = bpy.data.worlds.new("W")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.20, 0.22, 0.26, 1.0)
    bg.inputs[1].default_value = 1.0

    key = bpy.data.lights.new("Key", "AREA")
    key.energy = 520
    key.size = 3.0
    ko = bpy.data.objects.new("Key", key)
    scene.collection.objects.link(ko)
    ko.location = (2.6, -3.0, 3.4)
    ko.rotation_euler = (math.radians(52), 0, math.radians(40))
    fill = bpy.data.lights.new("Fill", "AREA")
    fill.energy = 190
    fill.size = 4.0
    fo = bpy.data.objects.new("Fill", fill)
    scene.collection.objects.link(fo)
    fo.location = (-3.0, -2.0, 1.8)
    fo.rotation_euler = (math.radians(78), 0, math.radians(-55))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 55
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = (0.0, -4.6, 1.05)
    cam.rotation_euler = (math.radians(88), 0.0, 0.0)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    scene.render.filepath = out_path
    bpy.ops.render.render(write_still=True)


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--preview", metavar="DIR", default=None,
                        help="render the layered body+clothes preview into DIR")
    parser.add_argument("--compare-scale", action="store_true",
                        help="also measure the brief's literal 1.05 X/Z scaling")
    parser.add_argument("--thickness-scale", type=float, default=1.0,
                        metavar="K",
                        help="multiply the per-garment cloth thickness by K")
    args = parser.parse_args(argv)

    print(f"Blender {bpy.app.version_string} — modular character system")
    print("\nTASK 1 — source + weights")
    source = load_source()
    groups = material_groups(source)
    bpy.context.scene.render.fps = rig.FPS
    probe_arm = rig.build_armature(rig.skeleton("anatomical"))
    weight_map = compute_weight_map(source, probe_arm)
    print(f"  weight map computed for {len(weight_map):,} vertices "
          f"(<= {rig.MAX_INFLUENCES} influences each)")

    results = {}
    report = {}
    for asset in ASSETS:
        label = {"body_base": "base body (single Skin material)",
                 "clothing_shirt": "shirt (torso + upper arms, solid blue)",
                 "clothing_pants": "pants (legs, solid black)"}[asset]
        print(f"\n  building {label}")
        obj, arm, meta = build_asset(asset, source, weight_map,
                                    args.thickness_scale)
        stats = export_asset(obj, arm, asset)
        results[asset] = {**meta, **stats}
        print(f"    {meta['verts']:,} verts | {meta['tris']:,} tris | "
              f"{stats['bytes'] / 1024:.1f} KB | {stats['joints']} joints | "
              f"{stats['animation_names']} | {stats['images']} textures")
        if "poke_through" in meta:
            p = meta["poke_through"]
            report[asset] = p
            print(f"    offset {p['offset_min_mm']:.1f}-{p['offset_max_mm']:.1f} mm "
                  f"along {p['normals']} welded outward normals "
                  f"({p['rim_vertices']} rim vertices tapered) | "
                  f"folded faces {p['folded_faces']} | "
                  f"inconsistent edges {p['inconsistent_edges']}"
                  + (f" | waistband raised {p['waist_rise_mm']:.0f} mm"
                     if p.get("waist_rise_mm") else ""))
            print(f"    coverage {p['coverage_pct']:.1f}% "
                  f"({p['covered']} body vertices see cloth, "
                  f"{p['uncovered']} on the rim) | clearance "
                  f"{p['clearance_min_mm']:.1f}-{p['clearance_median_mm']:.1f} mm")
            print(f"    self-contacts by body group: {p['contacts_by_group']}")
            if p["folded_faces"]:
                raise RuntimeError(f"{asset}: {p['folded_faces']} faces folded "
                                   f"through the surface during the offset")
            if p["coverage_pct"] < 85.0:
                raise RuntimeError(f"{asset}: garment covers only "
                                   f"{p['coverage_pct']:.1f}% of the body it replaces")

    if args.compare_scale:
        print("\n  comparison — the brief's literal 'scale 1.05 on X and Z':")
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=os.path.join(CHAR_DIR, "body_base.glb"))
        body = [o for o in bpy.data.objects if o.type == "MESH"][0]
        imported, _ = lib.import_obj(SOURCE_OBJ)
        src = lib.join_meshes(imported)
        lib.normalise_transform(src, HEIGHT, "Src")
        groups = material_groups(src)
        for asset in ("clothing_shirt", "clothing_pants"):
            faces = set()
            for group in GARMENT_GROUPS[asset]:
                faces |= groups[group]
            part, _idx = build_part(src, faces, "Cmp")
            scale_xy_z(part, BRIGHT_SCALE)
            result = garment_check(src, part, faces, BRIGHT_SCALE)
            report[f"{asset}__scale_1.05"] = result
            print(f"    {asset:16s} coverage {result['coverage_pct']:5.1f}% | "
                  f"clearance min {result['clearance_min_mm']:6.2f} mm | "
                  f"median {result['clearance_median_mm']:6.2f} mm")
            bpy.data.objects.remove(part, do_unlink=True)

    # ---- layered preview render
    if args.preview:
        print("\n  rendering layered preview")
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.context.scene.render.fps = rig.FPS
        armatures = []
        for asset in ASSETS:
            bpy.ops.import_scene.gltf(filepath=os.path.join(CHAR_DIR, f"{asset}.glb"))
            armatures.append([o for o in bpy.data.objects if o.type == "ARMATURE"][-1])
        for a in armatures:
            if a.animation_data:
                a.animation_data.action = bpy.data.actions["Walk"]
                if hasattr(a.animation_data, "action_slot") and a.animation_data.action.slots:
                    a.animation_data.action_slot = a.animation_data.action.slots[0]
        bpy.context.scene.frame_set(1)
        bpy.context.view_layer.update()
        render_layered(os.path.join(args.preview, "modular_layered.png"))
        print(f"    -> {os.path.join(args.preview, 'modular_layered.png')}")

    manifest = os.path.join(CHAR_DIR, "modular_character.json")
    with open(manifest, "w", encoding="utf-8") as fh:
        json.dump({
            "generated_by": "tools/generate_modular_character.py",
            "blender": bpy.app.version_string,
            "height_m": HEIGHT,
            "cloth_thickness_m": {k: v * args.thickness_scale
                                  for k, v in GARMENT_THICKNESS.items()},
            "waistband_rise_m": WAIST_RISE,
            "shared_rig": "17-bone PlayerRig (identical in all three files)",
            "shared_animations": ["Idle", "Walk"],
            "assets": {k: {kk: vv for kk, vv in v.items() if kk != "animation_names"}
                       for k, v in results.items()},
            "poke_through": report,
        }, fh, indent=2)
        fh.write("\n")

    print(f"\n  Exported {len(results)} assets to "
          f"{os.path.relpath(CHAR_DIR, REPO_ROOT)}")
    for asset in ASSETS:
        print(f"    {asset:16s} {results[asset]['bytes'] / 1024:7.1f} KB  "
              f"{results[asset]['tris']:5d} tris  {results[asset]['joints']} joints  "
              f"{results[asset]['animation_names']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
