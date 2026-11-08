import math

try:
    import bpy
except ImportError:  # pragma: no cover - outside Blender
    bpy = None

NAME = "Battle Royale Outfit"
DESCRIPTION = "Low-poly modular Battle Royale tactical tee, cargo pants, belt, pouches, thigh holster, and combat boots."
PARAMETERS = {
    "height": {"label": "Character height (m)", "type": "float", "min": 1.50, "max": 2.10, "step": 0.05, "default": 1.75},
    "tee_color": {"label": "Tee color", "type": "color", "default": "#6E7847"},
    "pants_color": {"label": "Cargo pants color", "type": "color", "default": "#7E6E4B"},
    "gear_color": {"label": "Tactical gear color", "type": "color", "default": "#27272B"},
    "include_holster": {"label": "Thigh holster", "type": "bool", "default": True},
    "include_pouches": {"label": "Belt pouches + ammo", "type": "bool", "default": True},
    "include_boots": {"label": "Combat boots", "type": "bool", "default": True},
}


def _srgb_hex_to_linear(hex_color):
    rgb = tuple(int(hex_color[i:i + 2], 16) / 255.0 for i in (1, 3, 5))

    def to_lin(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return (to_lin(rgb[0]), to_lin(rgb[1]), to_lin(rgb[2]))


def build(p):
    k = p["height"] / 1.75
    palette = {
        "tee": _srgb_hex_to_linear(p["tee_color"]),
        "pants": _srgb_hex_to_linear(p["pants_color"]),
        "kneepad": (0.09, 0.11, 0.05),
        "black": _srgb_hex_to_linear(p["gear_color"]),
        "boot": (0.015, 0.015, 0.02),
        "steel": (0.65, 0.65, 0.68),
        "gold": (0.8, 0.55, 0.08),
        "brass": (0.7, 0.45, 0.1),
    }

    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 0))
    root = bpy.context.active_object
    root.name = "Outfit_BR"
    mats = {}

    def mat(key):
        if key in mats:
            return mats[key]
        m = bpy.data.materials.new("Outfit_BR_M_" + key)
        mats[key] = m
        m.use_nodes = True
        r, g, b = palette[key]
        m.diffuse_color = (r, g, b, 1)
        bsdf = m.node_tree.nodes.get("Principled BSDF") or m.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = (r, g, b, 1)
        metal = key in ("steel", "gold", "brass")
        bsdf.inputs["Roughness"].default_value = 0.3 if metal else 0.9
        bsdf.inputs["Metallic"].default_value = 1.0 if metal else 0.0
        return m

    def finish_part(o, name, key, scale=(1, 1, 1)):
        o.scale = scale
        o.name = name
        o.data.name = name
        o.data.materials.append(mat(key))
        bpy.ops.object.select_all(action="DESELECT")
        o.select_set(True)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.transform_apply(location=False, rotation=True, scale=True)
        for poly in o.data.polygons:
            poly.use_smooth = False
        o.parent = root
        return o

    def cyl(name, key, loc, r, h, sc=(1, 1, 1), rot=(0, 0, 0), v=8, r2=None):
        sloc = (loc[0] * k, loc[1] * k, loc[2] * k)
        if r2 is None:
            bpy.ops.mesh.primitive_cylinder_add(vertices=v, radius=r * k, depth=h * k, location=sloc, rotation=rot)
        else:
            bpy.ops.mesh.primitive_cone_add(vertices=v, radius1=r * k, radius2=r2 * k, depth=h * k, location=sloc, rotation=rot)
        return finish_part(bpy.context.active_object, name, key, sc)

    def box(name, key, loc, dim, rot=(0, 0, 0)):
        sloc = (loc[0] * k, loc[1] * k, loc[2] * k)
        sdim = (dim[0] * k, dim[1] * k, dim[2] * k)
        bpy.ops.mesh.primitive_cube_add(size=1, location=sloc, rotation=rot)
        return finish_part(bpy.context.active_object, name, key, sdim)

    cyl("Tee_Body", "tee", (0, 0, 1.275), 0.18, 0.51, sc=(1.1, 0.7, 1))
    cyl("Tee_Collar", "tee", (0, 0, 1.53), 0.085, 0.035, sc=(1, 0.9, 1))
    for s, side in ((1, "R"), (-1, "L")):
        cyl(f"Tee_Sleeve_{side}", "tee", (s * 0.285, 0, 1.429), 0.075, 0.2, rot=(0, s * math.radians(110), 0))
    box("Tee_ChestPatch", "black", (0.075, -0.118, 1.38), (0.07, 0.012, 0.08))
    box("Tee_ChestStar", "gold", (0.075, -0.125, 1.38), (0.03, 0.006, 0.03), rot=(0, math.radians(45), 0))

    cyl("Pants_Hips", "pants", (0, 0, 0.97), 0.21, 0.2, sc=(1, 0.65, 1))
    for s, side in ((1, "R"), (-1, "L")):
        cyl(f"Pants_Leg_{side}", "pants", (s * 0.1, 0, 0.65), 0.10, 0.74, r2=0.105)
        box(f"KneePad_{side}", "kneepad", (s * 0.1, -0.1, 0.52), (0.13, 0.05, 0.15))
    box("Cargo_Pocket", "pants", (0.215, -0.01, 0.74), (0.045, 0.12, 0.16))
    box("Cargo_Flap", "pants", (0.22, -0.01, 0.82), (0.05, 0.125, 0.04))

    if p["include_holster"]:
        box("Holster", "black", (-0.215, 0, 0.78), (0.05, 0.08, 0.2))
        for i, z in enumerate((0.88, 0.72)):
            cyl(f"Holster_Strap_{i}", "black", (-0.1, 0, z), 0.108, 0.03)

    cyl("Belt", "black", (0, 0, 1.04), 0.225, 0.07, sc=(1, 0.7, 1), v=12)
    box("Belt_Buckle", "black", (0, -0.16, 1.04), (0.06, 0.02, 0.05))
    if p["include_pouches"]:
        box("Pouch_R", "black", (0.25, -0.01, 1.0), (0.05, 0.1, 0.11))
        box("Pouch_L", "black", (-0.25, -0.01, 1.0), (0.05, 0.09, 0.1))
        for i in range(3):
            cyl(f"Bullet_{i}", "brass", (0.25, -0.04 + i * 0.03, 1.07), 0.008, 0.04, v=6)

    bpy.ops.mesh.primitive_torus_add(
        major_radius=0.025 * k,
        minor_radius=0.005 * k,
        major_segments=8,
        minor_segments=4,
        location=(0, -0.15 * k, 0.975 * k),
        rotation=(math.radians(90), 0, 0),
    )
    finish_part(bpy.context.active_object, "Carabiner", "steel")

    if p["include_boots"]:
        for s, side in ((1, "R"), (-1, "L")):
            cyl(f"Boot_Shaft_{side}", "boot", (s * 0.1, 0, 0.16), 0.086, 0.28, r2=0.096)
            box(f"Boot_Foot_{side}", "boot", (s * 0.1, -0.065, 0.06), (0.178, 0.26, 0.06))
            box(f"Boot_Sole_{side}", "black", (s * 0.1, -0.065, 0.015), (0.188, 0.28, 0.03))

    return root
