#!/usr/bin/env python3
"""Generate the two-storey Block 17 house as a Godot-ready GLB.

Run with Blender 3.6+ / 4.x:
  blender -b --python tools/generate_block17_house.py
  blender -b --python tools/generate_block17_house.py -- --output /path/to/block17.glb

The exported GLB includes the house, stairs, a stair collision ramp, and loot
spawn marker empties. Exterior openings are cut from the shell before interior
partitions are joined, avoiding booleans across overlapping wall solids.
"""
from __future__ import annotations

import argparse
import math
import os
import sys

import bpy
import bmesh

# Dimensions are in metres.
W, D = 8.0, 6.0
H_FLOOR = 3.2
WALL_T = 0.25
SLAB_T = 0.20


def parse_output_path() -> str:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "docs", "models", "buildings_modular", "block17_house.glb"),
        help="destination GLB path",
    )
    return os.path.abspath(parser.parse_args(argv).output)


def make_mat(name: str, rgba: tuple[float, float, float, float], roughness: float = 0.85):
    mat = bpy.data.materials.new(name=name)
    mat.diffuse_color = rgba
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = roughness
    return mat


def create_box(name, size, center, mat=None, collection=None):
    mesh = bpy.data.meshes.new(name + "Mesh")
    obj = bpy.data.objects.new(name, mesh)
    (collection or bpy.context.collection).objects.link(obj)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    bmesh.ops.translate(bm, vec=center, verts=bm.verts)
    bm.to_mesh(mesh)
    bm.free()
    if mat:
        obj.data.materials.append(mat)
    return obj


def cut_box(target, name, size, center):
    """Apply one exact cube difference to target, then discard the cutter."""
    cutter = create_box(name, size, center, collection=bpy.context.scene.collection)
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    bpy.context.view_layer.objects.active = target
    mod = target.modifiers.new(name="Cut_" + name, type="BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "EXACT"
    mod.object = cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def join_objects(objects, name):
    objects = [obj for obj in objects if obj and obj.name in bpy.data.objects]
    if not objects:
        raise RuntimeError("Cannot join an empty object list")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    joined = bpy.context.view_layer.objects.active
    joined.name = name
    joined.data.name = name + "Mesh"
    return joined


def add_openings(shell, floor_idx: int):
    """Cut all exterior openings for one storey from its hollow shell."""
    zbase = floor_idx * H_FLOOR
    door_z = zbase + SLAB_T + 2.3 / 2

    if floor_idx == 0:
        # Front and rear entry doors; one true left-side entrance.
        cut_box(shell, "Cut_Door_Front", (1.4, 0.8, 2.3), (0.0, -D / 2, door_z))
        cut_box(shell, "Cut_Door_Back", (1.4, 0.8, 2.3), (0.0, D / 2, door_z))
        cut_box(shell, "Cut_Door_LeftSide", (0.8, 1.2, 2.3), (-W / 2, -2.35, door_z))

    wz = zbase + SLAB_T + 0.95 + 1.3 / 2
    front_windows = [(-0.3, 1.5), (2.4, 1.5)]
    if floor_idx == 1:
        front_windows.insert(0, (-2.4, 1.4))
    for x, width in front_windows:
        cut_box(shell, f"Cut_FrontWindow_{floor_idx}_{x}", (width, 0.8, 1.3), (x, -D / 2, wz))

    for x in (-2.4, 0.0, 2.4):
        cut_box(shell, f"Cut_BackWindow_{floor_idx}_{x}", (1.5, 0.8, 1.3), (x, D / 2, wz))
    for y in (-1.4, 1.4):
        cut_box(shell, f"Cut_LeftWindow_{floor_idx}_{y}", (0.8, 1.4, 1.3), (-W / 2, y, wz))
    cut_box(shell, f"Cut_RightWindow_{floor_idx}", (0.8, 1.4, 1.3), (W / 2, 0.0, wz))


def add_partition(name, size, center, openings, material):
    wall = create_box(name, size, center, material)
    for opening_name, opening_size, opening_center in openings:
        cut_box(wall, "Cut_" + opening_name, opening_size, opening_center)
    return wall


def build_house(output_path: str):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    mat_cream = make_mat("MI_Wall_Cream", (0.92, 0.85, 0.72, 1.0))
    mat_roof = make_mat("MI_Roof_Brown", (0.38, 0.22, 0.14, 1.0))
    mat_floor = make_mat("MI_Floor_Grey", (0.65, 0.63, 0.60, 1.0))

    structural_parts = []

    # Hollow shells retain a 0.20 m floor slab at the bottom of each storey.
    for floor_idx in (0, 1):
        zbase = floor_idx * H_FLOOR
        shell = create_box(
            f"Shell_{'GF' if floor_idx == 0 else 'FF'}",
            (W, D, H_FLOOR), (0, 0, zbase + H_FLOOR / 2), mat_cream,
        )
        # Slightly overrun the open top to avoid a coplanar Boolean face.
        hollow_height = H_FLOOR - SLAB_T + 0.02
        cut_box(shell, f"Hollow_{floor_idx}",
                (W - 2 * WALL_T, D - 2 * WALL_T, hollow_height),
                (0, 0, zbase + SLAB_T + hollow_height / 2))
        if floor_idx == 1:
            # The stairwell intersects the first-floor slab only.
            cut_box(shell, "Stairwell_Hole", (1.6, 3.6, SLAB_T + 0.12),
                    (2.9, 0.2, H_FLOOR + SLAB_T / 2))
        add_openings(shell, floor_idx)
        structural_parts.append(shell)

    gf_mid = H_FLOOR / 2
    structural_parts.extend([
        add_partition("GF_Wall_Left", (WALL_T, D - 2 * WALL_T, H_FLOOR),
                      (-0.9, 0, gf_mid),
                      [("GF_Left_Passage", (0.8, 1.4, 2.3), (-0.9, 0, SLAB_T + 1.15))], mat_cream),
        add_partition("GF_Wall_Right", (WALL_T, D - 2 * WALL_T, H_FLOOR),
                      (0.9, 0, gf_mid),
                      [("GF_Right_Passage", (0.8, 1.4, 2.3), (0.9, 0, SLAB_T + 1.15))], mat_cream),
        add_partition("GF_Wall_Stair", (WALL_T, 4.0, H_FLOOR),
                      (2.1, 0.8, gf_mid),
                      [("GF_Stair_Passage", (0.8, 1.4, 2.3),
                        (2.1, -0.45, SLAB_T + 1.15))], mat_cream),
    ])

    ff_mid = H_FLOOR + H_FLOOR / 2
    structural_parts.append(add_partition(
        "FF_Wall_Hall", (W - 2 * WALL_T, WALL_T, H_FLOOR), (0, -0.6, ff_mid),
        [(f"FF_Bed_Door_{i}", (1.3, 0.8, 2.3), (x, -0.6, H_FLOOR + SLAB_T + 1.15))
         for i, x in enumerate((-2.4, 0.0, 2.0), 1)], mat_cream))
    structural_parts.extend([
        create_box("FF_Wall_Bed1", (WALL_T, 3.4, H_FLOOR), (-1.2, 1.1, ff_mid), mat_cream),
        create_box("FF_Wall_Bed2", (WALL_T, 3.4, H_FLOOR), (1.2, 1.1, ff_mid), mat_cream),
    ])

    # Front porch, now with its support columns located over the slab corners.
    structural_parts.extend([
        create_box("Porch_Slab", (2.8, 1.6, 0.2), (-0.4, -D / 2 - 0.8, 0.1), mat_floor),
        create_box("Porch_Pillar_L", (0.3, 0.3, 2.6), (-1.65, -D / 2 - 1.45, 1.3), mat_cream),
        create_box("Porch_Pillar_R", (0.3, 0.3, 2.6), (0.85, -D / 2 - 1.45, 1.3), mat_cream),
    ])
    walls = join_objects(structural_parts, "Block17_Walls-col")

    # Stair treads are visual; the separately named ramp is the walkable collider.
    num_steps, stair_len = 12, 3.2
    step_d = stair_len / num_steps
    step_h = H_FLOOR / num_steps
    steps = []
    for i in range(num_steps):
        z = SLAB_T + (i + 0.5) * step_h
        y = -1.4 + (i + 0.5) * step_d
        steps.append(create_box(f"Step_{i + 1:02d}", (1.4, step_d, step_h),
                                (2.9, y, z), mat_floor))
    join_objects(steps, "Stairs_Visual")

    ramp_len = math.hypot(stair_len, H_FLOOR)
    ramp_angle = math.atan2(H_FLOOR, stair_len)
    ramp = create_box("Stairs_Ramp-colonly", (1.4, ramp_len, 0.1),
                      (2.9, 0.2, SLAB_T + H_FLOOR / 2 - 0.05))
    ramp.rotation_euler.x = ramp_angle

    # Gable roof: two thin, solid panels, ridge running along the house length.
    overhang = 0.35
    half_span = D / 2 + overhang
    rise = 2.2
    pitch = math.atan2(rise, half_span)
    slope_len = math.hypot(half_span, rise)
    z_base = 2 * H_FLOOR
    z_center = z_base + rise / 2
    y_center = half_span / 2
    create_box("Roof_Slope_Left", (W + 2 * overhang, slope_len, 0.14),
               (0, -y_center, z_center), mat_roof).rotation_euler.x = pitch
    create_box("Roof_Slope_Right", (W + 2 * overhang, slope_len, 0.14),
               (0, y_center, z_center), mat_roof).rotation_euler.x = -pitch

    loot_spots = {
        "LootSpawn_Lawn_01": (-1.5, -4.8, 0.0),
        "LootSpawn_Lawn_02": (-0.5, -5.0, 0.0),
        "LootSpawn_Lawn_03": (0.5, -4.8, 0.0),
        "LootSpawn_GF_Living": (-2.5, 0.0, SLAB_T),
        "LootSpawn_GF_Kitchen": (1.2, 1.5, SLAB_T),
        "LootSpawn_FF_Bed1": (-2.5, 1.5, H_FLOOR + SLAB_T),
        "LootSpawn_FF_Bed2": (0.0, 1.5, H_FLOOR + SLAB_T),
    }
    for name, location in loot_spots.items():
        empty = bpy.data.objects.new(name, None)
        empty.empty_display_type = "ARROWS"
        empty.empty_display_size = 0.5
        empty.location = location
        bpy.context.collection.objects.link(empty)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.context.scene.objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = walls
    bpy.ops.export_scene.gltf(
        filepath=output_path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_extras=True,
    )
    if not os.path.isfile(output_path):
        raise RuntimeError(f"GLB export did not create {output_path}")
    print(f"Block 17 house exported successfully: {output_path}")


if __name__ == "__main__":
    build_house(parse_output_path())
