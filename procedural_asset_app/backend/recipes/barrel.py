import math
from .base import finish
import bpy
import bmesh

NAME = "Barrel"
DESCRIPTION = "A faceted wooden barrel with adjustable bulge, stave count and hoops."
PARAMETERS = {
    "radius": {"label":"Radius","type":"float","min":0.25,"max":0.9,"step":0.05,"default":0.48},
    "height": {"label":"Height","type":"float","min":0.5,"max":2.0,"step":0.1,"default":1.15},
    "bulge": {"label":"Bulge","type":"float","min":0.0,"max":0.35,"step":0.05,"default":0.15},
    "staves": {"label":"Stave count","type":"int","min":8,"max":24,"step":2,"default":12},
    "hoops": {"label":"Metal hoops","type":"int","min":0,"max":4,"step":1,"default":2},
    "color": {"label":"Material color","type":"color","default":"#96613D"}
}
def build(p):
    n=p["staves"]; radius=p["radius"]; height=p["height"]; bulge=p["bulge"]
    rings=7
    bm=bmesh.new()
    verts=[]
    for j in range(rings):
        z=height*j/(rings-1)
        profile=radius*(1+bulge*math.sin(math.pi*j/(rings-1)))
        for i in range(n):
            a=2*math.pi*i/n
            verts.append(bm.verts.new((profile*math.cos(a),profile*math.sin(a),z)))
    bm.verts.ensure_lookup_table()
    for j in range(rings-1):
        for i in range(n):
            a=j*n+i; b=j*n+(i+1)%n; c=(j+1)*n+(i+1)%n; d=(j+1)*n+i
            try: bm.faces.new((verts[a],verts[b],verts[c],verts[d]))
            except ValueError: pass
    bm.faces.new(tuple(verts[i] for i in range(n-1,-1,-1)))
    bm.faces.new(tuple(verts[(rings-1)*n+i] for i in range(n)))
    mesh=bpy.data.meshes.new("BarrelMesh"); bm.to_mesh(mesh); bm.free()
    obj=bpy.data.objects.new("BarrelBody",mesh); bpy.context.collection.objects.link(obj)
    parts=[obj]
    for i in range(p["hoops"]):
        z=height*(i+1)/(p["hoops"]+1)
        rr=radius*(1+bulge*math.sin(math.pi*z/height))*1.025
        bpy.ops.mesh.primitive_torus_add(major_radius=rr,minor_radius=radius*0.045,major_segments=n,minor_segments=6,location=(0,0,z))
        parts.append(bpy.context.object)
    return finish(parts,p["color"])
