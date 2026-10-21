#!/usr/bin/env python3
"""Generate the Elite Cargo Plane battle-royale drop-ship as a self-contained GLB.

The model deliberately uses only procedural Blender geometry and solid Principled /
emissive materials.  It is built for an in-game silhouette first: a 35 m long,
45 m span blended-wing stealth transport with a bottom-centre origin, a working
Boolean-cut rear cargo opening, four octagonal engines, and concentrated greeble
where players will see it up close.

Output:
    docs/models/vehicles/plane_cargo_elite.glb

Usage:
    pip install bpy
    python tools/generate_plane_cargo_elite.py
"""

from __future__ import annotations

import json
import math
import os
import struct
import sys
from typing import Iterable, Sequence

import bpy
from mathutils import Matrix, Vector


REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "vehicles")
OUTPUT_PATH = os.path.join(OUTPUT_DIR, "plane_cargo_elite.glb")

# The main body runs forward on +X.  Wings deliberately reach exactly +/-22.5 m,
# and the nose / ramp terminate at +/-17.5 m, making the gameplay footprint
# 35 m long by 45 m wide before the GLB Y-up conversion.
TARGET_LENGTH_M = 35.0
TARGET_SPAN_M = 45.0


# -----------------------------------------------------------------------------
# Scene / material helpers
# -----------------------------------------------------------------------------

def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)


def set_metric_units() -> None:
    scene = bpy.context.scene
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0


def srgb_channel(value: int) -> float:
    """Convert an 8-bit sRGB channel to Blender's linear working space."""
    c = value / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_rgba(value: str, alpha: float = 1.0) -> tuple[float, float, float, float]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"Expected #RRGGBB, received {value!r}")
    return (
        srgb_channel(int(value[0:2], 16)),
        srgb_channel(int(value[2:4], 16)),
        srgb_channel(int(value[4:6], 16)),
        alpha,
    )


def make_pbr(
    name: str,
    color: str,
    *,
    metallic: float = 0.0,
    roughness: float = 0.5,
) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = hex_rgba(color)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError("Principled BSDF was not created for material")
    bsdf.inputs["Base Color"].default_value = hex_rgba(color)
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    return mat


def make_emissive(name: str, color: str, strength: float) -> bpy.types.Material:
    """A texture-free emission material that exports as a glTF emissive factor."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = hex_rgba(color)
    emission.inputs["Strength"].default_value = strength
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    mat.diffuse_color = hex_rgba(color)
    return mat


def make_materials() -> dict[str, bpy.types.Material]:
    """Palette intentionally contains no bitmap/image texture nodes."""
    return {
        # User-specified body colour: matte dark gunmetal #2C2E33.
        "body": make_pbr("Body_Matte_Gunmetal_2C2E33", "#2C2E33", metallic=0.58, roughness=0.57),
        "panel": make_pbr("Access_Panels_Light_Grey", "#4A5059", metallic=0.54, roughness=0.42),
        "panel_dark": make_pbr("Panel_Lines_Dark_Grey", "#171C23", metallic=0.48, roughness=0.44),
        "edge": make_pbr("Stealth_Edge_Trim", "#667180", metallic=0.72, roughness=0.31),
        "cockpit": make_pbr("Cockpit_Deep_Blue_Tinted_Glass", "#082C52", metallic=0.80, roughness=0.10),
        "nozzle": make_pbr("Engine_Nozzle_Black_Chrome", "#101722", metallic=0.90, roughness=0.18),
        "cargo": make_pbr("Cargo_Bay_Interior", "#18212C", metallic=0.46, roughness=0.56),
        "cyan": make_emissive("Neon_Cyan_Thruster_and_Sensors", "#00E5FF", 8.0),
        "orange": make_emissive("Ion_Orange_Thruster_Ring", "#FF6B1A", 7.0),
        "red": make_emissive("Cargo_Bay_Status_Red", "#FF3045", 5.0),
        "green": make_emissive("Cargo_Bay_Status_Green", "#42FF9B", 5.0),
    }


# -----------------------------------------------------------------------------
# Mesh / primitive helpers
# -----------------------------------------------------------------------------

def finish_mesh(mesh: bpy.types.Mesh) -> None:
    mesh.validate(clean_customdata=True)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = False


def create_mesh(
    name: str,
    vertices: Sequence[tuple[float, float, float]],
    faces: Sequence[Sequence[int]],
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(f"{name}Mesh")
    mesh.from_pydata(vertices, [], faces)
    finish_mesh(mesh)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def activate_only(obj: bpy.types.Object) -> None:
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def apply_rotation_scale(obj: bpy.types.Object) -> None:
    activate_only(obj)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)


def create_box(
    name: str,
    size: tuple[float, float, float],
    location: tuple[float, float, float],
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location, rotation=rotation)
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = f"{name}Mesh"
    obj.dimensions = size
    apply_rotation_scale(obj)
    return obj


def create_cylinder(
    name: str,
    radius: float,
    depth: float,
    location: tuple[float, float, float],
    *,
    vertices: int = 8,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        end_fill_type="NGON",
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = f"{name}Mesh"
    apply_rotation_scale(obj)
    return obj


def create_cone(
    name: str,
    radius1: float,
    radius2: float,
    depth: float,
    location: tuple[float, float, float],
    *,
    vertices: int = 8,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices,
        radius1=radius1,
        radius2=radius2,
        depth=depth,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = f"{name}Mesh"
    apply_rotation_scale(obj)
    return obj


def create_uv_sphere(
    name: str,
    radius: float,
    location: tuple[float, float, float],
    *,
    segments: int = 12,
    rings: int = 6,
    scale: tuple[float, float, float] = (1.0, 1.0, 1.0),
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=rings,
        radius=radius,
        location=location,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = f"{name}Mesh"
    obj.scale = scale
    apply_rotation_scale(obj)
    return obj


def create_torus(
    name: str,
    major_radius: float,
    minor_radius: float,
    location: tuple[float, float, float],
    *,
    major_segments: int = 8,
    minor_segments: int = 4,
    rotation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major_radius,
        minor_radius=minor_radius,
        major_segments=major_segments,
        minor_segments=minor_segments,
        location=location,
        rotation=rotation,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.data.name = f"{name}Mesh"
    apply_rotation_scale(obj)
    return obj


def assign_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(material)


def apply_boolean_difference(target: bpy.types.Object, cutter: bpy.types.Object) -> None:
    """Cut a real open rear cargo portal into the fuselage."""
    modifier = target.modifiers.new(name="Cargo_Bay_Boolean_Cut", type="BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.object = cutter
    if hasattr(modifier, "solver"):
        modifier.solver = "EXACT"
    activate_only(target)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    finish_mesh(target.data)


def join_objects(objects: Iterable[bpy.types.Object], name: str) -> bpy.types.Object:
    objects = list(objects)
    if not objects:
        raise ValueError("No objects supplied for join")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    joined = bpy.context.active_object
    joined.name = name
    joined.data.name = f"{name}Mesh"
    return joined


def set_origin_bottom_center(obj: bpy.types.Object) -> None:
    """Bake all joined object transforms, then put bbox bottom-centre at (0,0,0)."""
    # Joining preserves the transform of its active object. Bake that transform so
    # exported mesh coordinates, not just an object transform, express the origin.
    obj.data.transform(obj.matrix_world.copy())
    obj.matrix_world = Matrix.Identity(4)
    coords = [Vector(vertex.co) for vertex in obj.data.vertices]
    if not coords:
        raise RuntimeError("Cannot set an origin on an empty mesh")
    min_x, max_x = min(v.x for v in coords), max(v.x for v in coords)
    min_y, max_y = min(v.y for v in coords), max(v.y for v in coords)
    min_z = min(v.z for v in coords)
    offset = Vector((-(min_x + max_x) / 2.0, -(min_y + max_y) / 2.0, -min_z))
    obj.data.transform(Matrix.Translation(offset))
    finish_mesh(obj.data)
    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)


def object_bbox(obj: bpy.types.Object) -> tuple[float, float, float, float, float, float]:
    points = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    return (
        min(p.x for p in points),
        max(p.x for p in points),
        min(p.y for p in points),
        max(p.y for p in points),
        min(p.z for p in points),
        max(p.z for p in points),
    )


# -----------------------------------------------------------------------------
# Purpose-built stealth-drop-ship geometry
# -----------------------------------------------------------------------------

def create_fuselage() -> bpy.types.Object:
    """A faceted station hull rather than a generic tube/cylinder."""
    # x, half-width, bottom z, top z.  The wide middle forms the blended body;
    # tapered nose/tail establish the next-gen stealth silhouette.
    stations = [
        (17.50, 0.25, 3.45, 5.25),
        (16.10, 1.70, 2.60, 5.95),
        (12.60, 3.30, 1.80, 6.80),
        (5.20, 4.40, 1.20, 7.30),
        (-6.00, 4.90, 1.10, 7.25),
        (-11.60, 4.20, 1.25, 6.95),
        (-15.20, 3.15, 1.70, 6.30),
        (-17.50, 2.25, 2.30, 5.60),
    ]
    vertices: list[tuple[float, float, float]] = []
    for x, half_width, bottom, top in stations:
        side_break = min(0.52, (top - bottom) * 0.25)
        vertices.extend(
            [
                (x, -half_width * 0.62, bottom),
                (x, -half_width, bottom + side_break),
                (x, -half_width, top - side_break * 1.15),
                (x, -half_width * 0.55, top),
                (x, half_width * 0.55, top),
                (x, half_width, top - side_break * 1.15),
                (x, half_width, bottom + side_break),
                (x, half_width * 0.62, bottom),
            ]
        )

    faces: list[Sequence[int]] = []
    ring_size = 8
    for station_index in range(len(stations) - 1):
        start = station_index * ring_size
        next_start = start + ring_size
        for i in range(ring_size):
            j = (i + 1) % ring_size
            faces.append((start + i, next_start + i, next_start + j, start + j))
    # Caps make it a watertight Boolean target.
    faces.append(tuple(reversed(range(ring_size))))
    last = (len(stations) - 1) * ring_size
    faces.append(tuple(last + i for i in range(ring_size)))
    return create_mesh("Stealth_Fuselage", vertices, faces)


def create_blended_root_fairing(side: int) -> bpy.types.Object:
    """A shallow planform fairing makes the wing feel grown from the body."""
    s = float(side)
    xy = [
        (9.20, s * 1.55),
        (5.20, s * 7.10),
        (-9.80, s * 7.75),
        (-12.00, s * 2.35),
    ]
    upper = [5.36, 4.92, 4.22, 4.08]
    lower = [z - 0.34 for z in upper]
    vertices = [(x, y, z) for (x, y), z in zip(xy, upper)]
    vertices += [(x, y, z) for (x, y), z in zip(xy, lower)]
    faces: list[Sequence[int]] = [(0, 1, 2, 3), (7, 6, 5, 4)]
    for i in range(4):
        j = (i + 1) % 4
        faces.append((i, 4 + i, 4 + j, j))
    return create_mesh(f"Blended_Wing_Root_{'R' if side > 0 else 'L'}", vertices, faces)


def create_main_wing(side: int) -> bpy.types.Object:
    """Swept, slightly dihedral wing with an intentionally hard-edged profile."""
    s = float(side)
    # Perimeter is root leading -> root trailing -> tip trailing -> tip leading.
    outline = [
        (8.50, s * 3.00),
        (-11.50, s * 3.30),
        (-12.00, s * 22.50),
        (-5.00, s * 22.50),
    ]
    upper = [4.72, 3.92, 4.50, 5.22]
    lower = [z - 0.36 for z in upper]
    vertices = [(x, y, z) for (x, y), z in zip(outline, upper)]
    vertices += [(x, y, z) for (x, y), z in zip(outline, lower)]
    faces: list[Sequence[int]] = [(0, 1, 2, 3), (7, 6, 5, 4)]
    for i in range(4):
        j = (i + 1) % 4
        faces.append((i, 4 + i, 4 + j, j))
    return create_mesh(f"Swept_Main_Wing_{'R' if side > 0 else 'L'}", vertices, faces)


def create_canted_winglet(side: int) -> bpy.types.Object:
    """Thin upward fin at the exact 45 m-span tips; it stays inside +/-22.5 m."""
    s = float(side)
    face = [
        (-12.05, s * 22.08, 4.43),
        (-5.05, s * 22.08, 5.18),
        (-7.25, s * 22.38, 8.00),
        (-10.92, s * 22.38, 7.18),
    ]
    # Give the canted surface a 0.16 m inward thickness, so it is real game mesh.
    inner_offset = -s * 0.16
    vertices = face + [(x, y + inner_offset, z) for x, y, z in face]
    faces: list[Sequence[int]] = [(0, 1, 2, 3), (7, 6, 5, 4)]
    for i in range(4):
        j = (i + 1) % 4
        faces.append((i, 4 + i, 4 + j, j))
    return create_mesh(f"Upturned_Winglet_{'R' if side > 0 else 'L'}", vertices, faces)


def create_twin_tail(side: int) -> bpy.types.Object:
    """Canted twin-tail fin; the two fins read as a stealthy tail in silhouette."""
    s = float(side)
    face = [
        (-17.02, s * 1.22, 5.03),
        (-10.20, s * 2.03, 5.68),
        (-13.48, s * 3.92, 10.18),
        (-16.10, s * 3.18, 8.54),
    ]
    thickness = -s * 0.26
    vertices = face + [(x, y + thickness, z) for x, y, z in face]
    faces: list[Sequence[int]] = [(0, 1, 2, 3), (7, 6, 5, 4)]
    for i in range(4):
        j = (i + 1) % 4
        faces.append((i, 4 + i, 4 + j, j))
    return create_mesh(f"Canted_Twin_Tail_{'R' if side > 0 else 'L'}", vertices, faces)


def create_ramp_wedge() -> bpy.types.Object:
    """A lowered, solid cargo ramp whose outer lip is the model's ground contact."""
    # Rear lip (-X) is at zero; the inner end rises into the actual Boolean bay.
    outer_x, inner_x = -17.50, -11.72
    half_width = 2.45
    top_outer, top_inner = 0.22, 1.52
    thickness = 0.18
    vertices = [
        (outer_x, -half_width, top_outer),
        (outer_x, half_width, top_outer),
        (inner_x, half_width, top_inner),
        (inner_x, -half_width, top_inner),
        (outer_x, -half_width, 0.00),
        (outer_x, half_width, 0.00),
        (inner_x, half_width, top_inner - thickness),
        (inner_x, -half_width, top_inner - thickness),
    ]
    faces = [
        (0, 1, 2, 3),
        (7, 6, 5, 4),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    return create_mesh("Lowered_Cargo_Ramp", vertices, faces)


def create_cockpit_canopy() -> bpy.types.Object:
    """Four faceted canopy stations form a long slanted blue-tinted windscreen."""
    stations = [
        (8.60, 2.52, 5.84, 7.18),
        (12.70, 2.18, 5.42, 6.98),
        (15.75, 1.05, 4.86, 6.04),
        (16.92, 0.24, 4.78, 5.20),
    ]
    vertices: list[tuple[float, float, float]] = []
    for x, width, base, top in stations:
        vertices.extend(
            [
                (x, -width, base),
                (x, -width * 0.58, top),
                (x, width * 0.58, top),
                (x, width, base),
            ]
        )
    faces: list[Sequence[int]] = []
    for station in range(len(stations) - 1):
        start = station * 4
        nxt = start + 4
        faces.extend(
            [
                (start, nxt, nxt + 1, start + 1),
                (start + 1, nxt + 1, nxt + 2, start + 2),
                (start + 2, nxt + 2, nxt + 3, start + 3),
                (start + 3, nxt + 3, nxt, start),
            ]
        )
    faces.append((3, 2, 1, 0))
    final = (len(stations) - 1) * 4
    faces.append((final, final + 1, final + 2, final + 3))
    return create_mesh("Slanted_Deep_Blue_Cockpit", vertices, faces)


def create_blade_antenna(
    name: str,
    x: float,
    y: float,
    base_z: float,
    height: float,
    base_length: float,
    thickness: float,
) -> bpy.types.Object:
    """A low-profile triangular avionics blade, much cheaper than a curved antenna."""
    half = thickness / 2.0
    base_front = x + base_length / 2.0
    base_back = x - base_length / 2.0
    apex_x = x + base_length * 0.12
    vertices = [
        (base_back, y - half, base_z),
        (base_front, y - half, base_z),
        (apex_x, y - half, base_z + height),
        (base_back, y + half, base_z),
        (base_front, y + half, base_z),
        (apex_x, y + half, base_z + height),
    ]
    faces = [(0, 1, 2), (5, 4, 3), (0, 3, 4, 1), (1, 4, 5, 2), (2, 5, 3, 0)]
    return create_mesh(name, vertices, faces)


# -----------------------------------------------------------------------------
# Assembly + greebling
# -----------------------------------------------------------------------------

def build_plane() -> bpy.types.Object:
    mats = make_materials()
    parts: list[bpy.types.Object] = []

    def add(obj: bpy.types.Object, material: bpy.types.Material) -> bpy.types.Object:
        assign_material(obj, material)
        parts.append(obj)
        return obj

    # 1. Main angular stealth body and actual Boolean-cut rear cargo portal.
    fuselage = create_fuselage()
    cargo_cutter = create_box(
        "Cargo_Bay_Opening_Cutter",
        (6.85, 5.35, 3.85),
        (-15.05, 0.0, 2.83),
    )
    apply_boolean_difference(fuselage, cargo_cutter)
    add(fuselage, mats["body"])

    # 2. Wide, swept wings, blended roots, upturned winglets and canted twin tail.
    for side in (-1, 1):
        add(create_blended_root_fairing(side), mats["body"])
        add(create_main_wing(side), mats["body"])
        add(create_canted_winglet(side), mats["body"])
        add(create_twin_tail(side), mats["body"])

        # Light grey wing-tip leading highlight, kept within the 45 m span.
        tip = create_box(
            f"Winglet_Leading_Accent_{side}",
            (1.55, 0.10, 0.13),
            (-7.75, side * 22.28, 6.58),
            rotation=(0.0, math.radians(-15.0), math.radians(side * 4.0)),
        )
        add(tip, mats["edge"])

        # Three broad access plates and a dark flap seam on each wing.
        for index, (x, y_abs, z, yaw) in enumerate(
            [
                (1.60, 7.20, 4.96, -9.0),
                (-3.00, 11.20, 5.03, -9.0),
                (-7.45, 16.30, 5.00, -9.0),
            ]
        ):
            plate = create_box(
                f"Wing_Access_Plate_{side}_{index}",
                (1.35, 2.25, 0.045),
                (x, side * y_abs, z),
                rotation=(0.0, 0.0, math.radians(side * yaw)),
            )
            add(plate, mats["panel"])
        flap = create_box(
            f"Wing_Trailing_Seam_{side}",
            (0.10, 10.60, 0.055),
            (-10.20, side * 14.80, 4.48),
            rotation=(0.0, 0.0, math.radians(side * 6.0)),
        )
        add(flap, mats["panel_dark"])

    # 3. Cockpit, its structural frames, and forward sensor pods/lenses.
    add(create_cockpit_canopy(), mats["cockpit"])
    add(
        create_box(
            "Cockpit_Center_Frame",
            (5.35, 0.11, 0.10),
            (12.10, 0.0, 6.94),
            rotation=(0.0, math.radians(-7.0), 0.0),
        ),
        mats["panel_dark"],
    )
    for side in (-1, 1):
        add(
            create_box(
                f"Cockpit_Windshield_Mullion_{side}",
                (0.10, 0.12, 1.72),
                (15.15, side * 0.74, 5.58),
                rotation=(0.0, math.radians(-39.0), 0.0),
            ),
            mats["panel_dark"],
        )
        sensor = create_cylinder(
            f"Nose_Sensor_Pod_{side}",
            0.28,
            0.58,
            (14.50, side * 2.58, 4.34),
            vertices=8,
            rotation=(0.0, math.pi / 2.0, 0.0),
        )
        add(sensor, mats["nozzle"])
        lens = create_cylinder(
            f"Nose_Sensor_Lens_{side}",
            0.16,
            0.045,
            (14.82, side * 2.58, 4.34),
            vertices=8,
            rotation=(0.0, math.pi / 2.0, 0.0),
        )
        add(lens, mats["cyan"])
    add(create_uv_sphere("Dorsal_Sensor_Dome", 0.25, (13.10, 0.0, 6.76), segments=8, rings=4), mats["cyan"])

    # 4. Four massive octagonal engines. Every engine gets an intake, outer ridge
    # strips, black nozzle, orange halo, cyan flame core, and a wing pylon.
    engine_y_positions = (-14.35, -7.10, 7.10, 14.35)
    for engine_index, engine_y in enumerate(engine_y_positions, start=1):
        engine = create_cylinder(
            f"Octagonal_Engine_Nacelle_{engine_index}",
            1.42,
            7.20,
            (-2.20, engine_y, 2.95),
            vertices=8,
            rotation=(0.0, math.pi / 2.0, 0.0),
        )
        add(engine, mats["body"])
        intake = create_cone(
            f"Engine_Intake_Shroud_{engine_index}",
            1.40,
            1.17,
            1.30,
            (2.05, engine_y, 2.95),
            vertices=8,
            rotation=(0.0, math.pi / 2.0, 0.0),
        )
        add(intake, mats["edge"])
        intake_face = create_cylinder(
            f"Engine_Intake_Dark_{engine_index}",
            1.08,
            0.12,
            (2.72, engine_y, 2.95),
            vertices=8,
            rotation=(0.0, math.pi / 2.0, 0.0),
        )
        add(intake_face, mats["panel_dark"])
        intake_ring = create_torus(
            f"Engine_Intake_Ring_{engine_index}",
            1.24,
            0.10,
            (2.67, engine_y, 2.95),
            major_segments=8,
            minor_segments=4,
            rotation=(0.0, math.pi / 2.0, 0.0),
        )
        add(intake_ring, mats["edge"])
        pylon = create_box(
            f"Engine_Pylon_{engine_index}",
            (2.45, 0.55, 1.05),
            (-1.15, engine_y, 4.10),
            rotation=(0.0, math.radians(-7.0), 0.0),
        )
        add(pylon, mats["body"])

        # Eight longitudinal ridge strips sell the mechanical octagonal casing.
        for ridge_index in range(8):
            angle = math.tau * ridge_index / 8.0
            ridge = create_box(
                f"Engine_Ridge_{engine_index}_{ridge_index}",
                (3.75, 0.10, 0.10),
                (-2.45, engine_y + math.cos(angle) * 1.38, 2.95 + math.sin(angle) * 1.38),
            )
            add(ridge, mats["panel"] if ridge_index % 2 == 0 else mats["panel_dark"])

        nozzle = create_cylinder(
            f"Engine_Nozzle_{engine_index}",
            1.22,
            0.72,
            (-6.14, engine_y, 2.95),
            vertices=8,
            rotation=(0.0, math.pi / 2.0, 0.0),
        )
        add(nozzle, mats["nozzle"])
        orange_ring = create_torus(
            f"Engine_Orange_Ion_Ring_{engine_index}",
            1.04,
            0.13,
            (-6.53, engine_y, 2.95),
            major_segments=8,
            minor_segments=4,
            rotation=(0.0, math.pi / 2.0, 0.0),
        )
        add(orange_ring, mats["orange"])
        thruster = create_cylinder(
            f"Engine_Cyan_Thruster_Core_{engine_index}",
            0.86,
            0.18,
            (-6.58, engine_y, 2.95),
            vertices=8,
            rotation=(0.0, math.pi / 2.0, 0.0),
        )
        add(thruster, mats["cyan"])

    # 5. Two low-poly drop tanks under the outer wings, with small fin assemblies.
    for side in (-1, 1):
        tank_y = side * 18.00
        tank = create_uv_sphere(
            f"Underwing_Drop_Tank_{side}",
            1.0,
            (-5.35, tank_y, 2.72),
            segments=12,
            rings=6,
            scale=(2.62, 0.60, 0.60),
        )
        add(tank, mats["panel"])
        pylon = create_box(
            f"Drop_Tank_Pylon_{side}",
            (0.90, 0.36, 1.15),
            (-5.35, tank_y, 4.02),
            rotation=(0.0, math.radians(-8.0), 0.0),
        )
        add(pylon, mats["body"])
        for fin_index, (fin_x, fin_z) in enumerate(((-6.35, 2.72), (-4.35, 2.72))):
            fin = create_box(
                f"Drop_Tank_Fin_{side}_{fin_index}",
                (0.45, 0.08, 0.55),
                (fin_x, tank_y, fin_z),
                rotation=(0.0, math.radians(-16.0), 0.0),
            )
            add(fin, mats["panel_dark"])

    # 6. Cargo bay floor/ramp hardware and red/green bay-status lamps.
    add(create_ramp_wedge(), mats["cargo"])
    cargo_floor = create_box("Cargo_Bay_Floor", (4.20, 4.65, 0.16), (-13.82, 0.0, 1.44))
    add(cargo_floor, mats["cargo"])
    for slat_index, x in enumerate((-16.52, -15.62, -14.72, -13.82, -12.92)):
        z = 0.22 + ((x + 17.50) / 5.78) * 1.30 + 0.045
        slat = create_box(f"Cargo_Ramp_Slat_{slat_index}", (0.10, 4.52, 0.055), (x, 0.0, z))
        add(slat, mats["panel"])
    for side in (-1, 1):
        rail = create_box(
            f"Cargo_Ramp_Guide_Rail_{side}",
            (5.40, 0.11, 0.12),
            (-14.61, side * 2.42, 0.92),
            rotation=(0.0, math.radians(-12.6), 0.0),
        )
        add(rail, mats["edge"])
        frame = create_box(
            f"Cargo_Bay_Door_Frame_{side}",
            (0.18, 0.22, 2.25),
            (-17.26, side * 2.25, 3.35),
        )
        add(frame, mats["edge"])
        lamp = create_uv_sphere(
            f"Cargo_Bay_Indicator_{'Green' if side > 0 else 'Red'}",
            0.14,
            (-17.33, side * 2.10, 4.42),
            segments=8,
            rings=4,
        )
        add(lamp, mats["green"] if side > 0 else mats["red"])
    add(create_box("Cargo_Bay_Upper_Header", (0.28, 4.62, 0.20), (-17.26, 0.0, 4.57)), mats["edge"])

    # 7. Top/side panel lines, access hatches, vent banks, and avionics antennas.
    # Longitudinal dark-grey strips on the top and sides are deliberately raised
    # boxes: robust on mobile and visible at distance, unlike sub-pixel decals.
    for side in (-1, 1):
        top_line = create_box(
            f"Top_Longitudinal_Panel_Line_{side}",
            (19.50, 0.10, 0.055),
            (-0.85, side * 2.78, 6.91),
            rotation=(0.0, math.radians(-1.5), 0.0),
        )
        add(top_line, mats["panel_dark"])
        side_line = create_box(
            f"Side_Longitudinal_Panel_Line_{side}",
            (16.40, 0.055, 0.12),
            (-1.55, side * 4.80, 3.78),
            rotation=(0.0, math.radians(-1.0), 0.0),
        )
        add(side_line, mats["panel_dark"])

        # Two six-slot vent banks near the engine root/fuselage junction.
        for bank_index, bank_x in enumerate((-7.45, -1.80)):
            for slot in range(6):
                vent = create_box(
                    f"Side_Vent_{side}_{bank_index}_{slot}",
                    (0.13, 0.065, 0.40),
                    (bank_x + slot * 0.30, side * 4.89, 4.42),
                    rotation=(0.0, math.radians(-8.0), 0.0),
                )
                add(vent, mats["panel_dark"])

    for seam_index, x in enumerate((10.00, 5.30, 0.30, -5.10, -9.65)):
        seam = create_box(
            f"Top_Transverse_Panel_Seam_{seam_index}",
            (0.105, 5.15, 0.055),
            (x, 0.0, 7.29 if x > -7.0 else 7.08),
        )
        add(seam, mats["panel_dark"])

    for hatch_index, (x, y, z, width, length) in enumerate(
        [
            (3.05, 0.0, 7.34, 2.10, 2.40),
            (-3.35, 0.0, 7.29, 1.95, 2.10),
            (-8.55, 0.0, 7.12, 1.55, 1.80),
        ]
    ):
        hatch = create_box(
            f"Dorsal_Access_Hatch_{hatch_index}",
            (length, width, 0.05),
            (x, y, z),
        )
        add(hatch, mats["panel"])

    add(create_blade_antenna("Dorsal_Comms_Antenna", -2.10, 0.0, 7.28, 1.45, 1.18, 0.18), mats["edge"])
    add(create_blade_antenna("Forward_Data_Antenna", 5.55, 0.0, 7.26, 0.68, 0.78, 0.14), mats["panel"])
    add(create_blade_antenna("Tail_ECM_Antenna", -10.55, 0.0, 6.95, 0.82, 0.92, 0.15), mats["panel"])

    # A final cyan dorsal running light makes the vehicle legible in a night drop.
    add(create_uv_sphere("Dorsal_Neon_Running_Light", 0.10, (4.80, 0.0, 7.42), segments=8, rings=4), mats["cyan"])

    plane = join_objects(parts, "Plane_Cargo_Elite")
    set_origin_bottom_center(plane)
    plane["asset_type"] = "Elite Level Modern Advanced Cargo Plane"
    plane["dimensions_m"] = "35 m length x 45 m wingspan"
    plane["origin"] = "bottom-center (0,0,0)"
    plane["materials"] = "Solid colors only; no texture images"
    return plane


# -----------------------------------------------------------------------------
# Export / validation
# -----------------------------------------------------------------------------

def export_glb(plane: bpy.types.Object, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    activate_only(plane)
    kwargs = {
        "filepath": path,
        "export_format": "GLB",
        "export_lights": False,
        "export_cameras": False,
        "use_selection": True,
    }
    bpy.ops.export_scene.gltf(**kwargs)
    if not os.path.isfile(path):
        raise RuntimeError(f"Export did not create {path}")


def validate_glb(path: str) -> dict[str, int]:
    with open(path, "rb") as handle:
        data = handle.read()
    if data[:4] != b"glTF":
        raise RuntimeError(f"{path} is not a binary glTF")
    json_length = struct.unpack("<I", data[12:16])[0]
    gltf = json.loads(data[20 : 20 + json_length])
    triangles = 0
    for mesh in gltf.get("meshes", []):
        for primitive in mesh.get("primitives", []):
            if "indices" in primitive:
                count = gltf["accessors"][primitive["indices"]]["count"]
            else:
                count = gltf["accessors"][primitive["attributes"]["POSITION"]]["count"]
            triangles += count // 3
    material_names = {material.get("name", "") for material in gltf.get("materials", [])}
    required_materials = {
        "Body_Matte_Gunmetal_2C2E33",
        "Cockpit_Deep_Blue_Tinted_Glass",
        "Neon_Cyan_Thruster_and_Sensors",
        "Ion_Orange_Thruster_Ring",
    }
    missing = required_materials - material_names
    if missing:
        raise RuntimeError(f"GLB missing expected materials: {sorted(missing)}")
    if gltf.get("images"):
        raise RuntimeError("Elite plane must use solid colors only; unexpected image texture found")
    return {
        "bytes": os.path.getsize(path),
        "triangles": triangles,
        "materials": len(gltf.get("materials", [])),
        "meshes": len(gltf.get("meshes", [])),
        "images": len(gltf.get("images", [])),
    }


def main() -> int:
    print(f"Blender bpy {bpy.app.version_string} — Elite Cargo Plane Generator")
    clear_scene()
    set_metric_units()
    plane = build_plane()
    x0, x1, y0, y1, z0, z1 = object_bbox(plane)
    length, span, height = x1 - x0, y1 - y0, z1 - z0
    print(
        f"  bbox: {length:.2f} m length x {span:.2f} m wingspan x {height:.2f} m high "
        f"| min z {z0:.4f} | {len(plane.data.polygons)} faces"
    )
    if abs(length - TARGET_LENGTH_M) > 0.20:
        raise RuntimeError(f"Length changed from target: {length:.3f} m")
    if abs(span - TARGET_SPAN_M) > 0.20:
        raise RuntimeError(f"Wingspan changed from target: {span:.3f} m")
    if abs(z0) > 0.001:
        raise RuntimeError(f"Origin is not at bottom centre; min Z is {z0:.6f}")
    if abs((x0 + x1) / 2.0) > 0.001 or abs((y0 + y1) / 2.0) > 0.001:
        raise RuntimeError("Origin is not centered in the ground footprint")

    export_glb(plane, OUTPUT_PATH)
    stats = validate_glb(OUTPUT_PATH)
    print(
        f"  verified {os.path.relpath(OUTPUT_PATH, REPO_ROOT)}: "
        f"{stats['bytes']:,} bytes, {stats['triangles']:,} triangles, "
        f"{stats['materials']} materials, {stats['images']} images"
    )
    print("Done — plane_cargo_elite.glb generated with bottom-centre origin.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
