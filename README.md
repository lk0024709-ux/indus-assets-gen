# 🎨 Indus : Battle Royale — 3D Asset Generator

Production asset pipeline for **Indus : Battle Royale**. Every model in this repository is generated procedurally with
**Blender Python (`bpy`)**, exported as a packed `.glb`, and published to a web viewer on **GitHub Pages**.

## 🚀 Live 3D Web Viewer

👉 **[lk0024709-ux.github.io/indus-assets-gen](https://lk0024709-ux.github.io/indus-assets-gen/)**

The gallery is deliberately small — it ships **only the production asset sets**:

| # | Category | Assets | Source | Where |
|---|---|---|---|---|
| 0 | 🧑 **Characters** | **17 assets** — 1 rigged + animated player (Idle/Walk) plus a 16-strong pool (1.80 m, **0 textures**) | `tools/rig_character.py`, `tools/convert_character_obj.py`, `tools/convert_characters_batch.py` | `docs/models/characters/` |
| 1 | 🛩 **Vehicles** | 1 Elite Cargo Dropship (45 m span) | `tools/generate_plane_cargo_elite.py` | `docs/models/vehicles/` |
| 2 | 🏯 **The Grand Mahal** | 1 assembled palace (+ 4 room blocks used to build it) | `tools/generate_mahal_rooms.py` | `docs/models/mahal/` |
| 3 | 🧱 **Modular Buildings** | 11 coloured blocks with real interior rooms | `tools/generate_building_modules.py` + `tools/assemble_buildings.py` | `docs/models/buildings_modular/` |
| 5 | 🌳 **Nature** | 3 low-poly trees — pine 9 m, oak 9 m, palm 12 m (solid colours) | `tools/generate_trees.py` | `docs/models/nature/` |
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
4. **CI/CD** — `.github/workflows/deploy.yml` installs `bpy`, runs the eight generator steps, drops the intermediate
   module kit from the published site and deploys `docs/` to GitHub Pages on every push to `main`.
5. **Viewer** — `docs/index.html` is a small, dependency-light Google `<model-viewer>` gallery built from a JS array of
   categories, with a category filter and a hero card for the palace.

## 📂 Project Structure

```
tools/
  convert_character_obj.py     # Male_Suit.obj -> solid-colour player_tactical.glb (imports the OBJ, recolours, joins, exports)
  convert_characters_batch.py  # every other docs/models/Character/*.obj -> solid-colour GLBs + manifest + gallery.js
  character_lib.py             # shared import/recolour/shade/export/verify helpers for both character tools
  generate_trees.py            # 3 low-poly trees: pine, oak, palm (solid colours, flat shaded)
  rig_character.py             # 17-bone armature + skinning + Idle/Walk -> player_animated.glb
  generate_modular_character.py # nude body_base.glb + clothing_shirt.glb + clothing_pants.glb (shared rig)
  generate_terrain.py          # 4 terrain tiles (1000 m ground, hill, plateau, valley)
  generate_mount_abu.py        # 150 m hill station: mesa + corniche road + Nakki Lake + collision
  generate_mahal_rooms.py      # 4 walk-in rooms + assemble_mahal() -> rajasthani_mahal_mega.glb
  generate_building_modules.py # 15 m modular kit (walls, partitions, slabs, roofs, stairs, furniture)
  assemble_buildings.py        # 11 building recipes -> one joined mesh each
  generate_plane_cargo_elite.py# Elite Cargo Dropship (Vehicles category)

docs/                          # GitHub Pages site (viewer + models)
  models/characters/           # 16 static + player_animated.glb (rigged) + body_base/clothing_shirt/clothing_pants
                               # + characters.json + gallery.js + modular_character.json
  index.html                   # 4-category gallery
  models/mahal/                # Grand Mahal (mega assembly + rooms/)
  models/buildings_modular/    # the 11 modular buildings
  models/terrain/              # Mount Abu (+ collision proxy) and the 4 tiles
  models/vehicles/             # plane_cargo_elite.glb
  models/nature/               # tree_pine.glb, tree_oak.glb, tree_palm.glb
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

### Rigged & animated — `rig_character.py`

`player_animated.glb` is the same 1.80 m mesh, skinned to a **17-bone armature** and shipped with two baked clips.
Stock `bpy` only — no add-ons, no plugins. Every joint position is derived from the 1.80 m height.

| Bone chain | Coordinates (Blender Z-up, metres) |
|---|---|
| `Hips` → `Spine` → `Chest` → `Neck` → `Head` | z = 0.9 → 1.0 → 1.2 → 1.4 → 1.5 → 1.8 |
| `UpperArm.[LR]` → `LowerArm` → `Hand` | shoulder (±0.2, 0, 1.4) → elbow (±0.205, 0, 1.10) → wrist (±0.21, 0, 0.86) → fingertip (±0.20, 0, 0.62) |
| `UpperLeg.[LR]` → `LowerLeg` → `Foot` | hip (±0.15, 0, 0.9) → knee (±0.15, 0, 0.48) → ankle (±0.16, 0, 0.10) → toe |

**Clips (30 fps, 30 frames = 1.25 s each, both loop)**

* `Idle` — chest rises **20 mm** at frame 15 and returns, plus a 2° arm settle.
* `Walk` — **±30°** arm and leg swing from `cos()`, knee follow-through a quarter cycle behind, chest
  counter-rotation, a **70 mm hip drop** from `sin()` at the stride extremes, and ankle counter-rotation to keep the
  soles level. Frame 1 and frame 30 are identical, frame 15 is the exact reverse.

#### Four things that needed real work

1. **Bone-heat weighting silently fails here.** `parent_set(type='ARMATURE_AUTO')` returns `FINISHED` and creates the
   vertex groups while assigning **zero weight** — the character is a set of disconnected shells (hands, shoes, hair are
   separate islands). The tool measures total weight, detects the failure, and falls back to a deterministic
   material-aware inverse-distance solver. Pure distance alone is not enough either: the hands hang at `|x| ≈ 0.21`
   right beside the thigh bones at `|x| = 0.15`, so each vertex is restricted to an anatomically sane bone set keyed
   off its material (shoes → feet, hair/eyes → head, low skin → hands, trousers → legs + hips).
2. **`pose_bone.location.z` is not "up".** Bone-local space puts a bone's Y along head→tail, so for the vertical Chest
   bone the breathing lift is `location = (0, 0.02, 0)`; setting `.z` would slide the chest forward instead.
3. **The exporter can emit quaternion sign flips.** Neighbouring rotation keys ending up as `q` and `-q` are the same
   orientation numerically, but a player that normalised-lerps instead of slerping spins the limb nearly 180° for one
   frame. A post-export pass rewrites the binary chunk in place so consecutive keys share a hemisphere (84 keys fixed).
4. **Leftover pose channels leak between clips.** Blender only overrides the channels an action actually animates, so
   Idle's 20 mm chest lift stayed in the pose when Walk was applied — and because the exporter samples the evaluated
   pose, it would have been baked into Walk as a permanent offset. The rig is reset before every action switch, and the
   tool asserts 0 mm deformation drift across the export.

The exported file is checked by re-parsing it: 1 skin, 17 joints, 8/8 primitives carrying `JOINTS_0`/`WEIGHTS_0`, every
one of the 1,965 vertices weighted, both clips present, and zero images.

### Modular character — `generate_modular_character.py`

The baked character is also available as **three separate files** that share one rig:

| File | Contents | Colour | Offset |
|---|---|---|---|
| `body_base.glb` | the whole body, every group collapsed to one material | `Body_Skin` `#D2A679` | — |
| `clothing_shirt.glb` | torso + upper arms | `Cloth_Shirt` `#2F6FB5` | **18 mm** |
| `clothing_pants.glb` | legs | `Cloth_Pants` `#141414` | **12 mm** |

All three carry the **same 17-bone armature and the same `Idle` + `Walk` clips**, and every garment vertex inherits the
body's own weights by source index, so any combination deforms in lockstep. Drop a new outfit in later by generating it
the same way — nothing about the body changes. Tested by rendering the assembled character with the body coloured
magenta: the only magenta left is head, hands and feet.

#### Why the clothes are offset along normals, not scaled

The brief asked for "scaled up by 1.05 on X and Z". In a Z-up frame that scales horizontal X and vertical Z but leaves
**Y (depth) untouched**, so the chest and back sit *inside* the shirt — the exact bug the scaling was meant to prevent.
It also moves a shoulder further than a wrist, because the displacement grows with distance from the origin. Offsetting
each vertex along its own smooth normal instead, by a real distance in metres, is what actually clears the body:

```
                                  coverage of the body   clearance (min)
brief's literal scale 1.05 X/Z      37% / 29%              0.17 / 0.23 mm   <- z-fighting
this tool, 18 mm / 12 mm            95% / 91%              9.0 / 3.0 mm
```

(`--compare-scale` prints both. Coverage is measured by casting a ray from every body vertex this garment replaces,
along that surface's own outward normal, and asking whether the cloth is there.)

#### Five things that needed real work

1. **The source is unwelded.** Every quad carries its own four vertices — the 240 jacket quads arrive as 940 vertices at
   256 positions — so a per-vertex normal is just a per-face normal and the offset tears the panel at every crease.
   Normals are averaged **per position** instead.
2. **`recalc_face_normals` flips the trousers inside-out.** It can make an open shell *consistent* but has no way to
   know which side is out, and on this asset it picks the wrong one for the whole `Pants` group: the trousers are then
   displaced 18 mm into the legs and vanish inside the body. The authored winding is already correct — every material
   group has **zero inconsistent edges** — so it is trusted as-is, and the build asserts it stays that way.
3. **Orienting normals "away from the nearest bone" looks right and is wrong.** The hands hang level with the thighs,
   so vertices on the outer thigh take `Hand.L` as their nearest bone and get flipped inwards — the same trap that
   tears distance-only skinning.
4. **The group names lie.** `Shirt` is only the suit *jacket*; the panel of shirt visible between its lapels is a
   separate shell under `TieTexture`, and collar, cuffs and belt are under `Details`. Taking all three is what gives a
   garment that actually covers the torso — the earlier build rendered as an open jacket with a bare chest.
5. **The two hems meet exactly at the waist** (both at z = 0.915) and the trousers' waist dips into a V, so with equal
   offsets the bare body shows through a wedge-shaped seam. Dragging the shirt hem down instead pushes it *into* the
   seat, because the body bulges below the waist. The trousers are made the inner layer (12 mm, rims tucked, waistband
   raised 48 mm up under the shirt) and the seam closes.

The build fails on any folded face, any inconsistent edge, or any garment covering less than 85 % of the body it
replaces, so a garment that would let skin show through cannot be deployed. Output verified with the Khronos
glTF validator: **0 errors / 1 warning / 0 infos** per file — the warning is the deliberate
`NODE_SKINNED_MESH_NON_ROOT` documented on `export_glb` — 1 skin, 17 joints, 0 images, 2 clips.

### The rest of the pool — `convert_characters_batch.py`

`convert_character_obj.py` builds the hand-tuned player. Every other raw OBJ in `docs/models/Character/` goes through
`convert_characters_batch.py`, which applies the same import -> recolour -> join -> normalise -> export pipeline:

```
docs/models/Character/*.obj   ->   docs/models/characters/<name>.glb   (15 files)
                              ->   docs/models/characters/characters.json   (manifest)
                              ->   docs/models/characters/gallery.js        (viewer entries)
```

| Role | Applied to | Colour |
|---|---|---|
| skin | head, neck, hands, bare arms/legs | `#D2A679` |
| shirt | torso + arms + dress | **per-character tactical colour** |
| shirt accent | collar / shirt trim / light jacket panels | shirt colour, lightened 18 % |
| pants | legs, shorts, socks | `#1A1A1A` |
| shoes | shoes (and soles hidden in the `Eyes` group) | `#101112` |
| hair | hair, hair base, eyebrows | `#241A18` |
| eyes / details / tie | eyeballs, belt + glasses, tie | `#F2F0EA` / `#5A616B` / `#16202B` |

**The shirt colour is seeded, not random.** `random.random()` would repaint every character on every deploy, so the
palette (Dark Blue, Forest Green, Grey, Brown, Navy, Olive, Maroon, Slate Blue) is shuffled once with a fixed seed and
dealt down the sorted file list. Deploys are byte-identical, and because the list is sorted each `Smooth_*` high-poly
twin is exactly 7 slots from its low-poly sibling, so the two never share a shirt colour (the tool asserts this).

`Male_Suit.obj` is skipped here — it is already `player_tactical.glb` with its fixed `#2C3E50` shirt, so the player is
not duplicated. Other robustness handled by the tool: `Eyebrows` / `HairBase` / `Hair2` / `Jacket` / `LightJacket` /
`Shirt2` / `Socks` / `Dress` groups all map to sensible roles, `Female_Dress` has no `Pants` group at all (bare legs),
and any unknown group falls back to neutral grey instead of failing.

## 🌳 Nature — Low-poly Trees (`docs/models/nature/`)

Three species for the map's biomes, all generated from maths by `generate_trees.py`, flat shaded, solid-coloured and
texture-free. Every trunk is a swept ring frustum with real outward normals, every cone is a closed cap + tip fan, and
each tree is one joined mesh with its origin at the bottom centre — so it drops onto terrain with no manual offset.

| Tree | Height | Tris | Where | Build |
|---|---|---|---|---|
| `tree_pine.glb` | **9.0 m** | 70 | Aravalli foothills / mountains | brown 8-sided trunk (0.28 → 0.19 m) + 3 stacked dark-green cones (r 2.35 / 1.78 / 1.20 m) that overlap so no gap shows between tiers |
| `tree_oak.glb` | **9.0 m** | 508 | forests / villages | thick brown trunk (0.62 → 0.42 m) → 4 tapered branches → one flattened icosphere canopy with 4 offset lobes, bright green `#4E8B2F` |
| `tree_palm.glb` | **12.0 m** | 312 | beaches / lake shores | pale trunk swept along a 1.55 m arc, tapering 0.34 → 0.17 m, carrying 8 **ridged** fronds (raised centre spine, arch then droop) |

Two build notes worth keeping:

* The pine's three tiers step one shade lighter from `#1E4023` to `#2A582D` so the layers read as three distinct cones
  rather than one flat mass.
* The palm fronds are **ridged, not flat planes**. The first version used flat quads and they disappeared when viewed
  edge-on — fatal for a game camera. Three vertices per station (left, raised centre, right) give each frond volume
  for the cost of one extra quad per segment.

The generator asserts its own output: `minZ == 0`, height inside each species' band (8–10 m pine/oak, 11–12.5 m palm),
≤ 800 tris, and **zero images in the GLB**.

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

python tools/generate_modular_character.py    # body_base + clothing_shirt + clothing_pants

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
