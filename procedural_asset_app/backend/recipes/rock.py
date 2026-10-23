import random
from .base import finish, smooth_mesh
import bpy
from mathutils import Vector

NAME = "Rock"
DESCRIPTION = "A seeded, irregular low-poly boulder with controllable surface variation."
PARAMETERS = {
    "seed": {"label":"Random seed","type":"int","min":0,"max":999999,"step":1,"default":42},
    "size": {"label":"Overall size","type":"float","min":0.5,"max":2.5,"step":0.1,"default":1.3},
    "noise": {"label":"Shape irregularity","type":"float","min":0.0,"max":0.65,"step":0.05,"default":0.28},
    "subdivision": {"label":"Detail level","type":"int","min":1,"max":3,"step":1,"default":2},
    "smoothness": {"label":"Smoothing","type":"float","min":0.0,"max":1.0,"step":0.1,"default":0.2},
    "color": {"label":"Material color","type":"color","default":"#777B78"}
}
def build(p):
    random.seed(p["seed"])
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=p["subdivision"], radius=p["size"], location=(0,0,p["size"]*0.72))
    obj=bpy.context.object
    obj.name="Rock"
    for v in obj.data.vertices:
        factor=1+random.uniform(-p["noise"],p["noise"])
        v.co.x*=factor
        v.co.y*=factor
        v.co.z*=factor*0.72
    obj.data.update()
    if p["smoothness"] > 0.05:
        smooth_mesh(obj,p["smoothness"]*0.45)
        bpy.ops.object.modifier_apply(modifier="Surface smoothing")
    return finish([obj],p["color"])
