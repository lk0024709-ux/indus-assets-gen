# Elite Cargo Dropship — Battle Royale Drop Sequence

| Field | Value |
|---|---|
| Asset | `plane_cargo_elite.glb` |
| Scale | **45.00 m wingspan × 35.00 m length × 10.33 m high** |
| Origin | Bottom-centre `(0, 0, 0)`; `min Z = 0.000` and the lowered ramp lip is the ground contact |
| Geometry | One flat-shaded mesh; **22,358 triangles**, 13,729 vertices, 12 material slots |
| Materials | Solid-color PBR/emissive only — **zero image textures** |
| Generator | `tools/generate_plane_cargo_elite.py` |

## Design contents

- A 12-station, chined blended-wing-body loft in matte gunmetal **#2C2E33**, rather than a round tube.
- More than 200 targeted greebles: curved panel-line ribbons, lighter access plates, vent slats, dorsal spine rails, RCS pods, dispensers, sensor blisters, tie-down rings, service hatches, boarding steps and grab handles.
- A six-station slanted deep-blue canopy (metallic `0.8`, roughness `0.1`) with frames, sensor pods, pitot probes, a chin EO/FLIR turret and cyan recognition strips.
- Swept seven-section wings with canted winglets, leading-edge accents, panel lines, flap fairings, vortex generators and two finned under-wing drop tanks.
- Four octagonal nacelles with recessed intake ducts, spinner cones, ten fan blades, guide vanes, armour bands, heat-exchanger fins, vectoring nozzle petals and cyan/ember/white emissive thrust cores.
- Canted twin tail fins, dorsal fairing and navigation/formation lights.
- A wide rear cargo portal made by an EXACT Boolean Difference. The generator ray-casts through the opening and fails if the wall is not open. The bay has ribs, floor/ceiling strips, tie-downs and strapped crates; its lowered ramp has treads, rails, cyan edges, hydraulics and red/green indicator lights.

After GitHub Pages deploys `main`, use the direct asset URL:

`https://lk0024709-ux.github.io/indus-assets-gen/models/vehicles/plane_cargo_elite.glb`
