from .base import cube, cylinder, sphere, finish

NAME = "Lamp"
DESCRIPTION = "A stylized table lamp with a configurable shade silhouette."
PARAMETERS = {
    "base_radius": {"label":"Base radius","type":"float","min":0.12,"max":0.55,"step":0.02,"default":0.3},
    "pole_height": {"label":"Pole height","type":"float","min":0.3,"max":1.5,"step":0.05,"default":0.8},
    "shade_size": {"label":"Shade size","type":"float","min":0.25,"max":0.9,"step":0.05,"default":0.55},
    "shade_type": {"label":"Shade type","type":"enum","options":["cone","cylinder","sphere"],"default":"cone"},
    "segments": {"label":"Radial detail","type":"int","min":8,"max":32,"step":4,"default":16},
    "color": {"label":"Material color","type":"color","default":"#E6B85C"}
}
def build(p):
    r, ph, sh = p["base_radius"],p["pole_height"],p["shade_size"]
    parts=[cylinder("Base",(0,0,0.08),r,0.16, max(12,p["segments"]))]
    parts.append(cylinder("Stem",(0,0,0.16+ph/2),r*0.13,ph,12))
    z=0.16+ph+sh*0.48
    if p["shade_type"] == "cone":
        parts.append(cylinder("Shade",(0,0,z),sh*0.5,sh,p["segments"],sh*0.9))
    elif p["shade_type"] == "cylinder":
        parts.append(cylinder("Shade",(0,0,z),sh*0.6,sh,p["segments"]))
    else:
        parts.append(sphere("Shade",(0,0,z),(sh*0.58,sh*0.58,sh*0.52),p["segments"],max(6,p["segments"]//2)))
    return finish(parts,p["color"])
