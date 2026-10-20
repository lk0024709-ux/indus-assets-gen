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
*   `tools/generate_building_modules.py` — **Lego module generator** (16 blocks: 8 structural bays/slabs/roofs/stairs + 2 interior partitions + 6 furniture pieces, 15 m grid).
*   `tools/assemble_buildings.py` — **Battle Royale building assembler** (11 recipes, wall + roof palettes, interior partition plans, room-aware furniture).
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
*   `docs/models/modules/` — the 16 modular blocks: `mod_wall_solid`, `mod_wall_window`, `mod_wall_door`, `mod_wall_garage`, `mod_floor`, `mod_roof_flat`, `mod_roof_slanted`, `mod_stairs`, interior `mod_wall_partition` + `mod_wall_partition_door` + furniture `mod_table`, `mod_bed`, `mod_crate`, `mod_shelf`, `mod_counter`, `mod_sofa`.
*   `docs/models/buildings_modular/` — the 11 Battle Royale buildings assembled from those modules (furniture already joined in).
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

## 🧱 Battle Royale Buildings: 15 m grid, interior rooms, wall/roof palettes

`tools/generate_building_modules.py` builds the kit, `tools/assemble_buildings.py` imports it and places every bay,
slab, stair, **interior partition** and **furniture piece** at exact X / Y / Z coordinates on a **15 m grid**
(3 m storeys, 0.2 m slabs, 0.2 m exterior walls, 0.10 m partitions). Every module and every assembled building has a
**bottom-centre `(0,0,0)`** origin and is flat shaded with solid Principled materials. Each building is joined into
**one mesh** before export.

The 11 blocks read as different places at a glance — like a real Battle Royale map (Blue House, Yellow School,
Green Apartment) — so footprint, floor count, wall colour, roof type, **room plan** and furniture all change per
recipe. No floor is a single empty room any more: each one is divided into bedrooms, hallways and living rooms.

### The kit — `docs/models/modules/` (15 m grid)

| Module | Size | Details | Tris |
|---|---|---|---|
| `mod_wall_solid.glb` | 15 × 0.20 × 3 m | plain bay | 12 |
| `mod_wall_window.glb` | 15 × 0.38 × 3 m | two 1.5 × 1.5 m windows at x = ±3.6, sill 1.0 m | 100 |
| `mod_wall_door.glb` | 15 × 0.32 × 3 m | 1.5 × 2.2 m walk-through doorway | 64 |
| `mod_wall_garage.glb` | 15 × 0.44 × 3 m | 6.0 × 2.6 m garage opening | 64 |
| `mod_floor.glb` | 15 × 15 × 0.2 m | floor / ceiling slab | 60 |
| `mod_roof_flat.glb` | 15 × 15 × 0.66 m | 0.4 m parapet + coping (2 mats) | 108 |
| `mod_roof_slanted.glb` | 15 × 15 × 3.04 m | true hip roof, 3 m ridge + wood cap (2 mats) | 44 |
| `mod_stairs.glb` | 2.4 × 3.4 × 3.0 m | 10 steps × 0.3 m rise × 0.34 m tread, 2.4 m wide | 144 |
| `mod_wall_partition.glb` | 15 × 0.10 × 3 m | interior partition, half the exterior thickness | 12 |
| `mod_wall_partition_door.glb` | 15 × 0.22 × 3 m | partition + 1.5 × 2.2 m doorway + slim casing | 88 |
| `mod_table.glb` | 2.2 × 1.1 × 0.79 m | top + 4 legs + stretcher (2 mats) | 72 |
| `mod_bed.glb` | 2.12 × 1.35 × 0.8 m | frame, headboard, mattress, blanket, pillow (3 mats) | 108 |
| `mod_crate.glb` | 1.13 × 1.13 × 1.12 m | corner posts + battens — loot crate (2 mats) | 108 |
| `mod_shelf.glb` | 1.8 × 0.45 × 2.0 m | 4 boards, sides + back (2 mats) | 84 |
| `mod_counter.glb` | 2.75 × 0.92 × 1.28 m | body, overhang top, kick, cash box (3 mats) | 48 |
| `mod_sofa.glb` | 2.3 × 0.95 × 0.8 m | seat, back, 2 arms (2 mats) | 60 |

### Palettes (hex → linear so the GLB shows the intended colour)

| Walls | Roofs | Trims |
|---|---|---|
| Bright Blue `#2F6FBF` | Dark Grey `#43454A` | Blue Dark `#1E4E8C` |
| School Yellow `#E8C24A` | Rust Orange `#B4552E` | Yellow Dark `#B8952F` |
| Concrete Green `#5E9E5A` | Slanted Red `#8E3B31` | Green Dark `#3F7343` |
| Wood Brown `#8B5A2B` | Flat Concrete `#A8A8A2` | Wood Dark `#5E3A1B` |
| Brick Red `#9E4B3C` | Tiled Terracotta `#A9573C` | Brick Dark `#7A3A2E` |
| Off-White `#E8E4DA` | — | Stone Grey `#B8B2A6` |
| Steel Blue `#4A7C99` | — | Steel Dark `#35596E` |
| Damaged Concrete `#8C8C84` | — | Rubble Grey `#6E6E68` |
| Dark Camo Green `#414B36` + Camo Brown `#5B4A33` | — | Bunker Trim `#333B2A` |
| Concrete Grey `#B4B4AE` | — | Concrete Dark `#8E8E88` |

### The buildings — `docs/models/buildings_modular/`

| Building | Grid / size | Floors | Walls + roof | Rooms | Furniture | Tris |
|---|---|---|---|---|---|---|
| `house_blue.glb` | 2×2 · 30.3 × 30.3 × 9.0 m | 2 | Bright Blue + Dark Grey hip | 3 rooms/floor | 2 beds, 2 tables, 2 counters, 2 shelves, 6 crates | 3,962 |
| `school_yellow.glb` | 3×2 · 45.3 × 30.3 × 6.7 m | 2 | School Yellow + flat concrete + parapet | 7 (5 m hall + 6 rooms) | 12 tables, 6 shelves, 3 counters, 6 crates | 6,894 |
| `apartment_green.glb` | 2×2 · 30.3 × 30.3 × 9.7 m | 3 | Concrete Green + flat concrete | 3/floor (9) | 4 beds, 3 tables, 3 shelves, 2 counters, 9 crates | 6,416 |
| `warehouse_metal.glb` | 3×2 · 45.3 × 30.3 × 3.7 m | 1 | Steel Blue + Rust Orange + 6 m garage | 7 (5 m aisle + 6 bays) | 18 crates, 4 shelves, 3 tables | 4,664 |
| `cabin_wood.glb` | 1×1 · 15.3 × 15.2 × 6.0 m | 1 | Wood Brown + red hip | 2 | 1 bed, 1 table, 1 counter, 1 shelf, 2 crates | 1,120 |
| `ruined_building.glb` | 2×2 · 30.3 × 30.3 × 6.1 m | 2 | Damaged Concrete, **no roof**, 3 missing bays, 5 Boolean holes, 20 % faces deleted, rubble | 3/floor, shattered | 8 crates, 2 shelves + 9 rubble | 3,736 |
| `shop_row.glb` | 2×1 · 30.3 × 17.4 × 6.0 m | 1 | Off-White + red slanted + 2 awnings | 2 shops + connecting door | 4 counters, 3 shelves, 2 tables, 2 crates | 1,932 |
| `villa_white.glb` | L-shaped 2×2 · 30.3 × 30.3 × 9.0 m | 2 | Off-White + flat roof + walk-on roof terrace with pergola | 3/floor (6) | 4 sofas, 3 tables, 2 beds, 2 shelves, 2 counters, 4 crates | 4,398 |
| `farmhouse_stone.glb` | 2×1 · 30.3 × 15.3 × 6.0 m | 1 | Brick Red + terracotta tiled hip | 2 (kitchen + bedroom) | 1 bed, 3 tables, 2 shelves, 5 crates | 1,980 |
| `bunker_military.glb` | 1×1 · 15.3 × 15.2 × 3.7 m | 1 | Dark Camo Green + camo banding, **no windows**, flat roof | 2 (bunk + supply) | 1 bed, 1 shelf, 6 crates | 1,700 |
| `tower_sniper.glb` | 1×1 · 15.3 × 15.3 × 13.0 m | 4 | Concrete Grey, **open top** with 0.95 m parapet | 2/floor (8) | 2 crates, 1 shelf | 2,966 |

### Interior rooms

Every storey is divided by **0.10 m partition walls** so the buildings have bedrooms, hallways and
living rooms instead of one empty shell. The plans are declarative (`plan=` on each recipe) and the
rooms are *derived* by splitting the footprint outline with each wall, so furniture placement knows
exactly which room it is in.

| Plan | Buildings | Result |
|---|---|---|
| `middle` + jog | `house_blue`, `apartment_green`, `ruined_building` | 15 m wall down the middle + a 7.5 m jog wall → 15 m living room, 7.5 × 15 m hallway, 7.5 × 7.5 m bedroom (jog mirrored away from the staircase) |
| `hallway` (5 m) | `school_yellow`, `warehouse_metal` | 5 m central hallway full length + 3 rooms either side, each with its own doorway (7 rooms/floor) |
| `cross` | `cabin_wood`, `bunker_military`, `tower_sniper` | one 15 m wall → front room + bedroom on every floor |
| `middle` | `shop_row`, `farmhouse_stone` | two 15 × 15 m rooms joined by one doorway |
| `custom` | `villa_white` | 15 m spine wall + north wing wall through the L-shape → 3 rooms/floor |

Each run is built from `mod_wall_partition` bays with exactly one `mod_wall_partition_door`, grown by
10 cm at each end so the bays overlap and the end caps are buried inside the walls they meet.

**Build-time guarantees** (the script raises and refuses to export if any of these fail):

1. no partition cuts the staircase (2.4 × 3.4 m reserved box, 0.15 m pad);
2. no interior doorway sits in the stairwell, within 1.1 m of another wall, or within 2.4 m of the
   front door;
3. every room is reachable from the entrance through the doorway graph;
4. ray casts at 2.65 m through every partition hit solid geometry (bullets cannot pass through) and
   ray casts through every doorway pass cleanly;
5. no furniture footprint overlaps a partition, a doorway, the stairs or leaves its room.

### Furniture per room

Beds go to the bedroom, tables/shelves/counters/sofas to the living room & kitchen, and crates are
dealt round-robin to whichever room has the fewest pieces, so loot has to be searched for across the
whole building. Pieces are pushed against the nearest wall (headboards and shelf backs against it) on
a per-room 2.6 m lattice, 1.0 m off the walls.

### How the assembler works

* **Footprints** come from a cell list, so `villa_white` can be genuinely L-shaped (`[(0,0), (1,0), (0,1)]`);
  `exterior_edges()` finds only the outer perimeter, so there are no walls in the missing quadrant.
* **Wall bays** are chosen per side: `windows="all" | "alternate" | "none"`, plus recipe-declared
  `doors=[("S", 0, 0)]` and `garages=[("S", 1, 0)]` on the south face. Bunker passes `windows="none"`.
* **Stairs** land in a reserved 2.4 × 3.4 m box in a named cell corner, one flight per storey, and the slab above
  gets an exact Boolean hole (2.9 × 3.8 m cutter) so the flight breaks through.
* **Furniture** is placed on a 3 × 5 lattice of anchors 2.5 m apart inside every cell, deterministically shuffled,
  and an anchor is rejected if it is within 2.4 m of any doorway or 3.0 m of the stair — so nothing ever blocks a
  door or a flight. Beds/sofas prefer upper floors, crates/tables/counters the ground floor, spread round-robin.
* **Details**: 16° timber awnings on struts (`shop_row`), a roof terrace with deck, double railing, balusters and a
  4-slat pergola (`villa_white`), an open parapet top (`tower_sniper`), Boolean wall holes + rubble + BMesh face
  deletion (`ruined_building`, seed 11).
* **Export**: furniture is joined into the building's part list before the final `bpy.ops.object.join()`, so each
  `.glb` is one mesh with one material set → one `ConcavePolygonShape3D` for collision in Godot/Unity.

The old 10 m `docs/models/buildings/modular/` set was superseded by this one and is deleted by `deploy.yml`
(it produced same-named GLBs such as `school_yellow.glb`); the hand-detailed Phase-1 buildings in
`docs/models/buildings/` remain untouched.

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
