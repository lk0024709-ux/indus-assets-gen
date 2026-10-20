import bpy
import os
import math
from mathutils import Vector

# ==============================================================================
# 1. INITIALIZATION & SCENE CLEANUP
# ==============================================================================
bpy.ops.wm.read_factory_settings(use_empty=True)

OUTPUT_DIR = os.path.join("docs", "models", "modular")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ==============================================================================
# 2. HELPER FUNCTIONS
# ==============================================================================
def create_solid_material(name: str, rgb: tuple[float, float, float]) -> bpy.types.Material:
    """Creates a Principled BSDF material with a solid RGB base color."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None:
        bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")

    bsdf.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
    bsdf.inputs["Roughness"].default_value = 0.6
    return mat


def assign_material(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    """Replaces an object's material slots with the given material."""
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def set_origin_to_bottom_center(obj: bpy.types.Object) -> None:
    """Sets the object's origin to its bounding-box bottom-center and places it at (0, 0, 0)."""
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    # Apply rotation and scale so bounding box coordinates are accurate
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    # Calculate world-space bounding box limits
    bbox_world = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_x = min(v.x for v in bbox_world)
    max_x = max(v.x for v in bbox_world)
    min_y = min(v.y for v in bbox_world)
    max_y = max(v.y for v in bbox_world)
    min_z = min(v.z for v in bbox_world)

    bottom_center = Vector(((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, min_z))

    # Move 3D cursor to bottom-center, set object origin to cursor, and reset cursor
    saved_cursor = bpy.context.scene.cursor.location.copy()
    bpy.context.scene.cursor.location = bottom_center
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='MEDIAN')
    bpy.context.scene.cursor.location = saved_cursor

    # Snap object bottom-center origin to world (0, 0, 0)
    obj.location = (0.0, 0.0, 0.0)


def join_objects(main_obj: bpy.types.Object, parts: list[bpy.types.Object]) -> bpy.types.Object:
    """Joins a list of mesh objects into main_obj."""
    bpy.ops.object.select_all(action='DESELECT')
    main_obj.select_set(True)
    for part in parts:
        part.select_set(True)
    bpy.context.view_layer.objects.active = main_obj
    bpy.ops.object.join()
    return main_obj


def apply_boolean(
    target_obj: bpy.types.Object,
    cutter_obj: bpy.types.Object,
    operation: str = 'DIFFERENCE'
) -> None:
    """Applies a Boolean modifier to target_obj using cutter_obj and deletes cutter_obj."""
    bpy.ops.object.select_all(action='DESELECT')
    target_obj.select_set(True)
    bpy.context.view_layer.objects.active = target_obj

    mod = target_obj.modifiers.new(name="BooleanOp", type='BOOLEAN')
    mod.operation = operation
    mod.solver = 'EXACT'
    mod.use_self = True
    mod.object = cutter_obj

    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter_obj, do_unlink=True)


def export_block_to_glb(obj: bpy.types.Object, filename: str) -> None:
    """Exports the specified object as a standalone .glb file and removes it from the scene."""
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

    filepath = os.path.join(OUTPUT_DIR, filename)
    bpy.ops.export_scene.gltf(
        filepath=filepath,
        export_format='GLB',
        use_selection=True,
        export_apply=True
    )

    # Clean up the exported object before generating the next block
    bpy.data.objects.remove(obj, do_unlink=True)


# ==============================================================================
# 3. SHARED MATERIALS
# ==============================================================================
# Golden sandstone masonry (Amber Fort / Jaisalmer) — #D9C089
# #D9C089 sRGB -> linear so the GLB displays golden sandstone (not pale cream)
mat_sandstone_wall = create_solid_material("SandstoneWall", (0.6939, 0.5271, 0.2502))
mat_gold = create_solid_material("GoldYellow", (1.0, 0.8, 0.2))
mat_teal = create_solid_material("TealCyan", (0.2, 0.8, 0.8))
mat_sandstone = create_solid_material("SandstoneBeige", (0.9, 0.8, 0.7))
mat_red = create_solid_material("BandRed", (0.9, 0.15, 0.15))
mat_blue = create_solid_material("BandBlue", (0.15, 0.35, 0.9))
mat_yellow = create_solid_material("BandYellow", (1.0, 0.85, 0.1))


# ==============================================================================
# 4. BLOCK GENERATORS
# ==============================================================================
def build_wall_block() -> None:
    """BLOCK 1: wall_block.glb"""
    # Main Box: Width 10m, Depth 0.5m, Height 4m (Z: 0 to 4m -> center Z = 2.0)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 2.0))
    main_wall = bpy.context.active_object
    main_wall.name = "WallBlock"
    main_wall.scale = (10.0, 0.5, 4.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign_material(main_wall, mat_sandstone_wall)

    # Top Border: Width 10m, Depth 0.6m, Height 0.3m sitting on top (Z: 4.0 to 4.3m -> center Z = 4.15)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 4.15))
    top_border = bpy.context.active_object
    top_border.name = "WallTopBorder"
    top_border.scale = (10.0, 0.6, 0.3)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign_material(top_border, mat_gold)

    # Join parts, set origin to bottom-center (0,0,0), and export
    join_objects(main_wall, [top_border])
    set_origin_to_bottom_center(main_wall)
    export_block_to_glb(main_wall, "wall_block.glb")


def build_arch_block() -> None:
    """BLOCK 2: arch_block.glb"""
    # Main Box: Width 10m, Depth 0.5m, Height 6m (Z: 0 to 6m -> center Z = 3.0)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 3.0))
    arch_wall = bpy.context.active_object
    arch_wall.name = "ArchBlock"
    arch_wall.scale = (10.0, 0.5, 6.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign_material(arch_wall, mat_sandstone_wall)

    # Cutter Box: Width 4m, Depth 1m, Height 4m (bottom at Z=0 -> center at X=0, Y=0, Z=2.0)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 2.0))
    cutter_box = bpy.context.active_object
    cutter_box.name = "ArchCutterBox"
    cutter_box.scale = (4.0, 1.0, 4.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # Cutter Cylinder on top: Radius 2m, Depth 1m, rotated 90 deg on X, centered at (0, 0, 4.0)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32,
        radius=2.0,
        depth=1.0,
        location=(0.0, 0.0, 4.0),
        rotation=(math.pi / 2.0, 0.0, 0.0)
    )
    cutter_cyl = bpy.context.active_object
    cutter_cyl.name = "ArchCutterCylinder"
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)

    # Combine cutter box and cylinder into one unified arch cutter and set its origin to (0, 0, 0)
    apply_boolean(cutter_box, cutter_cyl, operation='UNION')
    set_origin_to_bottom_center(cutter_box)

    # Cut the arch out of the main box and delete the cutter
    apply_boolean(arch_wall, cutter_box, operation='DIFFERENCE')

    # Gold Border around the arch: left post, right post, and upper arch torus
    frame_thickness = 0.2
    frame_depth = 0.6

    # Left vertical frame post
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(-2.0, 0.0, 2.0))
    left_post = bpy.context.active_object
    left_post.scale = (frame_thickness, frame_depth, 4.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign_material(left_post, mat_gold)

    # Right vertical frame post
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(2.0, 0.0, 2.0))
    right_post = bpy.context.active_object
    right_post.scale = (frame_thickness, frame_depth, 4.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign_material(right_post, mat_gold)

    # Curved upper arch frame (Torus sliced to top half at Z >= 4.0)
    bpy.ops.mesh.primitive_torus_add(
        major_radius=2.0,
        minor_radius=0.12,
        major_segments=32,
        minor_segments=12,
        location=(0.0, 0.0, 4.0),
        rotation=(math.pi / 2.0, 0.0, 0.0)
    )
    arch_torus = bpy.context.active_object
    # scale depth (world Y) — after rotation pi/2, local Z maps to world Y
    arch_torus.scale = (1.0, 1.0, 2.5)
    bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
    assign_material(arch_torus, mat_gold)

    # Slice off the bottom half of the torus (below Z = 4.0) so the arch passage remains open
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 2.0))
    torus_cutter = bpy.context.active_object
    torus_cutter.scale = (5.0, 2.0, 4.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    apply_boolean(arch_torus, torus_cutter, operation='DIFFERENCE')

    # Join gold frame to arch wall, set origin to bottom-center (0,0,0), and export
    join_objects(arch_wall, [left_post, right_post, arch_torus])
    set_origin_to_bottom_center(arch_wall)
    export_block_to_glb(arch_wall, "arch_block.glb")


def build_dome() -> None:
    """BLOCK 3: dome.glb"""
    # UV Sphere: Radius 5m, Segments 16, Rings 8 at (0, 0, 0)
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=16,
        ring_count=8,
        radius=5.0,
        location=(0.0, 0.0, 0.0)
    )
    dome = bpy.context.active_object
    dome.name = "Dome"
    assign_material(dome, mat_teal)

    # Slice sphere in half at Z=0 using a Boolean cube covering Z <= 0
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, -3.0))
    bottom_cutter = bpy.context.active_object
    bottom_cutter.name = "DomeHalfCutter"
    bottom_cutter.scale = (12.0, 12.0, 6.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    apply_boolean(dome, bottom_cutter, operation='DIFFERENCE')

    # Spire Cylinder on top: Radius 0.3m, Height 3m (Z: 5.0 to 8.0m -> center Z = 6.5)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=16,
        radius=0.3,
        depth=3.0,
        location=(0.0, 0.0, 6.5)
    )
    spire_cyl = bpy.context.active_object
    spire_cyl.name = "SpireCylinder"
    assign_material(spire_cyl, mat_gold)

    # Small Cone on top of Spire Cylinder (Z: 8.0 to 9.0m -> center Z = 8.5)
    bpy.ops.mesh.primitive_cone_add(
        vertices=16,
        radius1=0.45,
        radius2=0.0,
        depth=1.0,
        location=(0.0, 0.0, 8.5)
    )
    spire_cone = bpy.context.active_object
    spire_cone.name = "SpireCone"
    assign_material(spire_cone, mat_gold)

    # Join spire parts to dome, set origin to bottom-center (0,0,0), and export
    join_objects(dome, [spire_cyl, spire_cone])
    set_origin_to_bottom_center(dome)
    export_block_to_glb(dome, "dome.glb")


def build_pillar() -> None:
    """BLOCK 4: pillar.glb"""
    # Main Cylinder: Radius 0.5m, Height 6m, Vertices 16 (Z: 0 to 6.0m -> center Z = 3.0)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=16,
        radius=0.5,
        depth=6.0,
        location=(0.0, 0.0, 3.0)
    )
    pillar = bpy.context.active_object
    pillar.name = "Pillar"
    assign_material(pillar, mat_sandstone)

    # 3 Decorative Bands (Bottom, Middle, Top) using Torus meshes
    band_configs = [
        ("BandBottom", 0.6, mat_red),
        ("BandMiddle", 3.0, mat_blue),
        ("BandTop", 5.4, mat_yellow),
    ]
    bands = []
    for band_name, z_pos, band_mat in band_configs:
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.52,
            minor_radius=0.08,
            major_segments=16,
            minor_segments=12,
            location=(0.0, 0.0, z_pos)
        )
        band = bpy.context.active_object
        band.name = band_name
        assign_material(band, band_mat)
        bands.append(band)

    # Join bands to main pillar, set origin to bottom-center (0,0,0), and export
    join_objects(pillar, bands)
    set_origin_to_bottom_center(pillar)
    export_block_to_glb(pillar, "pillar.glb")


# ==============================================================================
# 5. MAIN EXECUTION
# ==============================================================================
if __name__ == "__main__":
    build_wall_block()
    build_arch_block()
    build_dome()
    build_pillar()
