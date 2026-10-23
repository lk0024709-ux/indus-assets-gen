from .base import cube, cylinder, finish

NAME = "Table"
DESCRIPTION = "A configurable dining or work table with round or rectangular top."
PARAMETERS = {
    "width": {"label":"Width","type":"float","min":0.8,"max":3.0,"step":0.1,"default":1.8},
    "depth": {"label":"Depth / diameter","type":"float","min":0.7,"max":2.5,"step":0.1,"default":1.2},
    "height": {"label":"Height","type":"float","min":0.5,"max":1.5,"step":0.05,"default":0.85},
    "top_shape": {"label":"Top shape","type":"enum","options":["rectangular","round"],"default":"rectangular"},
    "leg_style": {"label":"Leg style","type":"enum","options":["straight","tapered"],"default":"straight"},
    "color": {"label":"Material color","type":"color","default":"#8A5A3B"}
}
def build(p):
    w,d,h = p["width"],p["depth"],p["height"]
    if p["top_shape"] == "round":
        top = cylinder("Round tabletop",(0,0,h),min(w,d)/2,0.12,32)
    else:
        top = cube("Tabletop",(0,0,h),(w,d,0.12),0.035)
    parts=[top]
    for x in (-w*0.42,w*0.42):
        for y in (-d*0.42,d*0.42):
            if p["leg_style"] == "tapered":
                parts.append(cylinder("Tapered leg",(x,y,h/2),0.065,h,12,0.095))
            else:
                parts.append(cube("Table leg",(x,y,h/2),(0.1,0.1,h),0.012))
    return finish(parts,p["color"])
