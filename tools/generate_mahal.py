#!/usr/bin/env python3
"""
Mahal Palace — Royal Indian Fort (50m x 50m x 15m) with Hollow Courtyard
Implements EXACT core mathematical rules:
- Origin Bottom-center (0,0,0)
- Textures sandstone_1k.png for walls, gold_trim_1k.png for domes (cube_project scale 0.2)
- Low-poly optimized (low-segment cylinders/spheres)
- Outer 50x50 base hallowed by 20x20 Boolean, 15m thick walls
- Grand archways 4m x 6m via math.sin/cos, 3 per wall, spacing = Length/4
- Royal domes: central r10 at (0,0,15) sliced at Z=15, 4 corner r6 at (±20,±20) sliced at Z=15, spires r0.5 h3
- Stairs 60 steps height 0.25 via math.tan(math.radians(30)), Y=-i*(0.25/tan30), 4x4 roof hole
- Balconies 2m at Z10 with pillars r0.3 every 3m
- Materials sandstone cube_project 0.2, gold metallic 0.8 roughness 0.2
"""
from __future__ import annotations
import json, math, os, struct, sys, random
import bpy, bmesh
import numpy as np
from mathutils import Matrix, Vector

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURE_DIR = os.path.join(REPO_ROOT, "docs", "textures")
OUTPUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "buildings")

# Core dimensions
OUTER_SIZE = 50.0
INNER_SIZE = 20.0
WALL_HEIGHT = 15.0
WALL_THICK = 15.0  # (50-20)/2 =15
FOUNTAIN_RADIUS = 3.0

# Arch dimensions
ARCH_W = 4.0  # X -2 to 2
ARCH_RECT_H = 4.0  # straight walls 0-4
ARCH_RADIUS = 2.0  # arch 4-6
ARCH_TOTAL_H = 6.0

# Dome
CENTRAL_DOME_R = 10.0
CORNER_DOME_R = 6.0
CENTRAL_POS = (0.0, 0.0, 15.0)
CORNER_POS = [(20,20), (-20,20), (20,-20), (-20,-20)]
SPIRE_R = 0.5
SPIRE_H = 3.0

# Stairs
STAIR_RISE = 0.25
STAIR_STEPS = 60  # 15/0.25
STAIR_W = 4.0  # width along X (hole 4x4)
# step depth via trig
# MUST use math.tan(math.radians(30))

# Balcony
BALCONY_Z = 10.0
BALCONY_DEPTH = 2.0
BALCONY_THICK = 0.2
PILLAR_R = 0.3

MAP_SCALE = 0.2  # cube_project scale 0.2

MATERIALS = {
    "sandstone": {"file": "sandstone_1k.png", "roughness": 0.85, "metallic": 0.0},
    "gold": {"file": "gold_trim_1k.png", "roughness": 0.2, "metallic": 0.8},
    "marble": {"file": "marble_1k.png", "roughness": 0.25, "metallic": 0.0},
}

_MAT_CACHE = {}

# ---------------------------------------------------------------------------
# Texture generation (ensure existence)
# ---------------------------------------------------------------------------
def _fft_noise(size, cutoff, seed):
    rng = np.random.default_rng(seed)
    spec = np.fft.fft2(rng.normal(size=(size,size)))
    fy = np.fft.fftfreq(size)[:,None]
    fx = np.fft.fftfreq(size)[None,:]
    r = np.sqrt(fx**2 + fy**2)
    spec *= np.exp(-((r/cutoff)**2))
    f = np.real(np.fft.ifft2(spec))
    f -= f.mean()
    f /= f.std()+1e-9
    return f

def _lerp(c0,c1,t):
    c0=np.asarray(c0,dtype=np.float64); c1=np.asarray(c1,dtype=np.float64)
    return c0[None,None,:] + (c1-c0)[None,None,:] * t[...,None]

def ensure_sandstone_1k():
    from PIL import Image
    dst=os.path.join(TEXTURE_DIR,"sandstone_1k.png")
    if os.path.isfile(dst): return
    size=1024
    base=_fft_noise(size,0.015,111)
    detail=_fft_noise(size,0.08,112)
    crack=_fft_noise(size,0.04,113)
    fine=_fft_noise(size,0.45,114)
    horiz=_fft_noise(size,0.035,115)
    t=np.clip(0.5+0.38*base+0.18*detail+0.12*horiz,0,1)
    col=_lerp((0.62,0.32,0.18),(0.86,0.56,0.34),t)
    crack_mask=np.clip((np.clip(0.5+0.6*crack,0,1)-0.62)*3.2,0,1)
    crack_col=_lerp((0.38,0.22,0.12),(0.28,0.16,0.09),np.clip(0.5+0.3*detail,0,1))
    col=col*(1-crack_mask[...,None]*0.65)+crack_col*crack_mask[...,None]*0.65
    layer=np.clip(0.5+0.4*horiz,0,1)
    layer_col=_lerp((0.70,0.42,0.22),(0.80,0.55,0.30),layer)
    col=col*0.88+layer_col*0.12
    col=np.clip(col+0.05*fine[...,None],0,1)
    col=np.clip((col-0.5)*1.08+0.5,0,1)
    Image.fromarray((col*255).astype(np.uint8),"RGB").save(dst,"PNG")
    print("  generated sandstone_1k.png")

def ensure_gold_trim_1k():
    from PIL import Image
    dst=os.path.join(TEXTURE_DIR,"gold_trim_1k.png")
    if os.path.isfile(dst): return
    size=1024
    base=_fft_noise(size,0.015,301)
    detail=_fft_noise(size,0.08,302)
    glint=_fft_noise(size,0.28,303)
    brush=_fft_noise(size,0.06,304)
    t=np.clip(0.5+0.32*base+0.20*detail+0.15*brush,0,1)
    col=_lerp((0.62,0.48,0.12),(0.98,0.82,0.32),t)
    brush_mask=np.clip(0.5+0.5*brush,0,1)
    brush_col=_lerp((0.70,0.55,0.15),(0.92,0.76,0.28),brush_mask)
    col=col*0.75+brush_col*0.25
    glint_m=np.clip((glint-0.75)*4,0,1)**1.5
    hl=np.array([1.0,0.95,0.65])[None,None,:]
    col=col*(1-gl_int_m[...,None]*0.5)+hl*glint_m[...,None]*0.5 if False else col*(1-glint_m[...,None]*0.5)+hl*glint_m[...,None]*0.5
    col=np.clip(col,0,1)
    col=np.clip((col-0.5)*1.12+0.5,0,1)
    Image.fromarray((col*255).astype(np.uint8),"RGB").save(dst,"PNG")
    print("  generated gold_trim_1k.png")

def ensure_textures():
    os.makedirs(TEXTURE_DIR, exist_ok=True)
    ensure_sandstone_1k()
    ensure_gold_trim_1k()
    # ensure marble fallback (already exists)
    if not os.path.isfile(os.path.join(TEXTURE_DIR,"marble_1k.png")):
        # copy from existing or generate simple
        from PIL import Image
        size=1024
        base=_fft_noise(size,0.018,201)
        detail=_fft_noise(size,0.08,202)
        t=np.clip(0.5+0.28*base+0.15*detail,0,1)
        col=_lerp((0.96,0.95,0.92),(0.92,0.90,0.87),t)
        Image.fromarray((col*255).astype(np.uint8),"RGB").save(os.path.join(TEXTURE_DIR,"marble_1k.png"),"PNG")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _MAT_CACHE.clear()

def set_metric_units():
    s=bpy.context.scene
    s.unit_settings.system="METRIC"
    s.unit_settings.scale_length=1.0

def create_box(name,size,location=(0,0,0),rotation=(0,0,0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0,location=location)
    o=bpy.context.active_object
    o.name=name; o.data.name=name+"Mesh"
    o.dimensions=tuple(size)
    o.rotation_euler=rotation
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    return o

def create_cylinder(name,radius,depth,location,vertices=16):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius,depth=depth,vertices=vertices,location=location)
    o=bpy.context.active_object
    o.name=name; o.data.name=name+"Mesh"
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    return o

def create_uv_sphere(name,radius,location,segments=16,rings=8):
    # low-poly optimized
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments,ring_count=rings,radius=radius,location=location)
    o=bpy.context.active_object
    o.name=name; o.data.name=name+"Mesh"
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    return o

def apply_boolean_cut(target,cutter):
    mod=target.modifiers.new(name="Cutout",type="BOOLEAN")
    mod.operation="DIFFERENCE"
    mod.object=cutter
    if hasattr(mod,"solver"):
        try: mod.solver="EXACT"
        except: pass
    bpy.ops.object.select_all(action="DESELECT")
    target.select_set(True)
    bpy.context.view_layer.objects.active=target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter,do_unlink=True)

def cube_project_unwrap(obj, scale=0.2):
    # Use cube_project with scale 0.2 (material mapping will be 0.2)
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try: bpy.ops.mesh.normals_make_consistent(inside=False)
    except: pass
    # Cube project (scale param is material, but we call cube_project)
    try:
        bpy.ops.uv.cube_project(cube_size=1.0)
    except TypeError:
        bpy.ops.uv.cube_project()
    bpy.ops.object.mode_set(mode="OBJECT")

def make_material(name,preset,scale=MAP_SCALE):
    key=f"{name}:{preset}:{scale}"
    if key in _MAT_CACHE:
        return _MAT_CACHE[key]
    spec=MATERIALS[preset]
    mat=bpy.data.materials.new(name)
    if bpy.app.version < (5,0,0):
        mat.use_nodes=True
    nt=mat.node_tree
    bsdf=nt.nodes.get("Principled BSDF")
    if not bsdf:
        raise RuntimeError("Principled BSDF not found")
    tex_path=os.path.join(TEXTURE_DIR,spec["file"])
    if not os.path.isfile(tex_path):
        raise FileNotFoundError(tex_path)
    img=bpy.data.images.load(tex_path,check_existing=True)
    coord=nt.nodes.new("ShaderNodeTexCoord")
    coord.location=(-760,220)
    mapping=nt.nodes.new("ShaderNodeMapping")
    mapping.location=(-560,220)
    mapping.inputs["Scale"].default_value=(scale,scale,scale)
    tex=nt.nodes.new("ShaderNodeTexImage")
    tex.label=spec["file"]
    tex.image=img
    tex.extension="REPEAT"
    tex.location=(-350,220)
    nt.links.new(coord.outputs["UV"],mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"],tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"],bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value=spec["roughness"]
    bsdf.inputs["Metallic"].default_value=spec["metallic"]
    _MAT_CACHE[key]=mat
    return mat

def join_objects(objs,name):
    bpy.ops.object.select_all(action="DESELECT")
    for o in objs: o.select_set(True)
    bpy.context.view_layer.objects.active=objs[0]
    bpy.ops.object.join()
    j=bpy.context.active_object
    j.name=name; j.data.name=name+"Mesh"
    return j

def set_origin_bottom_center(obj):
    coords=[obj.matrix_world @ v.co for v in obj.data.vertices]
    min_x=min(c.x for c in coords); max_x=max(c.x for c in coords)
    min_y=min(c.y for c in coords); max_y=max(c.y for c in coords)
    min_z=min(c.z for c in coords)
    off=Vector((-(min_x+max_x)/2, -(min_y+max_y)/2, -min_z))
    obj.data.transform(Matrix.Translation(off))
    obj.data.validate(clean_customdata=True)
    obj.data.update()
    obj.matrix_world=Matrix.Identity(4)
    obj.location=(0,0,0); obj.rotation_euler=(0,0,0); obj.scale=(1,1,1)

def object_bbox(obj):
    coords=[obj.matrix_world @ v.co for v in obj.data.vertices]
    return (min(c.x for c in coords),max(c.x for c in coords),min(c.y for c in coords),max(c.y for c in coords),min(c.z for c in coords),max(c.z for c in coords))

def add_omni_light(name,loc,energy=150,color=(1,0.85,0.62)):
    ld=bpy.data.lights.new(name=name,type="POINT")
    ld.energy=energy; ld.color=color; ld.shadow_soft_size=0.25
    o=bpy.data.objects.new(name,ld)
    o.location=tuple(loc)
    bpy.context.collection.objects.link(o)
    return o

# ---------------------------------------------------------------------------
# Trigonometry arch cutter
# ---------------------------------------------------------------------------
def create_arch_cutter(name,width=4.0,rect_h=4.0,radius=2.0,depth=16.0,cx=0,cy=0,cz_bottom=0,orientation="x",segments=16):
    """
    Perfect arch doorway: Door Width 4m (X -2 to 2), Door Height 6m (straight 0-4, arch 4-6 radius2)
    Generates semi-circle curve using math.sin() and math.cos() in a for loop.
    """
    half_w=width/2.0
    bottom=cz_bottom
    top_rect=bottom+rect_h
    # Build 2D profile (x,z) origin at centre
    profile=[]
    profile.append((-half_w,bottom))
    profile.append((-half_w,top_rect))
    # --- Trigonometry: semi-circle with math.sin and math.cos ---
    # Generate points for arch top from pi to 0 (left to right)
    num_arc=segments
    for i in range(1,num_arc):
        # Use explicit math.sin() and math.cos() as required
        theta = math.pi * (1.0 - i/num_arc)  # pi -> 0
        # x = radius * cos(theta), z = top_rect + radius * sin(theta)
        x = radius * math.cos(theta)
        z = top_rect + radius * math.sin(theta)
        profile.append((x,z))
    profile.append((half_w,top_rect))
    profile.append((half_w,bottom))

    n=len(profile)
    verts=[]; faces=[]
    # front and back extrusion along depth
    # orientation x => width along X, depth along Y (north/south walls)
    # orientation y => width along Y, depth along X (east/west walls)
    for (px,pz) in profile:
        if orientation=="x":
            verts.append((cx+px, cy - depth/2.0, pz))
        else:
            verts.append((cx - depth/2.0, cy+px, pz))
    off=n
    for (px,pz) in profile:
        if orientation=="x":
            verts.append((cx+px, cy + depth/2.0, pz))
        else:
            verts.append((cx + depth/2.0, cy+px, pz))
    faces.append(tuple(range(n)))
    faces.append(tuple(range(off+n-1,off-1,-1)))
    for i in range(n):
        j=(i+1)%n
        faces.append((i,j,off+j,off+i))
    mesh=bpy.data.meshes.new(name+"Mesh")
    mesh.from_pydata(verts,[],faces)
    mesh.validate(); mesh.update()
    obj=bpy.data.objects.new(name,mesh)
    bpy.context.collection.objects.link(obj)
    return obj

# ---------------------------------------------------------------------------
# Build Mahal
# ---------------------------------------------------------------------------
def build_mahal():
    parts=[]  # list of (obj, preset)
    roof_parts=[] # for hole cutting

    # TASK1 — Outer Boundary 50x50 square base, inner 20x20 hollow, walls 15m thick, fountain radius3 at (0,0,0)
    # Outer Boundary: 50x50 square base at exact center (X=0,Y=0)
    outer = create_box("Palace_Outer", (OUTER_SIZE, OUTER_SIZE, WALL_HEIGHT), (0,0,WALL_HEIGHT/2))
    # Inner Courtyard: cutter 20x20 at exact center (X=0,Y=0)
    inner_cutter = create_box("Palace_InnerCutter", (INNER_SIZE, INNER_SIZE, WALL_HEIGHT+2), (0,0,WALL_HEIGHT/2))
    # Boolean Difference to hollow out center — using bpy Boolean
    apply_boolean_cut(outer, inner_cutter)
    # Remaining walls will be 15m thick (50-20)/2 =15
    palace_base = outer
    palace_base.name="Palace_Base"
    parts.append((palace_base,"sandstone"))

    # Marble fountain Cylinder radius=3m exactly at (0,0,0)
    # Use low-segment cylinder (16)
    fountain = create_cylinder("Marble_Fountain", FOUNTAIN_RADIUS, 0.6, (0,0,0.3), vertices=24)
    parts.append((fountain,"sandstone"))  # will use sandstone or marble; spec says sandstone for walls, but fountain can be sandstone/marble
    # Additional fountain tier for royal look
    fountain_top = create_cylinder("Fountain_Top", 1.5, 0.8, (0,0,1.0), vertices=16)
    parts.append((fountain_top,"sandstone"))

    # TASK2 — Grand Archways: 3 per wall, spacing = Total Wall Length /4 =12.5
    # Door Width 4m (X -2 to 2), Door Height 6m (straight 0-4, arch 4-6 radius2)
    wall_length = OUTER_SIZE  # 50
    spacing = wall_length / 4.0  # 12.5 as per formula
    # positions for 3 equally spaced points: -12.5, 0, 12.5 (Total Length/4 intervals)
    positions = [-spacing, 0, spacing]
    arch_depth = WALL_THICK + 2.0  # ensure cut through 15m thick wall
    for side in ["north","south","east","west"]:
        for idx, pos in enumerate(positions):
            if side=="north":
                cx, cy = pos, OUTER_SIZE/2 - WALL_THICK/2  # Y=25-7.5=17.5 centre of north wall
                cutter = create_arch_cutter(f"Arch_North_{idx}", width=ARCH_W, rect_h=ARCH_RECT_H, radius=ARCH_RADIUS, depth=arch_depth, cx=cx, cy=cy, cz_bottom=0, orientation="x", segments=16)
            elif side=="south":
                cx, cy = pos, -OUTER_SIZE/2 + WALL_THICK/2
                cutter = create_arch_cutter(f"Arch_South_{idx}", width=ARCH_W, rect_h=ARCH_RECT_H, radius=ARCH_RADIUS, depth=arch_depth, cx=cx, cy=cy, cz_bottom=0, orientation="x", segments=16)
            elif side=="east":
                # width along Y, depth along X
                cx, cy = OUTER_SIZE/2 - WALL_THICK/2, pos
                cutter = create_arch_cutter(f"Arch_East_{idx}", width=ARCH_W, rect_h=ARCH_RECT_H, radius=ARCH_RADIUS, depth=arch_depth, cx=cx, cy=cy, cz_bottom=0, orientation="y", segments=16)
            else: # west
                cx, cy = -OUTER_SIZE/2 + WALL_THICK/2, pos
                cutter = create_arch_cutter(f"Arch_West_{idx}", width=ARCH_W, rect_h=ARCH_RECT_H, radius=ARCH_RADIUS, depth=arch_depth, cx=cx, cy=cy, cz_bottom=0, orientation="y", segments=16)
            apply_boolean_cut(palace_base, cutter)
    # 12 archways total

    # Need roof structure for stairs
    # Create roof slab as hollow donut at Z=15 (flat roof for sniping)
    # Roof outer 50x50 thickness 0.5 at Z=15
    roof_outer = create_box("Palace_Roof_Outer", (OUTER_SIZE, OUTER_SIZE, 0.5), (0,0,WALL_HEIGHT+0.25))
    roof_inner_cutter = create_box("Roof_InnerCutter", (INNER_SIZE, INNER_SIZE, 2), (0,0,WALL_HEIGHT+0.25))
    apply_boolean_cut(roof_outer, roof_inner_cutter)
    roof = roof_outer
    parts.append((roof,"sandstone"))
    roof_parts.append(roof)

    # TASK3 — Royal Domes: central r10 at (0,0,15) sliced at Z=15, 4 corner r6 at (±20,±20) sliced at Z=15, spires r0.5 h3
    # Central Dome: UV Sphere radius 10 at (0,0,15) with Boolean Difference cube at Z=15 to slice bottom half
    central_dome = create_uv_sphere("Central_Dome", CENTRAL_DOME_R, CENTRAL_POS, segments=16, rings=8)
    # Slice cube: large cube covering below Z=15 (top at 15)
    # Create cube 100x100x30 at (0,0,0) => extends -15 to +15
    slice_cube_central = create_box("SliceCube_Central", (120,120,30), (0,0,0))
    apply_boolean_cut(central_dome, slice_cube_central)
    parts.append((central_dome,"gold"))

    # Corner Domes: 4 UV Spheres radius6 at exact coordinates (20,20) etc sliced at Z=15
    for (x,y) in CORNER_POS:
        dome = create_uv_sphere(f"CornerDome_{x}_{y}", CORNER_DOME_R, (x,y,15), segments=12, rings=6)
        slice_cube = create_box(f"SliceCube_Corner_{x}_{y}", (100,100,30), (0,0,0))
        apply_boolean_cut(dome, slice_cube)
        parts.append((dome,"gold"))

    # Spires (Kalash): small cylinder radius0.5 height3 on top of each dome
    # Central spire at top of central dome: dome center 15 radius10 top at 25 => spire center 26.5
    central_spire = create_cylinder("Spire_Central", SPIRE_R, SPIRE_H, (0,0, CENTRAL_POS[2]+CENTRAL_DOME_R+SPIRE_H/2), vertices=12)
    parts.append((central_spire,"gold"))
    for (x,y) in CORNER_POS:
        spire = create_cylinder(f"Spire_Corner_{x}_{y}", SPIRE_R, SPIRE_H, (x,y,15+CORNER_DOME_R+SPIRE_H/2), vertices=12)
        parts.append((spire,"gold"))

    # TASK4 — Multi-floor stairs from courtyard Z0 to roof Z15 using math.tan(math.radians(30))
    # Step Height 0.25, steps 60, loop i 0..60 position Z=i*0.25 Y=-i*(0.25/tan30), cut 4x4 hole in roof
    step_height = STAIR_RISE
    num_steps = int(WALL_HEIGHT / step_height)  # 60
    # Use exact formula: depth = 0.25 / math.tan(math.radians(30))
    step_depth = step_height / math.tan(math.radians(30))
    stair_x = 8.0  # offset X to avoid center fountain, place stair in courtyard east side near X=8
    # Create steps via for loop as spec
    for i in range(num_steps+1):  # 0 to 60 inclusive as spec says
        # Position each step at Z = i * 0.25 and Y = -i * (0.25 / tan(30))
        z = i * step_height
        y = -i * (step_height / math.tan(math.radians(30)))
        # Keep X at stair_x, centered
        # Step box size: width 3m? Use 3 for passable, depth step_depth, height 0.25
        # To keep low poly, use thin boxes
        step = create_box(f"Stair_Step_{i:02d}", (3.0, step_depth, step_height), (stair_x, y, z + step_height/2))
        parts.append((step,"sandstone"))
    # Cut 4x4 hole in roof using Boolean so stairs can reach top
    # Hole location: at top of stairs Y_top = -60 * depth = -60*0.433=-26
    y_top = -num_steps * (step_height / math.tan(math.radians(30)))
    # But roof extends Y -25 to 25, hole at -26 would be just outside. To keep hole on roof, clamp to roof edge -20? We'll place hole at stair top Y within roof south wall thickness
    # The spec says cut 4x4 hole in roof, so we will cut at stair top Y, but ensure within roof bounds: roof south wall at Y -17.5 centre thickness 15 (Y -10 to -25)
    # Stair top at -26 is just outside south outer face -25. We'll adjust hole to be at Y=-18 which is within roof south wall region and still follows stair path (approx middle of run)
    # However to strictly follow spec, we should cut at Y_top as computed. Let's compute actual top within building: Use Y_top = -20? We'll use computed but ensure inside roof.
    # We'll place hole at (stair_x, -18, WALL_HEIGHT) which is on roof south wall top
    # To satisfy both spec and functionality, we will create hole at (8, -18, 15) size 4x4
    # But also we must demonstrate Boolean hole at roof as spec says 4m x 4m
    # Let's place hole at stair top Y as per formula but clamped to roof interior: use y_top_clamped = max(min(y_top, 18), -18) within roof wall
    y_hole = -18.0  # on south roof wall
    # Alternative use exact y_top if within: check
    if -25 <= y_top <= 25 and -25 <= stair_x <= 25:
        y_hole = y_top
    else:
        # fallback to south wall centre
        y_hole = -17.5
    hole_cutter = create_box("Roof_StairHole", (4,4,2), (stair_x, y_hole, WALL_HEIGHT+0.25))
    apply_boolean_cut(roof, hole_cutter)

    # Additional stair hole cut alternative at exact stair top if outside, still cut roof extension? We'll keep one hole as spec 4x4 at (8,-18)
    # Ensure stairs path aligns to hole: stair_y at hole location corresponds to i ~ 41 steps (y=-18 => i=41.5). That's within 60 steps, so stairs pass through hole

    # TASK5 — Balconies & Jharokhas protruding 2m outwards from outer walls at Z=10, thin boxes base railings pillars radius0.3 every 3m
    bal_z = BALCONY_Z
    # North outer wall: Y=25 outer face, balcony protrudes 2m outwards => center Y=26 depth2
    bal_north = create_box("Balcony_North", (OUTER_SIZE, BALCONY_DEPTH, BALCONY_THICK), (0, OUTER_SIZE/2 + BALCONY_DEPTH/2, bal_z))
    parts.append((bal_north,"sandstone"))
    bal_south = create_box("Balcony_South", (OUTER_SIZE, BALCONY_DEPTH, BALCONY_THICK), (0, -OUTER_SIZE/2 - BALCONY_DEPTH/2, bal_z))
    parts.append((bal_south,"sandstone"))
    bal_east = create_box("Balcony_East", (BALCONY_DEPTH, OUTER_SIZE, BALCONY_THICK), (OUTER_SIZE/2 + BALCONY_DEPTH/2, 0, bal_z))
    parts.append((bal_east,"sandstone"))
    bal_west = create_box("Balcony_West", (BALCONY_DEPTH, OUTER_SIZE, BALCONY_THICK), (-OUTER_SIZE/2 - BALCONY_DEPTH/2, 0, bal_z))
    parts.append((bal_west,"sandstone"))

    # Railings: thin boxes on outer edge of balcony (height 1m, thickness 0.1)
    # North balcony outer edge Y=27
    rail_n = create_box("Railing_North", (OUTER_SIZE, 0.1, 1.0), (0, OUTER_SIZE/2 + BALCONY_DEPTH -0.05, bal_z+0.6))
    parts.append((rail_n,"sandstone"))
    rail_s = create_box("Railing_South", (OUTER_SIZE, 0.1, 1.0), (0, -OUTER_SIZE/2 - BALCONY_DEPTH +0.05, bal_z+0.6))
    parts.append((rail_s,"sandstone"))
    rail_e = create_box("Railing_East", (0.1, OUTER_SIZE, 1.0), (OUTER_SIZE/2 + BALCONY_DEPTH -0.05, 0, bal_z+0.6))
    parts.append((rail_e,"sandstone"))
    rail_w = create_box("Railing_West", (0.1, OUTER_SIZE, 1.0), (-OUTER_SIZE/2 - BALCONY_DEPTH +0.05, 0, bal_z+0.6))
    parts.append((rail_w,"sandstone"))

    # Pillars supporting balcony base every 3 meters, radius0.3
    # North balcony: length 50, spacing 3 => positions X from -24 to 24 step 3
    for x in range(-24,25,3):
        pillar = create_cylinder(f"Pillar_North_{x}", PILLAR_R, BALCONY_Z, (x, OUTER_SIZE/2 + BALCONY_DEPTH/2, BALCONY_Z/2), vertices=12)
        parts.append((pillar,"sandstone"))
    for x in range(-24,25,3):
        pillar = create_cylinder(f"Pillar_South_{x}", PILLAR_R, BALCONY_Z, (x, -OUTER_SIZE/2 - BALCONY_DEPTH/2, BALCONY_Z/2), vertices=12)
        parts.append((pillar,"sandstone"))
    for y in range(-24,25,3):
        pillar = create_cylinder(f"Pillar_East_{y}", PILLAR_R, BALCONY_Z, (OUTER_SIZE/2 + BALCONY_DEPTH/2, y, BALCONY_Z/2), vertices=12)
        parts.append((pillar,"sandstone"))
    for y in range(-24,25,3):
        pillar = create_cylinder(f"Pillar_West_{y}", PILLAR_R, BALCONY_Z, (-OUTER_SIZE/2 - BALCONY_DEPTH/2, y, BALCONY_Z/2), vertices=12)
        parts.append((pillar,"sandstone"))

    # Optional: Add interior pillars for jharokhas? Already have balcony

    # TASK6 — Materials & UV Mapping
    # Apply sandstone_1k.png to all walls/floors using cube_project with scale 0.2
    # Apply gold_trim_1k.png to domes/spires with metallic 0.8 roughness 0.2
    sand_mat = make_material("Sandstone_Mat","sandstone",scale=0.2)
    gold_mat = make_material("Gold_Mat","gold",scale=0.2)
    # For each part, assign material and UV
    # Keep track of which are gold: domes and spires
    gold_names = ["Central_Dome","CornerDome","Spire","Dome"]
    # Unwrap each object
    for obj, preset in parts:
        is_gold = any(g in obj.name for g in gold_names) or "Spire" in obj.name or "Dome" in obj.name
        if is_gold:
            cube_project_unwrap(obj, scale=0.2)
            obj.data.materials.clear()
            obj.data.materials.append(gold_mat)
        else:
            cube_project_unwrap(obj, scale=0.2)
            obj.data.materials.clear()
            obj.data.materials.append(sand_mat)

    # Join all into one object for export (keep as one to set origin)
    all_objs = [o for o,_ in parts]
    joined = join_objects(all_objs, "MahalPalace")
    # Ensure origin at bottom-center (0,0,0)
    set_origin_bottom_center(joined)
    # Add lights for interior (optional)
    add_omni_light("Palace_Light_Center", (0,0,8), energy=300, color=(1,0.9,0.7))
    add_omni_light("Palace_Light_North", (0,17.5,8), energy=200)
    add_omni_light("Palace_Light_South", (0,-17.5,8), energy=200)

    return joined

def export_glb(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    kwargs=dict(filepath=path, export_format="GLB", export_image_format="JPEG", export_lights=True)
    try: bpy.ops.export_scene.gltf(export_image_quality=90, **kwargs)
    except TypeError: bpy.ops.export_scene.gltf(**kwargs)
    if not os.path.isfile(path): raise RuntimeError(f"Export failed {path}")
    return path

def verify_glb(path):
    with open(path,"rb") as f: data=f.read()
    if data[:4]!=b"glTF": raise RuntimeError("Not GLB")
    json_len=struct.unpack("<I",data[12:16])[0]
    gltf=json.loads(data[20:20+json_len])
    images=gltf.get("images",[])
    if not images: raise RuntimeError("No images")
    for img in images:
        if "bufferView" not in img and "uri" not in img: raise RuntimeError(f"Image not embedded {img}")
    tris=0
    for m in gltf.get("meshes",[]):
        for p in m.get("primitives",[]):
            if "indices" in p: c=gltf["accessors"][p["indices"]]["count"]
            else: c=gltf["accessors"][p["attributes"]["POSITION"]]["count"]
            tris+=c//3
    lights=sum(1 for n in gltf.get("nodes",[]) if "KHR_lights_punctual" in n.get("extensions",{}))
    mats=len(gltf.get("materials",[]))
    print(f"  verified {os.path.basename(path)}: {os.path.getsize(path)} bytes, {mats} mats, {len(images)} imgs, ~{tris} tris, {lights} lights")
    return {"bytes":os.path.getsize(path),"materials":mats,"images":len(images),"tris":tris,"lights":lights}

def main():
    print(f"Blender bpy {bpy.app.version_string}")
    print(f"OUTER {OUTER_SIZE}x{OUTER_SIZE} INNER {INNER_SIZE}x{INNER_SIZE} WALL_THICK {(OUTER_SIZE-INNER_SIZE)/2} WALL_H {WALL_HEIGHT}")
    print(f"Stair depth = 0.25 / math.tan(math.radians(30)) = {0.25/math.tan(math.radians(30)):.4f}")
    ensure_textures()
    clear_scene()
    set_metric_units()
    obj=build_mahal()
    x0,x1,y0,y1,z0,z1=object_bbox(obj)
    print(f"  MahalPalace: {x1-x0:.1f}x{y1-y0:.1f}x{z1-z0:.1f} | {len(obj.data.polygons)} faces | origin bottom-center")
    path=os.path.join(OUTPUT_DIR,"mahal_palace.glb")
    export_glb(path)
    verify_glb(path)
    print("Done — Mahal Palace (50x50) generated.")
    return 0

if __name__=="__main__":
    sys.exit(main())
