#!/usr/bin/env python3
"""
Rajasthani Mahal Master — Exterior + Interior Royal Darbar
Vibrant procedural textures, cube_project 0.2, bottom-center origin, low-poly optimized 4GB mobile
Phases 1-6 per spec: base 40x30, walls 30x20x12, sawtooth parapet, multi-layered arches, jharokhas,
central teal dome r6 + 4 yellow r3 + chhatris, interior checkered floor, pillars, ceiling dome, jali, throne etc.
Math sin/cos for arches & dome rings.
Export mahal_palace_master.glb -> push main via deploy.yml, live URL.
"""
from __future__ import annotations
import json, math, os, struct, sys
import bpy, bmesh
import numpy as np
from mathutils import Matrix, Vector

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURE_DIR = os.path.join(REPO_ROOT, "docs", "textures")
OUTPUT_DIR = os.path.join(REPO_ROOT, "docs", "models", "buildings")

BASE_W, BASE_D, BASE_H = 40.0, 30.0, 1.0
BUILD_W, BUILD_D, BUILD_H = 30.0, 20.0, 12.0
WALL_THICK = 0.8
CENTRAL_DOME_R = 6.0
CORNER_DOME_R = 3.0
CHHATRI_DOME_R = 1.4
JHAROKHA_R = 1.5

_MAT_CACHE = {}

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

def create_torus(name,major,minor,loc,seg=16,ring=8):
    bpy.ops.mesh.primitive_torus_add(major_radius=major,minor_radius=minor,major_segments=seg,minor_segments=ring,location=loc)
    o=bpy.context.active_object
    o.name=name; o.data.name=name+"Mesh"
    bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
    bpy.ops.object.shade_flat()
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

def cube_project_unwrap(obj,scale=0.2):
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try: bpy.ops.mesh.normals_make_consistent(inside=False)
    except: pass
    try: bpy.ops.uv.cube_project(cube_size=1.0)
    except TypeError: bpy.ops.uv.cube_project()
    bpy.ops.object.mode_set(mode="OBJECT")

def make_procedural_wall_mat(name="Rajasthani_Wall_Procedural", scale=0.2):
    key=name+":proc_wall"
    if key in _MAT_CACHE: return _MAT_CACHE[key]
    mat=bpy.data.materials.new(name)
    if bpy.app.version<(5,0,0): mat.use_nodes=True
    nt=mat.node_tree
    nt.nodes.clear()
    out=nt.nodes.new("ShaderNodeOutputMaterial"); out.location=(800,0)
    bsdf=nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location=(560,0)
    bsdf.inputs["Roughness"].default_value=0.85
    bsdf.inputs["Metallic"].default_value=0.0
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    coord=nt.nodes.new("ShaderNodeTexCoord"); coord.location=(-800,0)
    mapping=nt.nodes.new("ShaderNodeMapping"); mapping.location=(-600,0)
    mapping.inputs["Scale"].default_value=(scale,scale,scale)
    nt.links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    brick=nt.nodes.new("ShaderNodeTexBrick"); brick.location=(-350,150)
    brick.offset=0.5; brick.offset_frequency=3; brick.squash=0.8; brick.squash_frequency=2
    brick.inputs["Scale"].default_value=4.5
    brick.inputs["Mortar Size"].default_value=0.03
    brick.inputs["Mortar Smooth"].default_value=0.05
    brick.inputs["Bias"].default_value=0.0
    brick.inputs["Brick Width"].default_value=0.6
    brick.inputs["Row Height"].default_value=0.5
    nt.links.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    cr1=nt.nodes.new("ShaderNodeValToRGB"); cr1.location=(-80,150)
    cr1.color_ramp.elements[0].position=0.0; cr1.color_ramp.elements[0].color=(0.96,0.42,0.48,1)
    cr1.color_ramp.elements[1].position=1.0; cr1.color_ramp.elements[1].color=(0.96,0.42,0.48,1)
    e=cr1.color_ramp.elements.new(0.22); e.color=(0.97,0.50,0.18,1)
    e=cr1.color_ramp.elements.new(0.45); e.color=(0.98,0.85,0.22,1)
    e=cr1.color_ramp.elements.new(0.68); e.color=(0.22,0.38,0.85,1)
    e=cr1.color_ramp.elements.new(0.85); e.color=(0.85,0.25,0.55,1)
    nt.links.new(brick.outputs["Color"], cr1.inputs["Fac"])
    checker=nt.nodes.new("ShaderNodeTexChecker"); checker.location=(-350,-150)
    checker.inputs["Scale"].default_value=12.0
    nt.links.new(mapping.outputs["Vector"], checker.inputs["Vector"])
    cr2=nt.nodes.new("ShaderNodeValToRGB"); cr2.location=(-80,-50)
    cr2.color_ramp.elements[0].color=(0.98,0.44,0.50,1)
    cr2.color_ramp.elements[1].color=(0.98,0.85,0.25,1)
    nt.links.new(checker.outputs["Color"], cr2.inputs["Fac"])
    mix=nt.nodes.new("ShaderNodeMixRGB"); mix.location=(200,100); mix.blend_type="MIX"; mix.inputs[0].default_value=0.35
    nt.links.new(cr1.outputs["Color"], mix.inputs[1])
    nt.links.new(cr2.outputs["Color"], mix.inputs[2])
    nt.links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    brick.inputs["Mortar"].default_value=(0.92,0.88,0.85,1)
    _MAT_CACHE[key]=mat
    return mat

def make_checker_floor_mat(name="Darbar_Floor_Checker", scale=0.2):
    key=name+":checker"
    if key in _MAT_CACHE: return _MAT_CACHE[key]
    mat=bpy.data.materials.new(name)
    if bpy.app.version<(5,0,0): mat.use_nodes=True
    nt=mat.node_tree
    nt.nodes.clear()
    out=nt.nodes.new("ShaderNodeOutputMaterial"); out.location=(700,0)
    bsdf=nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location=(450,0)
    bsdf.inputs["Roughness"].default_value=0.45
    bsdf.inputs["Metallic"].default_value=0.05
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    coord=nt.nodes.new("ShaderNodeTexCoord"); coord.location=(-700,0)
    mapping=nt.nodes.new("ShaderNodeMapping"); mapping.location=(-500,0)
    mapping.inputs["Scale"].default_value=(scale,scale,scale)
    nt.links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    checker=nt.nodes.new("ShaderNodeTexChecker"); checker.location=(-250,0)
    checker.inputs["Scale"].default_value=6.0
    nt.links.new(mapping.outputs["Vector"], checker.inputs["Vector"])
    cr=nt.nodes.new("ShaderNodeValToRGB"); cr.location=(0,100)
    cr.color_ramp.elements[0].position=0.0; cr.color_ramp.elements[0].color=(0.96,0.35,0.55,1)
    e=cr.color_ramp.elements.new(0.25); e.color=(0.25,0.45,0.95,1)
    e=cr.color_ramp.elements.new(0.5); e.color=(0.98,0.85,0.18,1)
    e=cr.color_ramp.elements.new(0.75); e.color=(0.15,0.75,0.78,1)
    cr.color_ramp.elements[1].position=1.0; cr.color_ramp.elements[1].color=(0.96,0.35,0.55,1)
    nt.links.new(checker.outputs["Color"], cr.inputs["Fac"])
    nt.links.new(cr.outputs["Color"], bsdf.inputs["Base Color"])
    _MAT_CACHE[key]=mat
    return mat

def make_solid(name,rgba,rough=0.8,metal=0.0):
    if name in _MAT_CACHE: return _MAT_CACHE[name]
    mat=bpy.data.materials.new(name)
    if bpy.app.version<(5,0,0): mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value=tuple(rgba)
    bsdf.inputs["Roughness"].default_value=rough
    bsdf.inputs["Metallic"].default_value=metal
    _MAT_CACHE[name]=mat
    return mat

def make_image_mat(name,file,rough=0.8,metal=0.0,scale=0.2):
    key=f"{name}:{file}:{scale}"
    if key in _MAT_CACHE: return _MAT_CACHE[key]
    mat=bpy.data.materials.new(name)
    if bpy.app.version<(5,0,0): mat.use_nodes=True
    nt=mat.node_tree
    bsdf=nt.nodes.get("Principled BSDF")
    path=os.path.join(TEXTURE_DIR,file)
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    img=bpy.data.images.load(path,check_existing=True)
    coord=nt.nodes.new("ShaderNodeTexCoord"); coord.location=(-760,220)
    mapping=nt.nodes.new("ShaderNodeMapping"); mapping.location=(-560,220)
    mapping.inputs["Scale"].default_value=(scale,scale,scale)
    tex=nt.nodes.new("ShaderNodeTexImage"); tex.image=img; tex.extension="REPEAT"; tex.location=(-350,220)
    nt.links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value=rough
    bsdf.inputs["Metallic"].default_value=metal
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
    coords=[obj.matrix_world@v.co for v in obj.data.vertices]
    min_x=min(c.x for c in coords); max_x=max(c.x for c in coords)
    min_y=min(c.y for c in coords); max_y=max(c.y for c in coords)
    min_z=min(c.z for c in coords)
    off=Vector((-(min_x+max_x)/2, -(min_y+max_y)/2, -min_z))
    obj.data.transform(Matrix.Translation(off))
    obj.data.validate(clean_customdata=True); obj.data.update()
    obj.matrix_world=Matrix.Identity(4)
    obj.location=(0,0,0); obj.rotation_euler=(0,0,0); obj.scale=(1,1,1)

def object_bbox(obj):
    coords=[obj.matrix_world@v.co for v in obj.data.vertices]
    return (min(c.x for c in coords),max(c.x for c in coords),min(c.y for c in coords),max(c.y for c in coords),min(c.z for c in coords),max(c.z for c in coords))

def add_omni_light(name,loc,energy,color):
    ld=bpy.data.lights.new(name=name,type="POINT")
    ld.energy=energy; ld.color=color; ld.shadow_soft_size=0.25
    o=bpy.data.objects.new(name,ld); o.location=tuple(loc); bpy.context.collection.objects.link(o); return o

def create_arch_cutter(name,w,h_rect,r,depth,cx,cy,cz_bottom,orient="x",seg=12):
    half_w=w/2; bottom=cz_bottom; top_rect=bottom+h_rect
    profile=[(-half_w,bottom),(-half_w,top_rect)]
    for i in range(1,seg):
        theta=math.pi*(1 - i/seg)
        x=r*math.cos(theta); z=top_rect + r*math.sin(theta)
        profile.append((x,z))
    profile+=[(half_w,top_rect),(half_w,bottom)]
    n=len(profile); verts=[]; faces=[]
    for (px,pz) in profile:
        if orient=="x": verts.append((cx+px, cy - depth/2, pz))
        else: verts.append((cx - depth/2, cy+px, pz))
    off=n
    for (px,pz) in profile:
        if orient=="x": verts.append((cx+px, cy + depth/2, pz))
        else: verts.append((cx + depth/2, cy+px, pz))
    faces.append(tuple(range(n))); faces.append(tuple(range(off+n-1,off-1,-1)))
    for i in range(n):
        j=(i+1)%n; faces.append((i,j,off+j,off+i))
    mesh=bpy.data.meshes.new(name+"Mesh"); mesh.from_pydata(verts,[],faces); mesh.validate(); mesh.update()
    obj=bpy.data.objects.new(name,mesh); bpy.context.collection.objects.link(obj); return obj

def create_tri_prism(name,size,loc):
    s=size; h=s*math.sin(math.radians(60))
    verts=[(-s/2,0,0),(s/2,0,0),(0,h,0),(-s/2,0,s),(s/2,0,s),(0,h,s)]
    faces=[(0,1,2),(3,5,4),(0,3,4,1),(1,4,5,2),(2,5,3,0)]
    verts=[(x+loc[0], y+loc[1], z+loc[2]) for x,y,z in verts]
    mesh=bpy.data.meshes.new(name+"Mesh")
    mesh.from_pydata(verts,[],faces); mesh.validate(); mesh.update()
    obj=bpy.data.objects.new(name,mesh); bpy.context.collection.objects.link(obj)
    return obj

def build_master():
    walls=[]; doors_blue=[]; golds=[]; interior=[]; exterior=[]; pillar_objs=[]
    base=create_box("Base_Sandstone", (BASE_W,BASE_D,BASE_H),(0,0,BASE_H/2))
    walls.append(base)
    for i,(w,d,h,z) in enumerate([(12,1.6,0.5,0.25),(10,1.3,0.4,0.65),(8,1.0,0.3,1.0)]):
        y=-BASE_D/2 - d/2 - i*1.4
        s=create_box(f"Step_{i}",(w,d,h),(0,y,z))
        walls.append(s)
    wall_thick=WALL_THICK; floor_z=BASE_H; building_top=floor_z+BUILD_H; center_z=floor_z+BUILD_H/2
    floor_inside=create_box("Floor_Base",(BUILD_W,BUILD_D,0.3),(0,0,floor_z+0.15))
    walls.append(floor_inside)
    roof=create_box("Roof_Flat",(BUILD_W,BUILD_D,0.5),(0,0,building_top+0.25))
    walls.append(roof)
    front_wall=create_box("Wall_Front",(BUILD_W,wall_thick,BUILD_H),(0,-BUILD_D/2+wall_thick/2,center_z))
    back_wall=create_box("Wall_Back",(BUILD_W,wall_thick,BUILD_H),(0,BUILD_D/2-wall_thick/2,center_z))
    left_wall=create_box("Wall_Left",(wall_thick,BUILD_D-2*wall_thick,BUILD_H),(-BUILD_W/2+wall_thick/2,0,center_z))
    right_wall=create_box("Wall_Right",(wall_thick,BUILD_D-2*wall_thick,BUILD_H),(BUILD_W/2-wall_thick/2,0,center_z))
    walls.extend([front_wall,back_wall,left_wall,right_wall])
    # Sawtooth parapet
    parapet_objs=[]
    step=1.6
    for i,x in enumerate([ -BUILD_W/2+1.0 + k*step for k in range(int(BUILD_W/step)) ]):
        if x>BUILD_W/2-1.0: continue
        loc=(x, BUILD_D/2-0.2, building_top+0.5+0.4)
        prism=create_tri_prism(f"Parapet_N_{i}",0.9,loc)
        parapet_objs.append((prism,"pink" if i%2==0 else "yellow"))
    for i,x in enumerate([ -BUILD_W/2+1.0 + k*step for k in range(int(BUILD_W/step)) ]):
        if x>BUILD_W/2-1.0: continue
        loc=(x, -BUILD_D/2+0.2, building_top+0.5+0.4)
        prism=create_tri_prism(f"Parapet_S_{i}",0.9,loc)
        parapet_objs.append((prism,"pink" if i%2==0 else "yellow"))
    for i,y in enumerate([ -BUILD_D/2+1.5 + k*step for k in range(int(BUILD_D/step)) ]):
        if y>BUILD_D/2-1.5: continue
        loc=(BUILD_W/2-0.2, y, building_top+0.5+0.4)
        prism=create_tri_prism(f"Parapet_E_{i}",0.9,loc)
        prism.rotation_euler=(0,0,math.radians(90))
        bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
        parapet_objs.append((prism,"pink" if i%2==0 else "yellow"))
    for i,y in enumerate([ -BUILD_D/2+1.5 + k*step for k in range(int(BUILD_D/step)) ]):
        if y>BUILD_D/2-1.5: continue
        loc=(-BUILD_W/2+0.2, y, building_top+0.5+0.4)
        prism=create_tri_prism(f"Parapet_W_{i}",0.9,loc)
        prism.rotation_euler=(0,0,math.radians(90))
        bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
        parapet_objs.append((prism,"pink" if i%2==0 else "yellow"))
    # PHASE 2 arches
    front_arches=[(-8,2.8,2.2),(0,3.6,2.8),(8,2.8,2.2)]
    for idx,(x,w_outer,r_outer) in enumerate(front_arches):
        cx=x; cy=-BUILD_D/2+wall_thick/2
        outer_w=w_outer; outer_rect=3.0; outer_r=2.0
        cutter=create_arch_cutter(f"ArchOuter_Front_{idx}",outer_w,outer_rect,outer_r,wall_thick+3,cx,cy,floor_z,orient="x",seg=14)
        apply_boolean_cut(front_wall, cutter)
        inner_w=w_outer*0.78; inner_rect=2.5; inner_r=1.55
        inner_panel=create_arch_cutter(f"BlueInner_Front_{idx}",inner_w,inner_rect,inner_r,0.15,cx,cy,floor_z,orient="x",seg=12)
        inner_panel.name=f"BlueDoor_Front_{idx}"
        doors_blue.append(inner_panel)
        for t_i in range(8):
            theta=math.pi * (1 - t_i/7) * 0.9 + math.pi*0.05
            rx=outer_r*0.98*math.cos(theta); rz=outer_rect+outer_r*0.98*math.sin(theta)+floor_z
            trim=create_box(f"GoldTrim_Front_{idx}_{t_i}",(0.25,0.25,0.25),(cx+rx,cy,rz))
            golds.append(trim)
    for side, wall_obj, cx_base in [("East",right_wall,BUILD_W/2-wall_thick/2),("West",left_wall,-BUILD_W/2+wall_thick/2)]:
        for idx,y in enumerate([-5,5]):
            w_outer=2.6; outer_rect=3.0; outer_r=1.8
            cutter=create_arch_cutter(f"ArchOuter_{side}_{idx}",w_outer,outer_rect,outer_r,wall_thick+3,cx_base,y,floor_z,orient="y",seg=12)
            apply_boolean_cut(wall_obj, cutter)
            inner_w=w_outer*0.78; inner_rect=2.4; inner_r=1.45
            panel=create_arch_cutter(f"BlueInner_{side}_{idx}",inner_w,inner_rect,inner_r,0.15,cx_base,y,floor_z,orient="y",seg=12)
            panel.name=f"BlueDoor_{side}_{idx}"
            doors_blue.append(panel)
            for t_i in range(6):
                theta=math.pi*(1 - t_i/5)
                ry=outer_r*0.98*math.cos(theta); rz=outer_rect+outer_r*0.98*math.sin(theta)+floor_z
                trim=create_box(f"GoldTrim_{side}_{idx}_{t_i}",(0.22,0.22,0.22),(cx_base, y+ry, rz))
                golds.append(trim)
    for idx,x in enumerate([-7,7]):
        cy=-BUILD_D/2+wall_thick/2
        cutter=create_arch_cutter(f"JaliOuter_FrontU_{idx}",1.8,1.4,0.9,wall_thick+2,x,cy,floor_z+6.5,orient="x",seg=10)
        apply_boolean_cut(front_wall, cutter)
    # Jharokhas
    jharokha_domes=[]
    for (cx,cy) in [(BUILD_W/2+1.0, -5),(BUILD_W/2+1.0,5),(-BUILD_W/2-1.0,-5),(-BUILD_W/2-1.0,5)]:
        balcony=create_box(f"Jharokha_Balcony_{cx}_{cy}",(2.0,2.8,0.25),(cx,cy,floor_z+6))
        walls.append(balcony)
        for dy in [-0.9,0.9]:
            cxp=cx -0.6 if cx>0 else cx+0.6
            cyp=cy+dy
            pillar=create_cylinder(f"Jharokha_Pillar_{cx}_{cy}_{dy}",0.12,2.4,(cxp,cyp,floor_z+4.8),verts=8)
            golds.append(pillar)
        dome_center=(cx,cy,floor_z+6+1.1)
        dome=create_uv_sphere(f"Jharokha_Dome_{cx}_{cy}",JHAROKHA_R,dome_center,seg=12,rings=6)
        slice_box=create_box(f"Slice_Jharokha_{cx}_{cy}",(5,5,4),(cx,cy,floor_z+6-1))
        apply_boolean_cut(dome,slice_box)
        jharokha_domes.append(dome)
        sp=create_cone(f"Jharokha_Spire_{cx}_{cy}",0.18,0.0,0.6,(cx,cy,floor_z+6+1.1+JHAROKHA_R+0.3))
        golds.append(sp)
    # PHASE 3 roof domes
    roof_top=building_top+0.5
    dome_objs=[]
    central_dome=create_uv_sphere("Central_Dome_Teal",CENTRAL_DOME_R,(0,0,roof_top),seg=16,rings=8)
    slice_c=create_box("Slice_Central",(50,50,20),(0,0,roof_top-10))
    apply_boolean_cut(central_dome,slice_c)
    ring=create_torus("Central_Ring",CENTRAL_DOME_R*0.95,0.18,(0,0,roof_top),seg=16,ring=8)
    golds.append(ring)
    dome_objs.append(central_dome)
    kalash_base=create_cylinder("Kalash_Cyl",0.55,1.6,(0,0,roof_top+CENTRAL_DOME_R+0.8),verts=12)
    kalash_cone=create_cone("Kalash_Cone",0.55,0.0,1.2,(0,0,roof_top+CENTRAL_DOME_R+1.9))
    kalash_top=create_uv_sphere("Kalash_Top",0.25,(0,0,roof_top+CENTRAL_DOME_R+2.7),seg=8,rings=4)
    golds.extend([kalash_base,kalash_cone,kalash_top])
    flag_pole=create_cylinder("FlagPole_Central",0.07,2.2,(0,0,roof_top+CENTRAL_DOME_R+3.4),verts=8)
    flag_plane=create_plane("Flag_Central",1.6,(0.85,0,roof_top+CENTRAL_DOME_R+3.6))
    corners=[(BUILD_W/2-4,BUILD_D/2-4),(-BUILD_W/2+4,BUILD_D/2-4),(BUILD_W/2-4,-BUILD_D/2+4),(-BUILD_W/2+4,-BUILD_D/2+4)]
    corner_flags=[]
    for (cx,cy) in corners:
        d=create_uv_sphere(f"Corner_Yellow_{cx}_{cy}",CORNER_DOME_R,(cx,cy,roof_top),seg=12,rings=6)
        sc=create_box(f"Slice_Corner_{cx}_{cy}",(20,20,10),(cx,cy,roof_top-5))
        apply_boolean_cut(d,sc)
        dome_objs.append(d)
        r=create_torus(f"Corner_Ring_{cx}_{cy}",CORNER_DOME_R*0.92,0.14,(cx,cy,roof_top),seg=12,ring=6)
        golds.append(r)
        sp_cyl=create_cylinder(f"Corner_SpireCyl_{cx}_{cy}",0.32,0.9,(cx,cy,roof_top+CORNER_DOME_R+0.45),verts=10)
        sp_cone=create_cone(f"Corner_SpireCone_{cx}_{cy}",0.32,0.0,0.7,(cx,cy,roof_top+CORNER_DOME_R+1.1))
        golds.extend([sp_cyl,sp_cone])
        pole=create_cylinder(f"Corner_Pole_{cx}_{cy}",0.05,1.1,(cx,cy,roof_top+CORNER_DOME_R+1.6),verts=8)
        flag=create_plane(f"Corner_Flag_{cx}_{cy}",0.9,(cx+0.5,cy,roof_top+CORNER_DOME_R+1.7))
        golds.append(pole)
        corner_flags.append((pole,flag))
    chhatri_positions=[(8,6),(-8,6),(8,-6),(-8,-6)]
    for (cx,cy) in chhatri_positions:
        for dx,dy in [(-0.7,-0.7),(0.7,-0.7),(-0.7,0.7),(0.7,0.7)]:
            pill=create_cylinder(f"Chhatri_Pillar_{cx}_{cy}_{dx}_{dy}",0.10,1.8,(cx+dx,cy+dy,roof_top+0.9),verts=8)
            golds.append(pill)
        plat=create_box(f"Chhatri_Platform_{cx}_{cy}",(2.0,2.0,0.15),(cx,cy,roof_top+0.2))
        walls.append(plat)
        md=create_uv_sphere(f"Chhatri_Dome_{cx}_{cy}",CHHATRI_DOME_R,(cx,cy,roof_top+1.8),seg=10,rings=6)
        sc=create_box(f"Slice_Chhatri_{cx}_{cy}",(6,6,4),(cx,cy,roof_top+0.5))
        apply_boolean_cut(md,sc)
        dome_objs.append(md)
        sp=create_cone(f"Chhatri_Spire_{cx}_{cy}",0.12,0.0,0.45,(cx,cy,roof_top+1.8+CHHATRI_DOME_R+0.22))
        golds.append(sp)
    flag_objs=[flag_pole,flag_plane]
    # Phase 4 interior
    hole_cutter=create_box("Floor_Hole_Cutter",(4,4,1),( -BUILD_W/2+4, -BUILD_D/2+4, floor_z+0.15))
    apply_boolean_cut(floor_inside, hole_cutter)
    stair_rise=0.5; stair_depth= stair_rise / math.tan(math.radians(30))
    for i in range(8):
        z=floor_z - i*stair_rise
        y= -BUILD_D/2+4 + i*stair_depth
        x= -BUILD_W/2+4
        step=create_box(f"Interior_Stair_{i}",(3.5,stair_depth,0.25),(x,y,z))
        interior.append(step)
    pillar_positions=[]
    for y in [-6,-2,2,6]:
        pillar_positions.append((-BUILD_W/2+3, y))
        pillar_positions.append((BUILD_W/2-3, y))
    for idx,(px,py) in enumerate(pillar_positions):
        pillar=create_cylinder(f"Interior_Pillar_{idx}",0.45, BUILD_H-0.5,(px,py, floor_z+BUILD_H/2),verts=12)
        pillar_objs.append(pillar)
        for b_i,bz in enumerate([floor_z+2, floor_z+5, floor_z+8]):
            band=create_cylinder(f"PillarBand_{idx}_{b_i}",0.48,0.35,(px,py,bz),verts=12)
            interior.append(band)
    ceiling_dome=create_uv_sphere("Interior_Ceiling_Dome",7.0,(0,0,building_top-1.5),seg=16,rings=8)
    slice_ceiling=create_box("Slice_Ceiling",(40,40,20),(0,0,building_top-1.5+10))
    apply_boolean_cut(ceiling_dome,slice_ceiling)
    interior.append(ceiling_dome)
    chandelier_chain=create_cylinder("Chandelier_Chain",0.05,2.0,(0,0,building_top-2.5),verts=8)
    interior.append(chandelier_chain)
    for i,ang in enumerate([0,120,240]):
        rad=math.radians(ang)
        x=math.cos(rad)*0.6; y=math.sin(rad)*0.6
        cyl=create_cylinder(f"Chandelier_Arm_{i}",0.08,0.6,(x,y,building_top-3.2),verts=8)
        interior.append(cyl)
        bulb=create_uv_sphere(f"Chandelier_Bulb_{i}",0.18,(x,y,building_top-3.6),seg=8,rings=4)
        interior.append(bulb)
    for wall, positions in [(front_wall,[(-9,6.5),(9,6.5)]),(back_wall,[(-9,6.5),(9,6.5)]),(left_wall,[(-5,6.5),(5,6.5)]),(right_wall,[(-5,6.5),(5,6.5)])]:
        is_x = wall in [front_wall,back_wall]
        for (pos,h) in positions:
            if is_x:
                cx=pos; cy= -BUILD_D/2+wall_thick/2 if wall==front_wall else BUILD_D/2-wall_thick/2
                cutter=create_arch_cutter(f"JaliCut_{wall.name}_{pos}",3.2,2.8,1.6,wall_thick+2,cx,cy,floor_z+2.5,orient="x",seg=12)
                apply_boolean_cut(wall, cutter)
                lattice=create_arch_cutter(f"JaliLattice_{wall.name}_{pos}",3.0,2.6,1.5,0.08,cx,cy,floor_z+2.5,orient="x",seg=12)
                lattice.name=f"Jali_{wall.name}_{pos}"
                interior.append(lattice)
            else:
                cy=pos; cx= -BUILD_W/2+wall_thick/2 if wall==left_wall else BUILD_W/2-wall_thick/2
                cutter=create_arch_cutter(f"JaliCut_{wall.name}_{pos}",3.2,2.8,1.6,wall_thick+2,cx,cy,floor_z+2.5,orient="y",seg=12)
                apply_boolean_cut(wall, cutter)
                lattice=create_arch_cutter(f"JaliLattice_{wall.name}_{pos}",3.0,2.6,1.5,0.08,cx,cy,floor_z+2.5,orient="y",seg=12)
                lattice.name=f"Jali_{wall.name}_{pos}"
                interior.append(lattice)
    throne_base=create_box("Throne_Base",(2.2,2.0,0.6),(0,BUILD_D/2-2.5,floor_z+0.3))
    throne_back=create_box("Throne_Back",(2.2,0.3,1.8),(0,BUILD_D/2-1.6,floor_z+1.2))
    throne_cushion=create_box("Throne_Cushion",(1.8,1.4,0.25),(0,BUILD_D/2-2.5,floor_z+0.75))
    interior.extend([throne_base,throne_back,throne_cushion])
    for side_x in [-8,8]:
        sofa_base=create_box(f"Sofa_Base_{side_x}",(3.5,1.4,0.5),(side_x,0,floor_z+0.25))
        sofa_back=create_box(f"Sofa_Back_{side_x}",(3.5,0.25,0.8),(side_x,0.6,floor_z+0.65))
        interior.extend([sofa_base,sofa_back])
    for (px,py) in [(-BUILD_W/2+2,-BUILD_D/2+2),(BUILD_W/2-2,-BUILD_D/2+2),(-BUILD_W/2+2,BUILD_D/2-2),(BUILD_W/2-2,BUILD_D/2-2)]:
        pot=create_cylinder(f"Pot_{px}_{py}",0.35,0.5,(px,py,floor_z+0.25),verts=12)
        plant_trunk=create_cylinder(f"Plant_Trunk_{px}_{py}",0.08,1.0,(px,py,floor_z+1.0),verts=6)
        plant_top=create_uv_sphere(f"Plant_Top_{px}_{py}",0.45,(px,py,floor_z+1.6),seg=8,rings=4)
        interior.extend([pot,plant_trunk,plant_top])
    fountain_base=create_cylinder("Fountain_Base_Ext",2.2,0.4,(0,-BASE_D/2-1.5,BASE_H+0.2),verts=16)
    fountain_mid=create_cylinder("Fountain_Mid",1.2,0.6,(0,-BASE_D/2-1.5,BASE_H+0.6),verts=16)
    fountain_top=create_cylinder("Fountain_Top",0.4,0.7,(0,-BASE_D/2-1.5,BASE_H+1.2),verts=12)
    fountain_water=create_cylinder("Fountain_Water",1.9,0.1,(0,-BASE_D/2-1.5,BASE_H+0.4),verts=16)
    exterior.extend([fountain_base,fountain_mid,fountain_top,fountain_water])
    palm_positions=[(-12,-BASE_D/2-1.5),(12,-BASE_D/2-1.5),(-8,-BASE_D/2-2),(8,-BASE_D/2-2)]
    for idx,(px,py) in enumerate(palm_positions):
        trunk=create_cylinder(f"Palm_Trunk_{idx}",0.25,4.0,(px,py,BASE_H+2.0),verts=8)
        exterior.append(trunk)
        for a in range(5):
            ang=a*72; rad=math.radians(ang)
            lx=px+math.cos(rad)*0.4; ly=py+math.sin(rad)*0.4
            leaf=create_cone(f"Palm_Leaf_{idx}_{a}",0.38,0.0,0.85,(lx,ly,BASE_H+4.7))
            exterior.append(leaf)
        top=create_uv_sphere(f"Palm_Top_{idx}",0.45,(px,py,BASE_H+4.2),seg=8,rings=4)
        exterior.append(top)
    # Materials
    wall_proc=make_procedural_wall_mat("Rajasthani_Wall_Proc",scale=0.2)
    floor_proc=make_checker_floor_mat("Darbar_Floor_Checker",scale=0.2)
    teal_img=make_image_mat("Dome_Teal_Img","palace_dome_teal_2k.png",rough=0.35,metal=0.15,scale=1.0)
    yellow_img=make_image_mat("Dome_Yellow_Img","palace_dome_yellow_2k.png",rough=0.35,metal=0.2,scale=1.0)
    blue_img=make_image_mat("Door_Blue_Img","palace_door_blue_2k.png",rough=0.6,metal=0.0,scale=0.8)
    gold_solid=make_solid("Gold_Trim",(0.85,0.65,0.13,1),rough=0.25,metal=0.85)
    pink_solid=make_solid("Parapet_Pink",(0.96,0.42,0.55,1),rough=0.8)
    yellow_solid=make_solid("Parapet_Yellow",(0.98,0.85,0.18,1),rough=0.8)
    teal_solid=make_solid("Teal_Jharokha",(0.15,0.65,0.70,1),rough=0.4,metal=0.1)
    red_band=make_solid("Band_Red",(0.95,0.22,0.25,1),rough=0.6)
    blue_band=make_solid("Band_Blue",(0.22,0.38,0.85,1),rough=0.6)
    yellow_band=make_solid("Band_Yellow",(0.98,0.85,0.18,1),rough=0.6)
    jali_mat=make_procedural_wall_mat("Jali_Lattice",scale=0.3)
    throne_gold=make_solid("Throne_Gold",(0.90,0.75,0.20,1),rough=0.2,metal=0.9)
    cushion_red=make_solid("Cushion_Red",(0.85,0.15,0.25,1),rough=0.7)
    sofa_mat=make_solid("Sofa_Royal",(0.65,0.15,0.55,1),rough=0.75)
    pot_mat=make_solid("Pot_Terracotta",(0.70,0.30,0.15,1),rough=0.9)
    plant_mat=make_solid("Plant_Green",(0.20,0.60,0.25,1),rough=0.8)
    water_mat=make_solid("Fountain_Water",(0.30,0.65,0.90,1),rough=0.2)
    flag_red=make_solid("Flag_Red",(0.95,0.25,0.25,1))
    flag_orange=make_solid("Flag_Orange",(0.97,0.55,0.15,1))
    flag_yellow=make_solid("Flag_Yellow",(0.98,0.88,0.18,1))
    all_objs=[]
    for o in walls:
        cube_project_unwrap(o,scale=0.2)
        o.data.materials.clear()
        if "Floor_Base" in o.name: o.data.materials.append(floor_proc)
        else: o.data.materials.append(wall_proc)
        all_objs.append(o)
    for o in doors_blue:
        cube_project_unwrap(o,scale=0.2)
        o.data.materials.clear(); o.data.materials.append(blue_img)
        all_objs.append(o)
    for o in golds:
        cube_project_unwrap(o,scale=0.2)
        o.data.materials.clear(); o.data.materials.append(gold_solid)
        all_objs.append(o)
    for o in dome_objs:
        cube_project_unwrap(o,scale=0.2)
        o.data.materials.clear()
        if "Central" in o.name: o.data.materials.append(teal_img)
        elif "Corner" in o.name: o.data.materials.append(yellow_img)
        elif "Chhatri" in o.name: o.data.materials.append(teal_img)
        else: o.data.materials.append(teal_img)
        all_objs.append(o)
    for o in jharokha_domes:
        cube_project_unwrap(o,scale=0.2)
        o.data.materials.clear(); o.data.materials.append(teal_solid)
        if o not in all_objs: all_objs.append(o)
    for block,col in parapet_objs:
        cube_project_unwrap(block,scale=0.2)
        block.data.materials.clear()
        block.data.materials.append(pink_solid if col=="pink" else yellow_solid)
        all_objs.append(block)
    for o in exterior:
        cube_project_unwrap(o,scale=0.2)
        o.data.materials.clear()
        if "Water" in o.name: o.data.materials.append(water_mat)
        elif "Trunk" in o.name: o.data.materials.append(make_solid("Palm_Trunk",(0.45,0.30,0.18,1),rough=0.9))
        elif "Leaf" in o.name or "Top" in o.name: o.data.materials.append(plant_mat)
        else: o.data.materials.append(wall_proc)
        all_objs.append(o)
    for o in flag_objs:
        cube_project_unwrap(o,scale=0.2)
        o.data.materials.clear()
        if "Flag" in o.name and "Pole" not in o.name:
            h=hash(o.name)%3
            if h==0: o.data.materials.append(flag_red)
            elif h==1: o.data.materials.append(flag_orange)
            else: o.data.materials.append(flag_yellow)
        else: o.data.materials.append(gold_solid)
        all_objs.append(o)
    for pole,flag in corner_flags:
        cube_project_unwrap(pole,scale=0.2); pole.data.materials.clear(); pole.data.materials.append(gold_solid); all_objs.append(pole)
        cube_project_unwrap(flag,scale=0.2); flag.data.materials.clear()
        h=hash(flag.name)%3
        if h==0: flag.data.materials.append(flag_red)
        elif h==1: flag.data.materials.append(flag_orange)
        else: flag.data.materials.append(flag_yellow)
        all_objs.append(flag)
    for o in interior:
        cube_project_unwrap(o,scale=0.2)
        o.data.materials.clear()
        if "PillarBand" in o.name:
            if "_0" in o.name: o.data.materials.append(red_band)
            elif "_1" in o.name: o.data.materials.append(blue_band)
            else: o.data.materials.append(yellow_band)
        elif "Interior_Pillar" in o.name: o.data.materials.append(wall_proc)
        elif "Ceiling" in o.name: o.data.materials.append(make_procedural_wall_mat("Ceiling_Vibrant",scale=0.3))
        elif "Chandelier" in o.name: o.data.materials.append(gold_solid)
        elif "Jali" in o.name: o.data.materials.append(jali_mat)
        elif "Throne" in o.name:
            if "Cushion" in o.name: o.data.materials.append(cushion_red)
            else: o.data.materials.append(throne_gold)
        elif "Sofa" in o.name: o.data.materials.append(sofa_mat)
        elif "Pot" in o.name: o.data.materials.append(pot_mat)
        elif "Plant" in o.name: o.data.materials.append(plant_mat)
        elif "Interior_Stair" in o.name: o.data.materials.append(wall_proc)
        else: o.data.materials.append(wall_proc)
        all_objs.append(o)
    for o in pillar_objs:
        cube_project_unwrap(o,scale=0.2)
        o.data.materials.clear(); o.data.materials.append(wall_proc)
        all_objs.append(o)
    joined=join_objects(all_objs,"MahalPalaceMaster")
    set_origin_bottom_center(joined)
    add_omni_light("Master_Light_Center",(0,0,8),energy=400,color=(1,0.95,0.85))
    add_omni_light("Master_Light_Front",(0,-12,6),energy=250,color=(1,0.9,0.7))
    add_omni_light("Interior_Light",(0,0,5),energy=300,color=(1,1,0.9))
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
    clear_scene()
    set_metric_units()
    obj=build_master()
    x0,x1,y0,y1,z0,z1=object_bbox(obj)
    print(f"  MahalMaster: {x1-x0:.1f}x{y1-y0:.1f}x{z1-z0:.1f} | {len(obj.data.polygons)} faces | origin bottom-center (0,0,0)")
    path=os.path.join(OUTPUT_DIR,"mahal_palace_master.glb")
    export_glb(path)
    verify_glb(path)
    print("Done — Rajasthani Mahal Master generated.")
    return 0

if __name__=="__main__":
    sys.exit(main())
