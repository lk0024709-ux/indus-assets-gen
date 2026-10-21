# Elite Cargo Plane — Battle Royale Drop Ship

| Field | Value |
|---|---|
| Asset | `plane_cargo_elite.glb` |
| Scale | 35.0 m long × 45.0 m wingspan × 10.18 m high |
| Origin | Bottom-centre `(0, 0, 0)`; the lowered rear-ramp lip is the ground contact |
| Geometry | One flat-shaded mesh; 3,130 triangles; 11 material slots |
| Materials | Solid-color PBR only — no image textures |
| Generator | `tools/generate_plane_cargo_elite.py` |

## Design contents

- Faceted blended-wing gunmetal fuselage (`#2C2E33`) with raised dark panel seams, hatches, six-slot side vent banks and three avionics blade antennas.
- Deep blue glossy slanted canopy (metallic `0.8`, roughness `0.1`), cyan sensor pods and a dorsal running light.
- Swept wings, upturned/canted winglets, two streamlined under-wing drop tanks and canted twin tail fins.
- Four eight-sided engine nacelles. Each has an intake ring, mechanical casing ridges, black chrome nozzle, orange emissive ion halo and cyan emissive exhaust core.
- Rear cargo portal made by an EXACT Boolean subtraction, with a lowered ramp, floor, guide rails and red/green bay indicators.

After GitHub Pages deploys `main`, the direct asset URL is:

`https://lk0024709-ux.github.io/indus-assets-gen/models/vehicles/plane_cargo_elite.glb`
