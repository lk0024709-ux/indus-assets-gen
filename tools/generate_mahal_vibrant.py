#!/usr/bin/env python3
"""
Vibrant Stylized Low-Poly Indian Palace (40x30 base, 30x20x15 walls)
- 2K textures: wall tiles intricate geometric, teal dome, yellow dome, royal blue doors
- Cube_project UVs, origin bottom-center, low-poly flat shading
- Boolean cutouts for multi-layered arches, domes sliced, spires, jharokhas, flags, parapet, fountain, palms
"""
from __future__ import annotations
import json, math, os, struct, sys, random
import bpy, bmesh
import numpy as np
from mathutils import Matrix, Vector

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURE_DIR = os.path.join(REPO_ROOT, "docs", "textures")
OUTPUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "buildings")

# Dimensions
BASE_W, BASE_D, BASE_H = 40.0, 30.0, 1.0
BUILD_W, BUILD_D, BUILD_H = 30.0, 20.0, 15.0  # walls box
ROOF_H = 0.5
CENTRAL_DOME_R = 8.0
CORNER_DOME_R = 4.0
JHAROKHA_DOME_R = 1.2

# Arch
DOOR_BLUE_H = 4.0  # central doors height
WIN_H = 3.0
ARCH_W_SMALL = 2.0
ARCH_W_LARGE = 3.5
ARCH_RADIUS_SMALL = 1.0
ARCH_RADIUS_LARGE = 1.75

_MAT_CACHE = {}

def _fft_noise(size, cutoff, seed):
    rng=np.random.default_rng(seed)
    spec=np.fft.fft2(rng.normal(size=(size,size)))
    fy=np.fft.fftfreq(size)[:,None]
    fx=np.fft.fftfreq(size)[None,:]
    r=np.sqrt(fx**2+fy**2)
    spec*=np.exp(-((r/cutoff)**2))
    f=np.real(np.fft.ifft2(spec))
    f-=f.mean()
    f/=f.std()+1e-9
    return f

def _lerp(c0,c1,t):
    c0=np.asarray(c0,dtype=np.float64); c1=np.asarray(c1,dtype=np.float64)
    return c0[None,None,:]+(c1-c0)[None,None,:]*t[...,None]

def ensure_palace_wall_tiles_2k():
    from PIL import Image
    dst=os.path.join(TEXTURE_DIR,"palace_wall_tiles_2k.png")
    # Always regenerate to ensure vibrant look
    size=2048
    tile=256
    # Base warm golden sandstone (Amber Fort / Jaisalmer) instead of salmon pink
    sandstone = np.array([0.85,0.75,0.55]) # #D9C089
    orange = np.array([0.97,0.50,0.18])
    yellow = np.array([0.98,0.85,0.22])
    blue = np.array([0.22,0.38,0.85])
    tan = np.array([0.72,0.59,0.40])      # deep sandstone accent
    # Create coordinate grids
    xs=np.arange(size)
    ys=np.arange(size)
    X,Y=np.meshgrid(xs,ys)
    tx=X % tile
    ty=Y % tile
    # Diamond distance (Manhattan) for main diamonds
    cx=tile//2; cy=tile//2
    dist=np.abs(tx-cx)+np.abs(ty-cy)
    inside = dist < tile*0.32
    # Tile indices for color variation
    ix=X//tile
    iy=Y//tile
    pat=(ix*2 + iy*3) % 4  # 0-3

    # Initialize with a sandstone base (warm cream -> golden tan) with subtle noise
    base_noise=_fft_noise(size,0.02,101)
    base_t=np.clip(0.5+0.15*base_noise,0,1)
    col=_lerp(sandstone-0.05, sandstone+0.06, base_t)

    # Create diamond colors array
    # For inside diamonds, choose color based on pattern + position
    # Use pat to select orange/yellow/blue/tan
    # We need to create col array size*size*3
    # Vectorized assignment
    mask0=(pat==0)&inside
    mask1=(pat==1)&inside
    mask2=(pat==2)&inside
    mask3=(pat==3)&inside
    col[mask0]=orange
    col[mask1]=yellow
    col[mask2]=blue
    col[mask3]=tan

    # Add inner smaller diamonds (contrast)
    inner_dist=np.abs(tx-cx)+np.abs(ty-cy)
    inner = inside & (inner_dist < tile*0.18)
    # inner diamonds get opposite color for intricate pattern
    inner_pat=(ix+iy)%2
    col[inner & (inner_pat==0)] = np.array([0.98,0.95,0.25]) # bright yellow center
    col[inner & (inner_pat==1)] = np.array([0.25,0.65,0.85]) # cyan center

    # Add diamond borders (dark outlines)
    border = inside & (dist > tile*0.28) & (dist < tile*0.32)
    col[border]=np.array([0.35,0.18,0.15])*0.9

    # Add triangle patterns in corners: small triangles at tile corners
    tri_mask = (tx < 40) & (ty < 40) & (~inside)
    # Alternate triangle color
    tri_pat=(ix+iy)%2
    col[tri_mask & (tri_pat==0)] = np.array([0.95,0.70,0.20])
    col[tri_mask & (tri_pat==1)] = np.array([0.30,0.45,0.90])

    # Add subtle fine grain
    fine=_fft_noise(size,0.45,102)
    col=np.clip(col+0.04*fine[...,None],0,1)
    # Add grout lines
    grout = (tx < 4) | (ty < 4)
    col[grout]=np.clip(col[grout]*0.7,0,1)

    # Contrast boost
    col=np.clip((col-0.5)*1.08+0.5,0,1)
    Image.fromarray((col*255).astype(np.uint8),"RGB").save(dst,"PNG")
    print("  generated palace_wall_tiles_2k.png 2048")

def ensure_palace_dome_teal_2k():
    from PIL import Image
    dst=os.path.join(TEXTURE_DIR,"palace_dome_teal_2k.png")
    size=2048
    base=_fft_noise(size,0.02,201)
    detail=_fft_noise(size,0.08,202)
    glint=_fft_noise(size,0.35,203)
    t=np.clip(0.5+0.25*base+0.15*detail,0,1)
    col=_lerp((0.08,0.55,0.58),(0.18,0.78,0.75),t)
    # shiny highlight streaks
    highlight=np.clip((glint-0.7)*3,0,1)**1.2
    hl=np.array([0.70,0.95,0.92])
    col=col*(1-highlight[...,None]*0.35)+hl*highlight[...,None]*0.35
    col=np.clip(col+0.03*detail[...,None],0,1)
    col=np.clip((col-0.5)*1.1+0.5,0,1)
    Image.fromarray((col*255).astype(np.uint8),"RGB").save(dst,"PNG")
    print("  generated palace_dome_teal_2k.png 2048")

def ensure_palace_dome_yellow_2k():
    from PIL import Image
    dst=os.path.join(TEXTURE_DIR,"palace_dome_yellow_2k.png")
    size=2048
    base=_fft_noise(size,0.02,301)
    detail=_fft_noise(size,0.08,302)
    glint=_fft_noise(size,0.35,303)
    t=np.clip(0.5+0.25*base+0.15*detail,0,1)
    col=_lerp((0.85,0.65,0.10),(0.99,0.86,0.22),t)
    highlight=np.clip((glint-0.65)*3,0,1)**1.2
    hl=np.array([1.0,0.96,0.60])
    col=col*(1-highlight[...,None]*0.35)+hl*highlight[...,None]*0.35
    col=np.clip(col+0.03*detail[...,None],0,1)
    col=np.clip((col-0.5)*1.1+0.5,0,1)
    Image.fromarray((col*255).astype(np.uint8),"RGB").save(dst,"PNG")
    print("  generated palace_dome_yellow_2k.png 2048")

def ensure_palace_door_blue_2k():
    from PIL import Image
    dst=os.path.join(TEXTURE_DIR,"palace_door_blue_2k.png")
    size=2048
    base=_fft_noise(size,0.02,401)
    detail=_fft_noise(size,0.08,402)
    t=np.clip(0.5+0.2*base+0.1*detail,0,1)
    col=_lerp((0.10,0.18,0.55),(0.22,0.35,0.75),t)
    # subtle wood grain for door panels
    grain=_fft_noise(size,0.04,403)
    grain_mask=np.clip(0.5+0.5*grain,0,1)
    col=col*(1-grain_mask[...,None]*0.15)+np.array([0.15,0.22,0.60])*grain_mask[...,None]*0.15
    col=np.clip((col-0.5)*1.05+0.5,0,1)
    Image.fromarray((col*255).astype(np.uint8),"RGB").save(dst,"PNG")
    print("  generated palace_door_blue_2k.png 2048")

def ensure_textures():
    os.makedirs(TEXTURE_DIR, exist_ok=True)
    ensure_palace_wall_tiles_2k()
    ensure_palace_dome_teal_2k()
    ensure_palace_dome_yellow_2k()
    ensure_palace_door_blue_2k()

# Helpers
def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _MAT_CACHE.clear()

def set_metric_units():
    s=bpy.context.scene
    s.unit_settings.system="METRIC"
    s.unit_settings.scale_length=1.0

def create_box(name,size,loc=(0,0,0),rot=(0,0,0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0,location=loc)
    o=bpy.context.active_object
    o.name=name; o.data.name=name+"Mesh"
    o.dimensions=tuple(size)
    o.rotation_euler=rot
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    return o

def create_cylinder(name,r,h,loc,verts=16):
    bpy.ops.mesh.primitive_cylinder_add(radius=r,depth=h,vertices=verts,location=loc)
    o=bpy.context.active_object
    o.name=name; o.data.name=name+"Mesh"
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    return o

def create_uv_sphere(name,r,loc,seg=16,rings=8):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg,ring_count=rings,radius=r,location=loc)
    o=bpy.context.active_object
    o.name=name; o.data.name=name+"Mesh"
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    # low-poly faceted: flat shading
    bpy.ops.object.select_all(action="DESELECT")
    o.select_set(True)
    bpy.context.view_layer.objects.active=o
    bpy.ops.object.shade_flat()
    return o

def create_cone(name,r1,r2,h,loc,verts=16):
    bpy.ops.mesh.primitive_cone_add(radius1=r1,radius2=r2,depth=h,vertices=verts,location=loc)
    o=bpy.context.active_object
    o.name=name; o.data.name=name+"Mesh"
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    bpy.ops.object.shade_flat()
    return o

def create_plane(name,size,loc,rot=(0,0,0)):
    bpy.ops.mesh.primitive_plane_add(size=size,location=loc)
    o=bpy.context.active_object
    o.name=name; o.data.name=name+"Mesh"
    o.rotation_euler=rot
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    return o

def apply_boolean_cut(target,cutter):
    mod=target.modifiers.new(name="Cut",type="BOOLEAN")
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

def cube_project_unwrap(obj,scale=1.0):
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try: bpy.ops.mesh.normals_make_consistent(inside=False)
    except: pass
    try:
        bpy.ops.uv.cube_project(cube_size=1.0)
    except TypeError:
        bpy.ops.uv.cube_project()
    bpy.ops.object.mode_set(mode="OBJECT")

def make_material(name,file,rough=0.8,metal=0.0,scale=1.0):
    key=f"{name}:{file}:{scale}"
    if key in _MAT_CACHE:
        return _MAT_CACHE[key]
    mat=bpy.data.materials.new(name)
    if bpy.app.version<(5,0,0):
        mat.use_nodes=True
    nt=mat.node_tree
    bsdf=nt.nodes.get("Principled BSDF")
    path=os.path.join(TEXTURE_DIR,file)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    img=bpy.data.images.load(path,check_existing=True)
    coord=nt.nodes.new("ShaderNodeTexCoord")
    coord.location=(-760,220)
    mapping=nt.nodes.new("ShaderNodeMapping")
    mapping.location=(-560,220)
    mapping.inputs["Scale"].default_value=(scale,scale,scale)
    tex=nt.nodes.new("ShaderNodeTexImage")
    tex.image=img
    tex.extension="REPEAT"
    tex.location=(-350,220)
    nt.links.new(coord.outputs["UV"],mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"],tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"],bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value=rough
    bsdf.inputs["Metallic"].default_value=metal
    _MAT_CACHE[key]=mat
    return mat

def make_solid(name,rgba,rough=0.8,metal=0.0):
    if name in _MAT_CACHE: return _MAT_CACHE[name]
    mat=bpy.data.materials.new(name)
    if bpy.app.version<(5,0,0):
        mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value=tuple(rgba)
    bsdf.inputs["Roughness"].default_value=rough
    bsdf.inputs["Metallic"].default_value=metal
    _MAT_CACHE[name]=mat
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
    coords=[obj.matrix_world@v.co for v in obj.data.vertices]
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
    coords=[obj.matrix_world@v.co for v in obj.data.vertices]
    return (min(c.x for c in coords),max(c.x for c in coords),min(c.y for c in coords),max(c.y for c in coords),min(c.z for c in coords),max(c.z for c in coords))

def add_omni_light(name,loc,energy=150,color=(1,0.85,0.62)):
    ld=bpy.data.lights.new(name=name,type="POINT")
    ld.energy=energy; ld.color=color; ld.shadow_soft_size=0.25
    o=bpy.data.objects.new(name,ld)
    o.location=tuple(loc)
    bpy.context.collection.objects.link(o)
    return o

def create_arch_cutter(name,w,h_rect,r,depth,cx,cy,cz_bottom,orient="x",seg=12):
    half_w=w/2
    bottom=cz_bottom
    top_rect=bottom+h_rect
    profile=[]
    profile.append((-half_w,bottom))
    profile.append((-half_w,top_rect))
    for i in range(1,seg):
        theta=math.pi*(1 - i/seg) # pi->0
        x=r*math.cos(theta)
        z=top_rect + r*math.sin(theta)
        profile.append((x,z))
    profile.append((half_w,top_rect))
    profile.append((half_w,bottom))
    n=len(profile)
    verts=[]; faces=[]
    for (px,pz) in profile:
        if orient=="x":
            verts.append((cx+px, cy - depth/2, pz))
        else:
            verts.append((cx - depth/2, cy+px, pz))
    off=n
    for (px,pz) in profile:
        if orient=="x":
            verts.append((cx+px, cy + depth/2, pz))
        else:
            verts.append((cx + depth/2, cy+px, pz))
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

def build_vibrant():
    walls=[] # objects that need wall tiles
    doors=[] # blue
    golds=[] # domes yellow/teal? We'll separate
    # Base
    base = create_box("Palace_Base", (BASE_W, BASE_D, BASE_H), (0,0,BASE_H/2))
    walls.append(base)
    # Stepped entrance at front (south side Y negative)
    # Front is at Y = -BASE_D/2 = -15, building south face at Y=-10, so base extends 5m front.
    # Create 3 steps descending outward south
    step_w=12.0
    for i, (w,d,h,z) in enumerate([
        (12,1.5,0.6,0.3),
        (10,1.2,0.4,0.7),
        (8,1.0,0.3,0.95)
    ]):
        # Place steps protruding south beyond base edge
        # base edge Y=-15, steps at Y = -15 -d/2 - accumulated
        y = -BASE_D/2 - d/2 - i*1.3
        s=create_box(f"Entrance_Step_{i}", (w,d,h), (0,y,z))
        walls.append(s)
    # Side stair ramps? Keep simple

    # Main building walls box 30x20x15 high
    # Use 4 wall pieces for hollow interior
    wall_thick=0.8
    floor_z=BASE_H
    building_bottom=floor_z
    building_top=floor_z+BUILD_H
    center_z=building_bottom+BUILD_H/2
    # Floor inside
    floor_inside=create_box("Building_Floor", (BUILD_W, BUILD_D, 0.3), (0,0,floor_z+0.15))
    walls.append(floor_inside)
    # Roof (flat)
    roof=create_box("Building_Roof", (BUILD_W, BUILD_D, 0.5), (0,0,building_top+0.25))
    walls.append(roof)
    # Walls 4 sides
    front_wall=create_box("Wall_Front", (BUILD_W, wall_thick, BUILD_H), (0, -BUILD_D/2+wall_thick/2, center_z))
    back_wall=create_box("Wall_Back", (BUILD_W, wall_thick, BUILD_H), (0, BUILD_D/2-wall_thick/2, center_z))
    left_wall=create_box("Wall_Left", (wall_thick, BUILD_D-2*wall_thick, BUILD_H), (-BUILD_W/2+wall_thick/2,0,center_z))
    right_wall=create_box("Wall_Right", (wall_thick, BUILD_D-2*wall_thick, BUILD_H), (BUILD_W/2-wall_thick/2,0,center_z))
    walls.extend([front_wall,back_wall,left_wall,right_wall])

    # Multi-layered arched windows/doors on all sides
    # Front (south) : 5 arches - central door large (w3.5 h5), 4 small windows (w2 h3)
    # Back similarly, Sides 3 arches each
    # Apply deep blue texture inside arches -> we will create blue backing panels after boolean
    arch_specs=[]
    # Helper to add arches per wall
    # Front south
    front_positions=[-9, -4.5, 0, 4.5, 9]
    front_sizes=[(ARCH_W_SMALL,2.5,ARCH_RADIUS_SMALL),(ARCH_W_SMALL,2.5,ARCH_RADIUS_SMALL),(ARCH_W_LARGE,3.5,ARCH_RADIUS_LARGE),(ARCH_W_SMALL,2.5,ARCH_RADIUS_SMALL),(ARCH_W_SMALL,2.5,ARCH_RADIUS_SMALL)]
    # Actually h_rect is straight height, radius is arch; total = h_rect+radius
    for idx, (x, (w,h_rect,r)) in enumerate(zip(front_positions, front_sizes)):
        cx=x; cy=-BUILD_D/2+wall_thick/2
        cutter=create_arch_cutter(f"Arch_Front_{idx}", w, h_rect, r, wall_thick+2, cx, cy, floor_z, orient="x", seg=10)
        apply_boolean_cut(front_wall, cutter)
        # Create blue interior panel recessed inside opening (slightly smaller, blue)
        # Create a thin arch panel with blue material placed inside wall thickness, slightly inset
        # Use same shape but thinner depth 0.2 and position at cy (wall center) recessed 0.2 inside
        # Create panel geometry via same function but as solid panel not cutter
        # Simpler: create a box panel with arch shape? We'll create a thin arch solid
        panel=create_arch_cutter(f"BluePanel_Front_{idx}", w*0.9, h_rect*0.9, r*0.9, 0.2, cx, cy, floor_z, orient="x", seg=10)
        # Instead of cutting, we keep this panel as blue door (thin)
        # Need to convert cutter mesh to solid? Our cutter is same shape, but we want panel to be solid filling opening
        # Keep panel object
        panel.name=f"BlueDoor_Front_{idx}"
        doors.append(panel)

    # Back north similar
    back_positions=[-9,-4.5,0,4.5,9]
    for idx, x in enumerate(back_positions):
        w=ARCH_W_LARGE if idx==2 else ARCH_W_SMALL
        h_rect=3.5 if idx==2 else 2.5
        r=ARCH_RADIUS_LARGE if idx==2 else ARCH_RADIUS_SMALL
        cx=x; cy=BUILD_D/2-wall_thick/2
        cutter=create_arch_cutter(f"Arch_Back_{idx}", w, h_rect, r, wall_thick+2, cx, cy, floor_z, orient="x", seg=10)
        apply_boolean_cut(back_wall, cutter)
        panel=create_arch_cutter(f"BluePanel_Back_{idx}", w*0.9, h_rect*0.9, r*0.9, 0.2, cx, cy, floor_z, orient="x", seg=10)
        panel.name=f"BlueDoor_Back_{idx}"
        doors.append(panel)

    # East wall (right) X=15, positions Y -6,0,6
    east_positions=[-6,0,6]
    for idx,y in enumerate(east_positions):
        w=ARCH_W_SMALL; h_rect=2.5; r=ARCH_RADIUS_SMALL
        cx=BUILD_W/2-wall_thick/2; cy=y
        cutter=create_arch_cutter(f"Arch_East_{idx}", w, h_rect, r, wall_thick+2, cx, cy, floor_z, orient="y", seg=10)
        apply_boolean_cut(right_wall, cutter)
        panel=create_arch_cutter(f"BluePanel_East_{idx}", w*0.9, h_rect*0.9, r*0.9, 0.2, cx, cy, floor_z, orient="y", seg=10)
        panel.name=f"BlueDoor_East_{idx}"
        doors.append(panel)

    # West wall left
    west_positions=[-6,0,6]
    for idx,y in enumerate(west_positions):
        cx=-BUILD_W/2+wall_thick/2; cy=y
        cutter=create_arch_cutter(f"Arch_West_{idx}", ARCH_W_SMALL, 2.5, ARCH_RADIUS_SMALL, wall_thick+2, cx, cy, floor_z, orient="y", seg=10)
        apply_boolean_cut(left_wall, cutter)
        panel=create_arch_cutter(f"BluePanel_West_{idx}", ARCH_W_SMALL*0.9, 2.5*0.9, ARCH_RADIUS_SMALL*0.9, 0.2, cx, cy, floor_z, orient="y", seg=10)
        panel.name=f"BlueDoor_West_{idx}"
        doors.append(panel)

    # Additional upper arches multi-layered effect: add small upper windows above main arches on front/back (second layer)
    for idx,x in enumerate([-7,7]):
        cy=-BUILD_D/2+wall_thick/2
        cutter=create_arch_cutter(f"Arch_Front_Upper_{idx}", 1.5, 1.2, 0.75, wall_thick+2, x, cy, floor_z+7, orient="x", seg=8)
        apply_boolean_cut(front_wall, cutter)
        panel=create_arch_cutter(f"BluePanel_Front_Upper_{idx}", 1.5*0.9,1.2*0.9,0.75*0.9,0.2,x,cy,floor_z+7,orient="x",seg=8)
        panel.name=f"BlueDoor_Front_Upper_{idx}"
        doors.append(panel)

    # Domes
    dome_objs=[]
    # Central teal dome r8 on top of center, sliced half
    # Building top at 16 (1+15), dome center at top
    central_h = building_top+0.25 # roof top ~16.25? Actually building_top=16, roof thickness 0.5 center at 16.25 top 16.5
    roof_top = building_top+0.5 # 16.5
    central_center = (0,0,roof_top)
    central_dome = create_uv_sphere("Central_Dome_Teal", CENTRAL_DOME_R, central_center, seg=16, rings=8)
    # Slice bottom half via cube at Z=roof_top
    slice_cube = create_box("Slice_Central", (40,40,20), (0,0,roof_top-10))
    apply_boolean_cut(central_dome, slice_cube)
    dome_objs.append(central_dome)
    # Corner domes r4 at corners of roof
    corners=[(BUILD_W/2-4, BUILD_D/2-4), (-BUILD_W/2+4, BUILD_D/2-4), (BUILD_W/2-4, -BUILD_D/2+4), (-BUILD_W/2+4, -BUILD_D/2+4)]
    for (cx,cy) in corners:
        d=create_uv_sphere(f"Corner_Dome_Yellow_{cx}_{cy}", CORNER_DOME_R, (cx,cy,roof_top), seg=12, rings=6)
        sc=create_box(f"Slice_Corner_{cx}_{cy}", (20,20,10), (cx,cy,roof_top-5))
        apply_boolean_cut(d,sc)
        dome_objs.append(d)
    # Small jharokha domes: tiny dome roofs on sides of building protruding balconies
    # Create 4 jharokhas: east/west sides at mid height Y positions
    jharokha_positions=[]
    # East side 2 jharokhas protruding outward at X ~17, Y -5,5 height 8
    for (cx,cy) in [(BUILD_W/2+1.2, -5),(BUILD_W/2+1.2,5), (-BUILD_W/2-1.2,-5), (-BUILD_W/2-1.2,5)]:
        bal=create_box(f"Jharokha_Balcony_{cx}_{cy}", (1.5,2.5,0.2), (cx,cy, floor_z+6))
        walls.append(bal)
        # Pillars under balcony (2 small)
        for dy in [-0.8,0.8]:
            cx_p=cx -0.5 if cx>0 else cx+0.5
            cy_p=cy+dy
            pill=create_cylinder(f"Jharokha_Pillar_{cx}_{cy}_{dy}", 0.15, 2.5, (cx_p,cy_p, floor_z+4.8), verts=8)
            walls.append(pill)
        # Tiny dome roof above balcony
        td=create_uv_sphere(f"Jharokha_Dome_{cx}_{cy}", JHAROKHA_DOME_R, (cx,cy, floor_z+6+1.0), seg=10, rings=6)
        sc2=create_box(f"Slice_Jharokha_{cx}_{cy}", (4,4,4), (cx,cy, floor_z+6-1))
        apply_boolean_cut(td,sc2)
        dome_objs.append(td)

    # Spire on central dome: cylinder + cone
    spire_base=create_cylinder("Spire_Cylinder", 0.6, 2.0, (0,0, roof_top+CENTRAL_DOME_R+1.0), verts=12)
    spire_cone=create_cone("Spire_Cone", 0.6, 0.0, 1.5, (0,0, roof_top+CENTRAL_DOME_R+2.5))
    gold_spires=[spire_base,spire_cone]
    # Also add spire on tiny corner domes? optional

    # Flags on domes
    flag_objs=[]
    # Central dome flag pole + plane
    pole_c=create_cylinder("FlagPole_Central", 0.08, 2.0, (0,0, roof_top+CENTRAL_DOME_R+3.5), verts=8)
    flag_c=create_plane("Flag_Central", 1.5, (0.8,0, roof_top+CENTRAL_DOME_R+3.5), rot=(0,0,0))
    # Make flag double-sided? Keep as plane
    flag_objs.extend([pole_c,flag_c])
    for (cx,cy) in corners:
        pole=create_cylinder(f"FlagPole_{cx}_{cy}", 0.06, 1.2, (cx,cy, roof_top+CORNER_DOME_R+1.0), verts=8)
        flag=create_plane(f"Flag_{cx}_{cy}", 1.0, (cx+0.6,cy, roof_top+CORNER_DOME_R+1.0), rot=(0,0,0))
        flag_objs.extend([pole,flag])

    # Decorative border parapet alternating sandstone/yellow blocks along flat roof
    parapet_objs=[]
    # Roof perimeter 30x20, parapet height 1, thickness 0.6
    # Create alternating blocks along edges every 1.5m
    sand_mat_name="Parapet_Sandstone"
    yellow_mat_name="Parapet_Yellow"
    # North edge Y=10, X -15 to 15
    for i, x in enumerate(np.arange(-BUILD_W/2+0.5, BUILD_W/2, 1.8)):
        col = i%2
        block=create_box(f"Parapet_North_{i}", (1.4,0.6,0.9), (x, BUILD_D/2-0.3, roof_top+0.45))
        parapet_objs.append((block, "sand" if col==0 else "yellow"))
    for i, x in enumerate(np.arange(-BUILD_W/2+0.5, BUILD_W/2, 1.8)):
        block=create_box(f"Parapet_South_{i}", (1.4,0.6,0.9), (x, -BUILD_D/2+0.3, roof_top+0.45))
        parapet_objs.append((block, "sand" if i%2==0 else "yellow"))
    for i, y in enumerate(np.arange(-BUILD_D/2+1.0, BUILD_D/2, 1.8)):
        block=create_box(f"Parapet_East_{i}", (0.6,1.4,0.9), (BUILD_W/2-0.3, y, roof_top+0.45))
        parapet_objs.append((block, "sand" if i%2==0 else "yellow"))
    for i, y in enumerate(np.arange(-BUILD_D/2+1.0, BUILD_D/2, 1.8)):
        block=create_box(f"Parapet_West_{i}", (0.6,1.4,0.9), (-BUILD_W/2+0.3, y, roof_top+0.45))
        parapet_objs.append((block, "sand" if i%2==0 else "yellow"))

    # Fountain and palm trees in front courtyard (on sand)
    # Front courtyard sand area: base front strip south of building Y -15 to -10, X -20 to 20, plus sides
    # Place fountain at front center (0, -12.5, BASE_H)
    fountain_objs=[]
    fountain_base=create_cylinder("Fountain_Base", 2.2, 0.4, (0, -12.5, BASE_H+0.2), verts=16)
    fountain_objs.append(fountain_base)
    fountain_mid=create_cylinder("Fountain_Mid", 1.2, 0.6, (0,-12.5, BASE_H+0.6), verts=16)
    fountain_objs.append(fountain_mid)
    fountain_top=create_cylinder("Fountain_Top", 0.4, 0.8, (0,-12.5, BASE_H+1.3), verts=12)
    fountain_objs.append(fountain_top)
    fountain_water=create_cylinder("Fountain_Water", 1.9, 0.1, (0,-12.5, BASE_H+0.4), verts=16)
    fountain_objs.append(fountain_water)

    # Palm trees: low-poly trunk + leaves
    palm_objs=[]
    palm_positions=[(-12,-12.5),(12,-12.5),(-8,-13),(8,-13)]
    for idx,(px,py) in enumerate(palm_positions):
        trunk=create_cylinder(f"Palm_Trunk_{idx}", 0.25, 4.0, (px,py, BASE_H+2.0), verts=8)
        palm_objs.append(trunk)
        # Leaves as small cones at top (vertical, no tilt below ground)
        for a in range(5):
            ang=a*72
            rad=math.radians(ang)
            lx=px+math.cos(rad)*0.4
            ly=py+math.sin(rad)*0.4
            leaf=create_cone(f"Palm_Leaf_{idx}_{a}", 0.4,0.0,0.9,(lx,ly, BASE_H+4.9))
            # keep vertical, no tilt, just radial offset
            palm_objs.append(leaf)
        top=create_uv_sphere(f"Palm_Top_{idx}", 0.5, (px,py,BASE_H+4.2), seg=8, rings=4)
        palm_objs.append(top)

    # Materials assignment
    # Wall tiles
    wall_mat=make_material("Palace_Wall_Tiles","palace_wall_tiles_2k.png",rough=0.85,metal=0.0,scale=0.5)
    # Actually palace_wall_tiles is highly patterned, use scale 0.5-1
    # Teal dome
    teal_mat=make_material("Palace_Dome_Teal","palace_dome_teal_2k.png",rough=0.35,metal=0.2,scale=1.0)
    yellow_mat=make_material("Palace_Dome_Yellow","palace_dome_yellow_2k.png",rough=0.35,metal=0.3,scale=1.0)
    blue_mat=make_material("Palace_Door_Blue","palace_door_blue_2k.png",rough=0.7,metal=0.0,scale=0.8)
    sand_mat=make_material("Palace_Sand","sand_1k.png",rough=0.9,metal=0.0,scale=0.3) if os.path.isfile(os.path.join(TEXTURE_DIR,"sand_1k.png")) else wall_mat
    # Sandstone/Yellow parapet solids
    sandstone_solid=make_solid("Parapet_Sandstone_Solid",(0.6939,0.5271,0.2502,1.0),rough=0.8)  # #D9C089 linear
    yellow_solid=make_solid("Parapet_Yellow_Solid",(0.98,0.85,0.25,1.0),rough=0.8)
    # Flag solids
    flag_red=make_solid("Flag_Red",(0.95,0.25,0.25,1.0))
    flag_yellow=make_solid("Flag_Yellow",(0.98,0.85,0.15,1.0))
    flag_green=make_solid("Flag_Green",(0.25,0.75,0.35,1.0))
    # Fountain water blue
    water_solid=make_solid("Fountain_Water_Solid",(0.30,0.60,0.85,1.0),rough=0.3)
    palm_trunk_mat=make_solid("Palm_Trunk",(0.45,0.30,0.18,1.0),rough=0.9)
    palm_leaf_mat=make_solid("Palm_Leaf",(0.25,0.55,0.25,1.0),rough=0.85)

    all_assigned=[]

    # Assign wall tiles to walls/base/roof/balcony/jharokha balconies
    for o in walls:
        cube_project_unwrap(o,scale=1.0)
        o.data.materials.clear()
        o.data.materials.append(wall_mat)
        all_assigned.append(o)
    # Blue doors
    for o in doors:
        cube_project_unwrap(o,scale=1.0)
        o.data.materials.clear()
        o.data.materials.append(blue_mat)
        all_assigned.append(o)
    # Teal central dome
    cube_project_unwrap(central_dome,scale=1.0)
    central_dome.data.materials.clear()
    central_dome.data.materials.append(teal_mat)
    all_assigned.append(central_dome)
    # Yellow corner domes
    for d in dome_objs:
        if d==central_dome: continue
        # Determine if corner (radius 4) vs jharokha (1.2)
        if "Jharokha" in d.name:
            cube_project_unwrap(d,scale=1.0)
            d.data.materials.clear()
            d.data.materials.append(yellow_mat)
            all_assigned.append(d)
        elif "Corner" in d.name:
            cube_project_unwrap(d,scale=1.0)
            d.data.materials.clear()
            d.data.materials.append(yellow_mat)
            all_assigned.append(d)
    # Gold spires - use yellow mat as gold
    for o in gold_spires:
        cube_project_unwrap(o,scale=1.0)
        o.data.materials.clear()
        o.data.materials.append(yellow_mat)
        all_assigned.append(o)
    # Flags
    for idx, o in enumerate(flag_objs):
        cube_project_unwrap(o,scale=1.0)
        o.data.materials.clear()
        # alternate colors
        if "Flag" in o.name:
            if idx%3==0: o.data.materials.append(flag_red)
            elif idx%3==1: o.data.materials.append(flag_yellow)
            else: o.data.materials.append(flag_green)
        else: # pole
            o.data.materials.append(make_solid("FlagPole_Solid",(0.55,0.35,0.18,1.0)))
        all_assigned.append(o)
    # Parapet
    for block, color in parapet_objs:
        cube_project_unwrap(block,scale=1.0)
        block.data.materials.clear()
        if color=="sand":
            block.data.materials.append(sandstone_solid)
        else:
            block.data.materials.append(yellow_solid)
        all_assigned.append(block)
    # Fountain
    for o in fountain_objs:
        cube_project_unwrap(o,scale=1.0)
        o.data.materials.clear()
        if "Water" in o.name:
            o.data.materials.append(water_solid)
        else:
            # sandstone base or marble? Use wall_mat with sand variant
            if "Base" in o.name or "Mid" in o.name:
                o.data.materials.append(sand_mat)
            else:
                o.data.materials.append(wall_mat)
        all_assigned.append(o)
    # Palms
    for o in palm_objs:
        cube_project_unwrap(o,scale=1.0)
        o.data.materials.clear()
        if "Trunk" in o.name:
            o.data.materials.append(palm_trunk_mat)
        else:
            o.data.materials.append(palm_leaf_mat)
        all_assigned.append(o)

    # Join all
    joined=join_objects(all_assigned,"MahalPalaceVibrant")
    set_origin_bottom_center(joined)
    # Lights
    add_omni_light("Vibrant_Light_Center",(0,0,8),energy=250,color=(1,0.95,0.85))
    add_omni_light("Vibrant_Light_Front",(0,-12.5,5),energy=180)
    return joined

def export_glb(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    kwargs=dict(filepath=path, export_format="GLB", export_image_format="JPEG", export_lights=True)
    try: bpy.ops.export_scene.gltf(export_image_quality=90,**kwargs)
    except TypeError: bpy.ops.export_scene.gltf(**kwargs)
    if not os.path.isfile(path): raise RuntimeError(f"Export failed {path}")
    return path

def verify_glb(path):
    with open(path,"rb") as f: data=f.read()
    if data[:4]!=b"glTF": raise RuntimeError("Not GLB")
    jl=struct.unpack("<I",data[12:16])[0]
    gltf=json.loads(data[20:20+jl])
    images=gltf.get("images",[])
    if not images: raise RuntimeError("No images")
    tris=0
    for m in gltf.get("meshes",[]):
        for p in m.get("primitives",[]):
            if "indices" in p: c=gltf["accessors"][p["indices"]]["count"]
            else: c=gltf["accessors"][p["attributes"]["POSITION"]]["count"]
            tris+=c//3
    lights=sum(1 for n in gltf.get("nodes",[]) if "KHR_lights_punctual" in n.get("extensions",{}))
    mats=len(gltf.get("materials",[]))
    print(f"  verified {os.path.basename(path)}: {os.path.getsize(path)} bytes, {mats} mats, {len(images)} imgs, ~{tris} tris, {lights} lights")
    return {"bytes":os.path.getsize(path),"mats":mats,"images":len(images),"tris":tris,"lights":lights}

def main():
    print(f"Blender bpy {bpy.app.version_string}")
    ensure_textures()
    clear_scene()
    set_metric_units()
    obj=build_vibrant()
    x0,x1,y0,y1,z0,z1=object_bbox(obj)
    print(f"  VibrantPalace: {x1-x0:.1f}x{y1-y0:.1f}x{z1-z0:.1f} | {len(obj.data.polygons)} faces | origin bottom-center (0,0,0)")
    path=os.path.join(OUTPUT_DIR,"mahal_palace_vibrant.glb")
    export_glb(path)
    verify_glb(path)
    print("Done — Vibrant Palace generated.")
    return 0

if __name__=="__main__":
    sys.exit(main())
