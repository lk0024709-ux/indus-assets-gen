#!/usr/bin/env python3
"""Build rigged Battle Royale outfits fitted to the repository's 65-joint superhero models,
plus the standalone modular Battle Royale outfit kit.

Implements the exact geometry, bone-region cutting, solidification, tactical gear
measurements, and linear-RGB palette from `tools/outfit_fit_character.py` and
`tools/outfit_battle_royale.py` using only Python's standard library so CI and
workstations can rebuild all GLB assets without requiring Blender.
"""
from __future__ import annotations

import argparse
import copy
import json
import math
import re
import struct
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
CHARACTER_SOURCE_DIR = ROOT / "Base model " / "Character"
DEFAULT_OUTPUT = ROOT / "procedural_asset_app" / "frontend" / "assets" / "outfits"

GLB_MAGIC = b"glTF"
JSON_CHUNK = 0x4E4F534A
BIN_CHUNK = 0x004E4942

# ---------------- Shared Battle Royale outfit constants ----------------
SLEEVE_T = 0.50
Z_TEE_HEM = 0.53
Z_BELT = 0.575
Z_PANTS_TOP = 0.585
Z_PANTS_BOT = 0.11
Z_BOOT_TOP = 0.16

TEE_OFFS = (0.010, 0.006)
PANTS_OFFS = (0.006, 0.008)
BOOTS_OFFS = (0.003, 0.007)

PALETTE: dict[str, tuple[float, float, float]] = {  # LINEAR RGB
    "tee":     (0.16, 0.19, 0.07),
    "pants":   (0.22, 0.17, 0.08),
    "kneepad": (0.09, 0.11, 0.05),
    "black":   (0.02, 0.02, 0.025),
    "boot":    (0.015, 0.015, 0.02),
    "steel":   (0.65, 0.65, 0.68),
    "gold":    (0.8, 0.55, 0.08),
    "brass":   (0.7, 0.45, 0.1),
}
METALLIC_KEYS = frozenset({"steel", "gold", "brass"})

PIECE_GROUPS: dict[str, str] = {
    "Tee": "tee",
    "Tee_Body": "tee",
    "Tee_Collar": "tee",
    "Tee_Sleeve_R": "tee",
    "Tee_Sleeve_L": "tee",
    "Tee_ChestPatch": "tee",
    "Tee_ChestStar": "tee",
    "Cargo_Pants": "pants",
    "Pants_Hips": "pants",
    "Pants_Leg_R": "pants",
    "Pants_Leg_L": "pants",
    "Cargo_Pocket": "pants",
    "Cargo_Flap": "pants",
    "KneePad_R": "pants",
    "KneePad_L": "pants",
    "Belt": "gear",
    "Belt_Buckle": "gear",
    "Pouch_R": "gear",
    "Pouch_L": "gear",
    "Bullet_0": "gear",
    "Bullet_1": "gear",
    "Bullet_2": "gear",
    "Carabiner": "gear",
    "Holster": "gear",
    "Holster_Strap_0": "gear",
    "Holster_Strap_1": "gear",
    "Boots": "boots",
    "Boot_Shaft_R": "boots",
    "Boot_Shaft_L": "boots",
    "Boot_Foot_R": "boots",
    "Boot_Foot_L": "boots",
    "Boot_Sole_R": "boots",
    "Boot_Sole_L": "boots",
}

HAND_KEYS = ("hand", "thumb", "index", "middle", "ring", "pinky", "pinkie", "finger", "palm")
HEAD_KEYS = ("head", "neck", "jaw", "eye", "tongue", "teeth", "face", "hair")

Vec3 = tuple[float, float, float]
Vec4i = tuple[int, int, int, int]
Vec4f = tuple[float, float, float, float]


def align4(data: bytes | bytearray, pad: bytes = b"\0") -> bytes:
    return bytes(data) + pad * ((-len(data)) % 4)


def srgb_hex_to_linear(hex_color: str) -> Vec3:
    rgb = tuple(int(hex_color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))

    def to_lin(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return (to_lin(rgb[0]), to_lin(rgb[1]), to_lin(rgb[2]))


def norm_bone_name(name: str) -> str:
    name = re.split(r"[:|]", name)[-1]
    return re.sub(r"[^a-z]", "", name.lower())


def region_of(name: str | None) -> str:
    if not name:
        return "other"
    n = norm_bone_name(name)
    if any(k in n for k in HEAD_KEYS):
        return "head"
    if any(k in n for k in HAND_KEYS):
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


# ---------------- Linear algebra & coordinate helpers ----------------
def v_sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def v_add(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def v_scale(a: Vec3, s: float) -> Vec3:
    return (a[0] * s, a[1] * s, a[2] * s)


def v_dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def v_cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def v_norm(a: Vec3) -> Vec3:
    ln = math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
    if ln < 1e-12:
        return (0.0, 1.0, 0.0)
    return (a[0] / ln, a[1] / ln, a[2] / ln)


def blender_to_gltf_pt(p: Vec3) -> Vec3:
    """Convert Blender (x, y, z_up) to glTF (x, y_up, z_forward) via -90 deg X rotation."""
    return (p[0], p[2], -p[1])


def gltf_to_blender_pt(p: Vec3) -> Vec3:
    """Convert glTF (x, y_up, z_forward) to Blender (x, y, z_up)."""
    return (p[0], -p[2], p[1])


def euler_xyz_rotate(p: Vec3, rot: Vec3) -> Vec3:
    rx, ry, rz = rot
    x, y, z = p
    if rx:
        cx, sx = math.cos(rx), math.sin(rx)
        y, z = y * cx - z * sx, y * sx + z * cx
    if ry:
        cy, sy = math.cos(ry), math.sin(ry)
        x, z = x * cy + z * sy, -x * sy + z * cy
    if rz:
        cz, sz = math.cos(rz), math.sin(rz)
        x, y = x * cz - y * sz, x * sz + y * cz
    return (x, y, z)


def transform_blender_verts(
    verts: list[Vec3],
    scale: Vec3,
    rot: Vec3,
    loc: Vec3,
) -> list[Vec3]:
    out: list[Vec3] = []
    for vx, vy, vz in verts:
        scaled = (vx * scale[0], vy * scale[1], vz * scale[2])
        rotated = euler_xyz_rotate(scaled, rot)
        world_b = (rotated[0] + loc[0], rotated[1] + loc[1], rotated[2] + loc[2])
        out.append(blender_to_gltf_pt(world_b))
    return out


def mat4_mul(a: list[list[float]], b: list[list[float]]) -> list[list[float]]:
    return [
        [sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4)]
        for i in range(4)
    ]


def trs_to_mat4(t: list[float], r: list[float], s: list[float]) -> list[list[float]]:
    x, y, z, w = r
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    return [
        [(1.0 - 2.0 * (yy + zz)) * s[0], (2.0 * (xy - wz)) * s[1], (2.0 * (xz + wy)) * s[2], t[0]],
        [(2.0 * (xy + wz)) * s[0], (1.0 - 2.0 * (xx + zz)) * s[1], (2.0 * (yz - wx)) * s[2], t[1]],
        [(2.0 * (xz - wy)) * s[0], (2.0 * (yz + wx)) * s[1], (1.0 - 2.0 * (xx + yy)) * s[2], t[2]],
        [0.0, 0.0, 0.0, 1.0],
    ]


# ---------------- Mesh primitive builders (Blender-equivalent) ----------------
def primitive_box_gltf(loc: Vec3, dim: Vec3, rot: Vec3 = (0.0, 0.0, 0.0)) -> tuple[list[Vec3], list[tuple[int, int, int]]]:
    local_verts: list[Vec3] = [
        (-0.5, -0.5, -0.5),
        ( 0.5, -0.5, -0.5),
        ( 0.5,  0.5, -0.5),
        (-0.5,  0.5, -0.5),
        (-0.5, -0.5,  0.5),
        ( 0.5, -0.5,  0.5),
        ( 0.5,  0.5,  0.5),
        (-0.5,  0.5,  0.5),
    ]
    quads = [
        (0, 3, 2, 1),  # -Z bottom
        (4, 5, 6, 7),  # +Z top
        (0, 1, 5, 4),  # -Y front
        (2, 3, 7, 6),  # +Y back
        (1, 2, 6, 5),  # +X right
        (3, 0, 4, 7),  # -X left
    ]
    tris: list[tuple[int, int, int]] = []
    for a, b, c, d in quads:
        tris.append((a, b, c))
        tris.append((a, c, d))
    return transform_blender_verts(local_verts, dim, rot, loc), tris


def primitive_cylinder_gltf(
    loc: Vec3,
    r_bottom: float,
    r_top: float,
    depth: float,
    vertices: int = 8,
    scale: Vec3 = (1.0, 1.0, 1.0),
    rot: Vec3 = (0.0, 0.0, 0.0),
) -> tuple[list[Vec3], list[tuple[int, int, int]]]:
    hz = depth * 0.5
    local_verts: list[Vec3] = []
    for k in range(vertices):
        ang = 2.0 * math.pi * k / vertices
        ca, sa = math.cos(ang), math.sin(ang)
        local_verts.append((r_bottom * ca, r_bottom * sa, -hz))
    for k in range(vertices):
        ang = 2.0 * math.pi * k / vertices
        ca, sa = math.cos(ang), math.sin(ang)
        local_verts.append((r_top * ca, r_top * sa, hz))
    tris: list[tuple[int, int, int]] = []
    for k in range(vertices):
        k1 = (k + 1) % vertices
        b0, b1 = k, k1
        t0, t1 = vertices + k, vertices + k1
        tris.append((b0, b1, t1))
        tris.append((b0, t1, t0))
    for k in range(1, vertices - 1):
        tris.append((vertices, vertices + k, vertices + k + 1))
        tris.append((0, k + 1, k))
    return transform_blender_verts(local_verts, scale, rot, loc), tris


def primitive_torus_gltf(
    loc: Vec3,
    major_radius: float,
    minor_radius: float,
    major_segments: int = 8,
    minor_segments: int = 4,
    scale: Vec3 = (1.0, 1.0, 1.0),
    rot: Vec3 = (0.0, 0.0, 0.0),
) -> tuple[list[Vec3], list[tuple[int, int, int]]]:
    local_verts: list[Vec3] = []
    for i in range(major_segments):
        phi = 2.0 * math.pi * i / major_segments
        cp, sp = math.cos(phi), math.sin(phi)
        for j in range(minor_segments):
            psi = 2.0 * math.pi * j / minor_segments
            ring_r = major_radius + minor_radius * math.cos(psi)
            local_verts.append((ring_r * cp, ring_r * sp, minor_radius * math.sin(psi)))
    tris: list[tuple[int, int, int]] = []
    for i in range(major_segments):
        i1 = (i + 1) % major_segments
        for j in range(minor_segments):
            j1 = (j + 1) % minor_segments
            p00 = i * minor_segments + j
            p10 = i1 * minor_segments + j
            p11 = i1 * minor_segments + j1
            p01 = i * minor_segments + j1
            tris.append((p00, p10, p11))
            tris.append((p00, p11, p01))
    return transform_blender_verts(local_verts, scale, rot, loc), tris


# ---------------- Solidify & body-cut helpers ----------------
def compute_smooth_normals(verts: list[Vec3], tris: list[tuple[int, int, int]]) -> tuple[list[Vec3], list[Vec3]]:
    v_accum = [[0.0, 0.0, 0.0] for _ in verts]
    f_normals: list[Vec3] = []
    for a, b, c in tris:
        cross = v_cross(v_sub(verts[b], verts[a]), v_sub(verts[c], verts[a]))
        fn = v_norm(cross)
        f_normals.append(fn)
        for vi in (a, b, c):
            v_accum[vi][0] += cross[0]
            v_accum[vi][1] += cross[1]
            v_accum[vi][2] += cross[2]
    v_normals = [v_norm((acc[0], acc[1], acc[2])) for acc in v_accum]
    return v_normals, f_normals


def cut_and_solidify_garment(
    welded_pos_gltf: list[Vec3],
    welded_joints: list[Vec4i],
    welded_weights: list[Vec4f],
    welded_tris: list[tuple[int, int, int]],
    keep_fn: Callable[[int], bool],
    gap: float,
    thickness: float,
    piece_name: str,
) -> tuple[list[Vec3], list[Vec4i], list[Vec4f], list[tuple[int, int, int]]]:
    """Cut faces where all vertices match `keep_fn`, push outward by `gap`, and solidify."""
    n = len(welded_pos_gltf)
    kp = [keep_fn(i) for i in range(n)]
    kept_tris_orig = [t for t in welded_tris if kp[t[0]] and kp[t[1]] and kp[t[2]]]
    if not kept_tris_orig:
        raise RuntimeError(f"{piece_name} came out empty - region/height rules did not match rig.")

    # Compact to active vertices only (equivalent to deleting loose verts in BMesh)
    remap: dict[int, int] = {}
    sub_pos: list[Vec3] = []
    sub_jts: list[Vec4i] = []
    sub_wts: list[Vec4f] = []
    sub_tris: list[tuple[int, int, int]] = []
    for a, b, c in kept_tris_orig:
        tri_mapped = []
        for vi in (a, b, c):
            if vi not in remap:
                remap[vi] = len(sub_pos)
                sub_pos.append(welded_pos_gltf[vi])
                sub_jts.append(welded_joints[vi])
                sub_wts.append(welded_weights[vi])
            tri_mapped.append(remap[vi])
        sub_tris.append((tri_mapped[0], tri_mapped[1], tri_mapped[2]))

    # Step 1: bm.normal_update() + push outward by `gap`
    vn0, _ = compute_smooth_normals(sub_pos, sub_tris)
    inner_pos = [v_add(sub_pos[i], v_scale(vn0[i], gap)) for i in range(len(sub_pos))]

    # Step 2: Solidify(offset=+1.0, thickness=thickness, use_even_offset=True)
    vn1, fn1 = compute_smooth_normals(inner_pos, sub_tris)
    incident_factors: list[list[float]] = [[] for _ in inner_pos]
    for fi, (a, b, c) in enumerate(sub_tris):
        fn = fn1[fi]
        for vi in (a, b, c):
            d = max(v_dot(vn1[vi], fn), 0.4)
            incident_factors[vi].append(min(1.0 / d, 2.0))
    outer_pos: list[Vec3] = []
    for i in range(len(inner_pos)):
        factors = incident_factors[i]
        even_k = sum(factors) / len(factors) if factors else 1.0
        outer_pos.append(v_add(inner_pos[i], v_scale(vn1[i], thickness * even_k)))

    m = len(inner_pos)
    solid_pos = inner_pos + outer_pos
    solid_jts = sub_jts + sub_jts
    solid_wts = sub_wts + sub_wts

    dir_edges = set()
    for a, b, c in sub_tris:
        dir_edges.add((a, b))
        dir_edges.add((b, c))
        dir_edges.add((c, a))
    boundary_half_edges = [(u, v) for (u, v) in dir_edges if (v, u) not in dir_edges]

    solid_tris: list[tuple[int, int, int]] = []
    # Outer shell (CCW outward)
    for a, b, c in sub_tris:
        solid_tris.append((m + a, m + b, m + c))
    # Inner shell (reversed -> CCW inward towards skin)
    for a, b, c in sub_tris:
        solid_tris.append((a, c, b))
    # Boundary rim quads (CCW outward along garment opening)
    for u, v in boundary_half_edges:
        solid_tris.append((u, v, m + v))
        solid_tris.append((u, m + v, m + u))

    return solid_pos, solid_jts, solid_wts, solid_tris


def expand_flat_shaded(
    verts: list[Vec3],
    tris: list[tuple[int, int, int]],
    joints: list[Vec4i] | None = None,
    weights: list[Vec4f] | None = None,
) -> dict[str, Any]:
    """Expand indexed triangles into flat-shaded triangle soup while keeping corner skin weights."""
    out_pos: list[Vec3] = []
    out_nrm: list[Vec3] = []
    out_jts: list[Vec4i] = []
    out_wts: list[Vec4f] = []
    out_idx: list[int] = []
    for a, b, c in tris:
        p0, p1, p2 = verts[a], verts[b], verts[c]
        fn = v_norm(v_cross(v_sub(p1, p0), v_sub(p2, p0)))
        base = len(out_pos)
        out_pos.extend((p0, p1, p2))
        out_nrm.extend((fn, fn, fn))
        if joints is not None and weights is not None:
            out_jts.extend((joints[a], joints[b], joints[c]))
            out_wts.extend((weights[a], weights[b], weights[c]))
        out_idx.extend((base, base + 1, base + 2))
    return {
        "positions": out_pos,
        "normals": out_nrm,
        "joints": out_jts if joints is not None else None,
        "weights": out_wts if weights is not None else None,
        "indices": out_idx,
    }


# ---------------- glTF binary reading / writing ----------------
def read_gltf_accessor(gltf: dict[str, Any], binary: bytes, acc_idx: int) -> list[tuple[Any, ...]]:
    acc = gltf["accessors"][acc_idx]
    bv = gltf["bufferViews"][acc["bufferView"]]
    offset = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
    ncomp = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}[acc["type"]]
    fmt_ch = {5120: "b", 5121: "B", 5122: "h", 5123: "H", 5125: "I", 5126: "f"}[acc["componentType"]]
    stride = bv.get("byteStride", struct.calcsize("<" + fmt_ch * ncomp))
    return [struct.unpack_from("<" + fmt_ch * ncomp, binary, offset + i * stride) for i in range(acc["count"])]


class GlbWriter:
    def __init__(self, material_prefix: str, palette: dict[str, Vec3] | None = None) -> None:
        self.palette = dict(PALETTE if palette is None else palette)
        self.material_prefix = material_prefix
        self.binary = bytearray()
        self.buffer_views: list[dict[str, Any]] = []
        self.accessors: list[dict[str, Any]] = []
        self.materials: list[dict[str, Any]] = []
        self.material_index: dict[str, int] = {}
        self.meshes: list[dict[str, Any]] = []
        self.nodes: list[dict[str, Any]] = []
        self.skins: list[dict[str, Any]] = []

    def ensure_material(self, key: str) -> int:
        if key in self.material_index:
            return self.material_index[key]
        r, g, b = self.palette[key]
        metal = key in METALLIC_KEYS
        idx = len(self.materials)
        self.materials.append({
            "name": f"{self.material_prefix}{key}",
            "doubleSided": True,
            "pbrMetallicRoughness": {
                "baseColorFactor": [round(r, 6), round(g, 6), round(b, 6), 1.0],
                "metallicFactor": 1.0 if metal else 0.0,
                "roughnessFactor": 0.3 if metal else 0.9,
            },
        })
        self.material_index[key] = idx
        return idx

    def append_bytes(self, payload: bytes, target: int | None = None) -> int:
        self.binary.extend(b"\0" * ((-len(self.binary)) % 4))
        view_idx = len(self.buffer_views)
        view: dict[str, Any] = {
            "buffer": 0,
            "byteOffset": len(self.binary),
            "byteLength": len(payload),
        }
        if target is not None:
            view["target"] = target
        self.buffer_views.append(view)
        self.binary.extend(payload)
        return view_idx

    def add_vec3_accessor(self, values: list[Vec3]) -> int:
        raw = bytearray()
        xs = [p[0] for p in values]
        ys = [p[1] for p in values]
        zs = [p[2] for p in values]
        for x, y, z in values:
            raw.extend(struct.pack("<3f", x, y, z))
        view_idx = self.append_bytes(bytes(raw), target=34962)
        acc_idx = len(self.accessors)
        self.accessors.append({
            "bufferView": view_idx,
            "componentType": 5126,
            "count": len(values),
            "type": "VEC3",
            "min": [min(xs), min(ys), min(zs)],
            "max": [max(xs), max(ys), max(zs)],
        })
        return acc_idx

    def add_joints_accessor(self, values: list[Vec4i]) -> int:
        raw = bytearray()
        for j0, j1, j2, j3 in values:
            raw.extend(struct.pack("<4B", j0, j1, j2, j3))
        view_idx = self.append_bytes(bytes(raw), target=34962)
        acc_idx = len(self.accessors)
        self.accessors.append({
            "bufferView": view_idx,
            "componentType": 5121,
            "count": len(values),
            "type": "VEC4",
        })
        return acc_idx

    def add_weights_accessor(self, values: list[Vec4f]) -> int:
        raw = bytearray()
        for w0, w1, w2, w3 in values:
            s = w0 + w1 + w2 + w3
            if s > 1e-8:
                w0, w1, w2, w3 = w0 / s, w1 / s, w2 / s, w3 / s
            else:
                w0, w1, w2, w3 = 1.0, 0.0, 0.0, 0.0
            raw.extend(struct.pack("<4f", w0, w1, w2, w3))
        view_idx = self.append_bytes(bytes(raw), target=34962)
        acc_idx = len(self.accessors)
        self.accessors.append({
            "bufferView": view_idx,
            "componentType": 5126,
            "count": len(values),
            "type": "VEC4",
        })
        return acc_idx

    def add_indices_accessor(self, values: list[int]) -> int:
        use_u32 = max(values, default=0) >= 65535
        raw = bytearray()
        if use_u32:
            for idx in values:
                raw.extend(struct.pack("<I", idx))
            ctype = 5125
        else:
            for idx in values:
                raw.extend(struct.pack("<H", idx))
            ctype = 5123
        view_idx = self.append_bytes(bytes(raw), target=34963)
        acc_idx = len(self.accessors)
        self.accessors.append({
            "bufferView": view_idx,
            "componentType": ctype,
            "count": len(values),
            "type": "SCALAR",
        })
        return acc_idx

    def add_mesh_primitive(
        self,
        name: str,
        mat_key: str,
        verts: list[Vec3],
        tris: list[tuple[int, int, int]],
        joints: list[Vec4i] | None = None,
        weights: list[Vec4f] | None = None,
    ) -> int:
        expanded = expand_flat_shaded(verts, tris, joints=joints, weights=weights)
        attrs: dict[str, int] = {
            "POSITION": self.add_vec3_accessor(expanded["positions"]),
            "NORMAL": self.add_vec3_accessor(expanded["normals"]),
        }
        if expanded["joints"] is not None and expanded["weights"] is not None:
            attrs["JOINTS_0"] = self.add_joints_accessor(expanded["joints"])
            attrs["WEIGHTS_0"] = self.add_weights_accessor(expanded["weights"])
        indices_acc = self.add_indices_accessor(expanded["indices"])
        mat_idx = self.ensure_material(mat_key)
        mesh_idx = len(self.meshes)
        group = PIECE_GROUPS.get(name, "gear")
        self.meshes.append({
            "name": name,
            "extras": {"pieceGroup": group},
            "primitives": [{
                "attributes": attrs,
                "indices": indices_acc,
                "material": mat_idx,
                "mode": 4,
            }],
        })
        return mesh_idx

    def write_glb(self, destination: Path, scene_nodes: list[int], generator: str) -> dict[str, Any]:
        gltf: dict[str, Any] = {
            "asset": {"version": "2.0", "generator": generator},
            "scene": 0,
            "scenes": [{"name": "Scene", "nodes": scene_nodes}],
            "nodes": self.nodes,
            "meshes": self.meshes,
            "materials": self.materials,
            "accessors": self.accessors,
            "bufferViews": self.buffer_views,
            "buffers": [{"byteLength": len(self.binary)}],
        }
        if self.skins:
            gltf["skins"] = self.skins
        destination.parent.mkdir(parents=True, exist_ok=True)
        json_chunk = align4(json.dumps(gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), b" ")
        bin_chunk = align4(self.binary)
        total_len = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
        with destination.open("wb") as out:
            out.write(struct.pack("<4sII", GLB_MAGIC, 2, total_len))
            out.write(struct.pack("<II", len(json_chunk), JSON_CHUNK))
            out.write(json_chunk)
            out.write(struct.pack("<II", len(bin_chunk), BIN_CHUNK))
            out.write(bin_chunk)
        return gltf


# ---------------- 1. Fitted rigged character outfit builder ----------------
def build_fitted_outfit_glb(source_gltf_path: Path, destination: Path) -> dict[str, Any]:
    """Fit the 20-piece Battle Royale outfit onto a 65-joint superhero character and write a rigged GLB."""
    src_gltf = json.loads(source_gltf_path.read_text(encoding="utf-8"))
    src_bin = (source_gltf_path.parent / src_gltf["buffers"][0]["uri"]).read_bytes()

    # Find largest skinned mesh (same rule as outfit_fit_character.py)
    skinned_candidates: list[tuple[int, int, int]] = []
    for n_idx, nd in enumerate(src_gltf["nodes"]):
        if "mesh" in nd and "skin" in nd:
            prim = src_gltf["meshes"][nd["mesh"]]["primitives"][0]
            vcount = src_gltf["accessors"][prim["attributes"]["POSITION"]]["count"]
            skinned_candidates.append((vcount, n_idx, nd["mesh"]))
    if not skinned_candidates:
        raise RuntimeError(f"No skinned mesh found in {source_gltf_path}")
    _, body_node_idx, body_mesh_idx = max(skinned_candidates, key=lambda item: item[0])
    skin_idx = src_gltf["nodes"][body_node_idx]["skin"]
    src_skin = src_gltf["skins"][skin_idx]
    joint_node_indices: list[int] = list(src_skin["joints"])
    joint_names = [src_gltf["nodes"][j]["name"] for j in joint_node_indices]
    joint_index_by_name = {name: i for i, name in enumerate(joint_names)}

    # Compute world matrices of source nodes
    parents: dict[int, int] = {}
    for idx, nd in enumerate(src_gltf["nodes"]):
        for child in nd.get("children", []):
            parents[child] = idx
    world_mats: dict[int, list[list[float]]] = {}

    def get_world(idx: int) -> list[list[float]]:
        if idx not in world_mats:
            nd = src_gltf["nodes"][idx]
            lm = trs_to_mat4(
                nd.get("translation", [0.0, 0.0, 0.0]),
                nd.get("rotation", [0.0, 0.0, 0.0, 1.0]),
                nd.get("scale", [1.0, 1.0, 1.0]),
            )
            world_mats[idx] = mat4_mul(get_world(parents[idx]), lm) if idx in parents else lm
        return world_mats[idx]

    # Bone head & tail in Blender coords (x, -z_gltf, y_gltf)
    bone_heads_b: dict[str, Vec3] = {}
    bone_tails_b: dict[str, Vec3] = {}
    joint_set = set(joint_node_indices)
    for j_i, nidx in enumerate(joint_node_indices):
        wm = get_world(nidx)
        hb = gltf_to_blender_pt((wm[0][3], wm[1][3], wm[2][3]))
        bname = joint_names[j_i]
        bone_heads_b[bname] = hb
        joint_children = [c for c in src_gltf["nodes"][nidx].get("children", []) if c in joint_set]
        if len(joint_children) == 1:
            cwm = get_world(joint_children[0])
            bone_tails_b[bname] = gltf_to_blender_pt((cwm[0][3], cwm[1][3], cwm[2][3]))
        else:
            bone_dir_b = gltf_to_blender_pt((wm[0][1], wm[1][1], wm[2][1]))
            bone_tails_b[bname] = v_add(hb, v_scale(bone_dir_b, 0.1))

    # Read & weld body mesh so UV splits do not create false solidify boundaries
    body_prim = src_gltf["meshes"][body_mesh_idx]["primitives"][0]
    raw_pos: list[Vec3] = [
        (float(x), float(y), float(z))
        for x, y, z in read_gltf_accessor(src_gltf, src_bin, body_prim["attributes"]["POSITION"])
    ]
    raw_jts: list[Vec4i] = [
        (int(a), int(b), int(c), int(d))
        for a, b, c, d in read_gltf_accessor(src_gltf, src_bin, body_prim["attributes"]["JOINTS_0"])
    ]
    raw_wts: list[Vec4f] = [
        (float(a), float(b), float(c), float(d))
        for a, b, c, d in read_gltf_accessor(src_gltf, src_bin, body_prim["attributes"]["WEIGHTS_0"])
    ]
    raw_idx = [int(t[0]) for t in read_gltf_accessor(src_gltf, src_bin, body_prim["indices"])]

    weld_lookup: dict[tuple[int, int, int], int] = {}
    w_pos_gltf: list[Vec3] = []
    w_jts: list[Vec4i] = []
    w_wts: list[Vec4f] = []
    orig_to_weld: list[int] = []
    for pt, ji, wi in zip(raw_pos, raw_jts, raw_wts):
        key = (round(pt[0] * 1_000_000), round(pt[1] * 1_000_000), round(pt[2] * 1_000_000))
        if key not in weld_lookup:
            weld_lookup[key] = len(w_pos_gltf)
            w_pos_gltf.append(pt)
            w_jts.append(ji)
            w_wts.append(wi)
        orig_to_weld.append(weld_lookup[key])

    w_tris: list[tuple[int, int, int]] = []
    seen_tris: set[tuple[int, int, int]] = set()
    for k in range(0, len(raw_idx), 3):
        a, b, c = orig_to_weld[raw_idx[k]], orig_to_weld[raw_idx[k + 1]], orig_to_weld[raw_idx[k + 2]]
        if a != b and b != c and a != c:
            tkey = tuple(sorted((a, b, c)))
            if tkey not in seen_tris:
                seen_tris.add(tkey)
                w_tris.append((a, b, c))

    n_verts = len(w_pos_gltf)
    wv_b = [gltf_to_blender_pt(p) for p in w_pos_gltf]
    used_bones: set[str] = set()
    dom_bone: list[str | None] = []
    reg: list[str] = []
    for ji, wi in zip(w_jts, w_wts):
        for k in range(4):
            if wi[k] > 0:
                used_bones.add(joint_names[ji[k]])
        best_k = max(range(4), key=lambda k: wi[k])
        bname = joint_names[ji[best_k]] if wi[best_k] > 0 else None
        dom_bone.append(bname)
        reg.append(region_of(bname))

    zmin = min(p[2] for p in wv_b)
    zmax = max(p[2] for p in wv_b)
    height_m = zmax - zmin
    scale_k = height_m / 1.75

    def z_at(frac: float) -> float:
        return zmin + frac * height_m

    def band(zf: float, tol: float = 0.012, xs: Callable[[float], bool] | None = None) -> list[Vec3]:
        z0, t = z_at(zf), tol * height_m
        return [p for p in wv_b if abs(p[2] - z0) < t and (xs is None or xs(p[0]))]

    def ext(pts: list[Vec3]) -> tuple[float, float, float, float]:
        if not pts:
            raise RuntimeError("No body vertices at requested height band.")
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), max(xs), min(ys), max(ys)

    wx0, wx1, wy0, wy1 = ext(band(Z_BELT))
    cx, cy = (wx0 + wx1) * 0.5, (wy0 + wy1) * 0.5
    foot_ys = [wv_b[i][1] for i in range(n_verts) if reg[i] in ("foot", "toe")]
    front = 1 if foot_ys and (max(foot_ys) - cy) > (cy - min(foot_ys)) else -1
    right = front

    def leg(sx: int, zf: float, tol: float = 0.015) -> tuple[float, float, float, float]:
        pts = band(zf, tol, lambda x: (x - cx) * sx > 0.02 * height_m)
        x0, x1, y0, y1 = ext(pts)
        return (x0 + x1) * 0.5, (y0 + y1) * 0.5, (x1 - x0) * 0.5, (y1 - y0) * 0.5

    def front_y(x0: float, z0: float, tx: float = 0.03, tz: float = 0.03) -> float:
        ys = [p[1] for p in wv_b if abs(p[0] - x0) < tx * scale_k and abs(p[2] - z0) < tz * scale_k]
        if not ys:
            raise RuntimeError("Could not locate front chest surface.")
        return max(ys) if front > 0 else min(ys)

    def pick_bone(region: str, sx: int | None = None) -> str:
        cands = [bn for bn in joint_names if region_of(bn) == region and bn in used_bones]
        if sx is not None:
            cands = [bn for bn in cands if (bone_heads_b[bn][0] - cx) * sx > 0]
        if not cands:
            raise RuntimeError(f"No '{region}' bone found for side={sx}.")
        return max(cands, key=lambda bn: bone_heads_b[bn][2])

    tt_upperarm: list[float | None] = [None] * n_verts
    for i in range(n_verts):
        if reg[i] == "upperarm" and dom_bone[i]:
            h_pt = bone_heads_b[dom_bone[i]]
            t_pt = bone_tails_b[dom_bone[i]]
            d = v_sub(t_pt, h_pt)
            lsq = max(v_dot(d, d), 1e-9)
            tt_upperarm[i] = v_dot(v_sub(wv_b[i], h_pt), d) / lsq

    # Prepare GLB writer and copy exact 65-joint skeleton hierarchy + IBMs from character
    writer = GlbWriter(material_prefix="Outfit_BR_Fit_M_")

    # Copy nodes for skeleton tree (root -> all 65 joints) and Armature container
    # Identify skeleton root node under Armature
    armature_src_idx = src_gltf["scenes"][src_gltf.get("scene", 0)]["nodes"][0]
    skeleton_node_set: set[int] = set()

    def collect_skeleton_subtree(n_idx: int) -> None:
        if "mesh" in src_gltf["nodes"][n_idx]:
            return
        skeleton_node_set.add(n_idx)
        for ch in src_gltf["nodes"][n_idx].get("children", []):
            collect_skeleton_subtree(ch)

    collect_skeleton_subtree(armature_src_idx)
    sorted_skel_nodes = sorted(skeleton_node_set)
    node_remap = {old_idx: new_idx for new_idx, old_idx in enumerate(sorted_skel_nodes)}
    for old_idx in sorted_skel_nodes:
        src_nd = src_gltf["nodes"][old_idx]
        new_nd: dict[str, Any] = {"name": src_nd.get("name", f"node_{old_idx}")}
        for key in ("translation", "rotation", "scale", "matrix"):
            if key in src_nd:
                new_nd[key] = copy.deepcopy(src_nd[key])
        kept_children = [node_remap[c] for c in src_nd.get("children", []) if c in node_remap]
        if kept_children:
            new_nd["children"] = kept_children
        writer.nodes.append(new_nd)

    armature_out_idx = node_remap[armature_src_idx]

    # Copy exact inverseBindMatrices bytes from source character
    ibm_acc = src_gltf["accessors"][src_skin["inverseBindMatrices"]]
    ibm_bv = src_gltf["bufferViews"][ibm_acc["bufferView"]]
    ibm_start = ibm_bv.get("byteOffset", 0) + ibm_acc.get("byteOffset", 0)
    ibm_bytes = src_bin[ibm_start:ibm_start + ibm_acc["count"] * 64]
    ibm_view_idx = writer.append_bytes(ibm_bytes)
    ibm_acc_idx = len(writer.accessors)
    writer.accessors.append({
        "bufferView": ibm_view_idx,
        "componentType": 5126,
        "count": ibm_acc["count"],
        "type": "MAT4",
    })
    writer.skins.append({
        "name": src_skin.get("name", "Armature"),
        "inverseBindMatrices": ibm_acc_idx,
        "joints": [node_remap[j] for j in joint_node_indices],
    })

    piece_records: list[dict[str, Any]] = []

    def append_skinned_piece(
        name: str,
        mat_key: str,
        verts: list[Vec3],
        tris: list[tuple[int, int, int]],
        joints: list[Vec4i],
        weights: list[Vec4f],
    ) -> None:
        mesh_idx = writer.add_mesh_primitive(name, mat_key, verts, tris, joints=joints, weights=weights)
        node_idx = len(writer.nodes)
        group = PIECE_GROUPS.get(name, "gear")
        writer.nodes.append({
            "name": name,
            "mesh": mesh_idx,
            "skin": 0,
            "extras": {"pieceGroup": group},
        })
        writer.nodes[armature_out_idx].setdefault("children", []).append(node_idx)
        piece_records.append({
            "name": name,
            "group": group,
            "material": mat_key,
            "triangles": len(tris),
            "vertices": len(tris) * 3,
        })

    # 3 fitted garments cut from body mesh
    def keep_tee(i: int) -> bool:
        r, z = reg[i], wv_b[i][2]
        if r in ("spine", "clavicle", "pelvis"):
            return z >= z_at(Z_TEE_HEM)
        if r == "upperarm":
            return tt_upperarm[i] is None or tt_upperarm[i] <= SLEEVE_T
        return False

    def keep_pants(i: int) -> bool:
        return reg[i] in ("pelvis", "thigh", "calf") and z_at(Z_PANTS_BOT) <= wv_b[i][2] <= z_at(Z_PANTS_TOP)

    def keep_boots(i: int) -> bool:
        return reg[i] in ("foot", "toe") or (reg[i] == "calf" and wv_b[i][2] <= z_at(Z_BOOT_TOP))

    for piece_name, keep_fn, offs, mat_key in (
        ("Tee", keep_tee, TEE_OFFS, "tee"),
        ("Cargo_Pants", keep_pants, PANTS_OFFS, "pants"),
        ("Boots", keep_boots, BOOTS_OFFS, "boot"),
    ):
        p_verts, p_jts, p_wts, p_tris = cut_and_solidify_garment(
            w_pos_gltf,
            w_jts,
            w_wts,
            w_tris,
            keep_fn,
            gap=offs[0] * scale_k,
            thickness=offs[1] * scale_k,
            piece_name=piece_name,
        )
        append_skinned_piece(piece_name, mat_key, p_verts, p_tris, p_jts, p_wts)

    # Single-bone detail pieces
    def add_rigid_skinned(
        name: str,
        mat_key: str,
        bone_name: str,
        verts_tris: tuple[list[Vec3], list[tuple[int, int, int]]],
    ) -> None:
        verts, tris = verts_tris
        j_idx = joint_index_by_name[bone_name]
        jts: list[Vec4i] = [(j_idx, 0, 0, 0)] * len(verts)
        wts: list[Vec4f] = [(1.0, 0.0, 0.0, 0.0)] * len(verts)
        append_skinned_piece(name, mat_key, verts, tris, jts, wts)

    pelvis_b = pick_bone("pelvis")
    chest_b = pick_bone("spine")

    bz = z_at(Z_BELT)
    bx0, bx1, by0, by1 = ext(band(Z_BELT))
    bcx, bcy = (bx0 + bx1) * 0.5, (by0 + by1) * 0.5
    brx = (bx1 - bx0) * 0.5 + 0.030 * scale_k
    bry = (by1 - by0) * 0.5 + 0.030 * scale_k

    add_rigid_skinned(
        "Belt", "black", pelvis_b,
        primitive_cylinder_gltf((bcx, bcy, bz), 1.0, 1.0, 0.05 * scale_k, vertices=16, scale=(brx, bry, 1.0)),
    )
    add_rigid_skinned(
        "Belt_Buckle", "black", pelvis_b,
        primitive_box_gltf((bcx, bcy + front * bry, bz), (0.06 * scale_k, 0.02 * scale_k, 0.05 * scale_k)),
    )
    add_rigid_skinned(
        "Pouch_R", "black", pelvis_b,
        primitive_box_gltf(
            (bcx + right * (brx + 0.01 * scale_k), bcy, bz - 0.02 * scale_k),
            (0.05 * scale_k, 0.10 * scale_k, 0.11 * scale_k),
        ),
    )
    add_rigid_skinned(
        "Pouch_L", "black", pelvis_b,
        primitive_box_gltf(
            (bcx - right * (brx + 0.01 * scale_k), bcy, bz - 0.02 * scale_k),
            (0.05 * scale_k, 0.09 * scale_k, 0.10 * scale_k),
        ),
    )
    for i in range(3):
        add_rigid_skinned(
            f"Bullet_{i}", "brass", pelvis_b,
            primitive_cylinder_gltf(
                (bcx + right * (brx + 0.01 * scale_k), bcy + (i - 1) * 0.03 * scale_k, bz + 0.05 * scale_k),
                1.0, 1.0, 0.04 * scale_k, vertices=6, scale=(0.008 * scale_k, 0.008 * scale_k, 1.0),
            ),
        )
    add_rigid_skinned(
        "Carabiner", "steel", pelvis_b,
        primitive_torus_gltf(
            (bcx, bcy + front * (bry + 0.004 * scale_k), bz - 0.04 * scale_k),
            major_radius=0.025 * scale_k,
            minor_radius=0.005 * scale_k,
            major_segments=8,
            minor_segments=4,
            rot=(math.radians(90), 0.0, 0.0),
        ),
    )

    off_pants = (PANTS_OFFS[0] + PANTS_OFFS[1]) * scale_k
    for sx in (right, -right):
        thigh_b = pick_bone("thigh", sx)
        calf_b = pick_bone("calf", sx)
        lx, ly, lrx, _ = leg(sx, 0.40)
        kx, ky, _, kry = leg(sx, 0.28)
        side = "R" if sx == right else "L"
        add_rigid_skinned(
            f"KneePad_{side}", "kneepad", calf_b,
            primitive_box_gltf(
                (kx, ky + front * (kry + off_pants + 0.02 * scale_k), z_at(0.28)),
                (0.13 * scale_k, 0.05 * scale_k, 0.15 * scale_k),
            ),
        )
        if sx == right:
            add_rigid_skinned(
                "Holster", "black", thigh_b,
                primitive_box_gltf(
                    (lx + sx * (lrx + off_pants + 0.02 * scale_k), ly, z_at(0.40)),
                    (0.05 * scale_k, 0.08 * scale_k, 0.20 * scale_k),
                ),
            )
            for j, zf in enumerate((0.45, 0.35)):
                sxc, syc, srx, sry = leg(sx, zf)
                add_rigid_skinned(
                    f"Holster_Strap_{j}", "black", thigh_b,
                    primitive_cylinder_gltf(
                        (sxc, syc, z_at(zf)),
                        1.0, 1.0, 0.03 * scale_k, vertices=8,
                        scale=(srx + off_pants + 0.008 * scale_k, sry + off_pants + 0.008 * scale_k, 1.0),
                    ),
                )
        else:
            add_rigid_skinned(
                "Cargo_Pocket", "pants", thigh_b,
                primitive_box_gltf(
                    (lx + sx * (lrx + off_pants + 0.0225 * scale_k), ly, z_at(0.40)),
                    (0.045 * scale_k, 0.12 * scale_k, 0.16 * scale_k),
                ),
            )
            add_rigid_skinned(
                "Cargo_Flap", "pants", thigh_b,
                primitive_box_gltf(
                    (lx + sx * (lrx + off_pants + 0.0225 * scale_k), ly, z_at(0.40) + 0.09 * scale_k),
                    (0.05 * scale_k, 0.125 * scale_k, 0.04 * scale_k),
                ),
            )

    px = cx - right * 0.075 * scale_k
    pz = z_at(0.74)
    py = front_y(px, pz) + front * ((TEE_OFFS[0] + TEE_OFFS[1]) * scale_k + 0.006 * scale_k)
    add_rigid_skinned(
        "Tee_ChestPatch", "black", chest_b,
        primitive_box_gltf((px, py, pz), (0.07 * scale_k, 0.012 * scale_k, 0.08 * scale_k)),
    )
    add_rigid_skinned(
        "Tee_ChestStar", "gold", chest_b,
        primitive_box_gltf(
            (px, py + front * 0.006 * scale_k, pz),
            (0.03 * scale_k, 0.006 * scale_k, 0.03 * scale_k),
            rot=(0.0, math.radians(45), 0.0),
        ),
    )

    gltf = writer.write_glb(
        destination,
        scene_nodes=[armature_out_idx],
        generator="Indus Battle Royale Outfit Fitter (65-joint rigged GLB)",
    )
    return {
        "file": destination.name,
        "bytes": destination.stat().st_size,
        "pieces": len(piece_records),
        "vertices": sum(p["vertices"] for p in piece_records),
        "triangles": sum(p["triangles"] for p in piece_records),
        "skinned": True,
        "joints": len(joint_node_indices),
        "height_m": round(height_m, 4),
        "materials": [m["name"] for m in gltf["materials"]],
        "piece_details": piece_records,
    }


# ---------------- 2. Standalone modular Battle Royale outfit builder ----------------
def build_standalone_outfit_glb(
    destination: Path,
    *,
    height: float = 1.75,
    palette_overrides: dict[str, Vec3] | None = None,
    include_holster: bool = True,
    include_pouches: bool = True,
    include_boots: bool = True,
) -> dict[str, Any]:
    """Build the 29-piece standalone Outfit_BR GLB from `outfit_battle_royale.py`."""
    k = height / 1.75
    palette = dict(PALETTE)
    if palette_overrides:
        palette.update(palette_overrides)

    writer = GlbWriter(material_prefix="Outfit_BR_M_", palette=palette)
    root_idx = len(writer.nodes)
    writer.nodes.append({"name": "Outfit_BR", "children": []})
    piece_records: list[dict[str, Any]] = []

    def add_piece(name: str, mat_key: str, verts_tris: tuple[list[Vec3], list[tuple[int, int, int]]]) -> None:
        verts, tris = verts_tris
        if k != 1.0:
            verts = [(vx * k, vy * k, vz * k) for vx, vy, vz in verts]
        mesh_idx = writer.add_mesh_primitive(name, mat_key, verts, tris)
        node_idx = len(writer.nodes)
        group = PIECE_GROUPS.get(name, "gear")
        writer.nodes.append({
            "name": name,
            "mesh": mesh_idx,
            "extras": {"pieceGroup": group},
        })
        writer.nodes[root_idx]["children"].append(node_idx)
        piece_records.append({
            "name": name,
            "group": group,
            "material": mat_key,
            "triangles": len(tris),
            "vertices": len(tris) * 3,
        })

    # T-Shirt
    add_piece("Tee_Body", "tee", primitive_cylinder_gltf((0, 0, 1.275), 0.18, 0.18, 0.51, vertices=8, scale=(1.1, 0.7, 1.0)))
    add_piece("Tee_Collar", "tee", primitive_cylinder_gltf((0, 0, 1.53), 0.085, 0.085, 0.035, vertices=8, scale=(1.0, 0.9, 1.0)))
    for s, side in ((1, "R"), (-1, "L")):
        add_piece(
            f"Tee_Sleeve_{side}", "tee",
            primitive_cylinder_gltf((s * 0.285, 0, 1.429), 0.075, 0.075, 0.2, vertices=8, rot=(0.0, s * math.radians(110), 0.0)),
        )
    add_piece("Tee_ChestPatch", "black", primitive_box_gltf((0.075, -0.118, 1.38), (0.07, 0.012, 0.08)))
    add_piece("Tee_ChestStar", "gold", primitive_box_gltf((0.075, -0.125, 1.38), (0.03, 0.006, 0.03), rot=(0.0, math.radians(45), 0.0)))

    # Cargo pants
    add_piece("Pants_Hips", "pants", primitive_cylinder_gltf((0, 0, 0.97), 0.21, 0.21, 0.2, vertices=8, scale=(1.0, 0.65, 1.0)))
    for s, side in ((1, "R"), (-1, "L")):
        add_piece(f"Pants_Leg_{side}", "pants", primitive_cylinder_gltf((s * 0.1, 0, 0.65), 0.10, 0.105, 0.74, vertices=8))
        add_piece(f"KneePad_{side}", "kneepad", primitive_box_gltf((s * 0.1, -0.1, 0.52), (0.13, 0.05, 0.15)))
    add_piece("Cargo_Pocket", "pants", primitive_box_gltf((0.215, -0.01, 0.74), (0.045, 0.12, 0.16)))
    add_piece("Cargo_Flap", "pants", primitive_box_gltf((0.22, -0.01, 0.82), (0.05, 0.125, 0.04)))

    if include_holster:
        add_piece("Holster", "black", primitive_box_gltf((-0.215, 0, 0.78), (0.05, 0.08, 0.2)))
        for i, z in enumerate((0.88, 0.72)):
            add_piece(f"Holster_Strap_{i}", "black", primitive_cylinder_gltf((-0.1, 0, z), 0.108, 0.108, 0.03, vertices=8))

    # Belt + pouches
    add_piece("Belt", "black", primitive_cylinder_gltf((0, 0, 1.04), 0.225, 0.225, 0.07, vertices=12, scale=(1.0, 0.7, 1.0)))
    add_piece("Belt_Buckle", "black", primitive_box_gltf((0, -0.16, 1.04), (0.06, 0.02, 0.05)))
    if include_pouches:
        add_piece("Pouch_R", "black", primitive_box_gltf((0.25, -0.01, 1.0), (0.05, 0.1, 0.11)))
        add_piece("Pouch_L", "black", primitive_box_gltf((-0.25, -0.01, 1.0), (0.05, 0.09, 0.1)))
        for i in range(3):
            add_piece(f"Bullet_{i}", "brass", primitive_cylinder_gltf((0.25, -0.04 + i * 0.03, 1.07), 0.008, 0.008, 0.04, vertices=6))
    add_piece(
        "Carabiner", "steel",
        primitive_torus_gltf((0, -0.15, 0.975), 0.025, 0.005, major_segments=8, minor_segments=4, rot=(math.radians(90), 0.0, 0.0)),
    )

    if include_boots:
        for s, side in ((1, "R"), (-1, "L")):
            add_piece(f"Boot_Shaft_{side}", "boot", primitive_cylinder_gltf((s * 0.1, 0, 0.16), 0.086, 0.096, 0.28, vertices=8))
            add_piece(f"Boot_Foot_{side}", "boot", primitive_box_gltf((s * 0.1, -0.065, 0.06), (0.178, 0.26, 0.06)))
            add_piece(f"Boot_Sole_{side}", "black", primitive_box_gltf((s * 0.1, -0.065, 0.015), (0.188, 0.28, 0.03)))

    gltf = writer.write_glb(
        destination,
        scene_nodes=[root_idx],
        generator="Indus Battle Royale Standalone Outfit Kit (Outfit_BR)",
    )
    return {
        "file": destination.name,
        "bytes": destination.stat().st_size,
        "pieces": len(piece_records),
        "vertices": sum(p["vertices"] for p in piece_records),
        "triangles": sum(p["triangles"] for p in piece_records),
        "skinned": False,
        "joints": 0,
        "height_m": round(height, 4),
        "materials": [m["name"] for m in gltf["materials"]],
        "piece_details": piece_records,
    }


# ---------------- 3. Binary GLB combiner (Character + Fitted Outfit) ----------------
def parse_glb_chunks(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if len(raw) < 28:
        raise ValueError(f"GLB is too short: {path}")
    magic, version, total_len = struct.unpack_from("<4sII", raw, 0)
    if magic != GLB_MAGIC or version != 2 or total_len != len(raw):
        raise ValueError(f"Invalid GLB header: {path}")
    json_len, json_type = struct.unpack_from("<II", raw, 12)
    if json_type != JSON_CHUNK:
        raise ValueError(f"Missing JSON chunk in {path}")
    gltf = json.loads(raw[20:20 + json_len].decode("utf-8").rstrip(" \0"))
    bin_off = 20 + json_len
    bin_len, bin_type = struct.unpack_from("<II", raw, bin_off)
    if bin_type != BIN_CHUNK:
        raise ValueError(f"Missing BIN chunk in {path}")
    return gltf, raw[bin_off + 8:bin_off + 8 + bin_len]


def pack_character_with_outfit(
    character_glb_path: Path,
    outfit_glb_path: Path,
    destination_path: Path,
    *,
    included_groups: set[str] | None = None,
) -> dict[str, Any]:
    """Merge a packed superhero GLB and its fitted outfit GLB onto the shared 65-joint skin."""
    char_gltf, char_bin = parse_glb_chunks(character_glb_path)
    out_gltf, out_bin = parse_glb_chunks(outfit_glb_path)

    char_joints = [char_gltf["nodes"][j]["name"] for j in char_gltf["skins"][0]["joints"]]
    out_joints = [out_gltf["nodes"][j]["name"] for j in out_gltf["skins"][0]["joints"]]
    if char_joints != out_joints:
        raise ValueError("Character and outfit joint lists do not match.")

    combined_bin = bytearray(align4(char_bin))
    bin_offset = len(combined_bin)
    combined_bin.extend(out_bin)

    bv_offset = len(char_gltf["bufferViews"])
    for bv in out_gltf["bufferViews"]:
        new_bv = copy.deepcopy(bv)
        new_bv["buffer"] = 0
        new_bv["byteOffset"] = new_bv.get("byteOffset", 0) + bin_offset
        char_gltf["bufferViews"].append(new_bv)

    acc_offset = len(char_gltf["accessors"])
    for acc in out_gltf["accessors"]:
        new_acc = copy.deepcopy(acc)
        new_acc["bufferView"] = new_acc["bufferView"] + bv_offset
        char_gltf["accessors"].append(new_acc)

    mat_offset = len(char_gltf["materials"])
    for mat in out_gltf["materials"]:
        char_gltf["materials"].append(copy.deepcopy(mat))

    armature_idx = char_gltf["scenes"][char_gltf.get("scene", 0)]["nodes"][0]
    added_pieces = 0
    for nd in out_gltf["nodes"]:
        if "mesh" not in nd:
            continue
        src_mesh = out_gltf["meshes"][nd["mesh"]]
        group = (nd.get("extras") or src_mesh.get("extras") or {}).get("pieceGroup", "gear")
        if included_groups is not None and group not in included_groups:
            continue
        new_mesh = copy.deepcopy(src_mesh)
        for prim in new_mesh["primitives"]:
            prim["attributes"] = {k: v + acc_offset for k, v in prim["attributes"].items()}
            if "indices" in prim:
                prim["indices"] = prim["indices"] + acc_offset
            if "material" in prim:
                prim["material"] = prim["material"] + mat_offset
        mesh_idx = len(char_gltf["meshes"])
        char_gltf["meshes"].append(new_mesh)
        node_idx = len(char_gltf["nodes"])
        char_gltf["nodes"].append({
            "name": nd["name"],
            "mesh": mesh_idx,
            "skin": 0,
            "extras": {"pieceGroup": group},
        })
        char_gltf["nodes"][armature_idx].setdefault("children", []).append(node_idx)
        added_pieces += 1

    char_gltf["buffers"][0]["byteLength"] = len(combined_bin)
    char_gltf.setdefault("asset", {})["generator"] = (
        "Indus Superhero + Battle Royale Outfit GLB Combiner (source PBR + 65-joint rig preserved)"
    )

    destination_path.parent.mkdir(parents=True, exist_ok=True)
    json_chunk = align4(json.dumps(char_gltf, separators=(",", ":"), ensure_ascii=False).encode("utf-8"), b" ")
    bin_chunk = align4(combined_bin)
    total_len = 12 + 8 + len(json_chunk) + 8 + len(bin_chunk)
    with destination_path.open("wb") as out:
        out.write(struct.pack("<4sII", GLB_MAGIC, 2, total_len))
        out.write(struct.pack("<II", len(json_chunk), JSON_CHUNK))
        out.write(json_chunk)
        out.write(struct.pack("<II", len(bin_chunk), BIN_CHUNK))
        out.write(bin_chunk)
    return {
        "file": destination_path.name,
        "bytes": destination_path.stat().st_size,
        "added_pieces": added_pieces,
    }


def build_all_outfits(output_dir: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    female_record = build_fitted_outfit_glb(
        CHARACTER_SOURCE_DIR / "Superhero_Female_FullBody.gltf",
        output_dir / "outfit_br_female.glb",
    )
    female_record.update({
        "id": "outfit_br_female",
        "label": "Battle Royale Outfit · Female Fit",
        "target": "female",
        "description": "20-piece tactical tee, cargo pants, belt, pouches, holster, knee pads, and combat boots fitted & skinned to the 65-joint female superhero rig.",
    })

    male_record = build_fitted_outfit_glb(
        CHARACTER_SOURCE_DIR / "Superhero_Male_FullBody.gltf",
        output_dir / "outfit_br_male.glb",
    )
    male_record.update({
        "id": "outfit_br_male",
        "label": "Battle Royale Outfit · Male Fit",
        "target": "male",
        "description": "20-piece tactical tee, cargo pants, belt, pouches, holster, knee pads, and combat boots fitted & skinned to the 65-joint male superhero rig.",
    })

    standalone_record = build_standalone_outfit_glb(output_dir / "outfit_battle_royale.glb")
    standalone_record.update({
        "id": "outfit_battle_royale",
        "label": "Battle Royale Outfit · Standalone Kit",
        "target": "standalone",
        "description": "29-piece low-poly modular Outfit_BR kit (tee, collar, sleeves, cargo pants, belt, pouches, holster, brass bullets, steel carabiner, boots) with no body.",
    })

    manifest = {
        "title": "Indus Battle Royale Character Outfits",
        "source_scripts": [
            "tools/outfit_fit_character.py",
            "tools/outfit_battle_royale.py",
        ],
        "units": "metres",
        "groups": [
            {"id": "tee", "label": "Tee + Star"},
            {"id": "pants", "label": "Cargo Pants"},
            {"id": "gear", "label": "Belt + Holster"},
            {"id": "boots", "label": "Combat Boots"},
        ],
        "outfits": [female_record, male_record, standalone_record],
    }
    manifest_path = output_dir / "outfits.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--pack-combined-dir",
        type=Path,
        default=None,
        help="Optional directory to also write combined character+outfit GLBs for all 4 heroes.",
    )
    args = parser.parse_args()
    manifest = build_all_outfits(args.output_dir)
    for item in manifest["outfits"]:
        print(
            f"Built {item['file']}: {item['pieces']} pieces, {item['triangles']:,} tris, "
            f"{item['bytes']:,} bytes (skinned={item['skinned']})"
        )
    print(f"Wrote {args.output_dir / 'outfits.json'}")

    if args.pack_combined_dir is not None:
        char_dir = ROOT / "procedural_asset_app" / "frontend" / "assets" / "characters"
        for hero_id in (
            "superhero_female_dark",
            "superhero_female_light",
            "superhero_male_dark",
            "superhero_male_light",
        ):
            outfit_name = "outfit_br_female.glb" if "female" in hero_id else "outfit_br_male.glb"
            res = pack_character_with_outfit(
                char_dir / f"{hero_id}.glb",
                args.output_dir / outfit_name,
                args.pack_combined_dir / f"{hero_id}_battle_royale.glb",
            )
            print(f"Combined {res['file']}: {res['bytes']:,} bytes ({res['added_pieces']} outfit pieces)")


if __name__ == "__main__":
    main()
