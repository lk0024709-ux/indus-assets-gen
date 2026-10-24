#!/usr/bin/env python3
"""Shared character-pipeline helpers for the Indus asset tools.

Everything in here is palette-agnostic machinery used by both
``convert_character_obj.py`` (the single Player Tactical conversion) and
``convert_characters_batch.py`` (the whole character roster):

* colour maths — sRGB <-> linear, hex parsing, lighten
* solid Principled BSDF material creation
* OBJ import (with the Blender 4.x operator fallback)
* join / Y-up->Z-up / normalise to a target height with a bottom-centre origin
* flat vs smooth-by-angle shading
* GLB export + GLB re-parsing for verification
* an optional Cycles QA render (headless friendly)

Keeping this in one module means the two tools can never drift apart: whatever
shading/export rules ship for Player Tactical automatically apply to the rest
of the roster.
"""

from __future__ import annotations

import json
import math
import os
import struct

import bpy
from mathutils import Matrix

FEET_FRACTION = 0.15     # anything below 15 % of body height is "footwear"
SMOOTH_ANGLE_DEG = 40.0  # angle-based smoothing for the "smooth" mode


# ---------------------------------------------------------------------------
# Colour maths — hex is sRGB, converted to linear so the GLB displays the
# requested colour exactly (glTF baseColorFactor is linear).
# ---------------------------------------------------------------------------
def srgb_to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def linear_to_srgb(channel: float) -> float:
    return channel * 12.92 if channel <= 0.0031308 else 1.055 * channel ** (1 / 2.4) - 0.055


def hex_to_linear_rgba(value: str) -> tuple[float, float, float, float]:
    value = value.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return (srgb_to_linear(r), srgb_to_linear(g), srgb_to_linear(b), 1.0)


def linear_rgba_to_hex(rgba) -> str:
    return "".join(
        f"{max(0, min(255, round(linear_to_srgb(c) * 255))):02X}" for c in rgba[:3]
    )


def lighten_hex(value: str, amount: float) -> str:
    """Mix a hex colour towards white by ``amount`` (0..1) in sRGB space."""
    value = value.lstrip("#")
    out = []
    for i in (0, 2, 4):
        c = int(value[i:i + 2], 16) / 255.0
        out.append(round((c + (1.0 - c) * amount) * 255))
    return "".join(f"{max(0, min(255, c)):02X}" for c in out)


def set_bsdf_input(bsdf, names, value) -> bool:
    for name in names:
        if name in bsdf.inputs:
            bsdf.inputs[name].default_value = value
            return True
    return False


# ---------------------------------------------------------------------------
# Materials
# ---------------------------------------------------------------------------
def make_solid_material(name: str, hex_value: str, metallic: float = 0.0,
                        roughness: float = 0.8):
    """A Principled BSDF material with exactly one solid base colour."""
    mat = bpy.data.materials.new(name)
    if bpy.app.version < (5, 0, 0):
        mat.use_nodes = True
    mat.use_backface_culling = False
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is None:
        raise RuntimeError("Principled BSDF not found")
    rgba = hex_to_linear_rgba(hex_value)
    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Roughness"].default_value = roughness
    # A character must never be transparent or emissive.
    set_bsdf_input(bsdf, ("Alpha",), 1.0)
    set_bsdf_input(bsdf, ("Emission Strength",), 0.0)
    set_bsdf_input(bsdf, ("Emission Color", "Emission"), (0.0, 0.0, 0.0, 1.0))
    mat.diffuse_color = rgba
    return mat


# ---------------------------------------------------------------------------
# Scene / import / transform
# ---------------------------------------------------------------------------
def clear_scene() -> None:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    try:
        import addon_utils
        # The glTF exporter is a bundled extension; older bpy builds ship it
        # as an add-on that must be enabled explicitly.
        try:
            addon_utils.enable("io_scene_gltf2", default_set=True, persistent=True)
        except Exception:
            pass
    except Exception:
        pass


def import_obj(filepath: str):
    """Import an OBJ and return the imported mesh objects.

    Blender <= 3.6 ships the legacy ``bpy.ops.import_scene.obj`` operator.
    Blender 4.0 removed it in favour of the C++ ``bpy.ops.wm.obj_import``,
    which is what ``pip install bpy`` gives you today (5.0 here). We call the
    requested operator first and only fall back when it genuinely does not
    exist, so the script works on both the CI's bpy and older Blender.
    """
    if not os.path.isfile(filepath):
        raise FileNotFoundError(f"OBJ not found: {filepath}")
    before = {o.name for o in bpy.data.objects}
    try:
        # Legacy operator (Blender 2.8 - 3.6) - preferred when present.
        bpy.ops.import_scene.obj(filepath=filepath)
        importer = "bpy.ops.import_scene.obj (legacy OBJ importer)"
    except AttributeError:
        # Blender 4.x: the OBJ I/O is now the bundled "Wavefront OBJ" extension.
        bpy.ops.wm.obj_import(filepath=filepath)
        importer = "bpy.ops.wm.obj_import (Blender 4.x replacement)"
    imported = [o for o in bpy.data.objects if o.name not in before and o.type == "MESH"]
    if not imported:
        raise RuntimeError("OBJ import produced no mesh objects")
    return imported, importer


def join_meshes(objects):
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    if len(objects) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    return obj


def normalise_transform(obj, target_height: float, name: str | None = None):
    """Y-up OBJ -> Z-up Blender, exactly ``target_height`` m, origin bottom-centre.

    The source models face +Z (chest/tie/face point that way) and the OBJ "up"
    axis is +Y. Rotating +90 deg about X maps Y->Z (up) and Z->-Y, which the
    glTF exporter's Y-up conversion turns back into +Z facing the viewer.
    """
    me = obj.data
    if name:
        obj.name = name
        me.name = name
    me.transform(Matrix.Rotation(math.radians(90.0), 4, "X"))
    me.update()

    zs = [v.co.z for v in me.vertices]
    height = max(zs) - min(zs)
    if height <= 0:
        raise RuntimeError("Degenerate mesh (zero height)")
    scale = target_height / height
    me.transform(Matrix.Diagonal((scale, scale, scale, 1.0)))
    me.update()

    xs = [v.co.x for v in me.vertices]
    ys = [v.co.y for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    cx = (max(xs) + min(xs)) * 0.5
    cy = (max(ys) + min(ys)) * 0.5
    min_z = min(zs)
    me.transform(Matrix.Translation((-cx, -cy, -min_z)))
    me.update()

    obj.location = (0.0, 0.0, 0.0)
    obj.rotation_euler = (0.0, 0.0, 0.0)
    obj.scale = (1.0, 1.0, 1.0)
    return obj


# ---------------------------------------------------------------------------
# Shading
# ---------------------------------------------------------------------------
def clear_custom_normals(obj) -> None:
    """Drop the OBJ's baked split normals so the shading mode decides."""
    me = obj.data
    try:
        with bpy.context.temp_override(object=obj, active_object=obj,
                                       selected_objects=[obj],
                                       selected_editable_objects=[obj]):
            bpy.ops.mesh.customdata_custom_splitnormals_clear()
        return
    except Exception:
        pass
    attr = me.attributes.get("custom_normal")
    if attr is not None:
        me.attributes.remove(attr)


def set_shading(obj, mode: str, angle_deg: float = SMOOTH_ANGLE_DEG) -> None:
    """mode: "flat" | "smooth"."""
    me = obj.data
    clear_custom_normals(obj)
    if mode == "flat":
        for poly in me.polygons:
            poly.use_smooth = False
        me.update()
        return

    for poly in me.polygons:
        poly.use_smooth = True
    angle = math.radians(angle_deg)
    # Blender 4.1+ replaced auto-smooth with sharp-edge storage on the mesh.
    if hasattr(me, "set_sharp_from_angle"):
        me.set_sharp_from_angle(angle=angle)
    else:  # Blender <= 4.0
        me.use_auto_smooth = True
        me.auto_smooth_angle = angle
    me.update()


# ---------------------------------------------------------------------------
# Export + GLB inspection
# ---------------------------------------------------------------------------
def export_glb(obj, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    kwargs = dict(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=True,
        export_materials="EXPORT",
        export_image_format="NONE",
        export_texcoords=False,  # solid colours only: UVs would be dead weight
        export_normals=True,
        export_tangents=False,
        export_cameras=False,
        export_lights=False,
        export_animations=False,
        export_extras=True,
    )
    try:
        bpy.ops.export_scene.gltf(**kwargs)
    except TypeError:
        for option in ("export_image_format", "export_extras", "export_tangents"):
            kwargs.pop(option, None)
        bpy.ops.export_scene.gltf(**kwargs)
    if not os.path.isfile(path):
        raise RuntimeError(f"Export failed: {path} not written")


def read_glb(path: str) -> dict:
    """Return the JSON chunk of a GLB (and validate the container header)."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"glTF":
        raise RuntimeError("Not a GLB file")
    json_len = struct.unpack("<I", data[12:16])[0]
    return json.loads(data[20:20 + json_len])


def glb_stats(path: str) -> dict:
    """Parse a GLB back into the numbers we assert on."""
    with open(path, "rb") as fh:
        size = len(fh.read())
    gltf = read_glb(path)

    tris = 0
    pos_min = [1e9] * 3
    pos_max = [-1e9] * 3
    for mesh in gltf.get("meshes", []):
        for prim in mesh.get("primitives", []):
            if "indices" in prim:
                count = gltf["accessors"][prim["indices"]]["count"]
            else:
                count = gltf["accessors"][prim["attributes"]["POSITION"]]["count"]
            tris += count // 3
            acc = gltf["accessors"][prim["attributes"]["POSITION"]]
            for i in range(3):
                pos_min[i] = min(pos_min[i], acc["min"][i])
                pos_max[i] = max(pos_max[i], acc["max"][i])

    materials = {}
    for mat in gltf.get("materials", []):
        pbr = mat.get("pbrMetallicRoughness", {})
        materials[mat.get("name")] = {
            "hex": linear_rgba_to_hex(pbr.get("baseColorFactor", [1, 1, 1, 1])),
            "has_texture": "baseColorTexture" in pbr,
        }

    return {
        "bytes": size,
        "materials": materials,
        "material_count": len(gltf.get("materials", [])),
        "images": len(gltf.get("images", [])),
        "nodes": [n.get("name") for n in gltf.get("nodes", [])],
        "tris": tris,
        "height_m": round(pos_max[1] - pos_min[1], 4),
        "min": [round(v, 4) for v in pos_min],
        "max": [round(v, 4) for v in pos_max],
        "extras": gltf.get("nodes", [{}])[0].get("extras", {}) if gltf.get("nodes") else {},
    }


def verify_character_glb(path: str, expected_hex: dict, target_height: float) -> dict:
    """Assert a character GLB is solid-colour, correctly sized and grounded."""
    stats = glb_stats(path)

    if stats["images"]:
        raise RuntimeError(f"{os.path.basename(path)}: textures found — must be solid-colour only")
    for name, info in stats["materials"].items():
        if info["has_texture"]:
            raise RuntimeError(f"{os.path.basename(path)}: material '{name}' references a texture")

    for name, want in expected_hex.items():
        got = stats["materials"].get(name)
        if got is None:
            raise RuntimeError(f"{os.path.basename(path)}: material '{name}' missing")
        if got["hex"].upper() != want.lstrip("#").upper():
            raise RuntimeError(
                f"{os.path.basename(path)}: {name} is #{got['hex']}, expected #{want}"
            )

    if abs(stats["height_m"] - target_height) > 0.01:
        raise RuntimeError(
            f"{os.path.basename(path)}: height {stats['height_m']} m != {target_height} m"
        )
    if abs(stats["min"][1]) > 1e-3:
        raise RuntimeError(f"{os.path.basename(path)}: origin not at the feet (minY={stats['min'][1]})")
    if stats["tris"] <= 0:
        raise RuntimeError(f"{os.path.basename(path)}: no triangles exported")
    return stats


# ---------------------------------------------------------------------------
# Optional QA preview render (Cycles CPU — headless friendly)
# ---------------------------------------------------------------------------
def render_previews(obj, out_dir: str, height: float, views=None,
                    samples: int = 32, prefix: str = "preview",
                    resolution=(512, 768)) -> None:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.render.resolution_x, scene.render.resolution_y = resolution
    scene.render.film_transparent = False
    scene.world = bpy.data.worlds.new("PreviewWorld")
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs[0].default_value = (0.16, 0.17, 0.19, 1.0)
    bg.inputs[1].default_value = 1.0

    key = bpy.data.lights.new("Key", "AREA")
    key.energy = 420
    key.size = 3.0
    key_obj = bpy.data.objects.new("Key", key)
    scene.collection.objects.link(key_obj)
    key_obj.location = (2.6, -3.0, 3.4)
    key_obj.rotation_euler = (math.radians(52), 0, math.radians(40))

    fill = bpy.data.lights.new("Fill", "AREA")
    fill.energy = 160
    fill.size = 4.0
    fill_obj = bpy.data.objects.new("Fill", fill)
    scene.collection.objects.link(fill_obj)
    fill_obj.location = (-3.0, -2.0, 1.8)
    fill_obj.rotation_euler = (math.radians(78), 0, math.radians(-55))

    cam_data = bpy.data.cameras.new("Cam")
    cam_data.lens = 60
    cam = bpy.data.objects.new("Cam", cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam

    os.makedirs(out_dir, exist_ok=True)
    if views is None:
        views = {
            "front": (0.0, -3.2, height * 0.58),
            "three_quarter": (2.3, -2.3, height * 0.62),
        }
    for name, (x, y, z) in views.items():
        cam.location = (x, y, z)
        target_z = height * 0.52
        cam.rotation_euler = (
            math.atan2(math.hypot(x, y), z - target_z),
            0.0,
            math.atan2(y, x) + math.pi / 2,
        )
        scene.render.filepath = os.path.join(out_dir, f"{prefix}_{name}.png")
        bpy.ops.render.render(write_still=True)
