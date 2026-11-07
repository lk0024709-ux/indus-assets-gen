"""Generate clean, open battle-royale Blocks 15–18 for Blender, Godot and web.

Run headless with Blender:
  blender -b --python tools/generate_blocks_15_18.py
  blender -b --python tools/generate_blocks_15_18.py -- --output-dir /path/to/glbs
  blender -b --python tools/generate_blocks_15_18.py -- --preview

By default, four individual GLBs are written to docs/models/buildings/.
The optional preview mode builds all four side-by-side in one Blender scene.
Exterior and interior openings are assembled from wall segments (no Boolean
modifiers), and Godot collision suffixes are kept on walls and stair ramps.
"""
import argparse
import bpy
import bmesh
import math
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_OUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "buildings")

H = 3.2        # storey height (floor to floor)
WALL_T = 0.25  # exterior wall thickness
INT_T = 0.15   # interior wall thickness
SLAB = 0.20    # floor slab thickness
M_WALL, M_FLOOR = 0, 1
GREY = (0.62, 0.60, 0.57, 1.0)


# ------------------------------------------------------------------
# Opening helpers: (center along wall, width, sill, head)  heights are
# measured from the floor top of that storey.
# ------------------------------------------------------------------
def Door(c, w=1.2, h=2.3):
    return (c, w, 0.0, h)


def Win(c, w=1.4, sill=0.95, h=2.25):
    return (c, w, sill, h)


# ------------------------------------------------------------------
# Geometry helpers
# ------------------------------------------------------------------
def make_mat(name, rgba, rough=0.85):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = rgba
        bsdf.inputs["Roughness"].default_value = rough
    return mat


def add_box(bm, p0, p1, mat):
    (x0, y0, z0), (x1, y1, z1) = p0, p1
    if x1 - x0 < 1e-4 or y1 - y0 < 1e-4 or z1 - z0 < 1e-4:
        return
    verts = bmesh.ops.create_cube(bm, size=1.0)["verts"]
    bmesh.ops.scale(bm, vec=(x1 - x0, y1 - y0, z1 - z0), verts=verts)
    bmesh.ops.translate(bm, vec=((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), verts=verts)
    for f in {f for v in verts for f in v.link_faces}:
        f.material_index = mat


def wall(bm, axis, c, a, b, t, z0, z1, openings, mat):
    """axis 'x': wall runs along X at y=c.  axis 'y': runs along Y at x=c.
    a..b = extent along the wall, openings = list of Door()/Win()."""
    f0, f1 = c - t / 2, c + t / 2

    def seg(s0, s1, za, zb):
        if axis == "x":
            add_box(bm, (s0, f0, za), (s1, f1, zb), mat)
        else:
            add_box(bm, (f0, s0, za), (f1, s1, zb), mat)

    cur = a
    for (oc, w, sill, head) in sorted(openings):
        lo, hi = max(a, oc - w / 2), min(b, oc + w / 2)
        seg(cur, lo, z0, z1)              # solid pier before the opening
        seg(lo, hi, z0, z0 + sill)        # below the opening
        seg(lo, hi, z0 + head, z1)        # above the opening
        cur = max(cur, hi)
    seg(cur, b, z0, z1)


def slab(bm, x0, x1, y0, y1, z0, z1, mat, hole=None):
    if not hole:
        add_box(bm, (x0, y0, z0), (x1, y1, z1), mat)
        return
    hx0, hx1, hy0, hy1 = hole
    add_box(bm, (x0, y0, z0), (hx0, y1, z1), mat)
    add_box(bm, (hx1, y0, z0), (x1, y1, z1), mat)
    add_box(bm, (hx0, y0, z0), (hx1, hy0, z1), mat)
    add_box(bm, (hx0, hy1, z0), (hx1, y1, z1), mat)


def mk_obj(name, bm, mats):
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for m in mats:
        mesh.materials.append(m)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def make_roof(cfg, mat):
    W, D = cfg["W"], cfg["D"]
    ov = 0.4
    hx, hy = W / 2 + ov, D / 2 + ov
    zb = 2 * H + SLAB
    zt = zb + cfg["roof_rise"]
    rx = (hx - hy) if cfg.get("hip") else hx   # hip roof: shorter ridge
    verts = [(-hx, -hy, zb), (hx, -hy, zb), (hx, hy, zb), (-hx, hy, zb),
             (-rx, 0, zt), (rx, 0, zt)]
    faces = [(0, 1, 5, 4), (1, 2, 5), (2, 3, 4, 5), (3, 0, 4), (0, 3, 2, 1)]
    bm = bmesh.new()
    vs = [bm.verts.new(v) for v in verts]
    for f in faces:
        bm.faces.new([vs[i] for i in f])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return mk_obj(f"{cfg['name']}_Roof-col", bm, [mat])


def build_stairs(cfg, mat):
    st = cfg["stairs"]
    x0, x1, y0, run = st["x0"], st["x1"], st["y0"], st["run"]
    n = 16
    d, h = run / n, H / n
    bm = bmesh.new()
    for i in range(n):  # solid steps, each one reaches down to the slab
        add_box(bm, (x0, y0 + i * d, SLAB), (x1, y0 + (i + 1) * d, SLAB + (i + 1) * h), M_WALL)
    visual = mk_obj(f"{cfg['name']}_Stairs", bm, [mat])

    # invisible smooth ramp for CharacterBody3D (36 deg, under Godot's 45 deg limit)
    ang = math.atan2(H, run)
    length = math.hypot(run, H)
    w = x1 - x0
    bm2 = bmesh.new()
    add_box(bm2, (-w / 2, -length / 2, -0.05), (w / 2, length / 2, 0.05), 0)
    ramp = mk_obj(f"{cfg['name']}_Ramp-colonly", bm2, [mat])
    mid_y, mid_z = y0 + run / 2, SLAB + H / 2
    ramp.location = ((x0 + x1) / 2, mid_y + 0.05 * math.sin(ang), mid_z - 0.05 * math.cos(ang))
    ramp.rotation_euler.x = ang
    return [visual, ramp]


# ------------------------------------------------------------------
# Block builder
# ------------------------------------------------------------------
def build_block(cfg, ox=0.0):
    name, W, D = cfg["name"], cfg["W"], cfg["D"]
    m_wall = make_mat(f"{name}_Wall", cfg["wall"])
    m_floor = make_mat(f"{name}_Floor", GREY)
    m_roof = make_mat(f"{name}_Roof", cfg["roof"], 0.7)

    st = cfg["stairs"]
    sx0, sx1, sy0 = st["x0"], st["x1"], st["y0"]
    sy1 = sy0 + st["run"]

    bm = bmesh.new()

    # slabs: ground, first floor (with stairwell hole), roof deck
    slab(bm, -W / 2, W / 2, -D / 2, D / 2, 0, SLAB, M_FLOOR)
    slab(bm, -W / 2, W / 2, -D / 2, D / 2, H, H + SLAB, M_FLOOR, hole=(sx0, sx1, sy0, sy1))
    slab(bm, -W / 2, W / 2, -D / 2, D / 2, 2 * H, 2 * H + SLAB, M_FLOOR)

    # walls for both storeys
    for k in (0, 1):
        z0, z1 = k * H + SLAB, (k + 1) * H
        ex = cfg["ext"][k]
        wall(bm, "x", -D / 2 + WALL_T / 2, -W / 2, W / 2, WALL_T, z0, z1, ex.get("front", []), M_WALL)
        wall(bm, "x", D / 2 - WALL_T / 2, -W / 2, W / 2, WALL_T, z0, z1, ex.get("back", []), M_WALL)
        wall(bm, "y", -W / 2 + WALL_T / 2, -D / 2 + WALL_T, D / 2 - WALL_T, WALL_T, z0, z1, ex.get("left", []), M_WALL)
        wall(bm, "y", W / 2 - WALL_T / 2, -D / 2 + WALL_T, D / 2 - WALL_T, WALL_T, z0, z1, ex.get("right", []), M_WALL)
        for axis, c, a, b, ops in cfg["int"][k]:
            if a is None:
                a, b = (-D / 2 + WALL_T, D / 2 - WALL_T) if axis == "y" else (-W / 2 + WALL_T, W / 2 - WALL_T)
            wall(bm, axis, c, a, b, INT_T, z0, z1, ops, M_WALL)

    # porch + balcony / canopy above it
    p = cfg.get("porch")
    if p:
        x0, x1, dp = p["x0"], p["x1"], p["depth"]
        yf = -D / 2 - dp
        add_box(bm, (x0, yf, 0), (x1, -D / 2, SLAB), M_FLOOR)
        if p.get("pillars"):
            for px in (x0 + 0.05, x1 - 0.35):
                add_box(bm, (px, yf + 0.05, SLAB), (px + 0.3, yf + 0.35, H), M_WALL)
        th = SLAB if p["upper"] == "balcony" else 0.15
        add_box(bm, (x0, yf, H), (x1, -D / 2, H + th), M_FLOOR)
        if p.get("railing"):
            zt = H + th
            add_box(bm, (x0, yf, zt), (x1, yf + 0.12, zt + 1.0), M_WALL)
            add_box(bm, (x0, yf, zt), (x0 + 0.12, -D / 2, zt + 1.0), M_WALL)
            add_box(bm, (x1 - 0.12, yf, zt), (x1, -D / 2, zt + 1.0), M_WALL)

    objs = [mk_obj(f"{name}_Walls-col", bm, [m_wall, m_floor])]
    objs.append(make_roof(cfg, m_roof))
    objs += build_stairs(cfg, m_floor)

    # loot spawn markers (become Node3D in Godot)
    for lname, (x, y, z) in cfg["loot"]:
        e = bpy.data.objects.new(f"{name}_{lname}", None)
        e.empty_display_type = 'ARROWS'
        e.empty_display_size = 0.5
        e.location = (x, y, z)
        bpy.context.scene.collection.objects.link(e)
        objs.append(e)

    for o in objs:
        o.location.x += ox
    return objs


# ------------------------------------------------------------------
# Block configs (front = -Y, back = +Y)
# ------------------------------------------------------------------
UP = H + SLAB  # first floor top

BLOCK_15 = dict(
    name="Block15_OpenHouse", W=8.5, D=6.0,
    wall=(0.93, 0.90, 0.84, 1.0), roof=(0.18, 0.18, 0.20, 1.0), roof_rise=2.3,
    stairs=dict(x0=2.7, x1=4.0, y0=-2.2, run=4.4),
    porch=dict(x0=1.5, x1=4.25, depth=1.8, pillars=True, upper="balcony", railing=True),
    ext=[
        dict(front=[Win(-2.9), Win(-0.8), Door(1.9, 1.4)],
             back=[Win(-2.9), Win(-0.4), Door(1.9, 1.4)],
             left=[Win(0.0, 1.6)]),
        dict(front=[Win(-2.9), Win(-0.8), Door(2.9, 2.0)],
             back=[Win(-2.9), Win(-0.4), Win(2.9)],
             left=[Win(0.0, 1.6)]),
    ],
    int=[
        [("y", -1.9, None, None, [Door(0.5, 1.4)]), ("y", 1.0, None, None, [Door(0.5, 1.4)])],
        [("y", -1.9, None, None, [Door(-1.0)]), ("y", 1.0, None, None, [Door(-1.0)])],
    ],
    loot=[("Lawn_01", (-2.0, -4.0, 0.0)), ("Lawn_02", (-0.5, -4.2, 0.0)), ("Lawn_03", (0.9, -4.0, 0.0)),
          ("GF_Living", (-3.0, -1.0, SLAB)), ("FF_BedA", (-3.0, 1.0, UP))],
)

BLOCK_16 = dict(
    name="Block16_OpenShop", W=9.0, D=6.0,
    wall=(0.88, 0.85, 0.78, 1.0), roof=(0.22, 0.22, 0.24, 1.0), roof_rise=1.5,
    stairs=dict(x0=3.0, x1=4.25, y0=-2.2, run=4.4),
    porch=dict(x0=-4.5, x1=4.5, depth=1.0, pillars=False, upper="canopy"),
    ext=[
        dict(front=[Door(-2.9, 2.2), Door(0.0, 2.2), Win(3.1, 1.2)],
             back=[Win(-2.9, 1.6), Door(0.0, 1.4)],
             left=[Win(0.0, 1.6)]),
        dict(front=[Win(-2.9, 2.2, 0.9, 2.4), Win(0.0, 2.2, 0.9, 2.4), Win(3.1, 1.2)],
             back=[Win(-2.9, 1.6), Win(0.0, 1.6)],
             left=[Win(0.0, 1.6)]),
    ],
    int=[
        [("y", -1.5, None, None, [Door(0.0, 1.6)]), ("y", 1.5, None, None, [Door(0.0, 1.6)])],
        [("y", -1.5, None, None, [Door(-0.5)]), ("y", 1.5, None, None, [Door(-0.5)])],
    ],
    loot=[("Lawn_01", (-3.5, -4.6, 0.0)), ("Lawn_02", (0.5, -4.8, 0.0)), ("Lawn_03", (3.0, -4.6, 0.0)),
          ("GF_Shop", (0.0, 0.5, SLAB)), ("FF_Loft", (0.0, 1.0, UP))],
)

BLOCK_17 = dict(
    name="Block17_OpenFamilyHouse", W=8.0, D=6.0,
    wall=(0.92, 0.85, 0.72, 1.0), roof=(0.38, 0.22, 0.14, 1.0), roof_rise=2.2,
    stairs=dict(x0=2.45, x1=3.75, y0=-2.2, run=4.4),
    porch=dict(x0=-1.4, x1=1.4, depth=1.6, pillars=True, upper="canopy"),
    ext=[
        dict(front=[Win(-2.4, 1.5), Door(0.0, 1.4), Win(2.4, 1.5)],
             back=[Win(-2.4, 1.5), Door(0.0, 1.4), Win(2.4, 1.5)],
             left=[Win(-1.4), Win(1.4)]),
        dict(front=[Win(-2.4, 1.5), Win(0.0, 1.5), Win(2.4, 1.5)],
             back=[Win(-2.4, 1.5), Win(0.0, 1.5), Win(2.4, 1.5)],
             left=[Win(-1.4), Win(1.4)]),
    ],
    int=[
        [("y", -1.2, None, None, [Door(0.0)]), ("y", 1.2, None, None, [Door(0.0)])],
        [("x", -0.6, -3.75, 2.45, [Door(-2.4), Door(0.0), Door(1.8, 1.0)]),
         ("y", -1.2, -0.6, 2.75, []), ("y", 1.2, -0.6, 2.75, [])],
    ],
    loot=[("Lawn_01", (-2.6, -4.0, 0.0)), ("Lawn_02", (-2.0, -4.6, 0.0)), ("Lawn_03", (2.2, -4.0, 0.0)),
          ("GF_Living", (-3.0, 0.0, SLAB)), ("GF_Kitchen", (1.9, 0.0, SLAB)),
          ("FF_Bed1", (-2.5, 1.5, UP)), ("FF_Bed2", (0.0, 1.5, UP))],
)

BLOCK_18 = dict(
    name="Block18_OpenCornerHouse", W=9.0, D=6.0, hip=True,
    wall=(0.95, 0.72, 0.60, 1.0), roof=(0.45, 0.47, 0.50, 1.0), roof_rise=2.0,
    stairs=dict(x0=-0.6, x1=0.6, y0=-2.2, run=4.4),
    porch=dict(x0=-4.5, x1=-1.0, depth=2.0, pillars=True, upper="balcony", railing=False),
    ext=[
        dict(front=[Door(-3.0, 1.4), Door(0.0, 1.4), Win(3.2, 1.6)],
             back=[Win(-3.0, 1.6), Win(0.0), Win(3.2, 1.6)],
             left=[Win(0.0, 1.6)],
             right=[Door(0.0)]),
        dict(front=[Door(-3.0, 1.8), Win(0.0), Win(3.2, 1.6)],
             back=[Win(-3.0, 1.6), Win(0.0), Win(3.2, 1.6)],
             left=[Win(0.0, 1.6)],
             right=[Win(0.0, 1.6)]),
    ],
    int=[
        [("y", -1.9, None, None, [Door(0.5)]), ("y", 1.9, None, None, [Door(0.5)])],
        [("y", -1.9, None, None, [Door(0.5)]), ("y", 1.9, None, None, [Door(0.5)])],
    ],
    loot=[("Lawn_01", (1.5, -4.2, 0.0)), ("Lawn_02", (3.0, -4.4, 0.0)), ("Lawn_03", (0.5, -4.8, 0.0)),
          ("GF_Living", (-3.2, 0.0, SLAB)), ("GF_Storage", (3.2, 0.0, SLAB))],
)

BLOCKS = [BLOCK_15, BLOCK_16, BLOCK_17, BLOCK_18]


# ------------------------------------------------------------------
# Run
# ------------------------------------------------------------------
def clear_scene():
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    for m in list(bpy.data.meshes):
        bpy.data.meshes.remove(m)


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=DEFAULT_OUT_DIR,
                        help="directory for the four GLB files")
    parser.add_argument("--preview", action="store_true",
                        help="build all four blocks side-by-side without exporting")
    return parser.parse_args(argv)


def main():
    args = parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    if args.preview:
        for i, cfg in enumerate(BLOCKS):
            build_block(cfg, i * 16.0)
        print("Blocks 15-18 built side-by-side for preview.")
        return

    os.makedirs(args.output_dir, exist_ok=True)
    for cfg in BLOCKS:
        clear_scene()
        build_block(cfg, 0.0)
        filepath = os.path.join(args.output_dir, cfg["name"] + ".glb")
        bpy.ops.export_scene.gltf(filepath=filepath, export_format="GLB")
        if not os.path.isfile(filepath) or os.path.getsize(filepath) == 0:
            raise RuntimeError(f"GLB export failed: {filepath}")
        print(f"Exported {filepath}")

    print("Blocks 15-18 generated successfully.")


if __name__ == "__main__":
    main()
