#!/usr/bin/env python3
"""Procedural building generator for the Indus : Battle Royale 3D pipeline.

Generates the four Building-category assets with AI-generated PBR textures,
headless through the pip-installable ``bpy`` module (Blender as a Python
module).

Every building follows the same rules:

* real-world scale in metres, Z-up while building;
* the object origin sits exactly at the **bottom-centre** (0, 0, 0) of the
  footprint, with the model resting on z = 0;
* every mesh is unwrapped with ``bpy.ops.uv.smart_project()`` before the
  material is assigned, then normalised to a constant texel density so the
  textures tile at a believable physical size;
* each material is a Principled BSDF whose Base Color comes from an
  ``Image Texture`` node loaded from ``docs/textures/*.png``.  Images are
  packed so they travel inside the exported ``.glb``.

Run from the repository root:

    pip install bpy
    python tools/generate_buildings.py
"""

from __future__ import annotations

import math
import os
import sys

import bpy
from mathutils import Vector

# --- Paths -----------------------------------------------------------------
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURE_DIR = os.path.join(REPO_ROOT, "docs", "textures")
OUTPUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "buildings")

# --- Texture-driven materials ----------------------------------------------
# name -> (image file, world size in metres covered by one UV tile, roughness,
#          metallic)
MATERIALS = {
    "concrete": ("concrete_wall.png", 2.5, 0.90, 0.0),
    "brick": ("brick_wall.png", 1.6, 0.85, 0.0),
    "wood": ("wood_plank.png", 2.0, 0.80, 0.0),
    "metal": ("metal_corrugated.png", 2.4, 0.45, 0.85),
}

# Opening heights are measured from the floor the wall stands on.
EPS = 1e-3


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------
def reset_scene() -> None:
    """Start from a completely empty scene."""
    bpy.ops.wm.read_factory_settings(use_empty=True)


def ensure_dirs() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Primitives
# ---------------------------------------------------------------------------
def add_box(
    name: str,
    size: tuple[float, float, float],
    center: tuple[float, float, float],
) -> bpy.types.Object:
    """Add an axis-aligned box defined by its full size and centre point."""
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    sx, sy, sz = (s / 2.0 for s in size)
    verts = [
        (-sx, -sy, -sz), (sx, -sy, -sz), (sx, sy, -sz), (-sx, sy, -sz),
        (-sx, -sy, sz), (sx, -sy, sz), (sx, sy, sz), (-sx, sy, sz),
    ]
    faces = [
        (0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4),
        (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7),
    ]
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = center
    bpy.context.collection.objects.link(obj)
    return obj


def add_prism(
    name: str,
    footprint: tuple[float, float],
    eave_z: float,
    ridge_z: float,
) -> bpy.types.Object:
    """Add a solid gable-roof prism: rectangular base with a ridge along X."""
    hx, hy = footprint[0] / 2.0, footprint[1] / 2.0
    verts = [
        (-hx, -hy, eave_z), (hx, -hy, eave_z), (hx, hy, eave_z), (-hx, hy, eave_z),
        (-hx, 0.0, ridge_z), (hx, 0.0, ridge_z),
    ]
    faces = [
        (0, 3, 2, 1),      # underside
        (0, 1, 5, 4),      # front slope
        (3, 4, 5, 2),      # back slope
        (0, 4, 3),         # left gable
        (1, 2, 5),         # right gable
    ]
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def add_strut(
    name: str,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    thickness: float,
) -> bpy.types.Object:
    """Add a square-section beam running from ``start`` to ``end``."""
    p1, p2 = Vector(start), Vector(end)
    direction = p2 - p1
    length = direction.length
    obj = add_box(name, (thickness, thickness, length), (0.0, 0.0, 0.0))
    obj.location = (p1 + p2) / 2.0
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
    return obj


# ---------------------------------------------------------------------------
# Booleans
# ---------------------------------------------------------------------------
def cut_opening(
    wall: bpy.types.Object,
    width: float,
    height: float,
    center_x: float,
    base_z: float,
    depth: float,
) -> None:
    """Boolean-subtract a door/window box from a wall object."""
    cutter = add_box(
        f"{wall.name}_cutter",
        (width, depth, height),
        (center_x, wall.location.y, base_z + height / 2.0),
    )
    cutter.location = (center_x, wall.location.y, base_z + height / 2.0)

    mod = wall.modifiers.new(name="Opening", type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter

    with bpy.context.temp_override(
        object=wall, active_object=wall, selected_objects=[wall], selected_editable_objects=[wall]
    ):
        bpy.ops.object.modifier_apply(modifier=mod.name)

    bpy.data.objects.remove(cutter, do_unlink=True)


def cut_side_opening(
    wall: bpy.types.Object,
    width: float,
    height: float,
    center_y: float,
    base_z: float,
    depth: float,
) -> None:
    """Same as :func:`cut_opening` but for walls whose thickness runs along X."""
    cutter = add_box(
        f"{wall.name}_cutter",
        (depth, width, height),
        (wall.location.x, center_y, base_z + height / 2.0),
    )
    mod = wall.modifiers.new(name="Opening", type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter
    with bpy.context.temp_override(
        object=wall, active_object=wall, selected_objects=[wall], selected_editable_objects=[wall]
    ):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
def build_material(key: str) -> bpy.types.Material:
    """Principled BSDF + Image Texture (Base Color), image packed into the file."""
    filename, tile_m, roughness, metallic = MATERIALS[key]
    image_path = os.path.join(TEXTURE_DIR, filename)
    if not os.path.isfile(image_path):
        raise FileNotFoundError(
            f"missing texture {image_path} - run tools/make_seamless.py first"
        )

    mat = bpy.data.materials.new(name=f"M_{key}")
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    out.location = (420, 0)
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (120, 0)
    tex = nodes.new("ShaderNodeTexImage")
    tex.location = (-220, 0)

    image = bpy.data.images.load(image_path, check_existing=True)
    image.colorspace_settings.name = "sRGB"
    image.pack()  # embed the pixels so export_image_format can inline them
    tex.image = image
    tex.interpolation = "Linear"
    tex.extension = "REPEAT"

    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)

    links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


# ---------------------------------------------------------------------------
# UV unwrap + texel-density normalisation
# ---------------------------------------------------------------------------
def smart_unwrap(obj: bpy.types.Object, tile_m: float) -> None:
    """Unwrap with Smart UV Project, then scale UVs to a physical tile size.

    ``bpy.ops.uv.smart_project`` packs every island into 0..1, so the number
    of texture repeats has no relation to the real-world size of the mesh.
    After unwrapping we measure the surface area per UV unit and rescale all
    UVs so one texture tile covers ``tile_m`` metres on the model.
    """
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)

    with bpy.context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(
            angle_limit=math.radians(66.0),
            island_margin=0.015,
            area_weight=0.0,
            correct_aspect=True,
            scale_to_bounds=False,
        )
        bpy.ops.object.mode_set(mode="OBJECT")

    mesh = obj.data
    uv = mesh.uv_layers.active.data
    ratios = []
    for poly in mesh.polygons:
        world_area = poly.area
        if world_area <= 1e-9:
            continue
        uvs = [uv[li].uv for li in poly.loop_indices]
        uv_area = 0.0
        for i in range(1, len(uvs) - 1):
            uv_area += abs(
                (uvs[i] - uvs[0]).cross(uvs[i + 1] - uvs[0])
            ) / 2.0
        if uv_area > 1e-12:
            # metres of surface represented by one UV unit
            ratios.append(math.sqrt(world_area / uv_area))

    if not ratios:
        raise RuntimeError(f"could not measure UV density on {obj.name}")

    ratios.sort()
    metres_per_uv = ratios[len(ratios) // 2]
    # 1 UV unit currently spans ``metres_per_uv`` metres; we want it to span
    # exactly ``tile_m`` metres, so UVs get longer when the mesh is bigger.
    factor = metres_per_uv / tile_m
    for loop in uv:
        loop.uv = (loop.uv.x * factor, loop.uv.y * factor)

    # Re-measure and fail loudly if the real-world texel density is off.
    ratios_after = []
    for poly in mesh.polygons:
        world_area = poly.area
        uvs = [uv[li].uv for li in poly.loop_indices]
        uv_area = 0.0
        for i in range(1, len(uvs) - 1):
            uv_area += abs((uvs[i] - uvs[0]).cross(uvs[i + 1] - uvs[0])) / 2.0
        if world_area > 1e-9 and uv_area > 1e-12:
            ratios_after.append(math.sqrt(world_area / uv_area))
    ratios_after.sort()
    achieved = ratios_after[len(ratios_after) // 2]
    if not (0.9 * tile_m <= achieved <= 1.1 * tile_m):
        raise AssertionError(
            f"{obj.name}: texel density {achieved:.3f} m/UV, expected ~{tile_m:.2f} m/UV"
        )


# ---------------------------------------------------------------------------
# Assembly helpers
# ---------------------------------------------------------------------------
def join(objects: list[bpy.types.Object], name: str) -> bpy.types.Object:
    """Join parts into one game-ready object, keeping material slots."""
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    with bpy.context.temp_override(
        active_object=objects[0],
        selected_objects=objects,
        selected_editable_objects=objects,
    ):
        bpy.ops.object.join()
    merged = bpy.context.view_layer.objects.active
    merged.name = name
    merged.data.name = f"{name}Mesh"
    # Bake the remaining object transform into the mesh so every later
    # measurement works in plain world coordinates.
    with bpy.context.temp_override(
        active_object=merged, selected_objects=[merged], selected_editable_objects=[merged]
    ):
        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return merged


def set_origin_bottom_center(obj: bpy.types.Object) -> None:
    """Move mesh data so the origin is at the bottom-centre of the footprint."""
    mesh = obj.data
    coords = [v.co for v in mesh.vertices]
    min_x = min(c.x for c in coords)
    max_x = max(c.x for c in coords)
    min_y = min(c.y for c in coords)
    max_y = max(c.y for c in coords)
    min_z = min(c.z for c in coords)

    offset = Vector((-(min_x + max_x) / 2.0, -(min_y + max_y) / 2.0, -min_z))
    for v in mesh.vertices:
        v.co += offset
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    mesh.update()


def apply_material(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.material_index = 0


def assign_material_by_height(
    obj: bpy.types.Object,
    mat: bpy.types.Material,
    threshold: float,
) -> None:
    """Assign ``mat`` to every face whose centre sits above ``threshold``."""
    if mat.name not in [m.name for m in obj.data.materials]:
        obj.data.materials.append(mat)
    index = [m.name for m in obj.data.materials].index(mat.name)
    for poly in obj.data.polygons:
        if poly.center.z > threshold:
            poly.material_index = index


def check_building(obj: bpy.types.Object, expect: tuple[float, float, float]) -> None:
    """Assert the hard requirements: scale, bottom-centre origin, UVs, material."""
    dims = obj.dimensions
    for got, want, axis in zip(dims, expect, "XYZ"):
        if abs(got - want) > 1e-3:
            raise AssertionError(f"{obj.name}: {axis} size {got:.3f} m, expected {want:.3f} m")

    coords = [obj.matrix_world @ v.co for v in obj.data.vertices]
    min_z = min(c.z for c in coords)
    center_x = (min(c.x for c in coords) + max(c.x for c in coords)) / 2.0
    center_y = (min(c.y for c in coords) + max(c.y for c in coords)) / 2.0
    if abs(min_z) > 1e-4 or abs(center_x) > 1e-4 or abs(center_y) > 1e-4:
        raise AssertionError(
            f"{obj.name}: origin not bottom-centre "
            f"(min_z={min_z:.4f}, cx={center_x:.4f}, cy={center_y:.4f})"
        )
    if not obj.data.uv_layers.active:
        raise AssertionError(f"{obj.name}: no UV map")
    for slot in obj.material_slots:
        mat = slot.material
        tex = next((n for n in mat.node_tree.nodes if n.type == "TEX_IMAGE" and n.image), None)
        bsdf = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if tex is None or bsdf is None:
            raise AssertionError(f"{obj.name}: material {mat.name} missing image/BSDF")
        linked = any(
            l.from_node == tex and l.to_socket == bsdf.inputs["Base Color"]
            for l in mat.node_tree.links
        )
        if not linked:
            raise AssertionError(f"{obj.name}: texture not connected to Base Color")
    print(
        f"  check OK: {dims.x:.2f} x {dims.y:.2f} x {dims.z:.2f} m, origin bottom-centre, "
        f"UVs={obj.data.uv_layers.active.name}, materials={[s.material.name for s in obj.material_slots]}"
    )


def export_building(obj: bpy.types.Object, name: str) -> str:
    path = os.path.join(OUTPUT_DIR, f"{name}.glb")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_image_format="AUTO",
        export_jpeg_quality=90,
        export_texcoords=True,
        export_normals=True,
        export_yup=True,
    )
    if not os.path.isfile(path):
        raise RuntimeError(f"export failed: {path}")
    print(f"Exported {name}: {path} ({os.path.getsize(path)} bytes)")
    return path


def finish(
    name: str, parts: list[bpy.types.Object], material: bpy.types.Material, tile_m: float
) -> bpy.types.Object:
    obj = join(parts, name)
    obj.data.materials.clear()
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.material_index = 0
    set_origin_bottom_center(obj)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    smart_unwrap(obj, tile_m)
    return obj


# ---------------------------------------------------------------------------
# Building 1 - garage: 10 x 8 x 4 m, flat roof, 4 x 3 m door
# ---------------------------------------------------------------------------
def build_garage(material: bpy.types.Material) -> bpy.types.Object:
    w, d, h = 10.0, 8.0, 4.0
    wall_t, roof_t, floor_t = 0.30, 0.20, 0.15
    wall_h = h - roof_t

    front = add_box("wall_front", (w, wall_t, wall_h), (0, -d / 2 + wall_t / 2, wall_h / 2))
    back = add_box("wall_back", (w, wall_t, wall_h), (0, d / 2 - wall_t / 2, wall_h / 2))
    left = add_box(
        "wall_left", (wall_t, d - 2 * wall_t, wall_h), (-w / 2 + wall_t / 2, 0, wall_h / 2)
    )
    right = add_box(
        "wall_right", (wall_t, d - 2 * wall_t, wall_h), (w / 2 - wall_t / 2, 0, wall_h / 2)
    )
    floor = add_box(
        "floor", (w - 2 * wall_t, d - 2 * wall_t, floor_t), (0, 0, floor_t / 2)
    )
    roof = add_box("roof", (w, d, roof_t), (0, 0, h - roof_t / 2))

    # 4 m wide x 3 m tall garage door, centred on the front (-Y) wall.
    cut_opening(front, width=4.0, height=3.0, center_x=0.0, base_z=0.0, depth=wall_t + 0.2)

    return finish("Garage", [front, back, left, right, floor, roof], material, MATERIALS["concrete"][1])


# ---------------------------------------------------------------------------
# Building 2 - sniper tower: 4 x 4 m base, 10 m tall, wood
# ---------------------------------------------------------------------------
def build_sniper_tower(material: bpy.types.Material) -> bpy.types.Object:
    span = 4.0
    pillar = 0.30
    platform_z = 8.0
    platform_t = 0.25
    rail_h = 1.05
    parts: list[bpy.types.Object] = []

    inset = span / 2 - pillar / 2
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(
                add_box(
                    f"pillar_{sx}_{sy}",
                    (pillar, pillar, platform_z),
                    (sx * inset, sy * inset, platform_z / 2),
                )
            )
            # Knee brace from the pillar up to the underside of the platform.
            parts.append(
                add_strut(
                    f"brace_{sx}_{sy}",
                    (sx * inset, sy * inset, platform_z - 2.2),
                    (sx * inset, sy * inset * 0.15, platform_z - 0.35),
                    0.14,
                )
            )
            parts.append(
                add_strut(
                    f"brace_x_{sx}_{sy}",
                    (sx * inset, sy * inset, platform_z - 2.2),
                    (sx * inset * 0.15, sy * inset, platform_z - 0.35),
                    0.14,
                )
            )

    # X bracing between neighbouring pillars, halfway up the tower.
    brace_z = platform_z * 0.45
    for sign in (-1, 1):
        parts.append(
            add_strut(
                f"xbrace_front_{sign}",
                (-inset, sign * inset, brace_z - 0.9),
                (inset, sign * inset, brace_z + 0.9),
                0.13,
            )
        )
        parts.append(
            add_strut(
                f"xbrace_side_{sign}",
                (sign * inset, -inset, brace_z - 0.9),
                (sign * inset, inset, brace_z + 0.9),
                0.13,
            )
        )

    # Cross beams under the platform.
    parts.append(add_box("beam_x", (span, 0.18, 0.25), (0, -inset, platform_z - 0.3)))
    parts.append(add_box("beam_x2", (span, 0.18, 0.25), (0, inset, platform_z - 0.3)))

    platform = add_box(
        "platform", (span, span, platform_t), (0, 0, platform_z + platform_t / 2)
    )
    parts.append(platform)

    # Railings: top rail + mid rail on all four sides + corner posts.
    rail_z = platform_z + platform_t
    for axis, sign in (("x", -1), ("x", 1), ("y", -1), ("y", 1)):
        if axis == "x":
            pos = (0, sign * (span / 2 - 0.06), rail_z + rail_h / 2)
            size = (span, 0.10, 0.10)
        else:
            pos = (sign * (span / 2 - 0.06), 0, rail_z + rail_h / 2)
            size = (0.10, span, 0.10)
        parts.append(add_box(f"rail_top_{axis}{sign}", size, pos))
        mid = (pos[0], pos[1], rail_z + rail_h / 2 - 0.45)
        parts.append(add_box(f"rail_mid_{axis}{sign}", size, mid))

    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(
                add_box(
                    f"rail_post_{sx}_{sy}",
                    (0.10, 0.10, rail_h),
                    (sx * (span / 2 - 0.06), sy * (span / 2 - 0.06), rail_z + rail_h / 2),
                )
            )

    # Small roof on four corner posts, total height exactly 10 m.
    roof_t = 0.20
    roof_bottom = 10.0 - roof_t
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts.append(
                add_box(
                    f"roof_post_{sx}_{sy}",
                    (0.12, 0.12, roof_bottom - rail_z),
                    (sx * (span / 2 - 0.12), sy * (span / 2 - 0.12), (rail_z + roof_bottom) / 2),
                )
            )
    parts.append(add_box("roof", (span, span, roof_t), (0, 0, roof_bottom + roof_t / 2)))

    return finish("SniperTower", parts, material, MATERIALS["wood"][1])


# ---------------------------------------------------------------------------
# Building 3 - small house: 6 x 6 x 3.5 m, brick walls + wooden gable roof
# ---------------------------------------------------------------------------
def build_house_small(
    wall_mat: bpy.types.Material, roof_mat: bpy.types.Material
) -> bpy.types.Object:
    w, d, h = 6.0, 6.0, 3.5
    wall_t, floor_t = 0.25, 0.15
    # Low eave keeps the gable roof steep enough to read as a slanted roof
    # while still clearing the 2.2 m door.
    eave_z = 2.45

    front = add_box("wall_front", (w, wall_t, eave_z), (0, -d / 2 + wall_t / 2, eave_z / 2))
    back = add_box("wall_back", (w, wall_t, eave_z), (0, d / 2 - wall_t / 2, eave_z / 2))
    left = add_box(
        "wall_left", (wall_t, d - 2 * wall_t, eave_z), (-w / 2 + wall_t / 2, 0, eave_z / 2)
    )
    right = add_box(
        "wall_right", (wall_t, d - 2 * wall_t, eave_z), (w / 2 - wall_t / 2, 0, eave_z / 2)
    )
    floor = add_box("floor", (w - 2 * wall_t, d - 2 * wall_t, floor_t), (0, 0, floor_t / 2))

    # Door 1.2 x 2.2 m in the middle of the front wall.
    cut_opening(front, width=1.2, height=2.2, center_x=0.0, base_z=0.0, depth=wall_t + 0.2)
    # Exactly two 1.2 x 1.2 m windows, one either side of the door.
    cut_opening(front, width=1.2, height=1.2, center_x=-1.85, base_z=1.05, depth=wall_t + 0.2)
    cut_opening(front, width=1.2, height=1.2, center_x=1.85, base_z=1.05, depth=wall_t + 0.2)

    roof = add_prism("roof", (w, d), eave_z, h)

    parts = [front, back, left, right, floor, roof]
    obj = join(parts, "HouseSmall")
    set_origin_bottom_center(obj)

    obj.data.materials.clear()
    obj.data.materials.append(wall_mat)
    obj.data.materials.append(roof_mat)
    roof_index = 1
    for poly in obj.data.polygons:
        # Roof faces are the only ones above the eave line.
        poly.material_index = roof_index if poly.center.z > eave_z - 0.02 else 0

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    smart_unwrap(obj, MATERIALS["brick"][1])
    return obj


# ---------------------------------------------------------------------------
# Building 4 - warehouse: 15 x 10 x 6 m, flat roof, 5 x 4.5 m sliding doors
# ---------------------------------------------------------------------------
def build_warehouse(material: bpy.types.Material) -> bpy.types.Object:
    w, d, h = 15.0, 10.0, 6.0
    wall_t, roof_t, floor_t = 0.35, 0.25, 0.15
    wall_h = h - roof_t

    front = add_box("wall_front", (w, wall_t, wall_h), (0, -d / 2 + wall_t / 2, wall_h / 2))
    back = add_box("wall_back", (w, wall_t, wall_h), (0, d / 2 - wall_t / 2, wall_h / 2))
    left = add_box(
        "wall_left", (wall_t, d - 2 * wall_t, wall_h), (-w / 2 + wall_t / 2, 0, wall_h / 2)
    )
    right = add_box(
        "wall_right", (wall_t, d - 2 * wall_t, wall_h), (w / 2 - wall_t / 2, 0, wall_h / 2)
    )
    floor = add_box("floor", (w - 2 * wall_t, d - 2 * wall_t, floor_t), (0, 0, floor_t / 2))
    roof = add_box("roof", (w, d, roof_t), (0, 0, h - roof_t / 2))

    # 5 m wide x 4.5 m tall sliding door opening on the front wall.
    cut_opening(front, width=5.0, height=4.5, center_x=0.0, base_z=0.0, depth=wall_t + 0.2)

    return finish("Warehouse", [front, back, left, right, floor, roof], material, MATERIALS["metal"][1])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> int:
    print(f"Blender (bpy) version: {bpy.app.version_string}")
    ensure_dirs()
    reset_scene()

    mats = {key: build_material(key) for key in MATERIALS}
    print("Materials ready: " + ", ".join(sorted(m.name for m in mats.values())))

    jobs = [
        ("garage", lambda: build_garage(mats["concrete"])),
        ("sniper_tower", lambda: build_sniper_tower(mats["wood"])),
        ("house_small", lambda: build_house_small(mats["brick"], mats["wood"])),
        ("warehouse", lambda: build_warehouse(mats["metal"])),
    ]
    expected = {
        "garage": (10.0, 8.0, 4.0),
        "sniper_tower": (4.0, 4.0, 10.0),
        "house_small": (6.0, 6.0, 3.5),
        "warehouse": (15.0, 10.0, 6.0),
    }
    for name, builder in jobs:
        obj = builder()
        check_building(obj, expected[name])
        size = obj.dimensions
        print(
            f"{name}: {size.x:.2f} x {size.y:.2f} x {size.z:.2f} m, "
            f"origin={tuple(round(v, 3) for v in obj.location)}, "
            f"verts={len(obj.data.vertices)}, tris~{sum(len(p.vertices) - 2 for p in obj.data.polygons)}"
        )
        export_building(obj, name)
        bpy.data.objects.remove(obj, do_unlink=True)

    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
