#!/usr/bin/env python3
"""Mount Abu — rocky hill-station mesa for Indus : Battle Royale.

A single 150 x 150 m terrain tile built entirely from maths (no sculpting,
no primitives-as-final-geometry):

  150 x 150 m footprint, 1 m grid (151 x 151 verts)
  Z = 25 m flat plateau, r <= 30 m            -> 60 m wide buildable top
  Z = 25 -> 0 over r = 30 .. 40 m             -> 78.7 deg max cliff face
  Z = 0 flat apron, r >= 40 m, dead flat 5 m border for tile snapping
  3-octave value-noise + radial rib displacement, cliff band only
  Bezier corniche road, 8 m wide, carved bench, shrinkwrap-projected
  Nakki Lake: r = 15 m, 2 m deep Boolean cutout, water plane at Z = 24
  15 trees + 6 rocks on the plateau rim, centre left clear for buildings
  Concave collision proxy: carved terrain + road, no vegetation

The radial profile is the "sharpened smoothstep"

    S(u) = u^2 / (u^2 + (1-u)^2),      u = (r - 30) / 10
    z(r) = 25 * (1 - S(u))

which is C1 at both ends (so the plateau and the apron are *exactly* flat)
and peaks at S'(0.5) = 2, i.e. dz/dr = 25/10 * 2 = 5.0  ->  78.69 deg.

Usage:
  pip install bpy pillow numpy
  python tools/generate_mount_abu.py
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
import numpy as np
from mathutils import Matrix, Vector

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURE_DIR = os.path.join(REPO_ROOT, "docs", "textures")
TERRAIN_DIR = os.path.join(REPO_ROOT, "docs", "models", "terrain")
OUT_PATH = os.path.join(TERRAIN_DIR, "terrain_mount_abu.glb")
COLLISION_PATH = os.path.join(TERRAIN_DIR, "terrain_mount_abu_collision.glb")

# ---------------------------------------------------------------------------
# Shape constants
# ---------------------------------------------------------------------------
TILE = 150.0            # footprint
HALF = TILE / 2.0       # 75
DIVISIONS = 150         # grid subdivisions -> 1 m cells
STEP = TILE / DIVISIONS

PEAK_Z = 25.0           # plateau height
PLATEAU_R = 30.0        # flat-top radius
CLIFF_OUT_R = 70.0      # foot of the mountain (meets the flat apron)
CLIFF_BAND = CLIFF_OUT_R - PLATEAU_R   # 40 m of relief

# The brief's profile: 25 m of a 40 m band. Broken into three C1 segments so
# the wall has a rounded shoulder, a near-vertical core and a talus skirt.
#   shoulder 30 -> 40 m: 4.0 m of drop   (ease in)
#   core     40 -> 46 m: 18.0 m of drop  (1.5 * 18 / 6 = 4.5  ->  77.5 deg)
#   talus    46 -> 70 m: 3.0 m of drop   (ease out to the tile seam)
DROPS = ((PLATEAU_R, 40.0, 0.16), (40.0, 46.0, 0.72), (46.0, CLIFF_OUT_R, 0.12))

BORDER_M = 5.0          # flat border that snaps to the grass tiles
BORDER_R = HALF - BORDER_M          # 70

LAKE_R = 15.0
LAKE_DEPTH = 2.0
LAKE_FLOOR_Z = PEAK_Z - LAKE_DEPTH  # 23.0
WATER_Z = 24.0

ROAD_W = 8.0
ROAD_HALF = ROAD_W / 2.0
ROAD_SHOULDER = 4.6
ROAD_LIFT = 0.10        # shrinkwrap offset
BARRIER_OFFSET = ROAD_HALF - 0.35
BARRIER_STEP = 2.6

MAX_GRADE_DEG = 15.0

UV_SCALE = 10.0         # metres per texture repeat

# ---------------------------------------------------------------------------
# Small maths helpers
# ---------------------------------------------------------------------------

def smoothstep(e0: float, e1: float, x):
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _hash2(ix: np.ndarray, iy: np.ndarray, seed: int) -> np.ndarray:
    h = (ix * 374761393 + iy * 668265263 + seed * 2654435761) & 0xFFFFFFFF
    h = ((h ^ (h >> 13)) * 1274126177) & 0xFFFFFFFF
    h = (h ^ (h >> 16)) & 0xFFFFFFFF
    return h.astype(np.float64) / 4294967295.0


def value_noise(x: np.ndarray, y: np.ndarray, seed: int) -> np.ndarray:
    """Smooth 2D value noise in [-1, 1] (bilinear + smoothstep on a unit lattice)."""
    x0 = np.floor(x)
    y0 = np.floor(y)
    fx = x - x0
    fy = y - y0
    ux = fx * fx * (3.0 - 2.0 * fx)
    uy = fy * fy * (3.0 - 2.0 * fy)
    ix = x0.astype(np.int64)
    iy = y0.astype(np.int64)
    n00 = _hash2(ix, iy, seed)
    n10 = _hash2(ix + 1, iy, seed)
    n01 = _hash2(ix, iy + 1, seed)
    n11 = _hash2(ix + 1, iy + 1, seed)
    nx0 = n00 + (n10 - n00) * ux
    nx1 = n01 + (n11 - n01) * ux
    return (nx0 + (nx1 - nx0) * uy) * 2.0 - 1.0


def fbm(x: np.ndarray, y: np.ndarray, seed: int, octaves: int = 3) -> np.ndarray:
    total = np.zeros_like(x, dtype=np.float64)
    amp = 1.0
    freq = 1.0
    norm = 0.0
    for o in range(octaves):
        total += amp * value_noise(x * freq, y * freq, seed + o * 101)
        norm += amp
        amp *= 0.5
        freq *= 2.03
    return total / norm


# ---------------------------------------------------------------------------
# The height function
# ---------------------------------------------------------------------------

def radial_profile(r):
    """Z of the undisplaced mesa at radius r (exactly 25 / 0 outside the band).

    Sum of three smoothsteps, each with zero slope at both ends, so the whole
    profile is C1: the plateau is dead flat and the apron blends into Z=0.
    """
    r = np.asarray(r, dtype=np.float64)
    drop = np.zeros_like(r)
    for r0, r1, share in DROPS:
        drop = drop + share * smoothstep(r0, r1, r)
    return PEAK_Z * (1.0 - np.clip(drop, 0.0, 1.0))


def cliff_mask(r):
    """Displacement weight = normalised local steepness.

    Using |dz/dr| means the noise can only ever touch the steep rock: the flat
    top and the flat apron are mathematically excluded, not just faded out.
    """
    rs = np.linspace(PLATEAU_R, CLIFF_OUT_R, 4001)
    zs = radial_profile(rs)
    slope = np.abs(np.gradient(zs, rs))
    peak = slope.max()
    r = np.asarray(r, dtype=np.float64)
    local = np.abs(np.interp(r, rs, slope)) / max(peak, 1e-9)
    return np.clip(local, 0.0, 1.0) ** 1.1


def terrain_z(x, y):
    """Full height field: radial mesa + ribs + rock noise (cliff band only)."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    r = np.hypot(x, y)
    phi = np.arctan2(y, x)
    m = cliff_mask(r)

    # radial rock ribs: lateral displacement of the profile, cliff band only.
    # Tapered at the rim and at the toe so the plateau lip stays crisp and the
    # apron stays a clean tile seam.
    rib = (0.50 * np.sin(9.0 * phi + 0.7)
           + 0.30 * np.sin(17.0 * phi + 2.1)
           + 0.16 * np.sin(29.0 * phi + 4.0))
    rib *= smoothstep(0.0, 0.06, (r - PLATEAU_R) / CLIFF_BAND) * (
        1.0 - smoothstep(0.94, 1.0, (r - PLATEAU_R) / CLIFF_BAND))

    # craggy buttresses: small-scale radial noise, same taper
    crag = 0.62 * fbm(x / 7.0, y / 7.0, 71, 2) + 0.20 * fbm(x / 3.4, y / 3.4, 83, 1)
    crag *= smoothstep(0.0, 0.08, (r - PLATEAU_R) / CLIFF_BAND) * (
        1.0 - smoothstep(0.92, 1.0, (r - PLATEAU_R) / CLIFF_BAND))
    # the near-vertical core cannot resolve 1 m lateral noise: a 0.8 m rib on a
    # 78 deg face turns into a knife edge that renders as a black crevice.
    crag *= 1.0 - 0.75 * m

    r_eff = r + (rib + crag) * m

    z = radial_profile(r_eff)

    # vertical rock displacement, weight = distance from either flat end
    z = z + m * (0.34 * fbm(x / 7.5, y / 7.5, 11, 3)
                 + 0.16 * fbm(x / 3.2, y / 3.2, 23, 2))

    # horizontal strata, only where the wall is genuinely steep
    strata = np.sin(z * 1.35 + 1.3 * fbm(x / 20.0, y / 20.0, 61, 2))
    strata += 0.30 * np.sin(z * 3.1 + 0.8)
    z = z + 0.42 * m * strata

    # very gentle apron undulation, fades to exactly 0 at r = 66
    apron = (0.22 * smoothstep(70.0, 74.0, r)
             * (1.0 - smoothstep(66.0, 71.0, r))
             * fbm(x / 16.0, y / 16.0, 41, 3))
    z = z + np.where(m > 0.0, 0.0, apron)

    # exact flats (guards against any floating point residue)
    # hard limits: the top can never rise above 25, the apron never below 0
    z = np.clip(z, 0.0, PEAK_Z)
    z = np.where(r <= PLATEAU_R, PEAK_Z, z)
    z = np.where(r >= CLIFF_OUT_R, 0.0, z)
    return z


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

def reset_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0


def new_object(name: str, verts, faces, collection=None):
    me = bpy.data.meshes.new(name + "Mesh")
    me.from_pydata([tuple(v) for v in verts], [], [tuple(f) for f in faces])
    me.update()
    me.validate(verbose=False)
    ob = bpy.data.objects.new(name, me)
    (collection or bpy.context.scene.collection).objects.link(ob)
    return ob


def recalc_normals(obj) -> None:
    """Make face winding consistent after Booleans, then force it to face up.

    A height field has no closed volume, so recalc_face_normals has no reliable
    "outside" to work from and can flip the whole sheet. The terrain always
    points up, so the mean normal decides the orientation.
    """
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bm.normal_update()
    # a height field never overhangs: every face must point up. Fix each one
    # individually, not just the global orientation.
    flipped = [f for f in bm.faces if f.normal.z < 0.0]
    if flipped:
        bmesh.ops.reverse_faces(bm, faces=flipped)
    bm.normal_update()
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    print(f"  normals: fixed {len(flipped)} inward-facing faces")


def cleanup_degenerate(obj) -> None:
    """Remove zero-area faces/edges left behind by Booleans and dissolving."""
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    before = len(bm.faces)
    bmesh.ops.dissolve_degenerate(bm, dist=1e-4, edges=bm.edges[:])
    bmesh.ops.delete(
        bm,
        geom=[f for f in bm.faces if f.calc_area() < 1e-6],
        context="FACES",
    )
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    print(f"  cleanup: {before - len(obj.data.polygons)} degenerate faces removed")


def shade_flat(obj) -> None:
    me = obj.data
    for p in me.polygons:
        p.use_smooth = False
    me.update()


def apply_modifier(obj, mod) -> None:
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)


def triangle_count(obj) -> int:
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


# ---------------------------------------------------------------------------
# 1. Height field
# ---------------------------------------------------------------------------

def build_terrain():
    n = DIVISIONS + 1
    xs = np.linspace(-HALF, HALF, n)
    ys = np.linspace(-HALF, HALF, n)
    gx, gy = np.meshgrid(xs, ys, indexing="xy")
    gx = gx.ravel()
    gy = gy.ravel()
    gz = terrain_z(gx, gy)

    verts = np.stack([gx, gy, gz], axis=1)
    faces = []
    for j in range(DIVISIONS):
        for i in range(DIVISIONS):
            a = j * n + i
            b = a + 1
            c = a + n + 1
            d = a + n
            faces.append((a, b, c, d))
    ob = new_object("MountAbu_Terrain", verts, faces)
    print(f"  grid {n} x {n} = {len(verts):,} verts / {len(faces):,} quads "
          f"({triangle_count(ob):,} tris)")
    return ob


# ---------------------------------------------------------------------------
# 2. Bezier centre line
# ---------------------------------------------------------------------------

# corniche geometry, all angles in degrees. The climb is a ghat road: it winds
# out across the talus, spirals once around the steep core and comes onto the
# plateau over the shoulder. Radial knots are spaced ~12-24 m per turn so the
# loops never collide (road is 8 m wide + a cut batter of ~5 m).
ROAD_START_DEG = -8.0
ROAD_KNOTS = (
    (ROAD_START_DEG, 62.0),      # talus, essentially at Z=0
    (150.0, 52.0),               # climb the talus skirt
    (450.0, 40.0),               # one full turn up the steep core
    (570.0, 31.2),               # over the shoulder onto the lip
)
ROAD_END_R = 24.0                # flat run-in across the plateau
ROAD_END_DEG = 585.0


def _ease(a: float, b: float, t: float) -> float:
    """Linear in r vs theta.

    An eased schedule spends its radial budget quickly in the middle of each
    segment, which is exactly where the profile is steepest: that doubles the
    grade through the core (measured 19.8 deg). A constant dr/dtheta keeps
    dz/ds proportional to dz/dr, so the steep core is crossed at a steady,
    gentle angle instead.
    """
    return a + (b - a) * t


def road_radius(theta_deg: float) -> float:
    """Radius at a given accumulated turn angle (C1 piecewise ease)."""
    knots = ROAD_KNOTS
    if theta_deg <= knots[0][0]:
        return knots[0][1]
    for (t0, r0), (t1, r1) in zip(knots, knots[1:]):
        if theta_deg <= t1:
            return _ease(r0, r1, (theta_deg - t0) / (t1 - t0))
    if theta_deg <= ROAD_END_DEG:
        return _ease(knots[-1][1], ROAD_END_R,
                     (theta_deg - knots[-1][0]) / (ROAD_END_DEG - knots[-1][0]))
    return ROAD_END_R


def road_point(theta_deg: float):
    th = math.radians(theta_deg)
    r = road_radius(theta_deg)
    return np.array([r * math.cos(th), r * math.sin(th)])


def road_control_points():
    """Bezier knots: straight approach along the road start tangent, then the
    analytic ghat spiral. The approach shares the spiral's tangent so the join
    is C1 and the ribbon cannot fold on itself."""
    p_a = road_point(ROAD_START_DEG)
    p_b = road_point(ROAD_START_DEG + 0.02)
    tangent = (p_b - p_a) / np.linalg.norm(p_b - p_a)

    # run the approach back exactly to the tile edge so the road can be joined
    # to a neighbouring tile, but never past it
    limit = HALF - 0.5
    approach = 22.0
    for d in np.arange(approach, 1.0, -1.0):
        p = p_a - tangent * d
        if abs(p[0]) <= limit and abs(p[1]) <= limit:
            approach = float(d)
            break
    knots = [tuple(p_a - tangent * approach),
             tuple(p_a - tangent * approach * 0.5), tuple(p_a)]
    steps = 64
    for k in range(1, steps + 1):
        theta = ROAD_START_DEG + (ROAD_END_DEG - ROAD_START_DEG) * k / steps
        knots.append(tuple(road_point(theta)))
    return knots


def sample_bezier(knots, resolution=28):
    cu = bpy.data.curves.new("MountAbuRoadPath", "CURVE")
    cu.dimensions = "3D"
    cu.resolution_u = resolution
    sp = cu.splines.new("BEZIER")
    sp.bezier_points.add(len(knots) - 1)
    for bp, (x, y) in zip(sp.bezier_points, knots):
        bp.co = (x, y, 0.0)
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    ob = bpy.data.objects.new("MountAbuRoadPath", cu)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(depsgraph).to_mesh()
    pts = np.array([[v.co.x, v.co.y] for v in me.vertices], dtype=np.float64)
    ob.evaluated_get(depsgraph).to_mesh_clear()
    bpy.data.objects.remove(ob, do_unlink=True)
    bpy.data.curves.remove(cu)
    return pts


def resample_polyline(pts, spacing=1.0):
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0.0], np.cumsum(seg)])
    total = s[-1]
    count = int(math.floor(total / spacing)) + 1
    targets = np.linspace(0.0, total, count)
    out = np.empty((count, pts.shape[1]))
    for d in range(pts.shape[1]):
        out[:, d] = np.interp(targets, s, pts[:, d])
    return out, targets


def build_road_centreline():
    """Bezier spine -> 1 m samples -> height taken from the radial profile."""
    knots = road_control_points()
    dense = sample_bezier(knots)
    dense, _ = resample_polyline(dense, 0.5)
    pts2, s = resample_polyline(dense, 1.0)
    total = s[-1]

    r = np.hypot(pts2[:, 0], pts2[:, 1])
    z = radial_profile(r)
    # endpoints: flat on the apron, exactly 25 on the plateau
    z = np.where(r >= CLIFF_OUT_R, 0.0, z)
    z = np.where(r <= PLATEAU_R, PEAK_Z, z)

    seg_len = np.linalg.norm(np.diff(pts2, axis=0), axis=1)

    # light smoothing so the 10 deg knot spacing cannot leave kinks in the grade
    kernel = np.ones(5) / 5.0
    z = np.convolve(np.pad(z, 2, mode="edge"), kernel, mode="valid")

    # hard grade limiter: relax z until every 1 m step is under 14 deg. The
    # profile already lands near 11 deg, this only trims sampling noise.
    limit = math.tan(math.radians(14.0))
    for _ in range(200):
        g = np.abs(np.diff(z)) / np.maximum(seg_len, 1e-6)
        worst = np.where(g > limit)[0]
        if worst.size == 0:
            break
        for i in worst:
            mean = 0.5 * (z[i] + z[i + 1])
            z[i] = 0.55 * z[i] + 0.45 * mean
            z[i + 1] = 0.55 * z[i + 1] + 0.45 * mean

    # plan curvature -> minimum turning radius (an 8 m road folds below ~5 m)
    d1 = np.gradient(pts2, axis=0)
    d2 = np.gradient(d1, axis=0)
    cross = np.abs(d1[:, 0] * d2[:, 1] - d1[:, 1] * d2[:, 0])
    speed = np.linalg.norm(d1, axis=1)
    curvature = cross / np.maximum(speed ** 3, 1e-9)
    radius = 1.0 / np.maximum(curvature, 1e-9)

    pts = np.column_stack([pts2, z])
    d = np.diff(pts, axis=0)
    seg = np.linalg.norm(d, axis=1)
    grade = np.degrees(np.arctan2(np.abs(np.diff(z)), seg))
    return pts, s, grade, knots, float(radius[2:-2].min())


# ---------------------------------------------------------------------------
# 3. Carve the bench into the height field
# ---------------------------------------------------------------------------

def carve_road(mesh_obj, road_pts, z_nat_flat, chunk=1500):
    """Project a constant-width bench corridor onto the height field.

    The corridor is measured in PLAN (pure XY distance to the nearest
    centre-line sample) so the shelf keeps its 8 m + 2.8 m shoulder width even
    where it is many metres above the natural cone.
    """
    me = mesh_obj.data
    n = len(me.vertices)
    co = np.empty((n, 3))
    me.vertices.foreach_get("co", co.ravel())

    xy = co[:, :2]
    rxy = road_pts[:, :2]
    rz = road_pts[:, 2]

    dist = np.empty(n)
    nearest_z = np.empty(n)
    for start in range(0, n, chunk):
        stop = min(start + chunk, n)
        dx = xy[start:stop, None, 0] - rxy[None, :, 0]
        dy = xy[start:stop, None, 1] - rxy[None, :, 1]
        d2 = dx * dx + dy * dy
        idx = np.argmin(d2, axis=1)
        dist[start:stop] = np.sqrt(np.take_along_axis(d2, idx[:, None], axis=1)[:, 0])
        nearest_z[start:stop] = rz[idx]

    bench = np.maximum(nearest_z - 0.08, 0.0)

    # Adaptive batter: on the inside of the corniche the bench is cut into the
    # cliff, so the cut needs a real slope, not a 1 m vertical wall. Deeper cuts
    # get a wider batter (roughly 40 deg), fills stay tight to the road.
    cut_depth = np.maximum(z_nat_flat - bench, 0.0)
    fill_depth = np.maximum(bench - z_nat_flat, 0.0)
    batter = ROAD_SHOULDER + 1.15 * cut_depth + 0.45 * fill_depth
    inner = np.clip((dist - (ROAD_HALF + 1.5)) / batter, 0.0, 1.0)
    t = inner * inner * (3.0 - 2.0 * inner) ** 0.75
    carved = np.where(dist <= ROAD_HALF + 1.5, bench, bench + (z_nat_flat - bench) * t)
    carved = np.clip(carved, 0.0, PEAK_Z)

    # the summit must stay dead level, the border must stay dead flat
    r = np.hypot(co[:, 0], co[:, 1])
    carved = np.where((r < PLATEAU_R - 0.6) & (z_nat_flat >= PEAK_Z - 1e-6),
                      PEAK_Z, carved)
    carved = np.where((np.abs(co[:, 0]) >= BORDER_R) | (np.abs(co[:, 1]) >= BORDER_R),
                      0.0, carved)

    co[:, 2] = carved
    me.vertices.foreach_set("co", co.ravel())
    me.update()
    print(f"  bench carved: {int((dist <= ROAD_HALF + 1.5).sum()):,} verts on the carriageway")
    return dist


# ---------------------------------------------------------------------------
# 4. Decimate flat regions, then cut Nakki Lake
# ---------------------------------------------------------------------------

def relax_cliff(obj, iterations=2):
    """Laplacian relax of the steep band only (removes knife-edge facets).

    Only vertices whose normal deviates from +Z are touched, and only for the
    XZ height, so the plateau, the apron and the 5 m border stay exact.
    """
    me = obj.data
    side = DIVISIONS + 1
    idx = np.arange(len(me.vertices)).reshape(side, side)
    n = len(me.vertices)
    neigh = [[] for _ in range(n)]
    for a, b in ((idx[:, :-1].ravel(), idx[:, 1:].ravel()),
                 (idx[:-1, :].ravel(), idx[1:, :].ravel())):
        for i, j in zip(a, b):
            neigh[i].append(j)
            neigh[j].append(i)

    co = np.empty((n, 3))
    me.vertices.foreach_get("co", co.ravel())
    movable = (co[:, 2] > 0.4) & (co[:, 2] < PEAK_Z - 0.4)
    movable &= (np.abs(co[:, 0]) < BORDER_R) & (np.abs(co[:, 1]) < BORDER_R)

    for _ in range(iterations):
        newz = co[:, 2].copy()
        for i in np.where(movable)[0]:
            if neigh[i]:
                avg = sum(co[j, 2] for j in neigh[i]) / len(neigh[i])
                newz[i] = 0.55 * co[i, 2] + 0.45 * avg
        co[:, 2] = newz
    me.vertices.foreach_set("co", co.ravel())
    me.update()
    print(f"  relaxed {int(movable.sum()):,} cliff verts ({iterations} passes)")


def smooth_cut_edges(obj, road_pts, iterations=2):
    """Relax the razor spikes where the bench meets the natural wall.

    A 1 m grid cannot resolve a 25 m near-vertical cut: neighbouring vertices
    end up 5 m apart in Z, which reads as sawtooth teeth. A couple of Laplacian
    passes over the transition ring only (never the carriageway, never the
    plateau, never the border) removes the spikes without moving the road.
    """
    me = obj.data
    n = len(me.vertices)
    co = np.empty((n, 3))
    me.vertices.foreach_get("co", co.ravel())

    # build 4-neighbour adjacency from the regular grid
    side = DIVISIONS + 1
    idx = np.arange(n).reshape(side, side)
    neighbours = [[] for _ in range(n)]
    for a, b in ((idx[:, :-1].ravel(), idx[:, 1:].ravel()),
                 (idx[:-1, :].ravel(), idx[1:, :].ravel())):
        for i, j in zip(a, b):
            neighbours[i].append(j)
            neighbours[j].append(i)

    xy = co[:, :2]
    rxy = road_pts[:, :2]
    near = np.full(n, np.inf)
    for start in range(0, n, 1500):
        blk = xy[start:start + 1500]
        d2 = ((blk[:, None, 0] - rxy[None, :, 0]) ** 2
              + (blk[:, None, 1] - rxy[None, :, 1]) ** 2)
        near[start:start + 1500] = np.sqrt(d2.min(axis=1))

    movable = (near > ROAD_HALF + 0.9) & (near < ROAD_HALF + ROAD_SHOULDER + 2.5)
    movable &= co[:, 2] > 0.5
    movable &= co[:, 2] < PEAK_Z - 0.5
    movable &= (np.abs(co[:, 0]) < BORDER_R) & (np.abs(co[:, 1]) < BORDER_R)

    weights = [ (1.0 / len(nei)) if nei else 0.0 for nei in neighbours ]
    for _ in range(iterations):
        newz = co[:, 2].copy()
        for i in range(n):
            if not movable[i] or not neighbours[i]:
                continue
            avg = sum(co[j, 2] for j in neighbours[i]) * weights[i]
            newz[i] = 0.45 * co[i, 2] + 0.55 * avg
        co[:, 2] = newz

    me.vertices.foreach_set("co", co.ravel())
    me.update()
    print(f"  smoothed {int(movable.sum()):,} cut-edge verts ({iterations} passes)")


def planar_decimate(obj, degrees=1.0):
    before = triangle_count(obj)
    mod = obj.modifiers.new("PlanarMerge", "DECIMATE")
    mod.decimate_type = "DISSOLVE"
    mod.angle_limit = math.radians(degrees)
    mod.use_dissolve_boundaries = False
    apply_modifier(obj, mod)
    after = triangle_count(obj)
    print(f"  flat-region dissolve {degrees:.1f} deg: {before:,} -> {after:,} tris")
    return after


def cut_lake(obj):
    """Boolean difference with a 128-sided cylinder: r=15, z 20..26."""
    segs = 128
    verts = []
    faces = []
    for k in range(segs):
        a = 2.0 * math.pi * k / segs
        verts.append((LAKE_R * math.cos(a), LAKE_R * math.sin(a), LAKE_FLOOR_Z - 3.0))
    for k in range(segs):
        a = 2.0 * math.pi * k / segs
        verts.append((LAKE_R * math.cos(a), LAKE_R * math.sin(a), PEAK_Z + 1.0))
    for k in range(segs):
        k2 = (k + 1) % segs
        faces.append((k, k2, segs + k2, segs + k))
    cutter = new_object("LakeCutter", verts, faces)

    mod = obj.modifiers.new("NakkiLakeCut", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter
    apply_modifier(obj, mod)
    bpy.data.objects.remove(cutter, do_unlink=True)
    print(f"  Boolean lake cut r={LAKE_R} m, {triangle_count(obj):,} tris")


def build_basin_and_water():
    segs = 128
    # basin wall: ring at r=15 from Z=25 down to Z=23, normals inward
    verts = []
    for k in range(segs):
        a = 2.0 * math.pi * k / segs
        verts.append((LAKE_R * math.cos(a), LAKE_R * math.sin(a), PEAK_Z))
    for k in range(segs):
        a = 2.0 * math.pi * k / segs
        verts.append((LAKE_R * math.cos(a), LAKE_R * math.sin(a), LAKE_FLOOR_Z))
    faces = []
    for k in range(segs):
        k2 = (k + 1) % segs
        faces.append((k2, k, segs + k, segs + k2))
    wall = new_object("MountAbu_LakeWall", verts, faces)

    # lake floor
    fverts = [(0.0, 0.0, LAKE_FLOOR_Z)]
    for k in range(segs):
        a = 2.0 * math.pi * k / segs
        fverts.append((LAKE_R * math.cos(a), LAKE_R * math.sin(a), LAKE_FLOOR_Z))
    ffaces = [(0, k + 1, (k + 1) % segs + 1) for k in range(segs)]
    floor = new_object("MountAbu_LakeFloor", fverts, ffaces)

    # water surface at Z = 24 (slightly inside the wall to avoid z-fighting)
    wverts = [(0.0, 0.0, WATER_Z)]
    wr = LAKE_R - 0.03
    for k in range(segs):
        a = 2.0 * math.pi * k / segs
        wverts.append((wr * math.cos(a), wr * math.sin(a), WATER_Z))
    wfaces = [(0, k + 1, (k + 1) % segs + 1) for k in range(segs)]
    water = new_object("MountAbu_Water", wverts, wfaces)
    return wall, floor, water


# ---------------------------------------------------------------------------
# 5. Materials
# ---------------------------------------------------------------------------

def solid_material(name, rgb, roughness=0.8, metallic=0.0):
    mat = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def textured_material(name, filename, tint, roughness=0.9):
    mat = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    path = os.path.join(TEXTURE_DIR, filename)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"texture missing: {path}")
    image = bpy.data.images.load(path, check_existing=True)
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    tex.extension = "REPEAT"
    tex.location = (-420, 200)
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = 0.0
    if tint != (1.0, 1.0, 1.0):
        mix = nt.nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs["Fac"].default_value = 0.55
        mix.inputs["Color2"].default_value = (*tint, 1.0)
        mix.location = (-200, 200)
        nt.links.new(tex.outputs["Color"], mix.inputs["Color1"])
        nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


def set_materials(obj, materials) -> None:
    obj.data.materials.clear()
    for m in materials:
        obj.data.materials.append(m)


def assign_terrain_materials(obj, grass, rock, road_pts=None):
    """Slope-based material split + cylindrical UVs on the cliff."""
    me = obj.data
    set_materials(obj, [grass, rock])
    uv = me.uv_layers.new(name="UVMap")
    uv_data = uv.data

    centroids = np.empty((len(me.polygons), 2))
    for poly in me.polygons:
        c = poly.center
        centroids[poly.index] = (c.x, c.y)
    corridor = np.zeros(len(me.polygons), dtype=bool)
    if road_pts is not None:
        rxy = road_pts[:, :2]
        for start in range(0, len(centroids), 2000):
            blk = centroids[start:start + 2000]
            d2 = ((blk[:, None, 0] - rxy[None, :, 0]) ** 2
                  + (blk[:, None, 1] - rxy[None, :, 1]) ** 2)
            corridor[start:start + 2000] = np.sqrt(d2.min(axis=1)) < (ROAD_HALF + ROAD_SHOULDER)

    for poly in me.polygons:
        nz = abs(poly.normal.z)
        # the plateau and the apron stay grass even under the road; only a
        # cut face is allowed to turn to rock
        cut = corridor[poly.index] and nz <= 0.93
        is_rock = nz <= 0.84 or cut
        poly.material_index = 1 if is_rock else 0

    for poly in me.polygons:
        steep = abs(poly.normal.z) <= 0.84 or (corridor[poly.index] and abs(poly.normal.z) <= 0.93)
        for li in poly.loop_indices:
            vi = me.loops[li].vertex_index
            x, y, z = me.vertices[vi].co
            if steep:
                # cylindrical: arc length around the mesa, height up the face
                phi = math.atan2(y, x)
                u = (phi * 34.0) / UV_SCALE
                v = z / UV_SCALE
            else:
                u = x / UV_SCALE
                v = y / UV_SCALE
            uv_data[li].uv = (u, v)
    me.update()


# ---------------------------------------------------------------------------
# 6. Road ribbon, centre line, barriers
# ---------------------------------------------------------------------------

def ribbon_from_centreline(pts, width, lift, name, dash=None):
    """Offset a 3D polyline into a flat horizontal ribbon of `width` metres."""
    verts = []
    faces = []
    count = len(pts)
    half = width / 2.0
    keep = [True] * count
    if dash is not None:
        period = int(dash[0] + dash[1])
        for i in range(count):
            keep[i] = (i % period) < int(dash[0])

    index = {}
    for i in range(count):
        if not keep[i]:
            continue
        if i == 0:
            t = pts[1] - pts[0]
        elif i == count - 1:
            t = pts[-1] - pts[-2]
        else:
            t = pts[i + 1] - pts[i - 1]
        t = np.array([t[0], t[1], 0.0])
        norm = np.linalg.norm(t)
        if norm < 1e-9:
            t = np.array([1.0, 0.0, 0.0])
        else:
            t = t / norm
        # left-hand normal in plan
        nrm = np.array([-t[1], t[0], 0.0])
        base = np.array([pts[i][0], pts[i][1], pts[i][2] + lift])
        index[i] = len(verts)
        verts.append(tuple(base - nrm * half))
        verts.append(tuple(base + nrm * half))

    prev = None
    for i in range(count):
        if not keep[i]:
            prev = None
            continue
        if prev is not None and i - prev == 1:
            a = index[prev]
            b = index[i]
            faces.append((a, b, b + 1, a + 1))
        prev = i
    ob = new_object(name, verts, faces)
    ob["bench_z"] = [v[2] for v in verts]
    return ob


def shrinkwrap_project(obj, target, offset, label="RoadShrinkwrap"):
    """Project the ribbon straight down onto the carved bench.

    Only the downward direction is used: the ribbon is already built at the
    analytic bench height, so a ray that misses simply leaves the vertex where
    it belongs instead of flinging it onto a different face of the cliff.
    """
    mod = obj.modifiers.new(label, "SHRINKWRAP")
    mod.target = target
    mod.wrap_method = "PROJECT"
    mod.use_project_z = True
    mod.use_negative_direction = True
    mod.use_positive_direction = False
    mod.wrap_mode = "ON_SURFACE"
    mod.offset = offset
    apply_modifier(obj, mod)

    # Safety clamp: PROJECT shoots straight down, so on a 78 deg wall an edge
    # vertex would be dragged tens of metres down the face. The bench is flat,
    # so anything beyond a few decimetres is a projection miss -> restore it.
    me = obj.data
    expected = np.array(obj.get("bench_z", []), dtype=np.float64)
    if expected.size == len(me.vertices):
        co = np.empty((len(me.vertices), 3))
        me.vertices.foreach_get("co", co.ravel())
        dz = co[:, 2] - expected
        bad = np.abs(dz) > 0.30
        co[bad, 2] = expected[bad]
        me.vertices.foreach_set("co", co.ravel())
        me.update()
        obj["projection_clamped"] = int(bad.sum())
    return obj


def flatten_road_rungs(obj, centre_z, max_grade=14.0):
    """Make every cross-section of the ribbon dead level.

    PROJECT drops each of the two edge vertices onto whatever the cliff does
    beneath it, which on a curving bench gives the two edges different heights
    (a roll of up to ~17 deg). A drivable road is a ruled surface: one height
    per cross-section, so both edge vertices take the rung height and the only
    remaining slope is longitudinal.
    """
    me = obj.data
    n = len(me.vertices)
    co = np.empty((n, 3))
    me.vertices.foreach_get("co", co.ravel())
    assert n % 2 == 0, "ribbon must be built as edge pairs"
    rungs = n // 2

    mids = 0.5 * (co[0::2, 2] + co[1::2, 2])
    rungs_z = np.asarray(centre_z, dtype=np.float64)

    # bring the measured mid-height back onto the analytic rung heights
    z = 0.35 * rungs_z + 0.65 * mids

    # longitudinal grade limiter on the rung sequence
    limit = math.tan(math.radians(max_grade))
    for _ in range(300):
        g = np.abs(np.diff(z))
        worst = np.where(g > limit)[0]
        if worst.size == 0:
            break
        for i in worst:
            mean = 0.5 * (z[i] + z[i + 1])
            z[i] = 0.6 * z[i] + 0.4 * mean
            z[i + 1] = 0.6 * z[i + 1] + 0.4 * mean

    co[0::2, 2] = z
    co[1::2, 2] = z
    me.vertices.foreach_set("co", co.ravel())
    me.update()
    return z


def build_barriers(pts, name="MountAbu_Barriers"):
    verts = []
    faces = []
    count = len(pts)
    step = max(1, int(round(BARRIER_STEP)))
    for i in range(0, count - 1, step):
        p = np.asarray(pts[i], dtype=np.float64)
        t = np.asarray(pts[min(i + 1, count - 1)] - pts[max(i - 1, 0)], dtype=np.float64)
        t[2] = 0.0
        norm = np.linalg.norm(t)
        if norm < 1e-9:
            continue
        t = t / norm
        nrm = np.array([-t[1], t[0], 0.0])
        radial = np.array([p[0], p[1], 0.0])
        if np.dot(nrm, radial) < 0.0:
            nrm = -nrm
        probe = np.array([p[0], p[1], 0.0]) + nrm * 9.0
        drop = float(p[2]) - float(terrain_z(np.array([probe[0]]), np.array([probe[1]]))[0])
        if drop < 2.0:
            continue
        centre = np.array([p[0], p[1], p[2] + ROAD_LIFT]) + nrm * BARRIER_OFFSET
        half_len, thick, height = 0.5, 0.175, 0.5
        base = len(verts)
        for sx, sy, sz in ((-1, -1, 0), (1, -1, 0), (1, 1, 0), (-1, 1, 0),
                           (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)):
            verts.append((
                centre[0] + t[0] * half_len * sx + nrm[0] * thick * sy,
                centre[1] + t[1] * half_len * sx + nrm[1] * thick * sy,
                centre[2] + height * sz,
            ))
        for f in ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
                  (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)):
            faces.append(tuple(base + k for k in f))
    ob = new_object(name, verts, faces)
    print(f"  barriers: {len(faces) // 6} blocks")
    return ob


# ---------------------------------------------------------------------------
# 7. Vegetation
# ---------------------------------------------------------------------------

def add_icosphere(bm, matrix, subdiv=1):
    bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0, matrix=matrix)


def tree_bmesh(rng, bm_target, matrices):
    bm = bmesh.new()
    height = rng.uniform(3.4, 4.8)
    trunk = bmesh.new()
    bmesh.ops.create_cone(
        trunk, cap_ends=True, segments=6,
        radius1=0.24, radius2=0.13, depth=height,
        matrix=Matrix.Translation((0.0, 0.0, height / 2.0)),
    )
    for f in trunk.faces:
        f.material_index = 0
    # transfer trunk
    _merge_bm(bm, trunk)
    trunk.free()

    blobs = []
    crown_z = height * 0.82
    blobs.append((Vector((0.0, 0.0, crown_z)), Vector((1.55, 1.55, 1.15))))
    a = rng.uniform(0, 2 * math.pi)
    off = rng.uniform(0.6, 0.95)
    blobs.append((Vector((off * math.cos(a), off * math.sin(a), crown_z + 0.95)),
                  Vector((1.15, 1.15, 0.85))))
    b = a + rng.uniform(1.8, 3.4)
    blobs.append((Vector((0.8 * math.cos(b), 0.8 * math.sin(b), crown_z - 0.55)),
                  Vector((1.05, 1.05, 0.8))))
    for centre, scale in blobs:
        m = (Matrix.Translation(centre)
             @ Matrix.Diagonal((scale.x, scale.y, scale.z, 1.0))
             @ Matrix.Rotation(rng.uniform(0, 6.28), 4, "Z"))
        before = len(bm.faces)
        add_icosphere(bm, m, subdiv=1)
        bm.faces.ensure_lookup_table()
        for f in bm.faces[before:]:
            f.material_index = 1 if f.index % 5 else 2

    for m in matrices:
        _merge_bm_into(bm_target, bm, m)
    bm.free()


def _merge_bm(dst, src):
    tmp = bpy.data.meshes.new("tmp")
    src.to_mesh(tmp)
    dst.from_mesh(tmp)
    bpy.data.meshes.remove(tmp)


def _merge_bm_into(dst, src, matrix):
    tmp = bpy.data.meshes.new("tmp")
    src.to_mesh(tmp)
    tmp.transform(matrix)
    dst.from_mesh(tmp)
    bpy.data.meshes.remove(tmp)


def build_vegetation(road_pts, materials):
    rng = random.Random(7)
    bm = bmesh.new()
    placed = []

    def free_spot(x, y, min_sep, avoid_road):
        if math.hypot(x, y) > 28.6:
            return False
        if any((x - px) ** 2 + (y - py) ** 2 < min_sep ** 2 for px, py in placed):
            return False
        if avoid_road:
            d = np.hypot(road_pts[:, 0] - x, road_pts[:, 1] - y)
            if d.min() < 6.5:
                return False
        return True

    # trees: 15, on the outer ring of the plateau
    trees = 0
    attempts = 0
    while trees < 15 and attempts < 4000:
        attempts += 1
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(21.5, 28.2)
        x, y = r * math.cos(a), r * math.sin(a)
        if not free_spot(x, y, 3.4, True):
            continue
        placed.append((x, y))
        tree_bmesh(rng, bm, [Matrix.Translation((x, y, PEAK_Z))
                             @ Matrix.Rotation(rng.uniform(0, 6.28), 4, "Z")
                             @ Matrix.Scale(rng.uniform(0.85, 1.15), 4)])
        trees += 1

    # rocks: 6, scattered on the rim
    rocks = 0
    attempts = 0
    while rocks < 6 and attempts < 2000:
        attempts += 1
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(20.0, 27.5)
        x, y = r * math.cos(a), r * math.sin(a)
        if not free_spot(x, y, 3.0, True):
            continue
        placed.append((x, y))
        before = len(bm.faces)
        sx, sy, sz = rng.uniform(0.9, 2.0), rng.uniform(0.8, 1.7), rng.uniform(0.5, 1.1)
        m = (Matrix.Translation((x, y, PEAK_Z + sz * 0.35))
             @ Matrix.Rotation(rng.uniform(0, 6.28), 4, "Z")
             @ Matrix.Diagonal((sx, sy, sz, 1.0)))
        add_icosphere(bm, m, subdiv=1)
        bm.faces.ensure_lookup_table()
        for f in bm.faces[before:]:
            f.material_index = 3
            for v in f.verts:
                v.co += Vector((rng.uniform(-0.12, 0.12),
                                rng.uniform(-0.12, 0.12),
                                rng.uniform(-0.10, 0.10)))
        rocks += 1

    me = bpy.data.meshes.new("MountAbu_VegetationMesh")
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new("MountAbu_Vegetation", me)
    bpy.context.scene.collection.objects.link(ob)
    for m in materials:
        me.materials.append(m)
    print(f"  vegetation: {trees} trees + {rocks} rocks")
    return ob


# ---------------------------------------------------------------------------
# 8. Collision proxy
# ---------------------------------------------------------------------------

def build_collision(terrain, road):
    col = terrain.copy()
    col.data = terrain.data.copy()
    col.name = "MountAbu_Collision"
    col.data.name = "MountAbu_CollisionMesh"
    bpy.context.scene.collection.objects.link(col)

    mod = col.modifiers.new("CollisionDecimate", "DECIMATE")
    mod.decimate_type = "DISSOLVE"
    mod.angle_limit = math.radians(4.0)
    mod.use_dissolve_boundaries = False
    apply_modifier(col, mod)

    road_col = road.copy()
    road_col.data = road.data.copy()
    road_col.name = "MountAbu_CollisionRoad"
    road_col.data.name = "MountAbu_CollisionRoadMesh"
    bpy.context.scene.collection.objects.link(road_col)

    # join both into one collision object
    bpy.ops.object.select_all(action="DESELECT")
    col.select_set(True)
    road_col.select_set(True)
    bpy.context.view_layer.objects.active = col
    bpy.ops.object.join()

    col.data.materials.clear()
    proxy = solid_material("Collision_Proxy", (0.55, 0.20, 0.65), 1.0)
    col.data.materials.append(proxy)
    for p in col.data.polygons:
        p.material_index = 0
    col["collision"] = True
    col["kind"] = "concave-mesh-collider"
    print(f"  collision proxy: {triangle_count(col):,} tris")
    return col


# ---------------------------------------------------------------------------
# 9. Export + verification
# ---------------------------------------------------------------------------

def export_glb(path: str, selection_only: bool = False) -> str:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    kwargs = dict(
        filepath=path,
        export_format="GLB",
        export_image_format="JPEG",
        export_lights=False,
        export_cameras=False,
        export_extras=True,
        export_apply=True,
        export_yup=True,
        use_selection=selection_only,
    )
    try:
        bpy.ops.export_scene.gltf(export_image_quality=90, **kwargs)
    except TypeError:
        bpy.ops.export_scene.gltf(**kwargs)
    if not os.path.isfile(path):
        raise RuntimeError(f"export failed: {path}")
    return path


def analyse_glb(path: str) -> dict:
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"glTF":
        raise RuntimeError("not a GLB")
    json_len = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20:20 + json_len])
    tris = 0
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if prim.get("mode", 4) != 4:
                continue
            if "indices" in prim:
                tris += gltf["accessors"][prim["indices"]]["count"] // 3
            else:
                tris += gltf["accessors"][prim["attributes"]["POSITION"]]["count"] // 3
    return {
        "bytes": len(data),
        "tris": tris,
        "materials": len(gltf.get("materials", [])),
        "images": len(gltf.get("images", [])),
        "meshes": len(gltf.get("meshes", [])),
        "nodes": [n.get("name", "?") for n in gltf.get("nodes", [])],
    }


def verify(terrain, road_pts, grade, knots, road_obj, water_obj, min_radius=0.0):
    me = terrain.data
    n = len(me.vertices)
    co = np.empty((n, 3))
    me.vertices.foreach_get("co", co.ravel())
    x, y, z = co[:, 0], co[:, 1], co[:, 2]
    r = np.hypot(x, y)

    minx, maxx = float(x.min()), float(x.max())
    miny, maxy = float(y.min()), float(y.max())
    minz, maxz = float(z.min()), float(z.max())

    top = np.abs(z[(r > LAKE_R + 1.0) & (r < 28.5)] - PEAK_Z)
    border = np.abs(z[(np.abs(x) >= BORDER_R - 1e-6) | (np.abs(y) >= BORDER_R - 1e-6)])

    # cliff slope from the analytic profile
    rs = np.linspace(PLATEAU_R, CLIFF_OUT_R, 2001)
    zz = radial_profile(rs)
    slopes = np.abs(np.gradient(zz, rs))
    ang_all = np.degrees(np.arctan(slopes))
    wall = (rs > PLATEAU_R + 0.10 * CLIFF_BAND) & (rs < CLIFF_OUT_R - 0.10 * CLIFF_BAND)
    ang = ang_all[wall]

    max_grade = float(np.max(grade))
    road_len = float(np.sum(np.linalg.norm(np.diff(road_pts, axis=0), axis=1)))

    bad_normals = 0
    for poly in me.polygons:
        if poly.normal.z < -0.9:
            bad_normals += 1

    report = {
        "upward_faces_pct": round(100.0 * sum(1 for p in me.polygons if p.normal.z > 0) / len(me.polygons), 1),
        "footprint_m": (round(maxx - minx, 3), round(maxy - miny, 3)),
        "height_m": (round(minz, 3), round(maxz, 3)),
        "plateau_max_deviation_m": float(top.max()) if top.size else 0.0,
        "border_max_deviation_m": float(border.max()) if border.size else 0.0,
        "cliff_angle_deg": {
            "min": round(float(ang.min()), 2),
            "mean": round(float(ang.mean()), 2),
            "max": round(float(ang_all.max()), 2),
            "note": "min/mean over the wall (10-90% of the band), max over all", 
        },
        "road_length_m": round(road_len, 1),
        "road_min_turn_radius_m": round(min_radius, 1),
        "road_max_grade_deg": round(max_grade, 2),
        "road_tris": triangle_count(road_obj),
        "lake": {"radius_m": LAKE_R, "floor_z": LAKE_FLOOR_Z, "water_z": WATER_Z},
        "terrain_tris": triangle_count(terrain),
    }

    assert abs((maxx - minx) - TILE) < 1e-6, "footprint must be 150 m"
    assert abs((maxy - miny) - TILE) < 1e-6, "footprint must be 150 m"
    assert report["plateau_max_deviation_m"] < 1e-6, "plateau is not level"
    assert report["border_max_deviation_m"] < 1e-6, "border is not flat at Z=0"
    assert max_grade <= MAX_GRADE_DEG, f"road grade {max_grade:.2f} deg > 15 deg"
    assert road_len >= 100.0, "road shorter than 100 m"
    assert 70.0 <= float(ang_all.max()) <= 82.0, "cliff face outside 70-80 deg"
    assert abs(water_obj.data.vertices[0].co.z - WATER_Z) < 1e-6
    return report


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> int:
    reset_scene()

    print("[1/9] height field")
    terrain = build_terrain()
    me = terrain.data
    n = len(me.vertices)
    co = np.empty((n, 3))
    me.vertices.foreach_get("co", co.ravel())
    z_nat = co[:, 2].copy()

    print("[2/9] Bezier corniche")
    road_pts, s, grade, knots, min_radius = build_road_centreline()
    print(f"  centre line {len(road_pts)} samples, {s[-1]:.1f} m long, "
          f"max grade {grade.max():.2f} deg, min plan radius {min_radius:.1f} m")

    print("[3/9] carve road bench")
    carve_road(terrain, road_pts, z_nat)

    smooth_cut_edges(terrain, road_pts)
    relax_cliff(terrain)

    print("[4/9] dissolve flat regions")
    planar_decimate(terrain, 1.0)

    print("[5/9] Nakki Lake")
    cut_lake(terrain)
    cleanup_degenerate(terrain)
    recalc_normals(terrain)
    wall, floor, water = build_basin_and_water()

    print("[6/9] materials + UVs")
    grass = textured_material("MountAbu_Grass", "grass_1k.png", (0.72, 0.98, 0.55), 0.92)
    rock = textured_material("MountAbu_Rock", "rock_stone_1k.png", (1.0, 0.94, 0.86), 0.88)
    lake_rock = solid_material("MountAbu_LakeRock", (0.30, 0.28, 0.25), 0.85)
    asphalt = solid_material("MountAbu_Asphalt", (0.055, 0.058, 0.062), 0.88)
    line = solid_material("MountAbu_RoadLine", (0.86, 0.84, 0.74), 0.7)
    concrete = solid_material("MountAbu_BarrierConcrete", (0.66, 0.65, 0.62), 0.85)
    water_mat = solid_material("MountAbu_Water", (0.045, 0.26, 0.42), 0.12, 0.0)
    trunk = solid_material("MountAbu_Trunk", (0.20, 0.14, 0.09), 0.9)
    leaf_a = solid_material("MountAbu_LeafA", (0.07, 0.28, 0.11), 0.82)
    leaf_b = solid_material("MountAbu_LeafB", (0.12, 0.38, 0.14), 0.82)
    prop_rock = solid_material("MountAbu_Boulder", (0.34, 0.32, 0.29), 0.9)

    assign_terrain_materials(terrain, grass, rock, road_pts)
    for ob in (wall, floor):
        set_materials(ob, [lake_rock])
    set_materials(water, [water_mat])
    shade_flat(wall)
    shade_flat(floor)
    shade_flat(water)

    print("[7/9] road, markings, barriers")
    road = ribbon_from_centreline(road_pts, ROAD_W, ROAD_LIFT, "MountAbu_Road")
    shrinkwrap_project(road, terrain, ROAD_LIFT)
    rung_z = flatten_road_rungs(road, road_pts[:, 2] + ROAD_LIFT)
    set_materials(road, [asphalt])
    shade_flat(road)

    line_pts = road_pts.copy()
    line_pts[:, 2] = rung_z - ROAD_LIFT
    centre = ribbon_from_centreline(line_pts, 0.26, ROAD_LIFT + 0.03, "MountAbu_RoadLine",
                                    dash=(3, 4))
    set_materials(centre, [line])
    shade_flat(centre)

    barrier_pts = road_pts.copy()
    barrier_pts[:, 2] = rung_z - ROAD_LIFT
    barriers = build_barriers(barrier_pts)
    set_materials(barriers, [concrete])
    shade_flat(barriers)

    print("[8/9] vegetation")
    veg = build_vegetation(road_pts, [trunk, leaf_a, leaf_b, prop_rock])
    shade_flat(veg)

    print("[9/9] collision + export")
    collision = build_collision(terrain, road)

    shade_flat(terrain)

    # tidy hierarchy: everything under one empty, Z up, origin at (0,0,0)
    root = bpy.data.objects.new("TerrainMountAbu", None)
    bpy.context.scene.collection.objects.link(root)
    for props in (terrain, wall, floor, water, road, centre, barriers, veg):
        props["asset"] = "terrain_mount_abu"
    terrain["role"] = "heightfield"
    road["role"] = "road_surface"
    veg["role"] = "vegetation"
    water["role"] = "water"
    wall["role"] = "lake_wall"
    floor["role"] = "lake_floor"
    barriers["role"] = "barriers"

    # measure the grade on the real road surface, not just the centre line
    rme = road.data
    rco = np.empty((len(rme.vertices), 3))
    rme.vertices.foreach_get("co", rco.ravel())
    pairs = len(rco) // 2
    left = rco[0::2]
    right = rco[1::2]
    mids = (left + right) * 0.5
    d = np.diff(mids, axis=0)
    seg = np.linalg.norm(d[:, :2], axis=1)
    surface_grade = np.degrees(np.arctan2(np.abs(d[:, 2]), np.maximum(seg, 1e-6)))
    print(f"  road surface max grade {surface_grade.max():.2f} deg "
          f"(mean {surface_grade.mean():.2f} deg)")
    assert surface_grade.max() <= MAX_GRADE_DEG, "road surface exceeds 15 deg"

    report = verify(terrain, road_pts, grade, knots, road, water, min_radius)
    report["road_surface_max_grade_deg"] = round(float(surface_grade.max()), 2)

    # The collision proxy ships as its own file: glTF exports every object in the
    # scene (hide_render / hide_set are ignored), so it is exported first and then
    # deleted before the visual export.
    bpy.ops.object.select_all(action="DESELECT")
    collision.select_set(True)
    bpy.context.view_layer.objects.active = collision
    export_glb(COLLISION_PATH, selection_only=True)
    cinfo = analyse_glb(COLLISION_PATH)
    report["collision_glb"] = cinfo
    report["collision_mb"] = round(cinfo["bytes"] / 1048576.0, 2)
    bpy.data.objects.remove(collision, do_unlink=True)

    export_glb(OUT_PATH)
    info = analyse_glb(OUT_PATH)
    report["glb"] = info
    report["glb_mb"] = round(info["bytes"] / 1048576.0, 2)
    assert not any("Collision" in n for n in info["nodes"]), "collision leaked into the visual GLB"

    print("\n=== terrain_mount_abu.glb ===")
    print(json.dumps(report, indent=2))
    print(f"  exported -> {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
