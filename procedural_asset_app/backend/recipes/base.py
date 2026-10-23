import bpy
import bmesh
import math

def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials):
        for item in list(datablocks):
            if item.users == 0:
                datablocks.remove(item)

def material_from_hex(hex_color, name="AssetMaterial"):
    rgb = tuple(int(hex_color[i:i+2], 16) / 255 for i in (1, 3, 5))
    def linear(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*[linear(c) for c in rgb], 1)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*[linear(c) for c in rgb], 1)
    bsdf.inputs["Roughness"].default_value = 0.68
    return mat

def cube(name, location, scale, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        mod = obj.modifiers.new("Soft edges", "BEVEL")
        mod.width = min(bevel, min(scale) * 0.22)
        mod.segments = 2
        obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return obj

def cylinder(name, location, radius, depth, vertices=16, radius_top=None):
    if radius_top is not None:
        bpy.ops.mesh.primitive_cone_add(vertices=vertices, radius1=radius, radius2=radius_top,
                                        depth=depth, location=location)
    else:
        bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                            location=location)
    obj = bpy.context.object
    obj.name = name
    bevel = obj.modifiers.new("Edge highlights", "BEVEL")
    bevel.width = min(radius, depth) * 0.04
    bevel.segments = 2
    obj.modifiers.new("Weighted normals", "WEIGHTED_NORMAL")
    return obj

def sphere(name, location, scale, segments=16, rings=8):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj

def finish(parts, color):
    if not parts:
        raise RuntimeError("Recipe produced no geometry")
    bpy.ops.object.select_all(action="DESELECT")
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    obj = bpy.context.object
    obj.name = "GeneratedAsset"
    mat = material_from_hex(color)
    obj.data.materials.clear()
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.material_index = 0
    # Recalculate normals with bmesh for reliable exports.
    bm = bmesh.new()
    bm.from_mesh(obj.data)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(obj.data)
    bm.free()
    obj.data.update()
    return obj

def smooth_mesh(obj, factor=0.5):
    for poly in obj.data.polygons:
        poly.use_smooth = True
    if factor > 0:
        mod = obj.modifiers.new("Surface smoothing", "SMOOTH")
        mod.factor = factor
        mod.iterations = 2
    return obj
