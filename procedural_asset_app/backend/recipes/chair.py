from .base import cube, cylinder, finish

NAME = "Chair"
DESCRIPTION = "A low-poly chair with adjustable proportions and a solid seat."
PARAMETERS = {
    "seat_width": {"label":"Seat width","type":"float","min":0.7,"max":1.8,"step":0.05,"default":1.0},
    "seat_depth": {"label":"Seat depth","type":"float","min":0.65,"max":1.6,"step":0.05,"default":0.9},
    "seat_height": {"label":"Seat height","type":"float","min":0.35,"max":1.0,"step":0.05,"default":0.55},
    "back_height": {"label":"Back height","type":"float","min":0.5,"max":1.8,"step":0.05,"default":1.1},
    "leg_count": {"label":"Leg count","type":"enum","options":["3","4"],"default":"4"},
    "color": {"label":"Material color","type":"color","default":"#B87843"}
}
def build(p):
    w, d, h = p["seat_width"], p["seat_depth"], p["seat_height"]
    parts = [cube("Seat", (0,0,h), (w,d,0.12), 0.035)]
    count = int(p["leg_count"])
    for x in (-w*0.42, w*0.42):
        for y in (-d*0.42, d*0.42):
            if count == 3 and x < 0 and y > 0:
                continue
            parts.append(cube("Leg", (x,y,h/2), (0.09,0.09,h), 0.012))
    bh = p["back_height"]
    parts.append(cube("Backrest", (0,d*0.43,h+bh/2), (w*0.88,0.09,bh), 0.025))
    for x in (-w*0.38, w*0.38):
        parts.append(cube("Back post", (x,d*0.42,h+bh*0.42), (0.07,0.08,bh*0.85), 0.01))
    return finish(parts, p["color"])
