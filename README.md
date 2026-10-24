# 🎨 Indus : Battle Royale — 3D Asset Generator

Production asset pipeline for **Indus : Battle Royale**. Every model in this repository is generated procedurally with
**Blender Python (`bpy`)**, exported as a packed `.glb`, and published to a web viewer on **GitHub Pages**.

## 🚀 Live 3D Web Viewer

👉 **[lk0024709-ux.github.io/indus-assets-gen](https://lk0024709-ux.github.io/indus-assets-gen/)**

The gallery is deliberately small — it ships **only the production asset sets**:

| # | Category | Assets | Source | Where |
|---|---|---|---|---|
| 0 | 🧑 **Characters** | 1 Player Tactical (1.80 m, solid colours, **0 textures**) | `tools/convert_character_obj.py` | `docs/models/characters/` |
| 1 | 🛩 **Vehicles** | 1 Elite Cargo Dropship (45 m span) | `tools/generate_plane_cargo_elite.py` | `docs/models/vehicles/` |
| 2 | 🏯 **The Grand Mahal** | 1 assembled palace (+ 4 room blocks used to build it) | `tools/generate_mahal_rooms.py` | `docs/models/mahal/` |
| 3 | 🧱 **Modular Buildings** | 11 coloured blocks with real interior rooms | `tools/generate_building_modules.py` + `tools/assemble_buildings.py` | `docs/models/buildings_modular/` |
| 4 | 🌍 **Terrain** | 5 tiles — Mount Abu hill station + ground, hill, plateau, valley | `tools/generate_mount_abu.py`, `tools/generate_terrain.py` | `docs/models/terrain/` |

> **Note on folder names:** the brief calls these sets `buildings_final/` and `terrain_modules/`. In this repository they
> are the long-standing canonical paths **`docs/models/buildings_modular/`** and **`docs/models/terrain/`** — the 11 modular
> buildings and the 4 terrain tiles. Those paths are what the generators write to, what the CI publishes and what the
> Godot docs link to, so they were kept intact rather than renamed.

The **Elite Cargo Dropship** (`docs/models/vehicles/plane_cargo_elite.glb`) opens every Battle Royale match, so it gets its
own **Vehicles** category at the top of the gallery: 45.0 m span × 35.0 m length, 22,358 tris, 12 solid materials and
zero textures — see the [Dropship section](#-vehicles--elite-cargo-dropship-docsmodelsvehicles) below.

## ⚙️ How the Pipeline Works

1. **Generation** — each `tools/generate_*.py` script drives `bpy` (Blender as a Python module) to build meshes at
   real-world metre scale with Boolean openings, exact trig for arches and stairs, and deterministic placement.
2. **Materials** — the dropship, Mahal and buildings use **solid Principled BSDF colours** (no image textures). Only the terrain
   tiles carry a 1K PBR map (`grass_1k.png`, `rock_stone_1k.png`), and both can be regenerated procedurally.
   Colours are converted **sRGB → linear** before they reach the shader, so a hex value in the code is the colour you see
   in the GLB.
3. **Export** — every asset is joined into **one flat-shaded mesh**, normalised to its real size, and given a
   **bottom-centre `(0, 0, 0)`** origin so it drops onto the ground plane in Godot/Unity/the browser.
4. **CI/CD** — `.github/workflows/deploy.yml` installs `bpy`, runs the five generator steps, drops the intermediate
   module kit from the published site and deploys `docs/` to GitHub Pages on every push to `main`.
5. **Viewer** — `docs/index.html` is a small, dependency-light Google `<model-viewer>` gallery built from a JS array of
   categories, with a category filter and a hero card for the palace.

## 📂 Project Structure

```
tools/
  convert_character_obj.py     # Male_Suit.obj -> solid-colour player_tactical.glb (imports the OBJ, recolours, joins, exports)
  generate_terrain.py          # 4 terrain tiles (1000 m ground, hill, plateau, valley)
  generate_mount_abu.py        # 150 m hill station: mesa + corniche road + Nakki Lake + collision
  generate_mahal_rooms.py      # 4 walk-in rooms + assemble_mahal() -> rajasthani_mahal_mega.glb
  generate_building_modules.py # 15 m modular kit (walls, partitions, slabs, roofs, stairs, furniture)
  assemble_buildings.py        # 11 building recipes -> one joined mesh each
  generate_plane_cargo_elite.py# Elite Cargo Dropship (Vehicles category)

docs/                          # GitHub Pages site (viewer + models)
  models/characters/           # player_tactical.glb (solid colours, zero textures)
  index.html                   # 4-category gallery
  models/mahal/                # Grand Mahal (mega assembly + rooms/)
  models/buildings_modular/    # the 11 modular buildings
  models/terrain/              # Mount Abu (+ collision proxy) and the 4 tiles
  models/vehicles/             # plane_cargo_elite.glb
  textures/                    # grass_1k.png + rock_stone_1k.png (terrain only)
```

## 🛩 Vehicles — Elite Cargo Dropship (`docs/models/vehicles/`)

`generate_plane_cargo_elite.py` builds the next-gen stealth cargo plane used for the drop sequence and exports one joined
mesh. **45.00 m wingspan × 35.00 m length × 10.33 m tall**, origin bottom-centre `(0, 0, 0)`, **22,358 tris**, 1.2 MB,
12 solid materials, no textures.

| Part | Construction |
|---|---|
| Fuselage | blended-wing-body loft from 12 chined stations — no round tube — with ring seams and longitudinal panel-line ribbons |
| Greebling | ~200 pieces: access panels, 12 vent banks with slats, dorsal spine rails, blade antennas, RCS pods, chaff dispensers, sensor blisters, tie-downs, service hatches |
| Cockpit | faceted tinted canopy (metallic 0.8 / roughness 0.1) with arch framing, nose sensor pods, pitot probes, chin FLIR turret |
| Wings | 7-section sweeps with canted winglets, leading-edge bands, flap fairings, vortex generators, 2 under-wing drop tanks |
| Engines | 4 octagonal nacelles: open intakes with 10-blade fans, guide vanes, armour bands, heat fins, vectoring petals, emissive cyan + ember-orange thrusters |
| Tail | canted twin fins with cyan trailing strips, tapered dorsal fairing, strobe, heat vents |
| Cargo bay | EXACT Boolean opening (ray-cast verified at build time) with ribbed interior, ceiling strips, crates, and a lowered ramp in an explicit ramp-local frame; red/green indicator lights around the opening |

The generator asserts its own output — dimensions, `minZ == 0`, ≤ 120k tris, ≥ 10 materials, **zero images in the GLB**,
and a clear ray through the cargo opening.

## 🧑 Characters — Player Tactical (`docs/models/characters/`)

`convert_character_obj.py` turns the raw Quaternius `Male_Suit.obj` into the playable character. The OBJ itself was the
bug: its `.mtl` points at an external tie texture and nothing else, so Godot resolved six of seven materials to nothing
and the mesh came in untextured with an arbitrary unit scale.

```
docs/models/Character/Male_Suit.obj     (1,044 verts · 1,165 faces · 7 OBJ groups, CC0)
        │  bpy: import -> recolour -> join -> normalise -> export
        ▼
docs/models/characters/player_tactical.glb  (2,060 tris · 8 solid materials · 0 textures · 65 KB)
```

| OBJ group | Body part | Solid colour |
|---|---|---|
| `Skin` | head, neck, hands | `#D2A679` skin tone |
| `Shirt` | torso + arms | `#2C3E50` dark tactical shirt |
| `Pants` | legs | `#1A1A1A` pants |
| `Hair` / `Eyes` / `Details` / `TieTexture` | hair, eyes, belt+glasses, tie | `#241A18` / `#F2F0EA` / `#5A616B` / `#16202B` |
| `Eyes` below 15 % height | shoe soles | `#101112` (the soles hide in the `Eyes` group) |

* **Import:** `bpy.ops.import_scene.obj(...)` on Blender 2.8–3.6; Blender 4.x removed that operator, so the tool
  falls back to `bpy.ops.wm.obj_import(...)` and prints which one it used.
* **Materials:** every slot is rebuilt as a **solid Principled BSDF** (`metallic`/`roughness` per part, `Alpha=1`,
  no emission) and the imported MTL materials are deleted so Godot shows clean names. Colours go through
  **sRGB → linear** before they hit the shader, so the hex in the code is the hex in the GLB.
* **Join:** the OBJ imports as a single object; the tool joins anyway so a multi-part source still exports one mesh.
* **Shading:** the OBJ bakes 1,105 split normals that fight any shading choice, so they are dropped. **Smooth by
  angle (40°) ships** — flat shading exposed the torso triangulation, smooth-by-angle keeps the arms and legs round
  and the belt/boot edges crisp (and halves the file: 65 KB vs 157 KB).
* **Export:** 1.80 m tall, origin at the feet `(0, 0, 0)`, Y-up, no UVs, no images. The tool re-parses the GLB and
  asserts the height, the zero origin, the exact `baseColorFactor` per material and that `images` is empty.

## ⛰ Mount Abu — `docs/models/terrain/terrain_mount_abu.glb`

A Battle Royale hill station on a 150 × 150 m tile, generated from maths only (`generate_mount_abu.py`).
It ships as **two files**: the visual `terrain_mount_abu.glb` and a concordant concave collider
`terrain_mount_abu_collision.glb`.

| Constraint | Implementation | Measured |
|---|---|---|
| Footprint | 151 × 151 vertex grid, 1 m cells, 150 quads | **150.000 × 150.000 m** |
| Flat top | `Z = 25` for `r ≤ 30 m`, forced after displacement | **0.000 m deviation** |
| Cliff | C1 three-segment drop, `30 → 70 m` band (25 → 0 m) | **77.5°** steep core, mean 62° |
| Flat border | `|x|, |y| ≥ 70 m` is exactly `Z = 0` | **0.000 m deviation** |
| Road grade | 570° Bezier corniche, height taken from the profile | **13.5° max** (limit 15°) |
| Road length | ghat spiral + apron approach + plateau run-in | **508 m** |
| Lane | 8 m asphalt ribbon + dashed centre line | 8.0 m |
| Barriers | concrete blocks on the outer edge wherever it drops ≥ 2 m | 78 blocks |
| Lake | 128-gon Boolean cutout, `r = 15 m`, 2 m deep | floor `Z = 23`, water `Z = 24` |
| Vegetation | 15 trees + 6 boulders on the plateau rim | centre `Ø 30 m` left clear |
| Collision | decimated terrain + road, vegetation excluded | 5.9k tris, separate GLB |

### The maths

The radial profile is a sum of smoothsteps, which is `C¹` at every knot — that is why the plateau
and the apron are *exactly* flat rather than merely level-ish:

```
r 30 → 40 m : 0.16 of the drop   (shoulder, eases in)
r 40 → 46 m : 0.72 of the drop   (core: dz/dr = 1.5·18/6 = 4.5 → 77.5°)
r 46 → 70 m : 0.12 of the drop   (talus, eases out to the tile seam)
z(r) = 25 · (1 − Σ drop(r))
```

Displacement (3-octave value noise, radial ribs, rock strata) is weighted by the **local
`|dz/dr|`** of that profile, so noise mathematically cannot touch the flat top or the apron.
The road is a spiral in polar coordinates; its height is read off the same profile, which gives
`dz/ds ≈ (dz/dr)·(dr/ds) ≈ 4.5 × 0.06 ≈ 13°` — steep enough to be a real climb, shallow enough for
vehicles. The bench is carved into the height field (flat shelf + adaptive cut batter), the ribbon
is projected onto it, and each cross-section is forced dead level so the road never rolls.

**Verified:** 20,481 tris, 11 materials, 2 packed 1K textures, 2.1 MB (+ 0.53 MB collider).
The generator asserts footprint, plateau/border flatness, cliff angle, road length, road grade,
lake depth and water height, and fails the build if any of them regress.

## 🏯 The Grand Mahal — `docs/models/mahal/`

`generate_mahal_rooms.py` builds four walk-in rooms from solid materials, each with its origin at bottom-centre
`(0, 0, 0)` and its floor at `z = 0`, then welds them into one palace with `assemble_mahal()`.

| Piece | File | Size | Highlights |
|---|---|---|---|
| **Mega assembly** | `rajasthani_mahal_mega.glb` | 54 × 40.5 × 23.8 m | The full palace, one joined mesh, 62,542 tris |
| Darbar Hall | `rooms/room_darbar_hall.glb` | 20 × 15 × 6.07 m | 54 teal/cream checker tiles, 1 m dais, golden throne + canopy, 8 banded pillars, jali lattices |
| Courtyard Aangan | `rooms/room_courtyard.glb` | 20 × 20 m (open sky) | Marble fountain at the exact centre, 24 columns, 16 Boolean arches, 4 teal chhatris |
| Ranivas | `rooms/room_ranivas.glb` | 15 × 10 × 6 m | Two rooms + corridor, 90 protruding coloured cubes, 2 balconies with gold railings |
| Gateway | `rooms/room_gateway.glb` | 15 × 5 m | 5-lobed scalloped Mehrab, pink + gold frame, double doors swung open, flanking chhatris |

### Assembly layout (`assemble_mahal()`)

| Piece | Position (x, y, z) | Notes |
|---|---|---|
| `room_courtyard` | **0, 0, 0** | anchor of the palace |
| `room_darbar_hall` | **0, 17.5, 0** | north |
| `room_ranivas` | **17.5, 0, 0** and **−17.5, 0, 0** | east / west (west rotated 180° so the balconies face out) |
| `room_gateway` | **0, −12.5, 0** | south |
| Second floor | z = 6.4 | the same rooms scaled **0.85** (gateway 0.60) |
| Roof | z = 6.0 → 6.4 | covers the full 50 × 40 m plan **except** the 20 × 20 m courtyard |
| Central teal dome | 0, 17.5, 11.9 | r4.6 on a marble drum, gold spire, apex 23.8 m |
| 4 golden domes | (±21, 21) and (±21, −11.5) | r2.1 chhatri domes on the roof corners |

### Palette — golden sandstone (Amber Fort / Jaisalmer)

| Material | sRGB hex | Use |
|---|---|---|
| `Mahal_Wall_Sandstone` | **#D9C089** | main exterior masonry |
| `Mahal_Wall_Cream` | #EDDBB3 | light shade / parapet merlons / darbar tiles |
| `Mahal_Wall_Tan` | #B39466 | dark shade / Mehrab outer frame / ranivas dividers |
| `Mahal_SandstoneFloor` | #C9AC7C | floor slabs |
| Gold / Teal / DeepBlue / Yellow | unchanged | trim, domes, doors, windows |

## 🧱 Modular Buildings — `docs/models/buildings_modular/`

The kit is on a **15 m grid** (3 m storeys, 0.2 m slabs, 0.2 m exterior walls, 0.10 m interior partitions).
`assemble_buildings.py` places every bay, slab, stair, partition and furniture piece at an exact X / Y / Z
coordinate — no random geometry.

| Building | Grid / size | Floors | Walls + roof | Rooms | Furniture | Tris |
|---|---|---|---|---|---|---|
| `house_blue.glb` | 2×2 · 30.3 × 30.3 × 9.0 m | 2 | Bright Blue + Dark Grey hip | 3/floor | 2 beds, 2 tables, 2 counters, 2 shelves, 6 crates | 3,962 |
| `school_yellow.glb` | 3×2 · 45.3 × 30.3 × 6.7 m | 2 | School Yellow + flat concrete + parapet | 7 (5 m hall + 6 rooms) | 12 tables, 6 shelves, 3 counters, 6 crates | 6,894 |
| `apartment_green.glb` | 2×2 · 30.3 × 30.3 × 9.7 m | 3 | Concrete Green + flat concrete | 3/floor (9) | 4 beds, 3 tables, 3 shelves, 2 counters, 9 crates | 6,416 |
| `warehouse_metal.glb` | 3×2 · 45.3 × 30.3 × 3.7 m | 1 | Steel Blue + Rust Orange + 6 m garage | 7 (aisle + 6 bays) | 18 crates, 4 shelves, 3 tables | 4,664 |
| `cabin_wood.glb` | 1×1 · 15.3 × 15.2 × 6.0 m | 1 | Wood Brown + red hip | 2 | 1 bed, 1 table, 1 counter, 1 shelf, 2 crates | 1,120 |
| `ruined_building.glb` | 2×2 · 30.3 × 30.3 × 6.1 m | 2 | Damaged Concrete, no roof, 5 Boolean holes, 20 % faces deleted, rubble | 3/floor, shattered | 8 crates, 2 shelves + 9 rubble | 3,736 |
| `shop_row.glb` | 2×1 · 30.3 × 17.4 × 6.0 m | 1 | Off-White + red slanted + 2 awnings | 2 shops + connecting door | 4 counters, 3 shelves, 2 tables, 2 crates | 1,932 |
| `villa_white.glb` | L-shaped 2×2 · 30.3 × 30.3 × 9.0 m | 2 | Off-White + flat roof + roof terrace | 3/floor (6) | 4 sofas, 3 tables, 2 beds, 2 shelves, 2 counters, 4 crates | 4,398 |
| `farmhouse_stone.glb` | 2×1 · 30.3 × 15.3 × 6.0 m | 1 | Brick Red + terracotta hip | 2 | 1 bed, 3 tables, 2 shelves, 5 crates | 1,980 |
| `bunker_military.glb` | 1×1 · 15.3 × 15.2 × 3.7 m | 1 | Dark Camo Green + camo banding, no windows | 2 | 1 bed, 1 shelf, 6 crates | 1,700 |
| `tower_sniper.glb` | 1×1 · 15.3 × 15.3 × 13.0 m | 4 | Concrete Grey, open top + 0.95 m parapet | 2/floor (8) | 2 crates, 1 shelf | 2,966 |

### Interior rooms

Every storey is divided by **0.10 m partition walls** so the buildings have bedrooms, hallways and living rooms
instead of one empty shell. The plans are declarative (`plan=` on each recipe) and the rooms are *derived* by splitting
the footprint outline with each wall, so furniture placement knows exactly which room it is in.

| Plan | Buildings | Result |
|---|---|---|
| `middle` + jog | `house_blue`, `apartment_green`, `ruined_building` | 15 m wall + 7.5 m jog → living room, hallway, bedroom |
| `hallway` (5 m) | `school_yellow`, `warehouse_metal` | central hallway full length + 3 rooms either side (7 rooms/floor) |
| `cross` | `cabin_wood`, `bunker_military`, `tower_sniper` | one 15 m wall → front room + bedroom on every floor |
| `middle` | `shop_row`, `farmhouse_stone` | two 15 × 15 m rooms joined by one doorway |
| `custom` | `villa_white` | spine wall + wing wall through the L-shape → 3 rooms/floor |

**Build-time guarantees** — the assembler refuses to export if a partition blocks a doorway, crosses the staircase or
leaves a room unreachable.

## 🌍 Terrain — `docs/models/terrain/`

| File | Size (real-world) | Details | Texture |
|---|---|---|---|
| `terrain_ground.glb` | 1000 × 1000 m | flat base island ground plane | `grass_1k.png` |
| `terrain_hill_large.glb` | 80 × 80 × 40 m | jagged low-poly mountain; rock slopes + grassy top | `rock_stone_1k.png` + `grass_1k.png` |
| `terrain_plateau.glb` | 200 × 200 × 15 m | elevated flat plateau with walk-up ramps on 4 sides | `grass_1k.png` |
| `terrain_valley.glb` | 200 × 200 × 15 m | 15 m deep V-shaped valley cutout with steep rocky walls | `grass_1k.png` + `rock_stone_1k.png` |

## 🖥️ Running Locally

```bash
# 1. Install Blender as a Python module (Python 3.11 → bpy 5.0.x) + texture deps
pip install bpy pillow numpy

# 2. Regenerate the three shipped sets
python tools/generate_terrain.py
python tools/generate_mahal_rooms.py
python tools/generate_building_modules.py
python tools/assemble_buildings.py
rm -rf docs/models/modules        # intermediate kit, not published

# 3. Serve the viewer locally
python -m http.server 8000 --directory docs
# → open http://localhost:8000 in a browser
```

## 🛠️ Tech Stack

* **3D engine:** Blender via the `bpy` Python API (`pip install bpy`)
* **Materials:** solid Principled BSDF colours (sRGB → linear), emissive accents where needed; terrain uses two 1K PBR maps
* **Frontend viewer:** HTML / JS / Google `<model-viewer>`
* **CI/CD:** GitHub Actions (`configure-pages@v5`, `upload-pages-artifact@v3`, `deploy-pages@v4`)
* **Hosting:** GitHub Pages

## 📜 License

All procedurally generated assets in this repository are created in-house and are free to use for the
"Indus : Battle Royale" project.
