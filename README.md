# 🎨 Indus : Battle Royale — 3D Asset Generator

Welcome to the automated 3D asset generation pipeline for **Indus : Battle Royale**.

This repository uses **Blender Python (`bpy`)** to procedurally generate low-poly, game-ready 3D models. The generated models are automatically exported as `.glb` files and hosted on a web-based 3D viewer via **GitHub Pages**.

## 🚀 Live 3D Web Viewer
Click the link below to view, rotate, and zoom the generated 3D models directly in your mobile or PC browser:
👉 **[View 3D Models Live Here](https://lk0024709-ux.github.io/indus-assets-gen/)**
*(The site is published automatically by the GitHub Actions pipeline below — every push to `main` regenerates and redeploys the assets).*

## ⚙️ How the Pipeline Works
1. **Textures:** Seamless tileable maps (`brick_wall`, `wood_plank`, `metal_corrugated`, `concrete_wall`) plus procedurally generated maps (`grass`, `grass_hero` with baked building shadows, `metal_rusted`) live in `docs/textures/`. The generator also bakes **vibrant tinted variants** (`brick_red`, `concrete_yellow`, `concrete_green`, `wood_warm`, `metal_steelblue`, `rust_orange`, `concrete_greydark`, `concrete_dark`, `wood_dark`) so the colour multiplies are stored in the texture pixels themselves — Blender's glTF exporter drops intermediate MixRGB tint nodes, but honours baked images.
2. **Code Generation:** `tools/generate_phase1.py` uses `bpy` (Blender as a Python module) to build terrain and buildings at real-world metre scale — boolean door/window cutouts, density-normalised `uv.smart_project()` unwrapping, and for every wall/floor material the chain **`Texture Coordinate (UV) → Mapping (Scale 0.3, 0.3, 0.3) → Image Texture (Extension REPEAT) → Base Color`** so bricks/wood/concrete tile at human scale with no stretching (exported to glTF as `KHR_texture_transform`). Point lights are exported as `KHR_lights_punctual`. Every building's origin sits exactly at its bottom-centre (0, 0, 0).
3. **Automated Export:** Models are exported as packed `.glb` files (`export_format='GLB'`, `export_image_format='JPEG'` so the textures pack inside the container) into `docs/models/`.
4. **CI/CD Deployment:** GitHub Actions (`.github/workflows/deploy.yml`) triggers on every push to `main`, installs `bpy`, runs the Phase 1 generator, and deploys the `docs/` folder to GitHub Pages.
5. **Web Viewing:** `docs/index.html` uses Google's `<model-viewer>` (generated dynamically from a JS array) with `environment-image="neutral"` and `shadow-intensity="1"` so the PBR textures and shadows read clearly on any device — a hero card shows the combined `scene_phase1.glb` world preview.

## 📂 Project Structure
*   `tools/generate_terrain.py` — **Phase 2 Terrain `bpy` generator** (`terrain_ground.glb`, `terrain_hill_large.glb`, `terrain_plateau.glb`, `terrain_valley.glb`).
*   `tools/generate_water.py` — **Phase 2 Water & Beach `bpy` generator** (`water_ocean.glb`, `water_river.glb`, `beach_sand.glb`, `dam_concrete.glb`).
*   `tools/generate_bridges.py` — **Phase 2 Bridges `bpy` generator** (`bridge_wood.glb`, `bridge_concrete.glb`).
*   `tools/generate_nature.py` — **Phase 2 Nature & Plants `bpy` generator** (`tree_pine.glb`, `tree_oak.glb`, `tree_dead.glb`, `rock_large.glb`, `rock_small.glb`, `bush.glb`, `grass_clump.glb`).
*   `tools/generate_phase1.py` — **Phase 1 `bpy` generator** (base ground + 6 buildings + hero scene).
*   `tools/generate_buildings.py` — original four-building generator (pre-Phase-1 assets).
*   `tools/generate_mahal_rooms.py` — **Phase 4 Room-by-Room Mahal `bpy` generator** (4 walk-in rooms → `assemble_mahal()` → one 50×40 m mega palace).
*   `tools/generate_building_modules.py` — **Phase 5 Lego module generator** (8 building blocks on a 10 m grid).
*   `tools/assemble_buildings.py` — **Phase 5 building assembler** (recipes for the 11 standard buildings).
*   `tools/generate_test.py` — pipeline smoke-test (brown test crate).
*   `tools/make_seamless.py` — makes the AI texture tiles perfectly seamless.
*   `docs/` — The root folder for GitHub Pages.
*   `docs/index.html` — The 3D web viewer (dark UI, mobile responsive, categorized into Terrain, Water & Bridges, Nature, and Buildings).
*   `docs/textures/` — Seamless 1K texture maps (PNG), including `grass_1k.png`, `rock_stone_1k.png`, `wood_plank_1k.png`, `concrete_wall_1k.png`, `sand_1k.png`, `water_1k.png`.
*   `docs/models/terrain/` — Terrain `.glb` models.
*   `docs/models/water/` — Water, beach, and dam `.glb` models.
*   `docs/models/bridges/` — Wooden and concrete bridge `.glb` models.
*   `docs/models/nature/` — Trees, rocks, bushes, and grass `.glb` models.
*   `docs/models/buildings/` — Building `.glb` files (textures packed inside).
*   `docs/models/mahal/rooms/` — 4 walk-in room blocks (`room_darbar_hall`, `room_courtyard`, `room_ranivas`, `room_gateway`).
*   `docs/models/mahal/rajasthani_mahal_mega.glb` — the assembled palace (one joined mesh).
*   `docs/models/modules/` — the 8 modular building blocks (`mod_wall_solid`, `mod_wall_window`, `mod_wall_door`, `mod_wall_garage`, `mod_floor`, `mod_roof_flat`, `mod_roof_slanted`, `mod_stairs`).
*   `docs/models/buildings/modular/` — the 11 buildings assembled from those modules.
*   `.github/workflows/deploy.yml` — CI/CD pipeline: generate Phase 1 + Phase 2 assets and deploy to Pages.

## 🌍 Phase 2 Assets — Complete Map Environment
| Category | File | Size (real-world) | Details | 1K Texture |
|---|---|---|---|---|
| Terrain | `terrain_ground.glb` | 1000 m × 1000 m | Flat base island ground plane | `grass_1k.png` |
| Terrain | `terrain_hill_large.glb` | 80 m × 80 m × 40 m | Jagged low-poly mountain; rock slopes + grassy top | `rock_stone_1k.png` + `grass_1k.png` |
| Terrain | `terrain_plateau.glb` | 200 m × 200 m × 15 m | Elevated flat plateau with sloped walk-up ramps on 4 sides | `grass_1k.png` |
| Terrain | `terrain_valley.glb` | 200 m × 200 m × 15 m | 15 m deep V-shaped valley cutout with steep rocky walls | `grass_1k.png` + `rock_stone_1k.png` |
| Water & Beach | `water_ocean.glb` | 4000 m × 4000 m | Semi-transparent blue ocean plane (`alpha = 0.6`) | `water_1k.png` |
| Water & Beach | `water_river.glb` | 400 m × 30 m channel | Curved river mesh with semi-transparent water (`alpha = 0.6`) | `water_1k.png` |
| Water & Beach | `beach_sand.glb` | 1000 m × 1000 m (50 m band) | 50 m wide shoreline sand ring where grass meets water | `sand_1k.png` |
| Water & Beach | `dam_concrete.glb` | 50 m × 5 m × 20 m | Concrete hydro dam wall with curved arch front face | `concrete_wall_1k.png` |
| Bridges | `bridge_wood.glb` | 20 m × 4 m × 4.3 m | Wooden walkway with side railings and support pillars | `wood_plank_1k.png` |
| Bridges | `bridge_concrete.glb` | 40 m × 8 m × 6.7 m | Concrete highway bridge with high side barriers and thick pillars | `concrete_wall_1k.png` |
| Nature | `tree_pine.glb` | 3.7 m × 3.7 m × 8.0 m | 8 m tall pine: cylinder trunk + 3 stacked cones | `wood_plank_1k.png` + `grass_1k.png` |
| Nature | `tree_oak.glb` | 3.8 m × 3.3 m × 6.0 m | 6 m tall oak: thick trunk + low-poly green canopy | `wood_plank_1k.png` + `grass_1k.png` |
| Nature | `tree_dead.glb` | 3.6 m × 2.6 m × 5.5 m | Gnarled trunk with bare jagged branches | `wood_plank_1k.png` |
| Nature | `rock_large.glb` | 3.0 m × 3.0 m × 2.0 m | Displaced low-poly icosphere boulder | `rock_stone_1k.png` |
| Nature | `rock_small.glb` | 1.0 m × 1.0 m × 0.8 m | Displaced low-poly icosphere field stone | `rock_stone_1k.png` |
| Nature | `bush.glb` | 1.9 m × 1.3 m × 1.25 m | Cluster of 3 low-poly green spheres | `grass_1k.png` |
| Nature | `grass_clump.glb` | 0.85 m × 0.74 m × 0.90 m | 3 crossed planes with double-sided green material | `grass_1k.png` |

## 🧱 Phase 5 — Modular Buildings: 8 Lego modules → 11 buildings
`tools/generate_building_modules.py` builds the kit, `tools/assemble_buildings.py` imports it and places the pieces at
exact X / Y / Z coordinates on a **10 m grid** (3 m storeys, 0.2 m slabs). Every module and every assembled building
has a **bottom-centre `(0,0,0)`** origin and is flat shaded with solid Principled materials.

### The kit — `docs/models/modules/`
| Module | Size | Details | Tris |
|---|---|---|---|
| `mod_wall_solid.glb` | 10 × 0.2 × 3 m | plain panel | 12 |
| `mod_wall_window.glb` | 10 × 0.38 × 3 m | 1.5 × 1.5 m opening, sill 1.0 m, ledge + lintel | 56 |
| `mod_wall_door.glb` | 10 × 0.30 × 3 m | 1.5 × 2.2 m walk-through door, jambs + head | 64 |
| `mod_wall_garage.glb` | 10 × 0.42 × 3 m | 6.0 × 2.6 m roller door, roller box + tracks | 64 |
| `mod_floor.glb` | 10 × 10 × 0.2 m | slab with expansion grooves | 60 |
| `mod_roof_flat.glb` | 10 × 10 × 0.66 m | 0.4 m parapet + sandstone coping | 108 |
| `mod_roof_slanted.glb` | 10 × 10 × 2.64 m | hip roof, 2.6 m ridge, wood cap + eaves | 44 |
| `mod_stairs.glb` | 2 × 3 × 2 m | 10 steps × 0.2 m rise (0.3 m tread) | 144 |

Palette: **Sandstone `#D9C089`, Brick Red `#9E4B3C`, Concrete Grey `#B4B4AE`, Wood `#8B5A2B`** (hex → linear conversion so the
GLB shows the intended colour).

### The buildings — `docs/models/buildings/modular/`
| Building | Grid | Floors | Roof | Size | Tris | Modules |
|---|---|---|---|---|---|---|
| `house_small.glb` | 2×2 | 1 | slanted | 20.1 × 20.2 × 5.6 m | 576 | 13 |
| `cabin_wood.glb` | 1×1 | 1 | slanted | 10.2 × 10.1 × 5.6 m | 292 | 6 |
| `house_tactical.glb` | 2×2 | 2 | slanted | 20.2 × 20.2 × 8.6 m | 1,460 | 27 |
| `school_yellow.glb` | 3×2 | 2 | flat | 30.2 × 20.2 × 6.7 m | 2,704 | 40 |
| `apartment_green.glb` | 2×2 | 3 | flat | 20.2 × 20.2 × 9.7 m | 2,856 | 43 |
| `warehouse_metal.glb` | 3×2 | 1 | flat | 30.0 × 20.1 × 3.7 m | 1,268 | 22 |
| `warehouse.glb` | 3×2 | 1 | flat | 30.0 × 20.1 × 3.7 m | 1,268 | 22 |
| `garage.glb` | 1×1 | 1 | flat | 10.0 × 10.1 × 3.7 m | 268 | 6 |
| `sniper_tower.glb` | 1×1 | 4 | flat | 10.2 × 10.2 × 12.7 m | 1,676 | 24 |
| `ruined_building.glb` | 2×2 | 2 | none | 20.2 × 20.2 × 6.3 m | 1,167 | 26 |
| `shop_row.glb` | 2×1 | 1 | slanted | 20.0 × 11.2 × 5.6 m | 452 | 9 |

`ruined_building` gets a BMesh pass that deletes 18 % of its faces (seed 11) plus 7 rubble blocks. The original
hand-detailed Phase-1 buildings remain in `docs/models/buildings/` — the modular set is a parallel, swap-in version.

## 🏯 Phase 4 — Rajasthani Mahal: Room-by-Room Modular Assembly
`tools/generate_mahal_rooms.py` builds four **walk-in** rooms from solid vibrant materials (no textures), each with its origin at
**bottom-centre (0, 0, 0)** and its floor exactly at `z = 0`, then welds them into one palace with `assemble_mahal()`.

| Room | File | Size | Highlights |
|---|---|---|---|
| Darbar Hall (throne room) | `models/mahal/rooms/room_darbar_hall.glb` | 20 m × 15 m × 6.07 m | 54 teal/cream checkered tiles, raised 1 m dais, golden throne + red cushion + canopy, 8 pillars with red/blue/yellow bands, 4 deep-blue arched windows, 2 jali lattices (bar lengths solved from the arch equation) |
| Courtyard Aangan | `models/mahal/rooms/room_courtyard.glb` | 20 m × 20 m (open sky) | Marble fountain dead centre (0,0), sandstone/marble checker floor, arched jharokha walkways on all 4 sides — 24 columns, 16 Boolean arches, central 3 m bay left open as passage, 4 teal chhatris on the rim |
| Ranivas (residential) | `models/mahal/rooms/room_ranivas.glb` | 15 m × 10 m × 6 m | Two rooms + marble corridor, 90 protruding coloured cubes in a chevron pattern, 2 protruding balconies with gold railings and pyramid roofs |
| Gateway | `models/mahal/rooms/room_gateway.glb` | 15 m × 5 m (8.4 m block) | 5-lobed scalloped **Mehrab** built from semicircular foils on a semi-ellipse, pink + gold two-layer frame, double wooden doors swung 65° open, flanking chhatri turrets |

### Palette — Golden Sandstone (Amber Fort / Jaisalmer)
The Mahal exterior is no longer salmon pink. Every wall material is **golden sandstone `#D9C089`**, with **cream `#EDDBB3`**
highlights and **tan `#B39466`** carving shadows — this covers the room set *and* the 50×50 m Hot Drop fortress, whose
`sandstone_1k.png` map was regenerated as golden sandstone (mean ≈ `#D3BB8A`). Gold trim, teal domes and deep-blue
doors/windows were deliberately left untouched. Because Blender/glTF base colours are stored **linear**, the script converts
the sRGB hex through a `hex_color()` helper (`0.85/0.75/0.55` typed straight in would render as a washed-out `#EDE0C4`).

| Material | sRGB hex | Notes |
|---|---|---|
| `Mahal_Wall_Sandstone` | **#D9C089** | main exterior masonry |
| `Mahal_Wall_Cream` | #EDDBB3 | light shade / parapet merlons / darbar tiles |
| `Mahal_Wall_Tan` | #B39466 | dark shade / Mehrab outer frame / ranivas dividers |
| `Mahal_SandstoneFloor` | #C9AC7C | floor slabs |
| Gold / Teal / DeepBlue / Yellow | unchanged | gold trim, teal domes, deep-blue doors & windows |

The same palette is applied in `generate_mahal_rooms.py`, `generate_mahal_master.py` (procedural brick + checker ramps),
`generate_mahal_vibrant.py` (2K `palace_wall_tiles_2k.png` diamonds + parapet solids) and `generate_modular.py`
(`SandstoneWall`).

### Assembly (`assemble_mahal()`) — exact layout
| Piece | Position (x, y, z) | Notes |
|---|---|---|
| `room_courtyard` | **0, 0, 0** | anchor of the whole palace |
| `room_darbar_hall` | **0, 17.5, 0** | north |
| `room_ranivas` | **17.5, 0, 0** and **−17.5, 0, 0** | east / west (west rotated 180° so balconies face out) |
| `room_gateway` | **0, −12.5, 0** | south |
| Second floor | z = 6.4 | same darbar + ranivas rooms scaled **0.85**, gateway scaled 0.60 on the gate roof |
| Roof | z = 6.0 → 6.4 | covers the full 50 × 40 m plan **except** the 20 × 20 m courtyard |
| Central teal dome | 0, 17.5, 11.9 | r4.6 on a r4.7 marble drum, gold spire, apex 23.8 m |
| 4 golden domes | (±21, 21) and (±21, −11.5) | r2.1 chhatri domes on the roof corners |

Everything is joined into **one mesh** (`rajasthani_mahal_mega`) — 54 m × 40.5 m × 23.8 m, 62,542 tris, 12 materials, min Z = 0.000.
Corner service wings fill the cross-plan voids so the ground plane is continuous (no gaps to fall through).
Origin of the mega file = courtyard centre at ground level `(0, 0, 0)`; North is Blender **+Y** (glTF **−Z** after the Y-up conversion).

## 🏗️ Phase 1 Assets
| File | Size (real-world) | Details | Texture |
|---|---|---|---|
| `base_ground.glb` | 100 m × 100 m flat plane | Ground for the preview; origin = surface centre | `grass.png` |
| `house_tactical.glb` | 10 m × 8 m · 2 floors | **Red-brown brick**, wooden porch, balcony, rusty metal gable roof, back fire escape — **all 4 doors swing inward** (opposite side); interior stairs + furniture + OmniLights | `brick_red` + `wood_dark` + `rust_orange` |
| `school_yellow.glb` | 14 m × 10 m · 2 floors | **Bright yellow concrete** school: corridor partition, classrooms with desks on both floors, one 32° stair through an exact 3 m × 1.5 m slab hole, flat roof + parapet | `concrete_yellow` + `wood` |
| `apartment_green.glb` | 12 m × 10 m · 3 floors | **Vibrant green concrete**; switchback stairs connect all 3 floors **and** the flat roof (exact 3 m × 1.5 m Boolean holes in every slab) | `concrete_green` |
| `cabin_wood.glb` | 8 m × 6 m · 1 floor | **Warm brown wood** cabin: pitched rust roof, brick chimney, porch, shuttered windows, one OmniLight | `wood_warm` + `rust_orange` + `brick_red` |
| `warehouse_metal.glb` | 20 m × 12 m · 1 floor | **Split colourway: steel-blue walls + rusty orange roof/doors**; two open 6 m garage doors, side personnel door, dark concrete floor, crate cover | `metal_steelblue` + `rust_orange` |
| `ruined_building.glb` | 10 m × 8 m · 2 floors | **Darkened grey concrete**; BMesh random face deletion, bare doorway/window cutouts (**no door leaf or window shutters**), exposed rebar, rubble piles, no intact roof (stairs still passable) | `concrete_greydark` + `metal_rusted` |
| `scene_phase1.glb` | 100 m × 100 m world | Hero scene: ground + all six buildings + baked soft shadows | packed tinted PBR set |

### 🔺 Critical construction rules (enforced in code)
* **Stairs (trigonometry):** `step_depth = 0.2 / math.tan(math.radians(32))` → every flight climbs at exactly **32°**. Each floor slab above a flight gets an exact **3 m × 1.5 m Boolean Difference hole** (the head-room swept volume over the final 3 m of run), and the stairs are placed exactly there.
* **Texture scale (UV):** every wall/floor material is `TexCoord (UV) → Mapping (Scale 0.3) → Image Texture (REPEAT) → Base Color`, with per-object UV density normalised to `1 / (0.3 × tile_size)` world UV/m — bricks, planks and panels stay human-sized and tile without stretching.
* **Colour:** vibrant tinted textures per building (red brick house, yellow school, green apartment, warm-brown cabin, steel-blue + rust warehouse, dark-grey ruin); tint is baked into the PNG pixels because the glTF exporter drops MixRGB tint nodes.
* **Perfect-fit OPENings:** doors 1.5 m W × 2.2 m H and windows 1.2 m × 1.2 m (sills 1.0 m) are cut with Boolean Difference, then hung **open with leaves/shutters sized exactly to the opening** — leaf exactly 1.5 × 2.2, each shutter exactly 0.6 × 1.2, full height with the top flush with the opening head, and **hinges exactly on the opening's side edges** (no float, no undersize, no gap at the hinge). Openings stay passable: **no glass, no blockers**; garage openings hang a roll bundle exactly matching their 6 m width.
* **Interiors:** internal floors/ceilings use dark tinted concrete/wood (never plain white), roof material covers the roof underside, bed · table · crates for cover, warm OmniLights inside every building.

## 🖥️ Running Locally
```bash
# 1. Install Blender as a Python module (Python 3.11 → bpy 5.0.x) + texture deps
pip install bpy pillow numpy

# 2. Generate Phase 1 assets (terrain + 6 buildings + hero scene)
python tools/generate_phase1.py

# 3. Serve the viewer locally
python -m http.server 8000 --directory docs
# → open http://localhost:8000 in a browser
```

## 🛠️ Tech Stack
*   **3D Engine:** Blender (via `bpy` Python API — `pip install bpy`)
*   **Textures:** Seamless AI-generated texture maps, packed into the GLB as JPEG
*   **Frontend Viewer:** HTML / JS / Google `<model-viewer>`
*   **CI/CD:** GitHub Actions (`actions/configure-pages@v5`, `actions/upload-pages-artifact@v3`, `actions/deploy-pages@v4`)
*   **Hosting:** GitHub Pages

## 📜 License
All procedurally generated assets in this repository are created in-house and are free to use for the "Indus : Battle Royale" project.
