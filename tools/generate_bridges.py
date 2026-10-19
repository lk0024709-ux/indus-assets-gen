#!/usr/bin/env python3
"""Phase 2 — Bridges generator.

Assets:
  bridge_wood.glb     — 20m long, 4m wide wooden walkway with railings & pillars (wood_plank_1k.png)
  bridge_concrete.glb — 40m long, 8m wide concrete bridge with high barriers & thick pillars (concrete_wall_1k.png)

Usage:
  pip install bpy pillow numpy
  python tools/generate_bridges.py
"""

from __future__ import annotations

import json
import math
import os
import shutil
import struct
import sys

import bpy
from mathutils import Matrix, Vector

REPO_ROOT=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEXTURE_DIR=os.path.join(REPO_ROOT,"docs","textures")
BRIDGES_DIR=os.path.join(REPO_ROOT,"docs","models","bridges")

MAP_SCALE=0.3

MATERIALS={
    "wood": {"file":"wood_plank_1k.png","fallback":"wood_plank.png","roughness":0.72,"metallic":0.0,"tile":2.0},
    "concrete": {"file":"concrete_wall_1k.png","fallback":"concrete_wall.png","roughness":0.88,"metallic":0.0,"tile":2.5},
}

_MATERIAL_CACHE={}

def ensure_textures():
    os.makedirs(TEXTURE_DIR, exist_ok=True)
    for src,dst in [("wood_plank.png","wood_plank_1k.png"),("concrete_wall.png","concrete_wall_1k.png")]:
        d=os.path.join(TEXTURE_DIR,dst)
        if not os.path.isfile(d):
            s=os.path.join(TEXTURE_DIR,src)
            if os.path.isfile(s):
                shutil.copy(s,d)
                print(f"  copied {src} -> {dst}")

def clear_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _MATERIAL_CACHE.clear()

def set_metric_units():
    s=bpy.context.scene
    s.unit_settings.system="METRIC"
    s.unit_settings.scale_length=1.0

def create_box(name, size, location=(0,0,0), rotation=(0,0,0)):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    o=bpy.context.active_object
    o.name=name; o.data.name=name+"Mesh"
    o.dimensions=tuple(size)
    o.rotation_euler=rotation
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
    return o

def smart_unwrap(obj, target_density=None):
    if not obj.data.uv_layers:
        obj.data.uv_layers.new(name="UVMap")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active=obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    try: bpy.ops.mesh.normals_make_consistent(inside=False)
    except RuntimeError: pass
    try: bpy.ops.uv.smart_project(angle_limit=math.radians(66.0), island_margin=0.02)
    except TypeError: bpy.ops.uv.smart_project()
    bpy.ops.object.mode_set(mode="OBJECT")
    uvl=obj.data.uv_layers.active; me=obj.data
    def _cov(a,b):
        n=len(a)
        if n<2: return 0.0
        ma=sum(a)/n; mb=sum(b)/n
        return sum((a[i]-ma)*(b[i]-mb) for i in range(n))/n
    for poly in me.polygons:
        if abs(poly.normal.z)>=0.55: continue
        idxs=list(poly.loop_indices)
        us=[uvl.data[i].uv.x for i in idxs]
        vs=[uvl.data[i].uv.y for i in idxs]
        zs=[me.vertices[me.loops[i].vertex_index].co.z for i in idxs]
        if abs(_cov(us,zs)) > abs(_cov(vs,zs)):
            cx=sum(us)/len(us); cy=sum(vs)/len(vs)
            for i,u,v in zip(idxs, us, vs):
                x,y=u-cx,v-cy
                uvl.data[i].uv=(cx - y, cy + x)
    if target_density:
        area3d=sum(p.area for p in me.polygons)
        area_uv=0.0
        for p in me.polygons:
            pts=[uvl.data[i].uv for i in p.loop_indices]
            if len(pts)<3: continue
            s=0.0
            for a in range(len(pts)):
                b=(a+1)%len(pts)
                s+=pts[a].x*pts[b].y - pts[b].x*pts[a].y
            area_uv+=abs(s)/2.0
        if area3d>1e-9 and area_uv>1e-9:
            cur=math.sqrt(area_uv/area3d)
            k=target_density/cur
            for layer in obj.data.uv_layers:
                for uv in layer.data:
                    uv.uv=uv.uv*k

def density_for(preset):
    tile=MATERIALS[preset]["tile"]
    if not tile: return None
    return 1.0/(MAP_SCALE*tile)

def make_material(name, preset):
    key=f"{name}:{preset}"
    if key in _MATERIAL_CACHE: return _MATERIAL_CACHE[key]
    spec=MATERIALS[preset]
    mat=bpy.data.materials.new(name)
    if bpy.app.version < (5,0,0):
        mat.use_nodes=True
    nt=mat.node_tree
    bsdf=nt.nodes.get("Principled BSDF")
    tex_path=os.path.join(TEXTURE_DIR,spec["file"])
    if not os.path.isfile(tex_path):
        fb=spec.get("fallback")
        if fb: tex_path=os.path.join(TEXTURE_DIR,fb)
        if not os.path.isfile(tex_path):
            raise FileNotFoundError(tex_path)
    img=bpy.data.images.load(tex_path, check_existing=True)
    coord=nt.nodes.new("ShaderNodeTexCoord"); coord.location=(-760,220)
    mapping=nt.nodes.new("ShaderNodeMapping"); mapping.location=(-560,220)
    mapping.inputs["Scale"].default_value=(MAP_SCALE,MAP_SCALE,MAP_SCALE)
    tex=nt.nodes.new("ShaderNodeTexImage"); tex.location=(-350,220)
    tex.image=img; tex.extension="REPEAT"; tex.label=spec["file"]
    nt.links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value=spec["roughness"]
    bsdf.inputs["Metallic"].default_value=spec["metallic"]
    _MATERIAL_CACHE[key]=mat
    return mat

def assign_material(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)

def join_objects(objs, name):
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
    off=Vector((-(min_x+max_x)/2.0, -(min_y+max_y)/2.0, -min_z))
    obj.data.transform(Matrix.Translation(off))
    obj.data.validate(clean_customdata=True)
    obj.data.update()
    obj.matrix_world=Matrix.Identity(4)
    obj.location=(0,0,0); obj.rotation_euler=(0,0,0); obj.scale=(1,1,1)

def object_bbox(obj):
    coords=[obj.matrix_world @ v.co for v in obj.data.vertices]
    return (min(c.x for c in coords), max(c.x for c in coords), min(c.y for c in coords), max(c.y for c in coords), min(c.z for c in coords), max(c.z for c in coords))

def export_glb(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    kwargs=dict(filepath=path, export_format="GLB", export_image_format="JPEG", export_lights=False)
    try: bpy.ops.export_scene.gltf(export_image_quality=90, **kwargs)
    except TypeError: bpy.ops.export_scene.gltf(**kwargs)
    if not os.path.isfile(path): raise RuntimeError(f"Export failed {path}")
    return path

def verify_glb(path):
    with open(path,"rb") as fh:
        data=fh.read()
    if data[:4]!=b"glTF": raise RuntimeError(f"Not GLB {path}")
    json_len=struct.unpack("<I", data[12:16])[0]
    gltf=json.loads(data[20:20+json_len])
    images=gltf.get("images",[])
    tris=0
    for mesh in gltf.get("meshes",[]):
        for prim in mesh.get("primitives",[]):
            if "indices" in prim:
                count=gltf["accessors"][prim["indices"]]["count"]
            else:
                count=gltf["accessors"][prim["attributes"]["POSITION"]]["count"]
            tris+=count//3
    stats={"bytes":os.path.getsize(path),"materials":len(gltf.get("materials",[])),"images":len(images),"tris":tris}
    print(f"  verified {os.path.basename(path)}: {stats['bytes']} bytes, {stats['materials']} mat, {stats['images']} img, ~{stats['tris']} tris")
    return stats

def report(obj,label):
    x0,x1,y0,y1,z0,z1=object_bbox(obj)
    print(f"  {label}: {x1-x0:.2f}m x {y1-y0:.2f}m x {z1-z0:.2f}m | {len(obj.data.polygons)} faces")

# Builders

def build_bridge_wood():
    # 20m long (X), 4m wide (Y), deck thickness 0.3, height 3m
    deck_h=3.0
    deck_t=0.3
    width=4.0
    length=20.0
    parts=[]
    # deck
    deck=create_box("WoodDeck", (length, width, deck_t), (0,0, deck_h + deck_t/2))
    parts.append((deck,"wood"))
    # railings: posts and rails on both sides
    # posts: 5 per side at x = -8,-4,0,4,8 (5 posts)
    post_positions=[-8,-4,0,4,8]
    for x in post_positions:
        for side in (-1,1):
            y = side * (width/2 - 0.12)
            # post 0.12x0.12x1.0 tall, sitting on deck
            post=create_box(f"WoodPost_{x}_{side}", (0.12,0.12,1.0), (x, y, deck_h+deck_t+0.5))
            parts.append((post,"wood"))
    # top rail and mid rail per side
    for side in (-1,1):
        y = side * (width/2 - 0.12)
        # top rail at z= deck_h+deck_t+1.0
        top_rail=create_box(f"WoodTopRail_{side}", (length, 0.08, 0.08), (0, y, deck_h+deck_t+1.0))
        mid_rail=create_box(f"WoodMidRail_{side}", (length, 0.06, 0.06), (0, y, deck_h+deck_t+0.5))
        parts.append((top_rail,"wood"))
        parts.append((mid_rail,"wood"))
    # support pillars: at ends and middle, 2 per X position across width
    pillar_x=[-9, -4.5, 0, 4.5, 9]
    for x in pillar_x:
        for side in (-1,1):
            y = side * 1.0
            pillar=create_box(f"WoodPillar_{x}_{side}", (0.4,0.4,deck_h), (x, y, deck_h/2))
            parts.append((pillar,"wood"))
    # assign materials and unwrap
    mats={}
    for obj,kind in parts:
        if kind not in mats:
            mats[kind]=make_material(f"BridgeWood_{kind}", kind)
        smart_unwrap(obj, density_for(kind))
        assign_material(obj, mats[kind])
    joined=join_objects([o for o,_ in parts], "BridgeWood")
    set_origin_bottom_center(joined)
    return joined

def build_bridge_concrete():
    # 40m long, 8m wide, deck height maybe 5m, high side walls 1.2m tall
    deck_h=5.0
    deck_t=0.5
    width=8.0
    length=40.0
    wall_h=1.2
    wall_t=0.4
    parts=[]
    # deck
    deck=create_box("ConcDeck", (length, width, deck_t), (0,0, deck_h+deck_t/2))
    parts.append((deck,"concrete"))
    # side barriers (high walls)
    for side in (-1,1):
        y = side * (width/2 - wall_t/2)
        wall=create_box(f"ConcWall_{side}", (length, wall_t, wall_h), (0, y, deck_h+deck_t+wall_h/2))
        parts.append((wall,"concrete"))
    # pillars: thick 1.5x1.5x5m, at ends and quarter points
    pillar_x=[-18, -9, 0, 9, 18]
    for x in pillar_x:
        for side in (-1,1):
            y = side * 1.5
            pillar=create_box(f"ConcPillar_{x}_{side}", (1.2,1.2,deck_h), (x, y, deck_h/2))
            parts.append((pillar,"concrete"))
        # center pillar for extra support (at same X, y=0)
        center_pillar=create_box(f"ConcPillarC_{x}", (1.0,1.0,deck_h), (x, 0, deck_h/2))
        parts.append((center_pillar,"concrete"))
    mats={}
    for obj,kind in parts:
        if kind not in mats:
            mats[kind]=make_material(f"BridgeConc_{kind}", kind)
        smart_unwrap(obj, density_for(kind))
        assign_material(obj, mats[kind])
    joined=join_objects([o for o,_ in parts], "BridgeConcrete")
    set_origin_bottom_center(joined)
    return joined

def main():
    print(f"Blender {bpy.app.version_string} — Bridges Generator")
    ensure_textures()
    os.makedirs(BRIDGES_DIR, exist_ok=True)
    failures=[]
    def run(label, filename, builder):
        print(f"Building {label} ...")
        try:
            clear_scene(); set_metric_units()
            obj=builder()
            report(obj,label)
            path=os.path.join(BRIDGES_DIR, filename)
            export_glb(path)
            verify_glb(path)
        except Exception as e:
            failures.append((label,e))
            print(f"  FAILED {label}: {e!r}")
            import traceback; traceback.print_exc()
    run("bridge_wood","bridge_wood.glb", build_bridge_wood)
    run("bridge_concrete","bridge_concrete.glb", build_bridge_concrete)
    if failures:
        print(f"\n{len(failures)} failed:")
        for l,e in failures: print(f"  - {l}: {e!r}")
        return 1
    print("Done — Bridges generated.")
    return 0

if __name__=="__main__":
    sys.exit(main())
